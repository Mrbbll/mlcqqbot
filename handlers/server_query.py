"""
服务器查询处理器
处理 list / 视奸 / ip / 服务器地图 命令
移植自 NoneBot 项目 mybot/plugins/mlc/__init__.py
"""
from utils.mc_utils import (
    SERVERS, QUERY_ORDER,
    get_status, get_query, get_players, get_players_vc, get_icon_base64,
)


# ==================== 帮助信息 ====================

HELP_TEXT = """📋 指令帮助
━━━━━━━━━━━━━━━━━
list — 查询全部服务器状态
视奸 — 查看各服在线玩家
ip — 服务器延迟一览
status — 宿主机运行状态
服务器地图 — 地图和文档链接
MCSM面板（仅管理员）：
  /执行 <实例名> <命令>
  /开启 <实例名>
  /停止 <实例名>
  /终止 <实例名>"""

MAP_TEXT = """你好，我是服务器机器人 (●'◡'●)
生存服网页地图：43.248.188.28:19423
服务器文档：https://docs.qq.com/aio/DRnp3YU9sRmxWYnVB"""


# ==================== 格式化函数 ====================

async def format_server_full(server_name: str) -> str:
    """完整服务器信息（图标 + 在线 + 延迟 + 玩家）"""
    servers = SERVERS.get(server_name)
    if not servers:
        return f"❌ 未知服务器: {server_name}\n"

    main_addr, node_addr = servers[0], servers[1] if len(servers) > 1 else servers[0]
    status_main = await get_status(main_addr)
    status_node = await get_status(node_addr)

    if not status_main:
        return f"⚠️ {server_name}：无法连接\n"

    # 获取玩家列表
    if server_name == "生存服":
        query_vc = get_query(SERVERS["VC查人端口"][0])
        players = get_players_vc(query_vc)
    else:
        players = get_players(status_main)

    latency = f"{status_node.latency:.2f}ms" if status_node else "超时"

    return (
        f"━━━ {server_name} ━━━\n"
        f"在线: {status_main.players.online} 人\n"
        f"节点({node_addr})延迟: {latency}\n"
        f"玩家: {players}\n"
    )


async def format_server_players(server_name: str) -> str:
    """简化玩家信息（视奸）"""
    servers = SERVERS.get(server_name)
    if not servers:
        return f"❌ 未知服务器: {server_name}\n"

    main_addr = servers[0]
    status_main = await get_status(main_addr)

    if not status_main:
        return f"⚠️ {server_name}：无法连接\n"

    if server_name == "生存服":
        query_vc = get_query(SERVERS["VC查人端口"][0])
        players = get_players_vc(query_vc)
    else:
        players = get_players(status_main)

    return (
        f"🔹 {server_name}\n"
        f"在线: {status_main.players.online} 人\n"
        f"玩家: {players}\n"
    )


async def format_server_ping(server_name: str) -> str:
    """服务器延迟信息（ip）"""
    servers = SERVERS.get(server_name)
    if not servers:
        return f"❌ 未知服务器: {server_name}\n"

    main_addr, node_addr = servers[0], servers[1] if len(servers) > 1 else servers[0]
    status_main = await get_status(main_addr)
    status_node = await get_status(node_addr)

    if not status_main:
        return f"⚠️ {server_name}：无法连接\n"

    latency = f"{status_node.latency:.2f}ms" if status_node else "超时"

    return (
        f"🔹 {server_name}\n"
        f"节点({node_addr})延迟: {latency}\n"
    )


# ==================== 命令处理入口 ====================

async def handle_list() -> str:
    """处理 list 命令 — 全部服务器完整状态"""
    lines = ["📊 查服结果如下：\n"]
    for name in QUERY_ORDER:
        lines.append(await format_server_full(name))
    return "\n".join(lines)


async def handle_shijian() -> str:
    """处理 视奸 命令 — 全部服务器在线玩家"""
    lines = ["👀 在线群友\n"]
    for name in QUERY_ORDER:
        lines.append(await format_server_players(name))
    return "\n".join(lines)


async def handle_ip() -> str:
    """处理 ip 命令 — 全部服务器延迟"""
    lines = ["📡 服务器列表：\n"]
    for name in QUERY_ORDER:
        lines.append(await format_server_ping(name))
    return "\n".join(lines)


async def handle_map() -> str:
    """处理 服务器地图 命令"""
    return MAP_TEXT


async def handle_help() -> str:
    """处理 指令帮助 命令"""
    return HELP_TEXT
