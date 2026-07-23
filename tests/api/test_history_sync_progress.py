"""History sync exposes mid-run phase + message counts for poll-based UI."""

from __future__ import annotations

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
