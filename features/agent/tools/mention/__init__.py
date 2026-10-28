"""定义 Agent 在最终群聊回复中提及成员的轻量工具。"""

from pydantic import Field

from features.agent.tools.common import NonBlank, ToolArgs, ToolContext, ToolResult, ToolSpec


class MentionGroupMemberArgs(ToolArgs):
    """声明本轮消息中可用的群成员 OpenID。"""

    user_openid: NonBlank = Field(
        description="当前发言者或当前消息显式 @ 到的群成员 OpenID；只能使用系统提供的可提及成员 ID。"
    )


def mention_group_member(args: MentionGroupMemberArgs, context: ToolContext) -> ToolResult:
    """校验群聊和目标范围，将成员加入最终回复的提及队列。"""
    if not context.group_id:
        return ToolResult(False, "group_required", "成员提及只支持群聊。")
    target = args.user_openid.strip()
    if target not in context.mentionable_user_ids:
        return ToolResult(False, "mention_target_unavailable", "目标不在当前消息允许提及的成员范围内。")
    if target in context.pending_mentions:
        return ToolResult(True, "already_queued", "该成员已加入本轮回复的提及队列。", {"delivery": "pending"})

    context.pending_mentions.append(target)
    return ToolResult(
        True,
        "mention_queued",
        "成员已加入本轮最终群聊回复的提及队列；发送层会自动添加提及，不要在回复正文中编造提及标签。",
        {"delivery": "pending"},
    )


TOOLS = (
    ToolSpec(
        "mention_group_member",
        "仅当用户当前明确要求在回复中 @ 人时，提及当前发言者或当前消息显式 @ 到的群成员；最终回复会自动附加真实提及。",
        MentionGroupMemberArgs,
        mention_group_member,
    ),
)
