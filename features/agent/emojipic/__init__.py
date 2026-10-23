"""Agent 表情包收藏库的加载、保存与检索接口。"""

from typing import Any

from .library import EmojiLibrary


_LIBRARY = EmojiLibrary()


def load_emoji_library() -> int:
    """在机器人启动时加载同级 emojipic 目录中的索引表。"""
    return _LIBRARY.load()


def save_emoji_image(
    data_url: str,
    category: str,
    name: str,
    tags: list[str],
    source: dict[str, Any],
) -> dict[str, Any]:
    """保存 Agent 当前可见的表情包图片，并返回索引记录。"""
    return _LIBRARY.save(data_url, category, name, tags, source)


def search_emoji_images(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """按表情含义和标签搜索收藏库。"""
    return _LIBRARY.search(query, limit)


__all__ = ["load_emoji_library", "save_emoji_image", "search_emoji_images"]
