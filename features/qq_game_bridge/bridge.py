"""通过 OneBot v11 正向 WebSocket 服务端向 MCDR ImAPI 推送 QQ 群消息。"""
import asyncio
import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from urllib.parse import parse_qs, urlsplit

from websockets.exceptions import ConnectionClosed
from websockets.legacy.server import WebSocketServerProtocol, serve

from config import (
    ONEBOT_WS_ACCESS_TOKEN,
    ONEBOT_WS_HEARTBEAT,
    ONEBOT_WS_HOST,
    ONEBOT_WS_PORT,
    QQ_BOT_APPID,
)


_log = logging.getLogger("mlcbot")
_server = None
_clients: dict[WebSocketServerProtocol, str] = {}
_EVENT_PATHS = {"/", "/event", "/onebot/v11/ws"}
_API_PATHS = {"/", "/api", "/onebot/v11/ws"}
_ALLOWED_PATHS = _EVENT_PATHS | _API_PATHS
_MAX_MESSAGE_LENGTH = 2000
_NICKNAME_CACHE_LIMIT = 4096
_MENTION_PATTERN = re.compile(r"<@!?([\w-]+)>")
_nickname_cache: OrderedDict[str, str] = OrderedDict()


async def start_onebot_ws_server() -> None:
    """在 botpy 事件循环中启动 OneBot v11 正向 WebSocket 服务端。"""
    global _server
    if _server is not None:
        return
    try:
        _server = await serve(
            _handle_client,
            ONEBOT_WS_HOST,
            ONEBOT_WS_PORT,
            ping_interval=ONEBOT_WS_HEARTBEAT,
            ping_timeout=ONEBOT_WS_HEARTBEAT,
            max_size=1024 * 1024,
        )
    except OSError:
        _log.exception(
            "OneBot v11 WebSocket 服务启动失败，检查监听地址和端口: %s:%s",
            ONEBOT_WS_HOST,
            ONEBOT_WS_PORT,
        )
        return
    _log.info(
        "OneBot v11 WebSocket 服务已启动: ws://%s:%s/",
        ONEBOT_WS_HOST,
        ONEBOT_WS_PORT,
    )


async def forward_group_message(message) -> None:
    """将每条去重后的群消息推送给已连接的 ImAPI 客户端。"""
    group_openid = str(getattr(message, "group_openid", "") or "")
    if not group_openid:
        return

    _remember_message_nicknames(message)
    content = _message_text(message)
    if not content:
        return

    author = getattr(message, "author", None)
    member_openid = str(getattr(author, "member_openid", "") or "")
    user_id = _stable_numeric_id("user", member_openid or "unknown")
    group_id = _stable_numeric_id("group", group_openid)
    message_id = _stable_numeric_id(
        "message",
        str(getattr(message, "id", "") or f"{time.time_ns()}:{group_openid}:{member_openid}"),
    )
    nickname = _sender_nickname(message, author, member_openid)
    event = {
        "time": int(time.time()),
        "self_id": _self_id(),
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": message_id,
        "group_id": group_id,
        "user_id": user_id,
        "message": [{"type": "text", "data": {"text": content}}],
        "raw_message": content,
        "font": 0,
        "sender": {
            "user_id": user_id,
            "nickname": nickname,
            "card": "",
            "sex": "unknown",
            "age": 0,
            "area": "",
            "level": "",
            "role": "member",
            "title": "",
        },
        "group_openid": group_openid,
        "member_openid": member_openid,
    }
    payload = json.dumps(event, ensure_ascii=False)
    clients = [client for client, path in tuple(_clients.items()) if path in _EVENT_PATHS]
    if not clients:
        _log.debug("当前没有 OneBot 事件客户端，跳过群消息转发 group=%s", group_openid)
        return

    results = await asyncio.gather(
        *(client.send(payload) for client in clients),
        return_exceptions=True,
    )
    for client, result in zip(clients, results):
        if isinstance(result, Exception):
            _clients.pop(client, None)
            _log.debug("OneBot 事件推送失败，移除断开的客户端: %s", result)


