"""QQ Bot 事件适配层。"""
import logging
import random
import re
import traceback
from collections import OrderedDict
from time import monotonic

from botpy import Client
from botpy.message import C2CMessage, GroupMessage

from config import QQ_BOT_APPID
from handlers.command_router import route_command
from features.agent.service import handle_agent
from features.gitee_notifications.monitor import (
    handle_group_message as handle_gitee_group_message,
    start_gitee_monitor,
)
from features.interactions.dispatcher import handle_interaction
from presentation import messages
from features.commands.text import clean_message
from external_tools.storage.group_memory import (
    get_recent_group_messages,
    record_group_message,
)
from presentation.markdown import markdown_payload
from presentation.reply_payload import command_reply_payload
from external_tools.qq.botpy_compat import install_group_message_parser_compat


install_group_message_parser_compat()


_log = logging.getLogger("mlcbot")
_ERROR_REPLY = markdown_payload(messages.PROCESSING_ERROR)
_GROUP_MESSAGE_DEDUP_LIMIT = 4096
_AGENT_AUTO_REPLY_PROBABILITY = 0.05
_AT_MENTION_PATTERN = re.compile(r"<@!?(\w+)>")
_seen_group_messages: OrderedDict[tuple[str, str], dict[str, object]] = OrderedDict()


class MLCBot(Client):
    """将 QQ 事件转换为命令路由和按钮互动调用。"""

    async def on_ready(self):
        """记录机器人上线状态并启动 Gitee 后台监听。"""
        _log.info("机器人已上线！AppID: %s", QQ_BOT_APPID)
        await start_gitee_monitor()

    async def on_group_add_robot(self, event):
        """记录机器人加入群聊的事件。"""
        _log.info(
            "[机器人入群] group=%s operator=%s",
            event.group_openid,
            event.op_member_openid,
        )

    async def on_group_at_message_create(self, message: GroupMessage):
        """处理群聊中 @机器人的消息。"""
        await handle_group_message(
            message,
            api=getattr(self, "api", None),
            is_at_message=True,
        )

    async def on_group_message_create(self, message: GroupMessage):
        """处理开启全量消息模式后收到的群聊消息。"""
        await handle_group_message(
            message,
            api=getattr(self, "api", None),
            is_at_message=_has_at_mention(message),
        )

    async def on_c2c_message_create(self, message: C2CMessage):
        """处理私聊命令。"""
        await handle_c2c_message(message)

    async def on_interaction_create(self, interaction):
        """处理内联键盘回调。"""
        await handle_interaction(self.api, interaction, _log)


async def handle_group_message(
    message: GroupMessage,
    *,
    api=None,
    is_at_message: bool = False,
) -> None:
    """记录群消息、尝试提交通知回复，并把未匹配消息交给 agent 兜底。"""
    received_at = monotonic()
    is_duplicate, state = _register_group_message(message, is_at_message)
    if is_duplicate:
        _log.debug(
            "忽略重复群消息 group=%s message=%s seq=%s",
            getattr(message, "group_openid", ""),
            getattr(message, "id", ""),
            getattr(message, "msg_seq", ""),
        )
        if is_at_message and state and state.get("status") == "unmatched":
            await handle_command_message(
                message,
                _group_user_id(message),
                is_group=True,
                group_id=getattr(message, "group_openid", "") or "",
                force_agent=True,
            )
            state["status"] = "handled"
        return

    user_id = _group_user_id(message)
    group_id = getattr(message, "group_openid", "") or ""
    _log.info("[群消息] group=%s user=%s content=%s", group_id, user_id, message.content)
    record_group_message(
        group_id,
        user_id,
        clean_message(message.content),
        message_id=str(getattr(message, "id", "") or ""),
    )
    handled = await handle_command_message(
        message,
        user_id,
        is_group=True,
        group_id=group_id,
        api=api,
        is_at_message=is_at_message,
    )
    if state is not None:
        if not handled and state.get("at_message_pending"):
            handled = await handle_command_message(
                message,
                user_id,
                is_group=True,
                group_id=group_id,
                force_agent=True,
            )
            state["status"] = "handled"
        else:
            state["status"] = "handled" if handled else "unmatched"
    try:
        await handle_gitee_group_message(
            message,
            replies_already_sent=handled,
            received_at=received_at,
        )
    except Exception:
        _log.exception("处理 Gitee 提交通知队列失败")


def _group_user_id(message: GroupMessage) -> str:
    """读取群消息发送者的 OpenID，缺失时返回空字符串。"""
    return getattr(getattr(message, "author", None), "member_openid", "") or ""


def _has_at_mention(message: GroupMessage) -> bool:
    """检查全量消息是否明确 @ 了当前机器人。"""
    content = getattr(message, "content", "") or ""
    bot_id = str(QQ_BOT_APPID or "").strip()
    if not bot_id:
        return False
    return bot_id in _AT_MENTION_PATTERN.findall(content)


def _register_group_message(
    message: GroupMessage,
    is_at_message: bool,
) -> tuple[bool, dict[str, object] | None]:
    """登记群消息并标记并发到达的 @ 事件，返回是否为重复投递。"""
    message_id = getattr(message, "id", None)
    if message_id is None:
        return False, None

    message_seq = getattr(message, "msg_seq", None)
    key = (str(message_id), "" if message_seq is None else str(message_seq))
    state = _seen_group_messages.get(key)
    if state is not None:
        _seen_group_messages.move_to_end(key)
        if is_at_message and state.get("status") == "processing":
            state["at_message_pending"] = True
        return True, state

    state = {"status": "processing", "at_message_pending": False}
    _seen_group_messages[key] = state
    if len(_seen_group_messages) > _GROUP_MESSAGE_DEDUP_LIMIT:
        _seen_group_messages.popitem(last=False)
    return False, state


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
    is_at_message: bool = False,
    force_agent: bool = False,
) -> bool:
    """执行文本命令或 agent 兜底，并返回是否已经发送回复。"""
    try:
        if force_agent:
            reply_text = await _agent_reply_text(message, user_id, group_id)
        else:
            reply_text = await route_command(
                message.content or "",
                user_id,
                is_group=is_group,
                api=api,
                group_openid=group_id,
                message_id=getattr(message, "id", None),
            )
            if not reply_text and is_group:
                should_auto_reply = (
                    is_at_message
                    or random.random() < _AGENT_AUTO_REPLY_PROBABILITY
                )
                if should_auto_reply:
                    reply_text = await _agent_reply_text(message, user_id, group_id)
        if not reply_text:
            return False

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
        return True
    except Exception:
        _log.error("处理消息异常: %s", traceback.format_exc())
        await message.reply(**_ERROR_REPLY)
        return True


async def _agent_reply_text(
    message: GroupMessage | C2CMessage,
    user_id: str,
    group_id: str,
) -> str:
    """准备当前问题和近期群聊上下文，调用 agent 生成回复。"""
    _log.info(
        "[Agent 自动回复请求] group=%s user=%s message=%s",
        group_id,
        user_id,
        getattr(message, "id", ""),
    )
    question = clean_message(message.content)
    if not question:
        question = "请结合最近的群聊内容参与对话。"
    group_context = get_recent_group_messages(
        group_id,
        exclude_message_id=str(getattr(message, "id", "") or ""),
    )
    response = await handle_agent(question, user_id, group_context=group_context)
    return messages.agent_reply(response)
