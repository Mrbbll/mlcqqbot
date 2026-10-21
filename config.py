"""
项目配置文件
从 NoneBot 项目移植的 MCSM 面板和服务器配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ==================== QQ Bot 配置 ====================
QQ_BOT_APPID = os.getenv("QQ_BOT_APPID", "102090462")
QQ_BOT_SECRET = os.getenv("QQ_BOT_SECRET", "")


def get_env_list(name: str) -> list[str]:
    """读取以英文逗号分隔的环境变量，忽略空值和两侧空白。"""
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


def get_env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    """读取整数环境变量并校验下限及可选上限，无效值使用默认值。"""
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed < minimum or (maximum is not None and parsed > maximum):
        return default
    return parsed


# ==================== 超级用户 ====================
SUPERUSERS = get_env_list("SUPERUSERS")

# ==================== 云端 AI 助手 ====================
AGENT_API_URL = os.getenv("AGENT_API_URL", "").strip()
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "").strip()
AGENT_MODEL = os.getenv("AGENT_MODEL", "").strip()
AGENT_SERVER_CONTEXT = os.getenv("AGENT_SERVER_CONTEXT", "").strip()[:4000]
AGENT_LOG_MODEL_RESPONSE = os.getenv("AGENT_LOG_MODEL_RESPONSE", "").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}

# ==================== QQ 群聊指令面板 ====================
QQ_GROUP_OPENIDS = get_env_list("QQ_GROUP_OPENIDS")

# ==================== OneBot v11 QQ 群消息转发 ====================
ONEBOT_WS_HOST = os.getenv("ONEBOT_WS_HOST", "127.0.0.1").strip() or "127.0.0.1"
ONEBOT_WS_PORT = get_env_int("ONEBOT_WS_PORT", 8081, 1, 65535)
ONEBOT_WS_ACCESS_TOKEN = os.getenv("ONEBOT_WS_ACCESS_TOKEN", "").strip()
ONEBOT_WS_HEARTBEAT = get_env_int("ONEBOT_WS_HEARTBEAT", 30, 5, 300)

# ==================== OOPZ / KOOK 邀请链接 ====================
OOPZ_INVITE_URL = os.getenv("OOPZ_INVITE_URL", "").strip()
KOOK_INVITE_URL = os.getenv("KOOK_INVITE_URL", "").strip()

# ==================== Gitee 提交通知 ====================
GITEE_USERS = get_env_list("GITEE_USERS")
GITEE_NOTIFY_GROUPS = get_env_list("GITEE_NOTIFY_GROUPS")
GITEE_TOKEN = os.getenv("GITEE_TOKEN", "").strip()
GITEE_POLL_INTERVAL = get_env_int("GITEE_POLL_INTERVAL", 60, 5)
GITEE_REQUEST_TIMEOUT = get_env_int("GITEE_REQUEST_TIMEOUT", 20, 1, 120)
GITEE_MAX_COMMITS = get_env_int("GITEE_MAX_COMMITS", 10, 1, 20)

# ==================== 群聊投票 ====================
PROJECT_ROOT = Path(__file__).resolve().parent
TENCENT_SHEET_URL = os.getenv(
    "TENCENT_SHEET_URL",
    "https://docs.qq.com/sheet/DUU5xSWRCR2VZdkhO?tab=BB08J2",
)
TENCENT_ADVENTURE_TAB = os.getenv("TENCENT_ADVENTURE_TAB", "BB08J2")
TENCENT_TECHNOLOGY_TAB = os.getenv("TENCENT_TECHNOLOGY_TAB", "g9hsny")
POLL_DB_PATH = Path(
    os.getenv("POLL_DB_PATH", str(PROJECT_ROOT / "data" / "polls.sqlite3"))
)

# ==================== MCSM 面板配置 ====================
MCSM_PANEL_URL = "http://127.0.0.1:23333"
MCSM_API_SECRET = "d91738751a9447ccaca2086ea01574e5"
DEFAULT_DAEMON_ID = "48118c0a53ec4818b285251b35a9825d"


def get_instance_id(instance_name: str) -> str:
    """根据实例简称获取 MCSM 实例 UUID"""
    mapping = {
        "scf":       "ab1618cf3a484ebd9a8d1bc8e15222b7",   # 生存服
        "mod1":       "27ea20d72183463bb4cf090873793cc1",   # 冒险服
        "mod2":      "8ab80a3c099641f592f16164b6fb620a",   # 科技服
        "minigames": "63da3dc840434753b0abd2e62a08746c",   # 小游戏服
        "bot":       "d575610bc678421faf1fb524efd71a46",   # 机器人
    }
    return mapping.get(instance_name, "null")
