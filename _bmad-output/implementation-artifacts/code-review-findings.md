# Code review findings — Epics 1–4 + SSO

Date: 2026-07-22  
Updated: 2026-07-22 (patches applied)

## Decisions (resolved)

- [x] D1 Fail-closed on OBO Graph read
- [x] D2 Shared via Office shared context when available
- [x] D3 Keep unauthenticated ops health_detail (Tailscale trust)
- [x] D4 Retention shared-admin only

## Review Findings

### Decision needed — resolved

- [x] [Review][Decision] Graph read failure → fail-closed in OBO
- [x] [Review][Decision] Shared mailbox → Office shared context detection
- [x] [Review][Decision] ops health_detail → keep as-is
- [x] [Review][Decision] Personal retention → keep shared-admin only

### Patch — applied

- [x] [Review][Patch] Prevent mailbox reconnect ownership steal
- [x] [Review][Patch] Bind confirm-outbound to suggestion + disclosure always
- [x] [Review][Patch] Shared Graph paths via `/users/{id}` when shared
- [x] [Review][Patch] Prove shared mailbox mail access on connect
- [x] [Review][Patch] Idempotency fingerprint + reserve before Graph send
- [x] [Review][Patch] Add-in reuse idempotency_key until success
- [x] [Review][Patch] Scope ops connector config to principal.tenant_id
- [x] [Review][Patch] Enforce SharedAiSettings.enabled on analyze
- [x] [Review][Patch] Default GRAPH_SCOPES include Mail.Send
- [x] [Review][Patch] Block Accept without real recipients
- [x] [Review][Patch] Cap index batch size (100)
- [x] [Review][Patch] Retention purges routing_edges
- [x] [Review][Patch] Single ItemChanged handler (no stack)
- [x] [Review][Patch] Revalidate cached mailbox_profile_id vs Office email
- [x] [Review][Patch] Attachment byte limit via Graph size
- [x] [Review][Patch] Validate confirm recipients
- [x] [Review][Patch] Catch Graph send/forward transport errors
- [x] [Review][Patch] Reject path try/catch
- [x] [Review][Patch] Ignore stale analyze responses
- [x] [Review][Patch] Stable local message id
- [x] [Review][Patch] OpsHealthStatus removed from daily pane
- [x] [Review][Patch] ConfirmOutboundDialog focus trap

### Deferred (unchanged)

See `deferred-work.md`.
