---
title: "Product Brief: SpoqAssist"
status: "complete"
created: "2026-07-22"
updated: "2026-07-22"
inputs:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/brainstorming/brainstorming-session-2026-07-22-0843.md"
  - "conversation discovery 2026-07-22"
---

# Product Brief: SpoqAssist

## Executive Summary

SpoqAssist makes email faster and cheaper by running AI on our own data and hardware—without sending mailbox content to a cloud LLM. It connects Outlook (shared and personal mailboxes) to a local model stack on a Mac Studio hub and proposes the work humans already do all day: categorize, route, draft replies, and prioritize—always with a person confirming before anything is sent or forwarded.

Today, pattern-heavy inboxes (especially shared mailboxes such as office@) consume scarce FTE capacity. Cloud assistants trade that pain for data residency risk and unpredictable per-seat or per-token cost. SpoqAssist keeps inference on company-controlled infrastructure, learns from years of sent-mail history (the documentation already living in the mailbox), and ships first as a human-in-the-loop pilot for ~10 users—proving time saved before any autonomy.

## The Problem

Shared and personal mailboxes are full of repeatable work: forward to the right person, answer with a known pattern, prioritize what matters. That work sits in people’s heads and calendars—not in a wiki. Cloud AI can help, but it pushes sensitive mail through external models and locks cost to usage or licenses.

The cost of the status quo is measurable in hours: one FTE effectively parked on office@-style queues, while personal users rewrite the same tone every day. Without a local, org-aware assistant, the choice is slow humans or cloud AI with the wrong economics and trust profile.

## The Solution

SpoqAssist is an internal platform with two surfaces:

- **Shared mailboxes:** a web dashboard queue with confidence-scored suggestions (route, draft, priority, category)—batch review for office@-style work.
- **Personal mailboxes:** an Outlook for Mac add-in sidebar—draft and actions that match the user’s voice from their own sent history.

A central Mac Studio hub runs a reranker-first pipeline (fast classify/route; larger local model only when drafting). Feedback (accept / edit / reject / reroute) trains the next suggestions. AI-assisted outbound messages carry proactive disclosure. Admins can see shared-mailbox AI context; personal mailbox AI data stays owner-only.

## What Makes This Different

| Alternative | SpoqAssist |
|-------------|------------|
| Microsoft Copilot / cloud LLM APIs | Inference stays on-prem; no per-token mailbox path |
| Generic chatbots / MCP mail tools | Org workflow: shared queue + Entra multi-entity + processing register |
| Manual process / undocumented know-how | Sent-mail history *is* the knowledge base |

**Unfair advantage for us:** years of mailbox history already labeled by real behavior, plus a hard requirement for data control and predictable hardware cost. Differentiation is execution and fit—not a novel market category.

## Who This Serves

| Role | Need | Success looks like |
|------|------|--------------------|
| **Shared-mailbox operator** | Clear the morning queue without hunting forwards | Same volume in far less time; correct routes in one click |
| **Personal mailbox user** | Drafts that sound like them | Send with minimal edit; faster than typing |
| **IT / Ops** | Always-on hub, not laptop-bound AI | Health checks, remote access, connector auth |
| **Compliance** | Transparency and access clarity | AI disclosure + processing/access register; GDPR basis tracked |

Primary buyers of the outcome are leadership and ops leads who care about **FTE hours** and **cost/data posture**; daily users are mailbox operators and personal mail users.

## Success Criteria

**North-star (pilot):** reduce **FTE hours** on shared mailboxes (e.g. office@) and reduce **time per mail** vs. a measured baseline week.

**Supporting signals:**
- Draft accept rate (no/minimal edit)—especially personal style-copy
- Routing suggestion accuracy (calibrate after first labeled week)
- Weekly share of mail where AI suggestions are used
- 100% on-prem inference path; 100% AI disclosure on configured AI-assisted outbound

**Latency budgets (pilot):** classify/route/priority ≤10s; draft ≤30s for ~10 users.

*Baseline office@ hours: to be measured in pilot kickoff if not already known.*

**Pilot go/no-go (suggested):** After 4–6 weeks, continue if time-per-mail and/or shared-mailbox hours trend down vs. baseline *and* draft/routing feedback shows improving accept rates—without requiring autonomy.

## Scope

**In for the first release (single ship):**
- Local hub + HITL suggestions (categorize, route, draft, prioritize)
- Shared + personal mailboxes; attachments in AI read path
- Dual UI (dashboard + Outlook add-in); Entra ID; multi-entity deploy
- Feedback loop; explainability; AI disclosure; processing/access register
- Personal AI data admin-blind; shared admin-visible

**Explicitly out:**
- Autonomous send/forward
- Per-mailbox LoRA
- Follow-up / archive / escalate automation
- Closed GDPR legal basis (legal track runs in parallel; HITL remains until resolved)

## Compliance posture (this release)

- **AI Act:** proactive disclosure on AI-assisted outbound from day one.
- **GDPR:** legal basis for AI processing of mailbox content remains an **open item** (counsel in parallel). This release stays human-in-the-loop for send/forward; autonomy stays out of scope until basis is documented.
- **Access:** shared-mailbox AI visible to admins; personal-mailbox AI content owner-only (API-enforced).

## Vision

If the pilot works, SpoqAssist becomes the default way the company handles high-volume mail: high-confidence patterns eventually automate under policy, personal style deepens with optional fine-tuning, and the operating model for mailbox AI (GDPR + AI Act) becomes standard practice—still on our hardware, still our data.
