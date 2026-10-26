"""为当前 botpy 版本补充群聊全量消息事件解析。"""
from collections import OrderedDict
from typing import Any

from botpy.connection import ConnectionState
from botpy.message import GroupMessage


_RAW_GROUP_MESSAGE_DATA_LIMIT = 4096
_raw_group_message_data: OrderedDict[int, dict[str, Any]] = OrderedDict()


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
        _raw_group_message_data[id(message)] = payload
        _raw_group_message_data.move_to_end(id(message))
        while len(_raw_group_message_data) > _RAW_GROUP_MESSAGE_DATA_LIMIT:
            _raw_group_message_data.popitem(last=False)
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


def get_group_message_raw_data(message: GroupMessage) -> dict[str, Any]:
    """取出构造群消息时保留的原始载荷，用于读取 SDK 未建模的转发字段。"""
    return _raw_group_message_data.pop(id(message), {})


def get_group_message_indices(raw_message_data: dict[str, Any] | None) -> tuple[str, str]:
    """从 QQ 原始载荷提取当前消息索引和引用目标索引，不保留其他扩展字段。"""
    if not isinstance(raw_message_data, dict):
        return "", ""

    message_scene = (
        raw_message_data.get("message_scene")
        or raw_message_data.get("messageScene")
        or {}
    )
    extensions = message_scene.get("ext", []) if isinstance(message_scene, dict) else []
    message_index = str(
        raw_message_data.get("msg_idx") or raw_message_data.get("msgIdx") or ""
    ).strip()
    reference_index = str(
        raw_message_data.get("ref_msg_idx") or raw_message_data.get("refMsgIdx") or ""
    ).strip()
    if not isinstance(extensions, (list, tuple)):
        return message_index, reference_index

    for extension in extensions:
        if not isinstance(extension, str):
            continue
        key, separator, value = extension.partition("=")
        if not separator:
            continue
        if key.strip() == "msg_idx" and not message_index:
            message_index = value.strip()
        elif key.strip() == "ref_msg_idx" and not reference_index:
            reference_index = value.strip()
    return message_index, reference_index
