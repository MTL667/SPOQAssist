# SpoqAssist Hub API

FastAPI service on the Mac Studio (Docker Compose).

## Endpoints (Epic 1)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/health` | no | Non-content health |
| GET | `/v1/me` | Bearer | Entra identity stub |
| POST | `/v1/mailbox_profiles/connect` | Bearer | Graph connect (stub/OBO) |
| GET | `/v1/mailbox_profiles/{id}` | Bearer + entitlement | Profile |
| GET | `/v1/mailbox_profiles/{id}/content_stub` | Bearer + entitlement | Content gate test |
| GET | `/v1/ops/health_detail` | no | Non-content ops detail |
| GET/PUT | `/v1/ops/connector_config` | Bearer + ops OID | FR36 non-content config |

## Local

```bash
cd apps/hub-api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=sqlite://
export ENTRA_TENANT_IDS=...
export ENTRA_API_AUDIENCE=api://spoqassist
uvicorn app.main:app --reload --port 8000
```

## Compose

```bash
docker compose -f docker/docker-compose.yml up --build
curl -s http://localhost:8000/health
```

## Tests

From repo root: `apps/hub-api/.venv/bin/pytest`
