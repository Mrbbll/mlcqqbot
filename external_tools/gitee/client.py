"""Gitee REST API 的异步 HTTP 适配器。"""
import logging
import time
from typing import Any

import httpx


_API_BASE_URL = "https://gitee.com/api/v5"
_log = logging.getLogger("mlcbot")


class GiteeHTTPStatusError(RuntimeError):
    """保存 Gitee HTTP 错误状态码，不包含可能带 Token 的请求 URL。"""

    def __init__(self, status_code: int) -> None:
        """初始化仅含状态码的安全错误信息。"""
        super().__init__(f"Gitee API returned HTTP {status_code}")
        self.status_code = status_code


class GiteeApiClient:
    """管理 Gitee HTTP 会话、认证参数和限流冷却时间。"""

    def __init__(self, token: str, timeout: int) -> None:
        """保存连接配置；实际 HTTP 会话在 start 时创建。"""
        self._token = token.strip()
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self.retry_after = 0.0

    async def start(self) -> None:
        """创建 Gitee API 异步 HTTP 会话。"""
        params = {"access_token": self._token} if self._token else {}
        self._client = httpx.AsyncClient(
            headers={
                "Accept": "application/json",
                "User-Agent": "mlcbot-gitee-monitor",
            },
            params=params,
            timeout=self._timeout,
        )

    async def close(self) -> None:
        """关闭并清理异步 HTTP 会话。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """请求 Gitee API；遇到限流时记录冷却时间。"""
        if self._client is None:
            raise RuntimeError("Gitee API client is not started")

        response = await self._client.get(f"{_API_BASE_URL}{path}", **kwargs)
        if self._is_rate_limited(response):
            self._record_rate_limit(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GiteeHTTPStatusError(response.status_code) from exc
        return response

    @staticmethod
    def _is_rate_limited(response: httpx.Response) -> bool:
        """识别 Gitee 返回的限流响应。"""
        return response.status_code == 429 or (
            response.status_code == 403
            and (
                response.headers.get("X-RateLimit-Remaining") == "0"
                or "Retry-After" in response.headers
                or "rate limit" in response.text.lower()
            )
        )

    def _record_rate_limit(self, response: httpx.Response) -> None:
        """解析限流等待时间并保存下次允许请求的时间。"""
        delay = 60.0
        try:
            delay = max(delay, float(response.headers.get("Retry-After", "0")))
            if response.headers.get("X-RateLimit-Remaining") == "0":
                delay = max(
                    delay,
                    float(response.headers.get("X-RateLimit-Reset", "0"))
                    - time.time()
                    + 1,
                )
        except ValueError:
            pass
        self.retry_after = time.time() + delay
        _log.warning("[gitee] Gitee API 限流，暂停请求 %s 秒", int(delay))
