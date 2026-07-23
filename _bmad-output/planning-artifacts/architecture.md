---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/prd-validation-report.md'
  - '_bmad-output/planning-artifacts/ux-design-specification.md'
  - '_bmad-output/planning-artifacts/product-brief-SpoqAssist.md'
  - '_bmad-output/brainstorming/brainstorming-session-2026-07-22-0843.md'
  - '_bmad-output/planning-artifacts/ai-act-pellicaan-scope.pdf'
workflowType: 'architecture'
project_name: 'SpoqAssist'
user_name: 'Kevin'
date: '2026-07-22'
lastStep: 8
status: 'complete'
completedAt: '2026-07-22'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
37 FRs in clusters that map to architectural services:
- **Identity & Access (FR1–FR6):** Entra SSO, multi-entity, mailbox entitlements; admin shared-only vs personal owner-only (API-enforced)
- **Mailbox connection & ingestion (FR7–FR11):** M365/Exchange read path incl. attachments; historical sent/forwarded as retrieval corpus; retention aligned to Exchange
- **Analysis & suggestions (FR12–FR17):** classify, route, draft, prioritize + confidence + explainability
- **Shared queue (FR18–FR23):** concurrent delegates; accept/edit/reject/reroute (UX: primarily Outlook; dashboard optional)
- **Personal assist (FR24–FR27):** Outlook add-in; central deploy per Entra entity
- **Feedback & learning (FR28–FR30):** persist labels; routing corrections update shared knowledge without personal leakage
- **Compliance (FR31–FR34):** AI disclosure; processing/access register; suggestion→decision audit
- **Operations (FR35–FR37):** hub health (non-content); connector/auth config; **mandatory confirm before send/forward**

**Non-Functional Requirements:**
- **Performance:** classify/route/priority ≤10s; draft ≤30s (~10 users); queue may async-prep
- **Security:** no external LLM for mailbox content; TLS/(VPN+TLS); personal AI data admin-inaccessible at API; Entra authZ
- **Reliability:** hub down detectable ≤60s; clients show unavailable; no duplicate send/forward after outage; Confirm still required
- **Scale:** pilot ~10 users; growth = capacity planning
- **Integration:** Entra multi-entity; Outlook for Mac add-in; Graph and/or EWS; attachment size/type limits

**UX architectural implications:**
- Primary client = Outlook task pane (Fluent + SPOQ+ tokens); web dashboard secondary/optional
- Confidence-gated UI (hero vs review stack); ConfirmOutboundDialog is the only mutating outbound gate
- WCAG 2.2 AA; keyboard + VoiceOver; calm Analyzing/HubUnavailable states; no offline AI
- Component roadmap implies API contracts for suggestion payload, feedback events, health, confirm-execute

**Scale & Complexity:**
- Primary domain: full-stack (Office add-in + central API/hub + local ML/retrieval)
- Complexity level: medium–high (elevated by multi-Entra, personal/shared isolation, local model ops, compliance)
- Estimated major architectural components: ~8–10 (clients, API gateway/auth, mail connector, ingestion/index, retrieval+graph, inference orchestration, suggestion/feedback store, audit/register, ops health)

### Technical Constraints & Dependencies

- Company-controlled inference only (Mac Studio / internal network); **pinned stack:** see Core Architectural Decisions → Local Model Stack
- Vector DB + knowledge graph in-release; LoRA / autonomy out
- Mail API choice (Graph vs EWS) still open — architecture decision required
- Remote-reachable hub (VPN/Tailscale or equivalent) for WFH users
- GDPR legal basis open — architecture stays HITL; no silent auto-send paths
- UX surface shift vs older PRD emphasis: architect for Outlook-first; dashboard not blocking for core loop

### Cross-Cutting Concerns Identified

1. **Mailbox-profile tenancy** — isolation unit shared vs personal; no cross-profile leakage
2. **Authorization** — Entra entity + mailbox entitlement on every data/AI call
3. **Audit & transparency** — suggestion→decision logs; AI disclosure on outbound
4. **Retention** — indexes/embeddings lifecycle tied to Exchange retention
5. **Idempotent outbound** — Confirm + mail send must be safe under retries/outages
6. **Latency budgets** — pipeline split (fast path vs generation path)
7. **Ops without content** — health/auth management without reading personal mail
8. **Learning loop** — feedback writes must respect shared vs personal visibility rules