async def _handle_client(websocket: WebSocketServerProtocol, path: str) -> None:
    """校验 OneBot 客户端、推送生命周期心跳并处理其 API 请求。"""
    parsed_path = urlsplit(path)
    endpoint = (parsed_path.path or "/").rstrip("/") or "/"
    if endpoint not in _ALLOWED_PATHS:
        await websocket.close(code=1008, reason="Unsupported OneBot WebSocket path")
        return
    if not _is_authorized(websocket, parsed_path.query):
        await websocket.close(code=1008, reason="Invalid access token")
        _log.warning("拒绝未通过令牌校验的 OneBot WebSocket 连接")
        return

    _clients[websocket] = endpoint
    _log.info("OneBot WebSocket 客户端已连接 path=%s", endpoint)
    try:
        if endpoint in _EVENT_PATHS:
            await websocket.send(json.dumps(_lifecycle_event(), ensure_ascii=False))
        while True:
            try:
                raw_request = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=ONEBOT_WS_HEARTBEAT,
                )
            except asyncio.TimeoutError:
                if endpoint in _EVENT_PATHS:
                    await websocket.send(json.dumps(_heartbeat_event(), ensure_ascii=False))
                continue
            if endpoint in _API_PATHS:
                response = _action_response(raw_request)
                if response is not None:
                    await websocket.send(json.dumps(response, ensure_ascii=False))
    except ConnectionClosed:
        _log.info("OneBot WebSocket 客户端已断开 path=%s", endpoint)
    except Exception:
        _log.exception("处理 OneBot WebSocket 客户端时发生错误")
    finally:
        _clients.pop(websocket, None)


def _is_authorized(websocket: WebSocketServerProtocol, query: str) -> bool:
    """使用 OneBot 标准 Authorization 头或 access_token 查询参数校验连接。"""
    if not ONEBOT_WS_ACCESS_TOKEN:
        return True
    authorization = websocket.request_headers.get("Authorization", "")
    header_token = authorization.partition(" ")[2].strip()
    query_token = parse_qs(query).get("access_token", [""])[0]
    return (
        authorization.startswith("Bearer ")
        and header_token == ONEBOT_WS_ACCESS_TOKEN
    ) or query_token == ONEBOT_WS_ACCESS_TOKEN


def _action_response(raw_request) -> dict | None:
    """为基础 OneBot 状态查询返回响应，其余动作明确报告不支持。"""
    try:
        request = json.loads(raw_request)
    except (TypeError, ValueError):
        return None
    if not isinstance(request, dict) or not request.get("action"):
        return None

    action = request["action"]
    response = {
        "status": "ok",
        "retcode": 0,
        "data": None,
        "echo": request.get("echo"),
    }
    if action == "get_login_info":
        response["data"] = {"user_id": _self_id(), "nickname": "QQ Bot"}
    elif action == "get_status":
        response["data"] = {"online": True, "good": True}
    elif action == "get_version_info":
        response["data"] = {
            "app_name": "mlcqqbot",
            "app_version": "1.0.0",
            "protocol_version": "v11",
        }
    else:
        _log.debug("收到未支持的 OneBot API action: %s", action)
        response.update(status="failed", retcode=1404)
    return response


def _message_text(message) -> str:
    """保留群消息正文并附上昵称化的提及和附件提示。"""
    content = str(getattr(message, "content", "") or "").strip()
    content = _MENTION_PATTERN.sub(
        lambda match: "@" + _nickname_cache.get(match.group(1), match.group(1)),
        content,
    )
    parts = [content]
    attachments = getattr(message, "attachments", None) or []
    for attachment in attachments:
        content_type = _attachment_field(attachment, "content_type")
        filename = _attachment_field(attachment, "filename")
        if content_type.startswith("image/"):
            parts.append("[图片]")
        elif content_type.startswith("video/"):
            parts.append("[视频]")
        elif content_type.startswith("audio/") or content_type == "voice":
            parts.append("[语音]")
        else:
            parts.append(f"[文件: {filename}]" if filename else "[附件]")
    reference = getattr(message, "message_reference", None)
    if not any(parts) and getattr(reference, "message_id", None):
        parts.append("[回复消息]")
    content = " ".join(part for part in parts if part).strip()
    if len(content) > _MAX_MESSAGE_LENGTH:
        content = content[:_MAX_MESSAGE_LENGTH - 1] + "…"
    return content


