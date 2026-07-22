---
title: 'No forward suggestion without real route (directed mail → reply)'
type: 'bugfix'
created: '2026-07-22'
status: 'done'
baseline_commit: 'bc5800a4e85ff42d1bac22f38875d5cc7861902d'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-real-intent-routing-and-drafts.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** For a directed question to the mailbox owner (e.g. Lieselot → Kevin with concrete asks), the high-confidence hero shows **forward** as the suggested action. That comes from keyword category labeling (`category=forward`) even when **no** `RoutingEdge` / `suggested_route` exists—so the UI implies “doorsturen” incorrectly.

**Approach:** Never present forward as the primary suggested action unless a real suggested route exists. Keyword “forward/doorsturen” may still appear in `why` as a hint, but category/primary action for unrouted mail must be reply/action_required (not forward). Hero/review UI should label the action from `actions` + route presence, not raw category strings like `forward`.

## Boundaries & Constraints

**Always:**
- `actions` may include `forward` only when `suggested_route` is non-null (existing API rule stays).
- Primary UI label for high-confidence hero: `forward` only if route exists; otherwise `reply` (or category like `action_required` / `meeting` / `invoice` if those apply).
- Do not invent Contoso or other recipients.
- Directed-to-owner mail (To/recipient is the connected mailbox, or clear second-person asks) defaults to reply path when no learned route.

**Ask First:**
- Auto-teaching routes from personal mailbox feedback.
- Graph directory lookup for forward targets.

**Never:**
- Show “Suggested action: forward” with high confidence when `suggested_route` is null.
- Use substring keywords alone to set primary action to forward without a route.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Directed ask, no RoutingEdge | Body has tasks for owner; no learned route | Hero: reply (or action_required), not forward; no route line | N/A |
| Keyword doorsturen, no route | Body mentions doorsturen; no edge | Category ≠ forward as primary; why may note forward_unknown; actions without forward | N/A |
| Learned route exists | RoutingEdge for sender | suggested_route set; forward allowed in actions + UI | N/A |
| Meeting mail, no route | meeting keywords | category=meeting; still not forward | N/A |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/inference.py` -- sets `category=forward` from keywords without requiring learned route
- `apps/hub-api/app/services/analyze.py` -- builds actions from draft + route
- `apps/outlook-addin/src/taskpane/components/SuggestionHero.tsx` -- shows `suggestion.category` as suggested action
- `apps/outlook-addin/src/taskpane/App.tsx` -- Accept uses route⇒forward else send
- `tests/api/test_analyze_feedback_confirm.py` -- forward/route assertions

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/inference.py` -- Do not set `category="forward"` unless `learned_route` is present; keep forward_intent only in why when unrouted -- stop false primary forward
- [x] `apps/outlook-addin/src/taskpane/components/SuggestionHero.tsx` (+ review stack if needed) -- Display primary action from route/actions (`forward` vs `reply`), never show bare `forward` category without route -- UI matches product rules
- [x] `tests/api/test_analyze_feedback_confirm.py` -- Keyword-forward body without learned route → category not forward / no forward action; with learned route → forward remains -- regression lock

**Acceptance Criteria:**
- Given a directed owner question with no learned route, when analyze returns, then the hero does not show forward as the suggested action and `actions` does not include forward.
- Given a learned route for the sender, when analyze returns, then forward may still be suggested with that route.
- Given keyword “doorsturen” without a route, when analyze returns, then why may explain route unknown, but primary action is reply/action_required.

## Spec Change Log

## Verification

**Commands:**
- `cd apps/hub-api && .venv/bin/pytest ../../tests/api/test_analyze_feedback_confirm.py -q` -- expected: all passed

**Manual checks:**
- Re-analyze Lieselot→Kevin mail → hero shows reply/action, not forward

## Suggested Review Order

- Category forward only with learned route
  [`inference.py:129`](../../apps/hub-api/app/services/inference.py#L129)

- Hero action label from route, not bare category
  [`SuggestionHero.tsx:22`](../../apps/outlook-addin/src/taskpane/components/SuggestionHero.tsx#L22)