## Starter Template Evaluation

### Primary Technology Domain

**Multi-package internal platform** (not a single web starter):
1. Outlook for Mac Office Add-in (TypeScript + React + Fluent)
2. Mac Studio hub API + local inference orchestration (Python)
3. Data: PostgreSQL + pgvector (Docker on Mac Studio)

User preferences: TypeScript/React experience OK; Python allowed for hub; Postgres+pgvector; Docker on Mac Studio; remote access undecided; Entra + M365 + local Qwen confirmed.

### Starter Options Considered

| Option | Role | Verdict |
|--------|------|---------|
| **Yo Office** (`generator-office`) React + TypeScript + Outlook host | Primary client scaffold | **Selected** — Fluent React task pane, Office.js, maintained by Microsoft |
| Microsoft 365 Agents Toolkit (Outlook / unified manifest) | Alternate add-in scaffold | Viable later; Yo Office preferred for classic Outlook task-pane path and Fluent React quickstart alignment |
| FastAPI + LangChain “RAG templates” (OpenAI-centric) | Hub | **Rejected** — fights NFR-S1 (no external LLM for mailbox content); over-coupled to cloud RAG |
| **Lean FastAPI + Docker Compose + `pgvector/pgvector` image** | Hub + DB | **Selected** — minimal, local-Qwen-friendly; Alembic + SQLAlchemy async |
| Full-stack Next.js / T3 | Combined UI+API | **Rejected** — wrong primary surface (Outlook), not Mac Studio hub shape |

### Selected Starter: Dual scaffold (Yo Office + lean FastAPI/Docker)

**Rationale for Selection:**
- Matches UX (Fluent React Outlook pane) and developer familiarity (TS/React)
- Puts ML-adjacent code in Python where local Qwen/reranker tooling is natural
- Single Postgres+pgvector for relational (audit, feedback, config, graph edges) + embeddings
- Docker Compose fits “Mac Studio with Docker”; remote access left as a later decision (Tailscale vs corporate VPN)

**Initialization Commands:**

