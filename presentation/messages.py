"""集中生成所有固定的用户可见回复；消息正文统一来自 Markdown 模板。"""
from collections.abc import Sequence
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from presentation.markdown import escape_markdown, inline_code, mention_user
from presentation.template_loader import load_template, render_template

if TYPE_CHECKING:
    from external_tools.storage.poll_repository import PollResult


# ==================== 通用回复 ====================

PROCESSING_ERROR = load_template("messages/common/processing_error.md")
_NOT_CONFIGURED = load_template("messages/common/not_configured.md")


# ==================== Agent 回复 ====================

AGENT_NOT_CONFIGURED = load_template("messages/agent/not_configured.md")
AGENT_API_ERROR = load_template("messages/agent/api_error.md")
AGENT_EMPTY_REPLY = load_template("messages/agent/empty_reply.md")
AGENT_TOOL_LIMIT = load_template("messages/agent/tool_limit.md")


def agent_reply(content: str) -> str:
    """将动态 Agent 回复通过统一 Markdown 回复模板输出。"""
    return render_template("messages/agent/reply.md", {"reply": content})


# ==================== 帮助与服务器查询 ====================

HELP = load_template("help.md")
SERVER_MAP = load_template("server_map.md")


def _format_invite_link(platform: str, url: str) -> str:
    """将有效的 HTTP(S) 邀请地址渲染为链接，否则将配置值作为文本显示。"""
    value = url.strip()
    try:
        parsed_url = urlsplit(value)
        is_http_url = (
            parsed_url.scheme.lower() in {"http", "https"}
            and bool(parsed_url.netloc)
        )
    except ValueError:
        is_http_url = False

    if is_http_url:
        safe_url = quote(value, safe=":/?#[]@!$&'*+,;=%-._~")
        return render_template(
            "messages/invites/link.md",
            {
                "platform": escape_markdown(platform),
                "url": safe_url,
            },
        )
    return render_template(
        "messages/invites/value.md",
        {
            "platform": escape_markdown(platform),
            "value": inline_code(value or _NOT_CONFIGURED),
        },
    )


def community_invite_links(oopz_url: str, kook_url: str) -> str:
    """生成 OOPZ 和 KOOK 社群邀请链接回复。"""
    return render_template(
        "messages/invites/community.md",
        {
            "oopz_link": _format_invite_link("OOPZ", oopz_url),
            "kook_link": _format_invite_link("KOOK", kook_url),
        },
    )


def server_unknown(server_name: str) -> str:
    """渲染未知服务器回复。"""
    return render_template(
        "messages/server/unknown.md",
        {"server_name": escape_markdown(server_name)},
    )


def server_unreachable(server_name: str, domain: str | None = None) -> str:
    """渲染无法连接服务器的回复。"""
    if domain is not None:
        return render_template(
            "messages/server/unreachable_domain.md",
            {
                "server_name": escape_markdown(server_name),
                "domain": inline_code(domain or _NOT_CONFIGURED),
            },
        )
    return render_template(
        "messages/server/unreachable.md",
        {"server_name": escape_markdown(server_name)},
    )


def server_full(
    server_name: str,
    domain: str,
    online_players: int,
    players: str,
) -> str:
    """渲染包含域名、在线人数和玩家名称的服务器回复。"""
    return render_template(
        "messages/server/full.md",
        {
            "server_name": escape_markdown(server_name),
            "domain": inline_code(domain or _NOT_CONFIGURED),
            "online_players": online_players,
            "players": inline_code(players),
        },
    )


def server_players(server_name: str, online_players: int, players: str) -> str:
    """渲染服务器在线玩家回复。"""
    return render_template(
        "messages/server/players.md",
        {
            "server_name": escape_markdown(server_name),
            "online_players": online_players,
            "players": inline_code(players),
        },
    )


def server_domain(server_name: str, domain: str) -> str:
    """渲染只包含服务器连接域名的回复。"""
    return render_template(
        "messages/server/domain.md",
        {
            "server_name": escape_markdown(server_name),
            "domain": inline_code(domain or _NOT_CONFIGURED),
        },
    )


def _render_server_sections(template_name: str, sections: Sequence[str]) -> str:
    """将服务器分区内容填入对应的状态列表模板。"""
    section_text = "\n\n".join(sections)
    if section_text:
        section_text = f"\n\n{section_text}"
    return render_template(template_name, {"sections": section_text})


def server_status_list(sections: Sequence[str]) -> str:
    """渲染全部服务器状态回复。"""
    return _render_server_sections("messages/server/status_list.md", sections)


def server_player_list(sections: Sequence[str]) -> str:
    """渲染全部服务器玩家回复。"""
    if not sections:
        return load_template("messages/server/players_empty.md")
    return _render_server_sections("messages/server/players_list.md", sections)


