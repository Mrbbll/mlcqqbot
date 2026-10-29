"""命令文本清洗与标准化。"""
import re
from collections.abc import Sequence


def clean_message(content: str | None) -> str:
    """去除 QQ 原生提及标记并保留普通 @ 文本。"""
    content = re.sub(r"<@!?\w+>", "", content or "")
    return content.strip()


def normalize_command(content: str | None) -> str:
    """将用户输入标准化为以 ``/`` 开头的命令。"""
    content = clean_message(content)
    if content and not content.startswith("/"):
        return f"/{content}"
    return content


def has_command_prefix(content: str | None, prefixes: Sequence[str]) -> bool:
    """判断消息是否以完整命令前缀开头，参数需由空白分隔。"""
    command = normalize_command(content)
    for prefix in prefixes:
        normalized_prefix = normalize_command(prefix)
        if command == normalized_prefix:
            return True
        if command.startswith(normalized_prefix) and len(command) > len(normalized_prefix):
            if command[len(normalized_prefix)].isspace():
                return True
    return False
