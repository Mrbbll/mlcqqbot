"""离线验证直播状态迁移、通知排队和跨功能被动回复额度。"""

import asyncio
import unittest
from collections import deque
from unittest.mock import AsyncMock, patch

import httpx

from external_tools.bilibili.client import BilibiliApiClient, LiveRoomInfo
from features.bilibili_notifications import monitor as bili
from features.gitee_notifications import monitor as gitee
from features.passive_notifications import context


class FakeMessage:
    """记录被动回复参数，不连接 QQ。"""

    def __init__(self, message_id="message-1", group_id="group-1"):
        """创建可追踪回复的群消息。"""
        self.id = message_id
        self.group_openid = group_id
        self.reply = AsyncMock()


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    """验证状态变化只排队一次，并共享 Gitee 的回复额度。"""

    async def asyncSetUp(self):
        """隔离模块状态和配置，禁止真实网络调用。"""
        self.patches = [
            patch.object(bili, "BILIBILI_NOTIFY_GROUPS", ["group-1", "group-2"]),
            patch.object(bili, "active_rooms", [123]),
            patch.object(bili, "client", AsyncMock()),
            patch.object(bili, "status", {}),
            patch.object(bili, "pending_notifications", {}),
            patch.object(bili, "notification_after", {}),
            patch.object(bili, "send_lock", asyncio.Lock()),
            patch.object(context, "NOTIFY_GROUPS", {"group-1", "group-2"}),
            patch.object(context, "recent_messages", {}),
            patch.object(context, "reply_sequences", context.OrderedDict()),
            patch.object(gitee, "pending_notifications", {}),
            patch.object(gitee, "notification_after", {}),
            patch.object(gitee, "send_lock", asyncio.Lock()),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.message = FakeMessage()

    async def test_baseline_transitions_and_multiple_groups(self):
        """启动不补发；重复状态不排队；开播下播按群保留顺序。"""
        bili.client.get_room_info.return_value = LiveRoomInfo(123, False, "主播甲", "标题")
        await bili.check_all()
        self.assertFalse(bili.pending_notifications)
        bili.client.get_room_info.return_value = LiveRoomInfo(123, True, "主播甲", "标题")
        await bili.check_all()
        await bili.check_all()
        bili.client.get_room_info.return_value = LiveRoomInfo(123, False, "主播甲", "标题")
        await bili.check_all()
        for group in ("group-1", "group-2"):
            queue = bili.pending_notifications[group]
            self.assertEqual(len(queue), 2)
            self.assertIn("开播啦", queue[0])
            self.assertIn("https://live.bilibili.com/123", queue[0])
            self.assertIn("已下播", queue[1])
        context.remember_group_message(self.message)
        await bili.handle_group_message(self.message)
        self.message.reply.assert_awaited_once()
        self.assertEqual(len(bili.pending_notifications["group-1"]), 1)
        await bili.handle_group_message(self.message)
        self.assertEqual(self.message.reply.await_count, 1)

    async def test_query_failure_keeps_previous_state(self):
        """查询失败不改变基线，也不产生假下播通知。"""
        bili.status[123] = True
        bili.client.get_room_info.side_effect = ValueError("invalid payload")
        await bili.check_all()
        self.assertTrue(bili.status[123])
        self.assertFalse(bili.pending_notifications)

    async def test_failed_reply_retries_without_losing_queue(self):
        """发送失败保留通知，冷却后重试使用下一个序号。"""
        context.remember_group_message(self.message, replies_already_sent=True)
        bili.pending_notifications["group-1"] = deque(["开播"])
        self.message.reply.side_effect = RuntimeError("QQ error")
        await bili.flush_pending_notifications("group-1")
        self.assertEqual(list(bili.pending_notifications["group-1"]), ["开播"])
        self.message.reply.side_effect = None
        bili.notification_after.clear()
        await bili.flush_pending_notifications("group-1")
        self.assertNotIn("group-1", bili.pending_notifications)
        self.assertEqual([call.kwargs["msg_seq"] for call in self.message.reply.await_args_list], [2, 3])

    async def test_expired_or_exhausted_anchor_waits_for_new_message(self):
        """五分钟过期或单消息达到五次上限后等待新锚点。"""
        context.remember_group_message(self.message, received_at=context.monotonic() - 301)
        bili.pending_notifications["group-1"] = deque(["通知"])
        await bili.flush_pending_notifications("group-1")
        self.message.reply.assert_not_awaited()
        context.remember_group_message(self.message)
        for _ in range(5):
            context.next_reply_sequence("group-1", self.message)
        await bili.flush_pending_notifications("group-1")
        self.message.reply.assert_not_awaited()
        new_message = FakeMessage("message-2")
        context.remember_group_message(new_message)
        await bili.handle_group_message(new_message)
        self.assertEqual(new_message.reply.await_args.kwargs["msg_seq"], 1)

    async def test_gitee_and_bilibili_share_reply_sequences(self):
        """命令占用首个序号后，Gitee 和直播通知分别使用二、三号。"""
        context.remember_group_message(self.message, replies_already_sent=True)
        progress = gitee.UserProgress(0, set())
        notification = gitee.PendingNotification("提交", (("repo/name", "sha"),), progress, "user", "event")
        gitee.enqueue_notification("group-1", notification)
        await gitee.flush_pending_notifications("group-1")
        bili.pending_notifications["group-1"] = deque(["直播"])
        await bili.flush_pending_notifications("group-1")
        self.assertEqual([call.kwargs["msg_seq"] for call in self.message.reply.await_args_list], [2, 3])
        self.assertIn(("repo/name", "sha"), progress.sent_commits)
        self.assertFalse(progress.queued_commits)

    async def test_start_is_idempotent_and_validates_room_ids(self):
        """无效直播间被跳过，QQ 重连不会重建监听任务。"""
        with patch.object(bili, "BILIBILI_ROOM_IDS", ["123", "0", "bad", "123"]), patch.object(bili, "monitor_task", None):
            await bili.start_bilibili_monitor()
            first = bili.monitor_task
            await bili.start_bilibili_monitor()
            self.assertIs(bili.monitor_task, first)
            self.assertEqual(bili.active_rooms, [123])
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first


class ClientTests(unittest.IsolatedAsyncioTestCase):
    """使用 HTTP 模拟响应验证接口解析和错误识别。"""

    async def test_response_validation(self):
        """只接受明确的直播状态，风控及缺失数据一律报错。"""
        payloads = [
            {"code": 0, "data": {"by_room_ids": {"123": {"live_status": 1, "uname": "主播", "title": "标题"}}}},
            {"code": 0, "data": {"by_room_ids": {"123": {"live_status": 2}}}},
            {"code": -352},
            {"code": 0, "data": {"by_room_ids": {}}},
            {"code": 0, "data": {"by_room_ids": {"123": {}}}},
        ]
        for index, payload in enumerate(payloads):
            with self.subTest(index=index):
                client = BilibiliApiClient(5)
                client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)), base_url="https://api.live.bilibili.com")
                try:
                    if index < 2:
                        info = await client.get_room_info(123)
                        self.assertEqual(info.is_live, index == 0)
                    else:
                        with self.assertRaises(ValueError):
                            await client.get_room_info(123)
                finally:
                    await client.close()


if __name__ == "__main__":
    unittest.main()
