from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
AUDIENCE = "api://spoqassist"
OWNER_OID = "user-oid-1"
ADMIN_OID = "admin-oid-1"
OTHER_OID = "other-oid-1"
OPS_OID = "ops-oid-1"


@pytest.fixture
def rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def fake_jwks_client(rsa_keys):
    _private_key, public_key = rsa_keys

    class _SigningKey:
        def __init__(self, key: Any) -> None:
            self.key = key

    class FakeJwkClient:
        def get_signing_key_from_jwt(self, _token: str) -> _SigningKey:
            return _SigningKey(public_key)

    return FakeJwkClient()


@pytest.fixture
def make_token(rsa_keys):
    private_key, _public_key = rsa_keys
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    def _make(
        *,
        tenant_id: str = TENANT_A,
        audience: str = AUDIENCE,
        exp_offset: int = 3600,
        oid: str = OWNER_OID,
        extra: dict[str, Any] | None = None,
        corrupt_signature: bool = False,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "oid": oid,
            "sub": oid,
            "tid": tenant_id,
            "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            "aud": audience,
            "iat": now,
            "exp": now + exp_offset,
            "preferred_username": "kevin@example.com",
            "name": "Kevin",
        }
        if extra:
            payload.update(extra)
        token = jwt.encode(payload, pem, algorithm="RS256")
        if corrupt_signature:
            parts = token.split(".")
            # Deterministic invalid signature (not a single-char flip, which can rarely verify).
            parts[2] = ("A" * max(len(parts[2]), 16))[: len(parts[2]) or 16]
            return ".".join(parts)
        return token

    return _make


@pytest.fixture
def app_client(monkeypatch, fake_jwks_client):
    monkeypatch.setenv("ENTRA_TENANT_IDS", f"{TENANT_A},{TENANT_B}")
    monkeypatch.setenv("ENTRA_API_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("GRAPH_MODE", "stub")
    monkeypatch.setenv("OPS_PRINCIPAL_OIDS", OPS_OID)
    monkeypatch.delenv("ENTRA_ENTITIES", raising=False)

    monkeypatch.setenv("INFERENCE_MODE", "stub")

    from app.core.config import get_settings
    from app.core.security import clear_jwks_cache
    from app.db.session import reset_engine
    from app.services.inference import set_inference_client
    from app.services.mail_graph import set_mail_graph_client

    get_settings.cache_clear()
    clear_jwks_cache()
    reset_engine()
    set_mail_graph_client(None)
    set_inference_client(None)
    monkeypatch.setattr("app.core.security.get_jwks_client", lambda _tid: fake_jwks_client)

    from app.main import app

    with TestClient(app) as client:
        yield client

    set_mail_graph_client(None)
    set_inference_client(None)
    reset_engine()
    get_settings.cache_clear()
    clear_jwks_cache()
