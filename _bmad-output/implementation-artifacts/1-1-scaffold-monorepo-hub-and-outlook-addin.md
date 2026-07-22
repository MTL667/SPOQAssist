---
story_key: 1-1-scaffold-monorepo-hub-and-outlook-addin
epic: 1
story: 1
status: review
---

# Story 1.1: Scaffold monorepo hub and Outlook add-in

## Status

review

## Story

As a developer,
I want the dual scaffold (Docker Compose pgvector + FastAPI skeleton + Outlook React/TS add-in) in place,
So that later stories have a runnable baseline on Mac Studio and Mac clients.

## Acceptance Criteria

From `epics.md` Story 1.1 — Compose `db`+`api`; `GET /health` unauthenticated; add-in under `apps/outlook-addin`; `.env.example`; no mailbox content logged.

## Tasks / Subtasks

- [x] Create monorepo layout (`apps/hub-api`, `apps/outlook-addin`, `docker/`)
- [x] Compose: pgvector PG16 + API Dockerfile
- [x] FastAPI `GET /health` (no auth, no mailbox payload)
- [x] Outlook add-in React + Fluent shell + manifest
- [x] `.env.example` + `.gitignore` + README
- [x] Verify `docker compose up` — api + healthy db; `GET /health` 200; pgvector extension present
- [x] Verify local `uvicorn` `/health` returns 200
- [x] `npm install` + `npm run build` for outlook-addin

## Dev Agent Record

### Completion Notes

- Compose verified: `docker-api-1` + `docker-db-1` (healthy); `/health` → `{"status":"ok","service":"spoqassist-hub-api"}`; `vector` extension installed
- Add-in: manual React/Fluent scaffold (Yo Office CLI not installed); `npm run build` used to validate compile
- Sideload in Outlook for Mac is manual next step for the user (dev-server + manifest)

### File List

- `docker/docker-compose.yml`, `docker/Dockerfile.api`, `docker/initdb/01_extensions.sql`
- `apps/hub-api/**`
- `apps/outlook-addin/**`
- `.env.example`, `.gitignore`, `README.md`
