---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
  - '_bmad-output/planning-artifacts/ux-design-specification.md'
  - '_bmad-output/planning-artifacts/product-brief-SpoqAssist.md'
  - '_bmad-output/planning-artifacts/prd-validation-report.md'
  - '_bmad-output/brainstorming/brainstorming-session-2026-07-22-0843.md'
  - '_bmad-output/planning-artifacts/ai-act-pellicaan-scope.pdf'
workflowType: 'epics'
project_name: 'SpoqAssist'
user_name: 'Kevin'
date: '2026-07-22'
lastStep: 4
status: 'complete'
completedAt: '2026-07-22'
---

# SpoqAssist - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for SpoqAssist, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Users can sign in with Microsoft Entra ID.
FR2: The system can authorize users from multiple configured Entra entities.
FR3: Users can access SpoqAssist only for mailboxes they are entitled to use.
FR4: Admins can view and configure AI settings only for shared mailboxes.
FR5: Admins cannot view personal mailbox content or personal AI-derived data.
FR6: Personal mailbox owners can use SpoqAssist only for their own mailbox.
FR7: The system can connect to shared and personal mailboxes in Microsoft 365 / Exchange.
FR8: The system can read message content needed for analysis (subject, body, metadata, relevant thread context).
FR9: The system can read attachments as part of analysis for this release.
FR10: The system can use historical sent and forwarded mail as learning/retrieval context per mailbox profile.
FR11: AI-derived indexes follow the same retention rules as the underlying Exchange mailbox data.
FR12: The system can classify an inbound message into actionable categories.
FR13: The system can suggest a routing/forward target for a message.
FR14: The system can suggest a reply draft in the mailbox owner’s/shared mailbox style from historical context.
FR15: The system can assign a priority/urgency suggestion to a message.
FR16: The system can assign a confidence level to each suggestion.
FR17: Users can view an explanation of why a suggestion was made (at least for medium/low confidence).
FR18: Shared-mailbox delegates can view a queue of messages with AI suggestions and confidence.
FR19: Users with shared-mailbox delegate rights can work the same shared-mailbox queue concurrently, subject to existing mailbox permissions.
FR20: Users can accept a suggested action for a shared-mailbox message.
FR21: Users can edit a suggested draft or routing target before executing.
FR22: Users can reject a suggestion and handle the message manually.
FR23: Users can correct a wrong routing suggestion and record that correction.
FR24: Personal mailbox users can open SpoqAssist from Outlook for a selected message.
FR25: Personal mailbox users can review suggested draft, category, route, and priority in that context.
FR26: Personal mailbox users can accept, edit, or reject suggestions before sending.
FR27: Admins can centrally deploy the Outlook add-in to users/groups per Entra entity.
FR28: The system can record accept, edit, reject, and reroute outcomes as feedback.
FR29: After a recorded routing correction for a shared mailbox, subsequent similar messages show the corrected route as a suggestion within the next learning cycle for that mailbox profile.
FR30: Routing corrections can update shared-mailbox routing knowledge without exposing personal mailbox data to admins.
FR31: Users can send AI-assisted outbound messages with proactive AI disclosure.
FR32: Admins/compliance can view a processing & access register describing what is read, for what purpose, by which component, and which roles can see what.
FR33: The register documents the shared-vs-personal access split (admins shared-only; personal owner-only).
FR34: The system can keep an audit trail of suggestion → user decision for traceability.
FR35: Ops/admins can check whether the central AI hub and suggestion service are reachable/healthy (without reading personal mail).
FR36: Authorized operators can manage non-content configuration needed to keep mail connectors and auth working across Entra entities.
FR37: Users must explicitly confirm before any send or forward action is executed (human-in-the-loop for mutating outbound actions in this release).

### NonFunctional Requirements

