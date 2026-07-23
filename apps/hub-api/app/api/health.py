import asyncio
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


def _get_inference_health() -> dict:
    """Sync helper — called via to_thread to avoid blocking the event loop."""
    from app.services.inference import get_inference_client

    try:
        return get_inference_client().health()
    except Exception:
        return {"status": "unknown"}


def _get_queue_stats_sync(db: Session) -> dict:
    """Sync helper for queue stats."""
    from app.services.precompute import get_queue_stats

    try:
        return get_queue_stats(db)
    except Exception:
        return {"error": "db_unavailable"}


@router.get("/health")
async def health() -> dict:
    """Non-content health probe — no auth, no mailbox payloads (FR35 / Story 1.1)."""
    inference_health = await asyncio.to_thread(_get_inference_health)

    status = inference_health.get("status", "unknown")
    if status == "ok":
        overall = "ok"
    elif status == "down":
        overall = "down"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "service": "spoqsense-hub-api",
        "inference": inference_health,
    }


@router.get("/health/detail")
async def health_detail(db: Session = Depends(get_db)) -> dict:
    """Extended health with queue stats — ops only, no content (FR35)."""
    inference_health = await asyncio.to_thread(_get_inference_health)
    queue_stats = await asyncio.to_thread(_get_queue_stats_sync, db)

    status = inference_health.get("status", "unknown")
    if status == "ok":
        overall = "ok"
    elif status == "down":
        overall = "down"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "service": "spoqsense-hub-api",
        "inference": inference_health,
        "precompute_queue": queue_stats,
    }
