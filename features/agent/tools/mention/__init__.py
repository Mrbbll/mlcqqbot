"""定义 Agent 在最终群聊回复中提及成员的轻量工具。"""

from pydantic import Field

from features.agent.tools.common import NonBlank, ToolArgs, ToolContext, ToolResult, ToolSpec


class MentionGroupMemberArgs(ToolArgs):
    """声明从近期群聊上下文中选取的成员 user_id。"""

    user_id: NonBlank = Field(
        description="近期消息发言者的 user_id，或 QQ 原生 <@ID>/<@!ID> 标记内部的 ID；只填写 ID 值，不带标记。"
    )


def mention_group_member(args: MentionGroupMemberArgs, context: ToolContext) -> ToolResult:
    """校验群聊和目标范围，将成员加入最终回复的提及队列。"""
    if not context.group_id:
        return ToolResult(False, "group_required", "成员提及只支持群聊。")
    target = args.user_id.strip()
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
        "仅当用户当前明确要求在回复中 @ 人时，从当前或近期消息的 user_id 或原生 <@ID>/<@!ID> 标记中取得目标 ID，并将 ID 值填入 user_id 参数；不按昵称猜测或编造 ID。最终回复会自动附加真实提及。",
        MentionGroupMemberArgs,
        mention_group_member,
    ),
)
