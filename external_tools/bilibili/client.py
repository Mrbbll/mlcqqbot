"""读取 Bilibili 直播间状态，复用项目已有的 httpx 依赖。"""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class LiveRoomInfo:
    """保存通知需要的直播间状态、主播名和标题。"""

    room_id: int
    is_live: bool
    uname: str
    title: str


class BilibiliApiClient:
    """管理直播间查询使用的异步 HTTP 会话。"""

    def __init__(self, timeout: int) -> None:
        """保存请求超时配置，延迟创建 HTTP 会话。"""
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """创建带直播页面来源信息的 HTTP 会话。"""
        self._client = httpx.AsyncClient(
            base_url="https://api.live.bilibili.com",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://live.bilibili.com/",
            },
            timeout=self._timeout,
        )

    async def close(self) -> None:
        """关闭会话并释放连接。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_room_info(self, room_id: int) -> LiveRoomInfo:
        """校验接口返回值，避免将请求失败误判为下播。"""
        if self._client is None:
            raise RuntimeError("Bilibili API client is not started")
        response = await self._client.get(
            "/xlive/web-room/v1/index/getRoomBaseInfo",
            params={"room_ids": room_id, "req_biz": "web_room_componet"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise ValueError("Bilibili 直播间接口返回错误")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("Bilibili 直播间信息无效")
        rooms = data.get("by_room_ids")
        if not isinstance(rooms, dict) or len(rooms) != 1:
            raise ValueError("Bilibili 直播间不存在或返回信息不完整")
        room = next(iter(rooms.values()))
        if not isinstance(room, dict) or type(room.get("live_status")) is not int:
            raise ValueError("Bilibili 直播状态缺失或无效")
        if room["live_status"] not in (0, 1, 2):
            raise ValueError("Bilibili 直播状态未知")
        return LiveRoomInfo(
            room_id=room_id,
            is_live=room["live_status"] == 1,
            uname=str(room.get("uname") or "主播"),
            title=str(room.get("title") or "（无标题）"),
        )
