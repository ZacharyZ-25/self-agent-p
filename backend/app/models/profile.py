from __future__ import annotations

from pydantic import BaseModel, Field


class LocalizedIntro(BaseModel):
    zh: str
    en: str


class PublicContact(BaseModel):
    website: str | None = None
    github: str | None = None
    linkedin: str | None = None
    email: str | None = None


class PublicProfileResponse(BaseModel):
    persona_version: str
    display_name: str
    title: str
    intro: LocalizedIntro
    avatar_url: str | None = None
    quick_questions: dict[str, list[str]] = Field(default_factory=dict)
    contact: PublicContact
    disclaimer: str
