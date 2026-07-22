# Deferred work

## Deferred from: code review of epics.md (2026-07-22)

- Embeddings stored as JSON text, not Postgres `vector(1024)` — pilot/sqlite compatibility
- Reranker model name logged but heuristics used on fast path — needs live Ollama wiring
- No Graph SentItems/forward crawl for indexing — only client `POST …/index`
- Thread/conversation context not loaded for analyze (FR8 partial)
- Attachment content not ingested into analyze (names/warnings only)
- RoutePicker uses static candidate list — directory search later
- Confidence icon + responsive pane breakpoints (UX-DR13/14 polish)
- FastAPI `/docs` left open on hub — Tailscale-only pilot assumption
- Ops connector “secret” substring filter is weak — low risk behind ops OID gate
