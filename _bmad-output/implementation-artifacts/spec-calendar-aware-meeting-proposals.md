---
title: 'Calendar-aware meeting proposals and schedule action'
type: 'feature'
created: '2026-07-24'
status: 'done'
baseline_commit: '3237dc76c0b1a488d97b35ada92e9973c86084d2'
context:
  - '{project-root}/docs/graph-scopes.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When mail asks to schedule a meeting/appointment, SpoqSense drafts time proposals without checking the mailbox owner's Outlook calendar, so it can suggest times when the user is busy (e.g. vacation). There is also no way to create the Outlook appointment from the suggestion.

**Approach:** Only for meeting/appointment intent, consult the owner's calendar before drafting; propose free times in office hours (or before/after a blocked window). Expose an explicit Schedule action that creates a Graph calendar event with invitees and subject from the mail.

## Boundaries & Constraints

**Always:**
- Trigger only when classification category is `meeting` (or equivalent appointment-scheduling intent). Non-meeting mail must not call calendar APIs.
- Consult the **mailbox profile owner** calendar (signed-in user / OBO identity), not arbitrary colleagues' calendars.
- Office hours: Mon–Fri **09:00–17:00 Europe/Brussels**. Default proposed duration **60 minutes** unless the mail states another length.
- Draft may propose free times; never claim a hold is already booked, never invent Teams links, never auto-create events on analyze.
- If the requested window is fully busy/blocked (e.g. vacation through a deadline), the draft must say the owner is unavailable in that window and propose concrete times **before and/or after** the block, still within office hours.
- Schedule button creates one Outlook event: organizer = owner; attendees = sender + relevant recipients from the mail; subject/theme from the mail (subject + short purpose); start/end = chosen proposed time (or first proposed if UI does not pick).
- Human must click Schedule (confirm pattern like send/forward). Fail closed on missing Calendar consent (`CONSENT_REQUIRED` / `BAD_SCOPES`).
- Hub-only Graph OBO; add Graph calendar scopes to hub config + docs; Entra admin consent required on each entity app.

**Ask First:**
- Changing office-hours policy, default duration, or auto-booking without a button.
- Scheduling on behalf of a shared mailbox identity if product rules differ from personal OBO.
- Inviting external attendees beyond To/Cc/From of the analyzed message.

