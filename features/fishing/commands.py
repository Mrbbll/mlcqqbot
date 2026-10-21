"""钓鱼功能的文本命令处理入口。"""
from typing import Any, Callable

from features.fishing.service import draw_fishing_delay, start_fishing_session
from presentation import messages


async def handle_start_fishing(
    api: Any,
    group_openid: str,
    user_openid: str,
    *,
    is_group: bool = True,
    reply_message_id: str | None = None,
    draw_delay: Callable[[], int] | None = None,
) -> str:
    """校验群聊上下文并开始后台钓鱼会话。"""
    if not is_group:
        return messages.FISHING_GROUP_ONLY
    if not api or not group_openid or not user_openid or not reply_message_id:
        return messages.FISHING_CONTEXT_MISSING

    draw_delay = draw_delay or draw_fishing_delay
    started = start_fishing_session(
        api,
        group_openid,
        user_openid,
        reply_message_id=reply_message_id,
        draw_delay=draw_delay,
    )
    if started:
        return messages.FISHING_STARTED
    return messages.FISHING_ALREADY_ACTIVE
