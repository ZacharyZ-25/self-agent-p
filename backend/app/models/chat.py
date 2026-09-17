from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.common import TokenUsage

DISCLAIMER = "这是基于 Example Candidate 公开资料生成的 AI 回复。"


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


class ChatResponse(BaseModel):
    request_id: str
    reply: str
    model: str
    persona_version: str
    usage: TokenUsage
    disclaimer: str = DISCLAIMER
