from __future__ import annotations

import hashlib
import json
import logging
import re

from fastapi import APIRouter
from sqlalchemy.exc import IntegrityError

from app.api.deps import AuthCtx, DbSession, MailboxContentAccess
from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.enums import MailboxKind
from app.domain.schemas import ConfirmScheduleIn, ConfirmScheduleOut
from app.services import audit as audit_svc
from app.services.mail_graph import get_mail_graph_client
from app.services.scheduling import extract_attendee_emails

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/mailbox_profiles", tags=["schedule"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


_MAX_ATTENDEES = 25


def _fingerprint(
    *,
    suggestion_id: str,
    slot_start: str,
    slot_end: str,
    attendees: list[str],
) -> str:
    # Subject is server-derived (Graph re-fetch / draft fallback) and may differ
    # across retries; keep it out of the fingerprint so replays stay stable.
    payload = {
        "suggestion_id": suggestion_id,
        "action": "schedule",
        "slot_start": slot_start,
        "slot_end": slot_end,
        "attendees": sorted(attendees),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_attendees(attendees: list[str]) -> list[str]:
    cleaned: list[str] = []
    for a in attendees:
        email = (a or "").strip().lower()
        if email and email not in cleaned:
            cleaned.append(email)
    if not cleaned:
        raise AppError(
            code="VALIDATION_ERROR",
            message="At least one attendee email is required.",
            status_code=422,
            retryable=False,
        )
    if len(cleaned) > _MAX_ATTENDEES:
        raise AppError(
            code="VALIDATION_ERROR",
            message=f"Too many attendees (max {_MAX_ATTENDEES}).",
            status_code=422,
            retryable=False,
        )
    for email in cleaned:
        if not _EMAIL_RE.match(email):
            raise AppError(
                code="VALIDATION_ERROR",
                message="Attendee list contains an invalid email address.",
                status_code=422,
                retryable=False,
            )
    return cleaned


def _load_slots_envelope(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        data = {}
    if isinstance(data, list):
        return {"slots": data, "attendees": [], "subject": ""}
    if not isinstance(data, dict):
        return {"slots": [], "attendees": [], "subject": ""}
    slots = data.get("slots") or []
    if not isinstance(slots, list):
        slots = []
    attendees = data.get("attendees") or []
    if not isinstance(attendees, list):
        attendees = []
    subject = str(data.get("subject") or "")
    return {"slots": slots, "attendees": attendees, "subject": subject}


@router.post("/{mailbox_profile_id}/confirm-schedule", response_model=ConfirmScheduleOut)
async def confirm_schedule(
    body: ConfirmScheduleIn,
    access: MailboxContentAccess,
    auth: AuthCtx,
    db: DbSession,
) -> ConfirmScheduleOut:
    suggestion = ai_store.get_suggestion(db, body.suggestion_id)
    if suggestion is None or suggestion.mailbox_profile_id != access.profile.id:
        raise AppError(
            code="NOT_FOUND",
            message="Suggestion not found for this mailbox.",
            status_code=404,
            retryable=False,
        )
    envelope = _load_slots_envelope(getattr(suggestion, "proposed_slots_json", None))
    slots = envelope["slots"]
    # Scheduling is available whenever the suggestion carries proposed slots
    # (the calendar was consulted), regardless of the classifier's category
    # label. The slot-match check below enforces the slot actually came from
    # this suggestion.
    if not slots:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Schedule is only available for suggestions with proposed times.",
            status_code=422,
            retryable=False,
        )
    slot_start = (body.slot_start or "").strip()
    slot_end = (body.slot_end or "").strip()
    matched = None
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        if str(slot.get("start") or "") == slot_start and str(slot.get("end") or "") == slot_end:
            matched = slot
            break
    if matched is None:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Chosen slot must match a proposed slot from the suggestion.",
            status_code=422,
            retryable=False,
        )

    # Validate slot ordering + not-in-the-past BEFORE reserving an idempotency key,
    # so a bad payload never leaves an orphan reservation that blocks legit retries.
    from datetime import datetime, timezone

    from app.services.mail_graph import _parse_graph_dt

    start_dt = _parse_graph_dt(slot_start)
    end_dt = _parse_graph_dt(slot_end)
    if start_dt is None or end_dt is None or end_dt <= start_dt:
        raise AppError(
            code="VALIDATION_ERROR",
            message="slot_end must be after slot_start.",
            status_code=422,
            retryable=False,
        )
    if end_dt <= datetime.now(timezone.utc):
        raise AppError(
            code="VALIDATION_ERROR",
            message="Cannot schedule a meeting in the past.",
            status_code=422,
            retryable=False,
        )

    stored_attendees = [str(a).strip().lower() for a in envelope.get("attendees") or []]
    allowed = {
        *(stored_attendees),
        *(
            [suggestion.sender.strip().lower()]
            if suggestion.sender and suggestion.sender.strip()
            else []
        ),
    }
    allowed.discard((access.profile.email or "").strip().lower())
    if body.attendees:
        attendees = _valid_attendees(body.attendees)
        # Client-supplied attendees must be a subset of the analyzed mail participants.
        # If we have no participants to check against, reject overrides (fail closed).
        extra = set(attendees) - allowed
        if extra:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Attendees must be from the analyzed mail participants.",
                status_code=422,
                retryable=False,
            )
    else:
        attendees = extract_attendee_emails(
            suggestion.sender or "",
            stored_attendees,
            None,
            access.profile.email,
        )
        attendees = _valid_attendees(attendees)

    subject = (envelope.get("subject") or "").strip()
    if not subject:
        # Best-effort re-fetch; fall back to draft first line / Meeting.
        try:
            client = get_mail_graph_client()
            msg = client.get_message(
                user_assertion=auth.user_assertion,
                tenant_id=auth.principal.tenant_id,
                message_id=suggestion.message_id,
                mailbox_kind=MailboxKind(access.profile.kind),
                mailbox_email=access.profile.email,
                graph_mailbox_id=access.profile.graph_mailbox_id,
            )
            subject = (msg.subject or "").strip()
        except Exception:
            subject = ""
    if not subject:
        first_line = (suggestion.draft or "").strip().splitlines()
        subject = first_line[0][:120] if first_line else "Meeting"
    subject = subject[:500] or "Meeting"

    fp = _fingerprint(
        suggestion_id=suggestion.id,
        slot_start=slot_start,
        slot_end=slot_end,
        attendees=attendees,
    )

    existing = ai_store.get_idempotency(
        db, mailbox_profile_id=access.profile.id, key=body.idempotency_key
    )
    def _replay_or_conflict(row) -> ConfirmScheduleOut:
        if row.request_fingerprint and row.request_fingerprint != fp:
            raise AppError(
                code="CONFLICT",
                message="Idempotency key was already used with a different schedule payload.",
                status_code=409,
                retryable=False,
            )
        if not row.graph_message_id:
            raise AppError(
                code="CONFLICT",
                message="Schedule still in progress or prior create failed; retry with a new key.",
                status_code=409,
                retryable=True,
            )
        return ConfirmScheduleOut(
            status="ok",
            graph_event_id=row.graph_message_id,
            idempotent_replay=True,
        )

    if existing is not None:
        return _replay_or_conflict(existing)

    try:
        reserved = ai_store.reserve_idempotency(
            db,
            mailbox_profile_id=access.profile.id,
            key=body.idempotency_key,
            suggestion_id=suggestion.id,
            action="schedule",
            request_fingerprint=fp,
            actor_oid=auth.principal.subject,
        )
    except IntegrityError:
        existing = ai_store.get_idempotency(
            db, mailbox_profile_id=access.profile.id, key=body.idempotency_key
        )
        if existing is None:
            raise
        return _replay_or_conflict(existing)

    if reserved.graph_message_id:
        return ConfirmScheduleOut(
            status="ok",
            graph_event_id=reserved.graph_message_id,
            idempotent_replay=True,
        )

    kind = MailboxKind(access.profile.kind)
    client = get_mail_graph_client()
    event_body = (
        f"Scheduled from mail: {subject}\n"
        f"Suggested time: {matched.get('label') or f'{slot_start} – {slot_end}'}"
    )
    result = client.create_calendar_event(
        user_assertion=auth.user_assertion,
        tenant_id=auth.principal.tenant_id,
        mailbox_kind=kind,
        mailbox_email=access.profile.email,
        graph_mailbox_id=access.profile.graph_mailbox_id,
        subject=subject,
        start_iso=slot_start,
        end_iso=slot_end,
        attendees=attendees,
        body=event_body,
    )

    # The Graph event already exists; persisting the id must not make us "lose" it.
    # If completion fails, still return the created id so the client does not retry
    # (a retry with a new key would create a duplicate event).
    try:
        ai_store.complete_idempotency(
            db, row=reserved, graph_message_id=result.graph_event_id
        )
    except Exception:
        logger.exception(
            "schedule_complete_idempotency_failed suggestion_id=%s event_id=%s",
            suggestion.id,
            result.graph_event_id,
        )
    audit_svc.write_audit(
        db,
        mailbox_profile_id=access.profile.id,
        suggestion_id=suggestion.id,
        decision="confirm_schedule",
        actor_oid=auth.principal.subject,
        detail=f"idempotency_key_len={len(body.idempotency_key)}",
    )
    return ConfirmScheduleOut(
        status="ok",
        graph_event_id=result.graph_event_id,
        idempotent_replay=False,
    )
