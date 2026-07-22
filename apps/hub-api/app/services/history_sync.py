"""Index mailbox Sent Items into local embeddings for grounded drafts.

Lifecycle: bootstrap once (≤300), then incremental refresh on Outlook open.
Analyze must never block on Graph crawls.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import ai_store, mailboxes as mailbox_repo
from app.db.session import get_engine
from app.domain.enums import HistoryProfileStatus, MailboxKind
from app.domain.models import MailboxProfile
from app.services.inference import get_inference_client, plain_text_for_embed
from app.services.mail_graph import get_mail_graph_client

logger = logging.getLogger(__name__)

BOOTSTRAP_MAX_MESSAGES = 300
STALE_SYNCING_AFTER = timedelta(minutes=30)

_inflight_lock = threading.Lock()
_inflight_profiles: set[str] = set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def profile_history_snapshot(db: Session, mailbox_profile_id: str) -> dict:
    profile = mailbox_repo.get_profile(db, mailbox_profile_id)
    if profile is None:
        return {
            "history_status": HistoryProfileStatus.NOT_STARTED.value,
            "last_history_sync_at": None,
            "history_sync_error": None,
            "total_chunks": 0,
        }
    return {
        "history_status": getattr(profile, "history_status", None)
        or HistoryProfileStatus.NOT_STARTED.value,
        "last_history_sync_at": profile.last_history_sync_at.isoformat()
        if getattr(profile, "last_history_sync_at", None)
        else None,
        "history_sync_error": getattr(profile, "history_sync_error", None),
        "total_chunks": ai_store.count_chunks(db, mailbox_profile_id),
    }


def _mark_syncing(db: Session, profile: MailboxProfile) -> None:
    profile.history_status = HistoryProfileStatus.SYNCING.value
    profile.history_sync_error = None
    profile.history_sync_started_at = _utcnow()
    db.commit()


def _mark_ready(db: Session, profile: MailboxProfile) -> None:
    profile.history_status = HistoryProfileStatus.READY.value
    profile.history_sync_error = None
    profile.last_history_sync_at = _utcnow()
    profile.history_sync_started_at = None
    db.commit()


def _mark_failed(db: Session, profile: MailboxProfile, message: str) -> None:
    profile.history_status = HistoryProfileStatus.FAILED.value
    profile.history_sync_error = (message or "History sync failed")[:512]
    profile.history_sync_started_at = None
    db.commit()


def _is_stale_syncing(profile: MailboxProfile) -> bool:
    if (profile.history_status or "") != HistoryProfileStatus.SYNCING.value:
        return False
    started = getattr(profile, "history_sync_started_at", None)
    if started is None:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return _utcnow() - started > STALE_SYNCING_AFTER


def sync_sent_history(
    db: Session,
    *,
    mailbox_profile_id: str,
    user_assertion: str,
    tenant_id: str,
    mailbox_kind: str,
    mailbox_email: str,
    graph_mailbox_id: str | None,
    max_messages: int = BOOTSTRAP_MAX_MESSAGES,
) -> int:
    """Pull Sent Items via Graph (or stub) and embed new messages only."""
    max_messages = max(1, min(int(max_messages), BOOTSTRAP_MAX_MESSAGES))
    profile = mailbox_repo.get_profile(db, mailbox_profile_id)
    if profile is None:
        raise AppError(
            code="NOT_FOUND",
            message="Mailbox profile not found.",
            status_code=404,
            retryable=False,
        )

    _mark_syncing(db, profile)
    try:
        existing = ai_store.indexed_source_ids(db, mailbox_profile_id)
        client = get_mail_graph_client()
        messages = client.list_sent_messages(
            user_assertion=user_assertion,
            tenant_id=tenant_id,
            mailbox_kind=MailboxKind(mailbox_kind),
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
            max_messages=max_messages,
        )
        items: list[dict[str, str]] = []
        for msg in messages:
            if msg.message_id in existing:
                continue
            text = plain_text_for_embed(f"{msg.subject}\n{msg.body}")
            if len(text) < 20:
                continue
            items.append({"message_id": msg.message_id, "text": text})

        count = 0
        if items:
            inference = get_inference_client()
            count = ai_store.index_chunks(
                db,
                mailbox_profile_id=mailbox_profile_id,
                items=items,
                embed_fn=inference.embed,
            )
        db.refresh(profile)
        _mark_ready(db, profile)
        try:
            # Fast grounded refresh only — never block sync on a 14B summary call.
            from app.services.profile_inspect import ensure_cached_summary

            ensure_cached_summary(db, profile, allow_llm=False)
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            logger.info(
                "behavior_summary_refresh_after_sync_skipped mailbox_profile_id=%s",
                mailbox_profile_id,
            )
        logger.info(
            "history_sync_done mailbox_profile_id=%s indexed=%s mode=%s",
            mailbox_profile_id,
            count,
            get_settings().graph_mode,
        )
        return count
    except AppError as exc:
        db.refresh(profile)
        _mark_failed(db, profile, exc.message)
        raise
    except Exception as exc:
        db.refresh(profile)
        _mark_failed(db, profile, type(exc).__name__)
        logger.info(
            "history_sync_failed mailbox_profile_id=%s err_type=%s",
            mailbox_profile_id,
            type(exc).__name__,
        )
        raise AppError(
            code="HISTORY_SYNC_FAILED",
            message="Could not refresh mailbox history profile.",
            status_code=503,
            retryable=True,
        ) from None


def request_history_sync(
    db: Session,
    *,
    mailbox_profile_id: str,
    user_assertion: str,
    tenant_id: str,
    mailbox_kind: str,
    mailbox_email: str,
    graph_mailbox_id: str | None,
    max_messages: int = BOOTSTRAP_MAX_MESSAGES,
    wait: bool = True,
) -> tuple[int, bool]:
    """
    Start or run an incremental history sync.

    Returns (indexed_count, started).
    When wait=False, starts a background thread and returns (0, True/False).
    """
    profile = mailbox_repo.get_profile(db, mailbox_profile_id)
    if profile is None:
        raise AppError(
            code="NOT_FOUND",
            message="Mailbox profile not found.",
            status_code=404,
            retryable=False,
        )

    status = getattr(profile, "history_status", None) or HistoryProfileStatus.NOT_STARTED.value
    with _inflight_lock:
        if mailbox_profile_id in _inflight_profiles:
            return 0, False
        if status == HistoryProfileStatus.SYNCING.value and not _is_stale_syncing(profile):
            return 0, False
        _inflight_profiles.add(mailbox_profile_id)

    if wait:
        try:
            count = sync_sent_history(
                db,
                mailbox_profile_id=mailbox_profile_id,
                user_assertion=user_assertion,
                tenant_id=tenant_id,
                mailbox_kind=mailbox_kind,
                mailbox_email=mailbox_email,
                graph_mailbox_id=graph_mailbox_id,
                max_messages=max_messages,
            )
            return count, True
        finally:
            with _inflight_lock:
                _inflight_profiles.discard(mailbox_profile_id)

    # Non-blocking: mark syncing then run in a daemon thread with its own session.
    _mark_syncing(db, profile)

    def _worker() -> None:
        SessionLocal = _session_factory()
        with SessionLocal() as worker_db:
            try:
                sync_sent_history(
                    worker_db,
                    mailbox_profile_id=mailbox_profile_id,
                    user_assertion=user_assertion,
                    tenant_id=tenant_id,
                    mailbox_kind=mailbox_kind,
                    mailbox_email=mailbox_email,
                    graph_mailbox_id=graph_mailbox_id,
                    max_messages=max_messages,
                )
            except Exception:
                # Status already marked failed inside sync_sent_history when possible.
                logger.info(
                    "history_sync_bg_failed mailbox_profile_id=%s",
                    mailbox_profile_id,
                )
            finally:
                with _inflight_lock:
                    _inflight_profiles.discard(mailbox_profile_id)

    threading.Thread(target=_worker, name=f"history-sync-{mailbox_profile_id[:8]}", daemon=True).start()
    return 0, True