def server_domain_list(sections: Sequence[str]) -> str:
    """渲染全部服务器连接域名回复。"""
    return _render_server_sections("messages/server/domain_list.md", sections)


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
    """渲染宿主机状态回复。"""
    if cpu_frequency is None:
        frequency_text = load_template(
            "messages/host/cpu_frequency_unavailable.md"
        )
    else:
        current, minimum, maximum = cpu_frequency
        frequency_text = render_template(
            "messages/host/cpu_frequency.md",
            {
                "current": current,
                "minimum": minimum,
                "maximum": maximum,
            },
        )
    uptime = render_template(
        "messages/host/uptime.md",
        {
            "hours": uptime_seconds // 3600,
            "minutes": (uptime_seconds % 3600) // 60,
        },
    )
    return render_template(
        "messages/host/status.md",
        {
            "logical_cores": logical_cores,
            "cpu_frequency": frequency_text,
            "cpu_percent": cpu_percent,
            "disk_used_gb": disk_used_gb,
            "disk_percent": disk_percent,
            "disk_free_gb": disk_free_gb,
            "memory_used_gb": memory_used_gb,
            "memory_total_gb": memory_total_gb,
            "memory_percent": memory_percent,
            "boot_time": inline_code(boot_time),
            "uptime": inline_code(uptime),
        },
    )


# ==================== MCSM 管理 ====================

MCSM_PERMISSION_DENIED = load_template("messages/mcsm/permission_denied.md")
MCSM_COMMAND_REQUIRED = load_template("messages/mcsm/command_required.md")
MCSM_EXECUTE_USAGE = load_template("messages/mcsm/execute_usage.md")
MCSM_OPEN_USAGE = load_template("messages/mcsm/open_usage.md")
MCSM_STOP_USAGE = load_template("messages/mcsm/stop_usage.md")
MCSM_KILL_USAGE = load_template("messages/mcsm/kill_usage.md")
_MCSM_REASON_TEMPLATES = {
    200: "messages/mcsm/reason_200.md",
    400: "messages/mcsm/reason_400.md",
    403: "messages/mcsm/reason_403.md",
    404: "messages/mcsm/reason_404.md",
    500: "messages/mcsm/reason_500.md",
}
_MCSM_OPERATION_TITLE_TEMPLATES = {
    "open": "messages/mcsm/operation_title_open.md",
    "stop": "messages/mcsm/operation_title_stop.md",
    "kill": "messages/mcsm/operation_title_kill.md",
}


def mcsm_reason(status_code: int) -> str:
    """从对应模板读取 MCSM API 状态码说明。"""
    template_name = _MCSM_REASON_TEMPLATES.get(status_code)
    if template_name is not None:
        return load_template(template_name)
    return render_template(
        "messages/mcsm/reason_unknown.md",
        {"status_code": status_code},
    )


def mcsm_usage(command: str, usage: str) -> str:
    """使用通用模板渲染 MCSM 命令用法提示。"""
    return render_template(
        "messages/mcsm/usage.md",
        {
            "usage": inline_code(f"{command} {usage}"),
        },
    )


def mcsm_invalid_instance(instance_name: str) -> str:
    """渲染无效实例名回复。"""
    return render_template(
        "messages/mcsm/invalid_instance.md",
        {"instance_name": inline_code(instance_name)},
    )


def mcsm_execute_result(instance_name: str, command: str, reason: str) -> str:
    """渲染 MCSM 命令执行结果回复。"""
    return render_template(
        "messages/mcsm/execute_result.md",
        {
            "instance_name": inline_code(instance_name),
            "command": inline_code(command),
            "reason": escape_markdown(reason),
        },
    )


def mcsm_operation_result(operation: str, instance_name: str, reason: str) -> str:
    """渲染 MCSM 实例开启、停止或终止结果回复。"""
    try:
        title_template = _MCSM_OPERATION_TITLE_TEMPLATES[operation]
    except KeyError as exc:
        raise ValueError(f"未知 MCSM 操作: {operation}") from exc
    title = load_template(title_template)
    return mcsm_custom_operation_result(title, instance_name, reason)


def mcsm_custom_operation_result(title: str, instance_name: str, reason: str) -> str:
    """使用指定标题模板生成 MCSM 操作结果回复。"""
    return render_template(
        "messages/mcsm/operation_result.md",
        {
            "title": escape_markdown(title),
            "instance_name": inline_code(instance_name),
            "reason": escape_markdown(reason),
        },
    )


# ==================== 抽奖 ====================

LOTTERY_PERMISSION_DENIED = load_template("messages/lottery/permission_denied.md")
LOTTERY_GROUP_ONLY = load_template("messages/lottery/group_only.md")
LOTTERY_BUTTON_GROUP_ONLY = load_template(
    "messages/lottery/button_group_only.md"
)
LOTTERY_MUTE_FAILED = load_template("messages/lottery/mute_failed.md")


def lottery_prompt(min_minutes: int, max_minutes: int) -> str:
    """从模板生成抽奖参与提示。"""
    return render_template(
        "lottery_prompt.md",
        {
            "min_minutes": min_minutes,
            "max_minutes": max_minutes,
        },
    )


def lottery_result(minutes: int, member_openid: str = "") -> str:
    """从模板生成抽奖结果，并使用 QQ 提及显示中奖者群昵称。"""
    member = mention_user(member_openid) if member_openid else load_template(
        "messages/lottery/default_member.md"
    )
    if minutes == 0:
        return render_template(
            "messages/lottery/result_zero.md",
            {"member": member},
        )
    return render_template(
        "messages/lottery/result.md",
        {
            "member": member,
            "minutes": minutes,
        },
    )