```bash
# 0) Monorepo root (first implementation story)
mkdir -p SpoqAssist && cd SpoqAssist
# Suggested layout: apps/outlook-addin, apps/hub-api, docker/

# 1) Outlook add-in (React + TypeScript + Outlook)
npm install -g yo generator-office
yo office --projectType react --name "SpoqAssist" --host outlook --ts true
# Move generated project into apps/outlook-addin (or generate inside that folder)

# 2) Hub + Postgres/pgvector (Docker Compose skeleton — create in-repo, not a cloud-RAG clone)
# apps/hub-api: FastAPI (Python 3.12+), Alembic, async SQLAlchemy
# docker/docker-compose.yml services:
#   - api (hub)
#   - db (image: pgvector/pgvector:pg16)
#   - (later) inference sidecar or host-network to local model runtime
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime:**
- Add-in: TypeScript, Node (Office webpack/vite toolchain from Yo Office), React + Fluent UI
- Hub: Python 3.12+, FastAPI, Uvicorn
- DB: PostgreSQL 16 + pgvector extension

**Styling Solution:**
- Fluent UI React themed with SPOQ+ tokens (from UX spec); no Tailwind-as-primary

**Build Tooling:**
- Add-in: Yo Office default bundler/dev server + Office sideload
- Hub: Docker multi-stage image; Compose for local/Studio deploy
- Monorepo: simple folder layout first (optional pnpm/npm workspaces later for add-in only)

**Testing Framework:**
- Add-in: Jest/Vitest as introduced by generator / team standard
- Hub: pytest + httpx AsyncClient; DB tests against Compose pgvector

**Code Organization:**
- `apps/outlook-addin` — task pane UI, Office.js, talks to hub API only
- `apps/hub-api` — authZ, mail connector, analyze/suggest, feedback, audit, health
- `docker/` — Compose for api + postgres/pgvector; inference runtime may be sibling container or host process
- Shared OpenAPI contract: hub is source of truth for suggestion/feedback/confirm DTOs

**Development Experience:**
- Add-in: `npm start` / sideload into Outlook for Mac
- Hub: `docker compose up` for DB+API; hot-reload in API container or local uvicorn against Compose DB
- Remote access to Studio: **deferred decision** (candidates: Tailscale, WireGuard, corporate VPN) — required before WFH pilot

**Note:** Project initialization using these commands should be the first implementation stories (scaffold add-in + scaffold hub/Compose). Do not adopt LangChain/OpenAI RAG boilerplates as the base.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Dual scaffold: Yo Office React/TS add-in + FastAPI hub + Postgres/pgvector (Docker)
- Entra JWT validation on hub; mailbox-profile authorization on every data/AI call
- REST/OpenAPI; sync analyze with 10s/30s budgets; Confirm-outbound gate (FR37)
- Microsoft Graph (delegated/OBO) as mail API path aligned with Entra tokens
- No external LLM for mailbox content; inference on DGX Spark only (NFR-S1)
- Tailscale for DGX Spark ↔ client remote access

**Important Decisions (Shape Architecture):**
- Single Postgres for relational + pgvector embeddings + graph-as-tables
- Alembic migrations; Pydantic v2 validation
- Fluent UI React v9 (~9.7x line); mail-scoped React state; Office.js adapter layer
- Compose: api + db; inference host/sidecar; structured logs + /health
- Light CI (lint/test/image); vertical scale for ~10 users

**Decided (DGX Spark migration — see addendum):**
- Postgres-backed priority queue for pre-compute (no Redis needed)
- Dual-model routing: Qwen3.6-27B classify + Qwen3-72B draft via vLLM
- Embedding upgrade: 4096-dim (Qwen3-Embedding-8B) with full reindex
- Attachment processing pipeline (PDF, DOCX, vision model)
- Action extraction from mail content

**Deferred Decisions (Post-MVP):**
- Optional web dashboard scaffold
- App-level field encryption of bodies
- LoRA, autonomy, follow-up/archive/escalate
- Neo4j or separate graph DB
- Corporate VPN as alternate to Tailscale (not primary)

### Data Architecture

| Decision | Choice | Version / note |
|----------|--------|----------------|
| Primary store | PostgreSQL + pgvector | Image pin e.g. `pgvector/pgvector:0.8.5-pg16` |
| Knowledge graph | Relational edge tables in Postgres | No separate graph DB |
| Migrations | Alembic | With SQLAlchemy async |
| Validation | Pydantic v2 at API + DB constraints | |
| Caching | No Redis in pilot | Postgres + short-lived in-process/TTL if needed |
| Tenancy key | `mailbox_profile` (shared vs personal) | Embeddings/chunks scoped per profile; retention jobs align to Exchange |
| Provided by starter | Partial (Compose/pgvector image choice) | Modeling is custom |

### Authentication & Security

| Decision | Choice |
|----------|--------|
| Client→hub auth | Entra ID JWT (delegated / OBO); hub validates issuer/audience per entity |
| Authorization | Hub policy: entity + mailbox entitlement + role (owner / shared-delegate / admin / ops) |
| Mail credentials | Per-entity app registration; least-privilege Graph scopes; secrets on Studio only |
| Encryption | TLS in transit; volume/disk at rest; no app-level body encryption in pilot |
| API hardening | Auth on non-health routes; health non-content; light per-user/mailbox rate limits |
| Personal isolation | Enforced in API (NFR-S3), not UI-only |

### API & Communication Patterns

| Decision | Choice |
|----------|--------|
| Style | REST + JSON; OpenAPI from FastAPI as contract |
| Core flows | analyze → suggestion; feedback; confirm-outbound; GET /health |
| Errors | Stable envelope: `code`, `message`, `retryable` |
| Analyze mode | Sync with timeouts (≤2s classify; ≤8s draft on DGX Spark); pre-compute worker for background batch |
| Inference | Hub → vLLM on DGX Spark only; add-in never calls model directly |
| Docs | OpenAPI UI in non-prod; version prefix `/v1` |

### Frontend Architecture

| Decision | Choice |
|----------|--------|
| UI kit | `@fluentui/react-components` v9 + SPOQ+ theme tokens |
| State | Local React state + fetch per selected mail; server owns suggestions |
| Office.js | Thin adapter layer separate from UI components |
| Navigation | No router; explicit pane states (analyzing / hero / review / confirm / unavailable) |
| Dashboard | Deferred; reuse tokens/components later |
| A11y | WCAG 2.2 AA per UX spec |

### Infrastructure & Deployment

| Decision | Choice |
|----------|--------|
| Host | **Nvidia DGX Spark** (128 GB, Blackwell, DGX OS/Linux ARM64), Docker Compose (`api`, `db`; vLLM as systemd services) |
| DB image | `pgvector/pgvector` PG16, pin patch tag (e.g. `0.8.5-pg16`) |
| Environments | `dev` + `dgx` via env/secrets; AI path not on public cloud PaaS |
| Remote access | **Tailscale** (DGX Spark ↔ MacBooks) |
| CI/CD | Light pipeline: lint/test + image build; reviewed deploy to DGX Spark |
| Observability | Structured logs (no PII), `/health` + `/health/detail` (queue stats), Prometheus via vLLM |
| Scale | Vertical for ~10 users; no multi-node requirement this release |

### Local Model Stack

> **⚠️ Updated 2026-07-23** — migrated from Mac Studio / Ollama to DGX Spark / vLLM.
> Full details: `architecture-dgx-spark-addendum.md`

| Role | Choice | Notes |
|------|--------|-------|
| Runtime | **vLLM** (≥0.13, CUDA 13.0, systemd services) on DGX Spark | OpenAI-compatible `/v1/chat/completions`; replaces Ollama |
| Classify / triage | **Qwen3.6-27B** (port 8001) | Pre-compute path: <2s/mail; 262K context |
| Draft / deep analysis | **Qwen3-72B** (port 8002) | On-demand: 5-8s; complex NL drafts |
| Embeddings | **Qwen3-Embedding-8B** (port 8003) | 4096-dim dense; MRL truncation if needed |
| Reranker | **Qwen3-Reranker-4B** (port 8003) | Instruction-aware, 100+ languages |
| Vision (lazy-load) | **TBD ~7B VL model** (port 8004) | Only loaded when scan/image attachment present |
| pgvector dimension | **`vector(4096)`** | Upgraded from 1024; existing chunks re-embedded via management command |
| Network | Inference reachable only on DGX Spark/Tailscale; never exposed publicly; add-in never calls vLLM | NFR-S1 |
| Batch strategy | **Hybrid**: pre-compute on mail arrival (27B) + on-demand draft (72B) | Priority queue: user-opened > recent > retry |

**Backward compatibility:** `INFERENCE_MODE=ollama` still supported for fallback/dev. Config-driven: swap `INFERENCE_MODE=vllm` to activate DGX Spark stack.

**Change control:** Changing embedding dim or embedding model requires `python -m app.management.reembed` (full reindex). Changing instruct/reranker models is config-only if API contracts stay stable (OpenAI-compatible format preserved).

### Decision Impact Analysis

**Implementation Sequence:**
1. ~~Repo layout + Compose (db + api skeleton) + Alembic~~ ✅ Done
2. ~~Yo Office Outlook add-in scaffold + Fluent theme tokens~~ ✅ Done
3. ~~Entra app registration(s) + JWT validation + mailbox authZ middleware~~ ✅ Done
4. ~~Graph mail read path (single mailbox E2E)~~ ✅ Done
5. ~~Inference wiring (reranker-first + instruct for draft)~~ ✅ Done
6. ~~Analyze/feedback/confirm-outbound APIs + audit~~ ✅ Done
7. ~~Tailscale + studio deploy + health/runbook~~ ✅ Done
8. **DGX Spark migration** — vLLM dual-model, 4096-dim embeddings, pre-compute worker, attachments, actions (see `epics-dgx-spark-migration.md`)

**Cross-Component Dependencies:**
- Entra JWT choice drives Graph OBO and forbids client-held long-lived mail secrets
- Postgres-only graph means routing “learn” updates are SQL transactions + embedding refresh
- Pre-compute worker + latency NFRs constrain inference placement (same DGX Spark, warm models via vLLM)
- Embedding dim (4096) must match between index_chunks, retrieve_similar, and re-embed job
- Confirm-outbound + idempotency keys couple API, mail send, and audit tables
- Tailscale is prerequisite for WFH clients reaching hub without exposing inference publicly

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 12 areas (naming DB/API/code, structure, JSON/dates/errors, authZ checks, loading/retry, logging, confirm idempotency)

### Naming Patterns

**Database Naming Conventions:**
- Tables/columns: `snake_case`, plural tables (`mailbox_profiles`, `suggestions`, `audit_events`)
- PK: `id` (UUID); FK: `{table_singular}_id` (e.g. `mailbox_profile_id`)
- Indexes: `ix_{table}_{columns}`; unique: `uq_{table}_{columns}`
- pgvector columns: `embedding vector(...)` with explicit dim in migration

**API Naming Conventions:**
- Paths: `/v1/` + plural resources: `/v1/mailbox_profiles/{id}/messages/{message_id}/analyze`
- Path params: `{id}` style in OpenAPI; UUIDs for Spoq ids; Graph ids as opaque strings
- Query params: `snake_case`
- Headers: `Authorization: Bearer`; correlation `X-Request-Id`

**Code Naming Conventions:**
- Python: `snake_case` modules/functions; `PascalCase` Pydantic models
- TypeScript/React: `PascalCase` components/files (`SuggestionHero.tsx`); `camelCase` functions/vars
- Office adapter: `officeMail.ts` only place Office.js is imported

### Structure Patterns

**Project Organization:**
```
apps/outlook-addin/     # Yo Office root
apps/hub-api/           # FastAPI package
  app/
    api/                # routers
    core/               # config, security
    domain/             # models, policies
    services/           # mail, inference, analyze
    db/                 # session, repos
  alembic/
