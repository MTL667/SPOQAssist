---
title: 'Full thread as context; answer latest only'
type: 'bugfix'
created: '2026-07-22'
status: 'done'
baseline_commit: '77637bb86d0facc9049a9509a0002a107eb056d2'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-reply-latest-message-in-thread.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After the latest-vs-thread split, drafts correctly avoid parroting old lines, but the model may not see enough of the **full** mail chain as background (thread context was truncated; retrieve used only the latest segment).

**Approach:** Keep answering **only** the latest inbound segment, while feeding the **entire** original body (full thread) as context in the draft prompt. Clarify labeling so “answer latest / use full mail as context” is unambiguous. Optionally include light thread text in retrieve without letting quoted history dominate.

## Boundaries & Constraints

**Always:**
- Draft prompt includes: (1) LATEST message to answer, (2) FULL original body as thread context (not a short truncated quote slice only).
- Hard rules unchanged: answer only the latest ask; never paste prior owner replies from the thread; style snippets = tone only.
- Thread split still used to identify the latest segment.
- Analyze/draft must not invent Contoso routes.

**Ask First:**
- Graph `uniqueBody` for latest (still optional).

**Never:**
- Answering the whole chain as if it were one new request.
- Dropping thread context to save tokens when the body is a normal Outlook chain (pilot: allow larger context; keep num_ctx sane).
- External LLM APIs.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Long ACEG-style thread | Short latest + long quotes | Prompt has full body as context; draft answers latest only | Truncate only if far above instruct budget |
| Short single mail | No quotes | Latest = full body; context = same/full body OK | N/A |
| Parrot risk | Old owner line in thread | Still reject verbatim paste | Existing parrot guard |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/inference.py` -- `thread_ctx = parts.thread_context[:2000]`; prompt blocks
- `apps/hub-api/app/services/analyze.py` -- retrieve query uses only `latest_message`
- `apps/hub-api/app/services/thread_split.py` -- latest extraction
- `tests/api/test_thread_split.py` -- latest/parrot coverage

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/inference.py` -- Put full original `body` in a “Full mail thread (context)” block; keep “LATEST to answer” separate; raise caps within num_ctx; tighten wording -- full context, answer latest
- [x] `apps/hub-api/app/services/analyze.py` -- Retrieve with latest + short subject; optionally append truncated thread for topic (latest still weighted first) -- better background without quote-dominance
- [x] `tests/api/test_thread_split.py` -- Assert draft path/prompt construction uses full body as context field (unit or stub why/marker); still no parrot of “Top dank u” -- lock intent

**Acceptance Criteria:**
- Given a threaded mail, when a draft is generated, then the instruct prompt contains the full original body as context and a distinct latest-message block as the answer target.
- Given that same mail, when a draft is returned, then it answers the latest ask and does not reproduce prior owner lines from the thread.
- Given a short non-threaded mail, when drafting, then behavior remains correct (latest ≈ full body).

## Spec Change Log

## Design Notes

Preferred prompt shape:

```
LATEST message to answer (ONLY this):
...

Full mail thread (context — do not answer older parts; do not copy prior replies):
...entire body...
```

Keep `think: false` and parrot rejection.

## Verification

**Commands:**
- `apps/hub-api/.venv/bin/pytest tests/api/test_thread_split.py -q` -- expected: pass

**Manual checks:**
- ACEG “Al nieuws van?” → draft answers that, but can reference laptop/topic from the chain when relevant

## Suggested Review Order

- Full body as context + distinct LATEST block in draft prompt
  [`inference.py:363`](../../apps/hub-api/app/services/inference.py#L363)

- Helper: latest vs full body for drafts
  [`thread_split.py:34`](../../apps/hub-api/app/services/thread_split.py#L34)

- Retrieve: latest first, short thread tail for topic
  [`analyze.py:110`](../../apps/hub-api/app/services/analyze.py#L110)

- Test: full body kept as context, latest excludes old reply
  [`test_thread_split.py:64`](../../tests/api/test_thread_split.py#L64)
