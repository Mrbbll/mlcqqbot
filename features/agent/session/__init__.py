"""提供按群、用户和权限隔离的有界短期工具执行记忆。"""

from collections import OrderedDict, deque
from copy import deepcopy
import json
import time


SESSION_TTL_SECONDS = 600
MAX_SESSIONS = 64
MAX_TURNS = 4
MAX_SESSION_CHARS = 12000
MAX_TURN_CHARS = 3000
_sessions = OrderedDict()


def _prune(now: float) -> None:
    """清理失效会话及会话中已过期的单轮记录。"""
    for key, turns in list(_sessions.items()):
        while turns and now - turns[0][0] >= SESSION_TTL_SECONDS:
            turns.popleft()
        if not turns:
            _sessions.pop(key, None)


def get_execution_history(group_id: str, user_id: str, privileged: bool) -> list[dict]:
    """获取当前身份的执行事实副本，不返回其他身份或群的记录。"""
    _prune(time.monotonic())
    key = (group_id, user_id, privileged)
    # 权限变化时丢弃旧身份记录，防止恢复权限后取回过时授权背景。
    _sessions.pop((group_id, user_id, not privileged), None)
    turns = _sessions.get(key)
    if not turns:
        return []
    _sessions.move_to_end(key)
    return deepcopy([turn[1] for turn in turns])


def remember_execution(group_id: str, user_id: str, privileged: bool,
                       question: str, results: list[dict]) -> None:
    """保存发送者 ID 及实际工具执行记录；不保存待发送回复、图片或工具参数。"""
    if not results:
        return
    now = time.monotonic()
    _prune(now)
    key = (group_id, user_id, privileged)
    _sessions.pop((group_id, user_id, not privileged), None)
    turns = _sessions.setdefault(key, deque(maxlen=MAX_TURNS))
    # 每轮分别限定问题及工具文本，避免单次任务占满会话。
    remaining = MAX_TURN_CHARS - min(len(question), 600)
    records = []
    for result in results:
        if remaining <= 0:
            break
        text = result["result"]
        limit = min(remaining, 1000)
        if len(text) > limit:
            marker = "[执行记录已截断]"
            text = text[:max(0, limit - len(marker))] + marker
        records.append({"tool": result["tool"], "result": text})
        remaining -= len(text)
    turn = {"user_id": user_id, "question": question[:600], "results": records}
    while len(json.dumps(turn, ensure_ascii=False)) > MAX_TURN_CHARS and records:
        records.pop()
    turns.append((now, turn))
    while len(json.dumps([turn[1] for turn in turns], ensure_ascii=False)) > MAX_SESSION_CHARS:
        turns.popleft()
    _sessions.move_to_end(key)
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)
