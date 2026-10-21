"""禁言功能的按钮互动处理。"""
import logging
import traceback
from typing import Any, Awaitable, Callable

from external_tools.qq.group_moderation import mute_group_member
from features.muzzle.service import draw_mute_minutes
from presentation import messages
from presentation.markdown import markdown_payload


ReplySender = Callable[[Any, Any, dict[str, Any], logging.Logger], Awaitable[None]]


async def handle_lottery_interaction(
    api: Any,
    interaction: Any,
    logger: logging.Logger,
    *,
    send_reply: ReplySender,
    draw_minutes: Callable[[], int] = draw_mute_minutes,
    mute_member: Callable[[Any, str, str, int], Awaitable[Any]] = mute_group_member,
) -> None:
    """为点击抽奖按钮的群成员开奖并执行禁言。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_reply(
            api,
            interaction,
            markdown_payload(messages.LOTTERY_BUTTON_GROUP_ONLY),
            logger,
        )
        return

    minutes = draw_minutes()
    if minutes > 0:
        try:
            await mute_member(api, group_openid, member_openid, minutes)
        except Exception:
            logger.error("执行抽奖禁言异常: %s", traceback.format_exc())
            await send_reply(
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
    await send_reply(
        api,
        interaction,
        markdown_payload(messages.lottery_result(minutes, member_openid)),
        logger,
    )
