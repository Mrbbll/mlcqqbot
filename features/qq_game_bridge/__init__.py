"""将 QQ 群消息通过 OneBot v11 转发到 Minecraft 游戏服。"""

from .bridge import forward_group_message, start_onebot_ws_server

__all__ = ("forward_group_message", "start_onebot_ws_server")
