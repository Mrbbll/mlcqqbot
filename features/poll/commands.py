"""投票功能的文本命令处理入口。"""
from presentation import messages
from features.security.permissions import check_superuser
from external_tools.storage.poll_repository import get_active_poll_result


POLL_COMMAND = "/投票"
POLL_RESULTS_COMMAND = "/投票结果"


async def handle_poll(user_id: str, *, is_group: bool = True) -> str:
    """校验管理员权限并显示投票类别选择。"""
    if not check_superuser(user_id):
        return messages.POLL_PERMISSION_DENIED
    if not is_group:
        return messages.POLL_GROUP_ONLY
    return messages.POLL_CATEGORY_PROMPT


async def handle_poll_results(
    user_id: str,
    group_openid: str,
    *,
    is_group: bool = True,
) -> str:
    """返回群内当前投票结果。"""
    if not check_superuser(user_id):
        return messages.POLL_PERMISSION_DENIED
    if not is_group or not group_openid:
        return messages.POLL_RESULTS_GROUP_ONLY
    result = get_active_poll_result(group_openid)
    if result is None:
        return messages.POLL_NOT_ACTIVE
    return messages.poll_results(result)
