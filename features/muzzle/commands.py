"""禁言功能的文本命令处理入口。"""
from typing import Any, Callable, Awaitable

from features.muzzle.service import (
    LOTTERY_MAX_MINUTES,
    LOTTERY_MIN_MINUTES,
    apply_self_muzzle,
    draw_self_muzzle_minutes,
)
from external_tools.qq.group_moderation import mute_group_member
from presentation import messages
from features.security.permissions import check_superuser


SELF_MUZZLE_COMMAND = "/自助口球"


async def handle_lottery(
    user_id: str,
    *,
    is_group: bool = True,
    has_permission: Callable[[str], bool] | None = None,
) -> str:
    """处理管理员发起群聊禁言抽奖的命令。"""
    has_permission = has_permission or check_superuser
    if not has_permission(user_id):
        return messages.LOTTERY_PERMISSION_DENIED
    if not is_group:
        return messages.LOTTERY_GROUP_ONLY
    return messages.lottery_prompt(LOTTERY_MIN_MINUTES, LOTTERY_MAX_MINUTES)


async def handle_self_muzzle(
    api: Any | None,
    group_openid: str,
    member_openid: str,
    *,
    is_group: bool,
    draw_minutes: Callable[[], int] | None = None,
    mute_member: Callable[[Any, str, str, int], Awaitable[Any]] | None = None,
) -> str:
    """为发起命令的群成员随机禁言并返回结果文本。"""
    if not is_group:
        return messages.SELF_MUZZLE_GROUP_ONLY
    if api is None or not group_openid or not member_openid:
        return messages.SELF_MUZZLE_CONTEXT_MISSING

    draw_minutes = draw_minutes or draw_self_muzzle_minutes
    mute_member = mute_member or mute_group_member
    try:
        minutes = await apply_self_muzzle(
            api,
            group_openid,
            member_openid,
            draw_minutes=draw_minutes,
            mute_member=mute_member,
        )
    except Exception:
        return messages.SELF_MUZZLE_FAILED
    return messages.self_muzzle_success(minutes)
