"""
服务器查询处理器
处理 list / 视奸 / ip / 服务器地图 命令
移植自 NoneBot 项目 mybot/plugins/mlc/__init__.py
"""
from utils import messages
from utils.mc_utils import (
    SERVERS, QUERY_ORDER,
    get_status, get_query, get_players, get_players_vc,
)


# 兼容已有导入；文案实际统一维护在 utils.messages。
HELP_TEXT = messages.HELP
MAP_TEXT = messages.SERVER_MAP


# ==================== 格式化函数 ====================

async def format_server_full(server_name: str) -> str:
    """完整服务器信息（在线 + 延迟 + 玩家）。"""
    servers = SERVERS.get(server_name)
    if not servers:
        return messages.server_unknown(server_name)

    main_addr, node_addr = servers[0], servers[1] if len(servers) > 1 else servers[0]
    status_main = await get_status(main_addr)
    status_node = await get_status(node_addr)

    if not status_main:
        return messages.server_unreachable(server_name)

    # 获取玩家列表
    if server_name == "生存服":
        query_vc = get_query(SERVERS["VC查人端口"][0])
        players = get_players_vc(query_vc)
    else:
        players = get_players(status_main)

    latency = (
        f"{status_node.latency:.2f}ms"
        if status_node
        else messages.SERVER_TIMEOUT
    )

    return messages.server_full(
        server_name,
        status_main.players.online,
        node_addr,
        latency,
        players,
    )


async def format_server_players(server_name: str) -> str:
    """简化玩家信息（视奸）。"""
    servers = SERVERS.get(server_name)
    if not servers:
        return messages.server_unknown(server_name)

    main_addr = servers[0]
    status_main = await get_status(main_addr)

    if not status_main:
        return messages.server_unreachable(server_name)

    if server_name == "生存服":
        query_vc = get_query(SERVERS["VC查人端口"][0])
        players = get_players_vc(query_vc)
    else:
        players = get_players(status_main)

    return messages.server_players(server_name, status_main.players.online, players)


async def format_server_ping(server_name: str) -> str:
    """服务器延迟信息（ip）。"""
    servers = SERVERS.get(server_name)
    if not servers:
        return messages.server_unknown(server_name)

    main_addr, node_addr = servers[0], servers[1] if len(servers) > 1 else servers[0]
    status_main = await get_status(main_addr)
    status_node = await get_status(node_addr)

    if not status_main:
        return messages.server_unreachable(server_name)

    latency = (
        f"{status_node.latency:.2f}ms"
        if status_node
        else messages.SERVER_TIMEOUT
    )

    return messages.server_ping(server_name, node_addr, latency)


# ==================== 命令处理入口 ====================

async def handle_list() -> str:
    """处理 list 命令 — 全部服务器完整状态。"""
    sections = [await format_server_full(name) for name in QUERY_ORDER]
    return messages.server_status_list(sections)


async def handle_shijian() -> str:
    """处理 视奸 命令 — 全部服务器在线玩家。"""
    sections = [await format_server_players(name) for name in QUERY_ORDER]
    return messages.server_player_list(sections)


async def handle_ip() -> str:
    """处理 ip 命令 — 全部服务器延迟。"""
    sections = [await format_server_ping(name) for name in QUERY_ORDER]
    return messages.server_ping_list(sections)


async def handle_map() -> str:
    """处理 服务器地图 命令。"""
    return messages.SERVER_MAP


async def handle_help() -> str:
    """处理 指令帮助 命令。"""
    return messages.HELP
