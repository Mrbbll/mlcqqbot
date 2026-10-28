"""Agent 表情包收藏库的加载、保存、检索与删除接口。"""

from typing import Any

from .library import EmojiImageIdAmbiguousError, EmojiLibrary


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


def search_emoji_images(query: str, limit: int = 5, *, gif_only: bool = False,
                        exclude_id: str = "") -> list[dict[str, Any]]:
    """按表情含义和格式检索，可排除刚发送的表情包。"""
    return _LIBRARY.search(query, limit, gif_only=gif_only, exclude_id=exclude_id)


def list_emoji_images(page: int = 1, page_size: int = 10, *,
                      gif_only: bool = False, category: str = "") -> dict[str, Any]:
    """分页浏览收藏库，支持 GIF 和分类筛选。"""
    return _LIBRARY.list_images(page, page_size, gif_only=gif_only, category=category)


def get_emoji_image(image_id: str) -> dict[str, Any] | None:
    """按收藏 ID 获取图片及其安全解析后的发送路径。"""
    return _LIBRARY.get_image(image_id)


def delete_emoji_image(image_id: str) -> dict[str, Any] | None:
    """按完整收藏 ID 删除图片文件和对应索引记录。"""
    return _LIBRARY.delete_image(image_id)


__all__ = [
    "EmojiLibrary",
    "EmojiImageIdAmbiguousError",
    "load_emoji_library",
    "save_emoji_image",
    "search_emoji_images",
    "list_emoji_images",
    "get_emoji_image",
    "delete_emoji_image",
]
