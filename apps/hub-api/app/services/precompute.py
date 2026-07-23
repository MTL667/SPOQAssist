"""Pre-compute worker — background classify, embed, extract actions for incoming mail.

Runs as a separate process/thread. Processes the priority queue:
  1. User-opened mails (priority=10) — boosted by API on-open
  2. Recent mails (priority=0) — from push notification or poll
  3. Retry failed (priority=-1) — exponential backoff

Usage:
    python -m app.services.precompute [--concurrency 4] [--poll-interval 2]
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.domain.enums import PrecomputeStatus
from app.domain.models import (
    ExtractedAction,
    MailboxProfile,
    PrecomputeJob,
    Suggestion,
)
from app.services.actions import extract_actions
from app.services.inference import get_embedding_dim, get_inference_client
from app.services.retrieve import retrieve_similar

logger = logging.getLogger(__name__)

# Priority levels
PRIORITY_USER_OPENED = 10
PRIORITY_NORMAL = 0
PRIORITY_RETRY = -1

MAX_RETRIES = 3


def enqueue_precompute(
    db: Session,
    *,
    mailbox_profile_id: str,
    message_id: str,
    priority: int = PRIORITY_NORMAL,
) -> PrecomputeJob | None:
    """Add a message to the pre-compute queue. Idempotent — skips if already queued/done."""
    existing = db.execute(
        select(PrecomputeJob).where(
            PrecomputeJob.mailbox_profile_id == mailbox_profile_id,
            PrecomputeJob.message_id == message_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Boost priority if user opened and it's still pending/processing
        if priority > existing.priority and existing.status in (
            PrecomputeStatus.PENDING,
            PrecomputeStatus.PROCESSING,
        ):
            existing.priority = priority
            db.commit()
            db.refresh(existing)
        return existing

    job = PrecomputeJob(
        mailbox_profile_id=mailbox_profile_id,
        message_id=message_id,
        status=PrecomputeStatus.PENDING,
        priority=priority,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def boost_priority(
    db: Session,
    *,
    mailbox_profile_id: str,
    message_id: str,
) -> None:
    """Boost a job's priority when user opens the mail (on-demand path)."""
    enqueue_precompute(
        db,
        mailbox_profile_id=mailbox_profile_id,
        message_id=message_id,
        priority=PRIORITY_USER_OPENED,
    )


