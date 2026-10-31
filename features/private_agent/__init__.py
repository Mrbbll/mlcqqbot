"""管理按发送者隔离的短期私聊 Agent 上下文。"""
from collections import OrderedDict
from time import monotonic
from typing import Any


_CONTEXT_TTL_SECONDS = 10 * 60
_MAX_TRACKED_USERS = 64
_MAX_MESSAGES_PER_USER = 80
_MAX_CONTEXT_MESSAGES = 20
_MAX_MESSAGE_CHARS = 1200
_MAX_CONTEXT_CHARS = 8000
_messages_by_user: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()


def record_private_message(
    user_id: str,
    role: str,
    content: str,
    *,
    message_id: str = "",
) -> None:
    """保存一条私聊消息，并限制会话数量、时长和正文长度。"""
    normalized_user_id = str(user_id or "").strip()
    normalized_role = str(role or "").strip()
    normalized_content = str(content or "").strip()
    if not normalized_user_id or normalized_role not in {"user", "assistant"}:
        return
    if not normalized_content:
        return

    now = monotonic()
    messages = [
        item
        for item in _messages_by_user.get(normalized_user_id, [])
        if now - item["received_at"] < _CONTEXT_TTL_SECONDS
    ]
    messages.append(
        {
            "received_at": now,
            "message_id": str(message_id or ""),
            "user_id": normalized_user_id,
            "role": normalized_role,
            "content": normalized_content[:_MAX_MESSAGE_CHARS],
        }
    )
    _messages_by_user[normalized_user_id] = messages[-_MAX_MESSAGES_PER_USER:]
    _messages_by_user.move_to_end(normalized_user_id)
    while len(_messages_by_user) > _MAX_TRACKED_USERS:
        _messages_by_user.popitem(last=False)


def get_private_context(user_id: str) -> list[dict[str, Any]]:
    """返回该发送者最近十分钟内的有界私聊上下文。"""
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return []

    now = monotonic()
    messages = [
        item
        for item in _messages_by_user.get(normalized_user_id, [])
        if now - item["received_at"] < _CONTEXT_TTL_SECONDS
    ]
    if not messages:
        _messages_by_user.pop(normalized_user_id, None)
        return []

    _messages_by_user[normalized_user_id] = messages
    _messages_by_user.move_to_end(normalized_user_id)
    selected: list[dict[str, Any]] = []
    context_chars = 0
    for item in reversed(messages):
        content = item["content"]
        if selected and context_chars + len(content) > _MAX_CONTEXT_CHARS:
            break
        selected.append(item)
        context_chars += len(content)
        if len(selected) >= _MAX_CONTEXT_MESSAGES:
            break

    return [
        {
            "message_id": item["message_id"],
            "user_id": item["user_id"],
            "role": item["role"],
            "content": item["content"],
        }
        for item in reversed(selected)
    ]
