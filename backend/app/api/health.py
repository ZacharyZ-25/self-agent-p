from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.services.persona_service import PersonaService

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def health(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    payload = {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }
    if settings.render_git_commit:
        payload["revision"] = settings.render_git_commit[:12]
    return payload


@router.get("/readyz")
async def readiness(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    persona_report = PersonaService(settings.persona_dir).validate()

    checks = {
        "persona_package": persona_report.structural_valid,
        "persona_complete": persona_report.complete,
        "persona_approved": persona_report.approved,
        "llm_provider": settings.llm_provider,
        "llm_configured": settings.has_llm_config,
        # Kept temporarily so existing operational dashboards do not break.
        "deepseek_api_key": settings.has_deepseek_key,
    }

    production_ready = persona_report.production_ready and settings.has_llm_config
    strict_readiness = settings.is_production or settings.require_approved_persona
    ready = production_ready if strict_readiness else True
    payload = {
        "status": "ready" if ready else "not_ready",
        "mode": settings.app_env,
        "checks": checks,
    }
    if not settings.is_production:
        payload["persona_warnings"] = persona_report.warnings
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )
