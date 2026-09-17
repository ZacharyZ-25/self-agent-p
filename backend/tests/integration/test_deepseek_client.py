from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.config import Settings
from app.errors import AppError
from app.services.deepseek_client import (
    DeepSeekClient,
    ProviderDelta,
    ProviderDone,
    ProviderUsage,
)


def settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "deepseek_api_key": "test-only-key",
        "deepseek_base_url": "https://deepseek.test",
        "deepseek_max_retries": 0,
        "deepseek_retry_base_seconds": 0,
        **overrides,
    }
    return Settings(**values)


def completion_body(content: str = "你好") -> dict[str, object]:
    return {
        "id": "chatcmpl_test",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


@pytest.mark.asyncio
@respx.mock
async def test_non_stream_request_uses_v4_non_thinking_contract() -> None:
    route = respx.post("https://deepseek.test/chat/completions").mock(
        return_value=httpx.Response(200, json=completion_body())
    )
    client = DeepSeekClient(settings())
    try:
        result = await client.complete(
            [{"role": "user", "content": "hello"}], "anonymous-session"
        )
    finally:
        await client.close()

    assert result.reply == "你好"
    assert result.usage.total_tokens == 12
    request_body = json.loads(route.calls[0].request.content)
    assert request_body["model"] == "deepseek-v4-flash"
    assert request_body["thinking"] == {"type": "disabled"}
    assert request_body["user_id"] == "anonymous-session"
    assert request_body["temperature"] == 0.6


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error

    async def aclose(self) -> None:
        self.closed = True


def chunk(data: dict[str, object]) -> bytes:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def delta_chunk(text: str, finish_reason: str | None = None) -> dict[str, object]:
    return {
        "id": "chatcmpl_test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "index": 0,
                "delta": {"content": text},
                "finish_reason": finish_reason,
            }
        ],
    }


@pytest.mark.asyncio
@respx.mock
async def test_stream_handles_keepalive_half_chunks_and_utf8_boundaries() -> None:
    first = chunk(delta_chunk("我最有"))
    second = chunk(delta_chunk("代表性", "stop"))
    usage = chunk(
        {
            "id": "chatcmpl_test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "deepseek-v4-flash",
            "choices": [],
            "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
        }
    )
    combined = b": keep-alive\n\n" + first + second + usage + b"data: [DONE]\n\n"
    split_at = combined.index("最".encode()) + 1
    upstream = ChunkedStream(
        [
            combined[:split_at],
            combined[split_at : split_at + 5],
            combined[split_at + 5 :],
        ]
    )
    respx.post("https://deepseek.test/chat/completions").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=upstream
        )
    )
    client = DeepSeekClient(settings())
    try:
        events = [
            event
            async for event in client.stream(
                [{"role": "user", "content": "hello"}], "session"
            )
        ]
    finally:
        await client.close()

    text = "".join(event.text for event in events if isinstance(event, ProviderDelta))
    usage_totals = [
        event.usage.total_tokens for event in events if isinstance(event, ProviderUsage)
    ]
    assert text == "我最有代表性"
    assert usage_totals == [9]
    assert events[-1] == ProviderDone("stop")
    assert upstream.closed is True


@pytest.mark.asyncio
@respx.mock
async def test_429_retries_before_content() -> None:
    route = respx.post("https://deepseek.test/chat/completions").mock(
        side_effect=[
            httpx.Response(429, json={"error": {"message": "rate limit"}}),
            httpx.Response(200, json=completion_body("retried")),
        ]
    )
    client = DeepSeekClient(settings(deepseek_max_retries=1))
    try:
        result = await client.complete([{"role": "user", "content": "hello"}], "session")
    finally:
        await client.close()

    assert result.reply == "retried"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_auth_error_is_mapped_without_leaking_upstream_body() -> None:
    respx.post("https://deepseek.test/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "secret upstream body"}})
    )
    client = DeepSeekClient(settings())
    try:
        with pytest.raises(AppError) as captured:
            await client.complete([{"role": "user", "content": "hello"}], "session")
    finally:
        await client.close()

    assert captured.value.code == "UPSTREAM_AUTH_FAILED"
    assert "secret upstream body" not in captured.value.message


@pytest.mark.asyncio
@respx.mock
async def test_stream_does_not_retry_after_first_delta() -> None:
    upstream = ChunkedStream(
        [chunk(delta_chunk("already sent"))],
        error=httpx.ReadError("connection dropped"),
    )
    route = respx.post("https://deepseek.test/chat/completions").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=upstream
        )
    )
    client = DeepSeekClient(settings(deepseek_max_retries=2))
    seen = []
    try:
        with pytest.raises(AppError) as captured:
            async for event in client.stream(
                [{"role": "user", "content": "hello"}], "session"
            ):
                seen.append(event)
    finally:
        await client.close()

    assert seen == [ProviderDelta("already sent")]
    assert captured.value.code == "UPSTREAM_UNAVAILABLE"
    assert route.call_count == 1


def test_timeout_keeps_public_error_code_but_has_metric_category() -> None:
    error = DeepSeekClient._map_exception(TimeoutError())

    assert error.code == "UPSTREAM_UNAVAILABLE"
    assert error.metric_category == "timeout"
