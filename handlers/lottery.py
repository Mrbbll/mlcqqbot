"""抽奖命令与 QQ 群成员禁言操作。"""
import secrets

from handlers.group_mute import mute_group_member
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
