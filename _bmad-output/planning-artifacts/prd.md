---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
releaseMode: single-release
workflow_completed: true
completedAt: '2026-07-22'
inputDocuments:
  - '_bmad-output/brainstorming/brainstorming-session-2026-07-22-0843.md'
  - '_bmad-output/planning-artifacts/ai-act-pellicaan-scope.pdf'
workflowType: 'prd'
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 1
  projectDocs: 0
  compliance: 1
classification:
  projectType: saas_b2b
  domain: general
  complexity: medium
  projectContext: greenfield
---

# Product Requirements Document - SpoqAssist

**Author:** Kevin  
**Date:** 2026-07-22

## Executive Summary

SpoqAssist is an internal enterprise platform that makes email handling faster and cheaper by running AI on company-owned data and hardware. It connects Outlook mailboxes (shared and personal) to a local model stack on a Mac Studio middleware hub, learns from years of sent-mail history, and proposes actions—route, reply, prioritize, categorize—with humans confirming mutating actions in this release.

**Target users:** Shared-mailbox operators (e.g. office@) and ~10 personal mailbox users on Mac/Outlook.  
**Problem:** High-volume, pattern-based mailbox work (especially shared inboxes) consumes FTE capacity; cloud AI alternatives raise data residency and recurring cost concerns.  
**Outcome:** Measurable time saved per mail, fewer hours locked in office@, drafts and routing suggestions trained on the organization’s own history—without sending mailbox content to external LLM APIs.

### What Makes This Special

**Own data + cost control.** Inference and learning stay on the Mac Studio / internal network; historical sent and forwarded mail is the knowledge base—no separate documentation required. A reranker-first pipeline (lightweight retrieve/rank for classify/route; larger instruct model only for generation) keeps local compute viable. **UX for this release:** Outlook for Mac add-in is the primary daily path for shared and personal mailboxes; a web dashboard batch queue is **deferred/optional** (not required to ship). Differentiator vs. Copilot/cloud assistants: data does not leave the company stack, and unit economics are hardware-bound rather than per-token SaaS.

**Core insight:** The mailbox already contains the training set. Human accept/edit/reject labels improve suggestions over time. Proactive AI Act transparency (Art. 50-oriented disclosure) from day one; GDPR legal basis remains an open compliance item. Selective autonomy and per-mailbox fine-tuning are nice-to-have after this release.

## Project Classification

| Attribute | Value |
|-----------|--------|
| **Project Type** | saas_b2b (internal enterprise platform; Outlook add-in + local API; web dashboard deferred) |
| **Domain** | general — workplace productivity / email operations |
| **Complexity** | medium (elevated by AI Act transparency + GDPR on mailbox content) |
| **Project Context** | greenfield |
| **Release mode** | single-release |

## Success Criteria

### User Success

- Shared-mailbox operators clear the morning AI queue faster than the pre-SpoqAssist baseline (time-to-process comparable mail volume).
- Personal users accept a meaningful share of drafts with zero or minimal edit — “sounds like me” + faster than typing.
- Users trust suggestions enough to use them daily: accept / edit / reject feedback is habitual; “why this suggestion?” is available when confidence is medium/low.
- Aha moment: first day a draft is sent without rewrite, or a correct routing suggestion saves a manual forward chain.

### Business Success

- **FTE:** Measurable reduction in hours spent on office@ (and similar shared inboxes) within 3 months of pilot rollout.
- **Cost:** Lower or more predictable AI cost vs. cloud Copilot/API alternatives (hardware-bound local inference; no per-token mailbox processing).
- **Data:** Mailbox content used for inference/learning stays on company-controlled infrastructure (Mac Studio / internal network).
- **Longer-term aspiration (not this release):** Selective autonomy for high-confidence patterns; sustained adoption across ~10 users; GDPR legal basis documented.

### Technical Success

- End-to-end path: select mail → analyze → suggestion in Outlook add-in (shared + personal) within NFR latency budgets.
- Lightweight retrieve/rank path handles classify/route/priority; instruct model used for generation when needed; system remains usable for ~10 mailboxes.
- Feedback loop persists labels (accept/edit/reject/reroute) into the knowledge store; routing corrections apply for shared mailboxes without exposing personal mail to admins.
- Proactive AI disclosure on outbound AI-assisted messages; auditability of suggestions (inputs → recommendation).

