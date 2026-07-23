"""Mailbox profile inspector — metadata, routes, hub-side behavior summary cache."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.repositories import ai_store
from app.domain.enums import HistoryProfileStatus, HistorySyncPhase
from app.domain.models import MailboxProfile
from app.domain.schemas import (
    BehaviorSummaryOut,
    LearnedRouteOut,
    ProfileInspectOut,
)
from app.services import learning
from app.services.inference import get_inference_client

logger = logging.getLogger(__name__)

_DUTCH_HINTS = re.compile(
    r"\b(hallo|hoi|beste|vriendelijke|groeten|bedankt|graag|bijlage|factuur|vergadering)\b",
    re.I,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _routes_for_profile(db: Session, profile_id: str) -> list[LearnedRouteOut]:
    edges = learning.list_routing_edges(db, profile_id, limit=100)
    routes: list[LearnedRouteOut] = []
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
    return routes


def persist_behavior_summary(db: Session, profile: MailboxProfile, text: str) -> None:
    profile.behavior_summary_text = (text or "").strip() or None
    profile.behavior_summary_updated_at = _utcnow() if profile.behavior_summary_text else None
    db.commit()
    db.refresh(profile)


def grounded_behavior_summary(
    *,
    mailbox_email: str,
    kind: str,
    chunk_count: int,
    routes: list[LearnedRouteOut],
    samples: list[str],
) -> str:
    """Persona prompt from routes + Sent samples — no LLM, no invented empty habits."""
    blob = "\n".join(samples)
    dutch_hits = len(_DUTCH_HINTS.findall(blob))
    avg_len = int(sum(len(s) for s in samples) / len(samples)) if samples else 0
    if not samples:
        lang = "unknown (no Sent samples available)"
        length = "style not yet observable from samples"
        habits = "Do not invent style habits until Sent samples are available."
        sample_note = "0 recent Sent samples"
    else:
        if dutch_hits >= 2:
            lang = "mostly Dutch"
        else:
            lang = "mostly English or mixed"
        if avg_len < 280:
            length = "short, concise replies"
        else:
            length = "medium-length replies"
        habits = "Match tone of prior Sent mail; do not invent facts or recipients."
        sample_note = f"{min(len(samples), 8)} recent Sent samples"
    route_lines = [
        f"- {r.pattern_key} → {r.route_email}"
        + (f" ({r.route_name})" if r.route_name else "")
        + f" [weight {r.weight:g}]"
        for r in routes[:12]
    ]
    if not route_lines:
        route_lines = ["- (none learned yet)"]
    elif len(routes) > 12:
        route_lines.append(f"- … and {len(routes) - 12} more")
    return (
        f"Mailbox: {mailbox_email} ({kind})\n"
        f"Style: {lang}; {length} (from {sample_note}).\n"
        f"Habits: {habits}\n"
        "Routing:\n"
        + "\n".join(route_lines)
        + f"\nHistory: {chunk_count} Sent chunks indexed."
    )


def ensure_cached_summary(
    db: Session,
    profile: MailboxProfile,
    *,
    allow_llm: bool = False,
) -> str | None:
    """Return cached summary; if missing and history exists, fill grounded (or LLM if allowed).

    Uses SELECT FOR UPDATE to prevent concurrent duplicate model calls.
    """
    cached = (getattr(profile, "behavior_summary_text", None) or "").strip()
    if cached:
        return cached

    # Acquire row lock to prevent concurrent summary computation
    from sqlalchemy import select

    try:
        locked_profile = db.execute(
            select(MailboxProfile)
            .where(MailboxProfile.id == profile.id)
            .with_for_update(nowait=False)
        ).scalar_one_or_none()
    except Exception:
        # SQLite doesn't support FOR UPDATE — proceed without lock
        locked_profile = profile

    if locked_profile is None:
        return None

    # Re-check after lock — another thread may have populated the cache
    refreshed_text = (getattr(locked_profile, "behavior_summary_text", None) or "").strip()
    if refreshed_text:
        return refreshed_text

    chunk_count = int(ai_store.count_chunks(db, profile.id) or 0)
    routes = _routes_for_profile(db, profile.id)
    if chunk_count == 0 and not routes:
        return None

    samples = ai_store.sample_chunk_texts(db, profile.id, limit=8) if chunk_count else []
    if allow_llm and chunk_count > 0:
        summary = _compute_behavior_summary(
            profile=profile,
            chunk_count=chunk_count,
            routes=routes,
            samples=samples,
        )
        text = (summary.text or "").strip() if summary.status == "ok" else ""
    else:
        text = grounded_behavior_summary(
            mailbox_email=profile.email,
            kind=str(profile.kind),
            chunk_count=chunk_count,
            routes=routes,
            samples=samples,
        )
    if text:
        persist_behavior_summary(db, locked_profile, text)
        return text
    return None


def refresh_behavior_summary(db: Session, profile: MailboxProfile) -> BehaviorSummaryOut:
    """Recompute summary (LLM preferred) and persist when ok/empty-with-routes."""
    chunk_count = int(ai_store.count_chunks(db, profile.id) or 0)
    routes = _routes_for_profile(db, profile.id)
    samples = ai_store.sample_chunk_texts(db, profile.id, limit=8) if chunk_count else []
    summary = _compute_behavior_summary(
        profile=profile,
        chunk_count=chunk_count,
        routes=routes,
        samples=samples,
    )
    if summary.status == "ok" and (summary.text or "").strip():
        persist_behavior_summary(db, profile, summary.text or "")
    elif summary.status == "empty":
        persist_behavior_summary(db, profile, "")
    return summary


def build_profile_inspect(
    db: Session,
    profile: MailboxProfile,
    *,
    include_summary: bool = True,
) -> ProfileInspectOut:
    from app.services.history_sync import profile_history_snapshot

    snap = profile_history_snapshot(db, profile.id)
    db.refresh(profile)
    chunk_count = int(snap.get("total_chunks") or 0)
    indexed_messages = int(ai_store.count_indexed_messages(db, profile.id) or 0)
    routes = _routes_for_profile(db, profile.id)
    summary = BehaviorSummaryOut(status="skipped", text=None)
    if include_summary:
        summary = refresh_behavior_summary(db, profile)
        # Prefer freshly persisted cache for display consistency.
        cached = (getattr(profile, "behavior_summary_text", None) or "").strip()
        if cached and summary.status == "ok":
            summary = BehaviorSummaryOut(status="ok", text=cached, error=None)
    return ProfileInspectOut(
        id=profile.id,
        email=profile.email,
        kind=profile.kind,
        connection_status=profile.connection_status,
        connection_error=profile.connection_error,
        history_status=snap.get("history_status") or HistoryProfileStatus.NOT_STARTED,
        last_history_sync_at=snap.get("last_history_sync_at"),
        history_sync_error=snap.get("history_sync_error"),
        history_chunk_count=chunk_count,
        indexed_message_count=indexed_messages,
        history_sync_phase=snap.get("history_sync_phase") or HistorySyncPhase.NOT_STARTED,
        history_messages_fetched=int(snap.get("history_messages_fetched") or 0),
        history_messages_target=int(snap.get("history_messages_target") or 0),
        routes=routes,
        behavior_summary=summary,
    )


def _compute_behavior_summary(
    *,
    profile: MailboxProfile,
    chunk_count: int,
    routes: list[LearnedRouteOut],
    samples: list[str],
) -> BehaviorSummaryOut:
    if chunk_count == 0 and not routes:
        return BehaviorSummaryOut(
            status="empty",
            text=(
                f"No style profile yet for {profile.email}. "
                "Sent history is empty or still syncing — no habits invented."
            ),
        )
    if chunk_count == 0 and routes:
        text = grounded_behavior_summary(
            mailbox_email=profile.email,
            kind=str(profile.kind),
            chunk_count=0,
            routes=routes,
            samples=[],
        )
        return BehaviorSummaryOut(status="ok", text=text, error=None)

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
        if (text or "").strip():
            return BehaviorSummaryOut(status="ok", text=text.strip(), error=None)
        logger.info("behavior_summary_empty_using_grounded")
    except Exception as exc:  # AppError or transport — keep inspector usable
        logger.info("behavior_summary_failed err_type=%s", type(exc).__name__)

    fallback = grounded_behavior_summary(
        mailbox_email=profile.email,
        kind=str(profile.kind),
        chunk_count=chunk_count,
        routes=routes,
        samples=samples,
    )
    return BehaviorSummaryOut(status="ok", text=fallback, error=None)
