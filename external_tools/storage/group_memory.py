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
    message_index: str
    file_attachments: tuple[dict[str, Any], ...] = ()
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
    file_attachments: Iterable[dict[str, Any]] = (),
    reference_message_id: str = "",
    message_index: str = "",
    received_at: float | None = None,
    role: str = "user",
    emoji: dict[str, Any] | None = None,
) -> None:
    """保存消息作者 ID 与内容，并按接收时间维护群记忆。"""
    normalized_group_id = (group_id or "").strip()
    stored_content = content or ""
    normalized_images = tuple(
        _normalize_image_attachment(attachment)
        for attachment in image_attachments
        if _is_image_attachment(attachment)
    )
    normalized_reference_id = (reference_message_id or "").strip()
    normalized_message_index = (message_index or "").strip()
    normalized_files = tuple(_normalize_image_attachment(item) for item in list(file_attachments)[:5])
    if not normalized_group_id or not (
        stored_content.strip() or normalized_images or normalized_files or normalized_reference_id
    ):
        return

    now = time.monotonic()
    message_received_at = now if received_at is None else received_at
    group_messages = _messages_by_group.get(normalized_group_id)
    if group_messages is None:
        existing_messages: list[_GroupMessage] = []
    else:
        _discard_expired(group_messages, now)
        existing_messages = list(group_messages)
        _messages_by_group.move_to_end(normalized_group_id)

    if len(stored_content) > _MAX_MESSAGE_CHARS:
        stored_content = stored_content[:_MAX_MESSAGE_CHARS] + "…"
    new_message = _GroupMessage(
        received_at=message_received_at,
        message_id=message_id,
        user_id=(user_id or "未知用户").strip(),
        content=stored_content,
        has_image=bool(normalized_images or emoji),
        image_attachments=normalized_images,
        reference_message_id=normalized_reference_id,
        message_index=normalized_message_index,
        file_attachments=normalized_files,
        role=role,
        emoji=dict(emoji) if emoji else None,
    )
    # 转发完成顺序可能不同于事件到达顺序；保留时间顺序并只留下最新的有界记录。
    ordered_messages = sorted(
        [*existing_messages, new_message],
        key=lambda message: message.received_at,
    )
    _messages_by_group[normalized_group_id] = deque(
        ordered_messages[-_MAX_MESSAGES_PER_GROUP:],
        maxlen=_MAX_MESSAGES_PER_GROUP,
    )
    _messages_by_group.move_to_end(normalized_group_id)
    while len(_messages_by_group) > _MAX_TRACKED_GROUPS:
        _messages_by_group.popitem(last=False)


def get_recent_group_messages(
    group_id: str,
    *,
    exclude_message_id: str = "",
    referenced_message_ids: Iterable[str] = (),
    current_message_received_at: float | None = None,
) -> list[dict[str, Any]]:
    """返回当前消息之前的近期记录及明确引用，并限制上下文大小。"""
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
    current_message = next(
        (
            message
            for message in group_messages
            if exclude_message_id and message.message_id == exclude_message_id
        ),
        None,
    )
    context_received_at = (
        current_message.received_at
        if current_message is not None
        else current_message_received_at
    )
    recent_messages: list[_GroupMessage] = []
    context_chars = 0
    for message in reversed(group_messages):
        if exclude_message_id and message.message_id == exclude_message_id:
            continue
        if context_received_at is not None and message.received_at > context_received_at:
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
    if current_message and current_message.reference_message_id:
        referenced_ids.add(current_message.reference_message_id)
    if referenced_ids:
        for message in group_messages:
            if (
                _matches_reference(message, referenced_ids)
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
            "files": [{"filename": item["filename"], "size": item["size"]} for item in message.file_attachments],
        }
        for message in recent_messages
    ]


def get_recent_group_image_attachments(
    group_id: str,
    *,
    current_message_id: str = "",
    referenced_message_ids: Iterable[str] = (),
    current_message_received_at: float | None = None,
) -> list[dict[str, Any]]:
    """返回当前消息之前及明确引用的图片，供 Agent 请求按需下载。"""
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
    current_message = next(
        (
            message
            for message in group_messages
            if current_id and message.message_id == current_id
        ),
        None,
    )
    context_received_at = (
        current_message.received_at
        if current_message is not None
        else current_message_received_at
    )
    if current_message and current_message.reference_message_id:
        referenced_ids.add(current_message.reference_message_id)
    image_records: list[dict[str, Any]] = []
    for message in group_messages:
        is_referenced = _matches_reference(message, referenced_ids)
        if (
            context_received_at is not None
            and message.received_at > context_received_at
            and not is_referenced
        ):
            continue
        if not message.image_attachments:
            continue
        for attachment in message.image_attachments:
            if attachment.get("relation") == "引用消息":
                relation = "引用消息"
            elif current_id and message.message_id == current_id:
                relation = "当前消息"
            elif is_referenced:
                relation = "引用消息"
            else:
                relation = "历史消息"
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


def get_recent_group_file_attachments(
    group_id: str,
    *,
    current_message_id: str = "",
    reference_message_id: str = "",
    include_recent: bool = False,
    current_message_received_at: float | None = None,
) -> list[dict]:
    """返回当前或引用文件；明确询问时补充当前消息之前的最新文件。"""
    records = _messages_by_group.get((group_id or "").strip())
    if not records:
        return []
    _discard_expired(records, time.monotonic())
    referenced_ids = {reference_message_id} if reference_message_id else set()
    current_message = next(
        (
            item
            for item in records
            if current_message_id and item.message_id == current_message_id
        ),
        None,
    )
    context_received_at = (
        current_message.received_at
        if current_message is not None
        else current_message_received_at
    )
    if current_message and current_message.reference_message_id:
        referenced_ids.add(current_message.reference_message_id)
    selected = [
        item for item in records
        if item.file_attachments
        and (
            (current_message_id and item.message_id == current_message_id)
            or _matches_reference(item, referenced_ids)
        )
        and (
            context_received_at is None
            or item.received_at <= context_received_at
            or _matches_reference(item, referenced_ids)
        )
    ]
    if not selected and include_recent:
        selected = next(
            (
                [item]
                for item in reversed(records)
                if item.file_attachments
                and (
                    context_received_at is None
                    or item.received_at <= context_received_at
                )
            ),
            [],
        )
    return [
        {**attachment, "message_id": item.message_id}
        for item in selected
        for attachment in item.file_attachments
    ]


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
        "relation": str(attachment.get("relation") or ""),
    }


def _matches_reference(message: _GroupMessage, referenced_ids: set[str]) -> bool:
    """判断引用标识是否匹配原始消息 ID 或 QQ 的 REFIDX 索引。"""
    return bool(
        referenced_ids
        and (
            message.message_id in referenced_ids
            or (message.message_index and message.message_index in referenced_ids)
        )
    )


def _discard_expired(group_messages: deque[_GroupMessage], now: float) -> None:
    """从按接收时间排序的队列头部移除超过十分钟的消息。"""
    while (
        group_messages
        and now - group_messages[0].received_at >= _MESSAGE_TTL_SECONDS
    ):
        group_messages.popleft()
