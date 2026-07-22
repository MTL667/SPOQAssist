from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    FeedbackEvent,
    MailChunk,
    OutboundIdempotency,
    RetentionPolicy,
    SharedAiSettings,
    Suggestion,
)
from app.services.inference import EMBEDDING_DIM

logger = logging.getLogger(__name__)


def get_suggestion(db: Session, suggestion_id: str) -> Suggestion | None:
    return db.get(Suggestion, suggestion_id)


def create_feedback(
    db: Session,
    *,
    suggestion_id: str,
    mailbox_profile_id: str,
    outcome: str,
    edited_draft: str | None,
    corrected_route_email: str | None,
    teach: bool,
    actor_oid: str,
) -> FeedbackEvent:
    event = FeedbackEvent(
        suggestion_id=suggestion_id,
        mailbox_profile_id=mailbox_profile_id,
        outcome=outcome,
        edited_draft=edited_draft,
        corrected_route_email=corrected_route_email.lower() if corrected_route_email else None,
        teach=teach,
        actor_oid=actor_oid,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_idempotency(
    db: Session, *, mailbox_profile_id: str, key: str
) -> OutboundIdempotency | None:
    stmt = select(OutboundIdempotency).where(
        OutboundIdempotency.mailbox_profile_id == mailbox_profile_id,
        OutboundIdempotency.idempotency_key == key,
    )
    return db.execute(stmt).scalar_one_or_none()


def reserve_idempotency(
    db: Session,
    *,
    mailbox_profile_id: str,
    key: str,
    suggestion_id: str,
    action: str,
    request_fingerprint: str,
    actor_oid: str,
) -> OutboundIdempotency:
    row = OutboundIdempotency(
        mailbox_profile_id=mailbox_profile_id,
        idempotency_key=key,
        suggestion_id=suggestion_id,
        action=action,
        request_fingerprint=request_fingerprint,
        graph_message_id=None,
        actor_oid=actor_oid,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def complete_idempotency(
    db: Session, *, row: OutboundIdempotency, graph_message_id: str
) -> OutboundIdempotency:
    row.graph_message_id = graph_message_id
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_reroute_email(db: Session, *, suggestion_id: str) -> str | None:
    stmt = (
        select(FeedbackEvent)
        .where(
            FeedbackEvent.suggestion_id == suggestion_id,
            FeedbackEvent.outcome == "reroute",
        )
        .order_by(FeedbackEvent.created_at.desc())
    )
    row = db.execute(stmt).scalars().first()
    return row.corrected_route_email if row else None


def index_chunks(
    db: Session,
    *,
    mailbox_profile_id: str,
    items: list[dict[str, Any]],
    embed_fn: Callable[[str], list[float]],
) -> int:
    count = 0
    for item in items:
        text = str(item.get("text") or "").strip()
        message_id = str(item.get("message_id") or "")
        if not text or not message_id:
            continue
        emb = embed_fn(text)
        if len(emb) != EMBEDDING_DIM:
            emb = (emb + [0.0] * EMBEDDING_DIM)[:EMBEDDING_DIM]
        db.add(
            MailChunk(
                mailbox_profile_id=mailbox_profile_id,
                source_message_id=message_id,
                chunk_text=text[:8000],
                embedding_json=json.dumps(emb),
                embedding_dim=EMBEDDING_DIM,
            )
        )
        count += 1
    db.commit()
    logger.info(
        "chunks_indexed mailbox_profile_id=%s count=%s dim=%s",
        mailbox_profile_id,
        count,
        EMBEDDING_DIM,
    )
    return count


def get_ai_settings(db: Session, mailbox_profile_id: str) -> SharedAiSettings | None:
    return db.get(SharedAiSettings, mailbox_profile_id)


def upsert_ai_settings(
    db: Session,
    *,
    mailbox_profile_id: str,
    enabled: bool,
    auto_analyze: bool,
    default_forward_hint: str | None,
    notes: str,
) -> SharedAiSettings:
    row = get_ai_settings(db, mailbox_profile_id)
    if row is None:
        row = SharedAiSettings(mailbox_profile_id=mailbox_profile_id)
        db.add(row)
    row.enabled = enabled
    row.auto_analyze = auto_analyze
    row.default_forward_hint = default_forward_hint
    row.notes = notes
    db.commit()
    db.refresh(row)
    return row


def upsert_retention(
    db: Session,
    *,
    mailbox_profile_id: str,
    retain_days: int,
    purge_audit_with_indexes: bool,
) -> RetentionPolicy:
    row = db.get(RetentionPolicy, mailbox_profile_id)
    if row is None:
        row = RetentionPolicy(mailbox_profile_id=mailbox_profile_id)
        db.add(row)
    row.retain_days = retain_days
    row.purge_audit_with_indexes = purge_audit_with_indexes
    db.commit()
    db.refresh(row)
    return row
