"""命令文本清洗与标准化。"""
import re


def clean_message(content: str) -> str:
    """去除机器人 mention 并清理首尾空白。"""
    content = re.sub(r"<@!?\w+>", "", content)
    content = re.sub(r"@\S+", "", content)
    return content.strip()


def normalize_command(content: str) -> str:
    """将用户输入标准化为以 ``/`` 开头的命令。"""
    content = clean_message(content)
    if content and not content.startswith("/"):
        return f"/{content}"
    return content
