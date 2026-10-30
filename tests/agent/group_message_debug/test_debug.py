"""验证调试开关、原始与解析后字段对比，以及 SDK 接入。"""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from botpy.message import GroupMessage
from external_tools.qq.botpy_compat import install_group_message_parser_compat
from features import group_message_debug as debug


class GroupMessageDebugTests(unittest.TestCase):
    """不连接 QQ，仅使用合成消息定位字段丢失。"""

    def test_disabled_does_not_log(self):
        """默认关闭时不新增调试日志。"""
        with patch.object(debug, "QQ_GROUP_MESSAGE_DEBUG", False), patch.object(debug, "_log") as logger:
            debug.log_group_message_debug(None, {})
        logger.info.assert_not_called()

    def test_sdk_logs_raw_and_parsed_mentions_without_attachment_urls(self):
        """真实 SDK 构造链路显示 mentions 丢失，且不打印附件地址。"""
        install_group_message_parser_compat()
        payload = {
            "id": "debug-message", "group_openid": "group", "content": "hello",
            "mentions": [{"id": "target", "username": "niko"}],
            "attachments": [{"url": "https://example.invalid/private"}],
        }
        with patch.object(debug, "QQ_GROUP_MESSAGE_DEBUG", True), patch.object(debug, "_log") as logger:
            GroupMessage(None, "debug-event", payload)
        record = json.loads(logger.info.call_args.args[1])
        self.assertEqual(record["message_id"], "debug-message")
        self.assertEqual(record["raw_mentions"], [{"id": "target", "username": "niko"}])
        self.assertEqual(record["parsed_mentions"], [{"member_openid": None}])
        self.assertEqual(record["raw_content"], record["parsed_content"])
        self.assertNotIn("https://example.invalid/private", logger.info.call_args.args[1])

    def test_missing_mentions_and_invalid_elements_are_loggable(self):
        """平台未给提及、扩展元素异常时仍输出可判读记录。"""
        with patch.object(debug, "QQ_GROUP_MESSAGE_DEBUG", True), patch.object(debug, "_log") as logger:
            debug.log_group_message_debug(SimpleNamespace(content="hello"), {"msg_elements": 1})
        record = json.loads(logger.info.call_args.args[1])
        self.assertFalse(record["raw_mentions_present"])
        self.assertEqual(record["raw_element_keys"], [])