### Measurable Outcomes

| Metric | Direction (to calibrate in pilot) |
|--------|-----------------------------------|
| Time per mail (office@ / personal) | ↓ vs. baseline week |
| Routing suggestion accuracy | ↑ (target set after first labeled week) |
| Draft accept rate (no/minimal edit) | ↑ |
| Share of mail with AI suggestion used | ↑ weekly active use |
| Inference stays on-prem | 100% of SpoqAssist AI path |
| AI disclosure present when AI-assisted | 100% of configured flows |

## Product Scope

Aligned with **single-release** delivery (see also Project Scoping).

### Must-Have (This Release)

- Mac Studio middleware hub (remote-reachable) + local instruct model + reranker
- Mail connect for office@ **and** personal mailboxes; attachments in AI read path
- Vector store + knowledge graph for retrieval/routing rules (no LoRA)
- Suggestive actions: categorize, route, reply draft, prioritize
- Confidence levels + accept / edit / reject / reroute feedback
- Primary UI: Outlook for Mac add-in (shared + personal). Web dashboard batch queue: deferred/optional after this release
- Proactive AI disclosure on AI-assisted outbound
- Style copy via retrieval of historical sent mail (RAG)
- Entra ID auth; multi-Entra entity deploy; processing & access register
- Personal mailbox AI data admin-blind; shared mailbox admin-visible
- Retention of AI indexes aligned with Exchange

### Nice-to-Have (After This Release)

- Autonomous send/forward (confidence thresholds)
- Per-mailbox LoRA for stronger style match
- Follow-up detection, archive, escalate
- Web dashboard batch queue for shared mailboxes (deferred from this release)
- Richer analytics / batch polish beyond the MVP Outlook flow
- Closed GDPR/AI Act operating model as default company practice

## User Journeys

### Journey A — Shared mailbox operator (office@) — morning queue

**Persona:** Lisa, handles office@ most days; high volume, pattern work (route, standard replies, prioritize).

**Opening:** Monday 08:15. 40+ unread. Previously: open, read, forward, template-reply — hours gone.

**Rising action:** Works office@ in Outlook for Mac with the SpoqAssist add-in. Messages show confidence-scored suggestions (route, category, priority, draft where relevant). She works high-confidence first: accept → confirm send/forward; medium: skim “why” + edit; low: handle manually or teach via reject/reroute. (A separate web batch dashboard is deferred—not required for this journey in this release.)

**Climax:** In under an hour she clears what used to take half a morning — including a correct route she would have hunted for.

**Resolution:** Less dread opening office@; feedback improves tomorrow’s queue. Colleague with shared access can pick up the same queue later.

**Notes:** Outbound AI-assisted replies include proactive AI disclosure. Human confirms mutating actions in this release; GDPR legal basis remains an open compliance item.

**Reveals:** Outlook shared-mailbox assist, confidence tiers, route/reply/priority suggestions, explainability, multi-person shared access, feedback loop, AI disclosure.

### Journey B — Personal mailbox user — draft that sounds like me

**Persona:** Tom, ~10-person pilot user; lives in Outlook for Mac; hates rewriting the same tone every day.

**Opening:** Customer thread needs a careful reply. He starts typing, then opens SpoqAssist add-in sidebar.

**Rising action:** Sees draft grounded in *his* sent history (RAG style-match), plus optional route/priority. He edits two sentences, accepts. Faster than writing from scratch; tone still “him.”

**Climax:** Sends without a full rewrite — first real “this saves me time” moment.

**Resolution:** Uses sidebar on most non-trivial mails; rejects bad drafts so the system learns.

**Notes:** AI disclosure on AI-assisted outbound. Adoption gate: style-copy + time saved. Admins cannot see his personal AI data.

**Reveals:** Outlook add-in, per-mailbox history retrieval, quick accept/edit/reject, draft generation, personal style via RAG.

### Journey C — Shared mailbox — wrong routing (edge / recovery)

**Persona:** Lisa again; a VIP client mail is suggested to the wrong colleague.

**Opening:** Medium-confidence item: “Forward to Finance.” She knows it should go to Account Management.

