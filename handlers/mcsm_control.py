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
from utils import messages
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


# 兼容已有调用；文案与格式化实现统一维护在 utils.messages。
def get_reason(response) -> str:
    return messages.mcsm_reason(response.status_code)


def format_usage(command: str, usage: str) -> str:
    return messages.mcsm_usage(command, usage)


def format_invalid_instance(instance_name: str) -> str:
    return messages.mcsm_invalid_instance(instance_name)


def format_operation_result(title: str, instance_name: str, reason: str) -> str:
    return messages.mcsm_custom_operation_result(title, instance_name, reason)


# ==================== 命令处理入口 ====================

async def handle_execute(args: str, user_id: str) -> str:
    """处理 /执行 命令。"""
    if not check_superuser(user_id):
        return messages.MCSM_PERMISSION_DENIED

    if not args:
        return messages.MCSM_EXECUTE_USAGE

    parts = args.split(" ", 1)
    instance_name = parts[0]
    command_content = parts[1] if len(parts) > 1 else ""

    if not command_content:
        return messages.MCSM_COMMAND_REQUIRED

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return messages.mcsm_invalid_instance(instance_name)

    response = send_mcsm_command(instance_uuid, DEFAULT_DAEMON_ID, command_content)
    reason = messages.mcsm_reason(response.status_code)
    return messages.mcsm_execute_result(
        instance_name,
        command_content,
        reason,
    )


async def handle_open(args: str, user_id: str) -> str:
    """处理 /开启 命令。"""
    if not check_superuser(user_id):
        return messages.MCSM_PERMISSION_DENIED

    instance_name = args.strip()
    if not instance_name:
        return messages.MCSM_OPEN_USAGE

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return messages.mcsm_invalid_instance(instance_name)

    response = send_mcsm_open(instance_uuid, DEFAULT_DAEMON_ID)
    reason = messages.mcsm_reason(response.status_code)
    return messages.mcsm_operation_result("open", instance_name, reason)


async def handle_stop(args: str, user_id: str) -> str:
    """处理 /停止 命令。"""
    if not check_superuser(user_id):
        return messages.MCSM_PERMISSION_DENIED

    instance_name = args.strip()
    if not instance_name:
        return messages.MCSM_STOP_USAGE

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return messages.mcsm_invalid_instance(instance_name)

    response = send_mcsm_stop(instance_uuid, DEFAULT_DAEMON_ID)
    reason = messages.mcsm_reason(response.status_code)
    return messages.mcsm_operation_result("stop", instance_name, reason)


async def handle_kill(args: str, user_id: str) -> str:
    """处理 /终止 命令。"""
    if not check_superuser(user_id):
        return messages.MCSM_PERMISSION_DENIED

    instance_name = args.strip()
    if not instance_name:
        return messages.MCSM_KILL_USAGE

    instance_uuid = get_instance_id(instance_name)
    if instance_uuid == "null":
        return messages.mcsm_invalid_instance(instance_name)

    response = send_mcsm_kill(instance_uuid, DEFAULT_DAEMON_ID)
    reason = messages.mcsm_reason(response.status_code)
    return messages.mcsm_operation_result("kill", instance_name, reason)
