"""通过 QQ 官方接口主动转发游戏端提供的 OneBot 群文本消息。"""

import html
import logging
import re

from config import ONEBOT_GROUP_MAPPINGS, QQ_GROUP_OPENIDS


_log = logging.getLogger("mlcbot")


def _group_mappings():
    """解析受允许群列表约束的群号映射，拒绝重复和冲突配置。"""
    mappings = {}
    used_openids = set()
    for entry in ONEBOT_GROUP_MAPPINGS:
        number, separator, openid = entry.partition("=")
        number, openid = number.strip(), openid.strip()
        if (not separator or not number.isascii() or not number.isdigit()
                or not openid or openid not in QQ_GROUP_OPENIDS
                or number in mappings or openid in used_openids):
            raise ValueError("ONEBOT_GROUP_MAPPINGS 配置无效、重复或不在 QQ_GROUP_OPENIDS 中")
        mappings[number] = openid
        used_openids.add(openid)
    return mappings


def onebot_group_id(openid, numeric_id):
    """返回配置的真实群号，未配置时沿用原有稳定数字别名。"""
    try:
        mappings = _group_mappings()
    except ValueError as exc:
        _log.warning("%s", exc)
        mappings = {}
    return next((int(number) for number, value in mappings.items() if value == openid),
                numeric_id("group", openid))


def _text_message(message):
    """提取纯文本消息；拒绝不能正确转发的非文本消息段。"""
    if isinstance(message, str):
        if re.search(r"\[CQ:[^\]]+\]", message):
            raise ValueError("不支持非文本 CQ 码")
        return html.unescape(message)
    if not isinstance(message, list) or not message:
        raise ValueError("消息必须是文本或文本消息段")
    parts = []
    for segment in message:
        if not isinstance(segment, dict) or segment.get("type") != "text":
            raise ValueError("仅支持文本消息段")
        data = segment.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            raise ValueError("文本消息段格式错误")
        parts.append(data["text"])
    return "".join(parts)


async def send_group_message(api, params, numeric_id):
    """校验目标群和内容，主动发送一次并返回 OneBot 消息 ID。"""
    if not isinstance(params, dict):
        raise ValueError("请求参数格式错误")
    group_id = str(params.get("group_id", ""))
    mappings = _group_mappings()
    group = mappings.get(group_id) or next((item for item in QQ_GROUP_OPENIDS
                  if group_id in (item, str(numeric_id("group", item)))), None)
    if not group:
        raise ValueError("目标群未匹配，请检查 QQ_GROUP_OPENIDS 和 ONEBOT_GROUP_MAPPINGS")
    content = _text_message(params.get("message"))
    if not content.strip():
        raise ValueError("消息内容为空")
    if api is None:
        raise RuntimeError("QQ API 尚未就绪")
    result = await api.post_group_message(group_openid=group, msg_type=0, content=content)
    if not isinstance(result, dict) or not result.get("id"):
        raise RuntimeError("QQ 消息接口未返回确认 ID")
    return numeric_id("message", str(result["id"]))
