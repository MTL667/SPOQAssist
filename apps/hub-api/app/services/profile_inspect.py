"""Mailbox profile inspector — metadata, routes, hub-side behavior summary."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.repositories import ai_store
from app.domain.enums import HistoryProfileStatus
from app.domain.models import MailboxProfile
from app.domain.schemas import (
    BehaviorSummaryOut,
    LearnedRouteOut,
    ProfileInspectOut,
)
from app.services import learning
from app.services.inference import get_inference_client

logger = logging.getLogger(__name__)


def build_profile_inspect(
    db: Session,
    profile: MailboxProfile,
    *,
    include_summary: bool = True,
) -> ProfileInspectOut:
    chunk_count = int(ai_store.count_chunks(db, profile.id) or 0)
    indexed_messages = int(ai_store.count_indexed_messages(db, profile.id) or 0)
    edges = learning.list_routing_edges(db, profile.id, limit=100)
    routes = []
    for e in edges:
        try:
            weight = float(e.weight) if e.weight is not None else 1.0
        except (TypeError, ValueError):
            weight = 1.0
        routes.append(
            LearnedRouteOut(
                pattern_key=e.pattern_key,
                route_email=e.route_email,
                route_name=e.route_name,
                weight=weight,
            )
        )
    last = getattr(profile, "last_history_sync_at", None)
    summary = BehaviorSummaryOut(status="skipped", text=None)
    if include_summary:
        summary = _behavior_summary(
            profile=profile,
            chunk_count=chunk_count,
            routes=routes,
            samples=ai_store.sample_chunk_texts(db, profile.id, limit=8),
        )
    return ProfileInspectOut(
        id=profile.id,
        email=profile.email,
        kind=profile.kind,
        connection_status=profile.connection_status,
        connection_error=profile.connection_error,
        history_status=getattr(profile, "history_status", None)
        or HistoryProfileStatus.NOT_STARTED,
        last_history_sync_at=last.isoformat() if last else None,
        history_sync_error=getattr(profile, "history_sync_error", None),
        history_chunk_count=chunk_count,
        indexed_message_count=indexed_messages,
        routes=routes,
        behavior_summary=summary,
    )


def _behavior_summary(
    *,
    profile: MailboxProfile,
    chunk_count: int,
    routes: list[LearnedRouteOut],
    samples: list[str],
) -> BehaviorSummaryOut:
    if chunk_count == 0:
        route_note = ""
        if routes:
            route_note = (
                f" Learned routes exist ({len(routes)}), but Sent history is empty — "
                "no style habits invented from mail."
            )
        return BehaviorSummaryOut(
            status="empty",
            text=(
                f"No style profile yet for {profile.email}. "
                "Sent history is empty or still syncing — no habits invented."
                f"{route_note}"
            ),
        )
    route_lines = [
        f"{r.pattern_key} → {r.route_email}"
        + (f" ({r.route_name})" if r.route_name else "")
        + f" [weight {r.weight:g}]"
        for r in routes[:12]
    ]
    client = get_inference_client()
    try:
        text = client.summarize_mailbox_behavior(
            mailbox_email=profile.email,
            kind=str(profile.kind),
            chunk_count=chunk_count,
            route_lines=route_lines,
            sample_snippets=samples,
        )
    except Exception as exc:  # AppError or transport — keep inspector usable
        logger.info("behavior_summary_failed err_type=%s", type(exc).__name__)
        return BehaviorSummaryOut(
            status="error",
            text=None,
            error="Behavior summary unavailable — retry when the local model is ready.",
        )
    if not (text or "").strip():
        return BehaviorSummaryOut(
            status="error",
            text=None,
            error="Behavior summary was empty — retry.",
        )
    return BehaviorSummaryOut(status="ok", text=text.strip(), error=None)
