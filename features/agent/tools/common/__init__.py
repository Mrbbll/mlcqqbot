"""定义工具共用的严格参数、宿主上下文、结果对象和注册记录。"""

from dataclasses import asdict, dataclass, field
import json
from typing import Annotated, Any, Callable

from pydantic import BaseModel, ConfigDict, StringConstraints


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MAX_TOOL_RESULT_CHARS = 8000


class ToolArgs(BaseModel):
    """所有工具参数拒绝类型隐式转换和未声明字段。"""

    model_config = ConfigDict(strict=True, extra="forbid")


@dataclass(slots=True)
class ToolContext:
    """由宿主注入身份、原始问题和本轮资源，永不生成模型参数。"""

    question: str = ""
    user_id: str = ""
    group_id: str = ""
    timeout_seconds: float = 120
    image_inputs: list[dict] = field(default_factory=list)
    saved_emoji_images: list[str] = field(default_factory=list)
    pending_emoji_images: list[dict] = field(default_factory=list)
    discovered_paths: set[str] = field(default_factory=set)
    pending_files: list[str] = field(default_factory=list)
    mentionable_user_ids: set[str] = field(default_factory=set)
    pending_mentions: list[str] = field(default_factory=list)
    available_emoji_ids: set[str] = field(default_factory=set)
    emoji_delete_attempted: bool = False


def _compact_data(value: Any, limit: int) -> Any:
    """逐层缩短长文本和列表，保留结构、数值以及布尔状态。"""
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_compact_data(item, limit) for item in value[:max(1, limit // 100)]]
    if isinstance(value, dict):
        return {key: _compact_data(item, limit) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class ToolResult:
    """用稳定状态与结构化数据表达结果，文案不参与执行状态判断。"""

    ok: bool
    code: str = "ok"
    message: str = ""
    data: dict = field(default_factory=dict)
    truncated: bool = False
    retryable: bool = False

    @property
    def status(self) -> str:
        """将明确的结果码映射为独立日志中的执行状态。"""
        if self.code in {"timeout", "cancelled", "skipped"}:
            return self.code
        if self.code in {"permission_denied", "unknown_tool"}:
            return "denied"
        return "completed" if self.ok else "failed"

    def to_json(self, max_chars: int = MAX_TOOL_RESULT_CHARS, guidance: str = "") -> str:
        """生成有界且始终可解析的 JSON，截断时保留状态和元数据。"""
        if max_chars < 512:
            raise ValueError("工具 JSON 摘要预算不能小于 512 字符。")
        payload = asdict(self)
        if guidance:
            payload["guidance"] = guidance
        text = json.dumps(payload, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        payload["truncated"] = True
        payload["message"] = self.message[:max_chars // 8]
        if guidance:
            payload["guidance"] = guidance[:max_chars // 8]
        limit = max_chars // 2
        while limit:
            payload["data"] = _compact_data(self.data, limit)
            text = json.dumps(payload, ensure_ascii=False)
            if len(text) <= max_chars:
                return text
            limit //= 2
        payload["data"] = {"notice": "工具数据过长，已截断；请缩小查询范围。"}
        return json.dumps(payload, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """一次绑定工具名称、说明、参数模型、处理函数及权限要求。"""

    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Callable[[Any, ToolContext], ToolResult]
    requires_superuser: bool = False
    permission_denied_message: str = "服务器文件和命令工具仅限超级用户使用。"

    @property
    def schema(self) -> dict:
        """从实际执行所用的参数模型生成 Chat Completions 工具定义。"""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.args_model.model_json_schema(),
        }}
