from __future__ import annotations

from tests.conftest import OPS_OID, OTHER_OID, TENANT_A


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_ops_health_detail_non_content(app_client):
    response = app_client.get("/v1/ops/health_detail")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "configured_tenant_ids" in body
    assert "subject" not in body
    assert "body" not in body


def test_ops_connector_config_requires_ops_principal(app_client, make_token):
    other = make_token(oid=OTHER_OID)
    denied = app_client.get(
        f"/v1/ops/connector_config/{TENANT_A}",
        headers=_auth(other),
    )
    assert denied.status_code == 403

    ops = make_token(oid=OPS_OID)
    ok = app_client.put(
        "/v1/ops/connector_config",
        headers=_auth(ops),
        json={
            "tenant_id": TENANT_A,
            "graph_scopes": "https://graph.microsoft.com/Mail.Read",
            "notes": "pilot scopes",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["graph_scopes"].endswith("Mail.Read")

    got = app_client.get(
        f"/v1/ops/connector_config/{TENANT_A}",
        headers=_auth(ops),
    )
    assert got.status_code == 200
    assert got.json()["notes"] == "pilot scopes"


def test_ops_rejects_secret_smuggling(app_client, make_token):
    ops = make_token(oid=OPS_OID)
    response = app_client.put(
        "/v1/ops/connector_config",
        headers=_auth(ops),
        json={
            "tenant_id": TENANT_A,
            "graph_scopes": "Mail.Read",
            "notes": "contains client secret value",
        },
    )
    assert response.status_code == 422
