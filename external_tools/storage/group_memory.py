"""为 agent 提供按群隔离、自动过期的近期消息上下文。"""
from collections import OrderedDict, deque
from dataclasses import dataclass
import time


_MESSAGE_TTL_SECONDS = 10 * 60
_MAX_MESSAGES_PER_GROUP = 200
_MAX_TRACKED_GROUPS = 64
_MAX_MESSAGE_CHARS = 1200
_MAX_CONTEXT_MESSAGES = 40
_MAX_CONTEXT_CHARS = 8000


@dataclass(frozen=True, slots=True)
class _GroupMessage:
    """保存单条群消息及其接收时间，用于 TTL 清理。"""

    received_at: float
    message_id: str
    user_id: str
    content: str


_messages_by_group: OrderedDict[str, deque[_GroupMessage]] = OrderedDict()


def record_group_message(
    group_id: str,
    user_id: str,
    content: str | None,
    *,
    message_id: str = "",
) -> None:
    """保存一条入站群消息，并清理已过期记录。"""
    normalized_group_id = (group_id or "").strip()
    normalized_content = (content or "").strip()
    if not normalized_group_id or not normalized_content:
        return

    now = time.monotonic()
    group_messages = _messages_by_group.get(normalized_group_id)
    if group_messages is None:
        group_messages = deque(maxlen=_MAX_MESSAGES_PER_GROUP)
        _messages_by_group[normalized_group_id] = group_messages
    else:
        _discard_expired(group_messages, now)
        _messages_by_group.move_to_end(normalized_group_id)

    if len(normalized_content) > _MAX_MESSAGE_CHARS:
        normalized_content = normalized_content[:_MAX_MESSAGE_CHARS] + "…"
    group_messages.append(
        _GroupMessage(
            received_at=now,
            message_id=message_id,
            user_id=(user_id or "未知用户").strip(),
            content=normalized_content,
        )
    )
    while len(_messages_by_group) > _MAX_TRACKED_GROUPS:
        _messages_by_group.popitem(last=False)


def get_recent_group_messages(
    group_id: str,
    *,
    exclude_message_id: str = "",
) -> list[dict[str, str]]:
    """返回该群最近十分钟内的消息，排除当前消息并限制上下文大小。"""
    normalized_group_id = (group_id or "").strip()
    group_messages = _messages_by_group.get(normalized_group_id)
    if group_messages is None:
        return []

    now = time.monotonic()
    _discard_expired(group_messages, now)
    if not group_messages:
        _messages_by_group.pop(normalized_group_id, None)
        return []

    _messages_by_group.move_to_end(normalized_group_id)
    recent_messages: list[_GroupMessage] = []
    context_chars = 0
    for message in reversed(group_messages):
        if exclude_message_id and message.message_id == exclude_message_id:
            continue
        if recent_messages and context_chars + len(message.content) > _MAX_CONTEXT_CHARS:
            break
        recent_messages.append(message)
        context_chars += len(message.content)
        if len(recent_messages) >= _MAX_CONTEXT_MESSAGES:
            break
    recent_messages.reverse()
    return [
        {"user_id": message.user_id, "content": message.content}
        for message in recent_messages
    ]


def _discard_expired(group_messages: deque[_GroupMessage], now: float) -> None:
    """从队列头部移除超过十分钟的消息。"""
    while (
        group_messages
        and now - group_messages[0].received_at >= _MESSAGE_TTL_SECONDS
    ):
        group_messages.popleft()
