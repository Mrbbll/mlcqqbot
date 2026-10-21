"""
MCSM 面板控制处理器
处理 /执行 /开启 /停止 /终止 命令
移植自 NoneBot 项目 mybot/plugins/mlc/command.py
"""
from typing import Callable

from config import (
    DEFAULT_DAEMON_ID,
    get_instance_id,
)
from external_tools.mcsm.client import (
    send_mcsm_command,
    send_mcsm_kill,
    send_mcsm_open,
    send_mcsm_stop,
)
from presentation import messages
from features.security.permissions import check_superuser


def _has_permission(
    user_id: str,
    permission_check: Callable[[str], bool] | None,
) -> bool:
    """调用当前 MCSM 操作的权限检查函数。"""
    return (permission_check or check_superuser)(user_id)


# ==================== 命令处理入口 ====================

async def handle_execute(
    args: str,
    user_id: str,
    *,
    has_permission: Callable[[str], bool] | None = None,
) -> str:
    """处理 /执行 命令。"""
    if not _has_permission(user_id, has_permission):
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


async def handle_open(
    args: str,
    user_id: str,
    *,
    has_permission: Callable[[str], bool] | None = None,
) -> str:
    """处理 /开启 命令。"""
    if not _has_permission(user_id, has_permission):
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


async def handle_stop(
    args: str,
    user_id: str,
    *,
    has_permission: Callable[[str], bool] | None = None,
) -> str:
    """处理 /停止 命令。"""
    if not _has_permission(user_id, has_permission):
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


async def handle_kill(
    args: str,
    user_id: str,
    *,
    has_permission: Callable[[str], bool] | None = None,
) -> str:
    """处理 /终止 命令。"""
    if not _has_permission(user_id, has_permission):
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
