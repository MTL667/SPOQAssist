---
title: 'Rebrand user-facing strings SpoqAssist → SpoqSense'
type: 'chore'
created: '2026-07-22'
status: 'done'
baseline_commit: '39732a94a355b5cbecb44f1d41bcc6df8c12b223'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The product and Entra app are SpoqSense, but Outlook UI, manifest labels, hub-facing copy, AI disclosure, and pilot runbooks still say SpoqAssist—confusing for users and IT during sideload.

**Approach:** Replace user-visible “SpoqAssist” branding with “SpoqSense” in the Outlook add-in, outbound AI disclosure text, hub health/OpenAPI display names, and pilot-facing runbooks. Do **not** rename the repo, GitHub remote, Docker Compose project, package names, or DB identifiers in this change.

## Boundaries & Constraints

**Always:**
- User-visible product name = **SpoqSense** (Outlook tab/button, pane titles, unavailable/checking copy, AI disclosure).
- Keep technical keys unchanged: `spoq_access_token`, `spoqassist` compose project, package `name` fields, DB name/URL path segments, folder `SpoqAssist`, GitHub `SPOQAssist`.
- Entra App ID URI / Resource stay as configured (`api://localhost:3000/{client-id}`)—branding only, not auth rewiring.
- After manifest DisplayName change, sideload/reload may be required for Outlook to show the new ribbon label.

**Ask First:**
- Renaming the git repo / GitHub repository / local folder.
- Changing Docker Compose project name or database name.
- Renaming npm/Python package identifiers.

**Never:**
- Break SSO by changing `WebApplicationInfo` Resource/Id as part of rebrand.
- Mass-edit historical BMAD planning artifacts (`_bmad-output/planning-artifacts/*`) in this pass (defer).
- Invent a new logo/icon set (text rebrand only unless assets already say SpoqSense).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Outlook ribbon / pane | Sideloaded manifest + taskpane | Labels/titles show SpoqSense | Reload/sideload if Outlook caches old DisplayName |
| Hub down | Health fail | “SpoqSense unavailable” copy | Retry unchanged |
| AI-assisted send | Confirm outbound | Disclosure mentions SpoqSense | N/A |
| GET /health | Ops/IT | `service` display string uses spoqsense branding | N/A |

</frozen-after-approval>

## Code Map

- `apps/outlook-addin/manifest.xml` -- DisplayName, GroupLabel, button label/tooltip
- `apps/outlook-addin/src/taskpane/App.tsx` -- Title3, Checking…, LAN unavailable message
- `apps/outlook-addin/src/taskpane/components/HubUnavailable.tsx` -- unavailable title/body
- `apps/outlook-addin/src/taskpane/components/ConfirmOutboundDialog.tsx` -- AI disclosure
- `apps/outlook-addin/src/taskpane/taskpane.html` -- `<title>`
- `apps/hub-api/app/services/mail_graph.py` -- outbound AI disclosure footer
- `apps/hub-api/app/main.py` -- FastAPI title/description/root service label
- `apps/hub-api/app/api/health.py` (+ `admin_ops.py` if mirrored) -- `service` field
- `docs/runbooks/*.md` -- pilot-facing SpoqAssist mentions (sideload, hub-unavailable, SSO, central deploy)

## Tasks & Acceptance

**Execution:**
- [x] `apps/outlook-addin/manifest.xml` + taskpane UI strings -- SpoqAssist → SpoqSense -- ribbon/pane brand
- [x] `apps/hub-api` user-visible strings (disclosure, OpenAPI title, health `service`) -- SpoqSense -- hub-facing brand
- [x] `docs/runbooks/` pilot docs -- SpoqAssist → SpoqSense where product name appears; leave path examples like `/path/to/SpoqAssist` as folder path -- ops consistency
- [x] Grep `apps/` + `docs/runbooks/` for remaining user-facing `SpoqAssist` -- expected none (except intentional path/repo notes)

**Acceptance Criteria:**
- Given the sideloaded add-in, when Outlook shows the message command, then the label/tooltip/pane title read SpoqSense.
- Given hub unavailable or checking, when the pane renders status copy, then it says SpoqSense (not SpoqAssist).
- Given AI-assisted outbound, when disclosure is applied, then the text names SpoqSense.
- Given repo/package/compose identifiers, when inspected, then they still use existing `spoqassist` / `SpoqAssist` technical names.

## Spec Change Log

## Verification

**Commands:**
- `rg -n "SpoqAssist" apps/ docs/runbooks/` -- expected: only path/repo notes if any; no UI/disclosure hits
- Manual: reload Outlook taskpane / re-sideload manifest if ribbon label stale

## Suggested Review Order

**Outlook brand**

- Manifest DisplayName / ribbon strings
  [`manifest.xml:11`](../../apps/outlook-addin/manifest.xml#L11)

- Pane title + checking/unavailable copy
  [`App.tsx:425`](../../apps/outlook-addin/src/taskpane/App.tsx#L425)

**Hub-facing brand**

- Outbound AI disclosure footer
  [`mail_graph.py:19`](../../apps/hub-api/app/services/mail_graph.py#L19)

- Health `service` label
  [`health.py:11`](../../apps/hub-api/app/api/health.py#L11)
