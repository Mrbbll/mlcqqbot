"""选择本轮需要发送的本地文件，发送目标及实际发送由 QQ 入口控制。"""

import re
from pathlib import Path

from pydantic import Field

from features.agent.tools.common import NonBlank, ToolArgs, ToolContext, ToolResult, ToolSpec
from features.agent.tools.filesystem import path_is_authorized
from features.file_sender import validate_file


_FILE_TERMS = r"文件|附件|日志|文档|压缩包|脚本|配置|\.[a-z0-9]{1,12}(?![a-z0-9])"
_DELIVERY_VERB = r"(?:发送(?!的|过|了)|上传(?!的|过|了)|发(?!送|的|过|了)|传(?!的|过|了))"
_CLAUSE = r"[^，。！？!?；;\n]"
_DELIVERY_PATTERNS = (
    rf"(?:把|将){_CLAUSE}{{0,80}}(?:{_FILE_TERMS}){_CLAUSE}{{0,40}}{_DELIVERY_VERB}",
    rf"{_DELIVERY_VERB}{_CLAUSE}{{0,80}}(?:{_FILE_TERMS})",
)
_NEGATED_DELIVERY = rf"(?:不要|别|勿|不必|不用|不需要|禁止|不准|不允许|先别|不把|不将){_CLAUSE}{{0,60}}(?:发送|上传|发|传)|不(?:发送|上传|发|传)"
_DELIVERY_DISCUSSION = rf"(?:为什么|为何|怎么|如何|是否|要不要){_CLAUSE}{{0,20}}(?:发送|上传|发|传)"
_TEXT_MESSAGE_DELIVERY = r"(?:发送|发|传)(?:给我)?(?:一条|一段|个|条)?(?:消息|文字|文本|通知)"
_TEXT_CONTENT_DELIVERY = rf"(?:{_DELIVERY_VERB}{_CLAUSE}{{0,40}}(?:文件|日志|附件)(?:的)?内容|(?:文件|日志|附件)(?:的)?内容{_CLAUSE}{{0,40}}{_DELIVERY_VERB})"


def user_requested_file_delivery(question: str) -> bool:
    """仅在当前消息明确提出文件发送请求时允许进入发送队列。"""
    normalized = (question or "").casefold()
    if any(re.search(pattern, normalized) for pattern in (
        _NEGATED_DELIVERY, _DELIVERY_DISCUSSION, _TEXT_MESSAGE_DELIVERY,
        _TEXT_CONTENT_DELIVERY,
    )):
        return False
    return any(re.search(pattern, normalized) for pattern in _DELIVERY_PATTERNS)


class SendFileArgs(ToolArgs):
    """仅允许模型选择文件，不允许指定其他接收人或群。"""

    path: NonBlank = Field(description="用户点名或本轮查找工具发现的文件绝对路径；支持日志、文档、压缩包等普通文件。")


def select_file(args: SendFileArgs, context: ToolContext) -> ToolResult:
    """校验发送范围并加入本轮待发送项，尚未实际上传或发送。"""
    if not context.group_id:
        return ToolResult(False, "group_required", "文件发送目前只支持当前群聊。")
    if not user_requested_file_delivery(context.question):
        return ToolResult(False, "delivery_not_requested", "用户当前消息没有明确要求发送文件；引用文件或请求查看文件时只读取附件，不发送本机文件。")
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
    ToolSpec("send_server_file", "用户要求发送文件时选择一个本轮已发现或用户点名的本地文件，最多 20 MB，每轮一个，只发到当前群；返回 pending 表示尚未确认发送。", SendFileArgs, select_file, True),
)
