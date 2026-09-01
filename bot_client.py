"""QQ Bot 事件适配层。"""
import logging
import traceback

from botpy import Client
from botpy.message import C2CMessage, GroupMessage

from config import QQ_BOT_APPID
from handlers.command_router import route_command
from handlers.interaction import handle_interaction
from utils import messages
from utils.markdown import markdown_payload
from utils.reply_payload import command_reply_payload


_log = logging.getLogger("mlcbot")
_ERROR_REPLY = markdown_payload(messages.PROCESSING_ERROR)


class MLCBot(Client):
    """将 QQ 事件转换为命令路由和按钮互动调用。"""

    async def on_ready(self):
        _log.info("机器人已上线！AppID: %s", QQ_BOT_APPID)

    async def on_group_add_robot(self, event):
        _log.info(
            "[机器人入群] group=%s operator=%s",
            event.group_openid,
            event.op_member_openid,
        )

    async def on_group_at_message_create(self, message: GroupMessage):
        """处理群聊 @机器人的命令。"""
        await handle_group_message(message, api=getattr(self, "api", None))

    async def on_c2c_message_create(self, message: C2CMessage):
        """处理私聊命令。"""
        await handle_c2c_message(message)

    async def on_interaction_create(self, interaction):
        """处理内联键盘回调。"""
        await handle_interaction(self.api, interaction, _log)


async def handle_group_message(message: GroupMessage, *, api=None) -> None:
    """提取群消息上下文后交给通用命令处理函数。"""
    user_id = message.author.member_openid if message.author else ""
    group_id = message.group_openid
    _log.info("[群消息] group=%s user=%s content=%s", group_id, user_id, message.content)
    await handle_command_message(
        message,
        user_id,
        is_group=True,
        group_id=group_id,
        api=api,
    )


async def handle_c2c_message(message: C2CMessage) -> None:
    """提取私聊消息上下文后交给通用命令处理函数。"""
    user_id = message.author.user_openid if message.author else ""
    _log.info("[私聊] user=%s content=%s", user_id, message.content)
    await handle_command_message(message, user_id, is_group=False)


async def handle_command_message(
    message: GroupMessage | C2CMessage,
    user_id: str,
    *,
    is_group: bool,
    group_id: str = "",
    api=None,
) -> None:
    """执行文本命令并回复统一格式的载荷。"""
    try:
        reply_text = await route_command(
            message.content,
            user_id,
            is_group=is_group,
            api=api,
            group_openid=group_id,
        )
        if not reply_text:
            return

        payload = command_reply_payload(
            message.content,
            reply_text,
            user_id,
            is_group=is_group,
        )
        if "keyboard" in payload:
            scope = "group=%s" % group_id if is_group else "c2c"
            _log.info("[内联键盘] %s user=%s", scope, user_id)
        await message.reply(**payload)
    except Exception:
        _log.error("处理消息异常: %s", traceback.format_exc())
        await message.reply(**_ERROR_REPLY)
