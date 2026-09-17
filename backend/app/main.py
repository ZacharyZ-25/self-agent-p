from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.config import Settings, get_settings
from app.errors import AppError, error_payload
from app.middleware.body_limit import BodyLimitMiddleware
from app.middleware.rate_limit import RateLimiter, RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.observability import RequestLogMiddleware, get_chat_metric
from app.services.chat_service import ChatProvider, ChatService
from app.services.openai_compatible_client import OpenAICompatibleClient
from app.services.persona_service import PersonaPackageError, PersonaService


def create_app(
    settings: Settings | None = None,
    *,
    provider: ChatProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    logging.getLogger("app").setLevel(resolved_settings.log_level.upper())

    persona_service = PersonaService(resolved_settings.persona_dir)
    persona_report = persona_service.validate()
    try:
        persona_snapshot = persona_service.load()
    except PersonaPackageError:
        persona_snapshot = None
    strict_persona = resolved_settings.is_production or resolved_settings.require_approved_persona
    if strict_persona and not persona_report.production_ready:
        persona_snapshot = None

    owns_provider = False
    resolved_provider = provider
    if resolved_provider is None and resolved_settings.has_llm_config:
        resolved_provider = OpenAICompatibleClient.from_settings(resolved_settings)
        owns_provider = True

    rate_limiter = RateLimiter(
        per_minute=resolved_settings.rate_limit_per_minute,
        per_day=resolved_settings.rate_limit_per_day,
        session_per_day=resolved_settings.rate_limit_session_per_day,
    )
    chat_service = (
        ChatService(
            resolved_settings,
            persona_snapshot,
            resolved_provider,
            session_limiter=rate_limiter,
        )
        if persona_snapshot is not None and resolved_provider is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_provider and resolved_provider is not None:
            close = getattr(resolved_provider, "close", None)
            if close is not None:
                await close()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs" if not resolved_settings.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.persona_service = persona_service
    app.state.persona_report = persona_report
    app.state.persona_snapshot = persona_snapshot
    app.state.provider = resolved_provider
    app.state.rate_limiter = rate_limiter
    app.state.chat_service = chat_service

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        metric = get_chat_metric(request)
        if metric is not None:
            metric.mark_error(error)
        request_id = getattr(request.state, "request_id", "req_unknown")
        return JSONResponse(
            error_payload(request_id, error), status_code=error.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, _: RequestValidationError
    ) -> JSONResponse:
        error = AppError(
            code="REQUEST_INVALID",
            message="请求格式不正确。",
            status_code=422,
            retryable=False,
        )
        metric = get_chat_metric(request)
        if metric is not None:
            metric.mark_error(error)
        request_id = getattr(request.state, "request_id", "req_unknown")
        return JSONResponse(error_payload(request_id, error), status_code=422)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _: Exception) -> JSONResponse:
        error = AppError(
            code="INTERNAL_ERROR",
            message="服务暂时不可用。",
            status_code=500,
            retryable=True,
        )
        metric = get_chat_metric(request)
        if metric is not None:
            metric.mark_error(error)
        request_id = getattr(request.state, "request_id", "req_unknown")
        return JSONResponse(error_payload(request_id, error), status_code=500)

    # add_middleware inserts the newest item outermost. The final order is:
    # request ID -> CORS -> observability -> body limit -> rate limit -> routing.
    app.add_middleware(
        RateLimitMiddleware,
        limiter=rate_limiter,
        trusted_proxies=resolved_settings.trusted_proxies,
    )
    app.add_middleware(BodyLimitMiddleware, max_bytes=resolved_settings.max_request_bytes)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router)
    app.include_router(profile_router)
    app.include_router(chat_router)
    return app


app = create_app()
