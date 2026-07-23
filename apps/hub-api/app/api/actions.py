"""Actions API — view, dismiss extracted actions from pre-computed suggestions."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AuthCtx, DbSession, MailboxContentAccess
from app.core.errors import AppError
from app.domain.models import ExtractedAction
from app.domain.schemas import ActionItem

from sqlalchemy import select

router = APIRouter(prefix="/v1/mailbox_profiles", tags=["actions"])


@router.get("/{mailbox_profile_id}/actions", response_model=list[ActionItem])
def list_actions(
    mailbox_profile_id: str,
    access: MailboxContentAccess,
    db: DbSession,
    *,
    include_dismissed: bool = False,
) -> list[ActionItem]:
    """List extracted actions for the mailbox (recent, undismissed by default)."""
    if mailbox_profile_id != access.profile.id:
        raise AppError(
            code="FORBIDDEN",
            message="Profile ID mismatch.",
            status_code=403,
            retryable=False,
        )
    stmt = (
        select(ExtractedAction)
        .where(ExtractedAction.mailbox_profile_id == access.profile.id)
        .order_by(ExtractedAction.created_at.desc())
        .limit(50)
    )
    if not include_dismissed:
        stmt = stmt.where(ExtractedAction.dismissed == False)  # noqa: E712

    rows = list(db.execute(stmt).scalars().all())
    return [
        ActionItem(
            id=row.id,
            action_type=row.action_type,
            description=row.description,
            due_date=row.due_date,
            dismissed=row.dismissed,
        )
        for row in rows
    ]


@router.post("/{mailbox_profile_id}/actions/{action_id}/dismiss")
def dismiss_action(
    mailbox_profile_id: str,
    action_id: str,
    access: MailboxContentAccess,
    db: DbSession,
) -> dict:
    """Dismiss an extracted action (user says 'not relevant')."""
    if mailbox_profile_id != access.profile.id:
        raise AppError(
            code="FORBIDDEN",
            message="Profile ID mismatch.",
            status_code=403,
            retryable=False,
        )
    action = db.get(ExtractedAction, action_id)
    if action is None or action.mailbox_profile_id != access.profile.id:
        raise AppError(
            code="NOT_FOUND",
            message="Action not found.",
            status_code=404,
            retryable=False,
        )
    action.dismissed = True
    db.commit()
    return {"status": "dismissed", "action_id": action_id}


@router.get("/{mailbox_profile_id}/messages/{message_id}/actions", response_model=list[ActionItem])
def message_actions(
    mailbox_profile_id: str,
    message_id: str,
    access: MailboxContentAccess,
    db: DbSession,
) -> list[ActionItem]:
    """Get actions for a specific message."""
    if mailbox_profile_id != access.profile.id:
        raise AppError(
            code="FORBIDDEN",
            message="Profile ID mismatch.",
            status_code=403,
            retryable=False,
        )
    stmt = (
        select(ExtractedAction)
        .where(
            ExtractedAction.mailbox_profile_id == access.profile.id,
            ExtractedAction.message_id == message_id,
        )
        .order_by(ExtractedAction.created_at.desc())
    )
    rows = list(db.execute(stmt).scalars().all())
    return [
        ActionItem(
            id=row.id,
            action_type=row.action_type,
            description=row.description,
            due_date=row.due_date,
            dismissed=row.dismissed,
        )
        for row in rows
    ]
