from __future__ import annotations

import hashlib
import json
import re

from fastapi import APIRouter
from sqlalchemy.exc import IntegrityError

from app.api.deps import AuthCtx, DbSession, MailboxContentAccess
from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.enums import MailboxKind, OutboundAction
from app.domain.schemas import ConfirmOutboundIn, ConfirmOutboundOut
from app.services import audit as audit_svc
from app.services.mail_graph import AI_DISCLOSURE_FOOTER, get_mail_graph_client

router = APIRouter(prefix="/v1/mailbox_profiles", tags=["confirm"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _fingerprint(
    *,
    suggestion_id: str,
    action: str,
    recipients: list[str],
    subject: str,
    body: str,
) -> str:
    payload = {
        "suggestion_id": suggestion_id,
        "action": action,
        "recipients": recipients,
        "subject": subject,
        "body": body,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_recipients(recipients: list[str]) -> list[str]:
    cleaned = [r.strip().lower() for r in recipients if r and r.strip()]
    if not cleaned:
        raise AppError(
            code="VALIDATION_ERROR",
            message="At least one valid recipient email is required.",
            status_code=422,
            retryable=False,
        )
    for email in cleaned:
        if not _EMAIL_RE.match(email):
            raise AppError(
                code="VALIDATION_ERROR",
                message="Recipient list contains an invalid email address.",
                status_code=422,
                retryable=False,
            )
    return cleaned


@router.post("/{mailbox_profile_id}/confirm-outbound", response_model=ConfirmOutboundOut)
async def confirm_outbound(
    body: ConfirmOutboundIn,
    access: MailboxContentAccess,
    auth: AuthCtx,
    db: DbSession,
) -> ConfirmOutboundOut:
    if body.action == OutboundAction.NONE:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Outbound action must be send or forward.",
            status_code=422,
            retryable=False,
        )

    suggestion = ai_store.get_suggestion(db, body.suggestion_id)
    if suggestion is None or suggestion.mailbox_profile_id != access.profile.id:
        raise AppError(
            code="NOT_FOUND",
            message="Suggestion not found for this mailbox.",
            status_code=404,
            retryable=False,
        )

    recipients = _valid_recipients(body.recipients)
    # Bind outbound to suggestion: forward must target suggested/corrected route when present.
    if body.action == OutboundAction.FORWARD and suggestion.suggested_route_email:
        allowed = {suggestion.suggested_route_email.lower()}
        latest = ai_store.latest_reroute_email(db, suggestion_id=suggestion.id)
        if latest:
            allowed.add(latest.lower())
        if set(recipients) - allowed:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Forward recipients must match the suggested or taught route.",
                status_code=422,
                retryable=False,
            )

    subject = (body.subject or f"Re: message").strip()[:500]
    # Prefer edited body, else suggestion draft — never an unrelated freeform relay without draft.
    content = body.body if body.body is not None else (suggestion.draft or "")
    if body.action == OutboundAction.SEND and not content.strip():
        raise AppError(
            code="VALIDATION_ERROR",
            message="Send requires a draft body from the suggestion or an edit.",
            status_code=422,
            retryable=False,
        )

    # Always disclose for AI-assisted suggestion confirm path (ignore client false).
    if AI_DISCLOSURE_FOOTER.strip() not in content:
        content = content + AI_DISCLOSURE_FOOTER
    disclosure_applied = True

    fp = _fingerprint(
        suggestion_id=suggestion.id,
        action=body.action.value,
        recipients=recipients,
        subject=subject,
        body=content,
    )

    existing = ai_store.get_idempotency(
        db, mailbox_profile_id=access.profile.id, key=body.idempotency_key
    )
    if existing is not None:
        if existing.request_fingerprint and existing.request_fingerprint != fp:
            raise AppError(
                code="CONFLICT",
                message="Idempotency key was already used with a different outbound payload.",
                status_code=409,
                retryable=False,
            )
        return ConfirmOutboundOut(
            status="ok",
            graph_message_id=existing.graph_message_id,
            idempotent_replay=True,
            ai_disclosure_applied=disclosure_applied,
        )

    # Reserve key before Graph mutate to reduce double-send races.
    try:
        reserved = ai_store.reserve_idempotency(
            db,
            mailbox_profile_id=access.profile.id,
            key=body.idempotency_key,
            suggestion_id=suggestion.id,
            action=body.action.value,
            request_fingerprint=fp,
            actor_oid=auth.principal.subject,
        )
    except IntegrityError:
        existing = ai_store.get_idempotency(
            db, mailbox_profile_id=access.profile.id, key=body.idempotency_key
        )
        if existing is None:
            raise
        if existing.request_fingerprint and existing.request_fingerprint != fp:
            raise AppError(
                code="CONFLICT",
                message="Idempotency key was already used with a different outbound payload.",
                status_code=409,
                retryable=False,
            )
        return ConfirmOutboundOut(
            status="ok",
            graph_message_id=existing.graph_message_id,
            idempotent_replay=True,
            ai_disclosure_applied=disclosure_applied,
        )

    if reserved.graph_message_id:
        return ConfirmOutboundOut(
            status="ok",
            graph_message_id=reserved.graph_message_id,
            idempotent_replay=True,
            ai_disclosure_applied=disclosure_applied,
        )

    kind = MailboxKind(access.profile.kind)
    client = get_mail_graph_client()
    if body.action == OutboundAction.SEND:
        result = client.send_mail(
            user_assertion=auth.user_assertion,
            tenant_id=auth.principal.tenant_id,
            recipients=recipients,
            subject=subject,
            body=content,
            mailbox_kind=kind,
            mailbox_email=access.profile.email,
            graph_mailbox_id=access.profile.graph_mailbox_id,
        )
    else:
        result = client.forward_mail(
            user_assertion=auth.user_assertion,
            tenant_id=auth.principal.tenant_id,
            message_id=suggestion.message_id,
            recipients=recipients,
            comment=content,
            mailbox_kind=kind,
            mailbox_email=access.profile.email,
            graph_mailbox_id=access.profile.graph_mailbox_id,
        )

    ai_store.complete_idempotency(
        db, row=reserved, graph_message_id=result.graph_message_id
    )
    audit_svc.write_audit(
        db,
        mailbox_profile_id=access.profile.id,
        suggestion_id=suggestion.id,
        decision=f"confirm_{body.action.value}",
        actor_oid=auth.principal.subject,
        detail=f"idempotency_key_len={len(body.idempotency_key)}",
    )
    return ConfirmOutboundOut(
        status="ok",
        graph_message_id=result.graph_message_id,
        idempotent_replay=False,
        ai_disclosure_applied=disclosure_applied,
    )
