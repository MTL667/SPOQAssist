---
title: 'Use cached behavior summary as draft user prompt'
type: 'feature'
created: '2026-07-22'
status: 'done'
baseline_commit: '53fbe03314c647c337f4cfff1aae95520081b1fc'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-mailbox-profile-inspector.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-fix-behavior-summary-qwen-think.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The mailbox behavior summary exists only for Check profiel. Draft / Generate response still ignore it, so generation does not consistently follow the user’s style/routing “prompt”.

**Approach:** Persist the behavior summary on the mailbox profile. Refresh it on Check profiel and after history sync becomes ready. Inject the cached summary into every draft generation path (analyze + Generate response) without re-running Ollama for the summary on each draft.

## Boundaries & Constraints

**Always:**
- Store summary text (+ updated timestamp) on `mailbox_profiles` (pilot schema ensure OK).
- Refresh cached summary when: (1) user opens Check profiel with summary, (2) history sync completes to ready (best-effort).
- Every draft generate (including Generate response → analyze `include_draft=true`) includes the cached summary as a first-class “user/mailbox prompt” block.
- If cache is empty at draft time: use fast **grounded** summary from chunks/routes (no extra 14B call), persist it, and use that for the draft.
- Keep RAG Sent snippets; summary guides tone/habits, snippets remain style examples.
- Never block analyze on a fresh LLM summary regeneration.

**Ask First:**
- Background cron refresh of summaries.
- Replacing RAG snippets entirely with summary-only prompting.

**Never:**
- External LLM APIs.
- Regenerating the LLM summary on every analyze/draft.
- Returning raw chunk bodies to the add-in.
- Inventing habits when history is empty (no cache, no grounded style).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Draft with cached summary | Profile has summary text | Draft prompt includes that block; draft can match tone | N/A |
| Draft, cache empty, history ready | Chunks exist, no cache | Grounded summary built+persisted; used in draft | No 14B summary call |
| Generate response | Same as analyze include_draft | Same summary injection | N/A |
| Check profiel | include_summary=true | Refresh cache (LLM or grounded fallback) then show | Keep inspect usable |
| Empty history | 0 chunks | No invented style in cache/draft | Draft may be absent/generic as today |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/domain/models.py` + `schema_ensure.py` -- mailbox profile columns
- `apps/hub-api/app/services/profile_inspect.py` -- build/refresh summary; grounded helper
- `apps/hub-api/app/services/history_sync.py` -- mark ready after sync
- `apps/hub-api/app/services/analyze.py` + `inference.py` -- pass summary into `_generate_draft`
- `apps/hub-api/app/api/mailbox_profiles.py` -- inspect refresh path
- `tests/api/test_analyze_feedback_confirm.py` / `test_profile_inspect.py` -- draft uses summary; cache persist

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/domain/models.py` + `schema_ensure.py` (+ schemas if needed) -- Add `behavior_summary_text` / `behavior_summary_updated_at`; ensure on boot -- durable cache
- [x] `apps/hub-api/app/services/profile_inspect.py` (+ small store helper) -- `refresh_behavior_summary` / `ensure_cached_summary`; inspect writes cache; grounded fill when empty -- one write path
- [x] `apps/hub-api/app/services/history_sync.py` -- After sync → ready, best-effort refresh cache (grounded OK if LLM heavy) -- stay fresh after index
- [x] `apps/hub-api/app/services/analyze.py` + `inference.py` -- Load cache (or ensure grounded); inject into draft prompt for analyze/Generate response -- use profile when generating
- [x] `tests/api/test_analyze_feedback_confirm.py` (+ inspect if needed) -- Cached/grounded summary appears in draft path; empty history does not invent -- lock matrix

**Acceptance Criteria:**
- Given a profile with a cached behavior summary, when analyze/Generate response creates a draft, then the instruct prompt includes that summary as the mailbox user prompt.
- Given history exists but cache is empty, when a draft is requested, then a grounded summary is persisted and used without a per-draft 14B summary call.
- Given Check profiel with summary, when it completes, then `behavior_summary_text` on the profile is updated.
- Given no Sent history, when drafting, then no invented style summary is forced into the prompt.

## Spec Change Log

## Design Notes

Draft prompt addition (illustrative):

```
Mailbox owner prompt (cached behavior profile):
Mailbox: kevin@… (personal)
Style: mostly Dutch; short replies…
Routing: …
```

Still followed by retrieved Sent style examples. Generate response is the same analyze `include_draft` path — no separate add-in API required if hub injection is correct.

## Verification

**Commands:**
- `apps/hub-api/.venv/bin/pytest tests/api/test_profile_inspect.py tests/api/test_analyze_feedback_confirm.py -q` -- expected: pass

**Manual checks:**
- Check profiel once → Analyze / Generate response → draft tone should reflect summary habits
- Confirm drafts do not wait on a new summary LLM call each time

## Suggested Review Order

**Durable cache**

- Profile columns for cached persona prompt
  [`models.py:40`](../../apps/hub-api/app/domain/models.py#L40)

- Pilot ALTER ensure for new columns
  [`schema_ensure.py:12`](../../apps/hub-api/app/db/schema_ensure.py#L12)

**Refresh + draft injection**

- Persist/ensure/refresh summary helpers
  [`profile_inspect.py:108`](../../apps/hub-api/app/services/profile_inspect.py#L108)

- Analyze loads cache (grounded fill) before draft
  [`analyze.py:117`](../../apps/hub-api/app/services/analyze.py#L117)

- Instruct prompt includes mailbox owner prompt block
  [`inference.py:351`](../../apps/hub-api/app/services/inference.py#L351)

- Grounded refresh after history sync ready
  [`history_sync.py:148`](../../apps/hub-api/app/services/history_sync.py#L148)

**Tests**

- First draft fills cache; inspect + draft consume profile
  [`test_profile_inspect.py:164`](../../tests/api/test_profile_inspect.py#L164)
