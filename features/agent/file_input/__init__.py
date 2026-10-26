"""提取和有界读取 QQ 文本文件附件，附件内容始终作为不可信输入。"""

from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx

from features.agent.tools.filesystem import decode_text


MAX_FILE_BYTES = 1024 * 1024
MAX_INPUT_CHARS = 16000
TEXT_SUFFIXES = {".txt", ".log", ".md", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".properties", ".py", ".js", ".ts", ".sh", ".java", ".c", ".cpp", ".h", ".sql"}
MEDIA_HOST = "multimedia.nt.qq.com.cn"
FILE_MEDIA_HOST = "grouptalk.c2c.qq.com"


def field(value: Any, name: str) -> Any:
    """兼容 BotPy 附件对象和原始字典字段。"""
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def extract_file_attachments(message: Any, raw: dict | None = None) -> list[dict]:
    """提取消息和平台附带引用消息中的普通附件，不扫描任意嵌套文本。"""
    candidates = list(getattr(message, "attachments", None) or [])
    if raw:
        candidates.extend(raw.get("attachments") or [])
        for element in (raw.get("msg_elements") or [])[:10]:
            if isinstance(element, dict):
                candidates.extend(element.get("attachments") or [])
    results = []
    seen = set()
    for item in candidates:
        content_type = str(field(item, "content_type") or "").split(";", 1)[0].lower()
        if content_type.startswith(("image/", "audio/", "video/")):
            continue
        url = str(field(item, "url") or "")
        name = str(field(item, "filename") or "附件")[:200]
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({"url": url, "filename": name, "content_type": content_type,
                        "size": field(item, "size")})
        if len(results) >= 5:
            break
    return results


def validated_url(value: str) -> str:
    """只下载 QQ 图片或群文件 CDN 地址，不跟随重定向。"""
    url = "https:" + value if value.startswith("//") else value
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {MEDIA_HOST, FILE_MEDIA_HOST}
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("附件地址不是支持的 QQ 媒体 CDN")
    return url


async def read_file_attachments(attachments: list[dict], api: Any) -> tuple[list[dict], list[str]]:
    """最多读取三个文本附件，限制单文件下载和总输入量，不保存下载凭证。"""
    inputs, skipped = [], []
    if not attachments:
        return inputs, skipped
    authorization = None
    http = getattr(api, "_http", None)
    if callable(getattr(http, "check_session", None)):
        try:
            await http.check_session()
            headers = getattr(http, "_headers", {})
            value = headers.get("Authorization") if isinstance(headers, dict) else None
            if isinstance(value, str) and value.startswith("QQBot "):
                authorization = value
        except Exception:
            pass
    headers = {"Authorization": authorization} if authorization else {}
    remaining = MAX_INPUT_CHARS
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        for attachment in attachments[:3]:
            name = str(attachment.get("filename") or "附件")[:200]
            try:
                suffix = PurePosixPath(name.replace("\\", "/")).suffix.lower()
                mime = str(attachment.get("content_type") or "")
                if suffix not in TEXT_SUFFIXES and not mime.startswith("text/"):
                    raise ValueError("暂不支持此文件格式，仅支持文本、日志和代码等文本文件")
                if PurePosixPath(name.replace("\\", "/")).name.casefold() in {".env", "config.py"}:
                    raise ValueError("敏感配置附件不发送给模型")
                declared = attachment.get("size")
                if declared is not None and int(declared) > MAX_FILE_BYTES:
                    raise ValueError("附件超过 1 MiB 读取上限")
                url = validated_url(str(attachment.get("url") or ""))
                # 不把图片 CDN 的 QQBot 凭证转发到群文件 CDN。
                request_headers = headers if urlsplit(url).hostname == MEDIA_HOST else {}
                data = bytearray()
                async with client.stream("GET", url, headers=request_headers) as response:
                    if response.status_code != 200:
                        raise ValueError(f"附件下载失败，HTTP {response.status_code}")
                    if int(response.headers.get("Content-Length", "0")) > MAX_FILE_BYTES:
                        raise ValueError("附件超过 1 MiB 读取上限")
                    async for chunk in response.aiter_bytes(65536):
                        if len(data) + len(chunk) > MAX_FILE_BYTES:
                            raise ValueError("附件超过 1 MiB 读取上限")
                        data.extend(chunk)
                text = decode_text(bytes(data))
                if text is None:
                    raise ValueError("附件不是可识别编码的文本")
                limit = min(8000, remaining)
                inputs.append({"filename": name, "message_id": str(attachment.get("message_id") or ""),
                               "content": text[:limit], "truncated": len(text) > limit})
                remaining -= min(len(text), limit)
                if remaining <= 0:
                    break
            except (ValueError, TypeError, httpx.HTTPError) as exc:
                reason = str(exc) if isinstance(exc, ValueError) and not str(exc).startswith("invalid literal") else "附件下载或元数据解析失败"
                skipped.append(f"{name}：{reason[:150]}")
    if len(attachments) > 3:
        skipped.append("本轮最多读取三个附件，其余未读取")
    return inputs, skipped
