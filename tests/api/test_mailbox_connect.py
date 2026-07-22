from __future__ import annotations

from tests.conftest import OWNER_OID


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_connect_personal_and_shared(app_client, make_token):
    token = make_token(oid=OWNER_OID)

    personal = app_client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": "me@contoso.com", "kind": "personal"},
    )
    assert personal.status_code == 200
    assert personal.json()["mailbox_profile"]["kind"] == "personal"
    assert personal.json()["mailbox_profile"]["connection_status"] == "connected"
    assert personal.json()["mailbox_profile"]["graph_mailbox_id"].startswith("personal:")
    assert personal.json()["role"] == "owner"

    shared = app_client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": "info@contoso.com", "kind": "shared"},
    )
    assert shared.status_code == 200
    assert shared.json()["mailbox_profile"]["kind"] == "shared"
    assert shared.json()["mailbox_profile"]["connection_status"] == "connected"
    assert shared.json()["mailbox_profile"]["graph_mailbox_id"].startswith("shared:")


def test_connect_consent_required_clear_error(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    response = app_client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": "x@consent-required.example", "kind": "personal"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_connect_bad_scopes_clear_error(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    response = app_client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": "x@bad-scopes.example", "kind": "shared"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "BAD_SCOPES"


def test_connect_failure_clear_error(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    response = app_client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": "x@connector-fail.example", "kind": "personal"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "CONNECTOR_FAILURE"
    assert response.json()["error"]["retryable"] is True
