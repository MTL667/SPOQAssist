from __future__ import annotations

import json
import logging
import math
import time

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain.models import MailChunk, RoutingEdge
from app.services.inference import InferenceClient, get_embedding_dim

logger = logging.getLogger(__name__)

# After 404/405, skip rerank briefly so a mid-restart does not burn the process lifetime.
_RERANKER_DISABLE_TTL_S = 300.0


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def retrieve_similar(
    db: Session,
    *,
    mailbox_profile_id: str,
    query_text: str,
    client: InferenceClient,
    limit: int = 5,
) -> list[str]:
    """Return chunk texts using pgvector cosine distance (SQL-side) + optional reranker."""
    q = client.embed(query_text)
    expected_dim = get_embedding_dim()

    # Try pgvector SQL-side cosine distance (efficient, no in-memory loading)
    try:
        results = _retrieve_pgvector(db, mailbox_profile_id, q, expected_dim, limit * 3)
    except Exception:
        # Fallback to in-memory if pgvector operator not available
        logger.info("retrieve_pgvector_fallback reason=operator_unavailable")
        results = _retrieve_in_memory(db, mailbox_profile_id, q, expected_dim, limit * 3)

    if not results:
        return []

    # Rerank if available (vLLM mode)
    reranked = _rerank(query_text, results, limit)
    return reranked


def _retrieve_pgvector(
    db: Session,
    mailbox_profile_id: str,
    query_vec: list[float],
    expected_dim: int,
    candidate_limit: int,
) -> list[tuple[float, str]]:
    """Use pgvector <=> on native embedding_vec column for efficient retrieval."""
    vec_literal = "[" + ",".join(str(v) for v in query_vec) + "]"
    # Prefer native embedding_vec column (HNSW-indexed); fall back to JSON cast
    # CAST(:param AS vector) — `:param::vector` is invalid with SQLAlchemy bind params.
    stmt = text(
        """
        SELECT chunk_text,
               (embedding_vec <=> CAST(:query_vec AS vector)) AS distance
        FROM mail_chunks
        WHERE mailbox_profile_id = :profile_id
          AND embedding_vec IS NOT NULL
        ORDER BY distance ASC
        LIMIT :lim
        """
    ).bindparams(
        profile_id=mailbox_profile_id,
        query_vec=vec_literal,
        lim=candidate_limit,
    )
    rows = db.execute(stmt).all()
    if not rows:
        # Fallback: JSON cast for chunks not yet migrated to native vec
        stmt_fallback = text(
            """
            SELECT chunk_text,
                   (CAST(embedding_json AS vector) <=> CAST(:query_vec AS vector)) AS distance
            FROM mail_chunks
            WHERE mailbox_profile_id = :profile_id
              AND embedding_dim = :dim
            ORDER BY distance ASC
            LIMIT :lim
            """
        ).bindparams(
            profile_id=mailbox_profile_id,
            query_vec=vec_literal,
            dim=expected_dim,
            lim=candidate_limit,
        )
        rows = db.execute(stmt_fallback).all()
    # Convert distance to similarity (cosine distance = 1 - similarity)
    return [(1.0 - float(row.distance), row.chunk_text) for row in rows]


def _retrieve_in_memory(
    db: Session,
    mailbox_profile_id: str,
    query_vec: list[float],
    expected_dim: int,
    candidate_limit: int,
) -> list[tuple[float, str]]:
    """Fallback: load chunks into memory and compute cosine (for DBs without pgvector operator)."""
    rows = list(
        db.execute(
            select(MailChunk)
            .where(
                MailChunk.mailbox_profile_id == mailbox_profile_id,
                MailChunk.embedding_dim == expected_dim,
            )
            .limit(candidate_limit * 2)  # Cap to prevent OOM
        ).scalars()
    )
    scored: list[tuple[float, str]] = []
    for row in rows:
        try:
            emb = json.loads(row.embedding_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(emb, list) or len(emb) != expected_dim:
            continue
        scored.append((_cosine(query_vec, [float(x) for x in emb]), row.chunk_text))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:candidate_limit]


_reranker_disabled = False
_reranker_disabled_until = 0.0


def _cosine_top(candidates: list[tuple[float, str]], limit: int) -> list[str]:
    strong = [text for score, text in candidates[:limit] if score > 0.08]
    if strong:
        return strong
    return [text for _, text in candidates[: min(3, limit)]]


def _reranker_is_disabled() -> bool:
    global _reranker_disabled, _reranker_disabled_until
    if not _reranker_disabled:
        return False
    if time.monotonic() >= _reranker_disabled_until:
        _reranker_disabled = False
        _reranker_disabled_until = 0.0
        logger.info("reranker_reenabled")
        return False
    return True


def _disable_reranker(*, status: int, url: str) -> None:
    global _reranker_disabled, _reranker_disabled_until
    _reranker_disabled = True
    _reranker_disabled_until = time.monotonic() + _RERANKER_DISABLE_TTL_S
    logger.info(
        "reranker_disabled status=%s url=%s ttl_s=%.0f",
        status,
        url,
        _RERANKER_DISABLE_TTL_S,
    )


def _rerank(query: str, candidates: list[tuple[float, str]], limit: int) -> list[str]:
    """Rerank candidates using Qwen3-Reranker-4B if available (vLLM mode)."""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.inference_mode.lower() != "vllm" or _reranker_is_disabled():
        return _cosine_top(candidates, limit)

    # Prefer dedicated reranker host when configured; never burn 10s on a known-404 path.
    rerank_base = (
        getattr(settings, "vllm_reranker_url", None)
        or settings.vllm_embed_url
    ).rstrip("/")
    reranker_model = getattr(settings, "vllm_reranker_model", "Qwen/Qwen3-Reranker-4B")

    texts = [t for _, t in candidates]
    if not texts:
        return []

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{rerank_base}/rerank",
                json={
                    "model": reranker_model,
                    "query": query[:500],
                    "documents": [doc[:500] for doc in texts[:20]],
                    "top_n": limit,
                },
            )
            if resp.status_code in (404, 405):
                _disable_reranker(status=resp.status_code, url=rerank_base)
                return _cosine_top(candidates, limit)
            if resp.status_code >= 400:
                logger.info("reranker_http_error status=%s", resp.status_code)
                return _cosine_top(candidates, limit)

            data = resp.json()
            results = data.get("results", [])
            if not isinstance(results, list):
                return _cosine_top(candidates, limit)
            reranked = []
            for item in results[:limit]:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index", 0)
                if isinstance(idx, int) and 0 <= idx < len(texts):
                    reranked.append(texts[idx])
            return reranked if reranked else _cosine_top(candidates, limit)

    except (httpx.TimeoutException, httpx.HTTPError) as exc:
        logger.info("reranker_unavailable err=%s", type(exc).__name__)
        return _cosine_top(candidates, limit)
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        logger.info("reranker_malformed err=%s", type(exc).__name__)
        return _cosine_top(candidates, limit)


def lookup_learned_route(
    db: Session, *, mailbox_profile_id: str, pattern_key: str
) -> tuple[str, str | None] | None:
    stmt = select(RoutingEdge).where(
        RoutingEdge.mailbox_profile_id == mailbox_profile_id,
        RoutingEdge.pattern_key == pattern_key,
    )
    edge = db.execute(stmt).scalar_one_or_none()
    if edge is None:
        return None
    return edge.route_email, edge.route_name
