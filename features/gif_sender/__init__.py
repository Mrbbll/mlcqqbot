"""GIF 备用发送功能：通过 QQ 分片上传保留动画，复用 BotPy 鉴权。"""

import asyncio
import hashlib
from typing import Any
from urllib.parse import urlsplit

import httpx
from botpy.http import Route


async def _post(api: Any, group_id: str, endpoint: str, payload: dict) -> dict:
    """调用群聊上传接口并拒绝空响应及显式业务失败。"""
    result = await api._http.request(
        Route("POST", "/v2/groups/{group_openid}/" + endpoint, group_openid=group_id),
        json=payload,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"QQ {endpoint} 未返回有效响应")
    code = result.get("code", result.get("err_code", 0))
    if code not in (0, None, "0"):
        raise RuntimeError(f"QQ {endpoint} 失败，错误码 {code}")
    return result.get("data") if isinstance(result.get("data"), dict) else result


async def upload_group_gif(api: Any, group_id: str, content: bytes, file_name: str) -> dict:
    """准备、逐片上传并合并 GIF；失败时抛错，绝不降级为静态图片。"""
    if not content.startswith((b"GIF87a", b"GIF89a")) or len(content) > 20_000_000:
        raise ValueError("备用上传只接受不大于20MB的 GIF")
    prepared = await _post(api, group_id, "upload_prepare", {
        "file_type": 1,
        "file_name": file_name,
        "file_size": len(content),
        "md5": hashlib.md5(content).hexdigest(),
        "sha1": hashlib.sha1(content).hexdigest(),
        "md5_10m": hashlib.md5(content[:10_002_432]).hexdigest(),
    })
    upload_id = prepared.get("upload_id")
    block_size = prepared.get("block_size")
    parts = prepared.get("parts")
    if not upload_id or type(block_size) is not int or block_size <= 0 or not isinstance(parts, list):
        raise RuntimeError("QQ GIF 分片准备响应缺少上传参数")
    expected_count = (len(content) + block_size - 1) // block_size
    if len(parts) != expected_count:
        raise RuntimeError("QQ GIF 分片数量不匹配")
    # 先验证所有分片，避免缺片、重复索引或无效地址导致不完整的上传。
    urls = {}
    for part in parts:
        if not isinstance(part, dict):
            raise RuntimeError("QQ GIF 分片参数无效")
        index = part.get("index")
        url = part.get("presigned_url")
        if (type(index) is not int or not 1 <= index <= expected_count or index in urls
                or not isinstance(url, str) or urlsplit(url).scheme != "https"
                or not urlsplit(url).hostname):
            raise RuntimeError("QQ GIF 分片索引或上传地址无效")
        urls[index] = url

    retry_timeout = min(max(float(prepared.get("retry_timeout") or 30), 1), 120)
    # COS 使用独立客户端，避免将机器人的 Authorization 头发给存储服务。
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        for index in sorted(urls):
            chunk = content[(index - 1) * block_size:index * block_size]
            response = await client.put(urls[index], content=chunk)
            if not 200 <= response.status_code < 300:
                raise RuntimeError(f"QQ GIF 第{index}片上传失败，HTTP {response.status_code}")
            deadline = asyncio.get_running_loop().time() + retry_timeout
            while True:
                try:
                    await _post(api, group_id, "upload_part_finish", {
                        "upload_id": upload_id, "part_index": index,
                        "block_size": len(chunk), "md5": hashlib.md5(chunk).hexdigest(),
                    })
                    break
                except RuntimeError as exc:
                    if "40093001" not in str(exc) or asyncio.get_running_loop().time() >= deadline:
                        raise
                    await asyncio.sleep(1)
    result = await _post(api, group_id, "files", {"upload_id": upload_id})
    if not result.get("file_info"):
        raise RuntimeError("QQ GIF 分片合并未返回 file_info")
    return result
