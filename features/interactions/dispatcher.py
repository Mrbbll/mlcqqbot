"""QQ 内联按钮互动事件处理。"""
import logging
import traceback
from typing import Any

from features.fishing.interactions import handle_fishing_interaction
from features.muzzle.interactions import handle_lottery_interaction
from features.poll.interactions import (
    handle_poll_category_interaction,
    handle_poll_submit_interaction,
    handle_poll_vote_interaction,
)
from features.fishing.service import claim_fish
from features.muzzle.service import draw_mute_minutes
from handlers.command_router import route_command
from external_tools.qq.group_moderation import mute_group_member
from presentation import messages
from presentation.keyboard import (
    LOTTERY_ACTION,
    command_from_interaction,
    fishing_token_from_action,
    poll_category_from_action,
    poll_submit_from_action,
    poll_vote_from_action,
)
from presentation.markdown import markdown_payload
from presentation.reply_payload import command_reply_payload


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
            await handle_lottery_interaction(
                api,
                interaction,
                logger,
                send_reply=send_interaction_reply,
                draw_minutes=draw_mute_minutes,
                mute_member=mute_group_member,
            )
            return

        fishing_token = fishing_token_from_action(action)
        if fishing_token is not None:
            await handle_fishing_interaction(
                api,
                interaction,
                fishing_token,
                logger,
                send_reply=send_interaction_reply,
                claim=claim_fish,
            )
            return

        poll_category = poll_category_from_action(action)
        if poll_category is not None:
            await handle_poll_category_interaction(
                api,
                interaction,
                poll_category,
                logger,
                send_reply=send_interaction_reply,
            )
            return

        poll_vote = poll_vote_from_action(action)
        if poll_vote is not None:
            await handle_poll_vote_interaction(
                api,
                interaction,
                poll_vote,
                logger,
                send_reply=send_interaction_reply,
            )
            return

        poll_submit = poll_submit_from_action(action)
        if poll_submit is not None:
            await handle_poll_submit_interaction(
                api,
                interaction,
                poll_submit,
                logger,
                send_reply=send_interaction_reply,
            )
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
