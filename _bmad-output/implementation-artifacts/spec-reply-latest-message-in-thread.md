---
title: 'Reply to latest message; thread is context only'
type: 'bugfix'
created: '2026-07-22'
status: 'done'
baseline_commit: '7ca18240dc71ccfc3430f2232c964473bfbe781e'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-use-cached-behavior-summary-in-drafts.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** On threaded mail (e.g. “Al nieuws van?” above quoted history), drafts often rewrite or paste an older outbound line from the same chain (e.g. “Top dank u, ook nog op haha”) instead of answering the newest inbound message.

**Approach:** Treat the full body as a mail thread: extract the **latest inbound segment** as the thing to answer, keep the rest as **thread context**, and harden the draft prompt so the model must answer only that latest ask and must not copy prior replies from the thread or style snippets.

## Boundaries & Constraints

**Always:**
- Split incoming text into `latest_message` + `thread_context` before draft generation (hub-side; works for Office.js full body and Graph body).
- Draft prompt labels them separately; instruct: answer **only** the latest message; use thread as background; never quote/reuse prior owner replies from the thread.
- Style RAG snippets remain tone-only — hard rule: do not copy their wording.
- Classification/analyze may still see enough of the latest message (and light context) to categorize.

**Ask First:**
- Prefer Graph `uniqueBody` as latest when OBO is available (nice-to-have; not required if splitter is solid).
- Changing Office.js to fetch conversation separately.

**Never:**
- Reply that is mostly a paste of text already in the thread from the mailbox owner.
- Dropping all thread context (user wants context retained).
- External LLM APIs.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Thread with quote | Latest “Al nieuws van?” + older Kevin reply in quotes | Draft answers the news ask; does not repeat “Top dank u…” | N/A |
| Single short mail | No quote markers | Entire body = latest; context empty | N/A |
| Split fails | Ambiguous body | Treat full body as latest; still ban copying owner-looking quoted blocks when detectable | Log split_fallback |
| Style snippet matches old reply | RAG returns similar Sent text | Prompt forbids verbatim reuse; draft must be new answer | N/A |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/inference.py` -- `_generate_draft` dumps `body[:1500]` as one “Incoming message”
- `apps/hub-api/app/services/analyze.py` / `mail_read.py` -- loads full body from Graph or client
- `apps/outlook-addin/src/taskpane/office/officeMail.ts` -- `body.getAsync(Text)` = full item text incl. quotes
- `tests/api/test_analyze_feedback_confirm.py` -- draft path coverage

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/thread_split.py` (new) + unit tests -- Split body into latest vs quoted thread via common markers (From:/Verzonden:/Original Message/On … wrote/etc.) -- reusable splitter
- [x] `apps/hub-api/app/services/inference.py` (+ analyze if needed) -- Pass latest + context into draft prompt; hard rules: answer latest only; no copy from thread/snippets -- stop parrot drafts
- [x] `tests/api/test_thread_split.py` (+ analyze draft case) -- Thread fixture “Al nieuws” + old “Top dank u” → draft prompt/path uses latest; stub/heuristic does not echo old line -- lock bug

**Acceptance Criteria:**
- Given a threaded body whose latest segment asks a new question and quotes an older owner reply, when a draft is generated, then the draft answers the latest question and does not reproduce that older owner reply verbatim.
- Given a non-threaded short body, when a draft is generated, then behavior stays equivalent (whole body is the latest message).
- Given split ambiguity, when drafting, then the system still produces a reply without inventing Contoso routes and without requiring Graph uniqueBody.

## Spec Change Log

## Design Notes

Observed failure: latest ask “Al nieuws van?”; draft = prior Kevin line from the same thread. Prompt today labels the whole blob `Incoming message`, so the model treats old outbound as content to “continue.”

Splitter heuristics (order matters): first cut at `-----Original Message-----`, `From:`, `Verzonden:`, `Op … schreef`, `On … wrote:`, Outlook `_` quote lines — take text **above** the first strong marker as latest.

## Verification

**Commands:**
- `apps/hub-api/.venv/bin/pytest tests/api/test_thread_split.py tests/api/test_analyze_feedback_confirm.py -q` -- expected: pass

**Manual checks:**
- Re-open the ACEG “Al nieuws van?” mail → Generate response → draft answers that ask, not “Top dank u…”

## Suggested Review Order

**Splitter**

- Latest vs quoted thread markers
  [`thread_split.py:34`](../../apps/hub-api/app/services/thread_split.py#L34)

**Draft path**

- Prompt: LATEST vs thread context + no-parrot rules
  [`inference.py:360`](../../apps/hub-api/app/services/inference.py#L360)

- Reject drafts that paste thread/style phrases
  [`inference.py:470`](../../apps/hub-api/app/services/inference.py#L470)

- Retrieve against latest ask only
  [`analyze.py:108`](../../apps/hub-api/app/services/analyze.py#L108)

**Tests**

- ACEG-style fixture: nieuws ask, no “Top dank u” in draft
  [`test_thread_split.py:54`](../../tests/api/test_thread_split.py#L54)
