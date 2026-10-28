"""QQ Bot 事件适配层。"""
import logging
import random
import re
import traceback
from collections import OrderedDict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from botpy import Client
from botpy.message import C2CMessage, GroupMessage

from config import QQ_BOT_APPID, QQ_BOT_MENTION_OPENIDS
from handlers.command_router import route_command
from features.agent.service import AgentReply, handle_agent
from features.agent.file_input import extract_file_attachments, read_file_attachments
from external_tools.storage.group_memory import get_recent_group_file_attachments
from features.agent.emojipic import load_emoji_library
from features.agent.reply_memory import record_bot_reply
from features.agent.vision import (
    download_image_attachments,
    extract_image_attachments,
)
from features.bilibili_notifications.monitor import (
    handle_group_message as handle_bilibili_group_message,
    start_bilibili_monitor,
)
from features.gitee_notifications.monitor import (
    handle_group_message as handle_gitee_group_message,
    start_gitee_monitor,
)
from features.qq_game_bridge import (
    forward_group_message as forward_group_message_to_game,
    start_onebot_ws_server,
)
from features.interactions.dispatcher import handle_interaction
from presentation import messages
from features.commands.text import clean_message
from external_tools.storage.group_memory import (
    get_recent_group_image_attachments,
    get_recent_group_messages,
    record_group_message,
)
from presentation.markdown import markdown_payload
from presentation.reply_payload import command_reply_payload
from external_tools.qq.botpy_compat import (
    get_group_message_indices,
    get_group_message_raw_data,
    install_group_message_parser_compat,
)
from external_tools.qq.media_sender import send_group_image
from features.file_sender import send_group_file


install_group_message_parser_compat()


_log = logging.getLogger("mlcbot")
_ERROR_REPLY = markdown_payload(messages.PROCESSING_ERROR)
_GROUP_MESSAGE_DEDUP_LIMIT = 4096
_AGENT_AUTO_REPLY_PROBABILITY = 0.01
_AT_MENTION_PATTERN = re.compile(r"<@!?(\w+)>")
_MEMBER_OPENID_PATTERN = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")
_seen_group_messages: OrderedDict[tuple[str, str], dict[str, object]] = OrderedDict()