**Never:**
- Calendar reads/writes for FYI / action_required / route-only mail.
- Silent event creation during analyze or Accept-as-send.
- Storing full calendar dumps in the hub DB (ephemeral consult for the request only).
- Putting Graph calendar tokens or secrets in the Outlook add-in.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Free times in window | Meeting mail asks for a moment before date D; owner free in range | Draft proposes 2–3 concrete free times in office hours; `proposed_slots` populated; Schedule enabled | N/A |
| Blocked window (vacation) | Requested range fully busy through D | Draft states unavailable in that block; proposes times before and/or after block in office hours | N/A |
| Non-meeting mail | category ≠ meeting | No calendar Graph calls; no Schedule button | N/A |
| Calendar consent missing | Meeting + OBO without Calendars.* | Draft falls back without invented holds; why-code notes calendar unavailable; Schedule returns consent error | `CONSENT_REQUIRED` / `BAD_SCOPES` |
| Schedule click | User picks/confirms a proposed slot | Graph event created; attendees + subject from mail; success ack in UI | Graph failure → clear error, no partial claim of success |
| Stub Graph mode | `GRAPH_MODE=stub` | Deterministic free/busy fixture; Schedule stub creates fake event id | N/A |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/analyze.py` -- after classify, before draft: meeting-only calendar consult; inject availability into draft pass; timings
- `apps/hub-api/app/services/inference.py` -- meeting draft prompts: use provided free times / unavailability; keep no-invented-hold guard
- `apps/hub-api/app/services/mail_graph.py` -- OBO token; add getSchedule/calendarView + create event (or sibling calendar module)
- `apps/hub-api/app/services/scheduling.py` -- NEW: office-hours free windows, blocked-range before/after proposals
- `apps/hub-api/app/core/config.py` + `docs/graph-scopes.md` -- add `Calendars.Read` + `Calendars.ReadWrite` (or minimal equivalent)
- `apps/hub-api/app/domain/schemas.py` -- `proposed_slots`, availability note; schedule request/response
- `apps/hub-api/app/api/confirm.py` or new schedule route -- human-gated create event (do not overload send/forward)
- `apps/outlook-addin/src/taskpane/components/*Feedback*` + `App.tsx` -- Schedule button for meeting suggestions
- `apps/outlook-addin/src/taskpane/api/client.ts` + mappers/`paneState.ts` -- schedule API + slots
- `tests/api/test_analyze_feedback_confirm.py` + new scheduling tests -- matrix coverage via stub Graph

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/core/config.py` + `docs/graph-scopes.md` -- add calendar scopes to defaults/docs -- Entra consent path
- [x] `apps/hub-api/app/services/mail_graph.py` (+ stub) -- free/busy query + create event over OBO -- Graph surface
- [x] `apps/hub-api/app/services/scheduling.py` -- Brussels office-hours slot finder + blocked-window before/after -- pure logic
- [x] `apps/hub-api/app/services/analyze.py` + `inference.py` + schemas -- meeting-only consult → draft context + `proposed_slots` -- quality proposals
- [x] Hub schedule API + enums -- confirm-style create event from suggestion + chosen slot -- no auto-book
- [x] Outlook add-in Feedback/App/client/mappers -- Schedule button when meeting + slots present -- user action
- [x] `tests/api/*` -- unit-test I/O matrix (free, blocked, non-meeting no-call, consent, stub schedule) -- regression

**Acceptance Criteria:**
- Given a meeting-intent mail with a deadline window and free calendar time, when analyze runs with draft, then the draft names concrete free times inside office hours and does not claim a booking exists.
- Given the requested window is fully blocked, when analyze drafts, then copy states unavailability for that block and proposes times before and/or after it in office hours.
- Given non-meeting mail, when analyze runs, then no calendar Graph endpoints are called and Schedule is hidden.
- Given a meeting suggestion with proposed slots, when the user confirms Schedule, then Graph creates one event with mail-derived attendees and theme and the UI reports success.
- Given missing Calendar consent, when Schedule is attempted (or consult fails closed), then the user sees a consent/scopes error and no false “scheduled” state.

### Review Findings

_Code review 2026-07-24 (blind + edge + acceptance layers)._

- [x] [Review][Decision] Shared-mailbox calendar consult uses `mailbox_email` — RESOLVED: allow shared-mailbox calendar (consult + create) same as personal; no gating [`schedule.py`, `mail_graph.py`]
- [x] [Review][Patch] Attendee allowlist bypass — `if extra and allowed:` skips check when allowed empty; also cap attendee count [`schedule.py:145`]
- [x] [Review][Patch] Duplicate event risk — Graph create succeeds but `complete_idempotency` failure leaves orphan reservation; retry advice creates second event [`schedule.py:244`]
- [x] [Review][Patch] Slot end>start validation runs after `reserve_idempotency` — failure poisons the key [`schedule.py`]
- [x] [Review][Patch] No past-slot guard — stale/replayed slot can create an event in the past [`schedule.py`]
- [x] [Review][Patch] Dead redundant first-slot match block after the loop [`schedule.py:117`]
- [x] [Review][Patch] No-op `if not subject...: pass` dead branch [`schedule.py:180`]
- [x] [Review][Patch] Fingerprint includes server-derived subject → spurious 409 when subject differs across retries [`schedule.py:168`]
- [x] [Review][Patch] getSchedule sends offset dateTime (`.replace("Z","")` keeps `+02:00`) with explicit timeZone — use `_graph_local_datetime` [`mail_graph.py:823`]
- [x] [Review][Patch] Busy path `resp.json()` unguarded for non-JSON 2xx [`mail_graph.py`]
- [x] [Review][Patch] calendarView pagination loop has no page cap [`mail_graph.py`]
- [x] [Review][Patch] Deadline regex matches ratios like `24/7` as a date [`scheduling.py:170`]
- [x] [Review][Patch] Duration parser matches unrelated `in 2 hours` / `within 30 minutes` as meeting length [`scheduling.py:225`]
- [x] [Review][Patch] Blocked-window side search can propose slots beyond fetched busy horizon — widen busy fetch pad [`analyze.py:299`, `scheduling.py`]
- [x] [Review][Defer] Hardcoded Europe/Brussels for all mailboxes (per-spec for pilot; multi-tz post-pilot)
- [x] [Review][Defer] UI books first slot only + attendee preview shows "mail participants" placeholder (slot picker deferred)

## Spec Change Log

## Design Notes

- Reuse OBO + confirm-outbound human-gate pattern; Schedule is a separate mutation from send/forward.
- Prefer Graph `getSchedule` / calendarView for busy intervals; compute free windows locally in `scheduling.py`.
- Golden: mail “moment vóór 31/8 voor opleiding” + owner busy 1–31 Aug → draft declines that window and offers late July / early September office-hour times; Schedule creates “Inventaris … opleiding” with Lieselot + thread attendees.

## Verification

**Commands:**
- `apps/hub-api/.venv/bin/python -m pytest tests/api/test_analyze_feedback_confirm.py tests/api/test_scheduling.py -q` -- expected: pass (create `test_scheduling.py` as needed)
- Manual: Entra grant Calendars scopes; analyze Lieselot-style mail; confirm draft times vs Outlook calendar; Schedule creates correct event

## Suggested Review Order

**Pipeline entry**

- Meeting-only calendar consult before draft; persist slots envelope
  [`analyze.py:294`](../../apps/hub-api/app/services/analyze.py#L294)

**Office-hours logic**

- Free-slot finder + blocked window before/after proposals
  [`scheduling.py:306`](../../apps/hub-api/app/services/scheduling.py#L306)

- Explicit duration parse from mail (hours/minutes)
  [`scheduling.py:225`](../../apps/hub-api/app/services/scheduling.py#L225)

**Graph calendar**

- OBO busy query with getSchedule + paginated calendarView fallback
  [`mail_graph.py:823`](../../apps/hub-api/app/services/mail_graph.py#L823)

- Human-gated event create + attendee allowlist + idempotency
  [`schedule.py:84`](../../apps/hub-api/app/api/schedule.py#L84)

**Add-in**

- Schedule opens confirm dialog (not one-click create)
  [`App.tsx:641`](../../apps/outlook-addin/src/taskpane/App.tsx#L641)

- Schedule button gated on meeting + proposed slots
  [`FeedbackControls.tsx:53`](../../apps/outlook-addin/src/taskpane/components/FeedbackControls.tsx#L53)

**Config / tests**

- Default Calendars.Read + ReadWrite scopes
  [`config.py:85`](../../apps/hub-api/app/core/config.py#L85)

- Matrix coverage for free/blocked/non-meeting/schedule
  [`test_scheduling.py:45`](../../tests/api/test_scheduling.py#L45)
