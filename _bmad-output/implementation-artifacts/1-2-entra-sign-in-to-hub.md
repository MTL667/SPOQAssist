---
story_key: 1-2-entra-sign-in-to-hub
epic: 1
story: 2
status: review
---

# Story 1.2: Entra sign-in to hub

## Status

review

## Story

As a user,
I want to authenticate with Microsoft Entra ID across configured entities,
So that only company identities can call SpoqAssist APIs.

## Acceptance Criteria

**Given** a valid Entra access token for a configured entity  
**When** I call a protected hub endpoint with `Authorization: Bearer`  
**Then** the hub accepts the request (FR1, FR2, NFR-S4, NFR-I1)

**Given** an expired, forged, or wrong-audience token  
**When** I call a protected hub endpoint  
**Then** the hub returns 401 with the standard error envelope  
**And** secrets and raw tokens are never written to logs

## Tasks / Subtasks

- [x] Config: multi-entity tenant IDs + API audience(s)
- [x] `errors.py` envelope + FastAPI handlers + request_id
- [x] `security.py` JWKS fetch/cache + JWT validate
- [x] `deps.py` Bearer dependency → principal
- [x] `GET /v1/me` protected stub
- [x] `.env.example` + Dockerfile deps (`PyJWT[crypto]`)
- [x] Pytest: valid / expired / wrong aud / forged / missing → envelope; health open

## Dev Agent Record

### Completion Notes

- Multi-entity via `ENTRA_TENANT_IDS` + `ENTRA_API_AUDIENCE`, or `ENTRA_ENTITIES` JSON
- JWKS from `login.microsoftonline.com/{tenant}/discovery/v2.0/keys`; RS256; iss v1/v2 candidates
- Error envelope: `{"error":{"code","message","retryable","request_id"}}`; `X-Request-Id` response header
- Auth failures log only `reason=` codes — never raw tokens
- `pytest`: 9 passed

### File List

- `apps/hub-api/app/core/config.py`
- `apps/hub-api/app/core/security.py`
- `apps/hub-api/app/core/errors.py`
- `apps/hub-api/app/core/logging.py`
- `apps/hub-api/app/api/deps.py`
- `apps/hub-api/app/api/me.py`
- `apps/hub-api/app/main.py`
- `apps/hub-api/pyproject.toml`
- `docker/Dockerfile.api`
- `.env.example`
- `pytest.ini`
- `tests/conftest.py`
- `tests/api/test_auth_me.py`
- `README.md`
