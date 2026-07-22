from __future__ import annotations

from tests.conftest import OWNER_OID


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _connect(client, token: str, email: str, kind: str) -> str:
    response = client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": email, "kind": kind},
    )
    assert response.status_code == 200, response.text
    return response.json()["mailbox_profile"]["id"]


def test_inspect_stable_profile_and_empty_summary(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "inspect@contoso.com", "personal")
    again = _connect(app_client, token, "inspect@contoso.com", "personal")
    assert again == profile_id

    response = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}/inspect",
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == profile_id
    assert body["email"] == "inspect@contoso.com"
    assert body["history_chunk_count"] == 0
    assert body["indexed_message_count"] == 0
    assert body["routes"] == []
    assert body["behavior_summary"]["status"] == "empty"
    assert "no style profile" in (body["behavior_summary"]["text"] or "").lower()
    # Never leak chunk bodies
    assert "chunk_text" not in body
    blob = str(body).lower()
    assert "embedding" not in blob


def test_inspect_includes_routes_and_stub_summary(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "office@contoso.com", "shared")

    # Seed a learned route via feedback teach on shared mailbox.
    analyze = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-route-1",
            "include_draft": False,
            "subject": "Invoice pack",
            "body": "Please handle",
            "sender": "vendor@finance.partner",
        },
    )
    assert analyze.status_code == 200, analyze.text
    suggestion_id = analyze.json()["suggestion_id"]
    feedback = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/feedback",
        headers=_auth(token),
        json={
            "suggestion_id": suggestion_id,
            "outcome": "reroute",
            "corrected_route_email": "finance@contoso.com",
            "corrected_route_name": "Finance",
            "teach": True,
        },
    )
    assert feedback.status_code == 200, feedback.text

    # Index one Sent chunk for non-empty summary path.
    indexed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index",
        headers=_auth(token),
        json={
            "items": [
                {
                    "message_id": "sent-1",
                    "text": "Subject: thanks\nHi, I will forward this to finance shortly.",
                }
            ]
        },
    )
    assert indexed.status_code == 200, indexed.text

    response = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}/inspect",
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == profile_id
    assert body["history_chunk_count"] >= 1
    assert body["indexed_message_count"] >= 1
    assert any(r["route_email"] == "finance@contoso.com" for r in body["routes"])
    assert body["behavior_summary"]["status"] == "ok"
    assert body["behavior_summary"]["text"]
    assert "finance@contoso.com" in body["behavior_summary"]["text"]


def test_inspect_without_summary_still_returns_metadata(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "meta@contoso.com", "personal")
    response = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}/inspect?include_summary=false",
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == profile_id
    assert body["behavior_summary"]["status"] == "skipped"
    assert body["behavior_summary"]["text"] is None


def test_inspect_summary_model_down_uses_grounded_fallback(
    app_client, make_token, monkeypatch
):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "failsum@contoso.com", "personal")
    indexed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index",
        headers=_auth(token),
        json={
            "items": [
                {
                    "message_id": "sent-fail",
                    "text": "Subject: hi\nHallo, bedankt — ik volg dit graag op.\nGroeten",
                }
            ]
        },
    )
    assert indexed.status_code == 200, indexed.text

    from app.services.inference import StubInferenceClient, set_inference_client

    class Boom(StubInferenceClient):
        def summarize_mailbox_behavior(self, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("model down")

    set_inference_client(Boom())
    try:
        response = app_client.get(
            f"/v1/mailbox_profiles/{profile_id}/inspect",
            headers=_auth(token),
        )
    finally:
        set_inference_client(None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == profile_id
    assert body["history_chunk_count"] >= 1
    assert body["behavior_summary"]["status"] == "ok"
    assert body["behavior_summary"]["error"] is None
    text = body["behavior_summary"]["text"] or ""
    assert "failsum@contoso.com" in text
    assert "mostly Dutch" in text
    assert "unavailable" not in text.lower()
