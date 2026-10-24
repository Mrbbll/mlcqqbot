"""轮询 Gitee 用户的公开 Push，并将提交通知回复到近期群消息。"""

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import monotonic
from urllib.parse import quote

from botpy.message import GroupMessage

from external_tools.gitee.client import GiteeApiClient, GiteeHTTPStatusError
from features.passive_notifications.context import (
    get_recent_message,
    next_reply_sequence,
    remember_group_message,
)

from config import (
    GITEE_MAX_COMMITS,
    GITEE_NOTIFY_GROUPS,
    GITEE_POLL_INTERVAL,
    GITEE_REQUEST_TIMEOUT,
    GITEE_TOKEN,
    GITEE_USERS,
)


_MAX_EVENT_PAGES = 10
_NOTIFICATION_INTERVAL = 60.0
_log = logging.getLogger("mlcbot")

client: GiteeApiClient | None = None
monitor_task: asyncio.Task | None = None
active_users: list[str] = []
check_lock = asyncio.Lock()
send_lock = asyncio.Lock()
notification_after: dict[str, float] = {}


@dataclass
class UserProgress:
    """保存单个 Gitee 用户在单个目标群的活动与提交进度。"""

    since: float
    seen_events: set[str]
    sent_commits: set[tuple[str, str]] = field(default_factory=set)
    queued_commits: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class PendingNotification:
    """保存等待近期群消息锚定的通知及其提交进度。"""

    text: str
    commits: tuple[tuple[str, str], ...]
    progress: UserProgress
    username: str
    event_id: str


user_state: dict[str, dict[str, UserProgress]] = {}
repo_descriptions: dict[str, tuple[float, str]] = {}
known_users: set[str] = set()
pending_notifications: dict[str, deque[PendingNotification]] = {}


def clear_progress() -> None:
    """清除 Gitee 活动基线与仓库描述缓存。"""
    user_state.clear()
    repo_descriptions.clear()
    known_users.clear()


async def fetch_user_events(username: str) -> list[dict]:
    """读取用户最近公开活动，并按群消息进度滚动分页。"""
    assert client is not None
    groups = user_state.get(username, {})
    progress = [groups[gid] for gid in GITEE_NOTIFY_GROUPS if gid in groups]
    common_seen = set.intersection(*(item.seen_events for item in progress)) if progress else set()
    events = []
    params = {"limit": 100}
    for _ in range(_MAX_EVENT_PAGES):
        try:
            response = await client.get(
                f"/users/{quote(username, safe='')}/events/public",
                params=params,
            )
        except GiteeHTTPStatusError as exc:
            if exc.status_code != 404:
                raise
            if username not in known_users:
                await client.get(f"/users/{quote(username, safe='')}")
                known_users.add(username)
            break
        batch = response.json()
        if not isinstance(batch, list) or any(
            not isinstance(event, dict)
            or not isinstance(event.get("id"), (str, int))
            for event in batch
        ):
            raise ValueError("Gitee 返回了无效的用户活动列表")
        known_users.add(username)
        events.extend(batch)
        if not progress or len(batch) < 100 or any(
            str(item["id"]) in common_seen for item in batch
        ):
            break
        if all(event_time(item) < min(item.since for item in progress) for item in batch):
            break
        cursor = str(batch[-1]["id"])
        if str(params.get("prev_id")) == cursor:
            raise ValueError("Gitee 活动分页游标未推进")
        params["prev_id"] = cursor
    else:
        raise ValueError("本轮新活动超过 1000 条，未推进发送进度")
    return events


def event_time(event: dict) -> float:
    """将 Gitee 活动时间转换为 Unix 时间戳。"""
    created = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone(timedelta(hours=8)))
    return created.timestamp()


def validate_repo(value: str) -> str:
    """校验 Gitee 活动中的仓库全名。"""
    if not isinstance(value, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        raise ValueError("Gitee 活动仓库 full_name 无效")
    return value


async def fetch_push_commits(event: dict) -> tuple[str, list[dict]]:
    """读取 Push 活动包含的完整提交详情。"""
    assert client is not None
    repo = validate_repo(event["repo"]["full_name"])
    payload = event["payload"]
    if payload.get("deleted") or payload.get("size") == 0:
        return repo, []
    listed = payload.get("commits") or []
    size = payload.get("size", len(listed))
    commits = []
    if listed and len(listed) >= size:
        for item in listed:
            sha = item["sha"]
            response = await client.get(f"/repos/{repo}/commits/{quote(sha, safe='')}")
            commits.append(response.json())
    elif payload.get("before") and set(payload["before"]) != {"0"}:
        before = quote(payload["before"], safe="")
        after = quote(payload["after"], safe="")
        response = await client.get(f"/repos/{repo}/compare/{before}...{after}")
        commits = response.json().get("commits")
        if not isinstance(commits, list) or len(commits) < size or (
            len(commits) == 100 and not size
        ):
            raise ValueError("Gitee 比较接口无法确认此次推送的完整提交列表")
    elif payload.get("after") and set(payload["after"]) != {"0"}:
        response = await client.get(
            f"/repos/{repo}/commits/{quote(payload['after'], safe='')}"
        )
        commits = [response.json()]
        if size > 1:
            raise ValueError("新分支 Push 未提供完整提交列表，未推进发送进度")
    elif size:
        raise ValueError("Gitee Push 缺少提交列表和 after")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("sha"), str)
        or not isinstance(item.get("commit"), dict)
        for item in commits
    ):
        raise ValueError("Gitee 返回了无效的 commit 详情")
    return repo, commits