**Rising action:** Opens explainability (“similar past forwards…”). Wrong. She chooses correct recipient, marks suggestion wrong, sends correct forward.

**Climax:** System records correction; routing knowledge updates so the pattern does not repeat blindly.

**Resolution:** Trust preserved because recovery was one action. Low-confidence / novel senders stay human-led.

**Reveals:** Reroute + explicit negative feedback, near-term learning on routing, VIP/edge handling.

### Journey D — Ops / IT — hub must stay reachable

**Persona:** Sam, IT; owns Mac Studio remote access and uptime for ~10 users.

**Opening:** Users report “no suggestions” while working from home.

**Rising action:** Checks remote access to Mac Studio, inference service health, mail connector auth. Restarts service or renews connector token; confirms latency back to normal.

**Climax:** Add-in suggestions light up again; hub processing resumes.

**Resolution:** Runbook exists: connectivity, model process, mail auth. Pilot does not depend on someone’s laptop being open — hub is the always-on path.

**Reveals:** Remote access, health/status, mail connector auth lifecycle, ops runbooks, central hub architecture.

### Journey Requirements Summary

| Area | From journeys |
|------|----------------|
| Primary UI | Outlook add-in for shared (A/C) + personal (B); web dashboard deferred |
| AI actions | Categorize, route, draft, prioritize + confidence |
| Feedback | Accept / edit / reject / reroute → learning |
| Explainability | “Why this suggestion?” |
| Shared access | Multi-person office@ queue |
| Compliance | AI disclosure + human confirmation (A/B) |
| Ops | Hub reachability, health, connector auth (D) |

## Domain-Specific Requirements

### Compliance & Regulatory

- **EU AI Act:** Treat SpoqAssist as an AI system; apply Art. 50-oriented transparency. Proactive AI disclosure on AI-assisted outbound mail in this release; stronger obligations if autonomy is later enabled.
- **GDPR:** Mailbox content and derived embeddings/indexes are personal data. **Legal basis for AI processing = open item** (legal counsel). Document processing purposes: classify, route, draft, prioritize, improve models via feedback.
- **Retention:** AI indexes / embeddings / learned artifacts follow **the same retention as Exchange mailbox data**.
- **Processing & access register:** Productized description of **what is read** (subject, body, metadata, sent history, **attachments**), purpose, system component, and human roles. Admins (shared) and compliance can view/export; personal mailbox content remains owner-only.

### Technical Constraints

- Inference and learning on company-controlled infrastructure; no external LLM API for mailbox content in the default path.
- Human-in-the-loop for send/forward and other mutating actions in this release.
- Auditability: log suggestion → user decision.
- Explainability for medium/low confidence suggestions.

### Access Control

- **Shared mailboxes:** Admins may view/configure AI processing, queues, and profile settings.
- **Personal mailboxes:** Content and AI-derived data are **not visible to admins**. Only the mailbox owner uses SpoqAssist for that mailbox. Ops may manage hub health without reading personal mail.
- Processing & access register documents this split.

### Integration Requirements

- Outlook for Mac + Microsoft 365 / Exchange (Graph and/or EWS — architecture decision).
- Shared and personal mailboxes; shared-queue access follows existing mailbox permissions.
- Multi-Entra entity support for auth and add-in deployment (details in SaaS B2B Specific Requirements).

### Risk Mitigations

| Risk | Mitigation |
|------|------------|
| Unclear GDPR basis | Stay HITL; counsel in parallel; block autonomy until basis documented |
| Over-retention of AI copies | Align index retention to Exchange |
| Admin overreach on personal mail | Hard isolation: personal owner-only; admins shared-only |
| Black-box wrong routing | Explainability + easy correction + feedback learning |
| AI Act non-disclosure | Mandatory disclosure on AI-assisted outbound |
| Hub unreachable | Health checks, remote access, ops runbooks |

## SaaS B2B Specific Requirements

### Project-Type Overview

Internal enterprise platform (not commercial multi-tenant SaaS). Dual clients against a central Mac Studio API. Identity via Microsoft Entra ID; mail via M365/Exchange. **Multiple Entra entities** supported in deployment and auth.

### Tenant Model

