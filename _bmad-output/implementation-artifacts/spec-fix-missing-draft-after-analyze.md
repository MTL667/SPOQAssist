---
title: 'Fix missing draft after successful classify'
type: 'bugfix'
created: '2026-07-23'
status: 'done'
baseline_commit: '12f7f4e'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-analyze-latency-under-10s.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Analyze often returns category/priority/why with no draft (“No draft yet” + Generate response). Timings of classify ~8s + draft ~12s match soft-fail on the 12s vLLM draft timeout; Generate only re-runs the same doomed path with no explanation.

**Approach:** Give draft enough time to finish on the shared 27B path, return a clear `draft_error` when soft-fail still happens, and show that reason in the add-in so Generate is an informed retry—not a silent loop.

## Boundaries & Constraints

**Always:**
- Default `VLLM_DRAFT_TIMEOUT` ≥ 30s (align code default with `.env.example`); keep classify soft-fail independent so analyze still returns 200 without a draft.
- When `include_draft=true` and history is not `none`, but draft is null, response MUST include a short machine+human `draft_error` (timeout | rejected | empty | unavailable).
- Add-in must show that reason instead of only “No draft yet”; Generate response remains available for retry.
- Existing tests pass; add coverage for timeout/reject → null draft + `draft_error` populated.
- Do not re-enable Qwen thinking on draft/classify.

**Ask First:**
- Raising draft timeout above 45s or restoring a separate 32B/72B draft service.
- Adding a dedicated draft-only HTTP endpoint (vs retrying full analyze).

**Never:**
- Invent canned/stub reply text when the model times out or rejects (no fake drafts).
- Fail the whole analyze with 5xx solely because draft soft-failed.
- Change accept/reject/confirm contracts except additive `draft_error`.
- Re-open history-sync stuck work (already shipped).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Draft succeeds within timeout | History ready, vLLM returns text | `draft` set, `draft_error` null | N/A |
| Draft times out | vLLM exceeds draft timeout | HTTP 200, classify OK, `draft` null, `draft_error` mentions timeout | Soft-fail; Generate retries |
| Parrot/inverted reject | Model returns rejected text | `draft` null, `draft_error` mentions rejected/filtered | Soft-fail |
| Empty history | `history_status=none` | `draft` null; UI empty-history copy (not timeout copy); no false timeout error | Skip draft |
| `include_draft=false` | Precompute/analyze without draft | `draft` null, `draft_error` null | N/A |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/core/config.py` -- `vllm_draft_timeout` default
- `.env.example` -- keep aligned with code default
- `apps/hub-api/app/services/inference.py` -- `_generate_draft` soft-fail reasons
- `apps/hub-api/app/services/analyze.py` -- propagate `draft_error` onto suggestion/response
- `apps/hub-api/app/domain/schemas.py` -- additive `draft_error` on suggestion out
- `apps/outlook-addin/src/taskpane/api/mappers.ts` + view models -- map field
- `apps/outlook-addin/src/taskpane/components/SuggestionHero.tsx` (+ ReviewStack if same copy) -- show reason
- `tests/api/test_vllm_client.py` / analyze tests -- timeout/reject → draft_error

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/core/config.py` (+ `.env.example` if needed) -- Raise default draft timeout to 30s -- Match observed timeout failures
- [x] `apps/hub-api/app/services/inference.py` + `analyze.py` + `schemas.py` -- Thread soft-fail reason into analyze response as `draft_error` -- Truthful UI
- [x] `apps/outlook-addin/src/taskpane/` (mappers, SuggestionHero, ReviewStack if applicable) -- Show `draft_error` with Generate still available -- Stop silent “No draft yet”
- [x] `tests/api/` -- Cover timeout and reject paths: draft null + draft_error set; success path unchanged -- Lock matrix

**Acceptance Criteria:**
- Given a typical short reply with history ready, when analyze runs with default timeouts, then draft completes more often within 30s (no automatic null at 12s).
- Given draft still soft-fails (timeout/reject/empty), when analyze returns 200, then `draft_error` is present and the pane shows why—not only “No draft yet.”
- Given `history_status=none`, when analyze returns, then UI uses empty-history messaging and does not claim a draft timeout.
- Given Generate response is clicked after a soft-fail, when analyze retries, then the user sees either a draft or an updated `draft_error` (no invented canned text).

## Spec Change Log

## Design Notes

Observed fingerprint: classify_ms≈8000 + draft_ms≈12000 with null draft ⇒ `VLLM_DRAFT_TIMEOUT=12` soft-fail. Shared 27B on :8001 is slower than the old dedicated draft service; 30s is the minimum honest default without bringing 32B back.

Prefer additive `draft_error: str | null` over a large status enum for pilot speed.

## Verification

**Commands:**
- `pytest tests/api/test_vllm_client.py tests/api/test_analyze_feedback_confirm.py -q` -- expected: pass with new draft_error cases
- `pytest tests/api/ -q -k 'draft or analyze'` -- expected: no regressions

**Manual checks (if no CLI):**
- On DGX: open a mail with history → draft text appears, or a clear timeout/reject reason; Generate retries without inventing a stub reply.

## Suggested Review Order

**Timeout + soft-fail reasons (entry)**

- Default draft timeout 12s → 30s
  [`config.py:65`](../../apps/hub-api/app/core/config.py#L65)

- VLLM `_generate_draft` returns `(draft, draft_error)` with timeout/reject/empty reasons
  [`inference.py:998`](../../apps/hub-api/app/services/inference.py#L998)

- Analyze attaches `draft_error` only when draft was attempted and missing
  [`analyze.py:337`](../../apps/hub-api/app/services/analyze.py#L337)

**UI**

- Hero shows grounded empty-history vs soft-fail reason
  [`SuggestionHero.tsx:66`](../../apps/outlook-addin/src/taskpane/components/SuggestionHero.tsx#L66)

- Mapper passes `draft_error` through
  [`mappers.ts:23`](../../apps/outlook-addin/src/taskpane/api/mappers.ts#L23)

**Tests**

- Timeout and parrot reject populate `draft_error`
  [`test_vllm_client.py:163`](../../tests/api/test_vllm_client.py#L163)
