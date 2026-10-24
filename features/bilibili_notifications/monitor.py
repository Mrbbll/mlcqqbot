"""检测直播状态变化，排队回复目标群近期消息，禁止主动推送。"""

import asyncio
import logging
from collections import deque
from time import monotonic

from botpy.message import GroupMessage

from config import (
    BILIBILI_NOTIFY_GROUPS,
    BILIBILI_POLL_INTERVAL,
    BILIBILI_REQUEST_TIMEOUT,
    BILIBILI_ROOM_IDS,
)
from external_tools.bilibili.client import BilibiliApiClient, LiveRoomInfo
from features.passive_notifications.context import get_recent_message, next_reply_sequence


_log = logging.getLogger("mlcbot")
_NOTIFICATION_INTERVAL = 60.0
client: BilibiliApiClient | None = None
monitor_task: asyncio.Task | None = None
active_rooms: list[int] = []
status: dict[int, bool] = {}
pending_notifications: dict[str, deque[str]] = {}
notification_after: dict[str, float] = {}
send_lock = asyncio.Lock()


def format_notification(room: LiveRoomInfo) -> str:
    """保留旧项目的开播和下播通知文案。"""
    if room.is_live:
        return (
            f"{room.uname} 开播啦！\n标题：{room.title}\n"
            f"链接：https://live.bilibili.com/{room.room_id}"
        )
    return f"{room.uname} 的直播间已下播！"


async def flush_pending_notifications(group_id: str) -> None:
    """每群每分钟尝试发送最早通知，失败和缺少锚点时保留队列。"""
    async with send_lock:
        queue = pending_notifications.get(group_id)
        message = get_recent_message(group_id)
        if not queue or message is None:
            return
        if monotonic() < notification_after.get(group_id, 0):
            return
        sequence = next_reply_sequence(group_id, message)
        if sequence is None:
            return
        notification_after[group_id] = monotonic() + _NOTIFICATION_INTERVAL
        try:
            await message.reply(msg_type=0, content=queue[0], msg_seq=sequence)
        except Exception as exc:
            _log.warning("[bilibili] 群 %s 回复失败：%s", group_id, type(exc).__name__)
            return
        queue.popleft()
        if not queue:
            pending_notifications.pop(group_id, None)


async def handle_group_message(message: GroupMessage) -> None:
    """群消息上下文由公共入口登记，此处仅尝试清空直播通知队列。"""
    group_id = str(getattr(message, "group_openid", "") or "").strip()
    if group_id in BILIBILI_NOTIFY_GROUPS:
        await flush_pending_notifications(group_id)


async def check_all() -> None:
    """逐个检查直播间，首次成功查询只建立基线，失败不改变状态。"""
    if client is None:
        return
    for room_id in active_rooms:
        try:
            room = await client.get_room_info(room_id)
            previous = status.get(room_id)
            if previous is not None and previous != room.is_live:
                text = format_notification(room)
                for group_id in dict.fromkeys(BILIBILI_NOTIFY_GROUPS):
                    pending_notifications.setdefault(group_id, deque()).append(text)
            status[room_id] = room.is_live
        except Exception as exc:
            _log.warning("[bilibili] 检查直播间 %s 失败：%s", room_id, type(exc).__name__)
    for group_id in BILIBILI_NOTIFY_GROUPS:
        await flush_pending_notifications(group_id)


async def _monitor_loop() -> None:
    """定时检查直播状态，在取消任务时关闭 HTTP 客户端。"""
    global client
    api_client = BilibiliApiClient(BILIBILI_REQUEST_TIMEOUT)
    client = api_client
    try:
        await api_client.start()
        status.clear()
        while True:
            await check_all()
            await asyncio.sleep(BILIBILI_POLL_INTERVAL)
    finally:
        await api_client.close()
        client = None


async def start_bilibili_monitor() -> None:
    """配置完整时启动唯一监听任务，重连不会重复启动或重置基线。"""
    global monitor_task, active_rooms
    if not BILIBILI_ROOM_IDS or not BILIBILI_NOTIFY_GROUPS:
        return
    if monitor_task is not None and not monitor_task.done():
        return
    valid_rooms = []
    for value in BILIBILI_ROOM_IDS:
        try:
            room_id = int(value)
            if room_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            _log.warning("[bilibili] 跳过无效直播间号")
            continue
        valid_rooms.append(room_id)
    active_rooms = list(dict.fromkeys(valid_rooms))
    if active_rooms:
        monitor_task = asyncio.create_task(_monitor_loop(), name="bilibili-live-monitor")
