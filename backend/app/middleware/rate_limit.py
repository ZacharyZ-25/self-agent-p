from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.errors import AppError, error_payload


@dataclass(slots=True)
class WindowCounter:
    started_at: float
    count: int


class RateLimiter:
    """Single-process fixed-window limiter for the single-instance MVP."""

    def __init__(
        self,
        per_minute: int,
        per_day: int,
        session_per_day: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self.session_per_day = session_per_day
        self._clock = clock
        self._counters: dict[tuple[str, str], WindowCounter] = {}
        self._lock = asyncio.Lock()

    async def check_ip(self, client_ip: str) -> None:
        async with self._lock:
            now = self._clock()
            self._consume("ip_minute", client_ip, 60.0, self.per_minute, now)
            self._consume("ip_day", client_ip, 86400.0, self.per_day, now)

    async def check_session(self, session_id: str) -> None:
        async with self._lock:
            self._consume(
                "session_day",
                session_id,
                86400.0,
                self.session_per_day,
                self._clock(),
            )

    def _consume(
        self,
        scope: str,
        key: str,
        window_seconds: float,
        limit: int,
        now: float,
    ) -> None:
        counter_key = (scope, key)
        counter = self._counters.get(counter_key)
        if counter is None or now - counter.started_at >= window_seconds:
            self._counters[counter_key] = WindowCounter(now, 1)
            return
        if counter.count >= limit:
            raise AppError(
                code="RATE_LIMITED",
                message="请求过于频繁，请稍后再试。",
                status_code=429,
                retryable=True,
            )
        counter.count += 1


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter,
        trusted_proxies: set[str] | None = None,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.trusted_proxies = trusted_proxies or set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in {"/api/v1/chat", "/api/v1/chat/stream"}
        ):
            await self.app(scope, receive, send)
            return
        try:
            await self.limiter.check_ip(client_ip_from_scope(scope, self.trusted_proxies))
        except AppError as error:
            request_id = scope.get("state", {}).get("request_id", "req_unknown")
            response = JSONResponse(
                error_payload(request_id, error),
                status_code=error.status_code,
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def client_ip_from_scope(scope: Scope, trusted_proxies: set[str]) -> str:
    direct_ip = scope.get("client", ("unknown", 0))[0] or "unknown"
    if direct_ip not in trusted_proxies:
        return direct_ip
    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1")
    chain = [item.strip() for item in forwarded.split(",") if item.strip()]
    chain.append(direct_ip)
    for address in reversed(chain):
        if address not in trusted_proxies:
            return address
    return chain[0] if chain else direct_ip
