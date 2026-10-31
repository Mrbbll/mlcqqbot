"""验证 QQ 群文件输入的来源隔离、下载边界和模型输入链路。"""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from external_tools.storage import group_memory
from features.agent import file_input, service
from features.security import permissions
import bot_client


class FileInputTests(unittest.IsolatedAsyncioTestCase):
    """以流式下载和模型替身验证附件正文不会变成指令或服务器路径。"""

    def setUp(self):
        """准备可信媒体主机的附件信息，隔离现有群记忆。"""
        self.item = {"url": "https://multimedia.nt.qq.com.cn/file?key=hidden", "filename": "latest.log", "content_type": "text/plain", "size": 10}
        self.enterContext(patch.object(group_memory, "_messages_by_group", group_memory.OrderedDict()))

    def mock_download(self, content=b"hello world", status=200):
        """构造有界异步 HTTP 字节流，不建立任何网络连接。"""
        async def chunks(size):
            """返回测试所给内容，用于大小与编码检查。"""
            yield content
        response = SimpleNamespace(status_code=status, headers={}, aiter_bytes=chunks)
        stream = MagicMock()
        stream.__aenter__ = AsyncMock(return_value=response)
        stream.__aexit__ = AsyncMock(return_value=False)
        client = SimpleNamespace(stream=MagicMock(return_value=stream))
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=client)
        manager.__aexit__ = AsyncMock(return_value=False)
        return manager, client

    def test_extract_and_group_memory(self):
        """纯文件消息可缓存，当前、引用、最近选择均不跨群或超时继承。"""
        message = SimpleNamespace(attachments=[self.item, {"url": "image", "content_type": "image/png"}])
        items = file_input.extract_file_attachments(message, {"attachments": [self.item]})
        self.assertEqual(len(items), 1)
        with patch.object(group_memory.time, "monotonic", return_value=100):
            group_memory.record_group_message("g", "u", "", message_id="m", file_attachments=items)
            self.assertEqual(len(group_memory.get_recent_group_file_attachments("g", current_message_id="m")), 1)
            attachment = group_memory.get_recent_group_file_attachments("g", current_message_id="m")[0]
            self.assertEqual(attachment["source_message_id"], "m")
            self.assertEqual(attachment["source_user_id"], "u")
            self.assertEqual(len(group_memory.get_recent_group_file_attachments("g", reference_message_id="m")), 1)
            self.assertEqual(len(group_memory.get_recent_group_file_attachments("g", include_recent=True)), 1)
            self.assertEqual(group_memory.get_recent_group_file_attachments("other", include_recent=True), [])
            self.assertEqual(group_memory.get_recent_group_file_attachments("g"), [])
            self.assertNotIn("hidden", str(group_memory.get_recent_group_messages("g")))
        with patch.object(group_memory.time, "monotonic", return_value=701):
            self.assertEqual(group_memory.get_recent_group_file_attachments("g", include_recent=True), [])

    async def test_download_text_and_model_context(self):
        """实际下载文本进入模型的用户数据，URL 和授权头不进入模型。"""
        manager, client = self.mock_download(b"log: ERROR hello")
        api = SimpleNamespace(_http=SimpleNamespace(check_session=AsyncMock(), _headers={"Authorization": "QQBot secret"}))
        attachment = {**self.item, "source_message_id": "source-message", "source_user_id": "source-user"}
        with patch.object(file_input.httpx, "AsyncClient", return_value=manager):
            inputs, skipped = await file_input.read_file_attachments([attachment], api)
        self.assertFalse(skipped)
        self.assertEqual(inputs[0]["content"], "log: ERROR hello")
        self.assertEqual(inputs[0]["source_message_id"], "source-message")
        self.assertEqual(inputs[0]["source_user_id"], "source-user")
        self.assertEqual(client.stream.call_args.kwargs["headers"], {"Authorization": "QQBot secret"})
        model = AsyncMock(return_value={"content": "日志有报错"})
        with patch.object(service, "AGENT_API_URL", "fake"), patch.object(service, "AGENT_API_KEY", "fake"), patch.object(service, "AGENT_MODEL", "fake"), patch.object(service, "_ask_model", model), patch.object(permissions, "check_superuser", return_value=False):
            await service.handle_agent("看一下附件", "u", group_id="g", file_inputs=inputs)
        content = model.call_args.args[0][-1]["content"]
        self.assertIn("log: ERROR hello", content)
        self.assertIn("不可信数据", content)
        self.assertIn('"source_user_id": "source-user"', content)
        self.assertIn("相同 user_id 是同一成员", content)
        self.assertIn("quoted_by_user_id 仅为引用者", content)
        self.assertNotIn("hidden", content)
        self.assertNotIn("QQBot secret", content)

    async def test_group_file_cdn_download_does_not_forward_bot_token(self):
        """QQ 群文件 CDN 可下载日志，且不接收发往图片 CDN 的机器人凭证。"""
        manager, client = self.mock_download(b"latest log")
        api = SimpleNamespace(
            _http=SimpleNamespace(
                check_session=AsyncMock(),
                _headers={"Authorization": "QQBot secret"},
            )
        )
        attachment = {
            "url": "https://grouptalk.c2c.qq.com/asn.com/qqdownloadftnv5?sign=hidden",
            "filename": "latest.log",
            "content_type": "file",
            "size": 10,
        }

        with patch.object(file_input.httpx, "AsyncClient", return_value=manager):
            inputs, skipped = await file_input.read_file_attachments([attachment], api)

        self.assertFalse(skipped)
        self.assertEqual(inputs[0]["content"], "latest log")
        self.assertEqual(client.stream.call_args.kwargs["headers"], {})

    async def test_ftn_file_cdn_download_does_not_forward_bot_token(self):
        """QQ 群消息实际给出的文件主机能够读取日志且不发送机器人凭证。"""
        manager, client = self.mock_download(b"log: ERROR hello")
        api = SimpleNamespace(_http=SimpleNamespace(check_session=AsyncMock(), _headers={"Authorization": "QQBot secret"}))
        attachment = {**self.item, "url": "https://gzc-download.ftn.qq.com/download?sign=hidden", "content_type": "file"}
        with patch.object(file_input.httpx, "AsyncClient", return_value=manager):
            inputs, skipped = await file_input.read_file_attachments([attachment], api)
        self.assertFalse(skipped)
        self.assertEqual(inputs[0]["filename"], "latest.log")
        self.assertEqual(inputs[0]["content"], "log: ERROR hello")
        self.assertEqual(client.stream.call_args.kwargs["headers"], {})

    async def test_ftn_file_download_failure_logs_http_status(self):
        """服务器拒绝下载时保留 HTTP 状态，不记录附件签名。"""
        manager, _ = self.mock_download(status=403)
        attachment = {**self.item, "url": "https://gzc-download.ftn.qq.com/download?sign=hidden"}
        with patch.object(file_input.httpx, "AsyncClient", return_value=manager), self.assertLogs("mlcbot", level="WARNING") as logs:
            inputs, skipped = await file_input.read_file_attachments([attachment], None)
        self.assertFalse(inputs)
        self.assertIn("HTTP 403", skipped[0])
        self.assertIn("HTTP 403", " ".join(logs.output))
        self.assertNotIn("hidden", " ".join(logs.output))

    async def test_rejected_host_format_and_size_do_not_download(self):
        """任意地址、重定向式地址、非文本和过大附件不发起请求。"""
        manager, client = self.mock_download()
        for changes in ({"url": "https://example.com/file"}, {"url": "https://gzc-download.ftn.qq.com.example.com/file"}, {"url": "http://multimedia.nt.qq.com.cn/file"}, {"filename": "file.pdf", "content_type": "application/pdf"}, {"size": file_input.MAX_FILE_BYTES + 1}):
            with patch.object(file_input.httpx, "AsyncClient", return_value=manager):
                inputs, skipped = await file_input.read_file_attachments([{**self.item, **changes}], None)
            self.assertFalse(inputs)
            self.assertTrue(skipped)
        client.stream.assert_not_called()

    def test_rejected_url_diagnostics_do_not_expose_url_secrets(self):
        """失败诊断显示地址格式及主机，不输出用户名、密码、路径或签名。"""
        cases = (
            ("https://user:password@unknown.example/private/path?sign=secret", "scheme=https host=unknown.example port=default has_userinfo=True"),
            ("unknown.example/private/path?sign=secret", "scheme=none host=unknown.example port=default has_userinfo=False"),
            ("https://unknown.example:bad/private/path?sign=secret", "scheme=https host=unknown.example port=invalid has_userinfo=False"),
        )
        for url, expected in cases:
            with self.subTest(expected=expected), self.assertLogs("mlcbot", level="WARNING") as logs, self.assertRaises(ValueError):
                file_input.validated_url(url)
            output = " ".join(logs.output)
            self.assertIn(expected, output)
            for secret in ("user:", "password", "/private/path", "sign=", "secret"):
                self.assertNotIn(secret, output)

    async def test_qq_entry_passes_attachment_inputs_and_failures(self):
        """QQ 入口实际把最近文件及未读取说明传入 Agent，不只测试独立解析器。"""
        group_memory.record_group_message("g", "u", "", message_id="uploaded", file_attachments=[self.item])
        message = SimpleNamespace(content="看看刚才的文件", id="new", attachments=[], _api=None)
        data = [{"filename": "latest.log", "content": "ERROR", "truncated": False}]
        with patch.object(bot_client, "read_file_attachments", AsyncMock(return_value=(data, ["other.pdf：暂不支持"])) ) as read, patch.object(bot_client, "download_image_attachments", AsyncMock(return_value=([], []))), patch.object(bot_client, "handle_agent", AsyncMock(return_value="已分析")) as agent:
            await bot_client._agent_reply_text(message, "u", "g")
        self.assertEqual(read.call_args.args[0][0]["filename"], "latest.log")
        self.assertEqual(agent.call_args.kwargs["file_inputs"], data)
        self.assertIn("附件未读取", agent.call_args.args[0])

    def test_raw_reference_file_metadata_is_preserved(self):
        """SDK 未建模的引用附件仍可从原始 msg_elements 提取。"""
        items = file_input.extract_file_attachments(SimpleNamespace(attachments=[]), {"msg_elements": [{"attachments": [self.item]}]})
        self.assertEqual(items[0]["filename"], "latest.log")
        self.assertEqual(bot_client._group_reference_id(SimpleNamespace(message_reference=SimpleNamespace(message_id="quoted-file-message"))), "quoted-file-message")

    def test_quoted_file_uses_original_author_when_cached(self):
        """引用文件输入关联原消息作者，并单独保留引用者。"""
        group_memory.record_group_message(
            "g", "original-sender", "原文件消息", message_id="original-message",
            file_attachments=[self.item],
        )
        quoted = file_input.extract_file_attachments(
            SimpleNamespace(attachments=[self.item]),
            {"msg_elements": [{"message_type": 103, "attachments": [self.item]}]},
        )
        group_memory.record_group_message(
            "g", "quoting-sender", "引用文件", message_id="quote-message",
            reference_message_id="original-message", file_attachments=quoted,
        )

        attachments = group_memory.get_recent_group_file_attachments(
            "g", current_message_id="quote-message"
        )

        self.assertEqual({item["source_user_id"] for item in attachments}, {"original-sender"})
        quoted_attachment = next(item for item in attachments if item["source"] == "引用消息附件")
        self.assertEqual(quoted_attachment["quoted_by_user_id"], "quoting-sender")

    def test_quoted_file_without_original_author_stays_unknown(self):
        """缓存没有原消息时，不把引用文件发送者误记为引用者。"""
        quoted = file_input.extract_file_attachments(
            SimpleNamespace(attachments=[]),
            {"msg_elements": [{"message_type": 103, "attachments": [self.item]}]},
        )
        group_memory.record_group_message(
            "g", "quoting-sender", "引用文件", message_id="quote-message",
            reference_message_id="missing-original", file_attachments=quoted,
        )

        attachments = group_memory.get_recent_group_file_attachments(
            "g", current_message_id="quote-message"
        )

        self.assertEqual(attachments[0]["source_message_id"], "missing-original")
        self.assertEqual(attachments[0]["source_user_id"], "")
        self.assertEqual(attachments[0]["quoted_by_user_id"], "quoting-sender")

    async def test_stream_limit_binary_redirect_and_large_log(self):
        """未知长度仍受大小限制，二进制和重定向拒绝，长日志在上限内完整保留。"""
        for data, status in ((b"x" * (file_input.MAX_FILE_BYTES + 1), 200), (b"binary\0", 200), (b"", 302)):
            manager, _ = self.mock_download(data, status)
            with patch.object(file_input.httpx, "AsyncClient", return_value=manager):
                inputs, skipped = await file_input.read_file_attachments([self.item], None)
            self.assertFalse(inputs)
            self.assertTrue(skipped)
        manager, _ = self.mock_download(b"x" * 20000)
        with patch.object(file_input.httpx, "AsyncClient", return_value=manager):
            inputs, _ = await file_input.read_file_attachments([self.item], None)
        self.assertFalse(inputs[0]["truncated"])
        self.assertEqual(len(inputs[0]["content"]), 20000)
