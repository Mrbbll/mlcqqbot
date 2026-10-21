"""命令回复与内联键盘载荷构造。"""
from typing import Any

from features.commands.text import has_command_prefix
from presentation.keyboard import (
    help_keyboard_payload,
    lottery_keyboard_payload,
    poll_category_keyboard_payload,
)
from presentation.markdown import markdown_payload
from features.security.permissions import check_superuser


def is_help_command(content: str) -> bool:
    """判断消息是否为帮助命令。"""
    return has_command_prefix(content, ("/指令帮助", "/help"))


def is_lottery_command(content: str) -> bool:
    """判断消息是否为抽奖命令。"""
    return has_command_prefix(content, ("/抽奖",))


def is_poll_command(content: str) -> bool:
    """判断消息是否为投票发起命令，而不是投票结果命令。"""
    return has_command_prefix(content, ("/投票",)) and not has_command_prefix(
        content,
        ("/投票结果",),
    )


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
    elif is_group and is_poll_command(content) and check_superuser(user_id):
        payload["keyboard"] = poll_category_keyboard_payload()
    return payload
