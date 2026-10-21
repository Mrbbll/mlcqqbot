"""OOPZ 功能的文本命令处理入口。"""
from config import KOOK_INVITE_URL, OOPZ_INVITE_URL
from presentation import messages


async def handle_invites() -> str:
    """生成 OOPZ 与 KOOK 社群邀请链接回复。"""
    return messages.community_invite_links(OOPZ_INVITE_URL, KOOK_INVITE_URL)
