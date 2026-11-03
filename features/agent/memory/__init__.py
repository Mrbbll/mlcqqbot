"""使用本地 Qdrant 持久化长期记忆，并通过外部服务生成检索向量。"""

from datetime import datetime, timezone
import math
from pathlib import Path
from threading import RLock
from uuid import uuid4

import requests

from config import AGENT_EMBEDDING_API_KEY, AGENT_EMBEDDING_MODEL, AGENT_EMBEDDING_URL, PROJECT_ROOT


DB_PATH = Path(PROJECT_ROOT).parent / "agent_memory_qdrant"
COLLECTION = "memories"
DELETE_THRESHOLD = 0.85
DELETE_BATCH_SIZE = 256
_lock = RLock()
_client = None


class MemoryError(Exception):
    """表示记忆存储或 Embedding 服务不可用。"""


def _embedding(text: str, timeout: float) -> list[float]:
    """请求外部服务生成向量；不向调用者暴露响应正文和凭证。"""
    if not AGENT_EMBEDDING_URL or not AGENT_EMBEDDING_MODEL or not AGENT_EMBEDDING_API_KEY:
        raise MemoryError("embedding_not_configured")
    try:
        response = requests.post(AGENT_EMBEDDING_URL, headers={"Authorization": f"Bearer {AGENT_EMBEDDING_API_KEY}"},
                                 json={"model": AGENT_EMBEDDING_MODEL, "input": [text], "encoding_format": "float"},
                                 timeout=timeout)
        response.raise_for_status()
        vector = response.json()["data"][0]["embedding"]
        if not isinstance(vector, list) or not vector or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
            raise ValueError("invalid vector")
        values = [float(v) for v in vector]
        if not math.isfinite(math.hypot(*values)) or not math.hypot(*values):
            raise ValueError("invalid vector magnitude")
        return values
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (401, 403):
            raise MemoryError("embedding_access_denied") from exc
        raise MemoryError("embedding_unavailable") from exc
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        raise MemoryError("embedding_unavailable") from exc


def _store(dimension: int):
    """复用进程内本地客户端，并验证单个集合的向量维度。调用方须持锁。"""
    global _client
    try:
        from qdrant_client import QdrantClient, models

        if _client is None:
            DB_PATH.mkdir(parents=True, exist_ok=True)
            # Agent 工具在线程池执行；所有客户端访问均由模块锁串行化。
            _client = QdrantClient(path=str(DB_PATH), force_disable_check_same_thread=True)
        if not _client.collection_exists(COLLECTION):
            _client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE))
        config = _client.get_collection(COLLECTION).config.params.vectors
        if not isinstance(config, models.VectorParams) or config.size != dimension:
            raise MemoryError("memory_dimension_mismatch")
        return _client, models
    except ImportError as exc:
        raise MemoryError("memory_dependency_missing") from exc
    except MemoryError:
        raise
    except Exception as exc:
        raise MemoryError("memory_store_unavailable") from exc


def _filter(models, user_id: str = ""):
    """按当前 Embedding 模型过滤，必要时限制记忆所属用户。"""
    conditions = [models.FieldCondition(key="model", match=models.MatchValue(value=AGENT_EMBEDDING_MODEL))]
    if user_id:
        conditions.append(models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)))
    return models.Filter(must=conditions)


def add(user_id: str, content: str, timeout: float) -> dict:
    """将当前发言者的一条记忆及向量保存在统一集合中。"""
    if not user_id.strip():
        raise ValueError("missing user")
    vector = _embedding(content, timeout)
    record = {"user_id": user_id, "content": content, "created_at": datetime.now(timezone.utc).isoformat(),
              "model": AGENT_EMBEDDING_MODEL}
    with _lock:
        client, models = _store(len(vector))
        try:
            client.upsert(COLLECTION, points=[models.PointStruct(id=str(uuid4()), vector=vector, payload=record)], wait=True)
        except Exception as exc:
            raise MemoryError("memory_store_unavailable") from exc
    return {key: record[key] for key in ("user_id", "content", "created_at")}


def search(query: str, limit: int, timeout: float, user_id: str = "") -> list[dict]:
    """按语义查询全部用户或指定用户的当前模型记忆。"""
    vector = _embedding(query, timeout)
    with _lock:
        client, models = _store(len(vector))
        try:
            result = client.query_points(COLLECTION, query=vector, query_filter=_filter(models, user_id),
                                         limit=limit, with_payload=True).points
        except Exception as exc:
            raise MemoryError("memory_store_unavailable") from exc
    return [{"user_id": item.payload["user_id"], "content": item.payload["content"],
             "created_at": item.payload["created_at"], "score": round(item.score, 6)} for item in result]


def delete(user_id: str, query: str, timeout: float) -> int:
    """删除指定用户下所有与查询相似度不低于阈值的当前模型记忆。"""
    if not user_id.strip():
        raise ValueError("missing user")
    vector = _embedding(query, timeout)
    deleted = 0
    with _lock:
        client, models = _store(len(vector))
        try:
            while True:
                points = client.query_points(COLLECTION, query=vector, query_filter=_filter(models, user_id),
                                             score_threshold=DELETE_THRESHOLD, limit=DELETE_BATCH_SIZE,
                                             with_payload=False).points
                if not points:
                    return deleted
                client.delete(COLLECTION, points_selector=models.PointIdsList(points=[point.id for point in points]), wait=True)
                deleted += len(points)
        except Exception as exc:
            raise MemoryError("memory_delete_incomplete") from exc
