from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.enums import Confidence, HistoryStatus, MailboxKind
from app.domain.models import Suggestion
from app.domain.schemas import (
    AnalyzeRequest,
    AttachmentWarning,
    RouteOut,
    SuggestionOut,
    WhyItem,
)
from app.services.inference import AnalyzeSignals, get_inference_client
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
PRECOMPUTE_MAX_AGE = timedelta(hours=2)


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


def _ms_since(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


def get_fresh_precomputed_suggestion(
    db: Session,
    *,
    mailbox_profile_id: str,
    message_id: str,
) -> Suggestion | None:
    """Latest precompute classify row for this message, if still fresh."""
    row = db.execute(
        select(Suggestion)
        .where(
            Suggestion.mailbox_profile_id == mailbox_profile_id,
            Suggestion.message_id == message_id,
            Suggestion.created_by_oid == "system:precompute",
        )
        .order_by(Suggestion.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    created = row.created_at
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if created > now or now - created > PRECOMPUTE_MAX_AGE:
        return None
    return row


def _signals_from_suggestion(row: Suggestion) -> AnalyzeSignals:
    try:
        why = json.loads(row.why_json or "[]")
        if not isinstance(why, list):
            why = []
        why = [item for item in why if isinstance(item, dict)]
    except json.JSONDecodeError:
        why = []
    try:
        hist = HistoryStatus(row.history_status or HistoryStatus.NONE.value)
    except ValueError:
        hist = HistoryStatus.NONE
    try:
        conf = Confidence(row.confidence or Confidence.MEDIUM.value)
    except ValueError:
        conf = Confidence.MEDIUM
    return AnalyzeSignals(
        category=row.category or "fyi",
        priority=row.priority or "normal",
        confidence=conf,
        route_email=row.suggested_route_email,
        route_name=row.suggested_route_name,
        why=why,
        draft=None,
        history_status=hist,
    )


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

    total_start = time.perf_counter()
    timings: dict[str, int] = {
        "graph_ms": 0,
        "retrieve_ms": 0,
        "classify_ms": 0,
        "draft_ms": 0,
        "total_ms": 0,
    }

    client = get_inference_client()
    t0 = time.perf_counter()
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
    timings["graph_ms"] = _ms_since(t0)
    logger.info(
        "analyze_start mailbox_profile_id=%s message_id=%s",
        mailbox_profile_id,
        message_id,
    )

    warnings = _attachment_warnings(loaded.attachment_names, loaded.attachment_sizes)
    from app.services.thread_split import split_thread_body

    parts = split_thread_body(loaded.body)
    thread_tail = (parts.thread_context or "")[:800]
    query = (
        f"{loaded.subject}\n{parts.latest_message}\n{loaded.sender}\n{thread_tail}"
    )

    t0 = time.perf_counter()
    snippets = retrieve_similar(
        db, mailbox_profile_id=mailbox_profile_id, query_text=query, client=client
    )
    timings["retrieve_ms"] = _ms_since(t0)

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

    cached = get_fresh_precomputed_suggestion(
        db,
        mailbox_profile_id=mailbox_profile_id,
        message_id=message_id,
    )
    precompute_status = "miss"
    classification: AnalyzeSignals | None = None
    if cached is not None:
        precompute_status = "hit"
        classification = _signals_from_suggestion(cached)
        classification.why = list(classification.why) + [
            {
                "code": "precompute_cache",
                "text": "Classification reused from fresh precompute cache.",
            }
        ]

    t0 = time.perf_counter()
    if classification is not None:
        signals = classification
        # Refresh history readiness from live retrieval — precompute may have run
        # before Sent index existed.
        if len(snippets) >= 2:
            signals.history_status = HistoryStatus.SUFFICIENT
        elif snippets:
            signals.history_status = HistoryStatus.LIMITED
        timings["classify_ms"] = 0
    else:
        signals = client.analyze_fast(
            subject=loaded.subject,
            body=loaded.body,
            sender=loaded.sender,
            mailbox_email=mailbox_email,
            retrieved_snippets=snippets,
            learned_route=learned,
            include_draft=False,
            behavior_summary=behavior_summary,
        )
        timings["classify_ms"] = _ms_since(t0)

    try:
        from app.services.precompute import boost_priority

        boost_priority(
            db,
            mailbox_profile_id=mailbox_profile_id,
            message_id=message_id,
        )
    except Exception:
        logger.info("precompute_boost_skipped mailbox_profile_id=%s", mailbox_profile_id)

    if body.include_draft:
        t0 = time.perf_counter()
        signals = client.analyze_fast(
            subject=loaded.subject,
            body=loaded.body,
            sender=loaded.sender,
            mailbox_email=mailbox_email,
            retrieved_snippets=snippets,
            learned_route=learned,
            include_draft=True,
            behavior_summary=behavior_summary,
            classification=signals,
        )
        timings["draft_ms"] = _ms_since(t0)

    route_email = signals.route_email if isinstance(signals.route_email, str) else None
    route_name = signals.route_name if isinstance(signals.route_name, str) else None
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

    actions: list[str] = []
    if suggestion.draft:
        actions.append("reply")
    if route:
        actions.append("forward")

    timings["total_ms"] = _ms_since(total_start)
    logger.info(
        "analyze_done mailbox_profile_id=%s total_ms=%s classify_ms=%s draft_ms=%s precompute=%s",
        mailbox_profile_id,
        timings["total_ms"],
        timings["classify_ms"],
        timings["draft_ms"],
        precompute_status,
    )

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
        precompute_status=precompute_status,
        timings=timings,
    )
