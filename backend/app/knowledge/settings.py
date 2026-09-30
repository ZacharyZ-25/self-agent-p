from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class KnowledgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KB_", extra="ignore")

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    pglite_compat: bool = False
    storage: Literal["local", "s3"] = "local"
    object_dir: Path = Path(__file__).resolve().parents[3] / "knowledge-data/objects"
    s3_bucket: str = ""
    s3_endpoint: str | None = None
    s3_region: str = "eu-central-1"
    # S3 credentials use the standard AWS SDK environment/provider chain.
    max_file_bytes: int = Field(20 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(200, ge=1)
    max_text_chars: int = Field(200_000, ge=1)
    chunk_tokens: int = Field(600, ge=100, le=700)
    overlap_tokens: int = Field(80, ge=0, le=100)
    lease_seconds: int = Field(60, ge=3)
    max_attempts: int = Field(3, ge=1, le=10)
    retry_seconds: float = Field(2, ge=0)
