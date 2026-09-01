"""抽奖命令与 QQ 群成员禁言操作。"""
import secrets

from utils import messages
from utils.permissions import check_superuser


LOTTERY_MIN_MINUTES = 0
LOTTERY_MAX_MINUTES = 30


async def handle_lottery(user_id: str, *, is_group: bool = True) -> str:
    """处理管理员发起抽奖的命令。"""
    if not check_superuser(user_id):
        return messages.LOTTERY_PERMISSION_DENIED

    if not is_group:
        return messages.LOTTERY_GROUP_ONLY

    return messages.lottery_prompt(LOTTERY_MIN_MINUTES, LOTTERY_MAX_MINUTES)


def draw_mute_minutes() -> int:
    """随机抽取包含首尾边界的禁言分钟数。"""
    choices = LOTTERY_MAX_MINUTES - LOTTERY_MIN_MINUTES + 1
    return LOTTERY_MIN_MINUTES + secrets.randbelow(choices)


# 兼容已有导入；文案实际统一维护在 utils.messages。
lottery_result_text = messages.lottery_result
