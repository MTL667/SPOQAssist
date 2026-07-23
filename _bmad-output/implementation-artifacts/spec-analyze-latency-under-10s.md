---
title: 'Analyze latency under 10 seconds'
type: 'refactor'
created: '2026-07-23'
status: 'done'
baseline_commit: '16f771a3415f872db874352783f09d6376ca2f75'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture-dgx-spark-addendum.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Outlook analyze currently takes ~45–60s wall-clock (observed 56s), which makes SpoqSense feel broken even when drafts are correct.

**Approach:** Cut the synchronous analyze path to ≤10s p50 on DGX by shrinking LLM work (context + tokens), skipping dead-weight steps (broken rerank), returning structured stage timings, and preferring cached/precomputed classify when available — without restarting the 32B draft service.

## Boundaries & Constraints

**Always:**
- Target: analyze with `include_draft=true` completes in ≤10s wall-clock on DGX for a typical short reply (no attachments, history ready).
- Keep thinking disabled for classify and draft (`chat_template_kwargs.enable_thinking=false`).
- Surface stage timings in the analyze API and add-in (`Laatste analyze` already exists; show stages when present).
- Existing tests must pass; add timing/contract coverage for the new fields.
- Scope this change tightly — do not expand unrelated dirty-tree WIP.

**Ask First:**
- Whether to drop 27B classify entirely for stub/heuristic classify on the hot path (quality tradeoff).
- Whether to start a separate smaller draft model / second vLLM instance (memory risk on 128GB Spark).

**Never:**
- Do not re-enable Qwen thinking mode on classify/draft.
- Do not block analyze on history sync or behavior-summary LLM regeneration.
- Do not change suggestion accept/reject/confirm contracts beyond additive timing fields.
- Do not require bringing `vllm-draft` 32B back online for this goal.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path short reply | History ready, include_draft=true, short NL/EN mail | Suggestion + draft in ≤10s; timings sum ≈ wall clock | N/A |
| Draft timeout / model busy | Draft exceeds budget | Analyze still 200 with draft=null; timings show draft stage; UI Generate response | Soft-fail draft, never 503 for timeout |
| Precompute hit | Cached suggestion exists for message | Reuse classify/retrieval; only draft (or skip draft if cached) | Fall back to full path if cache miss/stale |
| Reranker down | Reranker HTTP 404 | Skip rerank immediately (no 10s wait) | Log once; continue with vector ranking |
| No history | history_status none | Classify-only path still ≤10s; no draft required | N/A |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/analyze.py` -- orchestrates Graph load → retrieve → classify → draft
- `apps/hub-api/app/services/inference.py` -- `_classify_via_27b`, `_generate_draft`, token/context caps
- `apps/hub-api/app/services/retrieve.py` -- embed + optional rerank (currently 404 on DGX)
- `apps/hub-api/app/services/precompute.py` -- background classify cache not yet consumed by analyze
- `apps/hub-api/app/core/config.py` -- `VLLM_CLASSIFY_TIMEOUT`, `VLLM_DRAFT_TIMEOUT`
- `apps/hub-api/app/domain/schemas.py` -- `SuggestionOut` additive timings
- `apps/outlook-addin/src/taskpane/App.tsx` -- shows `Laatste analyze: Xs`
- `apps/outlook-addin/src/taskpane/components/AnalyzingState.tsx` -- live elapsed during analyze

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/retrieve.py` -- fail-fast when reranker is unavailable (no long timeout on 404) -- removes dead wait
- [x] `apps/hub-api/app/services/inference.py` -- cut draft context (thread/profile/style) and `max_tokens` (~180–256); keep thinking off -- main latency lever
- [x] `apps/hub-api/app/services/inference.py` -- cut classify prompt/body caps and `max_tokens` (~120–160) -- second LLM lever
- [x] `apps/hub-api/app/services/analyze.py` + `precompute.py` -- reuse precomputed classify/snippets when fresh for message_id -- avoid duplicate 27B classify
- [x] `apps/hub-api/app/domain/schemas.py` + analyze response mapping -- additive `timings` map (ms): `graph`, `retrieve`, `classify`, `draft`, `total` -- makes regressions visible
- [x] `apps/outlook-addin/src/taskpane/*` -- show stage timings under `Laatste analyze` when API provides them -- operator visibility
- [x] `tests/api/*` -- cover timings field + rerank fail-fast + draft context caps do not break language/parrot tests -- regression safety

