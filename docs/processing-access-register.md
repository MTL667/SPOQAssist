# SpoqAssist processing & access register (FR32 / FR33)

Living document — update when processing or visibility changes (Story 4.5 DoD).

## What is read

| Data | Purpose | Component | When |
|------|---------|-----------|------|
| Message subject, body, metadata | Classify / route / priority / draft | Hub `analyze` + Graph/`mail_read` | On analyze |
| Attachments (name/size; supported types) | Enrich analysis | Hub attachment ingest | On analyze |
| Sent/forwarded history chunks | Style + retrieval grounding | Hub indexer + `mail_chunks` | Index job / connect |
| User decisions (accept/edit/reject/reroute) | Feedback + learning + audit | Hub feedback/audit APIs | On user action |
| Outbound confirm payload | Send/forward after HITL | Hub `confirm-outbound` + Graph | On Confirm only |

## What is **not** done

- No external LLM API for mailbox content (NFR-S1)
- No send/forward without Confirm (FR37)
- No web dashboard required for daily shared work (this release)

## Roles & visibility (shared vs personal)

| Role | Personal mailbox AI/content | Shared mailbox AI/content | Shared AI settings | Ops health (non-content) |
|------|----------------------------|---------------------------|--------------------|--------------------------|
| Personal owner | Yes (own only) | If entitled delegate | No | Limited |
| Shared delegate | No | Yes (entitled shared) | No | Limited |
| Admin | **No (admin-blind)** | Yes (entitled) | **Yes (shared only)** | Yes (non-content) |
| Ops | No mail bodies | No mail bodies | No | Yes |

**Explicit split (FR33):** admins are **shared-only** for AI config/data; personal AI-derived data is **owner-only** and denied to admins at the API (`domain/policies.py`).

## Components

- Outlook add-in — UI only; Bearer to hub; never holds Graph refresh tokens; never calls Ollama
- Hub API — authZ, analyze, feedback, confirm, retention, ops
- Microsoft Graph — mail read/send/forward via hub OBO
- Local Ollama (Mac Studio) — Qwen3 Embedding 0.6B (`vector(1024)`), Reranker 0.6B, Instruct 14B

## Retention

AI indexes/embeddings/chunks follow Exchange-aligned retention per `mailbox_profile` (`retention_policies`, Story 4.4). Audit retention follows company policy / optional purge flag.
