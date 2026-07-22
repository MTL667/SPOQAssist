---
title: 'Mailbox profile inspector (Check profiel + behavior summary)'
type: 'feature'
created: '2026-07-22'
status: 'done'
baseline_commit: '262bb060c848bc21497bb311c367ec4fcba3b365'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-mailbox-history-profile-lifecycle.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Users cannot see what mailbox profile SpoqSense built, and switching mail feels like a new profile is created. There is also no human-readable summary of learned style/routing (“this user replies like X; finance goes to Y”).

**Approach:** Add a bottom **Check profiel** control that opens an inspector for the current mailbox profile: identity + sync stats + learned routes + a hub-generated behavior summary. Prove the same `mailbox_profile_id` is reused across mail selection (fix reconnect churn if found).

## Boundaries & Constraints

**Always:**
- Inspector is entitlement-gated for the current mailbox owner/delegate (same gate as analyze).
- Show: profile id (short), mailbox email, kind, connection status, history status, chunk count, distinct indexed Sent count if available, last sync time, sync error if any, learned routing edges (pattern → route).
- Behavior summary is generated **on the hub** from indexed chunks + routing edges via local Ollama; return short prose only (Dutch OK if mailbox content is Dutch).
- Selecting a different mail in the same mailbox must **not** create a new profile; inspector must show a stable id across selections.
- Never send mailbox content to external LLM APIs.

**Ask First:**
- Persisting the behavior summary in Postgres vs generate-on-open only.
- Exposing raw sample Sent excerpts in the UI (default: no — summary text only).

**Never:**
- Return raw `mail_chunks.chunk_text` / embeddings to the add-in.
- Admin visibility into personal mailbox inspector data.
- LoRA / separate fine-tune; RAG + edges + summary text only.
- Blocking analyze on summary generation.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Check profiel, ready profile | Cached profile id, history ready, some chunks | Panel shows metadata + routes + summary prose | N/A |
| Check profiel, empty history | Profile exists, 0 chunks | Metadata + empty routes; summary explains no history yet | No invent facts |
| Mail A → Mail B same mailbox | Two analyzes | Same `mailbox_profile_id` in inspector | If id changes → bug, fix reconnect |
| No routes learned | Personal mailbox, no teach edges | Routes section empty/clear copy | N/A |
| Summary model down | Ollama instruct unavailable | Metadata + routes still shown; summary error + Retry | No fake persona |
| Hub/profile 404 | Stale cached id | Clear message; allow reconnect without silent duplicate chaos | Surface error |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/api/mailbox_profiles.py` -- GET profile today; extend or add inspect endpoint
- `apps/hub-api/app/domain/schemas.py` -- `MailboxProfileOut` (no routes/summary yet)
- `apps/hub-api/app/domain/models.py` -- `MailboxProfile`, `MailChunk`, `RoutingEdge`
- `apps/hub-api/app/db/repositories/ai_store.py` -- chunk count / indexed ids
- `apps/hub-api/app/services/learning.py` / `retrieve.py` -- edge upsert / single lookup (no list yet)
- `apps/hub-api/app/services/inference.py` -- local instruct generate for summary
- `apps/outlook-addin/src/taskpane/api/auth.ts` -- `spoq_mailbox_profile_id` / email cache
- `apps/outlook-addin/src/taskpane/App.tsx` -- `ensureSession` connect-only-if-missing; mail change → analyze
- `apps/outlook-addin/src/taskpane/api/client.ts` -- `fetchMailboxProfile` (partial fields)
- `tests/api/test_analyze_feedback_confirm.py` -- existing profile/sync patterns

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/domain/schemas.py` + `mailbox_profiles.py` (+ repo helpers) -- Entitlement-gated inspect payload: profile fields, history stats, `routes[]`, `behavior_summary` (+ optional `regenerate`) -- one read model for UI
- [x] `apps/hub-api/app/services/profile_inspect.py` (+ `inference.py` hook) -- List edges; sample chunks hub-side; generate short behavior summary; never leak chunk bodies in API -- persona text without dumping mail
- [x] `apps/outlook-addin/src/taskpane/components/CheckProfilePanel.tsx` + `App.tsx` + `client.ts` -- Bottom **Check profiel** button; panel shows all fields + summary; stable id visible; Retry on summary failure -- user trust surface
- [x] `apps/outlook-addin/src/taskpane/App.tsx` (+ auth cache if needed) -- Audit mail-selection path; ensure no spurious connect/new profile; harden stale-id 404 → reconnect -- kill recreate illusion/bugs
- [x] `tests/api/test_profile_inspect.py` (or extend existing) -- Inspect returns stable profile + routes; summary absent/error safe when no model; connect upsert does not duplicate -- lock I/O matrix

**Acceptance Criteria:**
- Given a ready mailbox profile, when the user taps **Check profiel**, then they see identity, sync stats, learned routes, and a short behavior summary without raw Sent bodies.
- Given two different selected mails in the same mailbox, when the user opens the inspector each time, then the displayed profile id is unchanged.
- Given Ollama unavailable, when the user opens the inspector, then metadata/routes still render and summary shows a retryable error.
- Given no history chunks, when the user opens the inspector, then the UI states that no style profile exists yet and does not invent habits.

## Spec Change Log

## Design Notes

Behavior summary is **derived**, not a separate training artifact. Golden shape (illustrative):

```
Mailbox: kevin@example.com (personal)
Style: short Dutch replies, signs with first name, confirms next steps.
Routing: sender*@finance.partner → finance@company.com (weight 3)
History: 180 Sent chunks · last sync 2026-07-22T18:00Z · status ready
```

Generate from top routing edges + a small sample of chunk texts on the hub only. Default: generate on inspect open; if latency hurts, cache summary text with timestamp on the profile after Ask First.

## Verification

**Commands:**
- `pytest tests/api/test_profile_inspect.py -q` (or targeted file) -- expected: pass
- Add-in TypeScript build / existing lint if present -- expected: no new errors

**Manual checks:**
- Open add-in → Check profiel → note id → switch mail → Check again → same id
- Confirm summary mentions tone/routing without pasting full Sent mails

## Suggested Review Order

**Inspect API**

- Sync inspect endpoint — avoids blocking the asyncio loop during Ollama summary
  [`mailbox_profiles.py:104`](../../apps/hub-api/app/api/mailbox_profiles.py#L104)

- Assembles stats, capped routes, and hub-only summary (no chunk bodies out)
  [`profile_inspect.py:23`](../../apps/hub-api/app/services/profile_inspect.py#L23)

- Local instruct summarizer; samples stay server-side
  [`inference.py:451`](../../apps/hub-api/app/services/inference.py#L451)

**Stable mailbox identity**

- Never use selected-mail From: as profile key (stops “new profile” feel)
  [`App.tsx:251`](../../apps/outlook-addin/src/taskpane/App.tsx#L251)

**Add-in inspector UI**

- Bottom Check profiel + load/retry with race guard
  [`App.tsx:665`](../../apps/outlook-addin/src/taskpane/App.tsx#L665)

- Panel keeps metadata visible while summary reloads
  [`CheckProfilePanel.tsx:41`](../../apps/outlook-addin/src/taskpane/components/CheckProfilePanel.tsx#L41)

**Tests**

- Stable id, routes+summary, skipped summary, model-down keeps metadata
  [`test_profile_inspect.py:20`](../../tests/api/test_profile_inspect.py#L20)
