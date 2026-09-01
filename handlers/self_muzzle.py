"""群成员自助禁言（口球）命令。"""
import secrets
from typing import Any

from handlers.group_mute import mute_group_member
from utils import messages


SELF_MUZZLE_COMMAND = "/自助口球"
SELF_MUZZLE_MIN_MINUTES = 1
SELF_MUZZLE_MAX_MINUTES = 60


def draw_self_muzzle_minutes() -> int:
    """随机抽取 1–60 分钟的自助禁言时长。"""
    choices = SELF_MUZZLE_MAX_MINUTES - SELF_MUZZLE_MIN_MINUTES + 1
    return SELF_MUZZLE_MIN_MINUTES + secrets.randbelow(choices)


async def handle_self_muzzle(
    api: Any | None,
    group_openid: str,
    member_openid: str,
    *,
    is_group: bool,
) -> str:
    """为发起命令的群成员随机禁言并返回结果文本。"""
    if not is_group:
        return messages.SELF_MUZZLE_GROUP_ONLY
    if api is None or not group_openid or not member_openid:
        return messages.SELF_MUZZLE_CONTEXT_MISSING

    minutes = draw_self_muzzle_minutes()
    try:
        await mute_group_member(api, group_openid, member_openid, minutes)
    except Exception:
        return messages.SELF_MUZZLE_FAILED

    return messages.self_muzzle_success(minutes)
