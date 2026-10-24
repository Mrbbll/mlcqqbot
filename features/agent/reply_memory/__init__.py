"""记录机器人实际发出的群回复，并提供上一张表情包的换图依据。"""

from typing import Any

from external_tools.storage.group_memory import get_recent_group_messages, record_group_message


def record_bot_reply(
    group_id: str, text: str, response: Any, *, emoji: dict[str, Any] | None = None,
) -> None:
    """在调用方确认发送成功后写入群记忆，不保存本地路径或图片二进制。"""
    # BotPy 超时可能返回 None，仅收到消息 ID 才视为已确认发送成功。
    if not isinstance(response, dict) or not response.get("id"):
        return
    metadata = None
    if emoji:
        metadata = {key: emoji[key] for key in ("id", "name", "format", "query", "gif_only") if key in emoji}
        text = f"[已发送收藏表情包：{metadata.get('name', '')}，格式：{metadata.get('format', '')}]"
    message_id = str(response["id"])
    record_group_message(group_id, "MLC机器人", text, message_id=message_id,
                         role="assistant", emoji=metadata)


def last_sent_emoji(group_id: str) -> dict[str, Any] | None:
    """只从当前群有效期内的机器人发送记录中获取上一张表情包。"""
    for message in reversed(get_recent_group_messages(group_id)):
        if message.get("role") == "assistant" and message.get("emoji"):
            return dict(message["emoji"])
    return None
