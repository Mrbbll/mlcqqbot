"""验证文件选择、Agent 回复衔接和 QQ 发送确认，所有网络请求使用替身。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot_client import _agent_reply_text, handle_command_message
from external_tools.storage import group_memory
from features import file_sender
from features.agent import service
from features.agent.tools import execute_tool
from features.agent.tools.common import ToolContext
from features.security import permissions


class FileDeliveryTests(unittest.IsolatedAsyncioTestCase):
    """通过真实注册表、编排和发送入口检查文件完整链路。"""

    def setUp(self):
        """创建普通文件并隔离群聊记忆。"""
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / "server.log"
        self.path.write_bytes(b"hello\x00binary")
        self.context = ToolContext(user_id="admin", group_id="group", question="把日志文件发给我")
        self.context.discovered_paths.add(str(self.path))
        self.enterContext(patch.object(group_memory, "_messages_by_group", group_memory.OrderedDict()))

    def select(self, path=None, context=None):
        """通过真实校验入口选择文件，禁止绕过权限注册表。"""
        return execute_tool({"function": {"name": "send_server_file", "arguments": {"path": str(path or self.path)}}}, context or self.context)

    async def test_selection_and_model_loop_preserve_pending_file(self):
        """真实模型循环把待发送文件传到 AgentReply，pending 不算发送成功。"""
        call = {"id": "file-call", "type": "function", "function": {"name": "send_server_file", "arguments": {"path": str(self.path)}}}
        model = AsyncMock(side_effect=[{"tool_calls": [call]}, {"content": "即将发送文件"}])
        with patch.object(permissions, "check_superuser", return_value=True), patch.object(service, "AGENT_API_URL", "fake"), patch.object(service, "AGENT_API_KEY", "fake"), patch.object(service, "AGENT_MODEL", "fake"), patch.object(service, "_ask_model", model), patch.object(service, "record_tool_call"):
            reply = await service.handle_agent(f"把文件发送给我 {self.path}", "admin", group_id="group")
        self.assertEqual(reply.file_paths, (self.path,))
        self.assertIn('"delivery": "pending"', model.call_args.args[0][-1]["content"])
        self.assertEqual(group_memory.get_recent_group_messages("group"), [])

    async def test_permission_path_and_duplicate_limits(self):
        """普通用户、未知路径、非群聊和重复选择均被拒绝。"""
        with patch.object(permissions, "check_superuser", return_value=False):
            self.assertEqual(self.select().code, "permission_denied")
        with patch.object(permissions, "check_superuser", return_value=True):
            self.assertEqual(self.select(context=ToolContext(group_id="group", question="把这个日志发给我")).code, "path_not_requested")
            self.assertEqual(self.select(context=ToolContext()).code, "group_required")
            result = self.select()
            self.assertEqual(result.data["delivery"], "pending")
            self.assertEqual(self.select().code, "already_selected")

    async def test_explicit_log_file_requests_are_accepted(self):
        """实例日志、文件名和完整路径均能通过真实工具的发送意图检查。"""
        questions = (
            "发送mod1的日志",
            "发送mcdr.log",
            "发送 /opt/mcdr_mod1/logs/MCDR.log到本群",
            "能不能把这个日志发给我",
            "发送 server.properties",
            "发送日志，不要删除原文件",
        )
        with patch.object(permissions, "check_superuser", return_value=True):
            for question in questions:
                context = ToolContext(user_id="admin", group_id="group", question=question)
                context.discovered_paths.add(str(self.path))
                result = self.select(context=context)
                self.assertTrue(result.ok, (question, result.code))
                self.assertEqual(context.pending_files, [str(self.path)])

            context = ToolContext(user_id="admin", group_id="group", question=f"发送 {self.path}到本群")
            self.assertTrue(self.select(context=context).ok)

    async def test_quoted_file_discussion_never_queues_local_file(self):
        """引用、讨论和否定发送文件时，即使路径已发现也不能发送。"""
        with patch.object(permissions, "check_superuser", return_value=True):
            for question in (
                "我引用的是个文件，但他回复的是自己发送的文件",
                "看看刚才引用的日志内容",
                "不要把这个日志发给我",
                "不把这个日志发给我",
                "为什么要发送文件？",
                "怎么发送日志？",
                "发消息告诉我日志情况",
                "发送日志内容给我",
            ):
                context = ToolContext(user_id="admin", group_id="group", question=question)
                context.discovered_paths.add(str(self.path))
                result = self.select(context=context)
                self.assertEqual(result.code, "delivery_not_requested", question)
                self.assertFalse(context.pending_files)

    async def test_system_hint_cannot_authorize_file_delivery(self):
        """附件失败提示中出现发送字样也不能替代当前用户的授权。"""
        call = {"id": "file-call", "type": "function", "function": {"name": "send_server_file", "arguments": {"path": str(self.path)}}}
        model = AsyncMock(side_effect=[{"tool_calls": [call]}, {"content": "没有发送"}])
        message = SimpleNamespace(content="看看刚才的附件", id="inbound", attachments=[], _api=None)
        with patch("bot_client.read_file_attachments", AsyncMock(return_value=([], ["发送日志.log：下载失败"]))), patch("bot_client.download_image_attachments", AsyncMock(return_value=([], []))), patch.object(permissions, "check_superuser", return_value=True), patch.object(service, "AGENT_API_URL", "fake"), patch.object(service, "AGENT_API_KEY", "fake"), patch.object(service, "AGENT_MODEL", "fake"), patch.object(service, "_ask_model", model), patch.object(service, "record_tool_call"):
            reply = await _agent_reply_text(message, "admin", "group")
        self.assertNotIsInstance(reply, service.AgentReply)
        self.assertIn('"code": "delivery_not_requested"', model.call_args.args[0][-1]["content"])

    async def test_system_hint_does_not_cancel_explicit_file_delivery(self):
        """附加提示里的否定词不会覆盖当前用户明确的发送请求。"""
        call = {"id": "file-call", "type": "function", "function": {"name": "send_server_file", "arguments": {"path": str(self.path)}}}
        model = AsyncMock(side_effect=[{"tool_calls": [call]}, {"content": "即将发送"}])
        message = SimpleNamespace(content=f"发送 {self.path}到本群", id="inbound", attachments=[], _api=None)
        with patch("bot_client.read_file_attachments", AsyncMock(return_value=([], ["不要发送文件.log：下载失败"]))), patch("bot_client.download_image_attachments", AsyncMock(return_value=([], []))), patch.object(permissions, "check_superuser", return_value=True), patch.object(service, "AGENT_API_URL", "fake"), patch.object(service, "AGENT_API_KEY", "fake"), patch.object(service, "AGENT_MODEL", "fake"), patch.object(service, "_ask_model", model), patch.object(service, "record_tool_call"):
            reply = await _agent_reply_text(message, "admin", "group")
        self.assertIsInstance(reply, service.AgentReply)
        self.assertEqual(reply.file_paths, (self.path,))

    async def test_invalid_files_are_not_queued(self):
        """目录、空文件、敏感文件及超限文件在排队前拒绝。"""
        empty = self.path.parent / "empty.txt"
        empty.touch()
        sensitive = self.path.parent / ".env"
        sensitive.write_text("secret", encoding="utf-8")
        large = self.path.parent / "large.zip"
        with large.open("wb") as target:
            target.truncate(file_sender.MAX_FILE_BYTES + 1)
        with patch.object(permissions, "check_superuser", return_value=True):
            for path in (self.path.parent, empty, sensitive, large):
                self.context.discovered_paths.add(str(path))
                self.assertEqual(self.select(path).code, "invalid_file")
        self.assertFalse(self.context.pending_files)

    async def test_upload_and_send_preserve_original_file(self):
        """上传原始二进制及文件名，file_info 只用于当前群的被动回复。"""
        prepared = {"upload_id": "upload", "block_size": "6", "parts": [
            {"index": "1", "presigned_url": "https://storage.example/1", "block_size": "6"},
            {"index": "2", "presigned_url": "https://storage.example/2", "block_size": "6"},
        ]}
        api = SimpleNamespace(_http=SimpleNamespace(request=AsyncMock(side_effect=[prepared, {}, {}, {"file_info": "uploaded"}])), post_group_message=AsyncMock(return_value={"id": "sent"}))
        client = SimpleNamespace(put=AsyncMock(return_value=MagicMock()))
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=client)
        manager.__aexit__ = AsyncMock(return_value=False)
        with patch.object(file_sender.httpx, "AsyncClient", return_value=manager):
            result = await file_sender.send_group_file(api, "group", self.path, "inbound", message_sequence=3)
        payload = api._http.request.call_args_list[0].kwargs["json"]
        self.assertEqual(payload["file_type"], 4)
        self.assertEqual(payload["file_name"], self.path.name)
        self.assertEqual(payload["file_size"], len(self.path.read_bytes()))
        self.assertEqual(b"".join(call.kwargs["content"] for call in client.put.call_args_list), self.path.read_bytes())
        self.assertEqual(api._http.request.call_args.kwargs["json"], {"upload_id": "upload"})
        self.assertEqual(api.post_group_message.call_args.kwargs["msg_seq"], 3)
        self.assertEqual(api.post_group_message.call_args.kwargs["msg_id"], "inbound")
        self.assertEqual(result["id"], "sent")

    async def test_upload_rejection_does_not_send(self):
        """空响应、无文件引用和业务拒绝不继续发送，也不自动重试。"""
        for response in (None, {}, {"code": 123}, {"code": 0}):
            api = SimpleNamespace(_http=SimpleNamespace(request=AsyncMock(return_value=response)), post_group_message=AsyncMock())
            with self.assertRaises(RuntimeError):
                await file_sender.send_group_file(api, "group", self.path, "inbound")
            api.post_group_message.assert_not_called()

    async def test_success_and_failure_in_actual_reply_entry(self):
        """发送入口成功后才记忆文件，失败时发明确通知并使用独立序号。"""
        reply = service.AgentReply("即将发送", file_paths=(self.path,))
        for failed in (False, True):
            group_memory._messages_by_group.clear()
            message = SimpleNamespace(content="发送文件", id="inbound", reply=AsyncMock(return_value={"id": "text"}))
            sender = AsyncMock(side_effect=RuntimeError("rejected")) if failed else AsyncMock(return_value={"id": "file"})
            with patch("bot_client._agent_reply_text", AsyncMock(return_value=reply)), patch("bot_client.send_group_file", sender), patch("bot_client._log"):
                await handle_command_message(message, "admin", is_group=True, group_id="group", force_agent=True)
            self.assertEqual(sender.call_args.kwargs["message_sequence"], 2)
            records = group_memory.get_recent_group_messages("group")
            if failed:
                self.assertIn("文件发送失败", records[-1]["content"])
                self.assertEqual(message.reply.call_args.kwargs["msg_seq"], 3)
                self.assertFalse(any("[已发送文件]" in item["content"] for item in records))
            else:
                self.assertEqual(records[-1]["content"], "[已发送文件] server.log")

    async def test_file_changed_before_upload_is_rechecked(self):
        """排队之后文件删除或变空不会开始网络上传。"""
        self.path.write_bytes(b"")
        api = SimpleNamespace(_http=SimpleNamespace(request=AsyncMock()))
        with self.assertRaises(ValueError):
            await file_sender.send_group_file(api, "group", self.path, "inbound")
        api._http.request.assert_not_called()

    async def test_prepare_integer_parsing_and_diagnostics(self):
        """数字字符串兼容整数，布尔和浮点仍拒绝，异常诊断不打印凭证。"""
        for value in (6, "6"):
            self.assertEqual(file_sender.api_integer(value), 6)
        for value in (True, 6.5, "6.0", "-6", None):
            self.assertEqual(file_sender.api_integer(value), 0)
        response = {"upload_id": "secret-id", "block_size": None, "parts": [{"presigned_url": "secret-url"}]}
        with patch.object(file_sender, "post_upload", AsyncMock(return_value=response)), self.assertLogs("mlcbot", level="WARNING") as logs, self.assertRaises(RuntimeError):
            await file_sender.upload_file(None, "group", self.path, b"data")
        self.assertNotIn("secret-id", str(logs.output))
        self.assertNotIn("secret-url", str(logs.output))
        self.assertIn("block_size", str(logs.output))

    async def test_prepare_already_uploaded_token(self):
        """已有有效文件引用时不再强求不存在的分片参数。"""
        with patch.object(file_sender, "post_upload", AsyncMock(return_value={"file_info": "ready"})), patch.object(file_sender.httpx, "AsyncClient") as client:
            self.assertEqual(await file_sender.upload_file(None, "group", self.path, b"data"), "ready")
        client.assert_not_called()

    async def test_invalid_upload_parts_are_rejected_before_put(self):
        """缺片、重复索引和不安全地址在传输文件前失败。"""
        for parts in ([], [{"index": 1, "presigned_url": "http://storage.example/1"}], [{"index": 2, "presigned_url": "https://storage.example/2"}]):
            api = SimpleNamespace(_http=SimpleNamespace(request=AsyncMock(return_value={"upload_id": "u", "block_size": 100, "parts": parts})))
            with patch.object(file_sender.httpx, "AsyncClient") as client, self.assertRaises(RuntimeError):
                await file_sender.upload_file(api, "group", self.path, b"data")
            client.assert_not_called()

    async def test_message_rejection_and_timeout_are_not_success(self):
        """上传完成仍需消息确认，拒绝或超时不重发消息。"""
        for response in ({"code": 123}, {}, None):
            api = SimpleNamespace(post_group_message=AsyncMock(return_value=response))
            with patch.object(file_sender, "upload_file", AsyncMock(return_value="uploaded")), self.assertRaises(RuntimeError):
                await file_sender.send_group_file(api, "group", self.path, "inbound")
            self.assertEqual(api.post_group_message.await_count, 1)
        with patch.object(file_sender, "AGENT_TOOL_TIMEOUT_SECONDS", 0), self.assertRaises(TimeoutError):
            await file_sender.send_group_file(None, "group", self.path, "inbound")
