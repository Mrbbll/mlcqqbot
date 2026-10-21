"""禁言功能使用的随机规则和群成员禁言操作。"""
import secrets
from typing import Any, Callable, Awaitable

from external_tools.qq.group_moderation import mute_group_member


LOTTERY_MIN_MINUTES = 0
LOTTERY_MAX_MINUTES = 30
SELF_MUZZLE_MIN_MINUTES = 1
SELF_MUZZLE_MAX_MINUTES = 60


def draw_mute_minutes() -> int:
    """随机抽取抽奖禁言分钟数，包含首尾边界。"""
    choices = LOTTERY_MAX_MINUTES - LOTTERY_MIN_MINUTES + 1
    return LOTTERY_MIN_MINUTES + secrets.randbelow(choices)


def draw_self_muzzle_minutes() -> int:
    """随机抽取自助禁言分钟数，范围为 1–60 分钟。"""
    choices = SELF_MUZZLE_MAX_MINUTES - SELF_MUZZLE_MIN_MINUTES + 1
    return SELF_MUZZLE_MIN_MINUTES + secrets.randbelow(choices)


async def apply_self_muzzle(
    api: Any,
    group_openid: str,
    member_openid: str,
    *,
    draw_minutes: Callable[[], int] = draw_self_muzzle_minutes,
    mute_member: Callable[[Any, str, str, int], Awaitable[Any]] = mute_group_member,
) -> int:
    """抽取禁言时长并通过群管理工具执行自助禁言。"""
    minutes = draw_minutes()
    await mute_member(api, group_openid, member_openid, minutes)
    return minutes