class MLCBot(Client):
    """将 QQ 事件转换为命令路由和按钮互动调用。"""

    async def on_ready(self):
        """记录机器人上线状态并启动后台监听和 OneBot WebSocket 服务。"""
        _log.info("机器人已上线！AppID: %s", QQ_BOT_APPID)
        try:
            emoji_count = load_emoji_library()
            _log.info("表情包收藏库已加载: count=%s", emoji_count)
        except Exception:
            _log.exception("表情包收藏库加载失败")
        await start_gitee_monitor()
        await start_bilibili_monitor()
        await start_onebot_ws_server()

    async def on_group_add_robot(self, event):
        """记录机器人加入群聊的事件。"""
        _log.info(
            "[机器人入群] group=%s operator=%s",
            event.group_openid,
            event.op_member_openid,
        )

    async def on_group_at_message_create(self, message: GroupMessage):
        """处理群聊中 @机器人的消息。"""
        _log.info(
            "[收到群@机器人事件] group=%s user=%s message=%s",
            getattr(message, "group_openid", ""),
            _group_user_id(message),
            getattr(message, "id", ""),
        )
        await handle_group_message(
            message,
            api=getattr(self, "api", None),
            is_at_message=True,
        )

    async def on_group_message_create(self, message: GroupMessage):
        """处理全量群消息，并按配置的机器人 OpenID 识别 @。"""
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
    """先转发每条唯一群消息，再记录消息并尝试命令、Agent 和通知处理。"""
    received_at = monotonic()
    is_duplicate, state = _register_group_message(message, is_at_message)
    if is_duplicate:
        get_group_message_raw_data(message)
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
                api=api,
                force_agent=True,
            )
            state["status"] = "handled"
        return

    try:
        await forward_group_message_to_game(message)
    except Exception:
        _log.exception("转发 QQ 群消息到游戏失败")

    user_id = _group_user_id(message)
    group_id = getattr(message, "group_openid", "") or ""
    raw_message_data = get_group_message_raw_data(message)
    image_attachments = extract_image_attachments(message, raw_message_data)
    message_index, reference_index = get_group_message_indices(raw_message_data)
    reference_message_id = reference_index or _group_reference_id(message)
    raw_message_type = str(
        raw_message_data.get("message_type")
        or raw_message_data.get("messageType")
        or ""
    )
    message_elements = (
        raw_message_data.get("msg_elements")
        or raw_message_data.get("msgElements")
        or []
    )
    if not isinstance(message_elements, (list, tuple)):
        message_elements = []
    quote_elements = [
        element
        for element in message_elements
        if isinstance(element, dict)
        and str(
            element.get("message_type")
            or element.get("messageType")
            or raw_message_type
        ) == "103"
    ]
    quote_attachment_count = sum(
        len(element.get("attachments") or [])
        for element in quote_elements
        if isinstance(element.get("attachments") or [], (list, tuple))
    )
    _log.info(
        "[群消息] group=%s user=%s at_bot=%s message_type=%s has_ref_marker=%s "
        "has_ref_idx=%s msg_elements=%s quote_elements=%s quote_attachments=%s "
        "has_image=%s image_count=%s content=%s",
        group_id,
        user_id,
        is_at_message,
        raw_message_type or "unknown",
        bool(reference_message_id or raw_message_type == "103" or quote_elements),
        bool(reference_index),
        len(message_elements),
        len(quote_elements),
        quote_attachment_count,
        bool(image_attachments),
        len(image_attachments),
        message.content,
    )
    record_group_message(
        group_id,
        user_id,
        clean_message(message.content),
        message_id=str(getattr(message, "id", "") or ""),
        image_attachments=image_attachments,
        file_attachments=extract_file_attachments(message, raw_message_data),
        reference_message_id=reference_message_id,
        message_index=message_index,
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
                api=api,
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
    try:
        await handle_bilibili_group_message(message)
    except Exception:
        _log.exception("处理 Bilibili 直播通知队列失败")


def _group_user_id(message: GroupMessage) -> str:
    """读取群消息发送者的 OpenID，缺失时返回空字符串。"""
    return getattr(getattr(message, "author", None), "member_openid", "") or ""


def _agent_mentionable_user_ids(message: GroupMessage, user_id: str) -> list[str]:
    """返回当前发言者、本条消息显式 @ 到及正文明确提供的非机器人成员 OpenID。"""
    candidates = [user_id.strip()] if user_id.strip() else []
    for mention in getattr(message, "mentions", None) or []:
        for field in ("member_openid", "id", "user_openid"):
            mention_id = (
                mention.get(field, "")
                if isinstance(mention, dict)
                else getattr(mention, field, "")
            )
            mention_id = str(mention_id or "").strip()
            if mention_id:
                if mention_id not in QQ_BOT_MENTION_OPENIDS:
                    candidates.append(mention_id)
                break
    content = str(getattr(message, "content", "") or "")
    for match in _MEMBER_OPENID_PATTERN.finditer(content):
        mention_id = match.group(0)
        if mention_id not in QQ_BOT_MENTION_OPENIDS:
            candidates.append(mention_id)
    return list(dict.fromkeys(candidates))


def _group_reference_id(message: GroupMessage) -> str:
    """读取群消息引用目标的消息 ID。"""
    reference = getattr(message, "message_reference", None)
    message_id = (
        reference.get("message_id")
        if isinstance(reference, dict)
        else getattr(reference, "message_id", "")
    )
    return str(message_id or "").strip()


def _has_at_mention(message: GroupMessage) -> bool:
    """匹配消息中的机器人群内 OpenID，避免把提及其他成员当成提及机器人。"""
    mention_ids = _AT_MENTION_PATTERN.findall(getattr(message, "content", "") or "")
    return any(mention_id in QQ_BOT_MENTION_OPENIDS for mention_id in mention_ids)


def _register_group_message(
    message: GroupMessage,
    is_at_message: bool,
) -> tuple[bool, dict[str, object] | None]:
    """登记群消息并标记并发到达的 @ 事件，返回是否为重复投递。"""
    message_id = getattr(message, "id", None)
    if message_id is None:
        return False, None

    # QQ 可能用不同事件回调重复投递同一消息，按消息 ID 去重而不依赖序号。
    key = (str(message_id), "")
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
        emoji_image_path = None
        emoji_metadata = None
        file_paths = ()
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
        if isinstance(reply_text, AgentReply):
            emoji_image_path = reply_text.emoji_image_path
            emoji_metadata = reply_text.emoji_metadata
            file_paths = reply_text.file_paths
            reply_text = reply_text.text
        if not reply_text and emoji_image_path is None and not file_paths:
            return False

        if reply_text:
            payload = command_reply_payload(
                message.content or "",
                reply_text,
                user_id,
                is_group=is_group,
            )
            if "keyboard" in payload:
                scope = "group=%s" % group_id if is_group else "c2c"
                _log.info("[内联键盘] %s user=%s", scope, user_id)
            reply_result = await message.reply(**payload)
            if is_group and group_id:
                record_bot_reply(group_id, reply_text, reply_result)

        if emoji_image_path is not None:
            if not is_group or not group_id:
                _log.warning("跳过表情包发送：当前消息没有群聊上下文")
            else:
                try:
                    image_result = await send_group_image(
                        api or getattr(message, "_api", None),
                        group_id,
                        emoji_image_path,
                        str(getattr(message, "id", "") or ""),
                        message_sequence=2 if reply_text else 1,
                    )
                    record_bot_reply(group_id, "[已发送表情包]", image_result, emoji=emoji_metadata)
                    _log.info(
                        "Agent 表情包已发送: group=%s message=%s",
                        group_id,
                        getattr(message, "id", ""),
                    )
                except Exception:
                    _log.exception(
                        "Agent 表情包发送失败: group=%s message=%s",
                        group_id,
                        getattr(message, "id", ""),
                    )
        if file_paths:
            # 为文字、表情包及文件使用不同序号，上传不占用回复序号。
            sequence = 1 + bool(reply_text) + (emoji_image_path is not None)
            for file_path in file_paths[:1]:
                try:
                    result = await send_group_file(
                        api or getattr(message, "_api", None), group_id, file_path,
                        str(getattr(message, "id", "") or ""), message_sequence=sequence,
                    )
                    if is_group and group_id:
                        record_bot_reply(group_id, f"[已发送文件] {file_path.name}", result)
                except Exception:
                    _log.exception("Agent 文件发送失败: group=%s", group_id)
                    failure = "文件发送失败，尚未确认送达；请检查 QQ 普通文件发送权限、文件大小及服务日志。"
                    failure_result = await message.reply(content=failure, msg_seq=sequence + 1)
                    if is_group and group_id:
                        record_bot_reply(group_id, failure, failure_result)
        return True
    except Exception:
        _log.error("处理消息异常: %s", traceback.format_exc())
        await message.reply(**_ERROR_REPLY)
        return True


async def _agent_reply_text(
    message: GroupMessage | C2CMessage,
    user_id: str,
    group_id: str,
) -> str | AgentReply:
    """准备当前问题和近期群聊上下文，调用 agent 生成回复。"""
    _log.info(
        "[Agent 自动回复请求] group=%s user=%s message=%s",
        group_id,
        user_id,
        getattr(message, "id", ""),
    )
    question = clean_message(message.content)
    tool_question = question
    if not question:
        question = "请结合最近的群聊内容参与对话。"
    group_context = get_recent_group_messages(
        group_id,
        exclude_message_id=str(getattr(message, "id", "") or ""),
        referenced_message_ids=[_group_reference_id(message)],
    )
    image_attachments = get_recent_group_image_attachments(
        group_id,
        current_message_id=str(getattr(message, "id", "") or ""),
        referenced_message_ids=[_group_reference_id(message)],
    )
    current_message_id = str(getattr(message, "id", "") or "")
    file_attachments = get_recent_group_file_attachments(
        group_id, current_message_id=current_message_id,
        reference_message_id=_group_reference_id(message),
        include_recent=any(word in question for word in ("文件", "附件", "日志", "刚才", "刚刚")),
    )
    if not file_attachments:
        file_attachments = extract_file_attachments(message)
    file_inputs, skipped_files = await read_file_attachments(file_attachments, getattr(message, "_api", None))
    _log.info(
        "Agent 文件输入状态: group=%s message=%s attachments=%d downloaded=%d skipped=%d",
        group_id, current_message_id, len(file_attachments), len(file_inputs), len(skipped_files),
    )
    if skipped_files:
        question += "\n系统提示：以下附件未读取，不得猜测内容：" + "；".join(skipped_files)
    current_image_count = sum(
        attachment.get("relation") == "当前消息"
        for attachment in image_attachments
    )
    with TemporaryDirectory(prefix="mlcbot-agent-images-") as cache_directory:
        image_inputs, skipped_images = await download_image_attachments(
            image_attachments,
            getattr(message, "_api", None),
            Path(cache_directory),
            group_id=group_id,
        )
        _log.info(
            "Agent 图片输入状态: group=%s message=%s attachments=%d current=%d referenced=%d downloaded=%d skipped=%s",
            group_id,
            current_message_id,
            len(image_attachments),
            current_image_count,
            sum(item.get("relation") == "引用消息" for item in image_attachments),
            len(image_inputs),
            skipped_images,
        )
        if skipped_images:
            question = (
                f"{question}\n\n"
                "系统提示：本条消息附带的部分图片未能提供给模型（"
                f"{'；'.join(skipped_images)}），请勿猜测未读取图片的内容。"
            )
        response = await handle_agent(
            question,
            user_id,
            group_id=group_id,
            group_context=group_context,
            image_inputs=image_inputs,
            file_inputs=file_inputs,
            mentionable_user_ids=_agent_mentionable_user_ids(message, user_id),
            tool_question=tool_question,
            current_message_has_image=current_image_count > 0,
            current_message_image_count=current_image_count,
        )
    if isinstance(response, AgentReply):
        return AgentReply(
            messages.agent_reply(response.text),
            response.emoji_image_path,
            response.emoji_metadata,
            response.file_paths,
        )
    return messages.agent_reply(response)
