"""Same-origin, local owner management API for Phase 8.4."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse

from app.errors import AppError, service_not_ready_error
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.repository import KnowledgeRepository, Upload
from app.models.chat import ChatRequest, ChatResponse, SourceCitation, source_from_evidence
from app.models.knowledge_admin import DocumentSubmit, LoginRequest, UploadIntent, VersionSubmit
from app.services.chat_service import AnswerContext, is_followup_question, sanitize_history
from app.services.kb_admin_auth import (
    SESSION_COOKIE,
    AdminSession,
    admin_auth,
    require_admin,
    require_origin,
)
from app.services.knowledge_access import LocalKnowledgeAccess

router = APIRouter(prefix="/api/v1/admin/kb", tags=["knowledge-admin"])
page_router = APIRouter(tags=["knowledge-admin"])
PAGE = Path(__file__).resolve().parents[1] / "admin" / "kb.html"


def _access(request: Request) -> LocalKnowledgeAccess:
    access = request.app.state.knowledge_access
    if not isinstance(access, LocalKnowledgeAccess):
        raise AppError("KNOWLEDGE_UNAVAILABLE", "知识库暂不可用。", 503, True)
    return access


def _repository(request: Request) -> KnowledgeRepository:
    return _access(request).retriever.repository


def _indexer(request: Request) -> KnowledgeIndexer:
    access = _access(request)
    return KnowledgeIndexer(access.retriever.repository, access.retriever.provider)


def _bad_input(exc: ValueError) -> AppError:
    return AppError("KNOWLEDGE_INVALID", str(exc), 409, False)


async def _material(
    repository: KnowledgeRepository,
    session: AdminSession,
    text: str | None,
    upload_id: str | None,
) -> tuple[bytes, str]:
    if upload_id:
        try:
            return await asyncio.to_thread(
                repository.pending_upload, upload_id, session.upload_owner_id
            )
        except ValueError as exc:
            raise _bad_input(exc) from exc
    return (text or "").encode("utf-8"), ".txt"


@page_router.get("/admin/kb")
async def admin_page(request: Request) -> FileResponse:
    admin_auth(request)
    return FileResponse(PAGE, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/session")
async def session_state(request: Request) -> JSONResponse:
    auth = admin_auth(request)
    session = auth.session(request.cookies.get(SESSION_COOKIE))
    return JSONResponse(
        {"authenticated": bool(session), "csrf_token": session.csrf_token if session else None},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> JSONResponse:
    auth = admin_auth(request)
    require_origin(request)
    session = auth.login(payload.password, request.client.host if request.client else "local")
    response = JSONResponse(
        {"authenticated": True, "csrf_token": session.csrf_token},
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=8 * 60 * 60,
        path="/api/v1/admin/kb",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    require_admin(request, write=True)
    admin_auth(request).logout(request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/api/v1/admin/kb")
    return response


@router.post("/uploads", status_code=201)
async def create_upload(payload: UploadIntent, request: Request) -> dict:
    session = require_admin(request, write=True)
    suffix = Path(payload.filename).suffix.lower()
    try:
        upload_id = await asyncio.to_thread(
            _repository(request).create_upload_intent, session.upload_owner_id, suffix, payload.size
        )
    except ValueError as exc:
        raise _bad_input(exc) from exc
    return {
        "upload_id": upload_id,
        "upload_url": f"/api/v1/admin/kb/uploads/{upload_id}",
        "expires_in_seconds": 900,
    }


@router.put("/uploads/{upload_id}", status_code=204)
async def put_upload(upload_id: str, request: Request) -> None:
    session = require_admin(request, write=True)
    repository = _repository(request)
    data = await request.body()
    if not 0 < len(data) <= repository.settings.max_file_bytes:
        raise AppError("UPLOAD_INVALID", "文件大小无效。", 413, False)
    try:
        await asyncio.to_thread(
            repository.save_pending_upload, upload_id, session.upload_owner_id, data
        )
    except (ValueError, FileExistsError) as exc:
        raise _bad_input(ValueError("UPLOAD_NOT_AVAILABLE")) from exc


@router.post("/documents", status_code=202)
async def create_document(payload: DocumentSubmit, request: Request) -> dict:
    session = require_admin(request, write=True)
    repository = _repository(request)
    if payload.effective_at > date.today():
        raise AppError("KNOWLEDGE_INVALID", "生效日期不能晚于今天。", 422, False)
    data, suffix = await _material(repository, session, payload.text, payload.upload_id)
    try:
        result = await asyncio.to_thread(
            repository.submit,
            Upload(
                document_id=payload.document_id or uuid4().hex,
                title=payload.title.strip(),
                project=payload.project,
                fact_type=payload.fact_type,
                author=payload.author.strip(),
                subject_relation=payload.subject_relation,
                visibility=payload.visibility,
                source_date=payload.source_date.isoformat(),
                effective_at=payload.effective_at.isoformat(),
                data=data,
                suffix=suffix,
                actor="admin-web",
                auto_activate=True,
                auto_publish=payload.visibility == "public_answer",
            ),
        )
    except ValueError as exc:
        raise _bad_input(exc) from exc
    if payload.upload_id:
        await asyncio.to_thread(
            repository.consume_pending_upload, payload.upload_id, session.upload_owner_id
        )
    return result


@router.post("/documents/{document_id}/versions", status_code=202)
async def replace_version(document_id: str, payload: VersionSubmit, request: Request) -> dict:
    session = require_admin(request, write=True)
    repository = _repository(request)
    document = await asyncio.to_thread(repository.admin_document, document_id)
    if not document:
        raise AppError("DOCUMENT_NOT_FOUND", "资料不存在。", 404, False)
    if not document["active_version_id"]:
        raise AppError("VERSION_NOT_READY", "请等待当前版本处理完成。", 409, False)
    if payload.effective_at > date.today():
        raise AppError("KNOWLEDGE_INVALID", "生效日期不能晚于今天。", 422, False)
    data, suffix = await _material(repository, session, payload.text, payload.upload_id)
    try:
        result = await asyncio.to_thread(
            repository.submit,
            Upload(
                document_id=document_id,
                title=document["title"],
                project=document["project"],
                fact_type=document["fact_type"],
                author=document["author"],
                subject_relation=document["subject_relation"],
                visibility=document["visibility"],
                source_date=payload.source_date.isoformat(),
                effective_at=payload.effective_at.isoformat(),
                data=data,
                suffix=suffix,
                replaces=document["active_version_id"],
                actor="admin-web",
                auto_activate=True,
                auto_publish=False,
            ),
        )
    except ValueError as exc:
        raise _bad_input(exc) from exc
    if payload.upload_id:
        await asyncio.to_thread(
            repository.consume_pending_upload, payload.upload_id, session.upload_owner_id
        )
    return result


@router.get("/documents")
async def documents(request: Request) -> list[dict]:
    require_admin(request)
    return jsonable_encoder(await asyncio.to_thread(_repository(request).admin_documents))


@router.get("/jobs/{job_id}")
async def job(job_id: str, request: Request) -> dict:
    require_admin(request)
    found = await asyncio.to_thread(_repository(request).job, job_id)
    if not found:
        raise AppError("JOB_NOT_FOUND", "任务不存在。", 404, False)
    return jsonable_encoder(found)


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, request: Request) -> dict:
    require_admin(request, write=True)
    repository = _repository(request)
    try:
        await asyncio.to_thread(repository.retry, job_id)
    except ValueError as exc:
        raise _bad_input(exc) from exc
    return jsonable_encoder(await asyncio.to_thread(repository.job, job_id))


@router.get("/documents/{document_id}/versions/{version_id}/chunks")
async def document_chunks(document_id: str, version_id: str, request: Request) -> list[dict]:
    require_admin(request)
    repository = _repository(request)
    document = await asyncio.to_thread(repository.admin_document, document_id)
    if not document:
        raise AppError("DOCUMENT_NOT_FOUND", "资料不存在。", 404, False)
    if not await asyncio.to_thread(repository.version_belongs_to, document_id, version_id):
        raise AppError("VERSION_NOT_FOUND", "版本不存在。", 404, False)
    return jsonable_encoder(await asyncio.to_thread(repository.chunks, version_id))


@router.post("/documents/{document_id}/publish")
async def publish(document_id: str, request: Request) -> dict:
    require_admin(request, write=True)
    try:
        await asyncio.to_thread(
            _indexer(request).set_published, document_id, True, actor="admin-web"
        )
    except ValueError as exc:
        raise _bad_input(exc) from exc
    return {"document_id": document_id, "published": True}


@router.post("/documents/{document_id}/unpublish")
async def unpublish(document_id: str, request: Request) -> dict:
    require_admin(request, write=True)
    try:
        await asyncio.to_thread(
            _indexer(request).set_published, document_id, False, actor="admin-web"
        )
    except ValueError as exc:
        raise _bad_input(exc) from exc
    return {"document_id": document_id, "published": False}


@router.delete("/documents/{document_id}", status_code=202)
async def delete_document(document_id: str, request: Request) -> dict:
    require_admin(request, write=True)
    try:
        await asyncio.to_thread(_indexer(request).delete_document, document_id, actor="admin-web")
    except ValueError as exc:
        raise _bad_input(exc) from exc
    return {"document_id": document_id, "deleted": True, "cleanup": "queued"}


@router.post("/preview", response_model=ChatResponse, response_model_exclude_none=True)
async def preview(payload: ChatRequest, request: Request) -> ChatResponse:
    require_admin(request, write=True)
    service = request.app.state.chat_service
    if service is None:
        raise service_not_ready_error()
    history = ()
    if is_followup_question(payload.message):
        history = tuple(
            item["content"]
            for item in sanitize_history(
                payload.history,
                max_messages=service.settings.max_history_messages,
                max_chars=service.settings.max_history_chars,
                max_content_chars=service.settings.max_message_chars,
            )
            if item["role"] == "user"
        )[-2:]
    result = await _access(request).prepare_preview(payload.message, history)
    sources = tuple(
        source_from_evidence(item, f"S{index}").model_copy(
            update={
                "url": f"/api/v1/admin/kb/sources/{item.source_id}",
            }
        )
        for index, item in enumerate(result.evidence, 1)
    )
    answer = await service.complete(
        payload, context_override=AnswerContext(result, sources, scope="owner_preview")
    )
    return ChatResponse(
        request_id=request.state.request_id,
        reply=answer.reply,
        model=answer.model,
        persona_version=service.persona.persona_version,
        usage=answer.usage,
        sources=list(answer.sources or ()),
        knowledge_version=answer.knowledge_version,
        knowledge_status=answer.knowledge_status,
    )


@router.get("/sources/{chunk_id}", response_model=SourceCitation)
async def preview_source(chunk_id: str, request: Request) -> SourceCitation:
    require_admin(request)
    evidence = await _access(request).owner_source(chunk_id)
    if evidence is None:
        raise AppError("SOURCE_NOT_FOUND", "资料不可用。", 404, False)
    return source_from_evidence(evidence, chunk_id).model_copy(
        update={
            "url": f"/api/v1/admin/kb/sources/{chunk_id}",
        }
    )
