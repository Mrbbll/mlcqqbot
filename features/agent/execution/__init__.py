"""限制 Agent 工具结果大小，并协调单会话串行及全局并发。"""

import asyncio
from contextlib import asynccontextmanager
from weakref import WeakKeyDictionary


MAX_CONCURRENT_RUNS = 4
MAX_PENDING_RUNS = 64
_states = WeakKeyDictionary()


class AgentBusyError(RuntimeError):
    """表示 Agent 执行和等待中的请求数量已达到上限。"""


async def run_blocking(function, *args):
    """等待线程真实结束再传播取消，防止释放配额后后台工具仍在执行。"""
    future = asyncio.get_running_loop().run_in_executor(None, function, *args)
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        while not future.done():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        # 消费后台异常；取消不能被线程异常替代。
        if future.done() and not future.cancelled():
            future.exception()
        raise


@asynccontextmanager
async def agent_slot(group_id: str, user_id: str):
    """按事件循环管理执行配额，异常或取消时归还锁与等待名额。"""
    loop = asyncio.get_running_loop()
    state = _states.get(loop)
    if state is None:
        state = {"semaphore": asyncio.Semaphore(MAX_CONCURRENT_RUNS), "locks": {}, "pending": 0}
        _states[loop] = state
    if state["pending"] >= MAX_PENDING_RUNS:
        raise AgentBusyError("Agent 正忙，请稍后再试。")
    key = (group_id, user_id)
    locks = state["locks"]
    entry = locks.setdefault(key, {"lock": asyncio.Lock(), "users": 0})
    entry["users"] += 1
    state["pending"] += 1
    try:
        # 等待同会话时不占用全局执行名额。
        async with entry["lock"]:
            async with state["semaphore"]:
                yield
    finally:
        entry["users"] -= 1
        state["pending"] -= 1
        if not entry["users"]:
            locks.pop(key, None)
        if not state["pending"]:
            _states.pop(loop, None)
