"""验证 QQ 引用索引和图片附件进入群记忆及 Agent 图片输入链路。"""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from external_tools.qq.botpy_compat import get_group_message_indices
from external_tools.storage import group_memory
from features.agent.vision.image_input import _image_description, extract_image_attachments


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
        message = SimpleNamespace(attachments=[{
            "content_type": "image/png",
            "filename": "quoted.png",
            "size": 12,
            "url": "https://multimedia.nt.qq.com.cn/download?token=hidden",
        }])
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
        self.assertEqual(images[0]["source_user_id"], "")

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
        self.assertEqual(images[0]["source_user_id"], "sender")
        self.assertEqual([item["content"] for item in context], ["原图片消息"])
        self.assertEqual(context[0]["images"][0]["source_user_id"], "sender")
        self.assertEqual(files[0]["message_id"], "original-message")
        self.assertEqual(files[0]["source_user_id"], "sender")

    def test_image_description_exposes_original_sender_and_message(self):
        """传给模型的图片说明明确标出原始发送者和消息 ID。"""
        description = _image_description({
            "source": "消息附件",
            "source_message_id": "image-message",
            "source_user_id": "image-sender",
        })

        self.assertIn("原始发送者：image-sender", description)
        self.assertIn("原始消息：image-message", description)

    def test_quoted_image_uses_original_author_when_cached(self):
        """引用预览图优先关联到被引用消息作者，不归给引用者。"""
        url = "https://multimedia.nt.qq.com.cn/download?token=hidden"
        group_memory.record_group_message(
            "group",
            "original-sender",
            "原始图片",
            message_id="original-message",
            image_attachments=[{"url": url, "content_type": "image/png"}],
        )
        group_memory.record_group_message(
            "group",
            "quoting-sender",
            "引用图片",
            message_id="quote-message",
            reference_message_id="original-message",
            image_attachments=[{
                "url": url,
                "content_type": "image/png",
                "source": "引用消息图片",
                "relation": "引用消息",
            }],
        )

        images = group_memory.get_recent_group_image_attachments(
            "group", current_message_id="quote-message"
        )

        self.assertEqual({image["source_user_id"] for image in images}, {"original-sender"})
        quoted_preview = next(image for image in images if image["source"] == "引用消息图片")
        self.assertEqual(quoted_preview["quoted_by_user_id"], "quoting-sender")

    def test_quoted_image_without_original_author_stays_unknown(self):
        """原消息不在缓存时保留未知来源，不把引用者填成图片发送者。"""
        group_memory.record_group_message(
            "group",
            "quoting-sender",
            "引用图片",
            message_id="quote-message",
            reference_message_id="missing-original",
            image_attachments=[{
                "url": "https://multimedia.nt.qq.com.cn/download?token=hidden",
                "content_type": "image/png",
                "source": "引用消息图片",
                "relation": "引用消息",
            }],
        )

        images = group_memory.get_recent_group_image_attachments(
            "group", current_message_id="quote-message"
        )

        self.assertEqual(images[0]["source_message_id"], "missing-original")
        self.assertEqual(images[0]["source_user_id"], "")
        self.assertEqual(images[0]["quoted_by_user_id"], "quoting-sender")


if __name__ == "__main__":
    unittest.main()
