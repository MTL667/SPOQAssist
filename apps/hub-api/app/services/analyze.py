from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.enums import Confidence, MailboxKind
from app.domain.models import Suggestion
from app.domain.schemas import (
    AnalyzeRequest,
    AttachmentWarning,
    RouteOut,
    SuggestionOut,
    WhyItem,
)
from app.services.inference import get_inference_client
from app.services.learning import pattern_key_from_sender
from app.services.mail_read import load_message_for_analyze
from app.services.retrieve import lookup_learned_route, retrieve_similar

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
SUPPORTED_ATTACHMENT_SUFFIXES = {
    ".txt",
    ".pdf",
    ".docx",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".csv",
}


def _attachment_warnings(
    names: list[str], sizes: list[int] | None = None
) -> list[AttachmentWarning]:
    warnings: list[AttachmentWarning] = []
    sizes = sizes or []
    for idx, name in enumerate(names):
        lower = name.lower()
        suffix = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
        if suffix not in SUPPORTED_ATTACHMENT_SUFFIXES:
            warnings.append(
                AttachmentWarning(
                    name=name,
                    reason=f"Unsupported attachment type ({suffix or 'unknown'}); skipped.",
                )
            )
        size = sizes[idx] if idx < len(sizes) else None
        if size is not None and size > MAX_ATTACHMENT_BYTES:
            warnings.append(
                AttachmentWarning(
                    name=name,
                    reason=f"Attachment exceeds {MAX_ATTACHMENT_BYTES} bytes; skipped.",
                )
            )
    return warnings


def run_analyze(
    db: Session,
    *,
    mailbox_profile_id: str,
    message_id: str,
    actor_oid: str,
    user_assertion: str,
    tenant_id: str,
    mailbox_kind: str,
    mailbox_email: str,
    graph_mailbox_id: str | None,
    body: AnalyzeRequest,
) -> SuggestionOut:
    if mailbox_kind == MailboxKind.SHARED.value:
        settings_row = ai_store.get_ai_settings(db, mailbox_profile_id)
        if settings_row is not None and not settings_row.enabled:
            raise AppError(
                code="FORBIDDEN",
                message="AI suggestions are disabled for this shared mailbox.",
                status_code=403,
                retryable=False,
            )

    client = get_inference_client()
    loaded = load_message_for_analyze(
        user_assertion=user_assertion,
        tenant_id=tenant_id,
        message_id=message_id,
        mailbox_kind=mailbox_kind,
        mailbox_email=mailbox_email,
        graph_mailbox_id=graph_mailbox_id,
        fallback_subject=body.subject,
        fallback_body=body.body,
        fallback_sender=body.sender,
        attachment_names=body.attachment_names,
    )
    logger.info(
        "analyze_start mailbox_profile_id=%s message_id=%s",
        mailbox_profile_id,
        message_id,
    )

    warnings = _attachment_warnings(loaded.attachment_names, loaded.attachment_sizes)
    from app.services.thread_split import split_thread_body

    parts = split_thread_body(loaded.body)
    # Retrieve against the latest ask — avoid pulling style matches from quoted history.
    query = f"{loaded.subject}\n{parts.latest_message}\n{loaded.sender}"
    snippets = retrieve_similar(
        db, mailbox_profile_id=mailbox_profile_id, query_text=query, client=client
    )
    learned = lookup_learned_route(
        db,
        mailbox_profile_id=mailbox_profile_id,
        pattern_key=pattern_key_from_sender(loaded.sender),
    )
    behavior_summary = None
    if body.include_draft:
        from app.db.repositories import mailboxes as mailbox_repo
        from app.services.profile_inspect import ensure_cached_summary

        try:
            profile = mailbox_repo.get_profile(db, mailbox_profile_id)
            if profile is not None:
                # Grounded fill only — never a per-draft 14B summary regeneration.
                behavior_summary = ensure_cached_summary(db, profile, allow_llm=False)
        except Exception:
            logger.info(
                "behavior_summary_ensure_skipped mailbox_profile_id=%s",
                mailbox_profile_id,
            )
            try:
                db.rollback()
            except Exception:
                pass
            behavior_summary = None
    signals = client.analyze_fast(
        subject=loaded.subject,
        body=loaded.body,
        sender=loaded.sender,
        mailbox_email=mailbox_email,
        retrieved_snippets=snippets,
        learned_route=learned,
        include_draft=body.include_draft,
        behavior_summary=behavior_summary,
    )

    route_email = signals.route_email
    route_name = signals.route_name
    # Frozen product rule: Contoso never surfaces as a suggested route to the add-in.
    if route_email and "@contoso.com" in route_email.lower():
        route_email, route_name = None, None

    suggestion = Suggestion(
        mailbox_profile_id=mailbox_profile_id,
        message_id=message_id,
        sender=loaded.sender,
        category=signals.category,
        priority=signals.priority,
        confidence=signals.confidence.value,
        suggested_route_email=route_email,
        suggested_route_name=route_name,
        draft=signals.draft,
        why_json=json.dumps(signals.why),
        history_status=signals.history_status.value,
        attachment_warnings_json=json.dumps([w.model_dump() for w in warnings]),
        created_by_oid=actor_oid,
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    route = None
    if suggestion.suggested_route_email:
        route = RouteOut(
            email=suggestion.suggested_route_email,
            display_name=suggestion.suggested_route_name,
        )

    # Forward only when a real route exists (learned edge) — never invented recipients.
    actions: list[str] = []
    if suggestion.draft:
        actions.append("reply")
    if route:
        actions.append("forward")

    return SuggestionOut(
        suggestion_id=suggestion.id,
        mailbox_profile_id=mailbox_profile_id,
        message_id=message_id,
        category=suggestion.category,
        priority=suggestion.priority,
        confidence=Confidence(suggestion.confidence),
        suggested_route=route,
        draft=suggestion.draft,
        why=[WhyItem(**w) for w in json.loads(suggestion.why_json)],
        history_status=signals.history_status,
        attachment_warnings=warnings,
        actions=actions,
    )
