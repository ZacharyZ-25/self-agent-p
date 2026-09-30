from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.common import TokenUsage

if TYPE_CHECKING:
    from app.knowledge.retriever import Evidence

DISCLAIMER = "这是基于本人公开资料生成的 AI 回复。"


class HistoryMessage(BaseModel):
    # Keep role open at the transport boundary so privileged/unknown roles can be discarded
    # instead of ever being forwarded upstream.
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
    session_id: str | None = Field(default=None, max_length=128)
    locale: str | None = Field(default=None, max_length=32)
    persona_mode: Literal["professional", "casual"] = "professional"

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


class SourceCitation(BaseModel):
    source_id: str
    document_id: str
    version_id: str
    title: str
    locations: list[dict]
    snippet: str
    url: str
    author: str
    fact_type: str
    effective_at: date


class ChatResponse(BaseModel):
    request_id: str
    reply: str
    model: str
    persona_version: str
    usage: TokenUsage
    disclaimer: str = DISCLAIMER
    sources: list[SourceCitation] | None = None
    knowledge_version: str | None = None
    knowledge_status: str | None = None


def source_from_evidence(evidence: Evidence, source_id: str) -> SourceCitation:
    return SourceCitation(
        source_id=source_id,
        document_id=evidence.document_id,
        version_id=evidence.version_id,
        title=evidence.title,
        locations=[
            {
                key: location[key]
                for key in (
                    "page",
                    "section",
                    "line_start",
                    "line_end",
                    "paragraph",
                    "table",
                    "row",
                )
                if key in location
            }
            for location in evidence.locations
        ],
        snippet=evidence.body,
        url=f"/api/v1/knowledge/sources/{evidence.source_id}",
        author=evidence.author,
        fact_type=evidence.fact_type,
        effective_at=evidence.effective_at,
    )