- **Product tenancy:** Isolation unit = mailbox profile (shared vs personal).
- **Identity tenancy:** App registration, admin consent, and add-in deployment **per Entra entity**.
- Hub may serve configured entities; no cross-entity leakage of personal mailbox AI data.

### RBAC / Permission Matrix

| Role | Shared mailbox AI data/config | Personal mailbox AI data | Hub ops (health) |
|------|-------------------------------|--------------------------|------------------|
| Mailbox owner (personal) | — | Full (suggestions, feedback) | — |
| Shared mailbox delegate | Queue + suggestions for that shared MB | — | — |
| Admin (per Entra entity) | View/configure shared MB AI only | **No content/AI data** | Yes (non-content) |
| End user | Via Outlook permissions | Own only | — |

### Subscription Tiers

N/A (internal platform). Optional later: feature flags per group/entity.

### Integration List

- **Entra ID** — SSO; group-based assignment
- **Outlook for Mac add-in** — centralized admin deployment per Entra entity
- **Microsoft Graph and/or EWS** — mail read/write for authorized mailboxes
- **Mac Studio inference API** — analyze/suggest
- **Attachments** — in AI read path; size/type limits documented (NFR-I4)

### Compliance & Implementation Notes

- Domain compliance applies (AI Act, GDPR open, retention, register).
- Least-privilege Graph scopes documented per Entra entity.
- Personal isolation enforced in API, not only UI.
- Pilot checklist: per-entity app + add-in + mailbox connect; sideload only as temporary fallback.

## Project Scoping

### Strategy & Philosophy

**Approach:** Single-release problem-solving delivery — useful HITL mail assistant on own data/hardware for shared + personal mailboxes.  
**Learning goal:** Prove time saved + draft/routing quality without autonomy or LoRA.  
**Resources:** Small build team (add-in + API/hub + ML/ops) + IT for Entra/multi-entity + legal for GDPR basis (parallel).

### Complete Feature Set

**Journeys in scope:** A (office@ queue), B (personal draft), C (routing recovery), D (ops hub).

**Must-have / nice-to-have:** See Product Scope. Capability contract: Functional Requirements (FR1–FR37).

### Risk Mitigation Strategy

| Risk | Mitigation |
|------|------------|
| **Technical:** Graph/add-in + multi-Entra + local inference load | Early spike: one tenant E2E; measure latency; attachment limits |
| **Adoption:** Style-copy or time-save fails | Pilot metrics week 1; RAG quality; easy reject |
| **Resource:** Scope creep into autonomy | Hard freeze: autonomy/LoRA out of this release |
| **Compliance:** GDPR basis open | Stay HITL; document register; counsel in parallel |

## Functional Requirements

Capability contract for this release. Capabilities not listed are out of scope unless explicitly added.

### Identity & Access

- FR1: Users can sign in with Microsoft Entra ID.
- FR2: The system can authorize users from multiple configured Entra entities.
- FR3: Users can access SpoqAssist only for mailboxes they are entitled to use.
- FR4: Admins can view and configure AI settings only for shared mailboxes.
- FR5: Admins cannot view personal mailbox content or personal AI-derived data.
- FR6: Personal mailbox owners can use SpoqAssist only for their own mailbox.

### Mailbox Connection & Ingestion

- FR7: The system can connect to shared and personal mailboxes in Microsoft 365 / Exchange.
- FR8: The system can read message content needed for analysis (subject, body, metadata, relevant thread context).
- FR9: The system can read attachments as part of analysis for this release.
- FR10: The system can use historical sent and forwarded mail as learning/retrieval context per mailbox profile.
- FR11: AI-derived indexes follow the same retention rules as the underlying Exchange mailbox data.

### Analysis & Suggestions

- FR12: The system can classify an inbound message into actionable categories.
- FR13: The system can suggest a routing/forward target for a message.
- FR14: The system can suggest a reply draft in the mailbox owner’s/shared mailbox style from historical context.
- FR15: The system can assign a priority/urgency suggestion to a message.
- FR16: The system can assign a confidence level to each suggestion.
- FR17: Users can view an explanation of why a suggestion was made (at least for medium/low confidence).

### Shared Mailbox Work Queue

