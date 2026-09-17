from __future__ import annotations

from fastapi import APIRouter, Request

from app.errors import service_not_ready_error
from app.models.profile import PublicProfileResponse

router = APIRouter(prefix="/api/v1", tags=["profile"])


@router.get("/profile", response_model=PublicProfileResponse)
async def public_profile(request: Request) -> dict[str, object]:
    snapshot = request.app.state.persona_snapshot
    if snapshot is None:
        raise service_not_ready_error()
    return snapshot.public_profile()
