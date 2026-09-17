from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import AppError
from app.models.common import TokenUsage

logger = logging.getLogger("app.requests")
metrics_logger = logging.getLogger("app.metrics")

_CHAT_PATHS = {
    "/api/v1/chat": "json",
    "/api/v1/chat/stream": "sse",
}


@dataclass(slots=True)
class ChatMetricState:
    """Request-scoped, content-free telemetry for chat endpoints."""

    started_at: float
    request_id: str
    path: str
    transport: str
    cold_start: bool
    persona_mode: str | None = None
    locale: str | None = None
    message_chars: int | None = None
    history_count: int | None = None
    first_token_at: float | None = None
    usage: TokenUsage | None = None
    error_code: str | None = None
    failure_class: str | None = None
    outcome: str | None = None
    _emitted: bool = field(default=False, init=False, repr=False)

    def set_request_context(self, payload: Any) -> None:
        """Copy only bounded, non-content request attributes into telemetry."""

        self.persona_mode = _safe_enum(getattr(payload, "persona_mode", None))
        self.locale = _normalize_locale(getattr(payload, "locale", None))
        message = getattr(payload, "message", None)
        self.message_chars = len(message) if isinstance(message, str) else None
        history = getattr(payload, "history", None)
        self.history_count = len(history) if isinstance(history, list) else None

    def mark_first_token(self) -> None:
        if self.first_token_at is None:
            self.first_token_at = time.monotonic()

    def set_usage(self, usage: TokenUsage | None) -> None:
        if usage is None:
            return
        self.usage = TokenUsage.model_validate(usage.model_dump())

    def mark_completed(self) -> None:
        if self.outcome is None:
            self.outcome = "completed"
            self.failure_class = "success"

    def mark_cancelled(self) -> None:
        if self.outcome is None:
            self.outcome = "cancelled"
            self.failure_class = "cancelled"
            self.error_code = "REQUEST_CANCELLED"

    def mark_error(self, error: AppError) -> None:
        self.outcome = "failed"
        self.error_code = error.code
        self.failure_class = error.metric_category or _failure_class_for_code(error.code)

    def finalize(self, status_code: int) -> None:
        if self.outcome is None:
            fallback_code = _fallback_error_code(status_code)
            if fallback_code is not None:
                self.error_code = fallback_code
                self.failure_class = _failure_class_for_code(fallback_code)
                self.outcome = "failed"
            elif status_code == 200:
                self.failure_class = "incomplete"
                self.outcome = "incomplete"
            else:
                self.failure_class = "unknown_error"
                self.outcome = "failed"

    def emit(self, status_code: int) -> None:
        """Best-effort emission: telemetry failures must never fail the request."""

        if self._emitted:
            return
        self._emitted = True
        try:
            self.finalize(status_code)
            event = {
                "event": "chat_metric_v1",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "request_id": self.request_id,
                "path": self.path,
                "transport": self.transport,
                "persona_mode": self.persona_mode,
                "locale": self.locale,
                "http_status": status_code,
                "error_code": self.error_code,
                "failure_class": self.failure_class,
                "total_latency_ms": round((time.monotonic() - self.started_at) * 1000, 2),
                "first_token_latency_ms": (
                    round((self.first_token_at - self.started_at) * 1000, 2)
                    if self.first_token_at is not None
                    else None
                ),
                "usage": self.usage.model_dump() if self.usage is not None else None,
                "cold_start": self.cold_start,
                "outcome": self.outcome,
                "message_chars": self.message_chars,
                "history_count": self.history_count,
            }
            metrics_logger.info(
                json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            )
        except Exception:
            # A broken logger, formatter, or serializer must not affect chat.
            return


class RequestLogMiddleware:
    """Log allowlisted metadata only; never request or response bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._first_chat_request = True

    def _new_chat_metric(self, scope: Scope) -> ChatMetricState | None:
        if scope.get("method") != "POST":
            return None
        transport = _CHAT_PATHS.get(scope.get("path", ""))
        if transport is None:
            return None
        state = scope.setdefault("state", {})
        metric = ChatMetricState(
            started_at=time.monotonic(),
            request_id=str(state.get("request_id", "req_unknown")),
            path=str(scope.get("path", "")),
            transport=transport,
            # This is process-local first-request inference, not Render ground truth.
            cold_start=self._first_chat_request,
        )
        self._first_chat_request = False
        state["chat_metric"] = metric
        return metric

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        status_code = 500
        metric = self._new_chat_metric(scope)

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            logger.info(
                "request_complete",
                extra={
                    "request_id": scope.get("state", {}).get("request_id", "req_unknown"),
                    "method": scope.get("method"),
                    "route": scope.get("path"),
                    "status_code": status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
            if metric is not None:
                metric.emit(status_code)


def get_chat_metric(scope_or_request: Any) -> ChatMetricState | None:
    """Return the request-scoped metric state without exposing it in API models."""

    scope = getattr(scope_or_request, "scope", scope_or_request)
    state = scope.get("state", {}) if isinstance(scope, dict) else {}
    metric = state.get("chat_metric")
    return metric if isinstance(metric, ChatMetricState) else None


def _safe_enum(value: Any) -> str | None:
    return value if isinstance(value, str) and value in {"professional", "casual"} else None


def _normalize_locale(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    locale = value.strip().casefold().split("-", 1)[0].split("_", 1)[0]
    return locale if locale in {"zh", "en", "de"} else "unknown"


def _failure_class_for_code(code: str) -> str:
    if code in {"REQUEST_INVALID", "REQUEST_TOO_LARGE"}:
        return "validation_error"
    if code in {"RATE_LIMITED", "UPSTREAM_RATE_LIMITED", "UPSTREAM_BUSY"}:
        return "rate_limited"
    if code == "SERVICE_NOT_READY":
        return "not_ready"
    if code == "INTERNAL_ERROR":
        return "internal_error"
    if code == "REQUEST_CANCELLED":
        return "cancelled"
    if code.startswith("UPSTREAM_"):
        return "upstream_error"
    return "unknown_error"


def _fallback_error_code(status_code: int) -> str | None:
    return {
        413: "REQUEST_TOO_LARGE",
        422: "REQUEST_INVALID",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "UPSTREAM_UNAVAILABLE",
    }.get(status_code)
