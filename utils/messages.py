"""机器人回复文案及 Markdown 格式化函数。

所有用户可见的回复文字集中在这里维护。业务处理器只负责收集数据和执行操作，
再调用本模块生成最终回复，避免文案散落在各个 handler 中。
"""
from collections.abc import Sequence
from typing import TYPE_CHECKING

from utils.markdown import escape_markdown, inline_code, mention_user

if TYPE_CHECKING:
    from utils.poll_store import PollResult


# ==================== 通用回复 ====================

PROCESSING_ERROR = "⚠️ **处理请求时发生错误**\n\n请稍后再试"


# ==================== 帮助与服务器查询 ====================

HELP = """**📋 指令帮助**

- `/list` — 查询全部服务器状态
- `/视奸` — 查看各服在线玩家
- `/ip` — 服务器延迟一览
- `/status` — 宿主机运行状态
- `/服务器地图` — 地图和文档链接
- `/自助口球` — 随机禁言自己 1–60 分钟（仅群聊）

**实例管理**

- `/执行 <实例名> <命令>`
- `/开启 <实例名>`
- `/停止 <实例名>`
- `/终止 <实例名>`

**管理员互动**

- `/抽奖` — 发起随机禁言抽奖
- `/投票` — 从腾讯表格发起整合包投票
- `/投票结果` — 查看本群当前投票结果"""

SERVER_MAP = """**服务器地图**

- **生存服网页地图**：`43.248.188.28:19423`
- **服务器文档**：[打开服务器文档](https://docs.qq.com/aio/DRnp3YU9sRmxWYnVB)"""

PLAYER_UNKNOWN = "匿名/无人"
PLAYER_EMPTY = "无人"
SERVER_TIMEOUT = "超时"


def server_unknown(server_name: str) -> str:
    """未知服务器回复。"""
    return f"**{escape_markdown(server_name)}**\n\n- **状态**：❌ 未知服务器"


def server_unreachable(server_name: str) -> str:
    """服务器无法连接回复。"""
    return f"**{escape_markdown(server_name)}**\n\n- **状态**：⚠️ 无法连接"


def server_full(
    server_name: str,
    online_players: int,
    node_addr: str,
    latency: str,
    players: str,
) -> str:
    """完整服务器状态回复。"""
    return (
        f"**{escape_markdown(server_name)}**\n\n"
        f"- **在线人数**：{online_players} 人\n"
        f"- **节点延迟**（{inline_code(node_addr)}）：{inline_code(latency)}\n"
        f"- **玩家**：{inline_code(players)}"
    )


def server_players(server_name: str, online_players: int, players: str) -> str:
    """服务器在线玩家回复。"""
    return (
        f"**{escape_markdown(server_name)}**\n\n"
        f"- **在线人数**：{online_players} 人\n"
        f"- **玩家**：{inline_code(players)}"
    )


def server_ping(server_name: str, node_addr: str, latency: str) -> str:
    """服务器节点延迟回复。"""
    return (
        f"**{escape_markdown(server_name)}**\n\n"
        f"- **节点延迟**（{inline_code(node_addr)}）：{inline_code(latency)}"
    )


def _server_sections(title: str, sections: Sequence[str]) -> str:
    return "\n\n".join((f"**{title}**", *sections))


def server_status_list(sections: Sequence[str]) -> str:
    """全部服务器状态回复。"""
    return _server_sections("📊 服务器状态", sections)


def server_player_list(sections: Sequence[str]) -> str:
    """全部服务器玩家回复。"""
    return _server_sections("👀 在线群友", sections)


def server_ping_list(sections: Sequence[str]) -> str:
    """全部服务器延迟回复。"""
    return _server_sections("📡 服务器延迟", sections)


# ==================== 宿主机状态 ====================

def host_status(
    *,
    logical_cores: int | None,
    cpu_frequency: tuple[float, float, float] | None,
    cpu_percent: float,
    disk_used_gb: float,
    disk_free_gb: float,
    disk_percent: float,
    memory_used_gb: float,
    memory_total_gb: float,
    memory_percent: float,
    boot_time: str,
    uptime_seconds: int,
) -> str:
    """宿主机状态回复。"""
    uptime = (
        f"{uptime_seconds // 3600}小时"
        f"{(uptime_seconds % 3600) // 60}分钟"
    )
    lines = [
        "**宿主机运行状态**",
        "",
        f"- **CPU 核心**：逻辑 {logical_cores} 核",
    ]
    if cpu_frequency is None:
        lines.append("- **CPU 频率**：无法获取")
    else:
        current, minimum, maximum = cpu_frequency
        lines.append(
            f"- **CPU 频率**：当前 {current} MHz，"
            f"最小 {minimum} MHz，最大 {maximum} MHz"
        )
    lines.extend(
        (
            f"- **CPU 占用**：{cpu_percent}%",
            f"- **磁盘**：已用 {disk_used_gb}GB（{disk_percent}%），"
            f"可用 {disk_free_gb}GB",
            f"- **内存**：{memory_used_gb}GB / {memory_total_gb}GB"
            f"（{memory_percent}%）",
            f"- **启动于**：{inline_code(boot_time)}",
            f"- **运行时长**：{inline_code(uptime)}",
        )
    )
    return "\n".join(lines)


