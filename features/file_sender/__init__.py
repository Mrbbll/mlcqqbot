"""将有界本地文件上传并发送到当前 QQ 群，不通过外部文件托管。"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from botpy.http import Route
from config import AGENT_TOOL_TIMEOUT_SECONDS


MAX_FILE_BYTES = 20_000_000
SENSITIVE_FILENAMES = {"config.py", ".env"}


def api_integer(value: Any) -> int:
    """兼容协议中的整数及十进制数字字符串，拒绝布尔、浮点和负数。"""
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 20:
        return int(value)
    return 0


def validate_file(path_value: str | Path) -> Path:
    """校验原始与规范文件名、普通文件类型及有界文件大小。"""
    candidate = Path(path_value).expanduser()
    path = candidate.resolve(strict=True)
    if candidate.name.casefold() in SENSITIVE_FILENAMES or path.name.casefold() in SENSITIVE_FILENAMES:
        raise ValueError("敏感配置文件不允许发送。")
    if not path.is_file():
        raise ValueError("只能发送普通文件，目录请先选择具体文件。")
    if not 0 < path.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("文件为空或超过 20 MB，不能发送。")
    return path


def read_file_bytes(path_value: str | Path) -> tuple[Path, bytes]:
    """发送时重新校验并有界读取，防止排队后文件增长造成无界读取。"""
    path = validate_file(path_value)
    with path.open("rb") as source:
        content = source.read(MAX_FILE_BYTES + 1)
    if not 0 < len(content) <= MAX_FILE_BYTES:
        raise ValueError("文件为空或超过 20 MB，不能发送。")
    return path, content


def checked_response(result: Any) -> dict:
    """拒绝空响应及 HTTP 成功但业务失败的接口结果。"""
    if not isinstance(result, dict):
        raise RuntimeError("QQ 文件接口未返回有效响应。")
    code = result.get("code", result.get("err_code", 0))
    if code not in (0, None, "0"):
        raise RuntimeError(f"QQ 文件接口拒绝请求，错误码 {code}。")
    return result.get("data") if isinstance(result.get("data"), dict) else result


async def post_upload(api: Any, group_id: str, endpoint: str, payload: dict) -> dict:
    """使用机器人鉴权调用上传控制接口，不向存储服务发送该鉴权。"""
    return checked_response(await api._http.request(
        Route("POST", "/v2/groups/{group_openid}/" + endpoint, group_openid=group_id), json=payload,
    ))


async def upload_file(api: Any, group_id: str, path: Path, content: bytes) -> str:
    """按腾讯本地文件流程申请、上传并合并所有分片，保留原始文件名。"""
    prepared = await post_upload(api, group_id, "upload_prepare", {
        "file_type": 4, "file_name": path.name, "file_size": len(content),
        "md5": hashlib.md5(content).hexdigest(), "sha1": hashlib.sha1(content).hexdigest(),
        "md5_10m": hashlib.md5(content[:10_002_432]).hexdigest(),
    })
    if isinstance(prepared.get("file_info"), str) and prepared["file_info"]:
        return prepared["file_info"]
    upload_id = prepared.get("upload_id")
    block_size = api_integer(prepared.get("block_size"))
    parts = prepared.get("parts")
    if not isinstance(upload_id, str) or not upload_id or type(block_size) is not int or block_size <= 0 or not isinstance(parts, list):
        shape = {key: type(prepared[key]).__name__ for key in ("upload_id", "block_size", "parts", "file_info") if key in prepared}
        logging.getLogger("mlcbot").warning("QQ upload_prepare 响应结构异常: fields=%s types=%s", sorted(str(key)[:64] for key in prepared)[:30], shape)
        raise RuntimeError("QQ 文件上传缺少有效分片参数，请查看 upload_prepare 响应结构诊断。")
    count = (len(content) + block_size - 1) // block_size
    if len(parts) != count:
        raise RuntimeError("QQ 文件上传分片数量不匹配。")
    urls = {}
    for part in parts:
        index = api_integer(part.get("index")) if isinstance(part, dict) else None
        url = part.get("presigned_url") if isinstance(part, dict) else None
        if (type(index) is not int or not 1 <= index <= count or index in urls
                or not isinstance(url, str) or urlsplit(url).scheme != "https" or not urlsplit(url).hostname):
            raise RuntimeError("QQ 文件上传分片索引或地址无效。")
        expected = min(block_size, len(content) - (index - 1) * block_size)
        part_size = api_integer(part.get("block_size", expected))
        if part_size not in (0, expected, block_size):
            raise RuntimeError("QQ 文件上传分片长度不匹配。")
        urls[index] = url
    # 独立客户端只向平台返回的预签名地址 PUT，不携带机器人认证头。
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        for index in sorted(urls):
            chunk = content[(index - 1) * block_size:index * block_size]
            response = await client.put(urls[index], content=chunk)
            response.raise_for_status()
            deadline = asyncio.get_running_loop().time() + 30
            while True:
                try:
                    await post_upload(api, group_id, "upload_part_finish", {
                        "upload_id": upload_id, "part_index": index,
                        "block_size": len(chunk), "md5": hashlib.md5(chunk).hexdigest(),
                    })
                    break
                except RuntimeError as exc:
                    if "40093001" not in str(exc) or asyncio.get_running_loop().time() >= deadline:
                        raise
                    await asyncio.sleep(1)
    merged = await post_upload(api, group_id, "files", {"upload_id": upload_id})
    file_info = merged.get("file_info")
    if not isinstance(file_info, str) or not file_info:
        raise RuntimeError("QQ 文件合并未返回 file_info。")
    return file_info


async def send_group_file(api: Any, group_id: str, file_path: str | Path, message_id: str, *, message_sequence: int = 1) -> Any:
    """限制整次上传和发送时长；发送完成状态未确认时不自动重发。"""
    return await asyncio.wait_for(
        _send_group_file(api, group_id, file_path, message_id, message_sequence),
        timeout=AGENT_TOOL_TIMEOUT_SECONDS,
    )


async def _send_group_file(api: Any, group_id: str, file_path: str | Path, message_id: str, message_sequence: int) -> Any:
    """上传普通文件后发送引用，仅消息接口返回确认 ID 后视为成功。"""
    if not group_id or not message_id:
        raise ValueError("文件发送需要当前群及原始消息 ID。")
    path, content = await asyncio.to_thread(read_file_bytes, file_path)
    file_info = await upload_file(api, group_id, path, content)
    result = await api.post_group_message(
        group_openid=group_id, msg_type=7, content=" ", media={"file_info": file_info},
        msg_id=message_id, msg_seq=message_sequence,
    )
    if not checked_response(result).get("id"):
        raise RuntimeError("QQ 消息接口未返回确认 ID，文件送达状态未知。")
    return result
