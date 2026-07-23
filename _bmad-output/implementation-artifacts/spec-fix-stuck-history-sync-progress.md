---
title: 'Fix stuck history sync progress (0/3000)'
type: 'bugfix'
created: '2026-07-23'
status: 'done'
baseline_commit: '12b7b00'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-profile-sync-status-updates.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Outlook task pane can show `2/4 Sent-berichten ophalen (0/3000)` indefinitely while analyze already works and chunks may exist, so users cannot tell whether sync is alive, stuck, or already usable.

**Approach:** Make history-sync status truthful on every profile poll: recover stale/orphaned `syncing` rows, stop resetting usable profiles to a fake `0/3000` banner during background refresh, and surface a clear “klaar / verversen / vastgelopen” state instead of a silent hang.

## Boundaries & Constraints

**Always:**
- Poll-based status only (no SSE/WebSocket).
- If indexed chunks exist, the UI must never imply “no mail fetched yet” for longer than a short grace window after a refresh starts.
- Stale `syncing` without a live worker must self-heal on `GET` profile (or the next sync kick) within the stale threshold — not only on hub restart.
- Analyze may keep running while a background refresh is in progress (existing unlock-via-chunks behavior stays).
- Existing Dutch banner language remains; improve accuracy of step/counts, do not redesign the pane.

**Ask First:**
- Changing the stale-sync timeout away from the existing 3h constant (e.g. to ~5–15 minutes for pilot UX).
- Dropping automatic re-kick of `/index/sync` from the add-in when stuck (vs hub-only recovery).

**Never:**
- Block analyze again until sync reaches terminal state when chunks already exist.
- Stream mailbox content into the UI.
- Change Graph OBO auth, embedding models, or bootstrap max (3000) in this change.
- Fix missing-draft / generate-response failures (deferred separately).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Orphan after hub restart | `status=syncing`, not inflight, chunks>0 | Next GET (or startup recover) → `ready`; banner “Mailbox-profiel klaar” | Clear `history_sync_error` or keep last soft warning |
| Stale syncing, no chunks | `syncing` + started_at older than stale threshold, not inflight | → `failed` with clear error; banner mislukt; analyze unlocks | Persist short `history_sync_error` |
| Background refresh with chunks | Ready profile, new `/index/sync` starts | Banner shows refresh/verversen with non-zero context (not hard reset to `0/3000` as if empty) | On refresh fail with chunks: stay usable `ready` + error note |
| Live fetch before first page | Fresh sync, worker alive, 0 pages yet | May show `0/target` only briefly; progress rises after first Graph page | If no progress past grace+stale → recover as above |
| Duplicate sync while inflight | Second `/index/sync` during live worker | `started=false`; poll continues; no eternal orphan if worker dies (stale recover) | If worker dead but still marked inflight incorrectly, stale path must still heal on GET |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/history_sync.py` -- `_is_stale_syncing` (unused), orphan recover, `_mark_syncing` reset, `profile_history_snapshot` / `request_history_sync`
- `apps/hub-api/app/api/mailbox_profiles.py` -- GET profile mapping; hook stale heal before response
- `apps/hub-api/app/main.py` -- startup `recover_orphaned_syncing` (keep; complement with poll heal)
- `apps/hub-api/app/services/mail_graph.py` -- optional `on_progress(0)` after token / first heartbeat
- `apps/outlook-addin/src/taskpane/App.tsx` -- `historyProfileLabel`, poll, banner when chunks>0 && syncing
- `apps/outlook-addin/src/taskpane/api/client.ts` -- profile field mapping if additive status hints
- `tests/api/test_history_sync_progress.py` -- extend for orphan/stale/refresh-with-chunks

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/history_sync.py` (+ `mailbox_profiles.py` GET) -- Wire stale/orphan recovery into profile read path; stop `_mark_syncing` from presenting empty 0/target when chunks already exist (preserve last progress or use refresh semantics) -- Truthful status without hub restart
- [x] `apps/hub-api/app/services/mail_graph.py` -- Emit early progress heartbeat so live fetch is distinguishable from a dead worker -- Avoid silent 0/3000 during token/first page
- [x] `apps/outlook-addin/src/taskpane/App.tsx` (+ client types if needed) -- Banner copy: klaar vs achtergrond-verversen vs vastgelopen; never look empty when `history_chunk_count > 0` past grace -- Match user mental model
- [x] `tests/api/test_history_sync_progress.py` -- Cover orphan+chunks→ready, stale+no chunks→failed, refresh-with-chunks does not look empty forever, GET heals without requiring new sync POST -- Lock I/O matrix

