"""命令回复与内联键盘载荷构造。"""
from typing import Any

from utils.command_text import normalize_command
from utils.keyboard import help_keyboard_payload, lottery_keyboard_payload
from utils.markdown import markdown_payload
from utils.permissions import check_superuser


def is_help_command(content: str) -> bool:
    """判断消息是否为帮助命令。"""
    return normalize_command(content).startswith(("/指令帮助", "/help"))


def is_lottery_command(content: str) -> bool:
    """判断消息是否为抽奖命令。"""
    return normalize_command(content).startswith("/抽奖")


def command_reply_payload(
    content: str,
    reply_text: str,
    user_id: str = "",
    *,
    is_group: bool = True,
) -> dict[str, Any]:
    """构造 Markdown 命令回复，并在需要时附加键盘。"""
    payload = markdown_payload(reply_text)
    if is_help_command(content):
        payload["keyboard"] = help_keyboard_payload()
    elif is_group and is_lottery_command(content) and check_superuser(user_id):
        payload["keyboard"] = lottery_keyboard_payload()
    return payload
