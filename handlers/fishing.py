"""群聊钓鱼小游戏的会话管理、随机等待和渔获生成。"""
import asyncio
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Literal

from utils import messages
from utils.keyboard import fishing_keyboard_payload
from utils.markdown import markdown_payload


FISHING_MIN_DELAY_SECONDS = 1
FISHING_MAX_DELAY_SECONDS = 60
FISHING_HOOK_WINDOW_SECONDS = 2.0

_FISH_CATALOG = (
    ("鲫鱼", 80, 350),
    ("鲤鱼", 180, 900),
    ("草鱼", 300, 1200),
    ("鲈鱼", 150, 700),
    ("鳜鱼", 200, 800),
    ("鲶鱼", 250, 1500),
    ("河豚", 100, 400),
    ("金枪鱼", 600, 2500),
)
_log = logging.getLogger("mlcbot")


@dataclass(frozen=True)
class Fish:
    """一次成功拉钩获得的鱼。"""

    species: str
    size_cm: float


@dataclass
class _FishingSession:
    """一名群成员当前钓鱼流程的内存状态。"""

    group_openid: str
    user_openid: str
    token: str
    task: asyncio.Task[None] | None = None
    bite_deadline: float | None = None


HookResult = Literal["caught", "not_owner", "expired"]
_sessions_by_player: dict[tuple[str, str], _FishingSession] = {}
_sessions_by_token: dict[str, _FishingSession] = {}


def draw_fishing_delay() -> int:
    """随机生成包含 1 秒和 60 秒边界的上钩等待时间。"""
    choices = FISHING_MAX_DELAY_SECONDS - FISHING_MIN_DELAY_SECONDS + 1
    return FISHING_MIN_DELAY_SECONDS + secrets.randbelow(choices)


def draw_fish() -> Fish:
    """随机生成鱼的种类和该种类合理范围内的长度。"""
    species, minimum_mm, maximum_mm = secrets.choice(_FISH_CATALOG)
    size_mm = minimum_mm + secrets.randbelow(maximum_mm - minimum_mm + 1)
    return Fish(species=species, size_cm=size_mm / 10)


async def handle_start_fishing(
    api: Any,
    group_openid: str,
    user_openid: str,
    *,
    is_group: bool = True,
) -> str:
    """创建钓鱼会话并后台等待鱼上钩。"""
    if not is_group:
        return messages.FISHING_GROUP_ONLY
    if not api or not group_openid or not user_openid:
        return messages.FISHING_CONTEXT_MISSING

    player_key = (group_openid, user_openid)
    active = _sessions_by_player.get(player_key)
    if active and active.task and not active.task.done():
        return messages.FISHING_ALREADY_ACTIVE
    if active:
        _remove_session(active)

    token = secrets.token_urlsafe(8)
    while token in _sessions_by_token:
        token = secrets.token_urlsafe(8)
    session = _FishingSession(group_openid, user_openid, token)
    _sessions_by_player[player_key] = session
    _sessions_by_token[token] = session
    delay = draw_fishing_delay()
    session.task = asyncio.create_task(_announce_bite(api, session, delay))
    _log.info(
        "[钓鱼开始] group=%s user=%s delay_seconds=%s",
        group_openid,
        user_openid,
        delay,
    )
    return messages.FISHING_STARTED


async def _announce_bite(
    api: Any,
    session: _FishingSession,
    delay_seconds: int,
) -> None:
    """等待随机时长，发送拉钩按钮，并在窗口结束后清理会话。"""
    try:
        await asyncio.sleep(delay_seconds)
        if _sessions_by_token.get(session.token) is not session:
            return

        payload = markdown_payload(messages.fishing_bite(session.user_openid))
        payload["keyboard"] = fishing_keyboard_payload(
            session.token,
            session.user_openid,
        )
        await api.post_group_message(
            group_openid=session.group_openid,
            **payload,
        )
        session.bite_deadline = (
            asyncio.get_running_loop().time() + FISHING_HOOK_WINDOW_SECONDS
        )
        await asyncio.sleep(FISHING_HOOK_WINDOW_SECONDS)
        _remove_session(session)
    except asyncio.CancelledError:
        _remove_session(session)
        raise
    except Exception:
        _remove_session(session)
        _log.exception(
            "发送钓鱼上钩消息失败: group=%s user=%s",
            session.group_openid,
            session.user_openid,
        )


def claim_fish(
    token: str,
    group_openid: str,
    user_openid: str,
) -> tuple[HookResult, Fish | None]:
    """校验按钮点击者与时限，并在成功时生成一条随机渔获。"""
    session = _sessions_by_token.get(token)
    if not session or session.group_openid != group_openid:
        return "expired", None
    if session.user_openid != user_openid:
        return "not_owner", None

    loop_time = asyncio.get_running_loop().time()
    if session.bite_deadline is None or loop_time > session.bite_deadline:
        _remove_session(session, cancel_task=True)
        return "expired", None

    _remove_session(session, cancel_task=True)
    return "caught", draw_fish()


def _remove_session(
    session: _FishingSession,
    *,
    cancel_task: bool = False,
) -> None:
    """仅在映射仍指向当前局时清理状态，可选取消等待任务。"""
    player_key = (session.group_openid, session.user_openid)
    if _sessions_by_player.get(player_key) is session:
        _sessions_by_player.pop(player_key, None)
    if _sessions_by_token.get(session.token) is session:
        _sessions_by_token.pop(session.token, None)
    if cancel_task and session.task and not session.task.done():
        session.task.cancel()


def clear_fishing_sessions() -> None:
    """取消并清空所有钓鱼会话，供关闭流程和测试隔离使用。"""
    sessions = list(_sessions_by_token.values())
    for session in sessions:
        _remove_session(session, cancel_task=True)
