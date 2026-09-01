"""QQ 内联键盘消息的构造和按钮命令解析。"""
import re
from collections.abc import Sequence
from typing import Any


# 只将公开查询命令放进帮助键盘，管理员控制命令仍需手动输入并校验权限。
HELP_BUTTONS = (
    ("help_list", "服务器状态", "/list"),
    ("help_players", "在线玩家", "/视奸"),
    ("help_ip", "服务器延迟", "/ip"),
    ("help_status", "宿主机状态", "/status"),
    ("help_map", "服务器地图", "/服务器地图"),
    ("help_self_muzzle", "自助口球", "/自助口球"),
)

LOTTERY_BUTTON_ID = "lottery_draw"
LOTTERY_ACTION = "lottery:draw"
POLL_MAX_CANDIDATES = 20
POLL_BUTTONS_PER_ROW = 5
POLL_CATEGORY_ACTIONS = {
    "technology": "poll:category:technology",
    "adventure": "poll:category:adventure",
    "mixed": "poll:category:mixed",
}
_POLL_CATEGORY_BUTTONS = (
    ("poll_category_technology", "⚙️ 科技", POLL_CATEGORY_ACTIONS["technology"]),
    ("poll_category_adventure", "🗺️ 冒险", POLL_CATEGORY_ACTIONS["adventure"]),
    ("poll_category_mixed", "🧩 混合", POLL_CATEGORY_ACTIONS["mixed"]),
)
_POLL_VOTE_ACTION_PATTERN = re.compile(r"poll:vote:(\d+):(\d+)")
_POLL_VOTE_BUTTON_PATTERN = re.compile(r"poll_vote_(\d+)_(\d+)")
_POLL_SUBMIT_ACTION_PATTERN = re.compile(r"poll:submit:(\d+)")
_POLL_SUBMIT_BUTTON_PATTERN = re.compile(r"poll_submit_(\d+)")

_COMMAND_BY_BUTTON_ID = {button_id: command for button_id, _, command in HELP_BUTTONS}
_PUBLIC_COMMANDS = frozenset(command for _, _, command in HELP_BUTTONS)


def help_keyboard_payload() -> dict[str, Any]:
    """构造允许所有群成员点击的 QQ 帮助键盘。"""
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


def poll_category_keyboard_payload() -> dict[str, Any]:
    """构造管理员选择科技、冒险或混合类别的回调按钮。"""
    return {
        "content": {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": button_id,
                            "render_data": {
                                "label": label,
                                "visited_label": label,
                                "style": 1,
                            },
                            "action": {
                                "type": 1,
                                "permission": {"type": 2},
                                "data": action,
                            },
                        }
                        for button_id, label, action in _POLL_CATEGORY_BUTTONS
                    ]
                }
            ]
        }
    }


def poll_vote_keyboard_payload(
    poll_id: int,
    candidates: Sequence[str],
) -> dict[str, Any]:
    """以编号按钮构造一条最多包含 25 个候选项的投票键盘。"""
    if not candidates:
        raise ValueError("投票候选项不能为空")
    if len(candidates) > POLL_MAX_CANDIDATES:
        raise ValueError(f"投票候选项不能超过 {POLL_MAX_CANDIDATES} 个")

    buttons = []
    for candidate_id, _ in enumerate(candidates, start=1):
        action = f"poll:vote:{poll_id}:{candidate_id}"
        buttons.append(
            {
                "id": f"poll_vote_{poll_id}_{candidate_id}",
                "render_data": {
                    "label": str(candidate_id),
                    "visited_label": f"✓ {candidate_id}",
                    "style": 1,
                },
                "action": {
                    "type": 1,
                    "permission": {"type": 2},
                    "data": action,
                },
            }
        )
    rows = [
        {"buttons": buttons[index:index + POLL_BUTTONS_PER_ROW]}
        for index in range(0, len(buttons), POLL_BUTTONS_PER_ROW)
    ]
    submit_button = {
        "id": f"poll_submit_{poll_id}",
        "render_data": {
            "label": "✅ 提交投票",
            "visited_label": "✅ 已提交",
            "style": 1,
        },
        "action": {
            "type": 1,
            "permission": {"type": 2},
            "data": f"poll:submit:{poll_id}",
        },
    }
    rows.append({"buttons": [submit_button]})
    return {"content": {"style": {"font_size": "small"}, "rows": rows}}


def poll_category_from_action(action: str) -> str | None:
    """从已校验的类别动作中提取类别。"""
    for category, expected in POLL_CATEGORY_ACTIONS.items():
        if action == expected:
            return category
    return None


def poll_vote_from_action(action: str) -> tuple[int, int] | None:
    """从已校验的投票动作中提取投票 ID 和候选项 ID。"""
    match = _POLL_VOTE_ACTION_PATTERN.fullmatch(action)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def poll_submit_from_action(action: str) -> int | None:
    match = _POLL_SUBMIT_ACTION_PATTERN.fullmatch(action)
    return int(match.group(1)) if match else None


def _internal_poll_action(button_id: Any, button_data: Any) -> str | None:
    category_actions = {
        button: action for button, _, action in _POLL_CATEGORY_BUTTONS
    }
    action = category_actions.get(button_id)
    if action:
        return action

    if isinstance(button_id, str):
        match = _POLL_VOTE_BUTTON_PATTERN.fullmatch(button_id)
        if match:
            return f"poll:vote:{match.group(1)}:{match.group(2)}"
        match = _POLL_SUBMIT_BUTTON_PATTERN.fullmatch(button_id)
        if match:
            return f"poll:submit:{match.group(1)}"

    if isinstance(button_data, str):
        if poll_category_from_action(button_data) is not None:
            return button_data
        if poll_vote_from_action(button_data) is not None:
            return button_data
        if poll_submit_from_action(button_data) is not None:
            return button_data
    return None


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

    poll_action = _internal_poll_action(button_id, button_data)
    if poll_action:
        return poll_action

    if button_data in _PUBLIC_COMMANDS:
        return button_data
    return None
