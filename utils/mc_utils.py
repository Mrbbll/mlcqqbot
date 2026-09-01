"""
Minecraft 服务器查询工具函数
从 NoneBot 项目 (mybot/plugins/mlc/__init__.py) 移植
"""
import traceback
from base64 import b64decode
from io import BytesIO

from mcstatus import JavaServer

from utils.messages import PLAYER_EMPTY, PLAYER_UNKNOWN


# ==================== 服务器配置 ====================
# 格式: [主服务器地址, 节点服务器地址]
SERVERS = {
    "生存服": [
        "127.0.0.1:25566",          # 主服务器（图标/人数）
        "43.248.188.28:41894"       # 节点服务器（ping）
    ],
    "冒险服": [
        "127.0.0.1:25565",          # 主服务器
        "103.205.254.30:57904"      # 节点服务器
    ],
    "科技服": [
        "127.0.0.1:25569",
        "103.205.254.30:32364"
    ],
    "小游戏服": [
        "127.0.0.1:25571",
        "43.248.188.28:17343"
    ],
    "VC查人端口": ["127.0.0.1:25565"]   # 仅用于查人
}


# ==================== 查询函数 ====================

async def get_status(addr: str):
    """获取 Minecraft 服务器状态（延迟、人数、图标等），带异常处理"""
    try:
        server = JavaServer.lookup(addr)
        return server.status()
    except Exception as e:
        print(f"获取服务器 {addr} 状态失败：{str(e)}")
        traceback.print_exc()
        return None


def get_query(addr: str):
    """获取 Minecraft 服务器 query 信息（完整玩家名列表）"""
    try:
        server = JavaServer.lookup(addr)
        return server.query()
    except Exception as e:
        print(f"获取服务器 {addr} query 失败：{str(e)}")
        traceback.print_exc()
        return None


# ==================== 数据提取函数 ====================

def get_icon(status):
    """从 status 中提取服务器图标，返回 base64 解码后的 BytesIO 对象"""
    if not status or not status.icon:
        return None
    try:
        aa, bb = status.icon.split("base64,")
        return BytesIO(b64decode(bb))
    except Exception:
        return None


def get_icon_base64(status):
    """从 status 中提取服务器图标的 base64 字符串（去除前缀）"""
    if not status or not status.icon:
        return None
    try:
        aa, bb = status.icon.split("base64,")
        return bb
    except Exception:
        return None


def get_players(status):
    """从 status 中提取玩家名列表（通过 sample）"""
    if not status:
        return PLAYER_UNKNOWN
    try:
        if status.players.sample:
            return ", ".join(p.name for p in status.players.sample)
        return PLAYER_EMPTY
    except Exception:
        return PLAYER_UNKNOWN


def get_players_vc(query):
    """从 query 中提取完整玩家名列表"""
    if not query:
        return PLAYER_UNKNOWN
    try:
        if query.players.names:
            return ", ".join(query.players.names)
        return PLAYER_EMPTY
    except Exception:
        return PLAYER_UNKNOWN


# ==================== 服务器组列表 ====================
# 按查询顺序排列的服务器名称
QUERY_ORDER = ["生存服", "小游戏服", "冒险服", "科技服"]
