---
title: 'Draft language matches latest mail + profile (no English fallback)'
type: 'bugfix'
created: '2026-07-22'
status: 'done'
baseline_commit: 'a751df1c7b72f4213a4c7fc24149963413cab46e'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-full-thread-context-answer-latest.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dutch inbound mail and a Dutch-leaning mailbox profile still produce English stubs like “Thanks for your message — I will look into this…”. Hub logs show `draft_rejected_thread_parrot` then `ollama_draft_empty_fallback` — an English hardcoded fallback replaces the model reply.

**Approach:** Detect reply language from the LATEST message (with Dutch profile hints as secondary signal). Make every draft fallback language-aware (NL/EN). Soften parrot rejection so common greetings/closings do not discard a good Dutch reply.

## Boundaries & Constraints

**Always:**
- Reply language = language of LATEST inbound segment when detectable; else Dutch if profile/summary shows Dutch habits; else English.
- All hardcoded draft fallbacks (empty/timeout/parrot/inverted-perspective) use that language.
- Prompt keeps “match LATEST language” and may name the detected language explicitly.
- Parrot guard still blocks long distinctive paste from quoted history/style; common NL/EN openers/closers alone must not trigger reject → English stub.

**Ask First:**
- Languages beyond NL/EN.

**Never:**
- English-only fallback when LATEST is clearly Dutch.
- Removing parrot protection entirely.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dutch latest + parrot/empty/timeout | Model missing or rejected | Short Dutch fallback, not EN stub | Log + `fallback_lang=nl` |
| Dutch latest + OK model | Valid Dutch draft; only shares “Met vriendelijke groet” with thread | Draft kept | N/A |
| English latest | EN inbound | EN draft/fallback OK | N/A |
| Long verbatim paste | Draft copies 18+ char distinctive owner/thread phrase | Reject → language-matched fallback | Log parrot |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/inference.py` -- English stubs at empty/timeout/inverted paths; `_reject_thread_parrot` (4–6 word / 18+ char substring); prompt rule 7 already says match LATEST language
- `apps/hub-api/app/services/thread_split.py` -- `latest` segment for language detection
- `apps/hub-api/app/services/draft_language.py` -- new small helper (detect + fallback templates) if cleaner than stuffing inference.py
- `tests/api/test_draft_language.py` -- new unit tests for detect/fallback/parrot soften

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/draft_language.py` -- Detect `nl`/`en` from latest (+ optional profile text); NL/EN fallback templates with greet name -- single place for stubs
- [x] `apps/hub-api/app/services/inference.py` -- Wire detect into generate; replace all English stubs; pass detected lang into prompt; soften parrot (skip common closing/greeting phrases; require longer distinctive match) -- stop EN stub on Dutch mail
- [x] `tests/api/test_draft_language.py` -- Cover I/O matrix: Dutch latest → NL fallback; short groet overlap kept; long paste rejected -- lock

**Acceptance Criteria:**
- Given a Dutch latest message, when draft generation falls back after timeout/parrot/empty/inverted, then the shown draft is Dutch (not the English “Thanks for your message…” stub).
- Given a Dutch latest message and a successful model draft that only shares common Dutch closings with the thread, when parrot runs, then the draft is kept.
- Given an English latest message, when falling back, then English fallback remains acceptable.

## Spec Change Log

## Design Notes

Root cause: model output → `_reject_thread_parrot` too eager on shared phrases → English stub. Profile already mentions Dutch; prompt rule 7 is ignored by fallbacks.

NL fallback sketch:
`Dag {name},\n\nBedankt voor je bericht — ik kijk dit na en kom erop terug.\n\nMet vriendelijke groet`

Detection: simple keyword/heuristic on latest (nl markers: je/jij/bedankt/groet/dag/hallo/alsjeblieft/…); if weak, scan profile for “Dutch” / Dutch sample phrases.

## Verification

**Commands:**
- `apps/hub-api/.venv/bin/pytest tests/api/test_draft_language.py tests/api/test_thread_split.py -q` -- expected: pass

**Manual checks:**
- Dutch follow-up mail → Generate response → Dutch draft even if model path falls back

## Suggested Review Order

**Language detection + fallbacks**

- Single place for NL/EN detect and ack templates used on every failure path
  [`draft_language.py:135`](../../apps/hub-api/app/services/draft_language.py#L135)

- Safe Dutch ack replaces English stub when model/parrot path fails
  [`draft_language.py:161`](../../apps/hub-api/app/services/draft_language.py#L161)

- Ollama draft path detects lang, names it in the prompt, and falls back in that language
  [`inference.py:382`](../../apps/hub-api/app/services/inference.py#L382)

**Parrot softening**

- Skip common groeten; still reject distinctive 18+ / longer pastes
  [`draft_language.py:221`](../../apps/hub-api/app/services/draft_language.py#L221)

- Inverted-perspective rejects also use language-matched fallbacks
  [`inference.py:504`](../../apps/hub-api/app/services/inference.py#L504)

**Tests**

- Lock detect, NL fallback, closing keep, short/long paste reject
  [`test_draft_language.py:1`](../../tests/api/test_draft_language.py#L1)
