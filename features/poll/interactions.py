"""投票功能的按钮互动处理入口。"""
import asyncio
import logging
import traceback
from typing import Any, Awaitable, Callable

from external_tools.storage.poll_repository import (
    PollStoreError,
    close_poll,
    start_poll,
    submit_vote,
    toggle_vote_selection,
)
from external_tools.tencent_sheet.client import (
    TencentSheetError,
    fetch_poll_candidates,
)
from presentation import messages
from presentation.keyboard import POLL_MAX_CANDIDATES, poll_vote_keyboard_payload
from presentation.markdown import markdown_payload
from features.security.permissions import check_superuser


ReplySender = Callable[[Any, Any, dict[str, Any], logging.Logger], Awaitable[None]]


async def handle_poll_category_interaction(
    api: Any,
    interaction: Any,
    category: str,
    logger: logging.Logger,
    *,
    send_reply: ReplySender,
) -> None:
    """读取腾讯表格并在群内创建一轮动态候选投票。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_GROUP_ONLY),
            logger,
        )
        return
    if not check_superuser(member_openid):
        await send_reply(
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
        await send_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_SHEET_FAILED),
            logger,
        )
        return

    if len(candidates) > POLL_MAX_CANDIDATES:
        await send_reply(
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
        await send_reply(api, interaction, payload, logger)
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


async def handle_poll_vote_interaction(
    api: Any,
    interaction: Any,
    poll_vote: tuple[int, int],
    logger: logging.Logger,
    *,
    send_reply: ReplySender,
) -> None:
    """记录或修改群成员对当前活动投票的选择。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_reply(
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
        await send_reply(
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


async def handle_poll_submit_interaction(
    api: Any,
    interaction: Any,
    poll_id: int,
    logger: logging.Logger,
    *,
    send_reply: ReplySender,
) -> None:
    """提交群成员已选择的投票候选项。"""
    group_openid = getattr(interaction, "group_openid", None) or ""
    member_openid = getattr(interaction, "group_member_openid", None) or ""
    if not group_openid or not member_openid:
        await send_reply(
            api,
            interaction,
            markdown_payload(messages.POLL_GROUP_ONLY),
            logger,
        )
        return
    try:
        submission = submit_vote(group_openid, poll_id, member_openid)
    except PollStoreError:
        await send_reply(
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
    await send_reply(
        api,
        interaction,
        markdown_payload(
            messages.poll_submitted(
                member_openid,
                submission.candidate_names,
            )
        ),
        logger,
    )
