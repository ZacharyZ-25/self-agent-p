from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.errors import AppError, service_not_ready_error
from app.models.chat import ChatRequest, ChatResponse
from app.observability import get_chat_metric
from app.services.chat_service import ChatDone, ChatService, ChatSources
from app.services.provider import ProviderDelta, ProviderDone, ProviderUsage

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _chat_service(request: Request) -> ChatService:
    service = request.app.state.chat_service
    if service is None:
        raise service_not_ready_error()
    return service


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    metric = get_chat_metric(request)
    if metric is not None:
        metric.set_request_context(payload)
    service = _chat_service(request)
    try:
        result = await service.complete(payload)
    except asyncio.CancelledError:
        if metric is not None:
            metric.mark_cancelled()
        raise
    if metric is not None:
        metric.set_usage(result.usage)
        metric.mark_completed()
    return ChatResponse(
        request_id=request.state.request_id,
        reply=result.reply,
        model=result.model,
        persona_version=service.persona.persona_version,
        usage=result.usage,
        sources=list(result.sources) if getattr(result, "sources", None) is not None else None,
        knowledge_version=getattr(result, "knowledge_version", None),
        knowledge_status=getattr(result, "knowledge_status", None),
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    metric = get_chat_metric(request)
    if metric is not None:
        metric.set_request_context(payload)
    service = _chat_service(request)
    request_id = request.state.request_id

    async def events() -> AsyncIterator[bytes]:
        yield _sse(
            "meta",
            {
                "request_id": request_id,
                "persona_version": service.persona.persona_version,
            },
        )
        upstream = service.stream(payload)
        try:
            async for event in upstream:
                if isinstance(event, ChatSources):
                    data: dict[str, object] = {
                        "sources": [source.model_dump(mode="json") for source in event.sources],
                        "knowledge_status": event.knowledge_status,
                    }
                    if event.knowledge_version is not None:
                        data["knowledge_version"] = event.knowledge_version
                    yield _sse("sources", data)
                elif isinstance(event, ProviderDelta):
                    if metric is not None:
                        metric.mark_first_token()
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, ProviderUsage):
                    if metric is not None:
                        metric.set_usage(event.usage)
                    yield _sse("usage", event.usage.model_dump())
                elif isinstance(event, ProviderDone):
                    if metric is not None:
                        metric.mark_completed()
                    yield _sse("done", {"finish_reason": event.finish_reason})
                elif isinstance(event, ChatDone):
                    if metric is not None:
                        metric.mark_completed()
                    yield _sse(
                        "done",
                        {
                            "finish_reason": event.finish_reason,
                            "source_ids": list(event.source_ids),
                        },
                    )
        except asyncio.CancelledError:
            if metric is not None:
                metric.mark_cancelled()
            raise
        except AppError as error:
            if metric is not None:
                metric.mark_error(error)
            yield _sse(
                "error",
                {
                    "request_id": request_id,
                    "code": error.code,
                    "message": error.message,
                    "retryable": error.retryable,
                },
            )
        except Exception:
            if metric is not None:
                metric.mark_error(AppError("INTERNAL_ERROR", "服务暂时不可用。", 500, True))
            yield _sse(
                "error",
                {
                    "request_id": request_id,
                    "code": "INTERNAL_ERROR",
                    "message": "服务暂时不可用。",
                    "retryable": True,
                },
            )
        finally:
            await upstream.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict[str, object]) -> bytes:
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {serialized}\n\n".encode()
