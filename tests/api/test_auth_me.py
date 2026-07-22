from __future__ import annotations

import logging

from tests.conftest import TENANT_A, TENANT_B


def test_health_remains_unauthenticated(app_client):
    response = app_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "error" not in response.json()


def test_me_accepts_valid_token_entity_a(app_client, make_token):
    token = make_token(tenant_id=TENANT_A)
    response = app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "user-oid-1"
    assert body["tenant_id"] == TENANT_A
    assert body["upn"] == "kevin@example.com"
    assert "X-Request-Id" in response.headers


def test_me_accepts_valid_token_entity_b(app_client, make_token):
    token = make_token(tenant_id=TENANT_B, oid="user-oid-b")
    response = app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == TENANT_B
    assert response.json()["subject"] == "user-oid-b"


def test_me_rejects_missing_bearer(app_client):
    response = app_client.get("/v1/me")
    assert response.status_code == 401
    err = response.json()["error"]
    assert err["code"] == "UNAUTHENTICATED"
    assert err["retryable"] is False
    assert "request_id" in err


def test_me_rejects_expired_token(app_client, make_token):
    token = make_token(exp_offset=-10)
    response = app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_rejects_wrong_audience(app_client, make_token):
    token = make_token(audience="api://wrong-app")
    response = app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_rejects_forged_signature(app_client, make_token):
    token = make_token(corrupt_signature=True)
    response = app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_rejects_unknown_tenant(app_client, make_token):
    token = make_token(tenant_id="99999999-9999-9999-9999-999999999999")
    response = app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_logs_never_contain_raw_token(app_client, make_token, caplog):
    token = make_token(audience="api://wrong-app")
    with caplog.at_level(logging.INFO):
        app_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in joined
    assert "Bearer " not in joined