# ==================== MCSM 管理 ====================

MCSM_PERMISSION_DENIED = "⛔ **权限不足**\n\n仅管理员可执行此操作"
MCSM_COMMAND_REQUIRED = "⚠️ **格式错误**\n\n请提供命令内容"
_MCSM_AVAILABLE_INSTANCES = "`scf` / `mod` / `mod1` / `minigames` / `bot`"
MCSM_EXECUTE_USAGE = (
    "⚠️ **格式错误**\n\n"
    "- **用法**：`/执行 <实例名字> <命令内容>`\n"
    f"- **可用实例**：{_MCSM_AVAILABLE_INSTANCES}"
)
MCSM_OPEN_USAGE = (
    "⚠️ **格式错误**\n\n"
    "- **用法**：`/开启 <实例名字>`\n"
    f"- **可用实例**：{_MCSM_AVAILABLE_INSTANCES}"
)
MCSM_STOP_USAGE = (
    "⚠️ **格式错误**\n\n"
    "- **用法**：`/停止 <实例名字>`\n"
    f"- **可用实例**：{_MCSM_AVAILABLE_INSTANCES}"
)
MCSM_KILL_USAGE = (
    "⚠️ **格式错误**\n\n"
    "- **用法**：`/终止 <实例名字>`\n"
    f"- **可用实例**：{_MCSM_AVAILABLE_INSTANCES}"
)
_MCSM_OPERATION_TITLES = {
    "open": "▶️ 实例开启结果",
    "stop": "⏹️ 实例停止结果",
    "kill": "⏏️ 实例终止结果",
}
_MCSM_REASONS = {
    200: "✅ 命令请求成功 [200]",
    400: "❌ 参数错误（UUID/守护进程ID无效）",
    403: "❌ 无权限（API密钥错误或未授权）",
    404: "❌ 接口不存在（面板地址或API路径错误）",
    500: "❌ 面板服务器内部异常",
}


def mcsm_reason(status_code: int) -> str:
    """MCSM API 状态码对应的用户可见结果。"""
    return _MCSM_REASONS.get(status_code, f"❌ 未知错误 [{status_code}]")


def mcsm_usage(command: str, usage: str) -> str:
    """管理命令用法提示。"""
    return (
        "⚠️ **格式错误**\n\n"
        f"- **用法**：`{command} {usage}`\n"
        f"- **可用实例**：{_MCSM_AVAILABLE_INSTANCES}"
    )


def mcsm_invalid_instance(instance_name: str) -> str:
    """无效实例名回复。"""
    return (
        f"❌ **无效实例名**：{inline_code(instance_name)}\n\n"
        f"- **可用实例**：{_MCSM_AVAILABLE_INSTANCES}"
    )


def mcsm_execute_result(instance_name: str, command: str, reason: str) -> str:
    """MCSM 命令执行结果回复。"""
    return (
        "**📤 命令执行结果**\n\n"
        f"- **实例**：{inline_code(instance_name)}\n"
        f"- **命令**：{inline_code(command)}\n"
        f"- **结果**：{escape_markdown(reason)}"
    )


def mcsm_operation_result(operation: str, instance_name: str, reason: str) -> str:
    """MCSM 实例开启、停止或终止结果回复。"""
    try:
        title = _MCSM_OPERATION_TITLES[operation]
    except KeyError as exc:
        raise ValueError(f"未知 MCSM 操作: {operation}") from exc
    return mcsm_custom_operation_result(title, instance_name, reason)


def mcsm_custom_operation_result(title: str, instance_name: str, reason: str) -> str:
    """使用指定标题生成 MCSM 操作结果回复。"""
    return (
        f"**{title}**\n\n"
        f"- **实例**：{inline_code(instance_name)}\n"
        f"- **结果**：{escape_markdown(reason)}"
    )


# ==================== 抽奖 ====================

LOTTERY_PERMISSION_DENIED = "⛔ **权限不足**\n\n仅管理员可发起抽奖"
LOTTERY_GROUP_ONLY = "⚠️ **抽奖只能在群聊中发起**"
LOTTERY_BUTTON_GROUP_ONLY = "⚠️ **抽奖按钮只能在群聊中使用**"
LOTTERY_MUTE_FAILED = (
    "❌ **抽奖禁言失败**\n\n"
    "请确认机器人拥有群管理员权限，且点击者是普通群成员"
)


def lottery_prompt(min_minutes: int, max_minutes: int) -> str:
    """发起抽奖时的参与提示。"""
    return (
        "**🎲 群聊抽奖**\n\n"
        f"点击下方按钮参与抽奖，将随机获得 **{min_minutes}–{max_minutes} 分钟**禁言。\n\n"
        f"> 抽中 {min_minutes} 分钟时不会执行禁言"
    )


