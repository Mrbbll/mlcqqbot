"""将有界、脱敏的 Agent 工具调用记录写入独立轮转 JSON 日志。"""

import json
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from threading import Lock

from config import PROJECT_ROOT


LOG_PATH = Path(PROJECT_ROOT) / "logs" / "agent_tools.log"
_lock = Lock()
_sensitive = re.compile(r"password|passwd|secret|token|api.?key|authorization|密钥|密码", re.I)
_assignments = re.compile(
    r"((?:password|passwd|secret|token|api[_-]?key|authorization|密钥|密码)[\w-]*[\s\"']*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)", re.I,
)


def _redact_text(text: str) -> str:
    """遮蔽常见凭证赋值和 Bearer 值，再限制单条文本长度。"""
    text = re.sub(r"\bBearer\s+[^\s\"',;]+", "Bearer [REDACTED]", text, flags=re.I)
    text = _assignments.sub(r"\1[REDACTED]", text)
    return text if len(text) <= 1000 else text[:980] + "[日志摘要已截断]"


def _safe_arguments(arguments) -> dict:
    """只保留顶层参数摘要，屏蔽命令文本、凭证和多模态数据。"""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (ValueError, TypeError):
            return {"parse_error": True}
    if not isinstance(arguments, dict):
        return {"invalid_arguments": True}
    result = {}
    for key, value in list(arguments.items())[:20]:
        key = str(key)
        if _sensitive.search(key) or key in {"command", "data_url", "image_url"}:
            result[key[:80]] = "[REDACTED]"
        else:
            result[key[:80]] = _redact_text(str(value))
    return result


def _get_logger() -> logging.Logger:
    """幂等创建独立日志处理器，不向业务日志重复传播。"""
    logger = logging.getLogger("mlcbot.agent_tools")
    with _lock:
        if not logger.handlers:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3,
                                          encoding="utf-8", delay=True)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def record_tool_call(*, run_id: str, call_id: str, group_id: str, user_id: str,
                     name: str, arguments, result: str, status: str,
                     duration_ms: int, repeat_count: int) -> None:
    """记录一次执行、拒绝或跳过；日志不可写时不影响 Agent 返回。"""
    try:
        entry = {
            "time": datetime.now().astimezone().isoformat(),
            "run_id": run_id, "call_id": call_id, "group_id": group_id, "user_id": user_id,
            "tool": str(name)[:100], "status": status, "duration_ms": duration_ms,
            "repeat_count": repeat_count, "arguments": _safe_arguments(arguments),
            "result_chars": len(result), "result_preview": _redact_text(result),
        }
        _get_logger().info(json.dumps(entry, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        logging.getLogger("mlcbot").warning("Agent 工具日志写入失败，任务继续执行。")
