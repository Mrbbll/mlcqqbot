"""文本命令识别与业务处理器路由。"""
from typing import Any

from handlers.fishing import handle_start_fishing
from handlers.host_status import handle_status
from handlers.lottery import handle_lottery
from handlers.mcsm_control import (
    handle_execute,
    handle_kill,
    handle_open,
    handle_stop,
)
from handlers.poll import (
    POLL_COMMAND,
    POLL_RESULTS_COMMAND,
    handle_poll,
    handle_poll_results,
)
from handlers.self_muzzle import SELF_MUZZLE_COMMAND, handle_self_muzzle
from handlers.server_query import (
    handle_help,
    handle_ip,
    handle_list,
    handle_map,
    handle_shijian,
)
from utils.command_text import has_command_prefix, normalize_command


COMMAND_PREFIXES = (
    "/list", "/视奸", "/ip", "/status", "/map", "/help",
    "/服务器地图", "/指令帮助",
    "/执行", "/开启", "/停止", "/终止", "/抽奖",
    "/开始钓鱼",
    POLL_RESULTS_COMMAND, POLL_COMMAND,
    SELF_MUZZLE_COMMAND,
)


def should_reply(content: str) -> bool:
    """检查消息是否以支持的命令开头。"""
    return has_command_prefix(content, COMMAND_PREFIXES)


async def route_command(
    content: str,
    user_id: str,
    *,
    is_group: bool = True,
    api: Any | None = None,
    group_openid: str = "",
    message_id: str | None = None,
) -> str | None:
    """将标准化后的命令转交给对应业务处理器。"""
    command = normalize_command(content)

    if has_command_prefix(command, ("/指令帮助", "/help")):
        return await handle_help()
    if has_command_prefix(command, ("/服务器地图", "/map")):
        return await handle_map()
    if has_command_prefix(command, ("/list",)):
        return await handle_list()
    if has_command_prefix(command, ("/视奸",)):
        return await handle_shijian()
    if has_command_prefix(command, ("/ip",)):
        return await handle_ip()
    if has_command_prefix(command, ("/status",)):
        return await handle_status()
    if has_command_prefix(command, ("/抽奖",)):
        return await handle_lottery(user_id, is_group=is_group)
    if has_command_prefix(command, ("/开始钓鱼",)):
        return await handle_start_fishing(
            api,
            group_openid,
            user_id,
            is_group=is_group,
            reply_message_id=message_id,
        )
    if has_command_prefix(command, (POLL_RESULTS_COMMAND,)):
        return await handle_poll_results(
            user_id,
            group_openid,
            is_group=is_group,
        )
    if has_command_prefix(command, (POLL_COMMAND,)):
        return await handle_poll(user_id, is_group=is_group)
    if has_command_prefix(command, (SELF_MUZZLE_COMMAND,)):
        return await handle_self_muzzle(
            api,
            group_openid,
            user_id,
            is_group=is_group,
        )
    if has_command_prefix(command, ("/执行",)):
        return await handle_execute(command[len("/执行"):].strip(), user_id)
    if has_command_prefix(command, ("/开启",)):
        return await handle_open(command[len("/开启"):].strip(), user_id)
    if has_command_prefix(command, ("/停止",)):
        return await handle_stop(command[len("/停止"):].strip(), user_id)
    if has_command_prefix(command, ("/终止",)):
        return await handle_kill(command[len("/终止"):].strip(), user_id)
    return None
