from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace

from app.errors import AppError
from app.models.common import TokenUsage
from app.observability import ChatMetricState


def test_metric_allowlist_excludes_content_identity_and_secrets(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.metrics")
    metric = ChatMetricState(
        started_at=time.monotonic() - 0.01,
        request_id="req_test",
        path="/api/v1/chat",
        transport="json",
        cold_start=True,
    )
    metric.set_request_context(
        SimpleNamespace(
            persona_mode="professional",
            locale="de-DE",
            message="question secret Cookie Authorization 192.0.2.10",
            history=[SimpleNamespace(content="history answer")],
        )
    )
    metric.set_usage(TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3))
    metric.mark_completed()
    metric.emit(200)

    assert len(caplog.records) == 1
    event = json.loads(caplog.records[0].getMessage())
    assert set(event) == {
        "event",
        "timestamp_utc",
        "request_id",
        "path",
        "transport",
        "persona_mode",
        "locale",
        "http_status",
        "error_code",
        "failure_class",
        "total_latency_ms",
        "first_token_latency_ms",
        "usage",
        "cold_start",
        "outcome",
        "message_chars",
        "history_count",
    }
    serialized = json.dumps(event, ensure_ascii=False)
    for forbidden in (
        "question secret",
        "history answer",
        "Cookie",
        "Authorization",
        "192.0.2.10",
    ):
        assert forbidden not in serialized
    assert event["locale"] == "de"
    assert event["message_chars"] == len("question secret Cookie Authorization 192.0.2.10")
    assert event["history_count"] == 1


def test_metric_classifies_timeout_and_cancellation(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.metrics")
    timeout_metric = ChatMetricState(
        started_at=time.monotonic(),
        request_id="req_timeout",
        path="/api/v1/chat",
        transport="json",
        cold_start=False,
    )
    timeout_metric.mark_error(
        AppError(
            "UPSTREAM_UNAVAILABLE",
            "AI 服务暂时不可用。",
            503,
            True,
            metric_category="timeout",
        )
    )
    timeout_metric.emit(503)

    cancelled_metric = ChatMetricState(
        started_at=time.monotonic(),
        request_id="req_cancelled",
        path="/api/v1/chat/stream",
        transport="sse",
        cold_start=False,
    )
    cancelled_metric.mark_cancelled()
    cancelled_metric.emit(499)

    events = [json.loads(record.getMessage()) for record in caplog.records]
    assert events[0]["error_code"] == "UPSTREAM_UNAVAILABLE"
    assert events[0]["failure_class"] == "timeout"
    assert events[1]["error_code"] == "REQUEST_CANCELLED"
    assert events[1]["failure_class"] == "cancelled"
    assert events[1]["outcome"] == "cancelled"


def test_metric_emission_failure_is_swallowed(monkeypatch) -> None:
    import app.observability as observability

    monkeypatch.setattr(
        observability.metrics_logger,
        "info",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    metric = ChatMetricState(
        started_at=time.monotonic(),
        request_id="req_logger_failure",
        path="/api/v1/chat",
        transport="json",
        cold_start=False,
    )
    metric.mark_completed()
    metric.emit(200)