def get_precompute_status(
    db: Session,
    *,
    mailbox_profile_id: str,
    message_id: str,
) -> PrecomputeStatus | None:
    """Check pre-compute status for a message. Returns None if not queued."""
    job = db.execute(
        select(PrecomputeJob).where(
            PrecomputeJob.mailbox_profile_id == mailbox_profile_id,
            PrecomputeJob.message_id == message_id,
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    return PrecomputeStatus(job.status)


def fetch_next_batch(db: Session, *, batch_size: int = 4) -> list[PrecomputeJob]:
    """Fetch the next batch of jobs atomically using SELECT FOR UPDATE SKIP LOCKED."""
    stmt = (
        select(PrecomputeJob)
        .where(PrecomputeJob.status == PrecomputeStatus.PENDING)
        .order_by(PrecomputeJob.priority.desc(), PrecomputeJob.created_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    jobs = list(db.execute(stmt).scalars().all())
    for job in jobs:
        job.status = PrecomputeStatus.PROCESSING
    if jobs:
        db.commit()
    return jobs


def process_job(
    db: Session,
    job: PrecomputeJob,
) -> bool:
    """Process a single pre-compute job: embed, classify, extract actions.

    Returns True on success, False on failure.
    """
    try:
        client = get_inference_client()

        # Load the mail content (from Graph or cached)
        from app.services.mail_read import load_message_for_analyze

        profile = db.get(MailboxProfile, job.mailbox_profile_id)
        if profile is None:
            _mark_failed(db, job, "Mailbox profile not found")
            return False

        # Try to load the message
        try:
            loaded = load_message_for_analyze(
                user_assertion="",  # Background — no user token
                tenant_id=profile.tenant_id,
                message_id=job.message_id,
                mailbox_kind=profile.kind,
                mailbox_email=profile.email,
                graph_mailbox_id=profile.graph_mailbox_id,
                fallback_subject=None,
                fallback_body=None,
                fallback_sender=None,
                attachment_names=[],
            )
        except Exception:
            _mark_failed(db, job, "Could not load message content")
            return False

        # 1. Embed the mail body
        from app.services.thread_split import split_thread_body

        parts = split_thread_body(loaded.body)
        query_text = f"{loaded.subject}\n{parts.latest_message}\n{loaded.sender}"

        # 2. Retrieve similar chunks for context
        snippets = retrieve_similar(
            db,
            mailbox_profile_id=job.mailbox_profile_id,
            query_text=query_text,
            client=client,
        )

        # 3. Classify (using the analyze_fast path which already does classify)
        from app.services.learning import pattern_key_from_sender
        from app.services.retrieve import lookup_learned_route

        learned = lookup_learned_route(
            db,
            mailbox_profile_id=job.mailbox_profile_id,
            pattern_key=pattern_key_from_sender(loaded.sender),
        )

        # Get behavior summary if available
        behavior_summary = None
        if profile.behavior_summary_text:
            behavior_summary = profile.behavior_summary_text

        signals = client.analyze_fast(
            subject=loaded.subject,
            body=loaded.body,
            sender=loaded.sender,
            mailbox_email=profile.email,
            retrieved_snippets=snippets,
            learned_route=learned,
            include_draft=False,  # Pre-compute only classifies; draft is on-demand
            behavior_summary=behavior_summary,
        )

        # 4. Extract actions
        actions = extract_actions(
            subject=loaded.subject,
            body=loaded.body,
        )

        # 5. Store suggestion
        suggestion = Suggestion(
            mailbox_profile_id=job.mailbox_profile_id,
            message_id=job.message_id,
            sender=loaded.sender,
            category=signals.category,
            priority=signals.priority,
            confidence=signals.confidence.value,
            suggested_route_email=signals.route_email,
            suggested_route_name=signals.route_name,
            draft=None,  # Draft generated on-demand only
            why_json=json.dumps(signals.why),
            history_status=signals.history_status.value,
            attachment_warnings_json="[]",
            created_by_oid="system:precompute",
        )
        db.add(suggestion)
        db.flush()

        # 6. Store extracted actions
        for action in actions:
            db.add(ExtractedAction(
                suggestion_id=suggestion.id,
                mailbox_profile_id=job.mailbox_profile_id,
                message_id=job.message_id,
                action_type=action.action_type,
                description=action.description,
                due_date=action.due_date,
            ))

        # 7. Mark job complete
        job.status = PrecomputeStatus.DONE
        job.suggestion_id = suggestion.id
        job.error = None
        db.commit()

        logger.info(
            "precompute_done job_id=%s message_id=%s category=%s actions=%d",
            job.id,
            job.message_id,
            signals.category,
            len(actions),
        )
        return True

    except Exception as exc:
        logger.info(
            "precompute_error job_id=%s err=%s",
            job.id,
            type(exc).__name__,
        )
        try:
            db.rollback()
        except Exception:
            pass
        # After rollback, expire all to avoid stale ORM state
        db.expire_all()
        # Re-fetch the job to get a clean instance
        fresh_job = db.get(PrecomputeJob, job.id)
        if fresh_job is not None:
            _mark_failed(db, fresh_job, str(exc)[:500])
        return False


def _mark_failed(db: Session, job: PrecomputeJob, error: str) -> None:
    """Mark a job as failed with retry logic and progressive backoff."""
    job.retry_count += 1
    job.error = error
    if job.retry_count >= MAX_RETRIES:
        job.status = PrecomputeStatus.FAILED
    else:
        # Reset to pending for retry with progressively lower priority
        job.status = PrecomputeStatus.PENDING
        job.priority = PRIORITY_RETRY - job.retry_count  # -2, -3 on subsequent retries
    try:
        db.commit()
    except Exception:
        logger.warning("mark_failed_commit_error job_id=%s", job.id)
        try:
            db.rollback()
        except Exception:
            pass


def get_queue_stats(db: Session) -> dict:
    """Get queue depth and status counts for monitoring."""
    from sqlalchemy import func

    stmt = select(
        PrecomputeJob.status, func.count()
    ).group_by(PrecomputeJob.status)
    results = db.execute(stmt).all()
    stats = {status: 0 for status in PrecomputeStatus}
    for status, count in results:
        stats[status] = count
    return {
        "pending": stats.get(PrecomputeStatus.PENDING, 0),
        "processing": stats.get(PrecomputeStatus.PROCESSING, 0),
        "done": stats.get(PrecomputeStatus.DONE, 0),
        "failed": stats.get(PrecomputeStatus.FAILED, 0),
    }


def run_worker(
    *,
    batch_size: int = 4,
    poll_interval: float = 2.0,
    max_iterations: int | None = None,
) -> None:
    """Main worker loop — fetch and process jobs from the priority queue.

    Args:
        batch_size: Number of jobs to process concurrently.
        poll_interval: Seconds between queue polls when idle.
        max_iterations: Stop after N iterations (None = run forever). For testing.
    """
    from app.db.session import get_engine, init_db

    init_db()
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    logger.info("precompute_worker_start batch_size=%d poll_interval=%.1f", batch_size, poll_interval)

    def _process_one_job(job_id: str) -> bool:
        """Process a single job in its own session (thread-safe)."""
        with SessionLocal() as job_db:
            job = job_db.get(PrecomputeJob, job_id)
            if job is not None and job.status == PrecomputeStatus.PROCESSING:
                return process_job(job_db, job)
        return False

    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        with SessionLocal() as db:
            jobs = fetch_next_batch(db, batch_size=batch_size)

            if not jobs:
                time.sleep(poll_interval)
                continue

            # Extract IDs while session is still open
            job_ids = [j.id for j in jobs]

        # Process batch in parallel — each job gets its own session
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {executor.submit(_process_one_job, jid): jid for jid in job_ids}
            for future in as_completed(futures):
                jid = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    logger.error("parallel_job_failed job_id=%s err=%s", jid, type(exc).__name__)

        # Brief pause between batches
        time.sleep(0.1)

    logger.info("precompute_worker_stop iterations=%d", iterations)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Pre-compute worker for SpoqAssist")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    run_worker(batch_size=args.batch_size, poll_interval=args.poll_interval)
