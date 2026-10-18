"""QQ Bot 事件适配层。"""
import logging
import traceback
from collections import OrderedDict

from botpy import Client
from botpy.message import C2CMessage, GroupMessage

from config import QQ_BOT_APPID
from handlers.command_router import route_command
from handlers.interaction import handle_interaction
from utils import messages
from utils.markdown import markdown_payload
from utils.reply_payload import command_reply_payload
from utils.botpy_compat import install_group_message_parser_compat


install_group_message_parser_compat()


_log = logging.getLogger("mlcbot")
_ERROR_REPLY = markdown_payload(messages.PROCESSING_ERROR)
_GROUP_MESSAGE_DEDUP_LIMIT = 4096
_seen_group_messages: OrderedDict[tuple[str, str], None] = OrderedDict()


class MLCBot(Client):
    """将 QQ 事件转换为命令路由和按钮互动调用。"""

    async def on_ready(self):
        """记录机器人成功连接到 QQ 网关。"""
        _log.info("机器人已上线！AppID: %s", QQ_BOT_APPID)

    async def on_group_add_robot(self, event):
        """记录机器人加入群聊的事件。"""
        _log.info(
            "[机器人入群] group=%s operator=%s",
            event.group_openid,
            event.op_member_openid,
        )

    async def on_group_at_message_create(self, message: GroupMessage):
        """处理群聊中 @机器人的命令消息。"""
        await handle_group_message(message, api=getattr(self, "api", None))

    async def on_group_message_create(self, message: GroupMessage):
        """处理开启全量消息模式后收到的群聊消息。"""
        await handle_group_message(message, api=getattr(self, "api", None))

    async def on_c2c_message_create(self, message: C2CMessage):
        """处理私聊命令。"""
        await handle_c2c_message(message)

    async def on_interaction_create(self, interaction):
        """处理内联键盘回调。"""
        await handle_interaction(self.api, interaction, _log)


async def handle_group_message(message: GroupMessage, *, api=None) -> None:
    """去重群消息并将命令交给通用处理函数。"""
    if _is_duplicate_group_message(message):
        _log.debug(
            "忽略重复群消息 group=%s message=%s seq=%s",
            getattr(message, "group_openid", ""),
            getattr(message, "id", ""),
            getattr(message, "msg_seq", ""),
        )
        return

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


def _is_duplicate_group_message(message: GroupMessage) -> bool:
    """使用消息 ID 和序号抑制 QQ 网关的重复投递。"""
    message_id = getattr(message, "id", None)
    if message_id is None:
        return False

    message_seq = getattr(message, "msg_seq", None)
    key = (str(message_id), "" if message_seq is None else str(message_seq))
    if key in _seen_group_messages:
        _seen_group_messages.move_to_end(key)
        return True

    _seen_group_messages[key] = None
    if len(_seen_group_messages) > _GROUP_MESSAGE_DEDUP_LIMIT:
        _seen_group_messages.popitem(last=False)
    return False


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
            message.content or "",
            user_id,
            is_group=is_group,
            api=api,
            group_openid=group_id,
            message_id=getattr(message, "id", None),
        )
        if not reply_text:
            return

        payload = command_reply_payload(
            message.content or "",
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