def lottery_result(minutes: int, member_openid: str = "") -> str:
    """抽奖结果回复，并用 QQ 提及显示中奖者群昵称。"""
    member = mention_user(member_openid) if member_openid else "点击按钮的群友"
    if minutes == 0:
        return (
            "**🎉 抽奖结果**\n\n"
            f"恭喜 {member} 抽中 **0 分钟**，本次免于禁言！"
        )
    return (
        "**🎲 抽奖结果**\n\n"
        f"{member} 抽中 **{minutes} 分钟**禁言，奖励已发放。"
    )


# ==================== 群聊投票 ====================

POLL_PERMISSION_DENIED = "⛔ **权限不足**\n\n仅管理员可发起或查看投票结果"
POLL_GROUP_ONLY = "⚠️ **投票只能在群聊中发起或参与**"
POLL_RESULTS_GROUP_ONLY = "⚠️ **投票结果只能在群聊中查看**"
POLL_NOT_ACTIVE = "ℹ️ **当前没有进行中的投票**"
POLL_SHEET_FAILED = (
    "❌ **候选项读取失败**\n\n"
    "请确认腾讯表格仍允许通过分享链接查看，并稍后重试"
)
POLL_VOTE_UNAVAILABLE = (
    "⚠️ **无法记录选票**\n\n"
    "这轮投票可能已经被新投票替代，请点击最新的投票消息"
)
POLL_SUBMIT_UNAVAILABLE = (
    "⚠️ **无法提交投票**\n\n"
    "没有待提交的选择，或这轮投票已经结束。"
)
POLL_CATEGORY_PROMPT = (
    "**📊 发起群聊投票**\n\n"
    "请选择候选项来源：**科技**、**冒险**或**混合**。\n\n"
    "> 选择后会实时读取腾讯在线表格；新投票会结束本群上一轮投票"
)
_POLL_CATEGORY_LABELS = {
    "technology": "科技",
    "adventure": "冒险",
    "mixed": "混合",
}


def poll_candidate_limit(actual: int, maximum: int) -> str:
    """候选项超过单条 QQ 键盘容量时的提示。"""
    return (
        "⚠️ **候选项过多，无法发起投票**\n\n"
        f"当前读取到 **{actual} 项**，一条消息最多支持 **{maximum} 项**。\n\n"
        "> 请先整理腾讯表格"
    )


def poll_started(category: str, candidates: Sequence[str]) -> str:
    """生成编号候选项列表，按钮使用相同编号避免长名称截断。"""
    label = _POLL_CATEGORY_LABELS.get(category, category)
    lines = [
        "**📊 群聊投票**",
        "",
        f"- **类型**：{escape_markdown(label)}",
        f"- **候选项**：{len(candidates)} 个",
        "- **规则**：点击候选项进行选择，再点击最后的提交按钮，最后提交的投票会覆盖之前投票",
        "",
    ]
    lines.extend(
        f"{index}. {escape_markdown(name)}"
        for index, name in enumerate(candidates, start=1)
    )
    lines.extend(("", "> 点击下方对应编号完成投票"))
    return "\n".join(lines)


def poll_submitted(member_openid: str, candidate_names: Sequence[str]) -> str:
    """生成投票提交成功提示。"""
    member = mention_user(member_openid)
    if not candidate_names:
        return f"**✅ 投票已更新**\n\n{member} 已清空本轮选择。"
    lines = "\n".join(f"- {escape_markdown(name)}" for name in candidate_names)
    return f"**✅ 投票已提交**\n\n{member} 提交了：\n{lines}"


def poll_results(result: "PollResult") -> str:
    """生成当前投票的计票汇总。"""
    label = _POLL_CATEGORY_LABELS.get(result.category, result.category)
    lines = [
        "**📈 投票结果**",
        "",
        f"- **类型**：{escape_markdown(label)}",
        f"- **总选择数**：{result.total_votes}",
        "",
    ]
    for candidate_id, name, count in result.candidates:
        percentage = (
            count / result.total_votes * 100 if result.total_votes else 0.0
        )
        lines.append(
            f"{candidate_id}. {escape_markdown(name)} — "
            f"**{count} 票**"
        )
    return "\n".join(lines)


# ==================== 自助口球 ====================

SELF_MUZZLE_GROUP_ONLY = "⚠️ **自助口球只能在群聊中使用**"
SELF_MUZZLE_CONTEXT_MISSING = "❌ **自助口球执行失败**\n\n缺少群聊或成员信息"
SELF_MUZZLE_FAILED = (
    "❌ **自助口球执行失败**\n\n"
    "请确认机器人拥有群管理员权限，且你是普通群成员"
)


def self_muzzle_success(minutes: int) -> str:
    """自助口球成功回复。"""
    return f"**🤐 自助口球**\n\n已为你随机禁言 **{minutes} 分钟**。"