# ==================== 钓鱼小游戏 ====================

FISHING_STARTED = load_template("messages/fishing/started.md")
FISHING_GROUP_ONLY = load_template("messages/fishing/group_only.md")
FISHING_CONTEXT_MISSING = load_template("messages/fishing/context_missing.md")
FISHING_ALREADY_ACTIVE = load_template("messages/fishing/already_active.md")
FISHING_NOT_OWNER = load_template("messages/fishing/not_owner.md")
FISHING_EXPIRED = load_template("messages/fishing/expired.md")


def fishing_bite(member_openid: str) -> str:
    """从模板生成鱼上钩时提醒指定群成员的文案。"""
    return render_template(
        "messages/fishing/bite.md",
        {"member": mention_user(member_openid)},
    )


def fishing_result(member_openid: str, species: str, size_cm: float) -> str:
    """从模板生成包含鱼种与大小的成功拉钩结果。"""
    return render_template(
        "messages/fishing/result.md",
        {
            "member": mention_user(member_openid),
            "species": escape_markdown(species),
            "size_cm": f"{size_cm:.1f}",
        },
    )


# ==================== 群聊投票 ====================

POLL_PERMISSION_DENIED = load_template("messages/poll/permission_denied.md")
POLL_GROUP_ONLY = load_template("messages/poll/group_only.md")
POLL_RESULTS_GROUP_ONLY = load_template("messages/poll/results_group_only.md")
POLL_NOT_ACTIVE = load_template("messages/poll/not_active.md")
POLL_SHEET_FAILED = load_template("messages/poll/sheet_failed.md")
POLL_VOTE_UNAVAILABLE = load_template("messages/poll/vote_unavailable.md")
POLL_SUBMIT_UNAVAILABLE = load_template("messages/poll/submit_unavailable.md")
POLL_CATEGORY_PROMPT = load_template("messages/poll/category_prompt.md")
_POLL_CATEGORY_TEMPLATES = {
    "technology": "messages/poll/category_technology.md",
    "adventure": "messages/poll/category_adventure.md",
    "mixed": "messages/poll/category_mixed.md",
}


def _poll_category_label(category: str) -> str:
    """从模板读取投票类型显示名称。"""
    template_name = _POLL_CATEGORY_TEMPLATES.get(category)
    return load_template(template_name) if template_name else category


def poll_candidate_limit(actual: int, maximum: int) -> str:
    """从模板渲染候选项超过单条 QQ 键盘容量时的提示。"""
    return render_template(
        "messages/poll/candidate_limit.md",
        {
            "actual": actual,
            "maximum": maximum,
        },
    )


def poll_started(category: str, candidates: Sequence[str]) -> str:
    """渲染编号候选项列表，按钮使用相同编号避免长名称截断。"""
    candidate_lines = [
        render_template(
            "messages/poll/candidate_line.md",
            {
                "candidate_id": index,
                "candidate_name": escape_markdown(name),
            },
        )
        for index, name in enumerate(candidates, start=1)
    ]
    return render_template(
        "messages/poll/started.md",
        {
            "category": escape_markdown(_poll_category_label(category)),
            "candidate_count": len(candidates),
            "candidates": "\n".join(candidate_lines),
        },
    )


def poll_submitted(member_openid: str, candidate_names: Sequence[str]) -> str:
    """从模板生成投票提交成功提示。"""
    member = mention_user(member_openid)
    if not candidate_names:
        return render_template(
            "messages/poll/submitted_empty.md",
            {"member": member},
        )
    candidate_lines = [
        render_template(
            "messages/poll/submitted_candidate_line.md",
            {"candidate_name": escape_markdown(name)},
        )
        for name in candidate_names
    ]
    return render_template(
        "messages/poll/submitted.md",
        {
            "member": member,
            "candidates": "\n".join(candidate_lines),
        },
    )


def poll_results(result: "PollResult") -> str:
    """从模板生成当前投票的计票汇总。"""
    candidate_lines = [
        render_template(
            "messages/poll/result_candidate_line.md",
            {
                "candidate_id": candidate_id,
                "candidate_name": escape_markdown(name),
                "vote_count": count,
            },
        )
        for candidate_id, name, count in result.candidates
    ]
    return render_template(
        "messages/poll/results.md",
        {
            "category": escape_markdown(_poll_category_label(result.category)),
            "total_votes": result.total_votes,
            "candidates": "\n".join(candidate_lines),
        },
    )


# ==================== 自助口球 ====================

SELF_MUZZLE_GROUP_ONLY = load_template("messages/muzzle/group_only.md")
SELF_MUZZLE_CONTEXT_MISSING = load_template("messages/muzzle/context_missing.md")
SELF_MUZZLE_FAILED = load_template("messages/muzzle/failed.md")


def self_muzzle_success(minutes: int) -> str:
    """从模板渲染自助口球成功回复。"""
    return render_template(
        "messages/muzzle/success.md",
        {"minutes": minutes},
    )
