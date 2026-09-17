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
from app.services.provider import (
    ProviderConfig,
    ProviderDelta,
    ProviderDone,
    ProviderEvent,
    ProviderResult,
    ProviderUsage,
)


def provider_config_from_settings(settings: Settings) -> ProviderConfig:
    """Resolve generic settings while preserving legacy DeepSeek variables."""

    api_key = settings.resolved_llm_api_key
    extra_body: dict[str, Any] = {}
    if settings.llm_provider == "deepseek":
        extra_body = {
            "thinking": {
                "type": "enabled" if settings.resolved_llm_thinking_enabled else "disabled"
            },
            "user_id": "",
        }
    elif settings.llm_provider in {"local", "llama_cpp"}:
        extra_body = {
            "chat_template_kwargs": {
                "enable_thinking": settings.resolved_llm_thinking_enabled
            }
        }

    return ProviderConfig(
        provider=settings.llm_provider,
        api_key=api_key.get_secret_value() if api_key is not None else None,
        base_url=settings.resolved_llm_base_url,
        model=settings.resolved_llm_model,
        thinking_enabled=settings.resolved_llm_thinking_enabled,
        max_output_tokens=settings.resolved_llm_max_output_tokens,
        temperature=settings.resolved_llm_temperature,
        connect_timeout_seconds=settings.resolved_llm_connect_timeout_seconds,
        request_timeout_seconds=settings.resolved_llm_request_timeout_seconds,
        stream_first_token_timeout_seconds=settings.resolved_llm_stream_first_token_timeout_seconds,
        stream_idle_timeout_seconds=settings.resolved_llm_stream_idle_timeout_seconds,
        stream_total_timeout_seconds=settings.resolved_llm_stream_total_timeout_seconds,
        max_retries=settings.resolved_llm_max_retries,
        retry_base_seconds=settings.resolved_llm_retry_base_seconds,
        extra_body=extra_body,
    )


class OpenAICompatibleClient:
    """Provider adapter for local and remote OpenAI-compatible chat APIs."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        client: AsyncOpenAI | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        self._sleep = sleep
        self._client = client or AsyncOpenAI(
            api_key=config.api_key or "local-only",
            base_url=config.base_url,
            timeout=httpx.Timeout(
                connect=config.connect_timeout_seconds,
                read=config.request_timeout_seconds,
                write=config.connect_timeout_seconds,
                pool=config.connect_timeout_seconds,
            ),
            max_retries=0,
        )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        client: AsyncOpenAI | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> OpenAICompatibleClient:
        return cls(provider_config_from_settings(settings), client=client, sleep=sleep)

    async def close(self) -> None:
        await self._client.close()

    async def complete(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> ProviderResult:
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        **self._request_kwargs(messages, user_id),
                        stream=False,
                    ),
                    timeout=self.config.request_timeout_seconds,
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
                    model=response.model or self.config.model,
                    usage=self._usage(response.usage),
                    finish_reason=finish_reason,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = exc if isinstance(exc, AppError) else self._map_exception(exc)
                if attempt >= self.config.max_retries or not error.retryable:
                    raise error from None
                await self._backoff(attempt)
        raise AssertionError("retry loop exhausted")

    async def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]:
        total_deadline = time.monotonic() + self.config.stream_total_timeout_seconds
        for attempt in range(self.config.max_retries + 1):
            raw_stream: Any = None
            emitted = False
            finish_reason = "stop"
            first_deadline = min(
                total_deadline,
                time.monotonic() + self.config.stream_first_token_timeout_seconds,
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
                            time.monotonic() + self.config.stream_idle_timeout_seconds,
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
                if emitted or attempt >= self.config.max_retries or not error.retryable:
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
            "model": self.config.model,
            "messages": list(messages),
            "max_tokens": self.config.max_output_tokens,
        }
        extra_body = dict(self.config.extra_body)
        if self.config.provider == "deepseek":
            extra_body["user_id"] = user_id
        if extra_body:
            kwargs["extra_body"] = extra_body
        if not self.config.thinking_enabled:
            kwargs["temperature"] = self.config.temperature
        return kwargs

    async def _backoff(self, attempt: int) -> None:
        base = self.config.retry_base_seconds * (2**attempt)
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
    def _usage(usage: Any) -> Any:
        from app.models.common import TokenUsage

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
                    "UPSTREAM_REQUEST_INVALID", "服务配置异常，请稍后再试。", 502, False
                )
            if status_code == 401:
                return AppError("UPSTREAM_AUTH_FAILED", "服务暂时不可用。", 503, False)
            if status_code == 402:
                return AppError("UPSTREAM_BALANCE_EMPTY", "服务额度暂时不可用。", 503, False)
            if status_code == 429:
                return AppError("UPSTREAM_RATE_LIMITED", "当前请求较多，请稍后再试。", 503, True)
            if status_code >= 500:
                return AppError("UPSTREAM_UNAVAILABLE", "AI 服务暂时不可用。", 503, True)
        if isinstance(exc, APIResponseValidationError):
            return AppError(
                "UPSTREAM_INVALID_RESPONSE", "AI 服务返回了无效响应，请稍后再试。", 502, True
            )
        if isinstance(exc, (APITimeoutError, TimeoutError, httpx.TimeoutException)):
            return AppError(
                "UPSTREAM_UNAVAILABLE",
                "AI 服务暂时不可用。",
                503,
                True,
                metric_category="timeout",
            )
        if isinstance(exc, (APIConnectionError, httpx.HTTPError, APIError)):
            return AppError("UPSTREAM_UNAVAILABLE", "AI 服务暂时不可用。", 503, True)
        return AppError("UPSTREAM_UNAVAILABLE", "AI 服务暂时不可用。", 503, True)
