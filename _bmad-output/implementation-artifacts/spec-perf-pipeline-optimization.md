---
title: 'Performance Pipeline Optimization'
type: 'refactor'
created: '2026-07-23'
status: 'done'
baseline_commit: '660c84b'
context:
  - '_bmad-output/planning-artifacts/architecture-dgx-spark-addendum.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The pre-compute worker processes jobs sequentially (4x slower than designed), embeddings are stored as JSON text requiring runtime casts for pgvector queries, health endpoints block the async event loop, and the behavior summary cache has no concurrency guard causing duplicate model calls.

**Approach:** Enable ThreadPoolExecutor-based parallel processing in the worker, migrate embedding storage to native pgvector `vector(4096)` column, wrap blocking health calls in `asyncio.to_thread()`, and add row-level locking on behavior summary computation.

## Boundaries & Constraints

**Always:**
- All existing tests must pass after changes
- pgvector migration must be backward-compatible (old JSON column kept until reembed completes)
- ThreadPoolExecutor uses session-per-job (already the pattern)
- Connection pool size must accommodate concurrent workers (pool_size ≥ batch_size + API threads)

**Ask First:**
- Whether to drop `embedding_json` TEXT column after native vector column is populated (or keep as backup)
- Whether to add HNSW index parameters (m, ef_construction) or use defaults

**Never:**
- Do not change the analyze API contract (input/output schemas stay the same)
- Do not introduce async SQLAlchemy (keep sync sessions; use `to_thread` at endpoint level)
- Do not remove the in-memory cosine fallback (needed for SQLite test mode)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parallel processing — 4 jobs | 4 PENDING jobs in queue | All 4 complete within ~same wall-clock as 1 | Individual job failures don't crash others |
| Worker thread exception | Job #2 of 4 throws | Job #2 marked FAILED; #1,3,4 continue | Log error, increment retry_count |
| pgvector query on native column | Query vec + 4096-dim stored embeddings | Top-5 by cosine distance via `<=>` operator | Falls back to in-memory if extension missing |
| Health endpoint under load | 10 concurrent requests | All respond within 3s | `to_thread` prevents event loop blocking |
| Concurrent summary requests | 2 threads hit ensure_cached_summary | Only 1 computes; other waits and reads cache | SELECT FOR UPDATE blocks second caller |

</frozen-after-approval>

## Code Map

- `apps/hub-api/app/services/precompute.py` -- worker loop, job processing, ThreadPoolExecutor
- `apps/hub-api/app/api/health.py` -- async endpoints calling sync I/O
- `apps/hub-api/app/domain/models.py` -- MailChunk model, embedding column definition
- `apps/hub-api/app/db/repositories/ai_store.py` -- index_chunks writes embeddings
- `apps/hub-api/app/services/retrieve.py` -- pgvector query and fallback
- `apps/hub-api/app/management/reembed.py` -- re-embedding management command
- `apps/hub-api/app/services/profile_inspect.py` -- ensure_cached_summary, persist
- `apps/hub-api/app/db/session.py` -- connection pool configuration
- `tests/api/test_precompute.py` -- worker tests

## Tasks & Acceptance

**Execution:**
- [x] `apps/hub-api/app/services/precompute.py` -- Replace sequential `for` loop with `ThreadPoolExecutor(max_workers=batch_size)` using `submit` + `as_completed`; each job uses its own session
- [x] `apps/hub-api/app/db/session.py` -- Increase default `pool_size` to 8 and set `max_overflow=4` (for Postgres; SQLite unchanged)
- [x] `apps/hub-api/app/domain/models.py` -- Document `embedding_vec` native pgvector column on MailChunk; actual column managed by schema_ensure (SQLite compat)
- [x] `apps/hub-api/app/db/schema_ensure.py` -- Add `ensure_pgvector_column()`: CREATE EXTENSION vector, ALTER TABLE add embedding_vec, CREATE INDEX HNSW
- [x] `apps/hub-api/app/db/repositories/ai_store.py` -- Write both `embedding_json` AND `embedding_vec` (via raw SQL UPDATE) on index; graceful skip on SQLite
- [x] `apps/hub-api/app/services/retrieve.py` -- Use native `embedding_vec <=> query_vec` with fallback to JSON cast for un-migrated chunks + in-memory for SQLite
- [x] `apps/hub-api/app/management/reembed.py` -- Also populate `embedding_vec` column during re-embed batch
- [x] `apps/hub-api/app/api/health.py` -- Wrap all blocking calls in `asyncio.to_thread()` to keep event loop free
- [x] `apps/hub-api/app/services/profile_inspect.py` -- Add `SELECT ... FOR UPDATE` with double-check after lock; graceful fallback for SQLite
- [x] `tests/api/test_precompute.py` -- Add test for parallel execution (mock 4 jobs, verify all complete)

**Acceptance Criteria:**
- Given 4 pending precompute jobs, when the worker runs one batch, then all 4 are processed concurrently (wall-clock ≈ single-job time, not 4x)
- Given the native pgvector column exists, when retrieve_similar is called, then the query uses `embedding_vec <=> ...` without JSON parsing
- Given 10 concurrent health requests, when all hit the endpoint simultaneously, then none blocks others (response time < 3s under parallel load)
- Given two concurrent analyze requests for the same profile with no cached summary, when both call ensure_cached_summary, then the model is invoked exactly once

## Design Notes

**ThreadPoolExecutor pattern:**
```python
with ThreadPoolExecutor(max_workers=batch_size) as executor:
    futures = {executor.submit(_process_one_job, job.id): job.id for job in jobs}
    for future in as_completed(futures):
        job_id = futures[future]
        try:
            future.result()
        except Exception as exc:
            logger.error("job_%s_failed err=%s", job_id, exc)
```

Each `_process_one_job` creates its own `SessionLocal()` — the pattern already exists from the P3 code review fix.

**pgvector native column:** Use `from pgvector.sqlalchemy import Vector` for the column type. The HNSW index: `CREATE INDEX ... USING hnsw (embedding_vec vector_cosine_ops) WITH (m=16, ef_construction=64)`.

## Verification

**Commands:**
- `./apps/hub-api/.venv/bin/python -m pytest tests/ -x -q` -- expected: all tests pass
- `./apps/hub-api/.venv/bin/python -c "from app.services.precompute import run_worker; print('import ok')"` -- expected: no import errors
