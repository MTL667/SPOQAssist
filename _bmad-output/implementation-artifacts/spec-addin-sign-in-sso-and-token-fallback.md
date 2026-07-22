---
title: 'Add-in sign-in: Office SSO errors + paste-token fallback'
type: 'feature'
created: '2026-07-22'
status: 'done'
baseline_commit: 'a8d6bac2e41204ef324bcaea701b78d891be55ea'
context:
  - '{project-root}/docs/runbooks/office-sso-setup.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Outlook add-in reaches the hub and shows profile sync, but analyze is blocked with a generic “Sign-in required” message. Office SSO (`Office.auth.getAccessToken`) fails silently, and there is no in-pane way to set the sideload `spoq_access_token` fallback.

**Approach:** Surface a clear SSO failure reason (code/message, never the token). Keep trying Office SSO first. Add a small sign-in panel to paste/save/clear a hub Bearer token in `localStorage` for sideload/pilot. Verify manifest `WebApplicationInfo` + hub audience alignment; fix only add-in/auth UX issues found—do not invent new auth protocols.

## Boundaries & Constraints

**Always:**
- Never log or display the raw access token (mask when showing “token saved”).
- Acquisition order: Office SSO → stored `spoq_access_token` → sign-in panel.
- Hub still validates Entra JWT (audience/issuer); paste fallback must be a real access token for `ENTRA_API_AUDIENCE`.
- Dutch/English UI can stay English for this pane unless Dutch already used nearby; prefer short clear English matching current pane copy, or Dutch if adjacent strings are Dutch.
- Manifest Resource / hub `ENTRA_API_AUDIENCE` remain `api://localhost:3000/{client-id}` for this pilot host.

**Ask First:**
- Changing Entra app registration (new scopes, redirect URIs, production Resource host).
- Disabling JWT validation or adding a hub “dev bypass” auth mode.
- Storing refresh tokens or client secrets in the add-in.

**Never:**
- Hard-code a personal access token in the repo or manifest.
- Treat SSO failure as success with an empty Bearer.
- Build a full OAuth SPA login flow outside Office SSO + paste fallback.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| SSO success | `getAccessToken` returns JWT | Analyze/connect proceed; no paste panel required | N/A |
| SSO fails, no stored token | Office error / null | Show sign-in panel + SSO reason (e.g. 13001); paste field enabled | Retry SSO button |
| Valid pasted token | User saves JWT to localStorage | Token stored; panel dismisses; ensureSession succeeds | Invalid/empty → disable save |
| Clear token | User clears stored token | localStorage key removed; SSO retried | If SSO still fails, panel returns |
| Hub rejects token | 401 from API | Show auth error without dumping token; keep paste option | User can re-paste |

</frozen-after-approval>

## Code Map

- `apps/outlook-addin/src/taskpane/api/auth.ts` -- SSO swallowed in empty catch; `spoq_access_token` read-only helper
- `apps/outlook-addin/src/taskpane/App.tsx` -- generic sign-in error string; no paste UI
- `apps/outlook-addin/manifest.xml` -- `WebApplicationInfo` Id/Resource/scopes already present
- `docs/runbooks/office-sso-setup.md` -- setup + localStorage fallback notes
- `apps/hub-api/app/core/security.py` -- Entra JWT validation (audience must match)

## Tasks & Acceptance

**Execution:**
- [x] `apps/outlook-addin/src/taskpane/api/auth.ts` -- Return structured SSO result/error; add set/clear/has helpers for `spoq_access_token` (never log token) -- enable diagnosable SSO + safe storage
- [x] `apps/outlook-addin/src/taskpane/components/SignInPanel.tsx` (new) -- SSO retry + error text + paste/save/clear token UI -- sideload path without DevTools
- [x] `apps/outlook-addin/src/taskpane/App.tsx` -- When no token, render SignInPanel instead of dead-end string; after save, continue ensureSession/analyze -- wire UX
- [x] `docs/runbooks/office-sso-setup.md` -- Document common SSO error codes + paste UI steps -- pilot ops
- [x] Manual verify against hub audience / manifest Resource alignment; fix only add-in-side mismatches found -- SSO can succeed when Entra allows it (Resource == hub audience)

**Acceptance Criteria:**
- Given Office SSO fails, when the taskpane needs auth, then the user sees a specific SSO error reason (not only “Sign-in required”) and a paste-token form.
- Given a valid hub-audience access token is pasted and saved, when Analyze runs, then the hub accepts the Bearer and mailbox connect/analyze can proceed.
- Given SSO later succeeds, when the pane acquires a token, then the paste panel is not required.
- Given a token is cleared, when the user returns to the pane, then auth is required again via SSO or paste.

## Spec Change Log

## Design Notes

Office SSO errors often expose `code` / `message` on the thrown object (e.g. 13001 identity, 13005 resource). Capture `String(err?.code || err?.name || "")` and a short message—never `err.stack` with tokens.

Paste UI sketch:

```
[Office SSO failed: 13001 — …]
[ Retry SSO ]
Paste hub access token:
[____________________] [Save] [Clear]
```

## Verification

**Commands:**
- Manual / webpack compile — expected: add-in builds without TS errors

**Manual checks (if no CLI):**
- Reload taskpane → SSO fail shows code; paste valid token → Analyze works
- Clear token → sign-in panel returns

## Suggested Review Order

**Token acquisition**

- Structured SSO result + safe error text (never raw JWT)
  [`auth.ts:32`](../../apps/outlook-addin/src/taskpane/api/auth.ts#L32)

**Sign-in UI**

- Retry SSO + paste/save/clear sideload token
  [`SignInPanel.tsx:1`](../../apps/outlook-addin/src/taskpane/components/SignInPanel.tsx#L1)

- Show panel when auth missing; continue after save
  [`App.tsx:415`](../../apps/outlook-addin/src/taskpane/App.tsx#L415)

**Ops**

- SSO error codes + paste steps for pilot
  [`office-sso-setup.md:1`](../../docs/runbooks/office-sso-setup.md#L1)
