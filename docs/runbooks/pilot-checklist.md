# Pilot checklist — first real run (Mac Studio + Outlook for Mac)

Use this after Epics 1–4 + code-review patches. Goal: one personal mailbox and one shared mailbox end-to-end with HITL confirm.

## 0. Preconditions

- [ ] Mac Studio reachable from pilot MacBooks (Tailscale recommended)
- [ ] Docker Desktop running on Studio
- [ ] Entra app registration(s) ready per entity (see `office-sso-setup.md` + `graph-scopes.md`)
- [ ] Legal/GDPR track aware that HITL confirm remains mandatory

## 1. Hub on Mac Studio

```bash
cd /path/to/SpoqAssist
cp .env.example .env
# Edit .env — at minimum:
#   ENTRA_TENANT_IDS=<tenant-guid>
#   ENTRA_API_AUDIENCE=api://<host>/<client-id>   # must match manifest Resource
#   ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET         # for GRAPH_MODE=obo
#   GRAPH_MODE=obo                                # or stub for dry-run
#   INFERENCE_MODE=stub                           # or ollama when models pulled
#   OPS_PRINCIPAL_OIDS=<your-oid>
docker compose -f docker/docker-compose.yml up --build -d
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/v1/ops/health_detail
```

- [ ] `/health` → `status: ok`
- [ ] No secrets committed (`.env` stays local)

### Optional: real local models

```bash
# On Studio host (Ollama)
ollama pull qwen3-embedding:0.6b   # or your pinned tag → 1024-d
ollama pull qwen3-reranker:0.6b
ollama pull qwen3:14b
```

Set in `.env`: `INFERENCE_MODE=ollama` and matching `OLLAMA_*_MODEL` tags, then recreate api container.

## 2. Entra + manifest

- [ ] Replace `REPLACE_ENTRA_CLIENT_ID` in `apps/outlook-addin/manifest.xml`
- [ ] Application ID URI / Resource matches `ENTRA_API_AUDIENCE`
- [ ] Scope `access_as_user` exposed; Office client pre-authorized
- [ ] Graph admin consent for `Mail.Read`, `Mail.Read.Shared`, `Mail.Send` (see `graph-scopes.md`)

## 3. Add-in (sideload first)

```bash
cd apps/outlook-addin
export HUB_BASE_URL=http://<studio-tailscale-ip>:8000   # or https reverse proxy
npx office-addin-dev-certs install   # once
npm install
npm run dev-server
```

- [ ] Sideload `manifest.xml` (see `sideload-fallback.md`)
- [ ] Pane shows hub online (not HubUnavailable)
- [ ] Office SSO works, **or** temporary: `localStorage.spoq_access_token = "…"`

## 4. Smoke tests (HITL)

| # | Scenario | Expect |
|---|----------|--------|
| A | Personal message → Analyze | Suggestion or honest limited-history; no fake Accept if error |
| B | Accept → Confirm dialog | Disclosure visible; Cancel sends nothing |
| C | Confirm send/forward | One Graph action; retry same idempotency key does not double-send |
| D | Shared mailbox (Office shared context) | Connect as `shared`; delegate can analyze |
| E | Admin on personal AI | 403 on content/analyze |
| F | Admin shared AI settings | GET/PUT `/v1/admin/.../ai_settings` works |
| G | Stop hub | Pane → HubUnavailable + Retry; no stale Accept |

## 5. Central deploy (after sideload OK)

- [ ] Follow `central-add-in-deployment.md` per Entra entity
- [ ] Assign pilot users/groups only
- [ ] Record non-secret notes via ops connector config if useful

## 6. Ops day-2

- [ ] Bookmark `/health` + `/v1/ops/health_detail` (no mail bodies)
- [ ] Keep `docs/processing-access-register.md` updated when processing changes
- [ ] Retention: configure shared profiles under `/v1/admin/.../retention` when Exchange alignment is known

## Out of scope for first pilot

- Web dashboard queue
- Autonomy / auto-send
- LoRA fine-tunes
- Perfect pgvector SQL type (JSON 1024-d embeddings OK for pilot; migrate later)
