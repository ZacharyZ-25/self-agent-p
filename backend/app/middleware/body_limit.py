from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import AppError, error_payload


class BodyLimitExceeded(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(
        self, app: ASGIApp, max_bytes: int, admin_upload_max_bytes: int = 21 * 1024 * 1024
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.admin_upload_max_bytes = admin_upload_max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "")
        limit = self.max_bytes
        if path.startswith("/api/v1/admin/kb/") and (
            (method == "PUT" and "/uploads/" in path)
            or (
                method == "POST"
                and (path == "/api/v1/admin/kb/documents" or path.endswith("/versions"))
            )
        ):
            limit = self.admin_upload_max_bytes
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    raise BodyLimitExceeded
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyLimitExceeded:
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        error = AppError(
            code="REQUEST_TOO_LARGE",
            message="请求体过大。",
            status_code=413,
            retryable=False,
        )
        request_id = scope.get("state", {}).get("request_id", "req_unknown")
        response = JSONResponse(error_payload(request_id, error), status_code=413)
        await response(scope, receive, send)
