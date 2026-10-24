"""为 Gitee 和 Bilibili 通知共享近期群消息与被动回复序号。"""

from collections import OrderedDict
from time import monotonic

from botpy.message import GroupMessage
from config import BILIBILI_NOTIFY_GROUPS, GITEE_NOTIFY_GROUPS

NOTIFY_GROUPS = set(GITEE_NOTIFY_GROUPS) | set(BILIBILI_NOTIFY_GROUPS)
_RECENT_MESSAGE_WINDOW = 5 * 60.0
_MAX_REPLIES_PER_MESSAGE = 5
recent_messages: dict[str, tuple[float, GroupMessage]] = {}
reply_sequences: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()


def remember_group_message(
    message: GroupMessage,
    *,
    replies_already_sent: bool = False,
    received_at: float | None = None,
) -> None:
    """记录目标群最新消息及已使用的回复序号。"""
    group_id = str(getattr(message, "group_openid", "") or "").strip()
    if group_id and group_id in NOTIFY_GROUPS and getattr(message, "id", None):
        received_at = monotonic() if received_at is None else received_at
        current = recent_messages.get(group_id)
        if current is not None and current[0] > received_at:
            return
        while reply_sequences:
            oldest_key, (oldest_time, _) = next(iter(reply_sequences.items()))
            if received_at - oldest_time < _RECENT_MESSAGE_WINDOW:
                break
            reply_sequences.pop(oldest_key, None)
        recent_messages[group_id] = (received_at, message)
        message_id = str(message.id)
        key = (group_id, message_id)
        previous = reply_sequences.get(key)
        used_sequence = int(replies_already_sent)
        reply_sequences[key] = (
            previous[0], max(previous[1], used_sequence)
        ) if previous is not None else (received_at, used_sequence)


def get_recent_message(group_id: str) -> GroupMessage | None:
    """返回五分钟内最新的目标群消息，过期记录会被删除。"""
    cached = recent_messages.get(group_id)
    if cached is None:
        return None
    received_at, message = cached
    if monotonic() - received_at >= _RECENT_MESSAGE_WINDOW:
        recent_messages.pop(group_id, None)
        message_id = str(getattr(message, "id", "") or "")
        reply_sequences.pop((group_id, message_id), None)
        return None
    message_id = str(getattr(message, "id", "") or "")
    if reply_sequences.get((group_id, message_id), (received_at, 0))[1] >= _MAX_REPLIES_PER_MESSAGE:
        return None
    return message


def next_reply_sequence(group_id: str, message: GroupMessage) -> int | None:
    """为原消息分配未使用的被动回复序号，遵守单消息次数上限。"""
    message_id = str(getattr(message, "id", "") or "")
    if not message_id:
        return None
    key = (group_id, message_id)
    reply_state = reply_sequences.get(key)
    if reply_state is None or monotonic() - reply_state[0] >= _RECENT_MESSAGE_WINDOW:
        return None
    sequence = reply_state[1] + 1
    if sequence > _MAX_REPLIES_PER_MESSAGE:
        return None
    reply_sequences[key] = (reply_state[0], sequence)
    return sequence