- FR18: Shared-mailbox delegates can view a queue of messages with AI suggestions and confidence.
- FR19: Users with shared-mailbox delegate rights can work the same shared-mailbox queue concurrently, subject to existing mailbox permissions.
- FR20: Users can accept a suggested action for a shared-mailbox message.
- FR21: Users can edit a suggested draft or routing target before executing.
- FR22: Users can reject a suggestion and handle the message manually.
- FR23: Users can correct a wrong routing suggestion and record that correction.

### Personal Mailbox Assist

- FR24: Personal mailbox users can open SpoqAssist from Outlook for a selected message.
- FR25: Personal mailbox users can review suggested draft, category, route, and priority in that context.
- FR26: Personal mailbox users can accept, edit, or reject suggestions before sending.
- FR27: Admins can centrally deploy the Outlook add-in to users/groups per Entra entity.

### Feedback & Learning

- FR28: The system can record accept, edit, reject, and reroute outcomes as feedback.
- FR29: After a recorded routing correction for a shared mailbox, subsequent similar messages show the corrected route as a suggestion within the next learning cycle for that mailbox profile.
- FR30: Routing corrections can update shared-mailbox routing knowledge without exposing personal mailbox data to admins.

### Compliance & Transparency

- FR31: Users can send AI-assisted outbound messages with proactive AI disclosure.
- FR32: Admins/compliance can view a processing & access register describing what is read, for what purpose, by which component, and which roles can see what.
- FR33: The register documents the shared-vs-personal access split (admins shared-only; personal owner-only).
- FR34: The system can keep an audit trail of suggestion → user decision for traceability.

### Operations

- FR35: Ops/admins can check whether the central AI hub and suggestion service are reachable/healthy (without reading personal mail).
- FR36: Authorized operators can manage non-content configuration needed to keep mail connectors and auth working across Entra entities.
- FR37: Users must explicitly confirm before any send or forward action is executed (human-in-the-loop for mutating outbound actions in this release).

## Non-Functional Requirements

### Performance

- NFR-P1: Suggestion for a selected message (classify/route/priority path) returns within **10 seconds** under normal load for the pilot (~10 users).
- NFR-P2: Reply-draft generation returns within **30 seconds** under normal load.
- NFR-P3: Shared-mailbox suggestion load in the Outlook add-in shows current suggestions without blocking the rest of the UI for more than the above budgets per item (precompute/batch indexing may run asynchronously on the hub). A web dashboard queue, if built later, must meet the same per-item budgets.

### Security

- NFR-S1: Mailbox content and AI-derived data are processed only on company-controlled infrastructure for the default AI path (no external LLM API for mailbox content).
- NFR-S2: Data in transit between clients and hub uses TLS (or equivalent protected channel, e.g. VPN + TLS).
- NFR-S3: Personal mailbox AI data is inaccessible to admin roles; enforced in the API authorization layer.
- NFR-S4: Access is Entra ID–authenticated; authorization respects mailbox entitlements and the shared/personal split.
- NFR-S5: Audit logs of suggestion → decision are retained per company policy / aligned with mailbox retention where applicable.

### Reliability

- NFR-R1: Hub unavailability is detectable by ops within **60 seconds** via health check; clients show a clear “unavailable” state rather than silent failure (verified by stopping the hub service in a test environment).
- NFR-R2: After a temporary hub or mail-connector outage, the system resumes without corrupting mailbox data and without executing duplicate sends/forwards; mutating outbound actions still require human confirmation (FR37), verified by fault-injection tests.

### Scalability

- NFR-SC1: System supports the pilot scale of ~**10 users** and concurrent shared + personal mailbox processing without redesign.
- NFR-SC2: Growth beyond pilot is a capacity/planning exercise (more mailboxes/entities), not a hard requirement for this release.

### Integration

- NFR-I1: Supports Microsoft Entra ID sign-in and multi-entity configuration.
- NFR-I2: Supports Outlook for Mac add-in deployment model (centralized admin deployment per entity).
- NFR-I3: Supports Microsoft 365 / Exchange mailbox access sufficient for read/analyze and user-confirmed send/forward actions.
- NFR-I4: Attachment ingestion has documented size/type limits; unsupported types fail gracefully with user-visible reason.
