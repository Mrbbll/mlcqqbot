"""QQ 内联按钮互动事件处理。"""
import logging
import traceback
from typing import Any

from handlers.command_router import route_command
from handlers.group_mute import mute_group_member
from handlers.lottery import draw_mute_minutes
from utils import messages
from utils.keyboard import LOTTERY_ACTION, command_from_interaction
from utils.markdown import markdown_payload
from utils.reply_payload import command_reply_payload


async def send_interaction_reply(
    api: Any,
    interaction: Any,
    payload: dict[str, Any],
    logger: logging.Logger,
) -> None:
    """将按钮结果发送回触发它的群聊或私聊。"""
    group_openid = getattr(interaction, "group_openid", None)
    user_openid = getattr(interaction, "user_openid", None)
    if group_openid:
        await api.post_group_message(group_openid=group_openid, **payload)
    elif user_openid:
        await api.post_c2c_message(openid=user_openid, **payload)
    else:
        logger.warning("按钮事件缺少群 OpenID 和用户 OpenID: %r", interaction)


async def handle_interaction(
    api: Any,
    interaction: Any,
    logger: logging.Logger,
) -> None:
    """确认并分发 type=11 内联键盘互动事件。"""
    if getattr(interaction, "type", None) != 11:
        return

    action = command_from_interaction(interaction)
    try:
        await api.on_interaction_result(interaction.id, 0 if action else 1)
    except Exception:
        logger.error("确认按钮事件异常: %s", traceback.format_exc())

    if not action:
        logger.warning("收到未识别的按钮事件: %r", interaction)
        return

    user_id = (
        getattr(interaction, "group_member_openid", None)
        or getattr(interaction, "user_openid", None)
        or ""
    )
    try:
        if action == LOTTERY_ACTION:
            await _handle_lottery_interaction(api, interaction, logger)
            return

        group_openid = getattr(interaction, "group_openid", None) or ""
        reply_text = await route_command(
            action,
            user_id,
            is_group=bool(group_openid),
            api=api,
            group_openid=group_openid,
        )
        if reply_text:
            await send_interaction_reply(
                api,
                interaction,
                command_reply_payload(action, reply_text),
                logger,
            )
    except Exception:
        logger.error("处理按钮事件异常: %s", traceback.format_exc())
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.PROCESSING_ERROR),
            logger,
        )


async def _handle_lottery_interaction(
    api: Any,
    interaction: Any,
    logger: logging.Logger,
) -> None:
    """为点击抽奖按钮的群成员开奖并执行禁言。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.LOTTERY_BUTTON_GROUP_ONLY),
            logger,
        )
        return

    minutes = draw_mute_minutes()
    if minutes > 0:
        try:
            await mute_group_member(api, group_openid, member_openid, minutes)
        except Exception:
            logger.error("执行抽奖禁言异常: %s", traceback.format_exc())
            await send_interaction_reply(
                api,
                interaction,
                markdown_payload(messages.LOTTERY_MUTE_FAILED),
                logger,
            )
            return

    logger.info(
        "[抽奖] group=%s user=%s mute_minutes=%s",
        group_openid,
        member_openid,
        minutes,
    )
    await send_interaction_reply(
        api,
        interaction,
        markdown_payload(messages.lottery_result(minutes, member_openid)),
        logger,
    )