async def fetch_repo_description(repo: str) -> str:
    """获取并缓存仓库简介，网络异常时回退到默认描述。"""
    cached = repo_descriptions.get(repo)
    if cached is not None and time.time() < cached[0]:
        return cached[1]
    try:
        assert client is not None
        response = await client.get(f"/repos/{repo}")
        description = str(response.json().get("description") or "").strip() or "暂无描述"
        ttl = 600
    except Exception as exc:
        _log_warning(f"获取 {repo} 描述失败：{_error_reason(exc)}，继续推送提交")
        description, ttl = "暂无描述", 60
    repo_descriptions[repo] = (time.time() + ttl, description)
    return description


def format_notification(repo: str, commits: list[dict], description: str) -> str:
    """将仓库简介和提交说明格式化为群聊文本。"""
    lines = [f"检测到牛马工作提交进度\n仓库：{repo}\n描述：{description}"]
    for item in commits:
        details = item["commit"]
        message = str(details.get("message") or "").strip() or "（无提交说明）"
        date = (details.get("committer") or {}).get("date") or (
            details.get("author") or {}
        ).get("date")
        try:
            submitted = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone(timedelta(hours=8)))
            date_text = submitted.astimezone(timezone(timedelta(hours=8))).strftime(
                "%Y-%m-%d %H:%M:%S（北京时间）"
            )
        except (AttributeError, TypeError, ValueError):
            date_text = "未知时间"
        lines.append(f"提交信息：{message}\n提交时间：{date_text}")
    return "\n\n".join(lines)


async def handle_group_message(
    message: GroupMessage,
    *,
    replies_already_sent: bool = False,
    received_at: float | None = None,
) -> None:
    """记录新群消息并尝试发送等待中的提交通知。"""
    remember_group_message(
        message,
        replies_already_sent=replies_already_sent,
        received_at=received_at,
    )
    group_id = str(getattr(message, "group_openid", "") or "").strip()
    if group_id and group_id in GITEE_NOTIFY_GROUPS:
        await flush_pending_notifications(group_id)


def enqueue_notification(group_id: str, notification: PendingNotification) -> None:
    """把缺少近期回复目标的提交通知追加到群队列。"""
    pending_notifications.setdefault(group_id, deque()).append(notification)
    notification.progress.queued_commits.update(notification.commits)


async def send_notification(
    group_id: str,
    message: GroupMessage,
    notification: PendingNotification,
    *,
    from_queue: bool = False,
) -> bool:
    """将通知回复到入站消息，并在需要时从队列移除。"""
    async with send_lock:
        if get_recent_message(group_id) is not message:
            return False
        if monotonic() < notification_after.get(group_id, 0):
            return False
        queue = pending_notifications.get(group_id)
        if from_queue and (not queue or queue[0] is not notification):
            return False
        sequence = next_reply_sequence(group_id, message)
        if sequence is None:
            return False
        notification_after[group_id] = monotonic() + _NOTIFICATION_INTERVAL
        try:
            await message.reply(
                msg_type=0,
                content=notification.text,
                msg_seq=sequence,
            )
        except Exception as exc:
            _log_warning(
                f"用户 {notification.username} 活动 {notification.event_id} "
                f"→ 群 {group_id}{'队列' if from_queue else ''}回复失败："
                f"{_error_reason(exc)}"
            )
            return False
        notification.progress.sent_commits.update(notification.commits)
        notification.progress.queued_commits.difference_update(notification.commits)
        if from_queue and queue is not None:
            queue.popleft()
            if not queue:
                pending_notifications.pop(group_id, None)
        return True


async def flush_pending_notifications(group_id: str) -> None:
    """在存在近期群消息且冷却结束时发送队列中的最早通知。"""
    queue = pending_notifications.get(group_id)
    message = get_recent_message(group_id)
    if not queue or message is None:
        return
    await send_notification(group_id, message, queue[0], from_queue=True)


