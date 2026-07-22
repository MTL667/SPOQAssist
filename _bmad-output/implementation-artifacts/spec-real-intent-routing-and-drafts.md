---
title: 'Real intent routing and drafts (no Contoso placeholders)'
type: 'bugfix'
created: '2026-07-22'
status: 'done'
baseline_commit: '283bf34097b9afc85651e39183ccac4aeb7166d7'
context:
  - '{project-root}/_bmad-output/planning-artifacts/prd.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** In Ollama/pilot mode, analyze still emits Contoso demo routes (`desk@contoso.com`) and the RoutePicker shows Contoso defaults. Category/route come from stub keyword heuristics, not the user’s mailbox profile or history—so suggestions look invented. There is also no clear intent split between “draft a reply”, “suggest forward”, and “meeting follow-up”.

**Approach:** Remove all Contoso product routes from hub + add-in. Keep stub Contoso only in automated tests as mailbox fixtures if needed. Drive route suggestions from learned `RoutingEdge` (and later real directory—not Contoso). Split analyze into intent-aware behavior: reply draft via instruct + history; forward only when a real learned/org route exists; meeting as category + reply language that proposes next steps—not Graph calendar booking in this change.

## Boundaries & Constraints

**Always:**
- Never return `@contoso.com` (or Contoso display names) as suggested routes in `INFERENCE_MODE=ollama` or any pilot path used by the Outlook add-in.
- Suggested routes must come only from learned routing edges for that mailbox (or empty / no route).
- Drafts remain written as the mailbox owner to the inbound sender (existing perspective rules).
- Mailbox history snippets stay scoped to `mailbox_profile_id`.
- No mailbox subject/body/tokens in logs.

**Ask First:**
- Wiring Microsoft Graph Calendar create/update event APIs.
- Hard-coding any real company shared mailboxes as default routes.
- Teaching/learning routes on personal mailboxes (today teach is shared-only).

**Never:**
- Keep Contoso as “helpful defaults” in RoutePicker for pilot users.
- Invent forward recipients from keywords alone.
- Implement full meeting booking / Teams invites in this change.
- Send outbound mail without existing confirm-outbound HITL.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Meeting mail, no learned route | Body mentions call/meeting; no RoutingEdge | `category=meeting`; `suggested_route=null`; draft (if history) proposes reply/slots as owner; actions include `reply` only | Draft timeout → short safe fallback reply |
| Explicit forward + learned route | Learned edge for sender pattern | `suggested_route` = learned email/name; actions may include `forward` + optional reply draft | Missing edge → no Contoso; route null |
| Keyword “forward/route”, stub mode CI | `INFERENCE_MODE=stub` | May use non-Contoso test doubles or null route—never Contoso in API JSON consumed by add-in | N/A |
| RoutePicker open | User clicks Change route | No Contoso list; free-text email entry and/or learned/prior edges only | Invalid email → disable select |
| Short mail + indexed history | Weak similarity | Still retrieve best history; draft allowed when history exists | If index empty → no draft, clear message |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/inference.py` -- Stub Contoso route; Ollama reuses stub for category/route; `_generate_draft`
- `apps/hub-api/app/services/analyze.py` -- builds `actions` from draft + route
- `apps/hub-api/app/services/retrieve.py` -- `lookup_learned_route` / retrieve snippets
- `apps/hub-api/app/api/feedback.py` -- teach / `RoutingEdge` writes (shared)
- `apps/outlook-addin/src/taskpane/components/RoutePicker.tsx` -- `DEFAULT_ROUTES` Contoso
- `apps/outlook-addin/src/taskpane/components/SuggestionReviewStack.tsx` -- draft empty copy
- `tests/api/test_analyze_feedback_confirm.py` -- analyze/route/learning assertions

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/inference.py` -- Remove Contoso keyword route; in ollama path derive category/priority without inventing recipients; add intent-aware draft prompt branches (reply / forward-ack / meeting follow-up) using `mailbox_email`, sender, learned route, snippets -- stop stub Contoso leaking into pilot
- [x] `apps/hub-api/app/services/analyze.py` -- Set `actions` from intent: `reply` when draft; `forward` only if real `suggested_route`; never invent route -- align API contract with product rules
- [x] `apps/outlook-addin/src/taskpane/components/RoutePicker.tsx` -- Remove Contoso defaults; support free-text recipient + optional remembered edges list if already available client-side -- picker must not offer fake domains
- [x] `tests/api/test_analyze_feedback_confirm.py` -- Assert no `@contoso.com` in suggestion routes for ollama/stub product path; meeting without learned route → null route; learned route still wins -- lock regression
- [x] Deploy hub changes to Mac Studio compose API after tests pass -- pilot validation (run after present commit)

**Acceptance Criteria:**
- Given a meeting sales mail with no learned route, when analyze runs in ollama mode, then `suggested_route` is null and no Contoso address appears in API or RoutePicker defaults.
- Given a shared-mailbox learned route for a sender pattern, when analyze runs, then that route is suggested and `forward` is available.
- Given indexed sent history, when analyze needs a reply, then draft is generated as mailbox owner to the inbound sender with intent-specific instructions (reply vs meeting follow-up).
- Given RoutePicker opens, when no query is entered, then Contoso desk/finance/hr options are absent.

## Design Notes

Ollama today calls Stub for classify/route then overlays draft. Keep a small heuristic classifier (category/priority) but **route_email must stay null unless `learned_route` is set**. Meeting = category + draft copy that proposes scheduling language; calendar Graph is out of scope.

Draft prompt branches (illustrative):
```
intent=meeting → reply proposing times; do not invent calendar holds
intent=forward_with_route → short ack + note you will forward to {route}
intent=reply → normal grounded reply
```

## Verification

**Commands:**
- `cd apps/hub-api && .venv/bin/pytest ../../tests/api/test_analyze_feedback_confirm.py -q` -- expected: all passed
- `rg -n "desk@contoso|finance@contoso|hr@contoso" apps/` -- expected: no matches outside tests/docs comments if any

**Manual checks (if no CLI):**
- Outlook analyze on 3CX/meeting mail → no Contoso route; draft as Kevin if history present
- Change route UI → no Contoso chips; can type a real email

## Suggested Review Order

**No invented routes**

- Learned edges only; Contoso keyword invent removed
  [`inference.py:127`](../../apps/hub-api/app/services/inference.py#L127)

- Contoso never persisted/returned on analyze response
  [`analyze.py:129`](../../apps/hub-api/app/services/analyze.py#L129)

- `forward` action only when a real route exists
  [`analyze.py:160`](../../apps/hub-api/app/services/analyze.py#L160)

**Intent-aware drafts**

- Meeting / forward-ack / reply prompt branches for Ollama
  [`inference.py:300`](../../apps/hub-api/app/services/inference.py#L300)

**RoutePicker**

- Free-text email; Contoso defaults gone; priors filtered
  [`RoutePicker.tsx:10`](../../apps/outlook-addin/src/taskpane/components/RoutePicker.tsx#L10)

**Tests**

- Meeting/forward without learned route → null Contoso-free route
  [`test_analyze_feedback_confirm.py:50`](../../tests/api/test_analyze_feedback_confirm.py#L50)

- Learned non-Contoso route still enables `forward`
  [`test_analyze_feedback_confirm.py:219`](../../tests/api/test_analyze_feedback_confirm.py#L219)
