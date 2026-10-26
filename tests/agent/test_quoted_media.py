"""验证 QQ 引用索引和图片附件进入群记忆及 Agent 图片输入链路。"""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from external_tools.qq.botpy_compat import get_group_message_indices
from external_tools.storage import group_memory
from features.agent.vision.image_input import extract_image_attachments


class QuotedMediaTests(unittest.TestCase):
    """用 QQ 原始事件样例检查引用图片解析与 REFIDX 关联。"""

    def setUp(self):
        """隔离群记忆，避免测试读取其他用例留下的消息。"""
        self.memory_patch = patch.object(group_memory, "_messages_by_group", group_memory.OrderedDict())
        self.memory_patch.start()
        self.addCleanup(self.memory_patch.stop)

    def test_message_scene_indices_are_parsed_without_auth_token(self):
        """从 message_scene.ext 读取索引值，同时忽略认证扩展字段。"""
        raw_data = {
            "message_scene": {
                "ext": [
                    "ref_msg_idx=REFIDX_quoted==",
                    "msg_idx=REFIDX_current==",
                    "auth_token=must-not-be-kept",
                ]
            }
        }

        self.assertEqual(
            get_group_message_indices(raw_data),
            ("REFIDX_current==", "REFIDX_quoted=="),
        )

    def test_quoted_message_element_image_is_marked_as_reference(self):
        """引用元素直接附带的图片 URL 会被解析并标为引用图片。"""
        message = SimpleNamespace(attachments=[])
        raw_data = {
            "message_type": 103,
            "msg_elements": [
                {
                    "message_type": 103,
                    "content": "被引用的图片",
                    "attachments": [
                        {
                            "content_type": "image/png",
                            "filename": "quoted.png",
                            "size": 12,
                            "url": "https://multimedia.nt.qq.com.cn/download?token=hidden",
                        }
                    ],
                }
            ],
        }

        images = extract_image_attachments(message, raw_data)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["relation"], "引用消息")
        self.assertEqual(images[0]["source"], "引用消息图片")

    def test_reference_index_resolves_original_message_image(self):
        """当前消息的 ref_msg_idx 能找到此前缓存消息中的图片和文字。"""
        group_memory.record_group_message(
            "group",
            "sender",
            "原图片消息",
            message_id="original-message",
            message_index="REFIDX_original",
            image_attachments=[
                {
                    "url": "https://multimedia.nt.qq.com.cn/download?token=hidden",
                    "content_type": "image/jpeg",
                    "filename": "original.jpg",
                    "size": 20,
                }
            ],
            file_attachments=[
                {
                    "url": "https://multimedia.nt.qq.com.cn/download?file=hidden",
                    "content_type": "text/plain",
                    "filename": "original.log",
                    "size": 8,
                }
            ],
        )
        group_memory.record_group_message(
            "group",
            "quoting-sender",
            "这是什么？",
            message_id="quote-message",
            message_index="REFIDX_quote",
            reference_message_id="REFIDX_original",
        )

        images = group_memory.get_recent_group_image_attachments(
            "group",
            current_message_id="quote-message",
        )
        context = group_memory.get_recent_group_messages(
            "group",
            exclude_message_id="quote-message",
        )
        files = group_memory.get_recent_group_file_attachments(
            "group",
            current_message_id="quote-message",
        )

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["relation"], "引用消息")
        self.assertEqual(images[0]["message_id"], "original-message")
        self.assertEqual([item["content"] for item in context], ["原图片消息"])
        self.assertEqual(files[0]["message_id"], "original-message")


if __name__ == "__main__":
    unittest.main()
