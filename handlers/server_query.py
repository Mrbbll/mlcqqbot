"""
服务器查询处理器
处理 list / 视奸 / ip / 服务器地图 命令
移植自 NoneBot 项目 mybot/plugins/mlc/__init__.py
"""
from utils import messages
from utils.mc_utils import (
    SERVERS, SERVER_DOMAINS, QUERY_ORDER,
    get_status, get_query, get_players, get_players_vc,
)


# 兼容已有导入；文案实际统一维护在 utils.messages。
HELP_TEXT = messages.HELP
MAP_TEXT = messages.SERVER_MAP


# ==================== 格式化函数 ====================

async def format_server_full(server_name: str) -> str:
    """格式化服务器域名、在线人数和玩家名称。"""
    servers = SERVERS.get(server_name)
    if not servers:
        return messages.server_unknown(server_name)

    domain = SERVER_DOMAINS.get(server_name, "")
    status_main = await get_status(servers[0])

    if not status_main:
        return messages.server_unreachable(server_name, domain)

    # 获取玩家列表
    if server_name == "生存服":
        query_vc = get_query(SERVERS["VC查人端口"][0])
        players = get_players_vc(query_vc)
    else:
        players = get_players(status_main)

    return messages.server_full(
        server_name,
        domain,
        status_main.players.online,
        players,
    )


async def format_server_players(server_name: str) -> str | None:
    """格式化服务器在线人数和玩家名称。"""
    servers = SERVERS.get(server_name)
    if not servers:
        return messages.server_unknown(server_name)

    main_addr = servers[0]
    status_main = await get_status(main_addr)

    if not status_main:
        return None

    online_players = status_main.players.online
    if online_players <= 0:
        return None

    if server_name == "生存服":
        query_vc = get_query(SERVERS["VC查人端口"][0])
        players = get_players_vc(query_vc)
    else:
        players = get_players(status_main)

    return messages.server_players(server_name, online_players, players)


def format_server_domain(server_name: str) -> str:
    """格式化服务器对外连接域名，不发起网络查询。"""
    if server_name not in SERVERS:
        return messages.server_unknown(server_name)
    return messages.server_domain(
        server_name,
        SERVER_DOMAINS.get(server_name, ""),
    )


# ==================== 命令处理入口 ====================

async def handle_list() -> str:
    """处理 list 命令 — 各服域名、在线人数和玩家名称。"""
    sections = [await format_server_full(name) for name in QUERY_ORDER]
    return messages.server_status_list(sections)


async def handle_shijian() -> str:
    """处理 视奸 命令 — 各服在线人数和玩家名称。"""
    sections = []
    for name in QUERY_ORDER:
        section = await format_server_players(name)
        if section is not None:
            sections.append(section)
    return messages.server_player_list(sections)


async def handle_ip() -> str:
    """处理 ip 命令 — 仅返回各服连接域名。"""
    sections = [format_server_domain(name) for name in QUERY_ORDER]
    return messages.server_domain_list(sections)


async def handle_map() -> str:
    """处理 服务器地图 命令。"""
    return messages.SERVER_MAP


async def handle_help() -> str:
    """处理 指令帮助 命令。"""
    return messages.HELP
