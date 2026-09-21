"""QQ 内联按钮互动事件处理。"""
import asyncio
import logging
import traceback
from typing import Any

from handlers.command_router import route_command
from handlers.fishing import claim_fish
from handlers.group_mute import mute_group_member
from handlers.lottery import draw_mute_minutes
from utils import messages
from utils.keyboard import (
    LOTTERY_ACTION,
    POLL_MAX_CANDIDATES,
    command_from_interaction,
    fishing_token_from_action,
    poll_category_from_action,
    poll_submit_from_action,
    poll_vote_from_action,
    poll_vote_keyboard_payload,
)
from utils.markdown import markdown_payload
from utils.permissions import check_superuser
from utils.poll_store import (
    PollStoreError,
    close_poll,
    start_poll,
    submit_vote,
    toggle_vote_selection,
)
from utils.reply_payload import command_reply_payload
from utils.tencent_sheet import TencentSheetError, fetch_poll_candidates


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

        fishing_token = fishing_token_from_action(action)
        if fishing_token is not None:
            await _handle_fishing_interaction(
                api,
                interaction,
                fishing_token,
                logger,
            )
            return

        poll_category = poll_category_from_action(action)
        if poll_category is not None:
            await _handle_poll_category_interaction(
                api,
                interaction,
                poll_category,
                logger,
            )
            return

        poll_vote = poll_vote_from_action(action)
        if poll_vote is not None:
            await _handle_poll_vote_interaction(
                api,
                interaction,
                poll_vote,
                logger,
            )
            return

        poll_submit = poll_submit_from_action(action)
        if poll_submit is not None:
            await _handle_poll_submit_interaction(
                api,
                interaction,
                poll_submit,
                logger,
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


async def _handle_fishing_interaction(
    api: Any,
    interaction: Any,
    token: str,
    logger: logging.Logger,
) -> None:
    """校验拉钩按钮的点击者和时限，并发送随机渔获。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.FISHING_GROUP_ONLY),
            logger,
        )
        return

    result, fish = claim_fish(token, group_openid, member_openid)
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
    await send_interaction_reply(
        api,
        interaction,
        markdown_payload(reply),
        logger,
    )


async def _handle_poll_category_interaction(
    api: Any,
    interaction: Any,
    category: str,
    logger: logging.Logger,
) -> None:
    """读取腾讯表格并在群内创建一轮动态候选投票。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_GROUP_ONLY),
            logger,
        )
        return
    if not check_superuser(member_openid):
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_PERMISSION_DENIED),
            logger,
        )
        return

    loop = asyncio.get_running_loop()
    try:
        candidates = await loop.run_in_executor(
            None,
            fetch_poll_candidates,
            category,
        )
    except TencentSheetError:
        logger.error("读取腾讯投票表格异常: %s", traceback.format_exc())
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_SHEET_FAILED),
            logger,
        )
        return

    if len(candidates) > POLL_MAX_CANDIDATES:
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(
                messages.poll_candidate_limit(
                    len(candidates),
                    POLL_MAX_CANDIDATES,
                )
            ),
            logger,
        )
        return

    poll_id = start_poll(group_openid, category, candidates)
    payload = markdown_payload(messages.poll_started(category, candidates))
    payload["keyboard"] = poll_vote_keyboard_payload(poll_id, candidates)
    try:
        await send_interaction_reply(api, interaction, payload, logger)
    except Exception:
        close_poll(poll_id)
        raise
    logger.info(
        "[投票发起] group=%s admin=%s poll=%s category=%s candidates=%s",
        group_openid,
        member_openid,
        poll_id,
        category,
        len(candidates),
    )


async def _handle_poll_vote_interaction(
    api: Any,
    interaction: Any,
    poll_vote: tuple[int, int],
    logger: logging.Logger,
) -> None:
    """记录或修改群成员对当前活动投票的选择。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_GROUP_ONLY),
            logger,
        )
        return

    poll_id, candidate_id = poll_vote
    try:
        vote_change = toggle_vote_selection(
            group_openid,
            poll_id,
            member_openid,
            candidate_id,
        )
    except PollStoreError:
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_VOTE_UNAVAILABLE),
            logger,
        )
        return
    logger.info(
        "[投票] group=%s user=%s poll=%s candidate=%s name=%s selected=%s",
        group_openid,
        member_openid,
        poll_id,
        candidate_id,
        getattr(vote_change, "candidate_name", str(vote_change)),
        getattr(vote_change, "selected", True),
    )


async def _handle_poll_submit_interaction(
    api: Any,
    interaction: Any,
    poll_id: int,
    logger: logging.Logger,
) -> None:
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_interaction_reply(
            api, interaction, markdown_payload(messages.POLL_GROUP_ONLY), logger
        )
        return
    try:
        submission = submit_vote(group_openid, poll_id, member_openid)
    except PollStoreError:
        await send_interaction_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_SUBMIT_UNAVAILABLE),
            logger,
        )
        return
    logger.info(
        "[投票提交] group=%s user=%s poll=%s candidates=%s",
        group_openid,
        member_openid,
        poll_id,
        submission.candidate_names,
    )
    await send_interaction_reply(
        api,
        interaction,
        markdown_payload(messages.poll_submitted(member_openid, submission.candidate_names)),
        logger,
    )