**Acceptance Criteria:**
- Given a profile stuck in `syncing` with indexed chunks and no live worker, when the add-in polls GET profile, then status becomes `ready` and the banner no longer shows `0/3000` fetching.
- Given a ready profile starts a background refresh, when the pane polls during that refresh, then the user sees a refresh/verversen state rather than “no messages fetched yet.”
- Given sync is truly stuck with zero chunks past the stale threshold, when GET profile runs, then status becomes `failed` with a clear error and the pane unlocks.
- Given a live Graph fetch is in progress, when the first page (or heartbeat) completes, then `history_messages_fetched` increases above 0 before the full crawl finishes.

## Spec Change Log

## Design Notes

Likely failure modes observed in code (ordered):
1. Session re-kicks `/index/sync` → `_mark_syncing` resets to `0/3000` while chunks/analyze already usable.
2. Worker dies; poll is read-only; `_is_stale_syncing` never called; one sync kick per taskpane session.
3. No progress until first Graph page after OBO token (up to long timeout) — looks identical to dead.

Prefer hub-side heal on GET so any client benefits. UI copy is the second line of defense.

## Verification

**Commands:**
- `pytest tests/api/test_history_sync_progress.py -q` -- expected: all pass including new orphan/stale/refresh cases
- `pytest tests/api/ -q -k history_sync` -- expected: no regressions in related sync tests

**Manual checks (if no CLI):**
- On DGX with an existing indexed mailbox: open task pane → banner must not stick on `2/4 … (0/3000)` once chunks exist; after artificial hub restart mid-sync, next poll should show klaar (or mislukt if no chunks).

## Suggested Review Order

**Heal-on-poll (entry point)**

- GET/poll heals orphaned syncing without requiring hub restart
  [`history_sync.py:57`](../../apps/hub-api/app/services/history_sync.py#L57)

- Refresh-before-heal avoids wiping a just-committed worker terminal state
  [`history_sync.py:76`](../../apps/hub-api/app/services/history_sync.py#L76)

- API output reads healed snapshot status, not a stale ORM row
  [`mailbox_profiles.py:29`](../../apps/hub-api/app/api/mailbox_profiles.py#L29)

**Refresh honesty**

- Existing chunks keep a non-empty fetched floor on background refresh
  [`history_sync.py:128`](../../apps/hub-api/app/services/history_sync.py#L128)

- Monotonic progress so OBO heartbeat `0` cannot wipe that floor
  [`history_sync.py:108`](../../apps/hub-api/app/services/history_sync.py#L108)

- Early Graph heartbeat after OBO token
  [`mail_graph.py:595`](../../apps/hub-api/app/services/mail_graph.py#L595)

**UI copy**

- Banner: achtergrond verversen vs vastgelopen vs first-fetch
  [`App.tsx:125`](../../apps/outlook-addin/src/taskpane/App.tsx#L125)

**Tests**

- Orphan+chunks → ready on GET
  [`test_history_sync_progress.py:108`](../../tests/api/test_history_sync_progress.py#L108)

- Live inflight must not be healed
  [`test_history_sync_progress.py:150`](../../tests/api/test_history_sync_progress.py#L150)

- Mid-fetch progress rises before crawl finishes
  [`test_history_sync_progress.py:177`](../../tests/api/test_history_sync_progress.py#L177)
