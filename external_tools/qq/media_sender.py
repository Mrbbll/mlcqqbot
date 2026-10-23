"""BotPy 群聊富媒体图片发送适配器。"""

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from botpy.http import Route
from PIL import Image


_MAX_IMAGE_BYTES = 20_000_000


def _prepare_qq_image(image_bytes: bytes, image_path: Path) -> bytes:
    """保留 PNG/JPEG 原图，并将 GIF/WebP 转成 QQ 支持的 PNG 首帧。"""
    if image_path.suffix.casefold() in {".png", ".jpg", ".jpeg"}:
        return image_bytes

    with Image.open(BytesIO(image_bytes)) as source:
        source.seek(0)
        has_alpha = "A" in source.getbands() or "transparency" in source.info
        frame = source.convert("RGBA" if has_alpha else "RGB")
        output = BytesIO()
        frame.save(output, format="PNG", optimize=True)
        return output.getvalue()


async def send_group_image(
    api: Any,
    group_id: str,
    image_path: str | Path,
    message_id: str,
    *,
    message_sequence: int = 1,
) -> None:
    """将本地表情图片上传到 QQ 群并发送为富媒体回复。"""
    image_file = Path(image_path).resolve(strict=True)
    if not image_file.is_file():
        raise ValueError("表情包路径不是文件")
    image_bytes = image_file.read_bytes()
    if not image_bytes or len(image_bytes) > _MAX_IMAGE_BYTES:
        raise ValueError("表情包为空或大于20MB")
    image_bytes = _prepare_qq_image(image_bytes, image_file)
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise ValueError("转换后的表情包大于20MB")

    upload_route = Route(
        "POST",
        "/v2/groups/{group_openid}/files",
        group_openid=group_id,
    )
    upload_result = await api._http.request(
        upload_route,
        json={
            "file_type": 1,
            "file_data": base64.b64encode(image_bytes).decode("ascii"),
            "srv_send_msg": False,
        },
    )
    file_info = upload_result.get("file_info") if isinstance(upload_result, dict) else None
    if not file_info:
        raise RuntimeError("QQ 图片上传接口没有返回 file_info")

    await api.post_group_message(
        group_openid=group_id,
        msg_type=7,
        media={"file_info": file_info},
        msg_id=message_id or None,
        msg_seq=message_sequence,
    )


__all__ = ["send_group_image"]
