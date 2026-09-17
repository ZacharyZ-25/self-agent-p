from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from app.config import Settings
from app.errors import AppError
from app.models.common import TokenUsage
from app.services.provider import (
    ProviderDelta,
    ProviderDone,
    ProviderEvent,
    ProviderResult,
    ProviderUsage,
)


class DeepSeekClient:
    """OpenAI-compatible DeepSeek adapter with product-owned retry and timeout rules."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncOpenAI | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not settings.has_deepseek_key and client is None:
            raise ValueError("A DeepSeek API key is required")
        self.settings = settings
        self._sleep = sleep
        self._client = client or AsyncOpenAI(
            api_key=settings.deepseek_api_key.get_secret_value(),  # type: ignore[union-attr]
            base_url=settings.deepseek_base_url,
            timeout=httpx.Timeout(
                connect=settings.deepseek_connect_timeout_seconds,
                read=settings.deepseek_request_timeout_seconds,
                write=settings.deepseek_connect_timeout_seconds,
                pool=settings.deepseek_connect_timeout_seconds,
            ),
            max_retries=0,
        )

    async def close(self) -> None:
        await self._client.close()

    async def complete(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> ProviderResult:
        for attempt in range(self.settings.deepseek_max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        **self._request_kwargs(messages, user_id),
                        stream=False,
                    ),
                    timeout=self.settings.deepseek_request_timeout_seconds,
                )
                reply = response.choices[0].message.content if response.choices else None
                if not reply:
                    raise AppError(
                        code="UPSTREAM_INVALID_RESPONSE",
                        message="AI 服务返回了无效响应，请稍后再试。",
                        status_code=502,
                        retryable=True,
                    )
                finish_reason = (
                    str(response.choices[0].finish_reason or "stop")
                    if response.choices
                    else "stop"
                )
                return ProviderResult(
                    reply=reply,
                    model=response.model or self.settings.deepseek_model,
                    usage=self._usage(response.usage),
                    finish_reason=finish_reason,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = exc if isinstance(exc, AppError) else self._map_exception(exc)
                if attempt >= self.settings.deepseek_max_retries or not error.retryable:
                    raise error from None
                await self._backoff(attempt)
        raise AssertionError("retry loop exhausted")

    async def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]:
        total_deadline = time.monotonic() + self.settings.deepseek_stream_total_timeout_seconds
        for attempt in range(self.settings.deepseek_max_retries + 1):
            raw_stream: Any = None
            emitted = False
            finish_reason = "stop"
            first_deadline = min(
                total_deadline,
                time.monotonic() + self.settings.deepseek_stream_first_token_timeout_seconds,
            )
            try:
                raw_stream = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        **self._request_kwargs(messages, user_id),
                        stream=True,
                        stream_options={"include_usage": True},
                    ),
                    timeout=self._remaining(first_deadline),
                )
                iterator = raw_stream.__aiter__()
                while True:
                    deadline = (
                        min(
                            total_deadline,
                            time.monotonic()
                            + self.settings.deepseek_stream_idle_timeout_seconds,
                        )
                        if emitted
                        else first_deadline
                    )
                    try:
                        chunk = await asyncio.wait_for(
                            iterator.__anext__(), timeout=self._remaining(deadline)
                        )
                    except StopAsyncIteration:
                        break

                    if chunk.usage is not None:
                        yield ProviderUsage(self._usage(chunk.usage))
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        finish_reason = str(choice.finish_reason)
                    text = choice.delta.content
                    if text:
                        emitted = True
                        yield ProviderDelta(text)

                if not emitted:
                    raise AppError(
                        code="UPSTREAM_INVALID_RESPONSE",
                        message="AI 服务返回了无效响应，请稍后再试。",
                        status_code=502,
                        retryable=True,
                    )
                yield ProviderDone(finish_reason)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = exc if isinstance(exc, AppError) else self._map_exception(exc)
                if emitted or attempt >= self.settings.deepseek_max_retries or not error.retryable:
                    raise error from None
                await self._backoff(attempt)
            finally:
                if raw_stream is not None:
                    await raw_stream.close()
        raise AssertionError("retry loop exhausted")

    def _request_kwargs(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": list(messages),
            "max_tokens": self.settings.deepseek_max_output_tokens,
            "extra_body": {
                "thinking": {
                    "type": "enabled"
                    if self.settings.deepseek_thinking_enabled
                    else "disabled"
                },
                "user_id": user_id,
            },
        }
        if not self.settings.deepseek_thinking_enabled:
            kwargs["temperature"] = self.settings.deepseek_temperature
        return kwargs

    async def _backoff(self, attempt: int) -> None:
        base = self.settings.deepseek_retry_base_seconds * (2**attempt)
        delay = base + random.uniform(0, base / 2 if base else 0)
        if delay:
            await self._sleep(delay)

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        return remaining

    @staticmethod
    def _usage(usage: Any) -> TokenUsage:
        if usage is None:
            return TokenUsage()
        return TokenUsage(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        )

    @staticmethod
    def _map_exception(exc: Exception) -> AppError:
        if isinstance(exc, APIStatusError):
            status_code = exc.status_code
            if status_code in {400, 422}:
                return AppError(
                    "UPSTREAM_REQUEST_INVALID",
                    "服务配置异常，请稍后再试。",
                    502,
                    False,
                )
            if status_code == 401:
                return AppError(
                    "UPSTREAM_AUTH_FAILED", "服务暂时不可用。", 503, False
                )
            if status_code == 402:
                return AppError(
                    "UPSTREAM_BALANCE_EMPTY", "服务额度暂时不可用。", 503, False
                )
            if status_code == 429:
                return AppError(
                    "UPSTREAM_RATE_LIMITED", "当前请求较多，请稍后再试。", 503, True
                )
            if status_code >= 500:
                return AppError(
                    "UPSTREAM_UNAVAILABLE", "AI 服务暂时不可用。", 503, True
                )
        if isinstance(exc, APIResponseValidationError):
            return AppError(
                "UPSTREAM_INVALID_RESPONSE",
                "AI 服务返回了无效响应，请稍后再试。",
                502,
                True,
            )
        if isinstance(exc, (APITimeoutError, TimeoutError, httpx.TimeoutException)):
            return AppError(
                "UPSTREAM_UNAVAILABLE",
                "AI 服务暂时不可用。",
                503,
                True,
                metric_category="timeout",
            )
        if isinstance(exc, (APIConnectionError, httpx.HTTPError)):
            return AppError(
                "UPSTREAM_UNAVAILABLE", "AI 服务暂时不可用。", 503, True
            )
        if isinstance(exc, APIError):
            return AppError(
                "UPSTREAM_UNAVAILABLE", "AI 服务暂时不可用。", 503, True
            )
        return AppError(
            "UPSTREAM_UNAVAILABLE", "AI 服务暂时不可用。", 503, True
        )
