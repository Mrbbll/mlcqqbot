"""下载并校验 QQ 图片附件，为 Agent 准备临时多模态输入。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

import requests


_log = logging.getLogger("mlcbot")
_MAX_IMAGE_BYTES = 20_000_000
_IMAGE_MEDIA_HOSTS = {"multimedia.nt.qq.com.cn"}
_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}
_DOWNLOAD_TIMEOUT = (5, 30)
_DOWNLOAD_CHUNK_BYTES = 64 * 1024
_MAX_FORWARD_SCAN_DEPTH = 8
_MAX_FORWARD_SCAN_NODES = 1000
_MAX_EMBEDDED_JSON_BYTES = 1_000_000


class _ImageTooLarge(ValueError):
    """标记图片下载大小超过 Agent 输入上限。"""


def _attachment_field(attachment: Any, name: str) -> Any:
    """兼容 BotPy 附件对象和字典结构，读取指定字段。"""
    if isinstance(attachment, dict):
        return attachment.get(name)
    return getattr(attachment, name, None)


def _image_size(attachment: Any) -> int | None:
    """读取附件声明的字节数，无效值视为未知。"""
    value = _attachment_field(attachment, "size")
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalized_image_type(attachment: Any) -> str:
    """读取并规范化图片 MIME 类型。"""
    content_type = (
        _attachment_field(attachment, "content_type")
        or _attachment_field(attachment, "contentType")
        or ""
    )
    return str(content_type).split(";", 1)[0].strip().lower()


def extract_image_attachments(
    message: Any,
    raw_message_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """提取当前消息和可展开转发载荷中的图片附件元数据。"""
    attachments: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for attachment in getattr(message, "attachments", None) or []:
        _append_image_attachment(attachment, "消息附件", attachments, seen_urls)
    if raw_message_data:
        _extract_quoted_image_attachments(raw_message_data, attachments, seen_urls)
        remaining_nodes = [_MAX_FORWARD_SCAN_NODES]
        _scan_nested_image_attachments(
            raw_message_data,
            "",
            False,
            False,
            0,
            remaining_nodes,
            attachments,
            seen_urls,
        )
    return attachments


def _extract_quoted_image_attachments(
    raw_message_data: dict[str, Any],
    attachments: list[dict[str, Any]],
    seen_urls: set[str],
) -> None:
    """读取 QQ message_type=103 引用元素直接携带的图片附件。"""
    elements = (
        raw_message_data.get("msg_elements")
        or raw_message_data.get("msgElements")
        or []
    )
    if not isinstance(elements, (list, tuple)):
        return
    top_level_type = str(
        raw_message_data.get("message_type")
        or raw_message_data.get("messageType")
        or ""
    )
    for element in elements[:20]:
        if not isinstance(element, dict):
            continue
        element_type = str(
            element.get("message_type")
            or element.get("messageType")
            or top_level_type
        )
        if element_type != "103":
            continue
        quoted_attachments = element.get("attachments") or []
        if not isinstance(quoted_attachments, (list, tuple)):
            continue
        for attachment in quoted_attachments[:20]:
            _append_image_attachment(attachment, "引用消息图片", attachments, seen_urls)


def _append_image_attachment(
    attachment: Any,
    source: str,
    attachments: list[dict[str, Any]],
    seen_urls: set[str],
) -> None:
    """规范化图片附件字段并按 URL 去重。"""
    content_type = _normalized_image_type(attachment)
    if not content_type.startswith("image/"):
        return
    url = _attachment_field(attachment, "url")
    normalized_url = str(url or "").strip()
    dedupe_key = normalized_url or (
        f"{content_type}:{_attachment_field(attachment, 'filename') or ''}:{_image_size(attachment)}"
    )
    if dedupe_key in seen_urls:
        return
    seen_urls.add(dedupe_key)
    attachments.append(
        {
            "url": normalized_url,
            "content_type": content_type,
            "filename": str(_attachment_field(attachment, "filename") or ""),
            "size": _image_size(attachment),
            "source": source,
            "relation": "引用消息" if source == "引用消息图片" else "",
        }
    )


def _scan_nested_image_attachments(
    value: Any,
    parent_key: str,
    inside_forward: bool,
    inside_image: bool,
    depth: int,
    remaining_nodes: list[int],
    attachments: list[dict[str, Any]],
    seen_urls: set[str],
) -> None:
    """有界遍历原始事件中的转发节点和 JSON 卡片，收集其中显式标注的图片。"""
    if depth > _MAX_FORWARD_SCAN_DEPTH or remaining_nodes[0] <= 0:
        return
    remaining_nodes[0] -= 1
    if isinstance(value, dict):
        content_type = str(value.get("content_type") or value.get("contentType") or "")
        node_type = str(
            value.get("type") or value.get("element_type") or value.get("kind") or ""
        ).casefold()
        is_image_node = (
            inside_image
            or node_type in {"image", "img"}
            or "image" in parent_key.casefold()
        )
        image_url = value.get("url") or value.get("image_url") or value.get("src")
        if content_type.casefold().startswith("image/") or (
            inside_forward and is_image_node and image_url
        ):
            attachment_data = value
            if not content_type.casefold().startswith("image/"):
                attachment_data = {**value, "url": image_url, "content_type": "image/jpeg"}
            _append_image_attachment(
                attachment_data,
                "转发消息图片" if inside_forward else "消息附件",
                attachments,
                seen_urls,
            )
        for key, nested_value in value.items():
            normalized_key = str(key).casefold()
            nested_forward = inside_forward or any(
                marker in normalized_key
                for marker in ("forward", "node", "message_chain")
            )
            _scan_nested_image_attachments(
                nested_value,
                normalized_key,
                nested_forward,
                is_image_node or "image" in normalized_key,
                depth + 1,
                remaining_nodes,
                attachments,
                seen_urls,
            )
        return
    if isinstance(value, (list, tuple)):
        for nested_value in value:
            _scan_nested_image_attachments(
                nested_value,
                parent_key,
                inside_forward,
                inside_image,
                depth + 1,
                remaining_nodes,
                attachments,
                seen_urls,
            )
        return
    if isinstance(value, str) and inside_forward and inside_image and value.startswith("https://"):
        _append_image_attachment(
            {"url": value, "content_type": "image/jpeg"},
            "转发消息图片",
            attachments,
            seen_urls,
        )
        return
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")) and len(
        value.encode("utf-8", errors="ignore")
    ) <= _MAX_EMBEDDED_JSON_BYTES:
        try:
            nested_data = json.loads(value)
        except json.JSONDecodeError:
            return
        _scan_nested_image_attachments(
            nested_data,
            parent_key,
            inside_forward or "forward" in parent_key.casefold(),
            inside_image,
            depth + 1,
            remaining_nodes,
            attachments,
            seen_urls,
        )


def _validate_image_url(value: Any) -> str:
    """只接受 QQ 图片 CDN 的 HTTPS 地址，避免下载任意目标。"""
    if not isinstance(value, str) or not value:
        raise ValueError("missing image URL")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid image URL port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _IMAGE_MEDIA_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError("image URL is outside the QQ media host")
    return value


def _detect_image_type(content: bytes) -> str | None:
    """根据文件签名确认图片类型，拒绝伪装成图片的其他内容。"""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _download_image(url: str, headers: dict[str, str], destination: Path) -> str:
    """流式下载一张图片到临时文件并返回 base64 data URL。"""
    try:
        with requests.get(
            url,
            headers=headers,
            timeout=_DOWNLOAD_TIMEOUT,
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                response.raise_for_status()
                raise requests.RequestException("QQ 图片 CDN returned a non-200 status")

            content_length = response.headers.get("Content-Length")
            try:
                declared_length = int(content_length) if content_length else None
            except ValueError:
                declared_length = None
            if declared_length is not None and declared_length > _MAX_IMAGE_BYTES:
                raise _ImageTooLarge("declared image size exceeds limit")

            downloaded_bytes = 0
            with destination.open("wb") as image_file:
                for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                    if not chunk:
                        continue
                    if downloaded_bytes + len(chunk) > _MAX_IMAGE_BYTES:
                        raise _ImageTooLarge("downloaded image size exceeds limit")
                    image_file.write(chunk)
                    downloaded_bytes += len(chunk)

        if downloaded_bytes == 0:
            raise ValueError("empty image response")
        image_bytes = destination.read_bytes()
        detected_type = _detect_image_type(image_bytes)
        if detected_type not in _IMAGE_TYPES:
            raise ValueError("unsupported image content")
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{detected_type};base64,{encoded_image}"
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _download_images_sync(
    attachments: Iterable[Any],
    authorization: str,
    cache_directory: Path,
    group_id: str,
) -> tuple[list[dict[str, str]], list[str]]:
    """在线程中下载图片，保留来源说明并返回未处理提示。"""
    image_inputs: list[dict[str, str]] = []
    skipped: list[str] = []
    image_index = 0
    headers = {"Authorization": authorization}

    for attachment in attachments:
        content_type = _normalized_image_type(attachment)
        if not content_type.startswith("image/"):
            continue
        image_index += 1
        label = f"第{image_index}张图片"
        if content_type not in _IMAGE_TYPES:
            skipped.append(f"{label}格式暂不支持，已跳过")
            continue
        declared_size = _image_size(attachment)
        if declared_size is not None and declared_size > _MAX_IMAGE_BYTES:
            skipped.append(f"{label}大于20MB，已跳过")
            continue

        extension = _IMAGE_TYPES[content_type]
        destination = cache_directory / f"image_{image_index}.{extension}"
        try:
            image_url = _validate_image_url(_attachment_field(attachment, "url"))
            image_data_url = _download_image(image_url, headers, destination)
            image_inputs.append(
                {
                    "data_url": image_data_url,
                    "description": _image_description(attachment),
                    "source_group_id": group_id,
                    "source_message_id": str(
                        _attachment_field(attachment, "message_id") or ""
                    ),
                    "source_user_id": str(
                        _attachment_field(attachment, "user_id") or ""
                    ),
                }
            )
        except _ImageTooLarge:
            skipped.append(f"{label}大于20MB，已跳过")
        except (OSError, requests.RequestException, ValueError) as exc:
            _log.warning(
                "Agent 图片附件无法处理: image_index=%s error=%s",
                image_index,
                type(exc).__name__,
            )
            skipped.append(f"{label}下载失败，已跳过")

    return image_inputs, skipped


def _image_description(attachment: Any) -> str:
    """为图片输入生成不含下载地址的消息来源说明。"""
    fields = (
        ("消息关系", _attachment_field(attachment, "relation")),
        ("图片来源", _attachment_field(attachment, "source")),
        ("发送者", _attachment_field(attachment, "user_id")),
        ("消息", _attachment_field(attachment, "message_id")),
        ("消息文字", _attachment_field(attachment, "message_content")),
        ("文件名", _attachment_field(attachment, "filename")),
    )
    return "；".join(
        f"{label}：{str(value).strip()}"
        for label, value in fields
        if value is not None and str(value).strip()
    ) or "来源：群消息图片"


async def _qq_media_authorization(api: Any) -> str | None:
    """从 BotPy API 刷新并读取 QQ 媒体 CDN 所需的授权头。"""
    http_client = getattr(api, "_http", None)
    check_session = getattr(http_client, "check_session", None)
    if not callable(check_session):
        return None
    await check_session()
    headers = getattr(http_client, "_headers", None)
    authorization = headers.get("Authorization") if isinstance(headers, dict) else None
    if isinstance(authorization, str) and authorization.startswith("QQBot "):
        return authorization
    return None


async def download_image_attachments(
    attachments: Iterable[Any],
    api: Any,
    cache_directory: Path,
    *,
    group_id: str = "",
) -> tuple[list[dict[str, str]], list[str]]:
    """下载支持的 QQ 图片附件到给定临时目录，并限制每张不超过20MB。"""
    attachment_list = list(attachments or [])
    image_attachments = [
        attachment
        for attachment in attachment_list
        if _normalized_image_type(attachment).startswith("image/")
    ]
    if not image_attachments:
        return [], []

    skipped: list[str] = []
    downloadable: list[Any] = []
    for image_index, attachment in enumerate(image_attachments, start=1):
        content_type = _normalized_image_type(attachment)
        if content_type not in _IMAGE_TYPES:
            skipped.append(f"第{image_index}张图片格式暂不支持，已跳过")
            continue
        declared_size = _image_size(attachment)
        if declared_size is not None and declared_size > _MAX_IMAGE_BYTES:
            skipped.append(f"第{image_index}张图片大于20MB，已跳过")
            continue
        downloadable.append(attachment)
    if not downloadable:
        return [], skipped

    try:
        authorization = await _qq_media_authorization(api)
    except Exception as exc:
        _log.warning("Agent 图片附件授权获取失败: error=%s", type(exc).__name__)
        authorization = None
    if authorization is None:
        skipped.append("图片下载授权获取失败，未向模型发送图片")
        return [], skipped

    loop = asyncio.get_running_loop()
    downloaded, download_skips = await loop.run_in_executor(
        None,
        _download_images_sync,
        downloadable,
        authorization,
        cache_directory,
        group_id,
    )
    return downloaded, skipped + download_skips
