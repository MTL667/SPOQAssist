---
title: 'Fix behavior summary (Qwen3 think empties response)'
type: 'bugfix'
created: '2026-07-22'
status: 'done'
baseline_commit: 'efee71deb2cb49dfa137049ab6389b29fb62e6f4'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-mailbox-profile-inspector.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Check profiel shows “Behavior summary unavailable” even with 300 indexed Sent mails. Hub logs `ollama_behavior_summary_timeout` / empty responses because `qwen3:14b` spends tokens on `thinking` and leaves `response` empty — so the user never sees their style/routing “prompt”.

**Approach:** Disable Ollama thinking for instruct generation used by behavior summary (and the same draft generate path). Always return a usable summary when history exists: LLM text when available, otherwise a grounded heuristic persona prompt from routes + Sent samples (never invent habits from nothing).

## Boundaries & Constraints

**Always:**
- Instruct `/api/generate` calls for summary (and draft) set `think: false` (or equivalent) so `response` is populated.
- With indexed history, Check profiel **must** show non-empty behavior summary prose (LLM or grounded fallback) — not only an error string.
- Fallback summary is derived only from routes + hub-side chunk samples / counts; Dutch OK when samples are Dutch.
- Never return raw `chunk_text` arrays to the add-in.

**Ask First:**
- Switching instruct model away from `qwen3:14b`.
- Persisting the summary in Postgres.

**Never:**
- External LLM APIs.
- Fake persona when chunk_count is 0 and no routes.
- Blocking analyze on summary generation.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ready profile, Ollama OK | 300 chunks, think disabled | `behavior_summary.status=ok` with style/routing prose | N/A |
| Ollama timeout / down | History exists | Grounded fallback summary still `ok` (or `empty` only if no evidence) | Log timeout; no hard fail UI |
| Empty history | 0 chunks, 0 routes | Existing empty copy — no invented habits | N/A |
| Draft generate | Same model | `response` non-empty more often (think off) | Keep existing draft fallbacks |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/inference.py` -- `summarize_mailbox_behavior` / `_generate_draft` Ollama generate; empty/timeout paths
- `apps/hub-api/app/services/profile_inspect.py` -- turns AppError into `status=error` (hides fallback opportunity)
- `tests/api/test_profile_inspect.py` -- summary happy/error cases
- Studio log evidence: `ollama_behavior_summary_timeout`; local repro: generate without `think:false` → empty `response`, non-empty `thinking`

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/inference.py` -- Pass `think: false` on instruct generate (summary + draft); treat empty `response` after success as failure into fallback path -- fix Qwen3 empty replies
- [x] `apps/hub-api/app/services/profile_inspect.py` (+ inference helper) -- On summary timeout/unavailable/empty, build grounded heuristic persona text when chunks/routes exist; only `error` when truly nothing to say -- Check profiel always usable with history
- [x] `tests/api/test_profile_inspect.py` -- Timeout/raise from summarize still yields non-empty summary when chunks exist; empty history stays empty -- lock matrix

**Acceptance Criteria:**
- Given a ready mailbox with indexed Sent history, when the user opens Check profiel, then Gedragssamenvatting shows a real persona/style prompt (not only “unavailable”).
- Given Ollama times out, when inspect runs with history, then a grounded fallback summary is still returned.
- Given no history and no routes, when inspect runs, then no invented habits appear.

## Spec Change Log

## Design Notes

Root cause (Studio): `qwen3:14b` returns `thinking` filled and `response` `""` unless `think: false`. Same bug explains frequent `ollama_draft_empty_fallback`.

Fallback shape (illustrative):

```
Mailbox: kevin@… (personal)
Style: mostly Dutch; short confirmations; first-name sign-off (from Sent samples).
Routing: (none learned yet)
History: 300 Sent chunks · status ready
```

## Verification

**Commands:**
- `apps/hub-api/.venv/bin/pytest tests/api/test_profile_inspect.py -q` -- expected: pass

**Manual checks:**
- Studio Check profiel → Gedragssamenvatting shows style prose for kevinvanhoecke@…
- Retry after fix without waiting on a 45s hard fail

## Suggested Review Order

**Root cause fix**

- Disable Qwen3 thinking so `response` is filled for drafts
  [`inference.py:375`](../../apps/hub-api/app/services/inference.py#L375)

- Same for behavior summary generate
  [`inference.py:486`](../../apps/hub-api/app/services/inference.py#L486)

**Usable persona when model fails**

- Grounded fallback from Sent samples + routes
  [`profile_inspect.py:78`](../../apps/hub-api/app/services/profile_inspect.py#L78)

- Prefer LLM; on failure still return `ok` prose with history
  [`profile_inspect.py:173`](../../apps/hub-api/app/services/profile_inspect.py#L173)

**Tests**

- Model-down → grounded Dutch summary, not unavailable
  [`test_profile_inspect.py:120`](../../tests/api/test_profile_inspect.py#L120)
