"""
项目配置文件
从 NoneBot 项目移植的 MCSM 面板和服务器配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== QQ Bot 配置 ====================
QQ_BOT_APPID = os.getenv("QQ_BOT_APPID", "102090462")
QQ_BOT_SECRET = os.getenv("QQ_BOT_SECRET", "")


def get_env_list(name: str) -> list[str]:
    """读取以英文逗号分隔的环境变量，忽略空值和两侧空白。"""
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


# ==================== 超级用户 ====================
SUPERUSERS = get_env_list("SUPERUSERS")

# ==================== QQ 群聊指令面板 ====================
QQ_GROUP_OPENIDS = get_env_list("QQ_GROUP_OPENIDS")

# ==================== MCSM 面板配置 ====================
MCSM_PANEL_URL = "http://127.0.0.1:23333"
MCSM_API_SECRET = "d91738751a9447ccaca2086ea01574e5"
DEFAULT_DAEMON_ID = "48118c0a53ec4818b285251b35a9825d"


def get_instance_id(instance_name: str) -> str:
    """根据实例简称获取 MCSM 实例 UUID"""
    mapping = {
        "scf":       "ab1618cf3a484ebd9a8d1bc8e15222b7",   # 生存服
        "mod":       "27ea20d72183463bb4cf090873793cc1",   # 冒险服
        "mod1":      "8ab80a3c099641f592f16164b6fb620a",   # 科技服
        "minigames": "63da3dc840434753b0abd2e62a08746c",   # 小游戏服
        "bot":       "d575610bc678421faf1fb524efd71a46",   # 机器人
    }
    return mapping.get(instance_name, "null")
