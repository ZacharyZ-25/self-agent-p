from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class UploadIntent(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=20 * 1024 * 1024)


class DocumentSubmit(BaseModel):
    document_id: str | None = Field(default=None, min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    project: str | None = Field(default=None, max_length=120)
    fact_type: Literal["project", "external_reference"] = "project"
    author: str = Field(min_length=1, max_length=240)
    subject_relation: Literal["owner", "external_author"] = "owner"
    visibility: Literal["private_preview", "public_answer"] = "private_preview"
    source_date: date
    effective_at: date
    text: str | None = Field(default=None, max_length=200_000)
    upload_id: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> DocumentSubmit:
        if bool(self.text and self.text.strip()) == bool(self.upload_id):
            raise ValueError("Provide exactly one text or upload_id")
        if self.fact_type == "external_reference" and self.subject_relation != "external_author":
            raise ValueError("External references need an external author")
        if self.fact_type == "project" and self.subject_relation != "owner":
            raise ValueError("Project material needs owner attribution")
        return self


class VersionSubmit(BaseModel):
    source_date: date
    effective_at: date
    text: str | None = Field(default=None, max_length=200_000)
    upload_id: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> VersionSubmit:
        if bool(self.text and self.text.strip()) == bool(self.upload_id):
            raise ValueError("Provide exactly one text or upload_id")
        return self