docker/
tests/                  # hub tests (mirrors app/)
```

**File Structure Patterns:**
- Hub tests under repo `tests/` (not inside `app/`)
- Add-in tests co-located `*.test.tsx`
- Env: `.env.example` committed; `.env` never committed; Studio secrets via Docker/env
- Docs: `_bmad-output/` for planning; `docs/` for runbooks later

### Format Patterns

**API Response Formats:**
- Success: return resource/DTO directly (no `{data: ...}` wrapper)
- Error envelope:
  ```json
  {"error": {"code": "HUB_UNAVAILABLE", "message": "...", "retryable": true, "request_id": "..."}}
  ```
- HTTP: 401/403 authZ; 404 missing; 409 conflict (duplicate confirm); 422 validation; 503 hub/inference down
- Dates: ISO-8601 UTC strings (`2026-07-22T09:15:00Z`)
- Booleans: JSON `true`/`false`; null only when field optional

**Data Exchange Formats:**
- JSON body/fields: **snake_case**
- Add-in maps to camelCase at UI boundary only
- Suggestion payload always includes: `confidence` (`high|medium|low`), `actions[]`, optional `draft`, optional `why[]`, `suggestion_id`
- Confirm-outbound requires `suggestion_id` + `idempotency_key`

### Communication Patterns

**Event System Patterns:**
- Feedback types: `accept` | `edit` | `reject` | `reroute` (lowercase)
- Persist before UI shows “thanks”; never treat Accept as send

**State Management Patterns:**
- Pane state machine: `idle | analyzing | ready_hero | ready_review | confirming | unavailable | error`
- Immutable updates; new suggestion replaces previous for selected message
- Clear suggestion on mail selection change

### Process Patterns

**Error Handling Patterns:**
- Hub: map exceptions → error envelope; never leak stack traces to client
- Add-in: MessageBar + one recovery action; HubUnavailable for 503
- Do not show stale Accept after analyze failure

**Loading State Patterns:**
- AnalyzingState only during in-flight analyze; disable Accept while analyzing
- Slow hint after soft budget; cancel/replace request on message switch

**AuthZ / logging / idempotency:**
- Every handler resolves `MailboxContext` first; personal content never returned to admin roles
- Health endpoints: no mailbox payloads
- Structured JSON logs: `level`, `request_id`, `mailbox_profile_id` (ok), **never** subject/body/draft text
- Audit table stores suggestion→decision; separate from debug logs
- `confirm-outbound` is idempotent on `idempotency_key`; duplicate → same result, no second send

### Enforcement Guidelines

**All AI Agents MUST:**
- Follow snake_case API + DB; camelCase only inside React UI layer
- Put Office.js only in the mail adapter module
- Enforce mailbox authZ in hub services, not only in the add-in
- Use the shared error envelope and suggestion DTO fields
- Never call external LLM APIs with mailbox content
- Never send/forward without confirm-outbound success path

**Pattern Enforcement:**
- OpenAPI + Pydantic are source of truth for contracts
- PR checks: lint (ruff/eslint), pytest, typecheck
- Violations fixed in review; pattern changes update this architecture doc

### Pattern Examples

**Good Examples:**
- `POST /v1/mailbox_profiles/{id}/messages/{message_id}/analyze`
- `SuggestionHero.tsx` fetches via `api.analyze(...)` → maps snake_case → view model
- `confirm_outbound(..., idempotency_key=...)` returns 200 twice safely

**Anti-Patterns:**
- `/analyzeEmail` RPC with camelCase body mixed into Python models without aliases
- Logging email body “for debugging”
- Accept button calling Graph send directly from the add-in
- Admin debug endpoint returning personal embeddings

## Project Structure & Boundaries

### Complete Project Directory Structure

```
SpoqAssist/
├── README.md
├── .gitignore
├── .env.example
├── .github/
│   └── workflows/
│       ├── ci-hub.yml
│       └── ci-addin.yml
├── docker/
│   ├── docker-compose.yml          # api + db (pgvector/pg16)
│   ├── Dockerfile.api
│   └── initdb/
│       └── 01_extensions.sql       # CREATE EXTENSION vector;
├── apps/
│   ├── hub-api/
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   └── versions/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/
│   │   │   │   ├── deps.py
│   │   │   │   ├── health.py
│   │   │   │   ├── analyze.py
│   │   │   │   ├── feedback.py
│   │   │   │   ├── confirm.py
│   │   │   │   └── admin_ops.py      # non-content health/config
│   │   │   ├── core/
│   │   │   │   ├── config.py
│   │   │   │   ├── logging.py
│   │   │   │   ├── security.py       # JWT validate
│   │   │   │   └── errors.py
│   │   │   ├── domain/
│   │   │   │   ├── models.py         # SQLAlchemy
│   │   │   │   ├── schemas.py        # Pydantic DTOs
│   │   │   │   ├── enums.py
│   │   │   │   └── policies.py       # mailbox authZ
│   │   │   ├── db/
│   │   │   │   ├── session.py
│   │   │   │   └── repositories/
│   │   │   └── services/
│   │   │       ├── mail_graph.py
│   │   │       ├── inference.py
│   │   │       ├── retrieve.py
│   │   │       ├── analyze.py
│   │   │       ├── learning.py
│   │   │       ├── audit.py
│   │   │       └── retention.py
│   │   └── README.md
│   └── outlook-addin/              # Yo Office output
│       ├── package.json
│       ├── manifest*.xml
│       ├── src/
│       │   ├── taskpane/
│       │   │   ├── index.tsx
│       │   │   ├── App.tsx
│       │   │   ├── theme/
│       │   │   │   └── spoqTokens.ts
│       │   │   ├── state/
│       │   │   │   └── paneState.ts
│       │   │   ├── api/
│       │   │   │   ├── client.ts
│       │   │   │   └── mappers.ts    # snake → camel
│       │   │   ├── office/
│       │   │   │   └── officeMail.ts
│       │   │   └── components/
│       │   │       ├── SuggestionHero.tsx
│       │   │       ├── SuggestionReviewStack.tsx
│       │   │       ├── ConfirmOutboundDialog.tsx
│       │   │       ├── AnalyzingState.tsx
│       │   │       ├── HubUnavailable.tsx
│       │   │       ├── WhyExplanation.tsx
│       │   │       ├── RoutePicker.tsx
│       │   │       └── FeedbackControls.tsx
│       │   └── commands/             # if generated
│       └── README.md
├── tests/                          # hub-api tests
│   ├── conftest.py
│   ├── api/
│   ├── services/
│   ├── domain/
│   └── integration/
├── docs/
│   ├── runbooks/
│   │   └── hub-unavailable.md
│   └── processing-access-register.md
└── _bmad-output/                   # planning artifacts (existing)
```

### Architectural Boundaries

**API Boundaries:**
- External (add-in → hub): `/v1/*` over Tailscale/TLS; Bearer Entra JWT
- Public-ish: `GET /health` (no mailbox content)
- Mutating mail: only `POST .../confirm-outbound` (FR37); never analyze
- Admin/ops: health + connector config only; no personal AI data routes

**Component Boundaries:**
- UI components never import Office.js (only `officeMail.ts`)
- UI never holds Graph refresh tokens; only hub access token for API
- Dashboard deferred — no `apps/web` until explicitly added

**Service Boundaries:**
- `mail_graph` — Graph read/send/forward only
- `inference` — local model runtime client only
- `retrieve` — pgvector + routing edges
- `analyze` — orchestrates retrieve + inference → suggestion DTO
- `learning` — feedback → graph/embedding updates (shared vs personal scoped)
- `policies` — single place for mailbox authZ decisions

**Data Boundaries:**
- All durable state in Postgres (profiles, suggestions, feedback, audit, edges, embeddings)
- Isolation unit = `mailbox_profile_id`; queries always filtered by policy
- Retention job deletes/purges AI rows with Exchange-aligned rules

### Requirements to Structure Mapping

| FR cluster | Location |
|------------|----------|
| FR1–FR6 Identity/Access | `core/security.py`, `domain/policies.py`, `api/deps.py` |
| FR7–FR11 Mail ingestion | `services/mail_graph.py`, `services/retrieve.py`, `services/retention.py` |
| FR12–FR17 Analyze/suggest | `services/analyze.py`, `services/inference.py`, `api/analyze.py` |
| FR18–FR23 Shared queue actions | Same analyze/feedback/confirm APIs; Outlook UI components |
| FR24–FR27 Personal assist | `apps/outlook-addin` + same hub APIs |
| FR28–FR30 Feedback/learning | `api/feedback.py`, `services/learning.py` |
| FR31–FR34 Compliance | `services/audit.py`, `docs/processing-access-register.md`, confirm disclosure copy in add-in |
| FR35–FR37 Ops + HITL | `api/health.py`, `api/admin_ops.py`, `api/confirm.py`, `ConfirmOutboundDialog.tsx` |

**Cross-Cutting Concerns:**
- AuthZ → `domain/policies.py` + `api/deps.py`
- Errors → `core/errors.py` + add-in MessageBar mapping
- Audit → `services/audit.py` + `audit_events` table
- Correlation → `X-Request-Id` middleware + client

### Integration Points

**Internal Communication:** add-in `api/client.ts` → hub routers → services → db/inference/mail  
**External Integrations:** Entra ID · Microsoft Graph · local Qwen/reranker runtime · Tailscale  
**Data Flow:** Select mail → Office adapter → analyze → suggestion UI → accept/edit/reject/reroute → confirm-outbound → Graph send/forward + audit + learning

### File Organization Patterns

**Configuration:** `.env.example`, `docker/docker-compose.yml`, `apps/hub-api/app/core/config.py`, add-in manifest  
**Source:** `apps/hub-api/app/*`, `apps/outlook-addin/src/taskpane/*`  
**Tests:** hub `tests/`; add-in co-located `*.test.tsx`  
**Assets:** add-in static assets per Yo Office; no public marketing site in-repo for pilot

### Development Workflow Integration

- Dev: Compose `db` + local/uvicorn `hub-api`; `npm start` add-in sideload
- Studio: Compose `api`+`db`; inference host/sidecar; Tailscale; reviewed image deploy
- CI: `ci-hub.yml` (ruff/pytest), `ci-addin.yml` (eslint/typecheck/test)

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility:**
Yo Office React/TS + Fluent v9, FastAPI hub, Postgres/pgvector, Entra JWT + Graph OBO, Tailscale, local-only inference — no contradictory choices. Cloud RAG starters correctly rejected vs NFR-S1.

**Pattern Consistency:**
snake_case API/DB vs camelCase UI mapping, confirm idempotency, mailbox authZ in hub, Office.js adapter isolation — aligned with decisions and UX HITL rules.

**Structure Alignment:**
`apps/hub-api`, `apps/outlook-addin`, `docker/`, `tests/` match dual-scaffold and FR→module mapping; dashboard correctly absent for Phase 1.

### Requirements Coverage Validation

**Epic/Feature Coverage:**
No epics yet; FR clusters FR1–FR37 mapped to concrete modules/APIs/UI components.

**Functional Requirements Coverage:**
Identity, mail/Graph, analyze/suggest, feedback/learning, compliance/audit, ops/health, and FR37 confirm-outbound all have architectural homes. Shared-queue UX is Outlook-first (dashboard deferred) — still covered by same APIs.

**Non-Functional Requirements Coverage:**
- Perf: sync analyze + 10s/30s budgets; warm local models assumed
- Security: Entra, API authZ, TLS/Tailscale, no external LLM, personal isolation
- Reliability: `/health`, HubUnavailable, idempotent confirm
- Scale: vertical ~10 users
- Compliance: disclosure at confirm, audit trail, register doc path; GDPR legal basis remains parallel legal track (HITL retained)

### Implementation Readiness Validation

**Decision Completeness:**
Critical path documented; versions pinned where chosen (e.g. pgvector PG16 tag example, Fluent v9 line). Inference runtime product name not pinned (host/sidecar only).

**Structure Completeness:**
Full tree with key files; boundaries and integration points specified.

**Pattern Completeness:**
Naming, errors, state machine, logging (no PII), idempotency, enforcement rules with examples/anti-patterns.

### Gap Analysis Results

**Critical Gaps:** None.

**Important Gaps (non-blocking):**
1. ~~Pin local inference runtime + model artifacts~~ **Resolved** — Ollama host + Qwen3 14B Instruct + Qwen3-Reranker-0.6B + Qwen3-Embedding-0.6B @ 1024-d (see Local Model Stack)
2. ~~Pin embedding model + vector dimensions~~ **Resolved** — as above
3. Document concrete Graph permission scopes per Entra entity in `docs/` during first mail story
4. GDPR legal basis still open (legal) — architecture correctly stays HITL

**Nice-to-Have:**
- Optional `apps/web` dashboard later (explicitly out of this release)
- Redis/async workers if batch precompute needed
- Richer APM beyond structured logs

### Validation Issues Addressed

No critical issues requiring redesign. Inference/embedding pins closed 2026-07-22. Remaining: Graph scopes doc + GDPR legal track.

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION  
**Confidence Level:** high

**Key Strengths:**
- Clear dual-client/hub split with Outlook-first UX
- Strong personal/shared isolation story at API boundary
- HITL confirm + idempotency designed in
- Agent-conflict patterns (naming, errors, Office adapter) explicit

**Areas for Future Enhancement:**
- Optional web dashboard if shared-mailbox batch demand requires it after pilot
- Deepen retention job design with Exchange policy owners
- Evaluate MLX later if Ollama latency misses NFR-P1/P2 on Studio

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and boundaries
- Refer to this document for all architectural questions

**First Implementation Priority:**
1. Repo layout + `docker/docker-compose.yml` (pgvector) + FastAPI skeleton + Alembic  
2. `yo office --projectType react --name "SpoqAssist" --host outlook --ts true` → `apps/outlook-addin`  
3. Entra JWT validation + `/health` + first `analyze` stub E2E over Tailscale