**Acceptance Criteria:**
- Given mailbox history ready and a short confirmation mail, when the user runs Analyze with draft, then wall-clock ≤10s on DGX and a draft is usually present.
- Given reranker returns 404, when retrieve runs, then analyze does not spend multi-second waits on rerank.
- Given a fresh precomputed suggestion for the same message_id, when Analyze runs, then classify is skipped or reused and timings reflect that.
- Given draft generation exceeds its budget, when Analyze finishes, then HTTP 200 with draft=null and timings.draft populated — not 503.
- Given the add-in receives timings, when Analyze completes, then the UI shows total seconds and the dominant stage.

## Spec Change Log

## Design Notes

Dominant cost today is **two serial 27B calls on `:8001`**. Draft prompts currently allow ~16k thread + 3k profile + 2k style with `max_tokens=512`. Shrinking that and skipping classify on precompute hit is the cheapest path to ≤10s without more GPU memory.

Preferred order of attack:
1. Fail-fast rerank
2. Shrink draft/classify prompts + tokens
3. Consume precompute cache for classify/retrieval
4. Only if still >10s: ask about heuristic classify or a small dedicated draft model

Golden timing shape (additive JSON):

```json
"timings": {
  "graph_ms": 120,
  "retrieve_ms": 180,
  "classify_ms": 2400,
  "draft_ms": 5200,
  "total_ms": 8100
}
```

## Verification

**Commands:**
- `cd apps/hub-api && PYTHONPATH=. pytest ../../tests/api/test_draft_language.py ../../tests/api/test_vllm_client.py -q` -- expected: pass
- Manual DGX: Analyze short Sent-style confirmation mail twice -- expected: first ≤10s (or close), second with precompute ≤10s and lower `classify_ms`

**Manual checks (if no CLI):**
- Outlook add-in shows `Laatste analyze` under 10s and optional stage breakdown
- Hub logs no multi-second `reranker_http_error` stalls

## Suggested Review Order

**Orchestration + timings**

- Entry point: stage timers, precompute hit, boost queue
  [`analyze.py:131`](../../apps/hub-api/app/services/analyze.py#L131)

- Fresh precompute classify reuse
  [`analyze.py:73`](../../apps/hub-api/app/services/analyze.py#L73)

- Total timing logged + returned
  [`analyze.py:327`](../../apps/hub-api/app/services/analyze.py#L327)

**LLM shrink (main latency lever)**

- Cached classification skips 27B classify
  [`inference.py:763`](../../apps/hub-api/app/services/inference.py#L763)

- Classify token/thinking budget
  [`inference.py:886`](../../apps/hub-api/app/services/inference.py#L886)

- Draft context/token budget + soft-fail
  [`inference.py:1095`](../../apps/hub-api/app/services/inference.py#L1095)

**Rerank fail-fast**

- Disable after 404; 2s timeout
  [`retrieve.py:135`](../../apps/hub-api/app/services/retrieve.py#L135)

- Dedicated reranker URL + tighter timeouts
  [`config.py:62`](../../apps/hub-api/app/core/config.py#L62)

**API + UI**

- Additive timings field
  [`schemas.py:114`](../../apps/hub-api/app/domain/schemas.py#L114)

- Dominant stage in add-in
  [`App.tsx:725`](../../apps/outlook-addin/src/taskpane/App.tsx#L725)

**Tests**

- Timings schema + rerank fallback
  [`test_analyze_timings.py:1`](../../tests/api/test_analyze_timings.py#L1)
