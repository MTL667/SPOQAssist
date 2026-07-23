"""Tests for pre-compute worker, priority queue, and state machine."""

from __future__ import annotations

import pytest

from app.domain.enums import PrecomputeStatus
from app.domain.models import Base, ExtractedAction, PrecomputeJob
from app.services.precompute import (
    PRIORITY_NORMAL,
    PRIORITY_USER_OPENED,
    boost_priority,
    enqueue_precompute,
    fetch_next_batch,
    get_precompute_status,
    get_queue_stats,
)


PROFILE_ID = "test-profile-1"


@pytest.fixture
def db_session(monkeypatch):
    """In-memory SQLite session for pre-compute tests."""
    monkeypatch.setenv("INFERENCE_MODE", "stub")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    from app.core.config import get_settings
    from app.db.session import get_engine, reset_engine
    from app.domain.models import MailboxProfile
    from app.services.inference import set_inference_client

    get_settings.cache_clear()
    reset_engine()
    set_inference_client(None)

    from sqlalchemy.orm import sessionmaker

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()

    # Create a test mailbox profile (FK target)
    profile = MailboxProfile(
        id=PROFILE_ID,
        tenant_id="test-tenant",
        email="test@spoq.be",
        kind="shared",
        owner_oid="test-oid",
        connection_status="connected",
    )
    db.add(profile)
    db.commit()

    yield db
    db.close()
    reset_engine()
    get_settings.cache_clear()
    set_inference_client(None)


class TestEnqueue:
    def test_enqueue_creates_pending_job(self, db_session):
        job = enqueue_precompute(
            db_session,
            mailbox_profile_id=PROFILE_ID,
            message_id="msg-1",
        )
        assert job is not None
        assert job.status == PrecomputeStatus.PENDING
        assert job.priority == PRIORITY_NORMAL

    def test_enqueue_idempotent(self, db_session):
        job1 = enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        job2 = enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        assert job1.id == job2.id

    def test_enqueue_different_messages_creates_separate_jobs(self, db_session):
        job1 = enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        job2 = enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m2")
        assert job1.id != job2.id


class TestPriorityQueue:
    def test_user_opened_boosts_priority(self, db_session):
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1", priority=0)
        boost_priority(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        job = db_session.query(PrecomputeJob).filter_by(message_id="m1").first()
        assert job.priority == PRIORITY_USER_OPENED

    def test_fetch_batch_ordered_by_priority(self, db_session):
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="low", priority=0)
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="high", priority=10)
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="mid", priority=5)

        batch = fetch_next_batch(db_session, batch_size=3)
        assert len(batch) == 3
        assert batch[0].message_id == "high"
        assert batch[1].message_id == "mid"
        assert batch[2].message_id == "low"

    def test_fetch_batch_marks_processing(self, db_session):
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        batch = fetch_next_batch(db_session, batch_size=1)
        assert batch[0].status == PrecomputeStatus.PROCESSING

    def test_fetch_batch_skips_processing_jobs(self, db_session):
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        fetch_next_batch(db_session, batch_size=1)  # marks m1 as processing
        batch2 = fetch_next_batch(db_session, batch_size=1)
        assert len(batch2) == 0


class TestParallelExecution:
    def test_run_worker_processes_batch_concurrently(self, db_session, monkeypatch):
        """Verify the worker processes multiple jobs in parallel (ThreadPoolExecutor)."""
        import time
        from unittest.mock import patch, MagicMock

        # Enqueue 4 jobs
        for i in range(4):
            enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id=f"par-{i}")

        # Track how many process_job calls overlap in time
        call_times = []

        original_process = None

        def mock_process_job(db, job):
            call_times.append(time.time())
            time.sleep(0.05)  # Simulate brief work
            job.status = PrecomputeStatus.DONE
            db.commit()
            return True

        with patch("app.services.precompute.process_job", side_effect=mock_process_job):
            from app.services.precompute import run_worker

            run_worker(batch_size=4, poll_interval=0.1, max_iterations=1)

        # All 4 should have been called
        assert len(call_times) == 4
        # With ThreadPoolExecutor, all 4 should start within 0.02s of each other
        # (sequential would take 4 * 0.05 = 0.2s between first and last)
        time_spread = max(call_times) - min(call_times)
        assert time_spread < 0.1, f"Jobs not parallel: spread={time_spread:.3f}s"


class TestStateMachine:
    def test_get_status_returns_none_for_unknown(self, db_session):
        status = get_precompute_status(db_session, mailbox_profile_id=PROFILE_ID, message_id="unknown")
        assert status is None

    def test_get_status_returns_pending(self, db_session):
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        status = get_precompute_status(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        assert status == PrecomputeStatus.PENDING

    def test_queue_stats(self, db_session):
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m1")
        enqueue_precompute(db_session, mailbox_profile_id=PROFILE_ID, message_id="m2")
        fetch_next_batch(db_session, batch_size=1)  # marks one as processing

        stats = get_queue_stats(db_session)
        assert stats["pending"] == 1
        assert stats["processing"] == 1
        assert stats["done"] == 0
        assert stats["failed"] == 0
