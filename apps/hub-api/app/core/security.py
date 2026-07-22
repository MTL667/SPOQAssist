"""Entra ID JWT validation (issuer + audience per configured entity)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import EntraEntityConfig, Settings, get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

# JWKS client cache per tenant (PyJWKClient handles key rotation internally).
_jwks_clients: dict[str, PyJWKClient] = {}


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    tenant_id: str
    audience: str
    upn: str | None
    name: str | None


def _issuer_candidates(tenant_id: str) -> set[str]:
    tid = tenant_id.lower()
    return {
        f"https://login.microsoftonline.com/{tid}/v2.0",
        f"https://sts.windows.net/{tid}/",
        f"https://login.microsoftonline.com/{tid}/",
    }


def _jwks_uri(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"


def get_jwks_client(tenant_id: str) -> PyJWKClient:
    key = tenant_id.lower()
    client = _jwks_clients.get(key)
    if client is None:
        client = PyJWKClient(_jwks_uri(tenant_id), cache_keys=True, lifespan=3600)
        _jwks_clients[key] = client
    return client


def clear_jwks_cache() -> None:
    """Test helper — reset cached JWKS clients."""
    _jwks_clients.clear()


def _match_entity(
    unverified: dict[str, Any], entities: list[EntraEntityConfig]
) -> EntraEntityConfig | None:
    tid = str(unverified.get("tid") or "").lower()
    iss = str(unverified.get("iss") or "").rstrip("/").lower()
    for entity in entities:
        allowed_iss = {i.rstrip("/").lower() for i in _issuer_candidates(entity.tenant_id)}
        if tid and tid == entity.tenant_id.lower():
            return entity
        if iss in allowed_iss or any(iss.startswith(a) for a in allowed_iss):
            return entity
    return None


def validate_access_token(
    token: str,
    *,
    settings: Settings | None = None,
    jwks_client: PyJWKClient | None = None,
) -> AuthenticatedPrincipal:
    """Validate a Bearer access token against configured Entra entities.

    Never log the raw token.
    """
    cfg = settings or get_settings()
    if not cfg.entra_entities:
        logger.error("auth_misconfigured: no Entra entities configured")
        raise AppError(
            code="AUTH_MISCONFIGURED",
            message="Authentication is not configured on this hub.",
            status_code=503,
            retryable=True,
        )

    try:
        unverified = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except jwt.PyJWTError:
        logger.info("auth_rejected reason=malformed_token")
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        ) from None

    entity = _match_entity(unverified, cfg.entra_entities)
    if entity is None:
        logger.info("auth_rejected reason=unknown_entity")
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        )

    client = jwks_client or get_jwks_client(entity.tenant_id)
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=entity.audience,
            issuer=list(_issuer_candidates(entity.tenant_id)),
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        logger.info("auth_rejected reason=expired")
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        ) from None
    except jwt.InvalidAudienceError:
        logger.info("auth_rejected reason=wrong_audience")
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        ) from None
    except jwt.InvalidIssuerError:
        logger.info("auth_rejected reason=wrong_issuer")
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        ) from None
    except jwt.PyJWTError as exc:
        # Signature / JWKS / other JWT failures — never include token material.
        logger.info("auth_rejected reason=token_validation_failed err_type=%s", type(exc).__name__)
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        ) from None

    subject = str(claims.get("oid") or claims.get("sub") or "")
    if not subject:
        logger.info("auth_rejected reason=missing_subject")
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        )

    upn = claims.get("preferred_username") or claims.get("upn")
    return AuthenticatedPrincipal(
        subject=subject,
        tenant_id=str(claims.get("tid") or entity.tenant_id),
        audience=entity.audience,
        upn=str(upn) if upn else None,
        name=str(claims["name"]) if claims.get("name") else None,
    )
