---
title: 'Mailbox history profile lifecycle (bootstrap once, refresh on open)'
type: 'feature'
created: '2026-07-22'
status: 'done'
baseline_commit: 'd4fd5589a6bfb514b2809d8bebc528beb91e1bfb'
context:
  - '{project-root}/_bmad-output/planning-artifacts/prd.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** History indexing still feels like a per-mail crawl: first analyze can block on an empty index (40 msgs), connect only pulls 100, there is no durable “profile built” state, and reopening Outlook does not incrementally refresh. Users never see that a style profile is being built.

**Approach:** Treat Sent Items embeddings as a per-mailbox history profile. Bootstrap once up to **300** messages (non-blocking for analyze). Show clear UI status while building / ready / failed. On each Outlook session open (taskpane load / ensureSession), run an **incremental** sync that only embeds new Sent Items. Never crawl Graph inside analyze once a profile exists or a bootstrap is in progress.

## Boundaries & Constraints

**Always:**
- Bootstrap target = **300** Sent Items (hub max already 300).
- Analyze must proceed **immediately** even if history profile is empty or still syncing (draft may be absent until chunks exist).
- Sync is incremental: skip already-indexed `source_message_id`s; do not re-embed the whole mailbox every time.
- Persist per-mailbox sync lifecycle: at least `not_started | syncing | ready | failed`, `last_history_sync_at`, optional short error, and chunk count (or derive count).
- Outlook open = trigger refresh (taskpane session ensure / connect path), not every selected-mail analyze.
- No mailbox subject/body/tokens in logs.

**Ask First:**
- Background hub cron/scheduler (user chose Outlook-open only).
- Graph delta-link persistence beyond newest-N Sent Items listing.
- Raising the hard cap above 300.

**Never:**
- Block analyze on Graph Sent Items crawl.
- Re-run a full 300 crawl on every analyze or every mail selection.
- Invent Contoso/demo history content.
- Store a separate LoRA fine-tune in this change (RAG chunks only).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First connect, empty index | New/empty mailbox profile | Start bootstrap sync (≤300) async/non-blocking; UI: “Profiel opbouwen…”; analyze allowed | Sync fail → status `failed` + short message; analyze still works |
| Analyze during bootstrap | Chunks 0 or growing | Suggestion without waiting for sync; draft only if enough chunks already | No Graph crawl from analyze |
| Outlook reopen, profile ready | `ready` + prior chunks | Incremental sync for newer Sent Items only; UI brief then ready | Fail → keep previous chunks; status `failed` until next open |
| Sync while already syncing | Second open/connect | No overlapping crawl; reuse in-progress status | Idempotent / no-op |
| Partial Graph/embed failures | Some messages fail embed | Index successful ones; continue; report indexed/total | Skip bad items; do not wipe profile |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/history_sync.py` -- INITIAL 40 / sync_sent_history / ensure_history_indexed (blocking empty path)
- `apps/hub-api/app/api/analyze.py` -- calls ensure_history_indexed before analyze; `/index/sync`
- `apps/hub-api/app/domain/models.py` -- `MailboxProfile` (no history lifecycle fields yet)
- `apps/hub-api/app/db/session.py` -- `create_all` only (no Alembic); need safe column/table ensure for pilot
- `apps/hub-api/app/db/repositories/ai_store.py` -- chunk count / indexed ids
- `apps/hub-api/app/domain/schemas.py` -- `SyncIndexRequest`, `IndexResponse`, `MailboxProfileOut`
- `apps/outlook-addin/src/taskpane/App.tsx` -- connect-time sync(100), silent catch; no reopen refresh for cached profiles
- `apps/outlook-addin/src/taskpane/api/client.ts` -- `syncMailboxIndex`
- `apps/outlook-addin/src/taskpane/components/SuggestionReviewStack.tsx` -- history empty copy
- `tests/api/test_analyze_feedback_confirm.py` -- sync/analyze coverage

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/domain/models.py` (+ session ensure) -- Persist history profile lifecycle fields on mailbox (status, last sync, error); pilot-safe schema ensure without full Alembic rewrite -- durable profile state
- [x] `apps/hub-api/app/services/history_sync.py` -- Bootstrap max **300**; mark syncing/ready/failed; incremental only; remove analyze-blocking crawl (or reduce ensure to no-op when not empty / never block request thread for full crawl) -- one-time build + safe refresh
- [x] `apps/hub-api/app/api/analyze.py` + schemas -- Analyze never waits on Graph history; expose sync status on sync/connect/profile responses as needed -- API contract for UI
- [x] `apps/outlook-addin/src/taskpane/App.tsx` (+ client) -- On every Outlook session open (`ensureSession`), fire incremental sync (300 bootstrap if empty); show Dutch status: opbouwen / klaar / mislukt; do not await sync before analyze -- UX + open trigger
- [x] `tests/api/test_analyze_feedback_confirm.py` -- Analyze with empty index does not require sync completion; sync sets ready + chunk growth; second sync is incremental -- lock lifecycle

**Acceptance Criteria:**
- Given a new mailbox with no chunks, when the user opens the add-in, then a ≤300 Sent Items bootstrap starts and the UI shows profile-building status without blocking analyze.
- Given a mailbox already `ready`, when Outlook opens again, then only new Sent Items are indexed and prior chunks remain.
- Given analyze during sync or with empty history, when the user selects a mail, then analyze returns promptly with no Contoso routes and draft only if chunks already exist.
- Given sync failure, when the user looks at the pane, then a short failure state is visible and previous chunks (if any) remain usable.

## Spec Change Log

## Design Notes

Preferred lifecycle on `MailboxProfile` (or sibling 1:1 row if ALTER is painful):

```
history_status: not_started | syncing | ready | failed
last_history_sync_at: timestamptz | null
history_sync_error: short string | null
```

Outlook-open trigger = `ensureSession` always calling sync (not only first connect). Hub rejects/overlaps concurrent syncs for the same profile.

Analyze path: delete or neuter `ensure_history_indexed` blocking call; bootstrap is owned by open/sync endpoint.

## Verification

**Commands:**
- `cd apps/hub-api && .venv/bin/pytest ../../tests/api/test_analyze_feedback_confirm.py -q` -- expected: all passed

**Manual checks (if no CLI):**
- Fresh mailbox: open add-in → “Profiel opbouwen…” → analyze still runs; later drafts appear once chunks exist
- Reopen add-in on same mailbox → no long full reindex; status returns to klaar quickly

## Suggested Review Order

**Lifecycle API**

- Bootstrap ≤300, incremental, overlapping sync guarded
  [`history_sync.py:175`](../../apps/hub-api/app/services/history_sync.py#L175)

- Analyze never crawls Graph history
  [`analyze.py:54`](../../apps/hub-api/app/api/analyze.py#L54)

- Durable status fields on mailbox profile
  [`models.py:31`](../../apps/hub-api/app/domain/models.py#L31)

**Outlook open UX**

- One refresh per session; Dutch status; `wait:false`
  [`App.tsx:64`](../../apps/outlook-addin/src/taskpane/App.tsx#L64)

**Tests**

- Analyze without sync; incremental second sync indexes 0
  [`test_analyze_feedback_confirm.py:96`](../../tests/api/test_analyze_feedback_confirm.py#L96)
