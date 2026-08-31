"""机器人功能共用的权限校验。"""
from config import SUPERUSERS


def check_superuser(user_id: str) -> bool:
    """检查用户是否为配置中的超级用户。"""
    return user_id in SUPERUSERS
