from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class PersonaManifest(BaseModel):
    schema_version: int = 1
    persona_version: str = Field(min_length=1)
    status: str = "draft"
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    last_verified_at: date | None = None
    style_mode: str = "first_person"
    required_files: list[str] = Field(min_length=1)


class PersonaValidationReport(BaseModel):
    structural_valid: bool
    complete: bool
    approved: bool
    production_ready: bool
    persona_version: str | None = None
    qa_count: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
