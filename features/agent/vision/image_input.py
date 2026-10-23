"""下载并校验 QQ 图片附件，为 Agent 准备临时多模态输入。"""
from __future__ import annotations

import asyncio
import base64
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
    content_type = _attachment_field(attachment, "content_type") or ""
    return str(content_type).split(";", 1)[0].strip().lower()


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
) -> tuple[list[str], list[str]]:
    """在工作线程中下载图片附件，并返回 data URL 与未处理说明。"""
    image_data_urls: list[str] = []
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
            image_data_urls.append(_download_image(image_url, headers, destination))
        except _ImageTooLarge:
            skipped.append(f"{label}大于20MB，已跳过")
        except (OSError, requests.RequestException, ValueError) as exc:
            _log.warning(
                "Agent 图片附件无法处理: image_index=%s error=%s",
                image_index,
                type(exc).__name__,
            )
            skipped.append(f"{label}下载失败，已跳过")

    return image_data_urls, skipped


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
) -> tuple[list[str], list[str]]:
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
    )
    return downloaded, skipped + download_skips
