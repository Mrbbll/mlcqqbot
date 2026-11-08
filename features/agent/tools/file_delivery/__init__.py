"""选择本轮需要发送的本地文件，发送目标及实际发送由 QQ 入口控制。"""

from pathlib import Path

from pydantic import Field

from features.agent.tools.common import NonBlank, ToolArgs, ToolContext, ToolResult, ToolSpec
from features.agent.tools.filesystem import path_is_authorized
from features.file_sender import validate_file


class SendFileArgs(ToolArgs):
    """仅允许模型选择文件，不允许指定其他接收人或群。"""

    path: NonBlank = Field(description="用户点名或本轮查找工具发现的文件绝对路径；支持日志、文档、压缩包等普通文件。")


def select_file(args: SendFileArgs, context: ToolContext) -> ToolResult:
    """校验发送范围并加入本轮待发送项，尚未实际上传或发送。"""
    if not context.group_id:
        return ToolResult(False, "group_required", "文件发送目前只支持当前群聊。")
    if context.pending_files:
        return ToolResult(False, "already_selected", "本轮已选择一个文件，不重复发送。")
    if not Path(args.path).is_absolute():
        return ToolResult(False, "invalid_path", "请使用文件的绝对路径。")
    if not path_is_authorized(args.path, context):
        return ToolResult(False, "path_not_requested", "请先查找实际文件，或由用户明确文件路径。")
    try:
        path = validate_file(args.path)
        size = path.stat().st_size
    except ValueError as exc:
        return ToolResult(False, "invalid_file", str(exc))
    except (OSError, RuntimeError):
        return ToolResult(False, "file_unavailable", "文件不存在或无法访问。")
    context.pending_files.append(str(path))
    return ToolResult(True, message="文件已加入待发送队列；QQ 确认前不能声称已发送。", data={
        "name": path.name, "size_bytes": size, "delivery": "pending",
    })


TOOLS = (
    ToolSpec("send_server_file", "根据任务和上下文自主选择需要交付的本地文件，包括生成的图表或文档，无需用户另说发送；使用本轮已发现或用户点名的真实路径，最多 20 MB，每轮一个，只发到当前群；pending 尚未确认发送。", SendFileArgs, select_file, True),
)