async def check_users() -> None:
    """轮询配置用户的公开 Push，并按群缓存提交进度。"""
    assert client is not None
    for username in active_users:
        if time.time() < client.retry_after:
            break
        try:
            events = await fetch_user_events(username)
            ids = {str(event["id"]) for event in events}
            groups = user_state.setdefault(username, {})
            details_cache: dict[str, tuple[str, list[dict]]] = {}
            for group_id in GITEE_NOTIFY_GROUPS:
                if group_id not in groups:
                    groups[group_id] = UserProgress(time.time(), set(ids))
                    continue
                progress = groups[group_id]
                progress.seen_events.intersection_update(ids)
                for event in events:
                    event_id = str(event["id"])
                    if event_id in progress.seen_events:
                        continue
                    try:
                        if (
                            event.get("type") != "PushEvent"
                            or event.get("public") is not True
                            or (event.get("actor") or {}).get("login", "").lower()
                            != username
                            or event_time(event) < progress.since
                        ):
                            progress.seen_events.add(event_id)
                            continue
                        if monotonic() < notification_after.get(group_id, 0):
                            progress.seen_events.add(event_id)
                            continue
                        if event_id not in details_cache:
                            details_cache[event_id] = await fetch_push_commits(event)
                        repo, commits = details_cache[event_id]
                        keys = tuple(
                            (repo, item["sha"])
                            for item in commits
                            if (repo, item["sha"]) not in progress.sent_commits
                            and (repo, item["sha"]) not in progress.queued_commits
                        )
                        if not keys:
                            progress.seen_events.add(event_id)
                            continue
                        pending = [item for item in commits if (repo, item["sha"]) in keys]
                        description = await fetch_repo_description(repo)
                        batch = pending[-GITEE_MAX_COMMITS:]
                        batch_keys = tuple((repo, item["sha"]) for item in batch)
                        notification = PendingNotification(
                            text=format_notification(repo, batch, description),
                            commits=batch_keys,
                            progress=progress,
                            username=username,
                            event_id=event_id,
                        )
                        message = get_recent_message(group_id)
                        if message is None:
                            enqueue_notification(group_id, notification)
                            progress.seen_events.add(event_id)
                            break
                        if await send_notification(group_id, message, notification):
                            progress.seen_events.add(event_id)
                        break
                    except Exception as exc:
                        _log_warning(
                            f"用户 {username} 活动 {event_id} → 群 {group_id} 失败："
                            f"{_error_reason(exc)}"
                        )
                        if time.time() < client.retry_after:
                            return
                        break
        except Exception as exc:
            _log_warning(f"检查用户 {username} 失败：{_error_reason(exc)}")


async def check_all() -> None:
    """串行执行一轮活动检查，并先尝试发送已有队列。"""
    if client is None or check_lock.locked() or time.time() < client.retry_after:
        return
    async with check_lock:
        for group_id in GITEE_NOTIFY_GROUPS:
            await flush_pending_notifications(group_id)
        await check_users()


async def _monitor_loop() -> None:
    """建立 Gitee HTTP 客户端并按配置间隔持续检查活动。"""
    global client
    api_client = GiteeApiClient(GITEE_TOKEN, GITEE_REQUEST_TIMEOUT)
    client = api_client
    try:
        await api_client.start()
        clear_progress()
        await check_all()
        while True:
            await asyncio.sleep(GITEE_POLL_INTERVAL)
            await check_all()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log_warning(f"后台监听任务异常：{_error_reason(exc)}")
    finally:
        await api_client.close()
        client = None


async def start_gitee_monitor() -> None:
    """在机器人上线后启动后台 Gitee 监听任务。"""
    global active_users, monitor_task
    if not GITEE_USERS or not GITEE_NOTIFY_GROUPS:
        return
    invalid_users = [
        username
        for username in GITEE_USERS
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", username.strip().lower())
    ]
    if invalid_users:
        _log_warning("GITEE_USERS 包含无效登录名，已跳过无效项")
    valid_users = [
        username.strip().lower()
        for username in GITEE_USERS
        if re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", username.strip().lower())
    ]
    active_users = list(dict.fromkeys(valid_users))
    if not valid_users:
        return
    if monitor_task is not None and not monitor_task.done():
        async with check_lock:
            clear_progress()
        return
    monitor_task = asyncio.create_task(_monitor_loop(), name="gitee-commit-monitor")


def _error_reason(exc: Exception) -> str:
    """生成不包含 Gitee Token 或请求 URL 的简短错误信息。"""
    if isinstance(exc, GiteeHTTPStatusError):
        return f"HTTP {exc.status_code}"
    return type(exc).__name__


def _log_warning(message: str) -> None:
    """通过项目日志记录 Gitee 监听器的可操作错误。"""
    _log.warning("[gitee] %s", message)
