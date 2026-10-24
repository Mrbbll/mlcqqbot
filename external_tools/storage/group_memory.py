"""为 agent 提供按群隔离、自动过期的近期消息上下文。"""
from collections import OrderedDict, deque
from dataclasses import dataclass
import time
from typing import Any, Iterable


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
    has_image: bool
    image_attachments: tuple[dict[str, Any], ...]
    reference_message_id: str
    role: str = "user"
    emoji: dict[str, Any] | None = None


_messages_by_group: OrderedDict[str, deque[_GroupMessage]] = OrderedDict()


def record_group_message(
    group_id: str,
    user_id: str,
    content: str | None,
    *,
    message_id: str = "",
    image_attachments: Iterable[dict[str, Any]] = (),
    reference_message_id: str = "",
    role: str = "user",
    emoji: dict[str, Any] | None = None,
) -> None:
    """保存入站消息或已成功发送的机器人回复，并清理过期记录。"""
    normalized_group_id = (group_id or "").strip()
    normalized_content = (content or "").strip()
    normalized_images = tuple(
        _normalize_image_attachment(attachment)
        for attachment in image_attachments
        if _is_image_attachment(attachment)
    )
    normalized_reference_id = (reference_message_id or "").strip()
    if not normalized_group_id or not (
        normalized_content or normalized_images or normalized_reference_id
    ):
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
            has_image=bool(normalized_images or emoji),
            image_attachments=normalized_images,
            reference_message_id=normalized_reference_id,
            role=role,
            emoji=dict(emoji) if emoji else None,
        )
    )
    while len(_messages_by_group) > _MAX_TRACKED_GROUPS:
        _messages_by_group.popitem(last=False)


def get_recent_group_messages(
    group_id: str,
    *,
    exclude_message_id: str = "",
    referenced_message_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """返回最近群消息、图片标记和明确引用的记录，并限制上下文大小。"""
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
    selected_message_ids = {message.message_id for message in recent_messages}
    referenced_ids = {
        normalized_id
        for message_id in referenced_message_ids
        if (normalized_id := str(message_id or "").strip())
    }
    if referenced_ids:
        for message in group_messages:
            if (
                message.message_id in referenced_ids
                and message.message_id not in selected_message_ids
                and message.message_id != exclude_message_id
            ):
                recent_messages.append(message)
                selected_message_ids.add(message.message_id)
    recent_messages.sort(key=lambda message: message.received_at)
    return [
        {
            "message_id": message.message_id,
            "user_id": message.user_id,
            "role": message.role,
            "content": message.content,
            "has_image": message.has_image,
            "image_count": len(message.image_attachments) + int(bool(message.emoji)),
            "reference_message_id": message.reference_message_id,
            "emoji": dict(message.emoji) if message.emoji else None,
        }
        for message in recent_messages
    ]


def get_recent_group_image_attachments(
    group_id: str,
    *,
    current_message_id: str = "",
    referenced_message_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """返回该群记忆时限内所有图片及其消息归属，供 Agent 请求按需下载。"""
    normalized_group_id = (group_id or "").strip()
    group_messages = _messages_by_group.get(normalized_group_id)
    if group_messages is None:
        return []

    now = time.monotonic()
    _discard_expired(group_messages, now)
    if not group_messages:
        _messages_by_group.pop(normalized_group_id, None)
        return []

    current_id = str(current_message_id or "")
    referenced_ids = {
        normalized_id
        for message_id in referenced_message_ids
        if (normalized_id := str(message_id or "").strip())
    }
    image_records: list[dict[str, Any]] = []
    for message in group_messages:
        if not message.image_attachments:
            continue
        if message.message_id == current_id:
            relation = "当前消息"
        elif message.message_id in referenced_ids:
            relation = "引用消息"
        else:
            relation = "历史消息"
        for attachment in message.image_attachments:
            image_records.append(
                {
                    **attachment,
                    "message_id": message.message_id,
                    "user_id": message.user_id,
                    "message_content": message.content,
                    "relation": relation,
                }
            )
    return image_records


def _is_image_attachment(attachment: dict[str, Any]) -> bool:
    """判断记录是否描述图片附件。"""
    content_type = str(attachment.get("content_type") or "").split(";", 1)[0]
    return content_type.strip().casefold().startswith("image/")


def _normalize_image_attachment(attachment: dict[str, Any]) -> dict[str, Any]:
    """只保留短期下载所需的图片元数据，不在群记忆中保存图片二进制。"""
    size = attachment.get("size")
    try:
        normalized_size = int(size) if size is not None else None
    except (TypeError, ValueError):
        normalized_size = None
    return {
        "url": str(attachment.get("url") or ""),
        "content_type": str(attachment.get("content_type") or "").split(";", 1)[0].strip().lower(),
        "filename": str(attachment.get("filename") or ""),
        "size": normalized_size,
        "source": str(attachment.get("source") or "消息附件"),
    }


def _discard_expired(group_messages: deque[_GroupMessage], now: float) -> None:
    """从队列头部移除超过十分钟的消息。"""
    while (
        group_messages
        and now - group_messages[0].received_at >= _MESSAGE_TTL_SECONDS
    ):
        group_messages.popleft()
