from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession, MailboxContentAccess
from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.enums import FeedbackOutcome, MailboxKind
from app.domain.schemas import FeedbackIn, FeedbackOut
from app.services import audit as audit_svc
from app.services.learning import apply_routing_correction, pattern_key_from_sender

router = APIRouter(prefix="/v1/mailbox_profiles", tags=["feedback"])


@router.post("/{mailbox_profile_id}/feedback", response_model=FeedbackOut)
async def submit_feedback(
    body: FeedbackIn,
    access: MailboxContentAccess,
    principal: CurrentPrincipal,
    db: DbSession,
) -> FeedbackOut:
    suggestion = ai_store.get_suggestion(db, body.suggestion_id)
    if suggestion is None or suggestion.mailbox_profile_id != access.profile.id:
        raise AppError(
            code="NOT_FOUND",
            message="Suggestion not found for this mailbox.",
            status_code=404,
            retryable=False,
        )

    event = ai_store.create_feedback(
        db,
        suggestion_id=suggestion.id,
        mailbox_profile_id=access.profile.id,
        outcome=body.outcome.value,
        edited_draft=body.edited_draft,
        corrected_route_email=body.corrected_route_email,
        teach=body.teach,
        actor_oid=principal.subject,
    )
    audit = audit_svc.write_audit(
        db,
        mailbox_profile_id=access.profile.id,
        suggestion_id=suggestion.id,
        decision=body.outcome.value,
        actor_oid=principal.subject,
        detail=f"teach={body.teach}",
    )

    if (
        body.outcome == FeedbackOutcome.REROUTE
        and body.teach
        and body.corrected_route_email
        and access.profile.kind == MailboxKind.SHARED
    ):
        # Learning cycle for shared only — never pulls personal indexes (FR30)
        apply_routing_correction(
            db,
            mailbox_profile_id=access.profile.id,
            pattern_key=pattern_key_from_sender(suggestion.sender or suggestion.message_id),
            route_email=body.corrected_route_email,
            route_name=body.corrected_route_name,
        )

    return FeedbackOut(
        feedback_id=event.id,
        suggestion_id=suggestion.id,
        outcome=body.outcome,
        audit_id=audit.id,
    )
