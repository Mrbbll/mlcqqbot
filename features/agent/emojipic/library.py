"""持久化 Agent 表情包图片，并同步维护 JSON 索引与分类检索。"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT


_log = logging.getLogger("mlcbot")
_MAX_IMAGE_BYTES = 20_000_000
_INDEX_VERSION = 1
_ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class EmojiImageIdAmbiguousError(ValueError):
    """表示同一完整图片 ID 对应多条记录，无法安全删除。"""


def _safe_folder_name(value: str, fallback: str) -> str:
    """将模型提供的分类或图片名限制为安全的短目录名。"""
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._ -]+", "_", str(value or ""))
    cleaned = cleaned.strip(" ._")[:40].strip(" ._")
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in _WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def _decode_image_data_url(data_url: str) -> tuple[bytes, str, str]:
    """解析并验证 Agent 图片输入中的 MIME 类型、内容签名和大小。"""
    header, separator, encoded = str(data_url or "").partition(",")
    if not separator or not header.startswith("data:") or ";base64" not in header:
        raise ValueError("图片输入格式无效")
    mime_type = header[5:].split(";", 1)[0].strip().lower()
    extension = _ALLOWED_MIME_TYPES.get(mime_type)
    if extension is None:
        raise ValueError("图片格式不受支持")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("图片数据不是有效的 Base64") from exc
    if not image_bytes or len(image_bytes) > _MAX_IMAGE_BYTES:
        raise ValueError("图片为空或大于20MB")

    if image_bytes.startswith(b"\xff\xd8\xff"):
        detected_type = "image/jpeg"
    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_type = "image/png"
    elif image_bytes.startswith((b"GIF87a", b"GIF89a")):
        detected_type = "image/gif"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        detected_type = "image/webp"
    else:
        raise ValueError("图片内容签名无效")

    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
    if detected_type != mime_type:
        raise ValueError("图片 MIME 类型与文件内容不匹配")
    return image_bytes, detected_type, _ALLOWED_MIME_TYPES[detected_type]


def _search_terms(value: str) -> set[str]:
    """拆分中英文表情描述，生成轻量关键词集合。"""
    text = str(value or "").casefold()
    terms = set(re.findall(r"[a-z0-9]+", text))
    for phrase in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(phrase) == 1:
            terms.add(phrase)
        else:
            terms.update(phrase[index : index + 2] for index in range(len(phrase) - 1))
            if len(phrase) <= 8:
                terms.add(phrase)
    return terms


class EmojiLibrary:
    """管理同级 emojipic 目录、图片分类和内存索引。"""

    def __init__(self, root: Path | None = None) -> None:
        """初始化收藏库路径和线程安全索引状态。"""
        self.root = root or (PROJECT_ROOT.parent / "emojipic")
        self.index_path = self.root / "index.json"
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = []
        self._loaded = False
        self._load_failed = False

    def load(self) -> int:
        """创建收藏目录并把索引表加载到内存。"""
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            if not self.index_path.exists():
                self._items = []
                self._write_index(self._items)
                self._loaded = True
                self._load_failed = False
                return 0

            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _log.exception("表情包索引表读取失败: path=%s", self.index_path)
                self._loaded = True
                self._load_failed = True
                return 0

            raw_items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(raw_items, list):
                _log.error("表情包索引表格式无效: path=%s", self.index_path)
                self._loaded = True
                self._load_failed = True
                return 0

            self._items = [item for item in raw_items if self._valid_index_item(item)]
            self._loaded = True
            self._load_failed = False
            return len(self._items)

    def save(
        self,
        data_url: str,
        category: str,
        name: str,
        tags: list[str],
        source: dict[str, Any],
    ) -> dict[str, Any]:
        """将一张图片安全写入分类目录，并原子更新索引表。"""
        image_bytes, mime_type, extension = _decode_image_data_url(data_url)
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        category_name = _safe_folder_name(category, "其他")
        image_name = _safe_folder_name(name, "表情包")
        normalized_tags: list[str] = []
        for tag in tags or []:
            if not str(tag or "").strip():
                continue
            normalized_tag = _safe_folder_name(tag, "")
            if normalized_tag and normalized_tag not in normalized_tags:
                normalized_tags.append(normalized_tag)
            if len(normalized_tags) >= 12:
                break

        with self._lock:
            self._ensure_loaded()
            for item in self._items:
                if item.get("sha256") == image_hash:
                    return {**item, "duplicate": True}

            category_dir = self.root / category_name
            category_dir.mkdir(parents=True, exist_ok=True)
            relative_path = Path(category_name) / f"{image_name}_{image_hash[:12]}.{extension}"
            image_path = (self.root / relative_path).resolve()
            if not image_path.is_relative_to(self.root.resolve()):
                raise ValueError("收藏图片路径无效")

            record = {
                "id": image_hash[:16],
                "sha256": image_hash,
                "category": category_name,
                "name": image_name,
                "tags": normalized_tags,
                "file": relative_path.as_posix(),
                "mime_type": mime_type,
                "size": len(image_bytes),
                "source": {
                    "group_id": str(source.get("group_id") or ""),
                    "message_id": str(source.get("message_id") or ""),
                    "user_id": str(source.get("user_id") or ""),
                },
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            self._write_image(image_path, image_bytes)
            updated_items = [*self._items, record]
            try:
                self._write_index(updated_items)
            except OSError:
                image_path.unlink(missing_ok=True)
                raise
            self._items = updated_items
            return {**record, "duplicate": False, "file_path": str(image_path)}

    def search(self, query: str, limit: int = 5, *, gif_only: bool = False,
               exclude_id: str = "") -> list[dict[str, Any]]:
        """按关键词和格式检索；仅限 GIF 或排除旧图时允许空关键词。"""
        normalized_query = str(query or "").strip()
        if not normalized_query and not gif_only and not exclude_id:
            return []
        query_terms = _search_terms(normalized_query)
        with self._lock:
            self._ensure_loaded()
            matches: list[tuple[float, dict[str, Any]]] = []
            for item in self._items:
                if exclude_id and item.get("id") == exclude_id:
                    continue
                if gif_only and Path(str(item.get("file") or "")).suffix.casefold() != ".gif":
                    continue
                searchable = " ".join(
                    [
                        str(item.get("category") or ""),
                        str(item.get("name") or ""),
                        " ".join(str(tag) for tag in item.get("tags", [])),
                    ]
                )
                searchable_terms = _search_terms(searchable)
                overlap = len(query_terms & searchable_terms)
                score = overlap / max(len(query_terms), 1)
                if not normalized_query or normalized_query.casefold() in searchable.casefold():
                    score += 1.0
                if score > 0:
                    matches.append((score, item))

            matches.sort(key=lambda match: (-match[0], match[1].get("saved_at", "")))
            results: list[dict[str, Any]] = []
            for score, item in matches[: max(1, min(limit, 10))]:
                image_path = self._resolve_item_path(item)
                if image_path is not None:
                    results.append({**item, "file_path": str(image_path), "score": score})
            return results

    def list_images(self, page: int = 1, page_size: int = 10, *,
                    gif_only: bool = False, category: str = "") -> dict[str, Any]:
        """分页浏览可用收藏，先按格式与分类过滤，再计算总数和分页。"""
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 20:
            raise ValueError("页码必须为正整数，每页数量必须在1到20之间")
        with self._lock:
            self._ensure_loaded()
            items = []
            for item in self._items:
                if category and item.get("category") != category:
                    continue
                if gif_only and Path(str(item.get("file") or "")).suffix.casefold() != ".gif":
                    continue
                if self._resolve_item_path(item) is not None:
                    items.append(item)
            items.sort(key=lambda item: (item.get("saved_at", ""), item["id"]))
            total = len(items)
            start = (page - 1) * page_size
            return {
                "page": page, "page_size": page_size, "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "has_more": start + page_size < total,
                "items": [dict(item) for item in items[start:start + page_size]],
            }

    def get_image(self, image_id: str) -> dict[str, Any] | None:
        """只按索引中的完整 ID 获取图片，拒绝路径输入和不存在的本地文件。"""
        with self._lock:
            self._ensure_loaded()
            for item in self._items:
                if item.get("id") == image_id:
                    image_path = self._resolve_item_path(item)
                    return {**item, "file_path": str(image_path)} if image_path is not None else None
        return None

    def delete_image(self, image_id: str) -> dict[str, Any] | None:
        """按唯一完整 ID 暂存图片并原子更新索引，失败时尽力恢复原状态。"""
        if not isinstance(image_id, str) or not re.fullmatch(r"[0-9a-f]{16}", image_id):
            raise ValueError("表情包 ID 格式无效")

        with self._lock:
            self._ensure_loaded()
            matches = [item for item in self._items if item.get("id") == image_id]
            if len(matches) > 1:
                raise EmojiImageIdAmbiguousError("表情包 ID 不唯一，拒绝删除")
            if not matches:
                return None

            item = matches[0]
            image_path = self._resolve_item_path(item)
            if image_path is None:
                return None

            original_items = self._items
            updated_items = [entry for entry in original_items if entry is not item]
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".emojipic-delete-",
                suffix=image_path.suffix,
                dir=image_path.parent,
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            image_staged = False
            try:
                os.replace(image_path, temporary_path)
                image_staged = True
                try:
                    self._write_index(updated_items)
                except Exception:
                    try:
                        if image_path.exists():
                            raise FileExistsError("收藏图片原路径已被其他文件占用")
                        os.replace(temporary_path, image_path)
                        image_staged = False
                    except OSError as restore_error:
                        _log.exception("表情包删除时索引写入失败且图片恢复失败: id=%s", image_id)
                        raise RuntimeError("索引写入失败，暂存图片无法恢复，请检查图库目录。") from restore_error
                    raise

                self._items = updated_items
                try:
                    temporary_path.unlink()
                    image_staged = False
                except OSError as cleanup_error:
                    try:
                        if image_path.exists():
                            raise FileExistsError("收藏图片原路径已被其他文件占用")
                        os.replace(temporary_path, image_path)
                        image_staged = False
                        self._write_index(original_items)
                        self._items = original_items
                    except Exception as restore_error:
                        _log.exception("表情包删除清理失败且图库恢复失败: id=%s", image_id)
                        raise RuntimeError("删除清理失败，图库恢复未完成，请检查图库目录。") from restore_error
                    raise RuntimeError("图片清理失败，已恢复收藏索引和图片。") from cleanup_error

                self._remove_empty_category_directory(image_path.parent, image_id)
                return dict(item)
            finally:
                if not image_staged:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        _log.warning("表情包删除临时文件清理失败: id=%s", image_id)

    def _remove_empty_category_directory(self, directory: Path, image_id: str) -> None:
        """图片成功删除后，仅清理图库根目录下已空的分类目录。"""
        category_directory = directory.resolve()
        if category_directory.parent != self.root.resolve():
            return

        try:
            if not any(category_directory.iterdir()):
                category_directory.rmdir()
        except FileNotFoundError:
            return
        except OSError:
            _log.warning(
                "空表情包分类目录清理失败: id=%s path=%s",
                image_id,
                category_directory,
            )

    def _ensure_loaded(self) -> None:
        """确保索引已加载，且不覆盖无法解析的现有索引表。"""
        if not self._loaded:
            self.load()
        if self._load_failed:
            raise RuntimeError("表情包索引表损坏或不可读，已停止写入以保护收藏数据")

    def _valid_index_item(self, item: Any) -> bool:
        """检查索引记录字段与本地图片路径是否有效。"""
        if not isinstance(item, dict):
            return False
        required_text_fields = ("id", "sha256", "category", "name", "file", "saved_at")
        if any(not isinstance(item.get(field), str) for field in required_text_fields):
            return False
        tags = item.get("tags")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            return False
        return self._resolve_item_path(item) is not None

    def _resolve_item_path(self, item: dict[str, Any]) -> Path | None:
        """解析索引中的相对路径并拒绝越出 emojipic 根目录的路径。"""
        try:
            candidate = (self.root / str(item.get("file") or "")).resolve(strict=True)
            if candidate.is_file() and candidate.is_relative_to(self.root.resolve()):
                return candidate
        except (OSError, RuntimeError, ValueError):
            return None
        return None

    def _write_image(self, destination: Path, image_bytes: bytes) -> None:
        """用同目录临时文件写入图片，避免留下不完整收藏文件。"""
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".emojipic-",
                suffix=destination.suffix,
                dir=destination.parent,
                delete=False,
            ) as image_file:
                temporary_path = Path(image_file.name)
                image_file.write(image_bytes)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _write_index(self, items: list[dict[str, Any]]) -> None:
        """原子写入 JSON 索引表，降低程序中断导致索引损坏的概率。"""
        payload = json.dumps(
            {"version": _INDEX_VERSION, "items": items},
            ensure_ascii=False,
            indent=2,
        )
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".index-",
                suffix=".tmp",
                dir=self.root,
                delete=False,
            ) as index_file:
                temporary_path = Path(index_file.name)
                index_file.write(payload)
                index_file.flush()
                os.fsync(index_file.fileno())
            os.replace(temporary_path, self.index_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


__all__ = ["EmojiLibrary"]