NFR-P1: Suggestion for a selected message (classify/route/priority path) returns within 10 seconds under normal load for the pilot (~10 users).
NFR-P2: Reply-draft generation returns within 30 seconds under normal load.
NFR-P3: Dashboard/queue load for a shared mailbox shows current suggestions without blocking the rest of the UI for more than the above budgets per item (batch may process asynchronously). Note: UX makes Outlook the primary queue surface; same latency budgets apply.
NFR-S1: Mailbox content and AI-derived data are processed only on company-controlled infrastructure for the default AI path (no external LLM API for mailbox content).
NFR-S2: Data in transit between clients and hub uses TLS (or equivalent protected channel, e.g. VPN/Tailscale + TLS).
NFR-S3: Personal mailbox AI data is inaccessible to admin roles; enforced in the API authorization layer.
NFR-S4: Access is Entra ID–authenticated; authorization respects mailbox entitlements and the shared/personal split.
NFR-S5: Audit logs of suggestion → decision are retained per company policy / aligned with mailbox retention where applicable.
NFR-R1: Hub unavailability is detectable by ops within 60 seconds via health check; clients show a clear “unavailable” state rather than silent failure.
NFR-R2: After a temporary hub or mail-connector outage, the system resumes without corrupting mailbox data and without executing duplicate sends/forwards; mutating outbound actions still require human confirmation (FR37).
NFR-SC1: System supports the pilot scale of ~10 users and concurrent shared + personal mailbox processing without redesign.
NFR-SC2: Growth beyond pilot is a capacity/planning exercise, not a hard requirement for this release.
NFR-I1: Supports Microsoft Entra ID sign-in and multi-entity configuration.
NFR-I2: Supports Outlook for Mac add-in deployment model (centralized admin deployment per entity).
NFR-I3: Supports Microsoft 365 / Exchange mailbox access sufficient for read/analyze and user-confirmed send/forward actions.
NFR-I4: Attachment ingestion has documented size/type limits; unsupported types fail gracefully with user-visible reason.

### Additional Requirements

- **Starter (Epic 1 Story 1 priority):** Dual scaffold — Yo Office React/TS Outlook add-in + lean FastAPI hub + Docker Compose with `pgvector/pgvector` (PG16); monorepo `apps/outlook-addin`, `apps/hub-api`, `docker/`
- Hub on Mac Studio via Docker; inference host/sidecar; no public-cloud PaaS for AI path
- Remote access: Tailscale (Studio ↔ MacBooks)
- Auth: Entra JWT (delegated/OBO) validated on hub; Graph as mail API; secrets stay on Studio
- AuthZ: mailbox_profile + role policy on every data/AI call; personal admin-blind at API
- Data: PostgreSQL + pgvector; knowledge graph as relational edge tables; Alembic; Pydantic v2
- API: REST `/v1`, OpenAPI; sync analyze (10s/30s); error envelope; confirm-outbound with idempotency_key
- Patterns: snake_case API/DB; camelCase only in React UI mappers; Office.js only in `officeMail.ts`
- Observability: structured logs without PII; `/health`; light CI (hub + add-in)
- Compliance: AI disclosure on confirm; processing/access register doc; suggestion→decision audit
- Out of release: autonomy, LoRA, Redis-required queue, **web dashboard** (deferred/optional), separate graph DB
- **Local model stack (pinned):** Ollama on Mac Studio host; Qwen3 14B Instruct (draft); Qwen3-Reranker-0.6B (fast path); Qwen3-Embedding-0.6B with **pgvector `vector(1024)`**
- Open follow-ups (non-blocking): document Graph scopes per Entra entity

### Release UI Scope (clarification)

**This release ships Outlook for Mac add-in only** for shared + personal daily work (FR18 satisfied in Outlook). Do **not** implement a web dashboard queue unless a later epic explicitly adds it.

### UX Design Requirements

