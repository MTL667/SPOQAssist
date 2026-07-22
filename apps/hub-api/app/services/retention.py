from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.models import (
    AuditEvent,
    FeedbackEvent,
    MailChunk,
    RetentionPolicy,
    RoutingEdge,
    Suggestion,
)

logger = logging.getLogger(__name__)


def get_or_default_policy(db: Session, mailbox_profile_id: str) -> RetentionPolicy:
    row = db.get(RetentionPolicy, mailbox_profile_id)
    if row is None:
        row = RetentionPolicy(mailbox_profile_id=mailbox_profile_id, retain_days=365)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def run_retention(db: Session, mailbox_profile_id: str) -> dict[str, int]:
    policy = get_or_default_policy(db, mailbox_profile_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=policy.retain_days)

    chunks = db.execute(
        delete(MailChunk).where(
            MailChunk.mailbox_profile_id == mailbox_profile_id,
            MailChunk.created_at < cutoff,
        )
    ).rowcount

    db.execute(
        delete(RoutingEdge).where(
            RoutingEdge.mailbox_profile_id == mailbox_profile_id,
            RoutingEdge.created_at < cutoff,
        )
    )

    # Suggestions older than cutoff (AI-derived)
    old_suggestions = list(
        db.execute(
            select(Suggestion.id).where(
                Suggestion.mailbox_profile_id == mailbox_profile_id,
                Suggestion.created_at < cutoff,
            )
        ).scalars()
    )
    if old_suggestions:
        db.execute(delete(FeedbackEvent).where(FeedbackEvent.suggestion_id.in_(old_suggestions)))
        db.execute(delete(Suggestion).where(Suggestion.id.in_(old_suggestions)))

    purged_audit = 0
    if policy.purge_audit_with_indexes:
        purged_audit = db.execute(
            delete(AuditEvent).where(
                AuditEvent.mailbox_profile_id == mailbox_profile_id,
                AuditEvent.created_at < cutoff,
            )
        ).rowcount

    db.commit()
    logger.info(
        "retention_purged mailbox_profile_id=%s chunks=%s suggestions=%s audit=%s",
        mailbox_profile_id,
        chunks or 0,
        len(old_suggestions),
        purged_audit or 0,
    )
    return {
        "purged_chunks": int(chunks or 0),
        "purged_suggestions": len(old_suggestions),
        "purged_audit": int(purged_audit or 0),
    }
