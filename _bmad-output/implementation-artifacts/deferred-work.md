# Deferred work

## Deferred from: spec-use-cached-behavior-summary-in-drafts (2026-07-22)

- Invalidate/refresh cached summary when indexed chunk count changes materially (stale cache)
- Concurrent ensure_cached_summary locking / for-update
- Assert Ollama prompt contains summary text (CI uses stub marker today)

## Deferred from: spec-fix-behavior-summary-qwen-think (2026-07-22)

- Optional `behavior_summary.status=degraded` + UI hint when using grounded fallback (fix spec chose usable `ok`)
- Update parent inspector I/O row that still says model-down → error + Retry
- Extra matrix tests for TimeoutException / empty Ollama response (RuntimeError path covered)
- Draft path: if Ollama rejects unknown `think` field, soft-fallback like timeout

## Deferred from: spec-mailbox-profile-inspector (2026-07-22)

- Persist/cache behavior summary in Postgres (Ask First left open; generate-on-open for now)
- Prompt-injection hardening for behavior summary (same broader inference pass as drafts)
- Admin-denied personal inspect automated coverage (entitlement already shared with analyze)
- Add-in integration test for Mail A→B stable profile id (manual check remains)
- Cap/paginate routes UI beyond hub limit(100); kind flip cache for personal↔shared

## Deferred from: spec-mailbox-history-profile-lifecycle (2026-07-22)

- Report attempted/listed Sent Items count alongside indexed_count for richer progress UI
- Graph delta-link cursor for true incremental history beyond newest-N listing
- Full Alembic migration framework (pilot uses create_all + ALTER ensure)

## Deferred from: spec-real-intent-routing-and-drafts (2026-07-22)

- Live Ollama-mode integration tests for meeting/no-route (CI uses stub; classify path is shared)
- Architecture doc still mentions legacy `/messages/{id}/analyze` path — update when docs pass runs
- Embed/draft timeout budgets vs architecture NFR numbers (pre-existing pilot tuning)
- RoutePicker listbox a11y roles/keyboard — polish later
- Prompt-injection hardening for instruct drafts — broader inference security pass

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
