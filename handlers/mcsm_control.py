"""
MCSM 面板控制处理器
处理 /执行 /开启 /停止 /终止 命令
移植自 NoneBot 项目 mybot/plugins/mlc/command.py
"""
import requests

from config import (
    MCSM_PANEL_URL,
    MCSM_API_SECRET,
    DEFAULT_DAEMON_ID,
    get_instance_id,
)
from utils.markdown import escape_markdown, inline_code
from utils.permissions import check_superuser


# ==================== MCSM API 调用函数 ====================

def send_mcsm_command(uuid: str, daemon_id: str, command: str):
    """向 MCSM 实例发送控制台命令。"""
    url = f"{MCSM_PANEL_URL}/api/protected_instance/command"
    params = {
        "apikey": MCSM_API_SECRET,
        "uuid": uuid,
        "daemonId": daemon_id,
        "command": command,
    }
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    return requests.get(url=url, params=params, headers=headers)


def send_mcsm_open(uuid: str, daemon_id: str):
    """开启 MCSM 实例。"""
    url = f"{MCSM_PANEL_URL}/api/protected_instance/open"
    params = {"apikey": MCSM_API_SECRET, "uuid": uuid, "daemonId": daemon_id}
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    return requests.get(url=url, params=params, headers=headers)


def send_mcsm_stop(uuid: str, daemon_id: str):
    """停止 MCSM 实例。"""
    url = f"{MCSM_PANEL_URL}/api/protected_instance/stop"
    params = {"apikey": MCSM_API_SECRET, "uuid": uuid, "daemonId": daemon_id}
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    return requests.get(url=url, params=params, headers=headers)


def send_mcsm_kill(uuid: str, daemon_id: str):
    """终止 MCSM 实例。"""
    url = f"{MCSM_PANEL_URL}/api/protected_instance/kill"
    params = {"apikey": MCSM_API_SECRET, "uuid": uuid, "daemonId": daemon_id}
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    return requests.get(url=url, params=params, headers=headers)


def get_reason(response) -> str:
    """解析 MCSM API 响应状态码。"""
    status_code = response.status_code
    if status_code == 200:
        return "✅ 命令请求成功 [200]"
    elif status_code == 400:
        return "❌ 参数错误（UUID/守护进程ID无效）"
    elif status_code == 403:
        return "❌ 无权限（API密钥错误或未授权）"
    elif status_code == 404:
        return "❌ 接口不存在（面板地址或API路径错误）"
    elif status_code == 500:
        return "❌ 面板服务器内部异常"
    else:
        return f"❌ 未知错误 [{status_code}]"


def format_usage(command: str, usage: str) -> str:
    """格式化管理命令的 Markdown 用法提示。"""
    return (
        "⚠️ **格式错误**\n\n"
        f"- **用法**：`{command} {usage}`\n"
        "- **可用实例**：`scf` / `mod` / `mod1` / `minigames` / `bot`"
    )


def format_invalid_instance(instance_name: str) -> str:
    """格式化无效实例提示。"""
    return (
        f"❌ **无效实例名**：{inline_code(instance_name)}\n\n"
        "- **可用实例**：`scf` / `mod` / `mod1` / `minigames` / `bot`"
    )


def format_operation_result(title: str, instance_name: str, reason: str) -> str:
    """格式化不带额外命令内容的 MCSM 操作结果。"""
    return (
        f"# {title}\n\n"
        f"- **实例**：{inline_code(instance_name)}\n"
        f"- **结果**：{escape_markdown(reason)}"
    )


# ==================== 命令处理入口 ====================

async def handle_execute(args: str, user_id: str) -> str:
    """处理 /执行 命令。"""
    if not check_superuser(user_id):
        return "⛔ **权限不足**\n\n仅管理员可执行此操作"

    if not args:
        return format_usage("/执行", "<实例名字> <命令内容>")

    parts = args.split(" ", 1)
    instance_name = parts[0]
    command_content = parts[1] if len(parts) > 1 else ""

    if not command_content:
        return "⚠️ **格式错误**\n\n请提供命令内容"

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return format_invalid_instance(instance_name)

    response = send_mcsm_command(instance_uuid, DEFAULT_DAEMON_ID, command_content)
    reason = get_reason(response)

    return (
        "### 📤 命令执行结果\n\n"
        f"- **实例**：{inline_code(instance_name)}\n"
        f"- **命令**：{inline_code(command_content)}\n"
        f"- **结果**：{escape_markdown(reason)}"
    )


async def handle_open(args: str, user_id: str) -> str:
    """处理 /开启 命令。"""
    if not check_superuser(user_id):
        return "⛔ **权限不足**\n\n仅管理员可执行此操作"

    instance_name = args.strip()
    if not instance_name:
        return format_usage("/开启", "<实例名字>")

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return format_invalid_instance(instance_name)

    response = send_mcsm_open(instance_uuid, DEFAULT_DAEMON_ID)
    reason = get_reason(response)
    return format_operation_result("▶️ 实例开启结果", instance_name, reason)


async def handle_stop(args: str, user_id: str) -> str:
    """处理 /停止 命令。"""
    if not check_superuser(user_id):
        return "⛔ **权限不足**\n\n仅管理员可执行此操作"

    instance_name = args.strip()
    if not instance_name:
        return format_usage("/停止", "<实例名字>")

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return format_invalid_instance(instance_name)

    response = send_mcsm_stop(instance_uuid, DEFAULT_DAEMON_ID)
    reason = get_reason(response)
    return format_operation_result("⏹️ 实例停止结果", instance_name, reason)


async def handle_kill(args: str, user_id: str) -> str:
    """处理 /终止 命令。"""
    if not check_superuser(user_id):
        return "⛔ **权限不足**\n\n仅管理员可执行此操作"

    instance_name = args.strip()
    if not instance_name:
        return format_usage("/终止", "<实例名字>")

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return format_invalid_instance(instance_name)

    response = send_mcsm_kill(instance_uuid, DEFAULT_DAEMON_ID)
    reason = get_reason(response)
    return format_operation_result("⏏️ 实例终止结果", instance_name, reason)
