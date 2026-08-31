"""抽奖命令与 QQ 群成员禁言操作。"""
from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

from botpy.http import Route

from utils.permissions import check_superuser


LOTTERY_MIN_MINUTES = 0
LOTTERY_MAX_MINUTES = 30


async def handle_lottery(user_id: str, *, is_group: bool = True) -> str:
    """处理管理员发起抽奖的命令。"""
    if not check_superuser(user_id):
        return "⛔ **权限不足**\n\n仅管理员可发起抽奖"

    if not is_group:
        return "⚠️ **抽奖只能在群聊中发起**"

    return (
        "# 🎲 群聊抽奖\n\n"
        "点击下方按钮参与抽奖，将随机获得 **0–30 分钟**禁言。\n\n"
        "> 抽中 0 分钟时不会执行禁言"
    )


def draw_mute_minutes() -> int:
    """随机抽取包含首尾边界的禁言分钟数。"""
    choices = LOTTERY_MAX_MINUTES - LOTTERY_MIN_MINUTES + 1
    return LOTTERY_MIN_MINUTES + secrets.randbelow(choices)


def mute_expire_at(minutes: int) -> str:
    """把禁言分钟数转换为 QQ OpenAPI 使用的 RFC3339 到期时间。"""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return expires_at.isoformat(timespec="seconds")


async def mute_group_member(
    api: Any,
    group_openid: str,
    member_openid: str,
    minutes: int,
) -> Any:
    """调用 QQ 群管理接口禁言指定的普通群成员。"""
    member = {
        "op": "add",
        "member_openid": member_openid,
        "mute_expire_at": mute_expire_at(minutes),
    }

    # 兼容已封装新版群管理接口的 botpy。
    set_mutes = getattr(api, "set_group_member_mutes", None)
    if set_mutes is not None:
        return await set_mutes(group_openid, [member])

    # qq-botpy 1.2.x 尚未封装该接口，复用其鉴权 HTTP 客户端调用。
    route = Route(
        "POST",
        "/v2/groups/{group_openid}/restrict_chat_setting",
        group_openid=group_openid,
    )
    return await api._http.request(route, json={"members": [member]})


def lottery_result_text(minutes: int) -> str:
    """生成公开展示的抽奖结果。"""
    if minutes == 0:
        return (
            "# 🎉 抽奖结果\n\n"
            "恭喜点击按钮的群友抽中 **0 分钟**，本次免于禁言！"
        )

    return (
        "# 🎲 抽奖结果\n\n"
        f"点击按钮的群友抽中 **{minutes} 分钟**禁言，奖励已发放。"
    )
