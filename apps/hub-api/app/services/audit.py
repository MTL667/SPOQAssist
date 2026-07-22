from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.models import AuditEvent


def write_audit(
    db: Session,
    *,
    mailbox_profile_id: str,
    suggestion_id: str | None,
    decision: str,
    actor_oid: str,
    detail: str = "",
) -> AuditEvent:
    # Never put subject/body into detail.
    event = AuditEvent(
        mailbox_profile_id=mailbox_profile_id,
        suggestion_id=suggestion_id,
        decision=decision,
        actor_oid=actor_oid,
        detail=detail[:1024],
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
