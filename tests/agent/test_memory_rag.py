"""使用真实本地 Qdrant 和模拟 Embedding 测试 Agent 记忆工具。"""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from features.agent import memory
from features.agent.tools import execute_tool, visible_tools
from features.agent.tools.common import ToolContext


def call(name, args, user="A"):
    """通过真实工具注册入口调用记忆操作。"""
    return execute_tool({"function": {"name": name, "arguments": args}}, ToolContext(user_id=user, timeout_seconds=2))


class MemoryRagTests(unittest.TestCase):
    """以独立磁盘目录验证真实 Qdrant 读写与用户范围。"""

    def setUp(self):
        """配置临时目录和可预测的 Embedding 响应。"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.close_client)
        self.enterContext(patch.object(memory, "DB_PATH", Path(self.temp.name) / "memory"))
        self.enterContext(patch.object(memory, "AGENT_EMBEDDING_API_KEY", "test-key"))
        self.enterContext(patch.object(memory, "AGENT_EMBEDDING_MODEL", "test-model"))
        self.post = self.enterContext(patch.object(memory.requests, "post"))
        self.vector([1.0, 0.0])

    def close_client(self):
        """释放本地数据库锁，以便验证重新打开和清理临时目录。"""
        if memory._client is not None:
            memory._client.close()
            memory._client = None

    def vector(self, values):
        """更换模拟服务返回的向量。"""
        self.post.return_value = Mock(json=lambda: {"data": [{"embedding": values}]})

    def test_shared_store_persistence_and_filtered_deletion(self):
        """保存当前用户归属，重启后可跨用户查询，只删除指定用户的相似记忆。"""
        self.assertTrue({"add_memory", "search_memory", "delete_memory"}.issubset(
            {item["function"]["name"] for item in visible_tools("A")}))
        self.assertEqual(call("add_memory", {"content": "B 喜欢咖啡"}, "A").data["user_id"], "A")
        call("add_memory", {"content": "A 喜欢咖啡"}, "A")
        call("add_memory", {"content": "喜欢咖啡"}, "B")
        self.vector([0.0, 1.0])
        call("add_memory", {"content": "喜欢喝茶"}, "A")
        self.close_client()
        self.vector([1.0, 0.0])
        self.assertEqual(len(call("search_memory", {"query": "咖啡"}, "C").data["items"]), 4)
        self.assertEqual(len(call("search_memory", {"query": "咖啡", "user_id": "A"}).data["items"]), 3)
        result = call("delete_memory", {"user_id": "A", "query": "咖啡"}, "C")
        self.assertEqual(result.data["deleted_count"], 2)
        remaining = call("search_memory", {"query": "咖啡"}).data["items"]
        self.assertEqual({item["content"] for item in remaining}, {"喜欢喝茶", "喜欢咖啡"})
        self.assertEqual(self.post.call_args.kwargs["json"]["encoding_format"], "float")

    def test_delete_all_batches(self):
        """匹配数量超过单批大小时继续删除直到没有匹配。"""
        with patch.object(memory, "DELETE_BATCH_SIZE", 2):
            for index in range(5):
                self.assertTrue(call("add_memory", {"content": str(index)}).ok)
            result = call("delete_memory", {"user_id": "A", "query": "删除"})
            self.assertEqual(result.data["deleted_count"], 5)
            self.assertEqual(call("search_memory", {"query": "删除"}).data["items"], [])

    def test_threshold_and_threaded_access(self):
        """跨线程操作受锁保护，阈值两侧的记忆分别保留和删除。"""
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.vector([0.84, math.sqrt(1 - 0.84 ** 2)])
            self.assertTrue(pool.submit(call, "add_memory", {"content": "不匹配"}).result().ok)
            self.vector([0.86, math.sqrt(1 - 0.86 ** 2)])
            self.assertTrue(pool.submit(call, "add_memory", {"content": "匹配"}).result().ok)
            self.vector([1.0, 0.0])
            self.assertEqual(pool.submit(call, "delete_memory", {"user_id": "A", "query": "删除"}).result().data["deleted_count"], 1)
            self.assertEqual([item["content"] for item in call("search_memory", {"query": "查询"}).data["items"]], ["不匹配"])

    def test_model_and_dimension_boundaries(self):
        """不同模型记忆互不检索或删除，维度变化不覆盖已有数据。"""
        call("add_memory", {"content": "记忆"})
        with patch.object(memory, "AGENT_EMBEDDING_MODEL", "other"):
            self.assertEqual(call("search_memory", {"query": "记忆"}).data["items"], [])
            self.assertEqual(call("delete_memory", {"user_id": "A", "query": "记忆"}).data["deleted_count"], 0)
        self.vector([1.0, 0.0, 0.0])
        self.assertEqual(call("search_memory", {"query": "记忆"}).code, "memory_dimension_mismatch")
        self.vector([1.0, 0.0])
        self.assertEqual(len(call("search_memory", {"query": "记忆"}).data["items"]), 1)

    def test_invalid_embedding_and_host_identity(self):
        """拒绝模型伪造归属，不写入无效向量并报告缺少配置。"""
        self.assertEqual(call("add_memory", {"content": "内容", "user_id": "B"}).code, "invalid_arguments")
        self.vector([float("nan")])
        self.assertEqual(call("add_memory", {"content": "无效"}).code, "embedding_unavailable")
        with patch.object(memory, "AGENT_EMBEDDING_API_KEY", ""):
            self.assertEqual(call("search_memory", {"query": "内容"}).code, "embedding_not_configured")

    def test_rag_descriptions_and_access_denied(self):
        """模型可识别记忆工具属于 RAG，HTTP 权限拒绝得到明确状态。"""
        descriptions = {item["function"]["name"]: item["function"]["description"] for item in visible_tools("A")}
        self.assertTrue(all("RAG" in descriptions[name] for name in ("add_memory", "search_memory", "delete_memory")))
        response = Mock(status_code=403)
        self.post.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)
        self.assertEqual(call("search_memory", {"query": "内容"}).code, "embedding_access_denied")


if __name__ == "__main__":
    unittest.main()
