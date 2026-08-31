"""群成员自助禁言（口球）命令。"""
import secrets
from typing import Any

from handlers.group_mute import mute_group_member


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
        return "⚠️ **自助口球只能在群聊中使用**"
    if api is None or not group_openid or not member_openid:
        return "❌ **自助口球执行失败**\n\n缺少群聊或成员信息"

    minutes = draw_self_muzzle_minutes()
    try:
        await mute_group_member(api, group_openid, member_openid, minutes)
    except Exception:
        return (
            "❌ **自助口球执行失败**\n\n"
            "请确认机器人拥有群管理员权限，且你是普通群成员"
        )

    return (
        "# 🤐 自助口球\n\n"
        f"已为你随机禁言 **{minutes} 分钟**。"
    )
