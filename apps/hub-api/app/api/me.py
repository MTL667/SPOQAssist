"""Protected identity stub — proves Entra JWT acceptance (Story 1.2)."""

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal

router = APIRouter(prefix="/v1", tags=["identity"])


@router.get("/me")
async def me(principal: CurrentPrincipal) -> dict:
    return {
        "subject": principal.subject,
        "tenant_id": principal.tenant_id,
        "upn": principal.upn,
        "name": principal.name,
    }
