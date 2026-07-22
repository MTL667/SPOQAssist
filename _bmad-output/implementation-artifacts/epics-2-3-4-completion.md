---
status: review
epics: [2, 3, 4]
---

# Epics 2–4 completion notes

## Verification

- `pytest`: 27 passed (auth, entitlement, connect, ops, analyze/feedback/confirm, learning, admin-blind, retention)
- `npm run build` (outlook-addin): success

## Epic 2

- Pane state machine + empty select state + SPOQ theme
- Analyze API with attachment warnings; index `vector(1024)` embeddings (JSON in sqlite / 1024-d pin)
- Stub + Ollama inference clients (`INFERENCE_MODE`)
- UI: AnalyzingState, SuggestionHero, SuggestionReviewStack, WhyExplanation

## Epic 3

- FeedbackControls Accept/Edit/Reject (Accept ≠ send)
- ConfirmOutboundDialog + `confirm-outbound` idempotency + AI disclosure footer
- RoutePicker + teach → routing_edges (shared)
- feedback_events + audit_events

## Epic 4

- Admin AI settings shared-only; personal admin denied (CI tests)
- Shared delegate analyze path (same Outlook pane)
- Concurrent-safe: no exclusive locks; audit per actor_oid; idempotent confirm
- Retention policy + purge job
- `docs/processing-access-register.md`
- OpsHealthStatus + `/v1/ops/health_detail` inference hints (no mail bodies)

## Studio follow-ups (real E2E)

1. `INFERENCE_MODE=ollama` with pinned Qwen models
2. `GRAPH_MODE=obo` + Entra secrets on hub
3. Set add-in `localStorage.spoq_access_token` + `spoq_mailbox_profile_id` (SSO wiring next)
4. Postgres pgvector column type migration when leaving sqlite/JSON storage
