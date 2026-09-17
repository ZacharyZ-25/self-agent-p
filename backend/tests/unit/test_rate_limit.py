from __future__ import annotations

import pytest

from app.errors import AppError
from app.middleware.rate_limit import RateLimiter, client_ip_from_scope


@pytest.mark.asyncio
async def test_rate_limit_resets_after_window() -> None:
    now = [100.0]
    limiter = RateLimiter(1, 2, 1, clock=lambda: now[0])

    await limiter.check_ip("127.0.0.1")
    with pytest.raises(AppError, match="RATE_LIMITED"):
        await limiter.check_ip("127.0.0.1")

    now[0] += 61
    await limiter.check_ip("127.0.0.1")


@pytest.mark.asyncio
async def test_session_daily_limit() -> None:
    limiter = RateLimiter(10, 100, 1)
    await limiter.check_session("session")
    with pytest.raises(AppError, match="RATE_LIMITED"):
        await limiter.check_session("session")


@pytest.mark.asyncio
async def test_ip_daily_limit_blocks_the_sixteenth_round() -> None:
    now = [100.0]
    limiter = RateLimiter(10, 15, 50, clock=lambda: now[0])

    for _ in range(15):
        await limiter.check_ip("203.0.113.8")
        now[0] += 61

    with pytest.raises(AppError, match="RATE_LIMITED"):
        await limiter.check_ip("203.0.113.8")


def test_forwarded_ip_is_only_used_for_trusted_direct_proxy() -> None:
    scope = {
        "client": ("10.0.0.2", 1234),
        "headers": [(b"x-forwarded-for", b"203.0.113.8, 10.0.0.1")],
    }

    assert client_ip_from_scope(scope, set()) == "10.0.0.2"
    assert client_ip_from_scope(scope, {"10.0.0.1", "10.0.0.2"}) == "203.0.113.8"
