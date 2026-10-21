"""为当前 botpy 版本补充群聊全量消息事件解析。"""
from typing import Any

from botpy.connection import ConnectionState
from botpy.message import GroupMessage


def install_group_message_parser_compat() -> None:
    """在 botpy 创建解析器表前注册缺失的全量群消息解析器。"""
    if hasattr(ConnectionState, "parse_group_message_create"):
        return

    def parse_group_message_create(
        state: ConnectionState,
        payload: dict[str, Any],
    ) -> None:
        """将 GROUP_MESSAGE_CREATE 事件转换为 botpy 群消息对象。"""
        message = GroupMessage(
            state.api,
            payload.get("id"),
            payload.get("d", {}),
        )
        state._dispatch("group_message_create", message)

    setattr(
        ConnectionState,
        "parse_group_message_create",
        parse_group_message_create,
    )
