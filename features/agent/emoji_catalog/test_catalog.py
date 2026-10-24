"""验证收藏目录分页、按 ID 选择与换图衔接，不调用真实模型或 QQ。"""

import base64
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from external_tools.storage import group_memory
from features.agent.emojipic.library import EmojiLibrary
from features.agent.reply_memory import record_bot_reply
from features.agent.service import _agent_reply_with_emoji, _emoji_tool_result, _tool_result


class CatalogTests(unittest.TestCase):
    """使用临时收藏库验证浏览到发送的选择行为。"""

    def setUp(self):
        """建立包含两个 GIF 和一个 PNG 的隔离收藏库。"""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.library = EmojiLibrary(Path(directory.name))
        self.items = []
        for fmt, color, category in (("GIF", "red", "happy"), ("PNG", "green", "happy"),
                                      ("GIF", "blue", "sad")):
            output = BytesIO()
            Image.new("RGB", (2, 2), color).save(output, format=fmt)
            data = f"data:image/{fmt.lower()};base64," + base64.b64encode(output.getvalue()).decode()
            self.items.append(self.library.save(data, category, color, [color], {}))
        for patcher in (
            patch("features.agent.emojipic._LIBRARY", self.library),
            patch.object(group_memory, "_messages_by_group", group_memory.OrderedDict()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_registered_browse_tool_pages_without_keywords(self):
        """普通用户无需检索词即可浏览，分页没有遗漏或重复，结果不含路径。"""
        pages = []
        for page in (1, 2):
            result = _tool_result({"function": {"name": "list_emoji_images", "arguments": {
                "page": page, "page_size": 2,
            }}}, "看看收藏", "ordinary-user", {"group_id": "g"})
            pages.append(json.loads(result))
        self.assertEqual(pages[0]["total"], 3)
        self.assertEqual(pages[0]["total_pages"], 2)
        self.assertTrue(pages[0]["has_more"])
        self.assertFalse(pages[1]["has_more"])
        items = pages[0]["items"] + pages[1]["items"]
        self.assertEqual({item["id"] for item in items}, {item["id"] for item in self.items})
        self.assertEqual(len(items), 3)
        self.assertEqual(set(items[0]), {"id", "category", "name", "tags", "format"})

    def test_filters_empty_pages_and_invalid_parameters(self):
        """格式和分类筛选影响总数；空页明确返回，拒绝错误分页类型。"""
        result = json.loads(_emoji_tool_result("list_emoji_images", {"gif_only": True, "category": "happy"}, {}))
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["format"], "gif")
        self.assertEqual(json.loads(_emoji_tool_result("list_emoji_images", {"page": 99}, {}))["items"], [])
        self.assertEqual(json.loads(_emoji_tool_result("list_emoji_images", {"category": "absent"}, {}))["total"], 0)
        for args in ({"page": True}, {"page": 0}, {"page_size": 21}, {"gif_only": "true"}, {"category": []}):
            with self.subTest(args=args):
                self.assertIn("浏览失败", _emoji_tool_result("list_emoji_images", args, {}))

    def test_exact_id_does_not_repeat_search_and_only_selects_once(self):
        """指定 ID 后不再检索，即使附带其他关键词也发送所选图。"""
        context = {"group_id": "g"}
        with patch("features.agent.service.search_emoji_images") as search:
            _emoji_tool_result("send_emoji_image", {"image_id": self.items[2]["id"], "query": "happy"}, context)
            search.assert_not_called()
        reply = _agent_reply_with_emoji("hello", context["pending_emoji_images"])
        self.assertEqual(reply.emoji_metadata["id"], self.items[2]["id"])
        self.assertEqual(reply.emoji_image_path, Path(self.items[2]["file_path"]))
        _emoji_tool_result("send_emoji_image", {"image_id": self.items[0]["id"]}, context)
        self.assertEqual(len(context["pending_emoji_images"]), 1)

    def test_invalid_id_missing_file_and_gif_mismatch_do_not_fallback(self):
        """不存在的 ID、路径输入、丢失的文件和错误格式均不改发其他图片。"""
        Path(self.items[0]["file_path"]).unlink()
        for args in ({"image_id": "unknown"}, {"image_id": "../../image.png"},
                     {"image_id": self.items[0]["id"]},
                     {"image_id": self.items[1]["id"], "gif_only": True}):
            context = {"group_id": "g"}
            with self.subTest(args=args):
                self.assertIn("失败", _emoji_tool_result("send_emoji_image", args, context))
                self.assertEqual(context["pending_emoji_images"], [])
        self.assertEqual(self.library.list_images()["total"], 2)

    def test_browsed_image_can_be_replaced_without_keywords(self):
        """浏览后按 ID 发出的静态图，也能无关键词换成另一张。"""
        context = {"group_id": "g"}
        _emoji_tool_result("send_emoji_image", {"image_id": self.items[1]["id"]}, context)
        reply = _agent_reply_with_emoji("", context["pending_emoji_images"])
        record_bot_reply("g", "", {"id": "sent"}, emoji=reply.emoji_metadata)
        replacement = {"group_id": "g"}
        _emoji_tool_result("send_emoji_image", {"replace_previous": True}, replacement)
        self.assertNotEqual(replacement["pending_emoji_images"][0]["id"], self.items[1]["id"])
        duplicate = {"group_id": "g"}
        result = _emoji_tool_result("send_emoji_image", {
            "image_id": self.items[1]["id"], "replace_previous": True,
        }, duplicate)
        self.assertIn("上一张", result)
        self.assertEqual(duplicate["pending_emoji_images"], [])
