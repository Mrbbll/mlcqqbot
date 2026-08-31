"""QQ 内联键盘消息的构造和按钮命令解析。"""
from typing import Any


# 只将公开查询命令放进帮助键盘，管理员控制命令仍需手动输入并校验权限。
HELP_BUTTONS = (
    ("help_list", "服务器状态", "/list"),
    ("help_players", "在线玩家", "/视奸"),
    ("help_ip", "服务器延迟", "/ip"),
    ("help_status", "宿主机状态", "/status"),
    ("help_map", "服务器地图", "/服务器地图"),
)

LOTTERY_BUTTON_ID = "lottery_draw"
LOTTERY_ACTION = "lottery:draw"

_COMMAND_BY_BUTTON_ID = {button_id: command for button_id, _, command in HELP_BUTTONS}
_PUBLIC_COMMANDS = frozenset(command for _, _, command in HELP_BUTTONS)


def help_keyboard_payload(user_openid: str) -> dict[str, Any]:
    """构造仅允许指定用户点击的 QQ 内联键盘。"""
    if not user_openid:
        raise ValueError("生成帮助键盘时缺少用户 OpenID")

    buttons = [
        {
            "id": button_id,
            "render_data": {
                "label": label,
                "visited_label": label,
                "style": 1,
            },
            "action": {
                # type=2 表示指令按钮，点击后自动发送 data 中的命令。
                "type": 2,
                "permission": {
                    "type": 2,
                },
                "data": command,
                "enter": True,
            },
        }
        for button_id, label, command in HELP_BUTTONS
    ]

    # 群消息接口要求自定义键盘放在 keyboard.content.rows 下。
    return {
        "content": {
            "rows": [
                {"buttons": buttons[:2]},
                {"buttons": buttons[2:4]},
                {"buttons": buttons[4:]},
            ]
        }
    }


def lottery_keyboard_payload() -> dict[str, Any]:
    """构造允许所有群成员参与的抽奖回调按钮。"""
    return {
        "content": {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": LOTTERY_BUTTON_ID,
                            "render_data": {
                                "label": "🎲 点击抽奖",
                                "visited_label": "🎲 已开奖",
                                "style": 1,
                            },
                            "action": {
                                # type=1 直接触发互动事件，不向群里发送命令文本。
                                "type": 1,
                                "permission": {
                                    # type=2 表示所有群成员都可以点击。
                                    "type": 2,
                                },
                                "data": LOTTERY_ACTION,
                            },
                        }
                    ]
                }
            ]
        }
    }


def command_from_interaction(interaction: Any) -> str | None:
    """从 QQ 按钮事件中提取允许执行的命令或内部动作。"""
    data = getattr(interaction, "data", None)
    resolved = getattr(data, "resolved", None)
    button_id = getattr(resolved, "button_id", None)
    if button_id == LOTTERY_BUTTON_ID:
        return LOTTERY_ACTION

    command = _COMMAND_BY_BUTTON_ID.get(button_id)
    if command:
        return command

    # 兼容部分 SDK/平台版本仅回传 button_data 的情况，并限制为公开命令。
    button_data = getattr(resolved, "button_data", None)
    if button_data == LOTTERY_ACTION:
        return LOTTERY_ACTION

    if button_data in _PUBLIC_COMMANDS:
        return button_data
    return None
