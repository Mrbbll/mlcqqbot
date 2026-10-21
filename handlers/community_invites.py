"""OOPZ 和 KOOK 社群邀请链接命令处理器。"""
from config import KOOK_INVITE_URL, OOPZ_INVITE_URL
from utils import messages


async def handle_community_invites() -> str:
    """生成 OOPZ 与 KOOK 社群邀请链接回复。"""
    return messages.community_invite_links(OOPZ_INVITE_URL, KOOK_INVITE_URL)
