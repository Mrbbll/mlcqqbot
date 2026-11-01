"""验证群消息在异步转发期间进入 Agent 上下文的时序。"""

import asyncio
from collections import OrderedDict
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import bot_client
from external_tools.storage import group_memory


class GroupMessageOrderTests(unittest.IsolatedAsyncioTestCase):
    """隔离群记忆和外部服务，检查并发消息的可见性。"""

    async def asyncSetUp(self):
        """隔离消息缓存和不参与时序验证的外部调用。"""
        self.enterContext(patch.object(group_memory, "_messages_by_group", OrderedDict()))
        self.enterContext(patch.object(bot_client, "_seen_group_messages", OrderedDict()))
        self.enterContext(patch.object(bot_client, "get_group_message_raw_data", return_value={}))
        self.enterContext(patch.object(bot_client, "extract_image_attachments", return_value=[]))
        self.enterContext(patch.object(bot_client, "extract_file_attachments", return_value=[]))
        self.enterContext(patch.object(bot_client, "get_group_message_indices", return_value=("", "")))
        self.enterContext(patch.object(bot_client, "handle_gitee_group_message", new_callable=AsyncMock))
        self.enterContext(patch.object(bot_client, "handle_bilibili_group_message", new_callable=AsyncMock))

    async def test_pending_forward_keeps_earlier_message_visible(self):
        """第一条转发未完成时，第二条仍能读取它；重复事件不会重复写入。"""
        started = asyncio.Event()
        release = asyncio.Event()
        contexts = {}

        async def forward(message):
            """暂停第一条消息的转发。"""
            if message.id == "first":
                started.set()
                await release.wait()

        async def handle(message, user_id, **kwargs):
            """记录处理当前消息时取得的历史。"""
            contexts[message.id] = group_memory.get_recent_group_messages(
                "group", exclude_message_id=message.id,
                current_message_received_at=kwargs["received_at"],
            )
            return True

        first = SimpleNamespace(id="first", group_openid="group", content="先到", author=None)
        second = SimpleNamespace(id="second", group_openid="group", content="后到", author=None)
        with patch.object(bot_client, "forward_group_message_to_game", side_effect=forward), \
             patch.object(bot_client, "handle_command_message", side_effect=handle):
            pending = asyncio.create_task(bot_client.handle_group_message(first))
            try:
                await started.wait()
                await bot_client.handle_group_message(first)
                await bot_client.handle_group_message(second)
                self.assertEqual([item["content"] for item in contexts["second"]], ["先到"])
                self.assertEqual(len(group_memory.get_recent_group_messages("group")), 2)
            finally:
                release.set()
                await pending

    async def test_forward_failure_preserves_message_and_continues(self):
        """转发失败后，消息仍保留且命令处理继续。"""
        message = SimpleNamespace(id="failure", group_openid="group", content="内容", author=None)
        with patch.object(bot_client, "forward_group_message_to_game", new_callable=AsyncMock, side_effect=OSError()), \
             patch.object(bot_client, "handle_command_message", new_callable=AsyncMock, return_value=True) as handler, \
             patch.object(bot_client._log, "exception"):
            await bot_client.handle_group_message(message)
        handler.assert_awaited_once()
        self.assertEqual([item["content"] for item in group_memory.get_recent_group_messages("group")], ["内容"])
