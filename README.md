# SpoqAssist

Internal company AI email assistant — Outlook for Mac add-in + Mac Studio hub (local Qwen via Ollama).

## Status

**Epics 1–4 done** (incl. code-review patches). Ready for pilot wiring (Entra + optional Ollama).

## Quick start

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build

# Tests
cd apps/hub-api && pip install -e ".[dev]" && cd ../.. && pytest

# Add-in
cd apps/outlook-addin
export HUB_BASE_URL=http://localhost:8000
npm install && npm run dev-server
```

**First real pilot:** follow [`docs/runbooks/pilot-checklist.md`](docs/runbooks/pilot-checklist.md).

Auth: Office SSO ([`docs/runbooks/office-sso-setup.md`](docs/runbooks/office-sso-setup.md)). Sideload fallback:

```js
localStorage.setItem("spoq_access_token", "<entra access token aud=ENTRA_API_AUDIENCE>")
```

Mailbox profile auto-connects on first analyze (personal, or shared when Outlook shared context is detected).

## Key APIs

| Path | Purpose |
|------|---------|
| `POST /v1/mailbox_profiles/connect` | Graph connect |
| `POST …/messages/{id}/analyze` | Classify/route/draft/confidence |
| `POST …/index` | History embeddings (1024-d) |
| `POST …/feedback` | Accept/edit/reject/reroute + audit |
| `POST …/confirm-outbound` | HITL send/forward (idempotent) |
| `GET/PUT /v1/admin/…/ai_settings` | Shared-only admin config |
| `GET /v1/ops/health_detail` | Non-content ops health |

## Docs

- [`docs/runbooks/pilot-checklist.md`](docs/runbooks/pilot-checklist.md) — **start here for go-live**
- [`docs/processing-access-register.md`](docs/processing-access-register.md) — FR32/FR33
- [`docs/graph-scopes.md`](docs/graph-scopes.md)
- [`docs/runbooks/`](docs/runbooks/) — deploy, sideload, SSO, hub unavailable

## Inference

- Default `INFERENCE_MODE=stub` (CI / dry-run)
- Studio: `INFERENCE_MODE=ollama` + Qwen3 Embedding/Reranker/Instruct pins
