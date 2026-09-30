"""Local-only owner login for the Phase 8.4 management page."""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Request

from app.errors import AppError

SESSION_COOKIE = "kb_admin_session"
SESSION_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class AdminSession:
    token: str
    upload_owner_id: str
    csrf_token: str
    expires_at: float


class AdminAuth:
    def __init__(self, password: str):
        self.password = password
        self.sessions: dict[str, AdminSession] = {}
        self.failures: dict[str, tuple[int, float]] = {}

    def login(self, password: str, client_ip: str) -> AdminSession:
        now = time.monotonic()
        count, started = self.failures.get(client_ip, (0, now))
        if now - started >= 60:
            count, started = 0, now
        if count >= 5:
            raise AppError("ADMIN_LOGIN_LIMITED", "请稍后再试。", 429, True)
        if not hmac.compare_digest(password, self.password):
            self.failures[client_ip] = (count + 1, started)
            raise AppError("ADMIN_LOGIN_FAILED", "登录失败。", 401, False)
        self.failures.pop(client_ip, None)
        token = secrets.token_urlsafe(32)
        session = AdminSession(
            token, secrets.token_urlsafe(16), secrets.token_urlsafe(24), now + SESSION_SECONDS
        )
        self.sessions[token] = session
        return session

    def session(self, token: str | None) -> AdminSession | None:
        if not token:
            return None
        session = self.sessions.get(token)
        if session and session.expires_at > time.monotonic():
            return session
        self.sessions.pop(token, None)
        return None

    def logout(self, token: str | None) -> None:
        if token:
            self.sessions.pop(token, None)


def admin_auth(request: Request) -> AdminAuth:
    auth = getattr(request.app.state, "kb_admin_auth", None)
    if auth is None:
        raise AppError("NOT_FOUND", "页面不可用。", 404, False)
    return auth


def require_origin(request: Request) -> None:
    origin = request.headers.get("origin", "")
    expected = str(request.base_url).rstrip("/")
    if origin != expected:
        raise AppError("ADMIN_ORIGIN_INVALID", "请求来源无效。", 403, False)


def require_admin(request: Request, *, write: bool = False) -> AdminSession:
    auth = admin_auth(request)
    session = auth.session(request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise AppError("ADMIN_LOGIN_REQUIRED", "请先登录。", 401, False)
    if write:
        require_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(csrf, session.csrf_token):
            raise AppError("ADMIN_CSRF_INVALID", "请刷新页面后重试。", 403, False)
    return session
