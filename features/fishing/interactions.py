"""钓鱼功能的按钮互动处理入口。"""
import logging
from typing import Any, Awaitable, Callable

from features.fishing.service import Fish, HookResult
from presentation import messages
from presentation.markdown import markdown_payload


ReplySender = Callable[[Any, Any, dict[str, Any], logging.Logger], Awaitable[None]]
FishClaim = Callable[[str, str, str], tuple[HookResult, Fish | None]]


async def handle_fishing_interaction(
    api: Any,
    interaction: Any,
    token: str,
    logger: logging.Logger,
    *,
    send_reply: ReplySender,
    claim: FishClaim,
) -> None:
    """校验拉钩按钮的点击者和时限，并发送渔获结果。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_reply(
            api,
            interaction,
            markdown_payload(messages.FISHING_GROUP_ONLY),
            logger,
        )
        return

    result, fish = claim(token, group_openid, member_openid)
    if result == "not_owner":
        reply = messages.FISHING_NOT_OWNER
    elif result == "expired" or fish is None:
        reply = messages.FISHING_EXPIRED
    else:
        reply = messages.fishing_result(
            member_openid,
            fish.species,
            fish.size_cm,
        )
        logger.info(
            "[钓鱼成功] group=%s user=%s species=%s size_cm=%.1f",
            group_openid,
            member_openid,
            fish.species,
            fish.size_cm,
        )
    await send_reply(api, interaction, markdown_payload(reply), logger)
