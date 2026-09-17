from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.common import TokenUsage


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Resolved configuration shared by OpenAI-compatible providers."""

    provider: str
    api_key: str | None
    base_url: str
    model: str
    thinking_enabled: bool
    max_output_tokens: int
    temperature: float
    connect_timeout_seconds: float
    request_timeout_seconds: float
    stream_first_token_timeout_seconds: float
    stream_idle_timeout_seconds: float
    stream_total_timeout_seconds: float
    max_retries: int
    retry_base_seconds: float
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderResult:
    reply: str
    model: str
    usage: TokenUsage
    finish_reason: str


@dataclass(frozen=True, slots=True)
class ProviderDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    usage: TokenUsage


@dataclass(frozen=True, slots=True)
class ProviderDone:
    finish_reason: str


ProviderEvent = ProviderDelta | ProviderUsage | ProviderDone