UX-DR1: Implement SPOQ+ design tokens in Fluent theme (`brand.primary` #135067, `brand.accent` #42AB9A, surfaces, status colors) for the Outlook task pane.
UX-DR2: Build `SuggestionHero` — high-confidence airy card with mint Accept covering route and/or draft; secondary Edit/Change route/Reject quieter below.
UX-DR3: Build `SuggestionReviewStack` — medium/low confidence stacked route/draft review without forcing hero one-click.
UX-DR4: Build `ConfirmOutboundDialog` — teal Confirm / ghost Cancel; shows action type, recipients, draft excerpt, AI disclosure; FR37 gate; focus trap; Escape = Cancel.
UX-DR5: Build `AnalyzingState` — calm analyzing UX with aria-live; soft “Still working…” after soft budget; respects reduced motion.
UX-DR6: Build `HubUnavailable` — clear unavailable + Retry; no stale Accept; no fake suggestions.
UX-DR7: Build `WhyExplanation` — expand-in-place short rationale (not modal); available at least for medium/low confidence.
UX-DR8: Build `RoutePicker` — searchable recipient change + teach/remember for wrong-route recovery.
UX-DR9: Build `FeedbackControls` — Accept / Edit / Reject / Change route (compact under hero; full in review stack).
UX-DR10: Button hierarchy: mint = Accept only; teal = Confirm send/forward only; ghost = secondary; quiet danger outline = Reject.
UX-DR11: Pane state machine: idle | analyzing | ready_hero | ready_review | confirming | unavailable | error; clear suggestion on mail selection change.
UX-DR12: Empty states: no mail selected; low/no history honest empty (no hallucinated draft).
UX-DR13: WCAG 2.2 AA — keyboard path Accept→Edit→Confirm→Cancel; confidence label+icon (not color-only); focus rings; ≥40px primary targets.
UX-DR14: Task-pane responsive breakpoints: compact &lt;300px; default 300–399px; ≥400px more draft lines / secondary actions in a row.
UX-DR15: Optional `OpsHealthStatus` surface (non-mail-content) for hub/connector status — not in daily mail pane chrome.
UX-DR16: Outlook-first daily path for shared + personal; web dashboard not required for core stories this release.

### FR Coverage Map

FR1: Epic 1 — Entra sign-in
FR2: Epic 1 — Multi-entity authorization
FR3: Epic 1 — Mailbox entitlement checks
FR4: Epic 4 — Admin shared-mailbox AI config only
FR5: Epic 4 — Personal AI data admin-blind
FR6: Epic 1 — Personal owner scope
FR7: Epic 1 — Connect shared/personal mailboxes
FR8: Epic 2 — Read message content for analysis
FR9: Epic 2 — Read attachments in analysis path
FR10: Epic 2 — Historical sent/forwarded as retrieval context
FR11: Epic 4 — AI index retention aligned to Exchange
FR12: Epic 2 — Classify inbound message
FR13: Epic 2 — Suggest routing/forward target
FR14: Epic 2 — Suggest style-matched reply draft
FR15: Epic 2 — Suggest priority/urgency
FR16: Epic 2 — Assign confidence level
FR17: Epic 2 — Explainability (why)
FR18: Epic 4 — Shared-mailbox delegates see suggestions/queue in Outlook
FR19: Epic 4 — Concurrent shared-mailbox delegate work
FR20: Epic 3 — Accept suggested action (shared)
FR21: Epic 3 — Edit draft or route before execute
FR22: Epic 3 — Reject suggestion
FR23: Epic 3 — Correct wrong route + record
FR24: Epic 2 — Open SpoqAssist from Outlook on selected message
FR25: Epic 2 — Review draft/category/route/priority in pane
FR26: Epic 3 — Personal accept/edit/reject before send
FR27: Epic 1 — Central add-in deploy per Entra entity
FR28: Epic 3 — Record accept/edit/reject/reroute feedback
FR29: Epic 3 — Routing correction learning cycle
FR30: Epic 3 — Shared routing knowledge without personal leakage
FR31: Epic 3 — AI disclosure on AI-assisted outbound
FR32: Epic 4 — Processing & access register viewable
FR33: Epic 4 — Register documents shared-vs-personal split
FR34: Epic 3 — Audit trail suggestion → decision
FR35: Epic 1 — Hub health check (non-content)
FR36: Epic 1 — Non-content connector/auth ops config
FR37: Epic 3 — Explicit confirm before send/forward

## Epic List

### Epic 1: Connect & Sign In
Users open SpoqAssist in Outlook, authenticate with Entra, and reach a healthy hub (or a clear unavailable state).
**FRs covered:** FR1, FR2, FR3, FR6, FR7, FR27, FR35, FR36

### Epic 2: Get AI Suggestions in Outlook
For a selected message, users receive classify/route/draft/priority suggestions with confidence and optional why (hero or review UI).
**FRs covered:** FR8, FR9, FR10, FR12, FR13, FR14, FR15, FR16, FR17, FR24, FR25

### Epic 3: Confirm, Feedback & Learning
Users accept/edit/reject/reroute, confirm send/forward with AI disclosure, and the system records feedback and learns routing corrections.
**FRs covered:** FR20, FR21, FR22, FR23, FR26, FR28, FR29, FR30, FR31, FR34, FR37

### Epic 4: Shared Work & Trust Boundaries
Shared-mailbox delegates collaborate safely; admins see only shared AI config/data; retention and the processing/access register enforce the trust model.
**FRs covered:** FR4, FR5, FR11, FR18, FR19, FR32, FR33

## Epic 1: Connect & Sign In

Users open SpoqAssist in Outlook, authenticate with Entra, and reach a healthy hub (or a clear unavailable state).

### Story 1.1: Scaffold monorepo hub and Outlook add-in

As a developer,
I want the dual scaffold (Docker Compose pgvector + FastAPI skeleton + Yo Office Outlook React/TS) in place,
So that later stories have a runnable baseline on Mac Studio and Mac clients.

**Acceptance Criteria:**

**Given** a clean checkout of the SpoqAssist monorepo  
**When** I start `docker/` Compose for `db` and `api`  
**Then** Postgres has pgvector available and the API process starts  
**And** `GET /health` returns a non-content healthy response without requiring auth  

**Given** the Outlook add-in project under `apps/outlook-addin`  
**When** I sideload it into Outlook for Mac  
**Then** an empty SpoqAssist task pane loads without errors  
**And** `.env.example` documents required variables and no mailbox content is logged

### Story 1.2: Entra sign-in to hub

As a user,
I want to authenticate with Microsoft Entra ID across configured entities,
So that only company identities can call SpoqAssist APIs.

**Acceptance Criteria:**

**Given** a valid Entra access token for a configured entity  
**When** I call a protected hub endpoint with `Authorization: Bearer`  
**Then** the hub accepts the request (FR1, FR2, NFR-S4, NFR-I1)  

**Given** an expired, forged, or wrong-audience token  
**When** I call a protected hub endpoint  
**Then** the hub returns 401 with the standard error envelope  
**And** secrets and raw tokens are never written to logs

### Story 1.3: Mailbox entitlement gate

As a mailbox owner or delegate,
I want API access limited to mailboxes I am entitled to use,
So that I cannot reach other users’ personal mailboxes through SpoqAssist.

**Acceptance Criteria:**

**Given** an authenticated user without entitlement to mailbox profile X  
**When** they request any data/AI operation for X  
**Then** the hub returns 403 (FR3)  

**Given** a personal mailbox profile  
**When** a non-owner (including admin) requests its AI/content endpoints  
**Then** access is denied (FR6; foundation for FR5)  
**And** entitlement checks run in hub policy/deps, not only in the add-in UI

### Story 1.4: Connect mailbox via Microsoft Graph

As a user,
I want my shared or personal mailbox connected to SpoqAssist via Microsoft Graph,
So that the hub can later analyze my mail on company infrastructure.

**Acceptance Criteria:**

**Given** a configured Entra app and mailbox entitlement  
**When** the hub connects a test personal mailbox and a test shared mailbox  
**Then** connection succeeds for both (FR7, NFR-I3)  

**Given** missing consent, bad scopes, or connector failure  
**When** connect is attempted  
**Then** the user/ops sees a clear reason and no duplicate secret storage occurs in the client  
**And** Graph tokens/secrets remain on the Mac Studio hub only

### Story 1.5: Hub health and unavailable state in add-in

As a user or operator,
I want hub health checks and a clear unavailable state in the Outlook pane,
So that outages are detectable and not silent.

**Acceptance Criteria:**

**Given** the hub is running  
**When** ops or monitoring calls `GET /health`  
**Then** status is returned without mailbox content (FR35, NFR-R1)  

**Given** the hub is stopped or unreachable over Tailscale/TLS  
**When** the user opens the SpoqAssist pane  
**Then** `HubUnavailable` (or equivalent) is shown with Retry (UX-DR6)  
**And** no stale Accept/suggestion actions are offered (NFR-R1)

### Story 1.6: Central Outlook add-in deployment per Entra entity

As an admin,
I want the Outlook add-in deployable centrally per Entra entity,
So that pilot users receive SpoqAssist without relying only on sideload.

**Acceptance Criteria:**

**Given** at least one configured Entra entity  
**When** admin follows the documented centralized deployment steps  
**Then** the add-in can be assigned to users/groups for that entity (FR27, NFR-I2)  

**Given** deployment is not yet rolled out to a user  
**When** they need to test  
**Then** sideload remains a documented temporary fallback  
**And** non-content connector/auth ops config can be managed per FR36 without reading mail content

## Epic 2: Get AI Suggestions in Outlook

For a selected message, users receive classify/route/draft/priority suggestions with confidence and optional why (hero or review UI).

### Story 2.1: SPOQ+ Fluent theme and pane shell

As a user,
I want the SpoqAssist Outlook pane themed with SPOQ+ tokens and a clear pane state shell,
So that the assistant feels on-brand and ready when I select a message.

**Acceptance Criteria:**

**Given** the Outlook add-in from Epic 1  
**When** the task pane loads  
**Then** Fluent UI v9 uses SPOQ+ tokens (UX-DR1: primary/accent/surfaces/status)  

**Given** no message is selected  
**When** I view the pane  
**Then** an honest empty state asks me to select a message (UX-DR12)  

**Given** I select a message in Outlook  
**When** the pane reacts  
**Then** SpoqAssist opens in context for that message (FR24) and pane state can enter `analyzing` / later ready states (UX-DR11)

### Story 2.2: Read selected message and attachments

As a user,
I want SpoqAssist to read the selected message (and supported attachments) for analysis,
So that suggestions are based on the real mail content.

**Acceptance Criteria:**

**Given** a connected mailbox and selected message  
**When** the hub loads message content for analysis  
**Then** subject, body, metadata, and relevant thread context are available (FR8)  

**Given** attachments within documented size/type limits  
**When** analysis runs  
**Then** supported attachments are included in the read path (FR9)  

**Given** an unsupported or oversized attachment  
**When** ingestion fails for that part  
**Then** the user sees a graceful reason and analysis can continue without that attachment (NFR-I4)  
**And** no mailbox content is sent to an external LLM API (NFR-S1)

### Story 2.3: Index historical sent and forwarded mail

As a user,
I want my mailbox’s historical sent/forwarded mail indexed for retrieval,
So that drafts and routing can use real organizational style and patterns.

**Acceptance Criteria:**

**Given** Ollama on the Mac Studio host with **Qwen3-Embedding-0.6B** available  
**When** the hub embedding client is configured  
**Then** embeddings are written as **`vector(1024)`** in Postgres/pgvector (Architecture Local Model Stack)  

**Given** a connected mailbox_profile with sent/forwarded history  
**When** indexing runs on the hub  
**Then** chunks/embeddings are stored scoped to that profile (FR10)  

**Given** indexing completes for a profile  
**When** retrieve is called for that profile  
**Then** similar historical items can be returned without crossing into another mailbox_profile  

**Given** logs during indexing  
**When** inspected  
**Then** they do not contain full subject/body text (architecture logging pattern)

### Story 2.4: Analyze classify, route, priority, and confidence

As a user,
I want classify/route/priority suggestions with a confidence level for the selected message,
So that I know what SpoqAssist recommends and how sure it is.

**Acceptance Criteria:**

**Given** Ollama on the Studio host with **Qwen3-Reranker-0.6B** (and retrieval embeddings) available  
**When** the fast analyze path runs  
**Then** classify/route/priority use reranker-first retrieve/rank without requiring the 14B instruct model (Architecture Local Model Stack)  

**Given** readable message content and retrieval context  
**When** I trigger analyze (or pane auto-analyze on selection)  
**Then** the hub returns category, suggested route (when applicable), priority, and confidence within 10 seconds under normal pilot load (FR12, FR13, FR15, FR16, NFR-P1)  

**Given** inference/hub is on company infrastructure only  
**When** analyze runs  
**Then** no external LLM API is used for mailbox content (NFR-S1) and the add-in never calls Ollama directly  

**Given** analyze fails  
**When** the error returns to the add-in  
**Then** the standard error envelope is used and the pane does not show a fake suggestion

### Story 2.5: Generate style-matched reply draft

As a user,
I want a reply draft grounded in my mailbox history style,
So that I can respond faster without starting from a blank page.

**Acceptance Criteria:**

**Given** Ollama on the Studio host with **Qwen3 14B Instruct** available  
**When** draft generation runs  
**Then** the hub uses that instruct model (not the reranker) for generation  

**Given** an analyze context that requires a draft  
**When** draft generation runs  
**Then** a reply draft is returned within 30 seconds under normal pilot load (FR14, NFR-P2)  

**Given** sufficient sent-history context for the mailbox_profile  
**When** the draft is produced  
**Then** the draft is associated with the suggestion payload (`suggestion_id`, optional draft field)  

**Given** insufficient history  
**When** draft quality cannot be grounded  
**Then** the UI can show an honest limited-history state rather than inventing a confident fake voice (UX-DR12)

### Story 2.6: Suggestion UI — Analyzing, Hero/Review, and Why

As a user,
I want to see Analyzing, then a high-confidence Hero or medium/low Review stack with optional Why,
So that I can understand and act on suggestions with low cognitive load.

**Acceptance Criteria:**

**Given** analyze is in flight  
**When** I view the pane  
**Then** `AnalyzingState` is shown with polite live updates and reduced-motion respect (UX-DR5)  

**Given** a high-confidence suggestion  
**When** results arrive  
**Then** `SuggestionHero` shows route and/or draft with mint Accept affordance (UX-DR2) — Accept may be wired in Epic 3  

**Given** medium/low confidence  
**When** results arrive  
**Then** `SuggestionReviewStack` is used instead of forcing hero one-click (UX-DR3)  

**Given** medium/low confidence (and optionally high)  
**When** I open Why  
**Then** short rationale is shown expand-in-place (FR17, UX-DR7)  

**Given** a suggestion is displayed  
**When** I review category/route/draft/priority in the pane  
**Then** FR25 is satisfied  
**And** narrow pane breakpoints stack actions appropriately (UX-DR14)

## Epic 3: Confirm, Feedback & Learning

Users accept/edit/reject/reroute, confirm send/forward with AI disclosure, and the system records feedback and learns routing corrections.

### Story 3.1: Feedback controls — Accept, Edit, Reject

As a user,
I want to accept, edit, or reject a suggestion in the Outlook pane,
So that I stay in control before anything is sent.

**Acceptance Criteria:**

**Given** a displayed suggestion (hero or review)  
**When** I use FeedbackControls  
**Then** I can Accept, Edit draft/route fields, or Reject (FR20, FR21, FR22, FR26, UX-DR9)  

**Given** button hierarchy rules  
**When** Accept is shown  
**Then** it uses mint accent and does **not** by itself send/forward (UX-DR10)  

**Given** I reject a suggestion  
**When** reject completes  
**Then** no send/forward occurs and the pane allows manual handling / next action  
**And** edit keeps me in the pane without a multi-page form

### Story 3.2: Confirm outbound send or forward (HITL)

As a user,
I want an explicit confirm step before send or forward,
So that mutating outbound actions never happen silently.

**Acceptance Criteria:**

**Given** I accepted or prepared an outbound action  
**When** ConfirmOutboundDialog opens  
**Then** I see action type, recipients, draft excerpt, Confirm (teal) and Cancel (ghost) (FR37, UX-DR4)  

**Given** I confirm with a unique `idempotency_key`  
**When** the hub executes confirm-outbound  
**Then** Graph send/forward runs once and success is returned  

**Given** the same `idempotency_key` is retried after a transient failure  
**When** confirm-outbound is called again  
**Then** no duplicate send/forward occurs (NFR-R2)  

**Given** I cancel the dialog  
**When** it closes  
**Then** focus returns to the pane and nothing was sent

### Story 3.3: AI disclosure on AI-assisted outbound

As a user and recipient stakeholder,
I want proactive AI disclosure when outbound mail was AI-assisted,
So that transparency requirements are met from day one.

**Acceptance Criteria:**

**Given** an AI-assisted reply or forward is about to be sent  
**When** ConfirmOutboundDialog is shown  
**Then** AI disclosure text is visible before Confirm (FR31, UX-DR4)  

**Given** confirm succeeds  
**When** the message is sent/forwarded  
**Then** disclosure is included per the configured outbound approach (dialog-confirmed footer/body policy)  

**Given** a fully manual send path without AI assistance  
**When** disclosure rules are evaluated  
**Then** AI disclosure is not falsely applied

### Story 3.4: Change route and teach via RoutePicker

As a shared-mailbox operator,
I want to correct a wrong routing suggestion and record that correction,
So that recovery is one step and trust is preserved.

**Acceptance Criteria:**

**Given** a routing suggestion I believe is wrong  
**When** I open RoutePicker and choose the correct recipient  
**Then** the suggestion target updates and I can proceed to confirm forward (FR23, UX-DR8)  

**Given** I mark the original suggestion wrong / teach  
**When** feedback is submitted  
**Then** the correction is recorded for the shared mailbox_profile  

**Given** keyboard/accessibility requirements  
**When** I use RoutePicker  
**Then** search/select is operable without relying on color alone (UX-DR13)

### Story 3.5: Persist feedback and audit trail

As a compliance-minded operator,
I want accept/edit/reject/reroute outcomes and suggestion→decision audits stored,
So that SpoqAssist is traceable and can learn later.

**Acceptance Criteria:**

**Given** a user Accept, Edit, Reject, or Reroute action  
**When** the hub handles feedback  
**Then** the outcome is persisted (FR28)  

**Given** a suggestion and a user decision  
**When** audit is written  
**Then** an audit trail links suggestion → decision (FR34, NFR-S5)  

**Given** personal mailbox feedback  
**When** an admin role queries feedback/AI data APIs  
**Then** personal records remain inaccessible (foundation for Epic 4 isolation)

### Story 3.6: Shared routing learning cycle

As a shared-mailbox operator,
I want corrected routes to influence similar future suggestions,
So that the same mistake is not repeated blindly.

**Acceptance Criteria:**

**Given** a recorded routing correction on a shared mailbox_profile  
**When** the next learning cycle completes  
**Then** subsequent similar messages show the corrected route as a suggestion (FR29)  

**Given** learning updates for a shared profile  
**When** personal mailbox data/indexes are inspected for leakage paths  
**Then** routing knowledge updates do not expose personal mailbox AI data to admins (FR30)  

**Given** a novel/low-confidence sender pattern  
**When** suggestions are produced  
**Then** the system still allows human-led handling (no autonomy)

## Epic 4: Shared Work & Trust Boundaries

Shared-mailbox delegates collaborate safely; admins see only shared AI config/data; retention and the processing/access register enforce the trust model.

### Story 4.1: Enforce personal admin-blind and shared admin config

As a personal mailbox owner and as an admin,
I want personal AI data hidden from admins while shared-mailbox AI settings remain admin-configurable,
So that the trust split is enforced in the API, not only in the UI.

**Acceptance Criteria:**

**Given** an admin role for an Entra entity  
**When** they access AI settings/config for a shared mailbox  
**Then** view/configure is allowed (FR4)  

**Given** the same admin role  
**When** they request personal mailbox content or personal AI-derived data  
**Then** the API denies access (FR5, NFR-S3)  

**Given** automated authZ tests  
**When** run in CI  
**Then** at least one positive shared-admin case and one negative personal-admin case pass

### Story 4.2: Shared-mailbox suggestions in Outlook for delegates

As a shared-mailbox delegate,
I want to work office@ (or similar) messages with AI suggestions in Outlook,
So that I can clear shared mail without leaving my mail client.

**Acceptance Criteria:**

**Given** delegate rights on a shared mailbox  
**When** I open SpoqAssist on a selected shared message  
**Then** I can view suggestions and confidence for that mailbox (FR18, UX-DR16)  

**Given** UX Outlook-first decision  
**When** daily shared work is performed  
**Then** no separate web dashboard is required to complete the core loop  

**Given** I lack shared-mailbox rights  
**When** I try to open that shared profile  
**Then** access is denied

### Story 4.3: Concurrent shared-mailbox delegate work

As a shared-mailbox team,
I want multiple delegates to work the same shared mailbox concurrently under existing permissions,
So that morning volume can be shared without exclusive locks blocking everyone.

**Acceptance Criteria:**

**Given** two users with shared-mailbox delegate rights  
**When** they analyze/act on different messages in the same shared mailbox  
**Then** both can proceed subject to mailbox permissions (FR19)  

**Given** both attempt confirm-outbound on the same message with different keys  
**When** mail system/Graph constraints apply  
**Then** the hub does not corrupt mailbox data and still requires confirm per action (NFR-R2)  

**Given** concurrency  
**When** feedback/audit is written  
**Then** each decision is attributable to the acting user

### Story 4.4: AI index retention aligned to Exchange

As a compliance stakeholder,
I want AI indexes/embeddings retained in line with Exchange mailbox retention,
So that SpoqAssist does not keep AI copies longer than the source mail.

**Acceptance Criteria:**

**Given** retention rules configured to mirror Exchange policy for a mailbox_profile  
**When** source data is due for removal per that alignment  
**Then** AI-derived indexes/embeddings/chunks for that profile are purged or soft-deleted accordingly (FR11)  

**Given** retention job runs  
**When** logs are produced  
**Then** they record profile-level actions without dumping message bodies  

**Given** NFR-S5  
**When** audit retention is configured  
**Then** audit retention follows company policy / mailbox alignment documentation

### Story 4.5: Processing and access register

As an admin or compliance user,
I want a processing & access register that states what is read, why, by which component, and who can see what,
So that transparency and the shared-vs-personal split are explicit.

**Acceptance Criteria:**

**Given** the register document/UI delivered in-repo or admin-accessible surface  
**When** compliance opens it  
**Then** it describes subject/body/metadata/sent history/attachments, purposes, components, and roles (FR32)  

**Given** the shared-vs-personal access split  
**When** the register documents visibility  
**Then** admins shared-only and personal owner-only are explicit (FR33)  

**Given** product changes that alter processing  
**When** the register is outdated  
**Then** the story/definition of done requires updating the register with the change

### Story 4.6: Ops health surface without mail content

As an operator,
I want a lightweight hub/connector health surface without mail bodies,
So that I can restore service for users without reading personal mail.

**Acceptance Criteria:**

**Given** ops access  
**When** I open OpsHealthStatus (or equivalent admin health view)  
**Then** I see hub reachability/degraded/down and connector auth hints without message content (UX-DR15, FR35)  

**Given** hub is down  
**When** users open the add-in  
**Then** they still see HubUnavailable in the pane (continuity with Story 1.5)  

**Given** an ops user without mailbox entitlement  
**When** they use health/ops endpoints  
**Then** they cannot read personal or shared mail bodies through those endpoints
