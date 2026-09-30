"""Public source view; authorization is checked again for every request."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.errors import AppError
from app.models.chat import SourceCitation, source_from_evidence

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/sources/{chunk_id}", response_model=SourceCitation)
async def public_source(chunk_id: str, request: Request) -> SourceCitation:
    access = request.app.state.knowledge_access
    if access is None:
        raise AppError("SOURCE_NOT_FOUND", "资料不可用。", 404, False)
    evidence = await access.public_source(chunk_id)
    if evidence is None:
        raise AppError("SOURCE_NOT_FOUND", "资料不可用。", 404, False)
    return source_from_evidence(evidence, chunk_id)
