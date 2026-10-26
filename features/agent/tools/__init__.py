"""汇总分类工具定义，在权限检查后统一校验参数并执行处理函数。"""

import json
import logging

from pydantic import ValidationError

from features.security import permissions
from features.agent.tools.common import ToolContext, ToolResult
from features.agent.tools.command import TOOLS as COMMAND_TOOLS
from features.agent.tools.emoji import TOOLS as EMOJI_TOOLS
from features.agent.tools.filesystem import TOOLS as FILESYSTEM_TOOLS
from features.agent.tools.discovery import TOOLS as DISCOVERY_TOOLS
from features.agent.tools.file_delivery import TOOLS as FILE_DELIVERY_TOOLS


TOOL_SPECS = (*EMOJI_TOOLS, *FILESYSTEM_TOOLS, *COMMAND_TOOLS, *DISCOVERY_TOOLS, *FILE_DELIVERY_TOOLS)
TOOL_REGISTRY = {tool.name: tool for tool in TOOL_SPECS}
ALL_TOOL_SCHEMAS = [tool.schema for tool in TOOL_SPECS]
if len(TOOL_REGISTRY) != len(TOOL_SPECS):
    raise ValueError("Agent 工具名称不能重复。")


def visible_tools(user_id: str) -> list[dict]:
    """仅向模型提供当前用户可以调用的工具，权限不是模型参数。"""
    privileged = permissions.check_superuser(user_id)
    return [spec.schema for spec in TOOL_REGISTRY.values() if privileged or not spec.requires_superuser]


def execute_tool(tool_call: dict, context: ToolContext) -> ToolResult:
    """重新鉴权后按参数模型严格校验，保留机器可读的失败原因。"""
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return ToolResult(False, "invalid_arguments", "工具参数格式无效。")
    name = function.get("name")
    spec = TOOL_REGISTRY.get(name) if isinstance(name, str) else None
    if spec is None:
        return ToolResult(False, "unknown_tool", "当前未注册该工具。")
    if spec.requires_superuser and not permissions.check_superuser(context.user_id):
        return ToolResult(False, "permission_denied", "服务器文件和命令工具仅限超级用户使用。")
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return ToolResult(False, "invalid_arguments", "工具参数不是有效的 JSON。")
    try:
        args = spec.args_model.model_validate(arguments)
    except ValidationError as exc:
        errors = [{"field": ".".join(map(str, item["loc"])), "type": item["type"], "message": item["msg"]}
                  for item in exc.errors(include_input=False, include_context=False, include_url=False)[:10]]
        return ToolResult(False, "invalid_arguments", "工具参数校验失败，请按参数定义修正。", {"errors": errors})
    try:
        return spec.handler(args, context)
    except (OSError, RuntimeError, ValueError) as exc:
        logging.getLogger("mlcbot").warning("Agent 工具执行异常: tool=%s error=%s", name, type(exc).__name__)
        return ToolResult(False, "execution_error", "工具执行失败，请检查参数或运行环境。")
