---
title: 'Fire calendar consult on scheduling intent, not only category=="meeting"'
type: 'bugfix'
created: '2026-07-24'
status: 'done'
baseline_commit: '3d3d4a29b47fb4f568edd27a0459acf064d9d0aa'
context: ['{project-root}/_bmad-output/implementation-artifacts/spec-calendar-aware-meeting-proposals.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The calendar-availability consult in `analyze.py` only runs when the 27B classifier returns `category == "meeting"`. Real scheduling mails (e.g. "Kunnen we een moment voorzien voor 31/8 …") get classified as `action_required`, so the calendar is never checked and the draft stays vague ("ik stuur je zo een uitnodiging door") instead of proposing concrete free times.

**Approach:** Decouple the calendar consult from the single classifier label. Add a shared scheduling-intent detector and fire the consult when `category == "meeting"` OR scheduling intent is detected. Do not change priority/routing semantics.

## Boundaries & Constraints

**Always:** Consult the calendar only when there is genuine scheduling intent (a meeting/appointment is being arranged). Keep the consult on the draft path (`include_draft=True`) only. Reuse the same Graph busy-fetch + `find_free_slots` pipeline already built. Preserve existing behavior for mails already classified `meeting`.

**Ask First:** Changing the 27B classify prompt or the displayed `category` value. Broadening scope to non-draft (fast) analyze.

**Never:** Booking events automatically. Consulting the calendar for clearly non-scheduling mails (fyi/spam/invoice with only an incidental date). Adding new Graph scopes. Regressing the existing `meeting`-category flow.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Scheduling mail mislabeled | Mail with scheduling intent ("moment voorzien voor 31/8"), classifier → `action_required`, `include_draft=True` | Calendar consulted; `proposed_slots`/`availability_note` populated; draft proposes concrete times | Graph consent/scope errors handled as today (soft-fail, no slots) |
| Already `meeting` | Classifier → `meeting` | Unchanged: calendar consulted as before | Same as today |
| Non-scheduling mail | fyi/spam/newsletter, no scheduling verbs even if a date appears | No calendar consult; no Graph call | N/A |
| No draft requested | `include_draft=False` | No calendar consult (unchanged) | N/A |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/scheduling.py` -- `has_scheduling_intent(subject, body) -> bool` (Dutch+English scheduling keywords/phrases); reuses existing parsers.
- `apps/hub-api/app/services/analyze.py` -- broadened the meeting branch gate to also trigger on `has_scheduling_intent(...)`; broadened the `schedule` action to fire whenever `proposed_slots` exist (not only `category == "meeting"`).
- `apps/hub-api/app/services/inference.py` -- draft-injection gate: both draft paths (`_generate_draft` stub + vLLM) and `_apply_stub_availability` now honour `availability_prompt` regardless of `category`, so mislabeled scheduling mails still get concrete times in the draft.
- `tests/api/test_scheduling.py` -- cases for the detector and the broadened trigger.

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/scheduling.py` -- add `has_scheduling_intent(subject, body)` matching strong scheduling signals (meeting, call, afspraak, vergadering, uitnodiging, agenda, calendar, inplannen, "moment voorzien/vinden", "tijd vinden", beschikbaar(heid), availability, "past het/schikt", "let's meet") -- provides a label-independent trigger.
- [x] `apps/hub-api/app/services/analyze.py` -- gate now `if body.include_draft and (signals.category == "meeting" or has_scheduling_intent(loaded.subject, loaded.body)):`; `schedule` action fires when `proposed_slots` exist -- fires consult + exposes Schedule for mislabeled scheduling mails.
- [x] `apps/hub-api/app/services/inference.py` -- draft paths + `_apply_stub_availability` gate on `availability_prompt` presence instead of `category == "meeting"` -- required so the draft proposes concrete times (frozen Intent) even when the label isn't "meeting". (Stub `meeting_intent` keyword reuse deliberately skipped: `has_scheduling_intent` is broader, so not behavior-preserving; the analyze.py trigger already covers the case label-independently.)
- [x] `tests/api/test_scheduling.py` -- unit-test `has_scheduling_intent` (true/false cases incl. the screenshot mail; non-scheduling date mail is false) and that a scheduling mail classified non-`meeting` still yields proposed slots + draft availability + schedule action.

**Acceptance Criteria:**
- Given a scheduling mail the classifier labels `action_required`, when analyzed with `include_draft=True`, then the calendar is consulted and the suggestion carries `proposed_slots` (or an `availability_note` when blocked).
- Given a non-scheduling mail that merely mentions a date, when analyzed, then no calendar consult occurs.
- Given a mail classified `meeting`, when analyzed, then behavior is identical to before this change.

## Design Notes

The detector must be conservative to avoid needless Graph latency: match on scheduling verbs/nouns, not on the mere presence of a date. `parse_meeting_window`/`parse_duration_minutes` remain the source of the actual window once the consult fires. The displayed `category` is intentionally left unchanged (out of scope) — only the consult trigger widens.

## Verification

**Commands:**
- `source apps/hub-api/.venv/bin/activate && python -m pytest tests/api/test_scheduling.py -q` -- expected: all pass, incl. new intent/trigger cases.

## Suggested Review Order

**The trigger (why the calendar now fires)**

- Label-independent scheduling detector — conservative NL/EN verbs/nouns, not bare dates.
  [`scheduling.py:328`](../../apps/hub-api/app/services/scheduling.py#L328)
- Consult gate broadened: `category == "meeting"` OR scheduling intent.
  [`analyze.py:299`](../../apps/hub-api/app/services/analyze.py#L299)

**Draft + action must follow the consult**

- Draft paths honour `availability_prompt` regardless of category; forward intent still wins.
  [`inference.py:521`](../../apps/hub-api/app/services/inference.py#L521)
- Stub availability injection no longer gated on `category == "meeting"`.
  [`_apply_stub_availability:342`](../../apps/hub-api/app/services/inference.py#L342)
- `schedule` action offered whenever proposed slots exist.
  [`analyze.py:442`](../../apps/hub-api/app/services/analyze.py#L442)
- confirm-schedule accepts any suggestion with proposed slots (was meeting-only → fixed 422).
  [`schedule.py:124`](../../apps/hub-api/app/api/schedule.py#L124)

**Tests**

- Detector true/false cases + mislabeled scheduling mail still consults.
  [`test_scheduling.py:289`](../../tests/api/test_scheduling.py#L289)
