"""为表情包工具提供公开图片摘要，不暴露存储路径。"""

from pathlib import Path
from typing import Any



def emoji_summary(item: dict[str, Any]) -> dict[str, Any]:
    """仅返回模型选择图片所需的 ID、分类、名称、标签和文件格式。"""
    return {
        "id": item["id"], "category": item["category"], "name": item["name"],
        "tags": item.get("tags", []), "format": Path(item["file"]).suffix.lstrip(".").lower(),
    }
