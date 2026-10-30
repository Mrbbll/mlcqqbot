"""按配置记录群消息原始字段和 SDK 解析结果，用于定位提及信息丢失。"""

import json
import logging

from config import QQ_GROUP_MESSAGE_DEBUG


_log = logging.getLogger("mlcbot")
_MENTION_FIELDS = ("id", "member_openid", "user_openid", "username", "nickname", "nick")


def log_group_message_debug(message, payload: dict) -> None:
    """仅在开启调试时记录正文和提及身份字段，不输出完整载荷或附件地址。"""
    if not QQ_GROUP_MESSAGE_DEBUG:
        return
    raw_mentions = payload.get("mentions")
    parsed_mentions = getattr(message, "mentions", None)
    elements = payload.get("msg_elements") or payload.get("msgElements") or []
    if not isinstance(elements, (list, tuple)):
        elements = []
    diagnostic = {
        "message_id": payload.get("id"),
        "event_id": getattr(message, "event_id", None),
        "group_id": payload.get("group_openid"),
        "raw_keys": sorted(payload),
        "raw_content": payload.get("content"),
        "raw_mentions_present": "mentions" in payload,
        "raw_mentions_type": type(raw_mentions).__name__,
        "raw_mentions": _mention_fields(raw_mentions),
        "parsed_content": getattr(message, "content", None),
        "parsed_mentions": _mention_fields(parsed_mentions),
        "raw_element_keys": [
            sorted(element) for element in elements
            if isinstance(element, dict)
        ],
    }
    _log.info("[群消息提及调试] %s", json.dumps(diagnostic, ensure_ascii=False, default=str))


def _mention_fields(mentions) -> list[dict]:
    """从原始字典或 SDK 对象中提取身份字段，保留缺失和空值的区别。"""
    if not isinstance(mentions, (list, tuple)):
        return []
    return [
        {key: mention[key] for key in _MENTION_FIELDS if key in mention}
        if isinstance(mention, dict) else
        {key: getattr(mention, key) for key in _MENTION_FIELDS if hasattr(mention, key)}
        for mention in mentions
    ]
