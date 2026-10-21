"""为当前 botpy 版本补充群聊全量消息事件解析。"""
from typing import Any

from botpy.connection import ConnectionState
from botpy.message import GroupMessage


def install_group_message_parser_compat() -> None:
    """在 botpy 创建解析器表前注册缺失的全量群消息解析器。"""
    _install_group_message_nickname_compat()
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


def _install_group_message_nickname_compat() -> None:
    """保留 BotPy 群消息作者对象解析时会丢弃的 username 和成员 nick。"""
    if getattr(GroupMessage, "_mlc_nickname_compat_installed", False):
        return

    original_init = GroupMessage.__init__

    def group_message_init(
        message: GroupMessage,
        api,
        event_id,
        data: dict[str, Any],
    ) -> None:
        """解析群消息后把原始载荷中的昵称补回 author 对象。"""
        payload = data or {}
        original_init(message, api, event_id, payload)
        author_data = payload.get("author") or {}
        member_data = payload.get("member") or {}
        member_user_data = member_data.get("user") or {}
        nickname = (
            author_data.get("username")
            or author_data.get("nickname")
            or author_data.get("nick")
            or member_data.get("nick")
            or member_user_data.get("username")
        )
        if nickname:
            message.author.username = str(nickname)

    GroupMessage.__init__ = group_message_init
    GroupMessage._mlc_nickname_compat_installed = True
