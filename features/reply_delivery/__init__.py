"""在 QQ 被动回复窗口过期后尝试一次主动发送，统一文字和媒体策略。"""

from datetime import datetime, timezone
import logging
from time import monotonic


_log = logging.getLogger("mlcbot")


class ReplyDeliveryError(RuntimeError):
    """表示发送已失败或状态未知，调用方不应自动重复发送。"""


class ReplyDelivery:
    """代理当前会话的发送接口，上传接口仍由原始 SDK 处理。"""

    def __init__(self, message, *, is_group: bool, group_id: str = "", api=None, received_at=None):
        """保存原始会话及消息年龄，用单调时钟累计后续处理耗时。"""
        self.message = message
        self.api = api if api is not None else message._api
        self.is_group = is_group
        self.group_id = group_id or getattr(message, "group_openid", "")
        self.started_at = monotonic()
        self.initial_age = max(0.0, self.started_at - received_at) if received_at is not None else 0.0
        timestamp = getattr(message, "timestamp", None)
        try:
            sent_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if sent_at.tzinfo is not None:
                self.initial_age = max(self.initial_age, (datetime.now(timezone.utc) - sent_at).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass

    def __getattr__(self, name):
        """转发上传等 SDK 能力，不改变底层客户端或原消息对象。"""
        return getattr(self.api, name)

    async def _send(self, method: str, window: int, payload: dict):
        """发送前检查窗口；仅执行一次请求，失败时阻止错误回复重入。"""
        expired = self.initial_age + monotonic() - self.started_at >= window
        if expired:
            payload = {key: value for key, value in payload.items()
                       if key not in {"msg_id", "msg_seq", "event_id", "message_reference"}}
            _log.info("QQ 回复窗口已过期，尝试主动发送: method=%s", method)
        try:
            result = await getattr(self.api, method)(**payload)
            if not isinstance(result, dict) or not result.get("id"):
                raise RuntimeError("QQ 消息接口未返回确认 ID")
            return result
        except Exception as exc:
            _log.exception("QQ 消息发送失败，不自动重试: method=%s proactive=%s", method, expired)
            raise ReplyDeliveryError("QQ 消息未确认送达") from exc

    async def post_group_message(self, **payload):
        """为群文字及媒体在真正发送时检查五分钟窗口。"""
        return await self._send("post_group_message", 300, payload)

    async def post_c2c_message(self, **payload):
        """为私聊在真正发送时检查六十分钟窗口。"""
        return await self._send("post_c2c_message", 3600, payload)

    async def reply(self, **payload):
        """使用原会话发送回复，保留文字、Markdown 和键盘参数。"""
        payload = {**payload, "msg_id": self.message.id}
        if self.is_group:
            return await self.post_group_message(group_openid=self.group_id, **payload)
        return await self.post_c2c_message(openid=self.message.author.user_openid, **payload)
