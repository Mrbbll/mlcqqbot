"""QQ 自定义 Markdown 消息工具。

使用方式：
    from utils.markdown import inline_code, markdown_payload, mention_user

    content = "**标题**\n\n- **实例**：" + inline_code("scf")
    await message.reply(**markdown_payload(content))

功能说明：
    - ``markdown_payload``：构造 qq-botpy 所需的自定义 Markdown 消息参数，
      包含 ``msg_type=2`` 和 ``markdown.content``。
    - ``escape_markdown``：将动态普通文本中的 Markdown 控制字符转义，
      防止其意外改变消息排版。
    - ``inline_code``：安全地将动态值包裹为行内代码，支持值中包含反引号。
    - ``mention_user``：生成 QQ Markdown 用户提及，由客户端显示真实群昵称。

本模块仅构造消息内容和参数，不依赖 botpy；群聊与私聊均可复用。
"""
from html import escape
from typing import Any


_MARKDOWN_SPECIAL_CHARS = frozenset(r"\\`*_{}[]()#+-.!|>~")


def escape_markdown(value: object) -> str:
    """转义普通文本中的 Markdown 特殊字符。"""
    text = str(value)
    escaped: list[str] = []
    for char in text:
        if char in _MARKDOWN_SPECIAL_CHARS:
            escaped.append("\\")
        escaped.append(char)
    return "".join(escaped)


def inline_code(value: object) -> str:
    """将动态值包装为 Markdown 行内代码，并兼容值中包含反引号的情况。"""
    text = str(value).replace("\r", " ").replace("\n", " ")
    longest_run = 0
    current_run = 0
    for char in text:
        if char == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    delimiter = "`" * (longest_run + 1)
    return f"{delimiter}{text}{delimiter}"


def mention_user(user_openid: object) -> str:
    """生成 QQ Markdown 用户提及，客户端会将其渲染为真实群昵称。"""
    openid = str(user_openid).strip()
    if not openid:
        raise ValueError("生成用户提及时缺少 OpenID")
    return f'<qqbot-at-user id="{escape(openid, quote=True)}" />'


def markdown_payload(content: str) -> dict[str, Any]:
    """构造 qq-botpy 的自定义 Markdown 消息参数。"""
    return {
        "msg_type": 2,
        "markdown": {
            "content": content,
        },
    }
