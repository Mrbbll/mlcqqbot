"""GIF 发送功能回归测试：验证动画字节、备用切换和分片完整性。"""

import base64
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from botpy.errors import AuthenticationFailedError, ServerError
from PIL import Image

from features.gif_sender import upload_group_gif
from external_tools.qq.media_sender import send_group_image


def animated_gif() -> bytes:
    """生成有两帧、不同帧时长及循环信息的真实 GIF。"""
    output = BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        output, format="GIF", save_all=True,
        append_images=[Image.new("RGB", (4, 4), "blue")], duration=[80, 160], loop=0,
    )
    return output.getvalue()


def fake_api(results) -> SimpleNamespace:
    """提供可记录调用顺序的 BotPy 接口替身。"""
    return SimpleNamespace(
        _http=SimpleNamespace(request=AsyncMock(side_effect=results)),
        post_group_message=AsyncMock(),
    )


class GifSendTests(unittest.IsolatedAsyncioTestCase):
    """覆盖现有表情包发送入口的动图和失败行为。"""

    async def test_original_animation_is_uploaded(self):
        """验证上传与原文件逐字节一致，且保留循环、时长和两帧。"""
        content = animated_gif()
        api = fake_api([{"file_info": "original"}])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            path.write_bytes(content)
            await send_group_image(api, "group", path, "message", message_sequence=2)
        payload = api._http.request.call_args.kwargs["json"]
        uploaded = base64.b64decode(payload["file_data"])
        self.assertEqual(uploaded, content)
        with Image.open(BytesIO(uploaded)) as image:
            self.assertEqual(image.n_frames, 2)
            self.assertEqual(image.info["loop"], 0)
            self.assertEqual(image.info["duration"], 80)
            image.seek(1)
            self.assertEqual(image.info["duration"], 160)
        self.assertEqual(api.post_group_message.call_args.kwargs["msg_seq"], 2)

    async def test_format_rejection_uses_gif_fallback(self):
        """格式不支持时将完整原始字节交给备用接口并只发送一次。"""
        api = fake_api([ServerError("unsupported image format")])
        content = animated_gif()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            path.write_bytes(content)
            with patch("external_tools.qq.media_sender.upload_group_gif", new_callable=AsyncMock) as fallback:
                fallback.return_value = {"file_info": "chunked"}
                await send_group_image(api, "group", path, "message")
                fallback.assert_awaited_once_with(api, "group", content, path.name)
        api.post_group_message.assert_awaited_once()
        self.assertEqual(api.post_group_message.call_args.kwargs["media"], {"file_info": "chunked"})

    async def test_unrelated_errors_do_not_trigger_fallback(self):
        """服务端、鉴权及缺失响应错误均不重复上传或发送。"""
        for error in (ServerError("internal server error"), AuthenticationFailedError("expired"), None):
            with self.subTest(error=error), TemporaryDirectory() as directory:
                path = Path(directory) / "animated.gif"
                path.write_bytes(animated_gif())
                api = fake_api([error])
                with patch("external_tools.qq.media_sender.upload_group_gif", new_callable=AsyncMock) as fallback:
                    with self.assertRaises(RuntimeError):
                        await send_group_image(api, "group", path, "message")
                    fallback.assert_not_awaited()
                api.post_group_message.assert_not_awaited()

    async def test_fallback_failure_does_not_send_static_frame(self):
        """备用上传失败时保持失败，不把首帧当作完整 GIF 发送。"""
        api = fake_api([ServerError("unsupported format")])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            path.write_bytes(animated_gif())
            with patch("external_tools.qq.media_sender.upload_group_gif", new_callable=AsyncMock) as fallback:
                fallback.side_effect = RuntimeError("GIF rejected")
                with self.assertRaisesRegex(RuntimeError, "GIF rejected"):
                    await send_group_image(api, "group", path, "message")
        api.post_group_message.assert_not_awaited()


class GifChunkTests(unittest.IsolatedAsyncioTestCase):
    """验证分片协议的原始内容、校验和及错误响应处理。"""

    async def test_chunked_upload_preserves_every_byte(self):
        """将两片重新拼接后应等于原 GIF，完成接口只携带 upload_id。"""
        content = animated_gif()
        size = len(content) // 2 + 1
        api = fake_api([
            {"upload_id": "upload", "block_size": size, "parts": [
                {"index": 2, "presigned_url": "https://cos.example/2"},
                {"index": 1, "presigned_url": "https://cos.example/1"},
            ]}, {}, {}, {"file_info": "done"},
        ])
        client = SimpleNamespace(put=AsyncMock(return_value=SimpleNamespace(status_code=200)))
        with patch("features.gif_sender.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            result = await upload_group_gif(api, "group", content, "test.gif")
        self.assertEqual(result, {"file_info": "done"})
        chunks = [call.kwargs["content"] for call in client.put.call_args_list]
        self.assertEqual(b"".join(chunks), content)
        calls = api._http.request.call_args_list
        self.assertEqual(calls[0].kwargs["json"]["md5"], hashlib.md5(content).hexdigest())
        for index, chunk in enumerate(chunks, 1):
            self.assertEqual(calls[index].kwargs["json"], {
                "upload_id": "upload", "part_index": index,
                "block_size": len(chunk), "md5": hashlib.md5(chunk).hexdigest(),
            })
        self.assertEqual(calls[-1].kwargs["json"], {"upload_id": "upload"})

    async def test_invalid_parts_are_rejected_before_put(self):
        """准备响应异常时停止，不上传缺失或无效的分片。"""
        content = animated_gif()
        for parts in ([], [{"index": 0, "presigned_url": "https://cos.example/1"}],
                      [{"index": 1, "presigned_url": "http://cos.example/1"}]):
            with self.subTest(parts=parts):
                api = fake_api([{"upload_id": "u", "block_size": len(content), "parts": parts}])
                with patch("features.gif_sender.httpx.AsyncClient") as factory:
                    with self.assertRaises(RuntimeError):
                        await upload_group_gif(api, "group", content, "test.gif")
                    factory.assert_not_called()

    async def test_cos_failure_does_not_complete_upload(self):
        """COS 拒绝分片时不确认、不合并。"""
        content = animated_gif()
        api = fake_api([{"upload_id": "u", "block_size": len(content), "parts": [
            {"index": 1, "presigned_url": "https://cos.example/1"},
        ]}])
        client = SimpleNamespace(put=AsyncMock(return_value=SimpleNamespace(status_code=403)))
        with patch("features.gif_sender.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                await upload_group_gif(api, "group", content, "test.gif")
        self.assertEqual(api._http.request.await_count, 1)
