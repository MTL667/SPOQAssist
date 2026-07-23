---
title: 'Profile sync status updates'
type: 'feature'
created: '2026-07-23'
status: 'done'
baseline_commit: '660c84b9d2e5c8ff2a95c221bb19613b064eea93'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When a mailbox profile is created/synced, the task pane only shows a coarse “Profiel opbouwen…” banner while history stays at 0 chunks. Analyze runs in parallel and surfaces “empty history” before the user knows what the hub is doing.

**Approach:** Expose mid-sync progress from the hub (phase + live counts), poll those fields in the add-in, show clear step/count status, and defer analyze/draft UI until the first history sync finishes (ready or failed).

## Boundaries & Constraints

**Always:**
- Keep poll-based status (no SSE/WebSocket in this change).
- Bootstrap remains ≤300 Sent messages; analyze must not block Graph forever after sync completes/fails.
- Status copy stays user-facing Dutch for lifecycle banner (existing language mix OK elsewhere).
- First-session profile bootstrap: wait for sync terminal state before auto-analyze.
- Failed sync still unlocks the pane (limited/empty history) so the user is never stuck.

**Ask First:**
- Changing bootstrap max (300) or poll interval defaults.
- Adding SSE/WebSocket instead of denser poll fields.

**Never:**
- Invent style/habits while sync is still running.
- Stream mailbox content into the UI (only counts/phase/errors).
- Rewrite the Graph connector or embedding model stack.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh connect + sync | New profile, `wait:false` sync | Banner shows phases + rising message/chunk counts; analyze waits | N/A |
| Sync already ready | Reopen task pane, history `ready` | Banner “Mailbox-profiel klaar”; analyze runs immediately | N/A |
| Sync fails mid-run | Graph/embed error | Banner shows failure reason; analyze unlocks with empty/limited history | Surface `history_sync_error` |
| Sync already in flight | Second `/index/sync` | Poll continues; no second crawl | `started=false` unchanged |
| Inspect during sync | Open Check profiel | Panel reflects same live counts/phase from GET/inspect | N/A |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/history_sync.py` -- mark syncing/ready/failed; crawl+index loop (needs mid-run progress commits)
- `apps/hub-api/app/domain/models.py` -- `MailboxProfile` history columns
- `apps/hub-api/app/domain/schemas.py` -- `MailboxProfileOut`, `IndexResponse`, `ProfileInspectOut`
- `apps/hub-api/app/db/schema_ensure.py` -- additive columns if new progress fields persist
- `apps/hub-api/app/api/mailbox_profiles.py` -- `_to_out` / inspect mapping
- `apps/hub-api/app/services/profile_inspect.py` -- inspect snapshot fields
- `apps/outlook-addin/src/taskpane/App.tsx` -- sync kickoff, 4s poll, banner, auto-analyze gate
- `apps/outlook-addin/src/taskpane/api/client.ts` -- profile/sync types + fetch mappers
- `apps/outlook-addin/src/taskpane/components/CheckProfilePanel.tsx` -- show phase/counts
- `tests/api/` -- extend history-sync / mailbox profile tests for progress fields

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/history_sync.py` (+ models/schemas/schema_ensure as needed) -- Persist and return sync phase + progress counts during crawl/index (`fetching` → `indexing` → `ready`/`failed`; messages fetched/target; chunks) -- Enables live status without streaming
- [x] `apps/hub-api/app/api/mailbox_profiles.py` + `profile_inspect.py` -- Expose new fields on GET profile / index/sync / inspect -- Same source of truth for poll + inspector
- [x] `tests/api/` -- Cover progress field transitions and failed unlock path -- Lock I/O matrix edge cases
- [x] `apps/outlook-addin/src/taskpane/api/client.ts` + `App.tsx` -- Poll phase/counts; richer banner; defer auto-analyze until terminal sync; then run analyze once -- A+B+C UX
- [x] `apps/outlook-addin/src/taskpane/components/CheckProfilePanel.tsx` -- Show phase + live counts while syncing -- Consistent detail view

**Acceptance Criteria:**
- Given a new mailbox profile, when history sync starts, then the task pane shows ordered steps and updating message/chunk counts (not only “Profiel opbouwen…”).
- Given first-session sync is still running, when the user opens a mail, then analyze/draft UI does not claim empty history or show a grounded suggestion yet.
- Given sync reaches `ready` or `failed`, when that terminal state is observed, then analyze proceeds once and the banner reflects klaar or the failure reason.
- Given sync is in progress, when the user opens Check profiel, then phase/counts match the latest GET/inspect snapshot.

## Design Notes

Suggested API fields (names may vary if existing columns can be reused):

```text
history_sync_phase: not_started|fetching|indexing|ready|failed
history_messages_fetched: int
history_messages_target: int   # e.g. bootstrap max or fetched list size
history_chunk_count: int       # already exists — keep polling it
```

Map phases to Dutch banner steps, e.g.:
1. Verbinden / starten
2. Sent-berichten ophalen (N/M)
3. Chunks indexeren (C chunks)
4. Mailbox-profiel klaar | mislukt: …

Keep poll interval ~2–4s; updating counts mid-sync requires committing progress from the background sync thread (same DB session pattern as today).

## Verification

**Commands:**
- `apps/hub-api/.venv/bin/python -m pytest tests/api/ -q -k 'history or mailbox or sync or profile'` -- expected: pass
- `cd apps/outlook-addin && npx tsc --noEmit` -- expected: no type errors

**Manual checks:**
- Fresh profile on DGX/hub: banner advances through fetch/index with rising counts; analyze only after klaar/failed.
- Reopen with existing ready profile: immediate analyze, no stuck waiting UI.

## Suggested Review Order

**Sync progress API**

- Mid-sync phase + message counts committed for poll clients
  [`history_sync.py:83`](../../apps/hub-api/app/services/history_sync.py#L83)

- Derive phase from lifecycle when column still default after migration
  [`history_sync.py:41`](../../apps/hub-api/app/services/history_sync.py#L41)

- Persist progress columns on mailbox profiles
  [`models.py:40`](../../apps/hub-api/app/domain/models.py#L40)

- Inspect uses same phase derivation as GET profile
  [`profile_inspect.py:219`](../../apps/hub-api/app/services/profile_inspect.py#L219)

**Add-in status UX + analyze gate**

- Dutch step banner from phase/counts (status wins over stale phase)
  [`App.tsx:71`](../../apps/outlook-addin/src/taskpane/App.tsx#L71)

- First bootstrap waits for terminal ready/failed; existing history does not
  [`App.tsx:115`](../../apps/outlook-addin/src/taskpane/App.tsx#L115)

- Prior snapshot + 2s poll + one pending analyze after unlock
  [`App.tsx:245`](../../apps/outlook-addin/src/taskpane/App.tsx#L245)

- Check profiel shows phase + message/chunk progress
  [`CheckProfilePanel.tsx:90`](../../apps/outlook-addin/src/taskpane/components/CheckProfilePanel.tsx#L90)

**Tests**

- Ready progress fields + failed phase coverage
  [`test_history_sync_progress.py:22`](../../tests/api/test_history_sync_progress.py#L22)
