"""History sync exposes mid-run phase + message counts for poll-based UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

OWNER_OID = "owner-progress-oid"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _connect(client, token: str, email: str, kind: str = "personal") -> str:
    resp = client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": email, "kind": kind},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["mailbox_profile"]["id"]


def _force_syncing(profile_id: str, *, fetched: int = 0, target: int = 3000, started_at=None) -> None:
    from app.db.session import get_engine
    from app.domain.models import MailboxProfile
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        profile = db.get(MailboxProfile, profile_id)
        assert profile is not None
        profile.history_status = "syncing"
        profile.history_sync_phase = "fetching"
        profile.history_messages_fetched = fetched
        profile.history_messages_target = target
        profile.history_sync_started_at = started_at or datetime.now(timezone.utc)
        profile.history_sync_error = None
        db.commit()


def test_index_sync_returns_progress_fields(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "progress@contoso.com")
    synced = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 10, "wait": True},
    )
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert body["history_status"] == "ready"
    assert body["history_sync_phase"] == "ready"
    assert body["history_messages_fetched"] >= 1
    assert body["history_messages_target"] >= body["history_messages_fetched"]
    assert (body.get("total_chunks") or 0) >= 1

    profile = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}",
        headers=_auth(token),
    )
    assert profile.status_code == 200
    snap = profile.json()
    assert snap["history_sync_phase"] == "ready"
    assert snap["history_messages_fetched"] >= 1
    assert snap["history_chunk_count"] >= 1

    inspect = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}/inspect?include_summary=false",
        headers=_auth(token),
    )
    assert inspect.status_code == 200
    data = inspect.json()
    assert data["history_sync_phase"] == "ready"
    assert data["history_messages_fetched"] >= 1
    assert data["history_chunk_count"] >= 1


def test_failed_sync_sets_failed_phase(app_client, make_token, monkeypatch):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "fail-progress@contoso.com")

    from app.services import history_sync

    class BoomClient:
        def list_sent_messages(self, **_kwargs):
            raise RuntimeError("graph_down")

    monkeypatch.setattr(history_sync, "get_mail_graph_client", lambda: BoomClient())

    synced = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 5, "wait": True},
    )
    assert synced.status_code == 503
    profile = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}",
        headers=_auth(token),
    )
    assert profile.status_code == 200
    body = profile.json()
    assert body["history_status"] == "failed"
    assert body["history_sync_phase"] == "failed"
    assert body["history_sync_error"]


def test_get_heals_orphaned_syncing_with_chunks(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "orphan-chunks@contoso.com")
    synced = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 10, "wait": True},
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["history_status"] == "ready"

    _force_syncing(profile_id, fetched=0, target=3000)

    healed = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}",
        headers=_auth(token),
    )
    assert healed.status_code == 200
    body = healed.json()
    assert body["history_status"] == "ready"
    assert body["history_sync_phase"] == "ready"
    assert (body.get("history_chunk_count") or 0) >= 1
    assert body["history_messages_fetched"] >= 1


def test_get_heals_stale_syncing_without_chunks(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "stale-empty@contoso.com")
    stale_started = datetime.now(timezone.utc) - timedelta(hours=4)
    _force_syncing(profile_id, fetched=0, target=3000, started_at=stale_started)

    healed = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}",
        headers=_auth(token),
    )
    assert healed.status_code == 200
    body = healed.json()
    assert body["history_status"] == "failed"
    assert body["history_sync_phase"] == "failed"
    assert body["history_sync_error"]


def test_get_does_not_heal_live_inflight_non_stale_sync(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "live-inflight@contoso.com")
    from app.services import history_sync

    with history_sync._inflight_lock:
        history_sync._inflight_profiles.add(profile_id)
    try:
        _force_syncing(
            profile_id,
            fetched=0,
            target=3000,
            started_at=datetime.now(timezone.utc),
        )
        mid = app_client.get(
            f"/v1/mailbox_profiles/{profile_id}",
            headers=_auth(token),
        )
        assert mid.status_code == 200
        body = mid.json()
        assert body["history_status"] == "syncing"
        assert body["history_sync_phase"] == "fetching"
    finally:
        with history_sync._inflight_lock:
            history_sync._inflight_profiles.discard(profile_id)


def test_fetch_progress_rises_before_crawl_finishes(app_client, make_token, monkeypatch):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "mid-progress@contoso.com")

    from app.services import history_sync
    from app.services.mail_graph import GraphMessage

    gate = {"release": False}

    class PagingClient:
        def list_sent_messages(self, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress is not None:
                on_progress(0)
                on_progress(2)
            while not gate["release"]:
                import time

                time.sleep(0.01)
            return [
                GraphMessage(
                    message_id="mid-1",
                    subject="Re: one",
                    body="Thanks for the update. I will follow up shortly with details.",
                    sender="mid-progress@contoso.com",
                ),
                GraphMessage(
                    message_id="mid-2",
                    subject="Re: two",
                    body="Noted on our side. Happy to schedule a call next week if needed.",
                    sender="mid-progress@contoso.com",
                ),
            ]

    monkeypatch.setattr(history_sync, "get_mail_graph_client", lambda: PagingClient())

    started = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 10, "wait": False},
    )
    assert started.status_code == 200
    assert started.json()["started"] is True

    import time

    seen_progress = False
    for _ in range(50):
        snap = app_client.get(
            f"/v1/mailbox_profiles/{profile_id}",
            headers=_auth(token),
        ).json()
        if snap["history_status"] == "syncing" and int(snap["history_messages_fetched"] or 0) >= 2:
            seen_progress = True
            break
        time.sleep(0.02)
    assert seen_progress, "expected fetched >= 2 while sync still running"

    gate["release"] = True
    for _ in range(50):
        snap = app_client.get(
            f"/v1/mailbox_profiles/{profile_id}",
            headers=_auth(token),
        ).json()
        if snap["history_status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)
    assert snap["history_status"] == "ready"


def test_refresh_with_chunks_does_not_reset_fetched_to_zero(app_client, make_token, monkeypatch):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "refresh-keep@contoso.com")
    synced = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 10, "wait": True},
    )
    assert synced.status_code == 200
    ready_fetched = int(synced.json()["history_messages_fetched"] or 0)
    assert ready_fetched >= 1

    from app.services import history_sync

    gate = {"release": False}

    class SlowClient:
        def list_sent_messages(self, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress is not None:
                on_progress(0)
            while not gate["release"]:
                import time

                time.sleep(0.01)
            if on_progress is not None:
                on_progress(ready_fetched)
            return []

    monkeypatch.setattr(history_sync, "get_mail_graph_client", lambda: SlowClient())

    started = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 10, "wait": False},
    )
    assert started.status_code == 200
    assert started.json()["started"] is True
    # Immediately after kickoff (and during hang), fetched must not look empty.
    mid = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}",
        headers=_auth(token),
    )
    assert mid.status_code == 200
    mid_body = mid.json()
    assert mid_body["history_status"] == "syncing"
    assert mid_body["history_messages_fetched"] >= 1
    assert (mid_body.get("history_chunk_count") or 0) >= 1

    gate["release"] = True
    # Allow background worker to finish.
    import time

    for _ in range(50):
        snap = app_client.get(
            f"/v1/mailbox_profiles/{profile_id}",
            headers=_auth(token),
        ).json()
        if snap["history_status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)
    assert snap["history_status"] == "ready"
