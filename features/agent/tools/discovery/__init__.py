"""通过本机 Bash 发现通用文件路径，独立于实例管理面板。"""

import os
import subprocess
import time
from pathlib import Path
from typing import Literal

from pydantic import Field

from config import AGENT_FILE_SEARCH_ROOTS, PROJECT_ROOT
from features.agent.tools import command
from features.agent.tools.common import NonBlank, ToolArgs, ToolContext, ToolResult, ToolSpec


# 外部值只通过位置参数传递；NUL 分隔兼容含空格和换行的文件名。
FIND_SCRIPT = r'''
set -o pipefail
command -v find >/dev/null || exit 127
types=()
case "$3" in
  file) types=(-type f);;
  directory) types=(-type d);;
  *) types=('(' -type f -o -type d ')');;
esac
find "$1" -maxdepth "$4" \( -path /proc -o -path /sys -o -path /dev -o -path /run \) -prune -o "${types[@]}" -iname "$2" -print0 2>/dev/null |
{ n=0; while IFS= read -r -d '' item; do
    printf '%s\0' "$item"
    n=$((n+1))
    if ((n >= $5)); then break; fi
  done
}
status=$?
if ((status == 141)); then exit 0; fi
exit "$status"
'''


class FindPathsArgs(ToolArgs):
    """定义与文件用途无关的 Bash 文件发现范围。"""

    pattern: NonBlank = Field(description="文件或目录名 glob，例如 *mod1*、*.jar、server.properties。")
    root: str = Field(default="", description="可选搜索根目录；不知道位置时留空，使用部署配置的范围。")
    kind: Literal["any", "file", "directory"] = Field(default="any", description="查找文件、目录或两者。")
    max_depth: int = Field(default=8, ge=1, le=32, description="最大搜索深度。")
    max_results: int = Field(default=50, ge=1, le=200, description="最多返回的路径数量。")


def find_paths(args: FindPathsArgs, context: ToolContext) -> ToolResult:
    """用固定 Bash 脚本发现真实路径，并向本轮后续文件工具提供凭据。"""
    roots = [args.root] if args.root else (AGENT_FILE_SEARCH_ROOTS or [str(PROJECT_ROOT) if os.name == "nt" else "/"])
    items = []
    searched = []
    partial = False
    deadline = time.monotonic() + context.timeout_seconds
    try:
        for value in roots:
            root = Path(value).expanduser().resolve(strict=True)
            if not root.is_dir():
                return ToolResult(False, "directory_unavailable", "搜索起点不是可访问目录。")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired("find", context.timeout_seconds)
            result = command.run_bash(FIND_SCRIPT, [root.as_posix(), args.pattern, args.kind, str(args.max_depth), str(args.max_results + 1)], remaining)
            if result.returncode not in (0, 1):
                return ToolResult(False, "search_failed", "Bash 文件查找失败，请检查 Bash 和 find 是否可用。", {"exit_code": result.returncode})
            partial |= result.returncode == 1
            searched.append(str(root))
            for raw in result.stdout.split(b"\0"):
                if not raw:
                    continue
                try:
                    candidate = Path(os.fsdecode(raw))
                    if candidate.is_symlink():
                        continue
                    path = candidate.resolve(strict=True)
                    path.relative_to(root)
                    kind = "directory" if path.is_dir() else "file" if path.is_file() else None
                    item = {"path": str(path), "kind": kind}
                    if kind and (args.kind == "any" or kind == args.kind) and item not in items:
                        items.append(item)
                except (OSError, RuntimeError, ValueError):
                    partial = True
            if len(items) > args.max_results:
                break
    except FileNotFoundError:
        return ToolResult(False, "bash_or_path_unavailable", "Bash 或搜索目录不存在；请检查 AGENT_BASH_PATH 和搜索范围。")
    except subprocess.TimeoutExpired:
        return ToolResult(False, "timeout", "Bash 文件查找超时，请缩小范围或降低搜索深度。", retryable=True)
    except (OSError, RuntimeError, ValueError):
        return ToolResult(False, "search_unavailable", "无法访问搜索范围或启动 Bash。")
    selected = items[:args.max_results]
    context.discovered_paths.update(item["path"] for item in selected)
    return ToolResult(True, message="路径查找完成；未找到时可调整名称、范围或深度。", data={
        "roots": searched, "pattern": args.pattern, "items": selected, "partial": partial,
    }, truncated=partial or len(items) > args.max_results)


TOOLS = (
    ToolSpec("find_server_paths", "通过机器人所在主机的 Bash 按名称发现任意文件或目录，不依赖 MCSM；可先找目录再找配置、脚本、日志等文件。", FindPathsArgs, find_paths, True),
)
