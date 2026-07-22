from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Non-content health probe — no auth, no mailbox payloads (FR35 / Story 1.1)."""
    return {
        "status": "ok",
        "service": "spoqsense-hub-api",
    }
