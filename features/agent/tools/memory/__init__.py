"""向 Agent 注册长期记忆的添加、查询与移除工具。"""

from pydantic import Field

from features.agent import memory
from features.agent.tools.common import NonBlank, ToolArgs, ToolContext, ToolResult, ToolSpec


class AddMemoryArgs(ToolArgs):
    """定义需要保存的单条长期记忆。"""

    content: NonBlank = Field(max_length=2000, description="当前发言者提供的有长期价值的信息，标明其为陈述而非未经验证的事实。")


class SearchMemoryArgs(ToolArgs):
    """定义语义检索内容、数量和可选的发言者过滤。"""

    query: NonBlank = Field(max_length=2000, description="记忆语义检索词。")
    user_id: str = Field(default="", max_length=200, description="按归属用户过滤；留空检索全部用户。")
    limit: int = Field(default=5, ge=1, le=20, description="最多返回的记忆条数。")


class DeleteMemoryArgs(ToolArgs):
    """定义目标用户和用于语义匹配的内容。"""

    user_id: NonBlank = Field(max_length=200, description="要删除其记忆的用户 ID。")
    query: NonBlank = Field(max_length=2000, description="需要删除的记忆内容或语义描述。")


def _failure(exc: Exception) -> ToolResult:
    """将存储和网络故障转换成不暴露敏感信息的稳定状态。"""
    code = str(exc) if isinstance(exc, memory.MemoryError) else "memory_store_unavailable"
    messages = {
        "memory_delete_incomplete": "记忆 RAG 删除未完成，部分记忆可能已删除，请重新查询。",
        "embedding_not_configured": "记忆 RAG 的 Embedding 服务尚未配置完整。",
        "embedding_access_denied": "Embedding 请求返回 401 或 403，请检查服务权限、密钥及网络代理。",
        "embedding_unavailable": "Embedding 服务请求失败或响应无效。",
        "memory_dimension_mismatch": "记忆 RAG 的向量维度与已有集合不匹配。",
        "memory_dependency_missing": "记忆 RAG 缺少 qdrant-client，请在机器人运行环境中安装项目依赖。",
    }
    message = messages.get(code, "记忆 RAG 操作失败，请检查 Embedding 服务和本地存储。")
    return ToolResult(False, code, message, retryable=True)


def add_memory(args: AddMemoryArgs, context: ToolContext) -> ToolResult:
    """只使用宿主提供的当前发送者作为新记忆的归属。"""
    try:
        record = memory.add(context.user_id, args.content, context.timeout_seconds)
        return ToolResult(True, message="记忆已保存。", data=record)
    except (memory.MemoryError, OSError, ValueError) as exc:
        return _failure(exc)


def search_memory(args: SearchMemoryArgs, context: ToolContext) -> ToolResult:
    """查询全部用户或指定用户的记忆，并返回归属和相似度。"""
    try:
        items = memory.search(args.query, args.limit, context.timeout_seconds, args.user_id.strip())
        return ToolResult(True, message="记忆查询完成。", data={"items": items})
    except (memory.MemoryError, OSError, ValueError) as exc:
        return _failure(exc)


def delete_memory(args: DeleteMemoryArgs, context: ToolContext) -> ToolResult:
    """删除指定用户中相似度达到阈值的所有记忆。"""
    try:
        count = memory.delete(args.user_id.strip(), args.query, context.timeout_seconds)
        return ToolResult(True, message="匹配记忆已删除。" if count else "没有找到符合条件的记忆。", data={"deleted_count": count})
    except (memory.MemoryError, OSError, ValueError) as exc:
        return _failure(exc)


TOOLS = (
    ToolSpec("add_memory", "记忆 RAG：将当前发言者提供的有长期价值的信息向量化并保存。", AddMemoryArgs, add_memory),
    ToolSpec("search_memory", "记忆 RAG：按向量语义检索所有用户或指定用户的长期记忆，返回归属和时间。", SearchMemoryArgs, search_memory),
    ToolSpec("delete_memory", "记忆 RAG：用户明确要求时删除指定用户语义相似度至少 0.85 的全部匹配记忆。", DeleteMemoryArgs, delete_memory),
)
