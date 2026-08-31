"""QQ 群成员禁言接口的共用封装。"""
from datetime import datetime, timedelta, timezone
from typing import Any

from botpy.http import Route


def mute_expire_at(minutes: int) -> str:
    """把禁言分钟数转换为 QQ OpenAPI 使用的 RFC3339 到期时间。"""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return expires_at.isoformat(timespec="seconds")


async def mute_group_member(
    api: Any,
    group_openid: str,
    member_openid: str,
    minutes: int,
) -> Any:
    """调用 QQ 群管理接口禁言指定的普通群成员。"""
    member = {
        "op": "add",
        "member_openid": member_openid,
        "mute_expire_at": mute_expire_at(minutes),
    }

    set_mutes = getattr(api, "set_group_member_mutes", None)
    if set_mutes is not None:
        return await set_mutes(group_openid, [member])

    route = Route(
        "POST",
        "/v2/groups/{group_openid}/restrict_chat_setting",
        group_openid=group_openid,
    )
    return await api._http.request(route, json={"members": [member]})
