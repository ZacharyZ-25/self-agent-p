from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AppError(Exception):
    """A stable product error safe to expose to the browser."""

    code: str
    message: str
    status_code: int
    retryable: bool = False
    metric_category: str | None = None

    def __str__(self) -> str:
        return self.code


def error_payload(request_id: str, error: AppError) -> dict[str, object]:
    return {
        "request_id": request_id,
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    }


def service_not_ready_error() -> AppError:
    return AppError(
        code="SERVICE_NOT_READY",
        message="AI 服务尚未就绪，请稍后再试。",
        status_code=503,
        retryable=True,
    )