def _sender_nickname(message, author, member_openid: str) -> str:
    """读取消息携带的群昵称或缓存昵称，缺失时才回退到 OpenID。"""
    for source in (author, getattr(message, "member", None)):
        nickname = _first_nickname(source)
        if nickname:
            _remember_nickname(member_openid, nickname)
            return nickname
    return _nickname_cache.get(member_openid) or member_openid or "unknown"


def _remember_message_nicknames(message) -> None:
    """按参考实现缓存发送者和消息中被 @ 成员的 OpenID 与昵称。"""
    author = getattr(message, "author", None)
    sender_id = str(getattr(author, "member_openid", "") or "")
    sender_nickname = _first_nickname(author) or _first_nickname(
        getattr(message, "member", None)
    )
    _remember_nickname(sender_id, sender_nickname)

    for mention in getattr(message, "mentions", None) or []:
        nickname = _first_nickname(mention)
        if not nickname:
            continue
        for field in ("member_openid", "id", "user_openid"):
            member_id = str(getattr(mention, field, "") or "")
            _remember_nickname(member_id, nickname)


def _remember_nickname(member_openid: str, nickname: str | None) -> None:
    """更新有界的 OpenID 昵称缓存，避免持续收消息导致内存增长。"""
    if not member_openid or not nickname:
        return
    _nickname_cache[member_openid] = str(nickname)
    _nickname_cache.move_to_end(member_openid)
    if len(_nickname_cache) > _NICKNAME_CACHE_LIMIT:
        _nickname_cache.popitem(last=False)


def _first_nickname(source) -> str:
    """从 BotPy 或兼容 SDK 对象中读取第一个可用昵称字段。"""
    if source is None:
        return ""
    for field in ("username", "nickname", "nick"):
        value = getattr(source, field, None)
        if value:
            return str(value).strip()
    return ""


def _attachment_field(attachment, field: str) -> str:
    """兼容 BotPy 对象和字典两种附件结构，读取指定的文本字段。"""
    value = (
        attachment.get(field, "")
        if isinstance(attachment, dict)
        else getattr(attachment, field, "")
    )
    return str(value or "")


def _stable_numeric_id(namespace: str, value: str) -> int:
    """将 BotPy 的非数字 OpenID 稳定转换为 OneBot v11 所需的正整数 ID。"""
    digest = hashlib.blake2b(
        f"{namespace}:{value}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return (int.from_bytes(digest, "big") & ((1 << 63) - 1)) or 1


def _self_id() -> int:
    """返回机器人 AppID 的数字形式，AppID 非数字时使用稳定数字别名。"""
    try:
        return int(QQ_BOT_APPID)
    except (TypeError, ValueError):
        return _stable_numeric_id("self", str(QQ_BOT_APPID))


def _lifecycle_event() -> dict:
    """构造 OneBot v11 客户端连接成功事件。"""
    return {
        "time": int(time.time()),
        "self_id": _self_id(),
        "post_type": "meta_event",
        "meta_event_type": "lifecycle",
        "sub_type": "connect",
    }


def _heartbeat_event() -> dict:
    """构造 OneBot v11 定时心跳事件。"""
    return {
        "time": int(time.time()),
        "self_id": _self_id(),
        "post_type": "meta_event",
        "meta_event_type": "heartbeat",
        "status": {"online": True, "good": True},
        "interval": ONEBOT_WS_HEARTBEAT * 1000,
    }
