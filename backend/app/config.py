from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
LOCAL_LLM_BASE_URL = "http://127.0.0.1:8010/v1"
LOCAL_LLM_MODEL = "local-model"


def discover_persona_dir() -> Path:
    """Support both the source tree and the compact /app Docker layout."""
    candidates = (PROJECT_ROOT / "persona.example", BACKEND_ROOT / "persona.example")
    return next((path for path in candidates if path.is_dir()), candidates[0])


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "Example Candidate Digital Twin API"
    app_version: str = "0.1.0"
    render_git_commit: str = ""

    # Phase 6B/6C generic OpenAI-compatible provider settings. Empty optional
    # values preserve the legacy DeepSeek settings only when LLM_PROVIDER=deepseek.
    llm_provider: str = "deepseek"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = ""
    llm_model: str = ""
    llm_thinking_enabled: bool | None = None
    llm_max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    llm_temperature: float | None = Field(default=None, ge=0, le=2)
    llm_connect_timeout_seconds: float | None = Field(default=None, gt=0, le=60)
    llm_request_timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    llm_stream_first_token_timeout_seconds: float | None = Field(
        default=None, gt=0, le=120
    )
    llm_stream_idle_timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    llm_stream_total_timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    llm_max_retries: int | None = Field(default=None, ge=0, le=5)
    llm_retry_base_seconds: float | None = Field(default=None, ge=0, le=10)

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking_enabled: bool = False
    deepseek_max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    deepseek_temperature: float = Field(default=0.6, ge=0, le=2)
    deepseek_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    deepseek_request_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    deepseek_stream_first_token_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    deepseek_stream_idle_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    deepseek_stream_total_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    deepseek_max_retries: int = Field(default=2, ge=0, le=5)
    deepseek_retry_base_seconds: float = Field(default=0.25, ge=0, le=10)

    persona_dir: Path = Field(default_factory=discover_persona_dir)
    require_approved_persona: bool = False

    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"
    max_message_chars: int = Field(default=2000, ge=1, le=2000)
    max_history_messages: int = Field(default=20, ge=0, le=20)
    max_history_chars: int = Field(default=12000, ge=0, le=12000)
    max_request_bytes: int = Field(default=32768, ge=1024, le=32768)

    rate_limit_per_minute: int = Field(default=10, ge=1, le=10000)
    rate_limit_per_day: int = Field(default=15, ge=1, le=1000000)
    rate_limit_session_per_day: int = Field(default=50, ge=1, le=1000000)
    max_llm_concurrency: int = Field(default=20, ge=1, le=1000)
    trusted_proxy_ips: str = ""

    rag_enabled: bool = False
    database_url: SecretStr | None = None
    rag_top_k: int = Field(default=5, ge=1, le=10)
    rag_context_token_budget: int = Field(default=3000, ge=100, le=12000)
    rag_timeout_seconds: float = Field(default=2, gt=0, le=10)
    rag_max_concurrency: int = Field(default=4, ge=1, le=32)
    kb_admin_enabled: bool = False
    kb_admin_password: SecretStr | None = None

    log_level: str = "INFO"
    log_raw_conversations: bool = False

    @field_validator("app_env")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def normalize_llm_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"local", "deepseek", "openai_compatible", "llama_cpp"}:
            raise ValueError(
                "LLM_PROVIDER must be local, deepseek, openai_compatible, or llama_cpp"
            )
        return normalized

    @field_validator("persona_dir", mode="before")
    @classmethod
    def resolve_persona_dir(cls, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            candidates = (
                (Path.cwd() / path).resolve(),
                (PROJECT_ROOT / path).resolve(),
                (BACKEND_ROOT / path).resolve(),
            )
            path = next(
                (candidate for candidate in candidates if candidate.exists()), candidates[1]
            )
        return path

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def has_deepseek_key(self) -> bool:
        return bool(self.deepseek_api_key and self.deepseek_api_key.get_secret_value().strip())

    @property
    def resolved_llm_api_key(self) -> SecretStr | None:
        if self.llm_api_key is not None:
            return self.llm_api_key
        return self.deepseek_api_key if self.llm_provider == "deepseek" else None

    @property
    def resolved_llm_base_url(self) -> str:
        if self.llm_base_url.strip():
            return self.llm_base_url.strip().rstrip("/")
        if self.llm_provider == "local":
            return LOCAL_LLM_BASE_URL
        if self.llm_provider == "deepseek":
            return self.deepseek_base_url.strip().rstrip("/")
        return ""

    @property
    def resolved_llm_model(self) -> str:
        if self.llm_model.strip():
            return self.llm_model.strip()
        if self.llm_provider == "local":
            return LOCAL_LLM_MODEL
        if self.llm_provider == "deepseek":
            return self.deepseek_model
        return ""

    @property
    def resolved_llm_thinking_enabled(self) -> bool:
        if self.llm_thinking_enabled is not None:
            return self.llm_thinking_enabled
        return self.deepseek_thinking_enabled if self.llm_provider == "deepseek" else False

    @property
    def resolved_llm_max_output_tokens(self) -> int:
        return self.llm_max_output_tokens or self.deepseek_max_output_tokens

    @property
    def resolved_llm_temperature(self) -> float:
        return (
            self.llm_temperature
            if self.llm_temperature is not None
            else self.deepseek_temperature
        )

    @property
    def resolved_llm_connect_timeout_seconds(self) -> float:
        return self.llm_connect_timeout_seconds or self.deepseek_connect_timeout_seconds

    @property
    def resolved_llm_request_timeout_seconds(self) -> float:
        return self.llm_request_timeout_seconds or self.deepseek_request_timeout_seconds

    @property
    def resolved_llm_stream_first_token_timeout_seconds(self) -> float:
        return (
            self.llm_stream_first_token_timeout_seconds
            or self.deepseek_stream_first_token_timeout_seconds
        )

    @property
    def resolved_llm_stream_idle_timeout_seconds(self) -> float:
        return self.llm_stream_idle_timeout_seconds or self.deepseek_stream_idle_timeout_seconds

    @property
    def resolved_llm_stream_total_timeout_seconds(self) -> float:
        return self.llm_stream_total_timeout_seconds or self.deepseek_stream_total_timeout_seconds

    @property
    def resolved_llm_max_retries(self) -> int:
        return (
            self.llm_max_retries
            if self.llm_max_retries is not None
            else self.deepseek_max_retries
        )

    @property
    def resolved_llm_retry_base_seconds(self) -> float:
        return (
            self.llm_retry_base_seconds
            if self.llm_retry_base_seconds is not None
            else self.deepseek_retry_base_seconds
        )

    @property
    def has_llm_config(self) -> bool:
        endpoint_ready = bool(self.resolved_llm_base_url and self.resolved_llm_model)
        if self.llm_provider == "local":
            return endpoint_ready
        return endpoint_ready and bool(
            self.resolved_llm_api_key
            and self.resolved_llm_api_key.get_secret_value().strip()
        )

    @property
    def trusted_proxies(self) -> set[str]:
        return {item.strip() for item in self.trusted_proxy_ips.split(",") if item.strip()}

    @model_validator(mode="after")
    def validate_security_invariants(self) -> Settings:
        if self.kb_admin_enabled and (
            not self.rag_enabled or self.database_url is None or not self.kb_admin_password
            or not self.kb_admin_password.get_secret_value()
        ):
            raise ValueError(
                "KB_ADMIN_ENABLED needs RAG_ENABLED, DATABASE_URL and KB_ADMIN_PASSWORD"
            )
        if self.is_production:
            if self.rag_enabled and self.database_url is None:
                raise ValueError("Production RAG_ENABLED needs the public DATABASE_URL")
            if self.kb_admin_enabled:
                raise ValueError(
                    "KB_ADMIN_ENABLED is local-only until production identity is configured"
                )
            origins = self.allowed_origins
            if not origins or len(origins) != len(set(origins)):
                raise ValueError("production CORS_ORIGINS requires unique explicit HTTPS origins")
            for origin in origins:
                parsed = urlsplit(origin)
                if (parsed.scheme != "https" or not parsed.hostname
                        or parsed.username or parsed.password or parsed.path
                        or parsed.query or parsed.fragment or "*" in origin):
                    raise ValueError("production CORS_ORIGINS must contain HTTPS origins only")
            if self.log_raw_conversations:
                raise ValueError("LOG_RAW_CONVERSATIONS must be false in production")
            if self.llm_provider == "local":
                raise ValueError(
                    "LLM_PROVIDER=local is only allowed in development or test; "
                    "production must use an HTTPS remote provider"
                )
        self._validate_llm_endpoint()
        if self.rate_limit_per_day < self.rate_limit_per_minute:
            raise ValueError("RATE_LIMIT_PER_DAY must be >= RATE_LIMIT_PER_MINUTE")
        return self

    def _validate_llm_endpoint(self) -> None:
        """Reject ambiguous or unsafe provider URLs before a request can be made."""

        endpoint = self.resolved_llm_base_url
        if not endpoint:
            return

        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("LLM_BASE_URL must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("LLM_BASE_URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("LLM_BASE_URL must not contain a query string or fragment")

        if not self.is_production:
            return
        if parsed.scheme != "https":
            raise ValueError("production LLM_BASE_URL must use HTTPS")

        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"}:
            raise ValueError("production LLM_BASE_URL must not target localhost")
        try:
            address = ip_address(host)
        except ValueError:
            return
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_unspecified
        ):
            raise ValueError("production LLM_BASE_URL must not target a private or loopback IP")


@lru_cache
def get_settings() -> Settings:
    return Settings()
