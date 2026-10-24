"""向 Agent 提供收藏目录的分页浏览和公开图片摘要，不暴露存储路径。"""

import json
from pathlib import Path
from typing import Any

from features.agent.emojipic import list_emoji_images


def emoji_summary(item: dict[str, Any]) -> dict[str, Any]:
    """仅返回模型选择图片所需的 ID、分类、名称、标签和文件格式。"""
    return {
        "id": item["id"], "category": item["category"], "name": item["name"],
        "tags": item.get("tags", []), "format": Path(item["file"]).suffix.lstrip(".").lower(),
    }


def list_emoji_tool_result(arguments: dict[str, Any]) -> str:
    """校验分页及筛选参数，返回包含总数和翻页信息的目录摘要。"""
    page = arguments.get("page", 1)
    page_size = arguments.get("page_size", 10)
    gif_only = arguments.get("gif_only", False)
    category = arguments.get("category", "")
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 20:
        return "浏览失败：页码必须为正整数，每页数量必须在1到20之间。"
    if not isinstance(gif_only, bool) or not isinstance(category, str):
        return "浏览失败：gif_only 必须是布尔值，category 必须是字符串。"
    try:
        result = list_emoji_images(page, page_size, gif_only=gif_only, category=category.strip())
    except (OSError, RuntimeError, ValueError):
        return "浏览失败：收藏索引暂时不可用。"
    return json.dumps({**result, "items": [emoji_summary(item) for item in result["items"]]}, ensure_ascii=False)
