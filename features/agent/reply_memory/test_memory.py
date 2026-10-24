"""验证群回复记忆、成功确认和继承条件换图，所有发送均使用替身。"""

import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from bot_client import handle_command_message
from external_tools.storage import group_memory
from features.agent.emojipic.library import EmojiLibrary
from features.agent.reply_memory import last_sent_emoji, record_bot_reply
from features.agent.service import AgentReply, _agent_reply_with_emoji, _emoji_tool_result


class ReplyMemoryTests(unittest.IsolatedAsyncioTestCase):
    """检查实际发送入口到下一轮上下文与换图选择的完整链路。"""

    def setUp(self):
        """隔离每个用例的内存记录。"""
        self.memory_patch = patch.object(group_memory, "_messages_by_group", group_memory.OrderedDict())
        self.memory_patch.start()
        self.addCleanup(self.memory_patch.stop)

    async def test_successful_text_and_emoji_are_recorded(self):
        """成功回复保留真实消息 ID、机器人身份和表情信息。"""
        metadata = {"id": "emoji-1", "name": "happy", "format": "gif", "query": "happy", "gif_only": True}
        reply = AgentReply("hello", Path("happy.gif"), metadata)
        message = SimpleNamespace(content="hello", id="inbound", reply=AsyncMock(return_value={"id": "text-id"}))
        with patch("bot_client._agent_reply_text", new=AsyncMock(return_value=reply)), \
             patch("bot_client.send_group_image", new=AsyncMock(return_value={"id": "image-id"})):
            await handle_command_message(message, "user", is_group=True, group_id="group", force_agent=True)
        context = group_memory.get_recent_group_messages("group")
        self.assertEqual([item["message_id"] for item in context], ["text-id", "image-id"])
        self.assertTrue(all(item["role"] == "assistant" for item in context))
        self.assertEqual(context[0]["content"], "hello")
        self.assertTrue(context[1]["has_image"])
        self.assertEqual(last_sent_emoji("group"), metadata)
        self.assertIsNone(last_sent_emoji("other-group"))

    async def test_failed_image_does_not_become_last_sent(self):
        """图片发送失败时只记录已成功发送的文字。"""
        reply = AgentReply("hello", Path("happy.gif"), {"id": "not-sent"})
        message = SimpleNamespace(content="hello", id="inbound", reply=AsyncMock(return_value={"id": "text-id"}))
        with patch("bot_client._agent_reply_text", new=AsyncMock(return_value=reply)), \
             patch("bot_client.send_group_image", new=AsyncMock(side_effect=RuntimeError("rejected"))), \
             self.assertLogs("mlcbot", level="ERROR"):
            await handle_command_message(message, "user", is_group=True, group_id="group", force_agent=True)
        self.assertEqual(len(group_memory.get_recent_group_messages("group")), 1)
        self.assertIsNone(last_sent_emoji("group"))

    def test_unconfirmed_and_expired_replies_are_not_used(self):
        """无发送确认不记忆，已有记忆遵循十分钟过期机制。"""
        record_bot_reply("group", "hello", None)
        self.assertEqual(group_memory.get_recent_group_messages("group"), [])
        with patch.object(group_memory.time, "monotonic", return_value=100):
            record_bot_reply("group", "hello", {"id": "image"}, emoji={"id": "old"})
        with patch.object(group_memory.time, "monotonic", return_value=701):
            self.assertIsNone(last_sent_emoji("group"))

    def test_replacement_inherits_gif_filter_and_excludes_previous(self):
        """真实索引检索换一张时沿用关键词与 GIF 格式，并且先排除旧 ID。"""
        with TemporaryDirectory() as directory:
            library = EmojiLibrary(Path(directory))
            for fmt, color in (("GIF", "red"), ("GIF", "blue"), ("PNG", "green")):
                output = BytesIO()
                Image.new("RGB", (2, 2), color).save(output, format=fmt)
                data = f"data:image/{fmt.lower()};base64," + base64.b64encode(output.getvalue()).decode()
                library.save(data, "happy", color, ["happy"], {})
            with patch("features.agent.service.search_emoji_images", side_effect=library.search):
                first = {"group_id": "group"}
                _emoji_tool_result("send_emoji_image", {"query": "happy", "gif_only": True}, first)
                first_reply = _agent_reply_with_emoji("hello", first["pending_emoji_images"])
                # 只选择但未发送时不应建立换图依据。
                self.assertIsNone(last_sent_emoji("group"))
                record_bot_reply("group", "", {"id": "image-1"}, emoji=first_reply.emoji_metadata)
                second = {"group_id": "group"}
                _emoji_tool_result("send_emoji_image", {"query": "", "replace_previous": True}, second)
                next_item = second["pending_emoji_images"][0]
                self.assertNotEqual(next_item["id"], first_reply.emoji_metadata["id"])
                self.assertEqual(next_item["query"], "happy")
                self.assertTrue(next_item["gif_only"])
                self.assertTrue(next_item["file"].endswith(".gif"))
                self.assertEqual(library.search("happy", gif_only=True, exclude_id=next_item["id"])[0]["id"],
                                 first_reply.emoji_metadata["id"])

    def test_no_previous_or_no_alternative_does_not_repeat(self):
        """缺少上一张或没有候选时明确返回，不把旧图片重新加入待发送队列。"""
        result = _emoji_tool_result("send_emoji_image", {"query": "", "replace_previous": True}, {"group_id": "g"})
        self.assertIn("没有近期", result)
        record_bot_reply("g", "", {"id": "sent"}, emoji={"id": "only", "query": "happy", "gif_only": True})
        context = {"group_id": "g"}
        with patch("features.agent.service.search_emoji_images", return_value=[]) as search:
            result = _emoji_tool_result("send_emoji_image", {"query": "", "replace_previous": True}, context)
        search.assert_called_once_with("happy", 1, gif_only=True, exclude_id="only")
        self.assertIn("没有其他", result)
        self.assertEqual(context["pending_emoji_images"], [])
