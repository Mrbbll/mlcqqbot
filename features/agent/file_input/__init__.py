"""提取和有界读取 QQ 文本文件附件，附件内容始终作为不可信输入。"""

import logging
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx

from features.agent.tools.filesystem import decode_text


MAX_FILE_BYTES = 1024 * 1024
MAX_INPUT_CHARS = MAX_FILE_BYTES
TEXT_SUFFIXES = {".txt", ".log", ".md", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".properties", ".py", ".js", ".ts", ".sh", ".java", ".c", ".cpp", ".h", ".sql"}
MEDIA_HOST = "multimedia.nt.qq.com.cn"
FILE_MEDIA_HOST = "grouptalk.c2c.qq.com"
FTN_FILE_MEDIA_HOST = "gzc-download.ftn.qq.com"
_log = logging.getLogger("mlcbot")


def field(value: Any, name: str) -> Any:
    """兼容 BotPy 附件对象和原始字典字段。"""
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def extract_file_attachments(message: Any, raw: dict | None = None) -> list[dict]:
    """提取消息和平台附带引用消息中的普通附件，不扫描任意嵌套文本。"""
    quoted_candidates = []
    element_candidates = []
    if raw:
        elements = (raw.get("msg_elements") or [])[:10]
        for element in elements:
            if isinstance(element, dict):
                element_type = str(
                    element.get("message_type")
                    or element.get("messageType")
                    or raw.get("message_type")
                    or raw.get("messageType")
                    or ""
                )
                is_quoted = element_type == "103"
                target = quoted_candidates if is_quoted else element_candidates
                target.extend(
                    (
                        item,
                        "引用消息附件" if is_quoted else "消息附件",
                        "引用消息" if is_quoted else "当前消息",
                    )
                    for item in element.get("attachments") or []
                )
    candidates = quoted_candidates + [
        (item, "消息附件", "当前消息")
        for item in getattr(message, "attachments", None) or []
    ]
    if raw:
        candidates.extend(
            (item, "消息附件", "当前消息")
            for item in raw.get("attachments") or []
        )
    candidates.extend(element_candidates)
    results = []
    seen = set()
    for item, source, relation in candidates:
        content_type = str(field(item, "content_type") or "").split(";", 1)[0].lower()
        if content_type.startswith(("image/", "audio/", "video/")):
            continue
        url = str(field(item, "url") or "")
        name = str(field(item, "filename") or "附件")[:200]
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "url": url,
            "filename": name,
            "content_type": content_type,
            "size": field(item, "size"),
            "source": source,
            "relation": relation,
            "source_message_id": str(
                field(item, "source_message_id") or field(item, "message_id") or ""
            ),
            "source_user_id": str(
                field(item, "source_user_id") or field(item, "user_id") or ""
            ),
        })
        if len(results) >= 5:
            break
    return results


def _log_invalid_url(value: str) -> None:
    """仅记录地址格式和主机信息，避免泄露路径、参数和凭证。"""
    try:
        url = "https:" + value if value.startswith("//") else value
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if not parsed.scheme and not parsed.netloc and not url.startswith("/"):
            host = urlsplit("//" + url).hostname or ""
        host = host if re.fullmatch(r"[a-z0-9.-]{1,253}", host) else "none_or_invalid"
        scheme = parsed.scheme if parsed.scheme in {"http", "https", "file"} else ("none" if not parsed.scheme else "other")
        try:
            port = parsed.port
            port_status = "default" if port is None else ("443" if port == 443 else "other")
        except ValueError:
            port_status = "invalid"
        _log.warning(
            "Agent 文件地址校验失败: scheme=%s host=%s port=%s has_userinfo=%s",
            scheme, host, port_status, parsed.username is not None or parsed.password is not None,
        )
    except ValueError:
        _log.warning("Agent 文件地址校验失败: scheme=invalid host=none_or_invalid port=invalid has_userinfo=unknown")


def validated_url(value: str) -> str:
    """只下载 QQ 图片或群文件 CDN 地址，不跟随重定向。"""
    url = "https:" + value if value.startswith("//") else value
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        _log_invalid_url(value)
        raise ValueError("附件地址不是支持的 QQ 媒体 CDN") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {MEDIA_HOST, FILE_MEDIA_HOST, FTN_FILE_MEDIA_HOST}
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        _log_invalid_url(value)
        raise ValueError("附件地址不是支持的 QQ 媒体 CDN")
    return url


async def read_file_attachments(attachments: list[dict], api: Any) -> tuple[list[dict], list[str]]:
    """最多读取三个文本附件，单文件与总输入均限制为 1 MiB，不保存下载凭证。"""
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
                        _log.warning("Agent 文件下载失败: HTTP %s", response.status_code)
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
                limit = min(len(text), remaining)
                source_message_id = str(
                    attachment.get("source_message_id") or attachment.get("message_id") or ""
                )
                source_user_id = str(
                    attachment.get("source_user_id") or attachment.get("user_id") or ""
                )
                inputs.append({
                    "filename": name,
                    "message_id": source_message_id,
                    "user_id": source_user_id,
                    "source_message_id": source_message_id,
                    "source_user_id": source_user_id,
                    "relation": str(attachment.get("relation") or "来源未知"),
                    "carrier_message_id": str(attachment.get("carrier_message_id") or ""),
                    "carrier_user_id": str(attachment.get("carrier_user_id") or ""),
                    "quoted_by_user_id": str(attachment.get("quoted_by_user_id") or ""),
                    "content": text[:limit],
                    "truncated": len(text) > limit,
                })
                remaining -= min(len(text), limit)
                if remaining <= 0:
                    break
            except (ValueError, TypeError, httpx.HTTPError) as exc:
                reason = str(exc) if isinstance(exc, ValueError) and not str(exc).startswith("invalid literal") else "附件下载或元数据解析失败"
                skipped.append(f"{name}：{reason[:150]}")
    if len(attachments) > 3:
        skipped.append("本轮最多读取三个附件，其余未读取")
    return inputs, skipped
