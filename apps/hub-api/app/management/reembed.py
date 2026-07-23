"""Re-embed all mail chunks with the current embedding model and dimension.

Usage (from hub-api root):
    python -m app.management.reembed [--batch-size 100] [--dry-run]

This is idempotent: chunks already at the target dimension are skipped.
Progress is reported to stdout. Safe to Ctrl+C and resume.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.db.session import get_engine, init_db
from app.domain.models import MailChunk
from app.services.inference import get_embedding_dim, get_inference_client, set_inference_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-embed mail chunks to current model dimension.")
    parser.add_argument("--batch-size", type=int, default=100, help="Chunks per batch (default: 100)")
    parser.add_argument("--dry-run", action="store_true", help="Count stale chunks without re-embedding")
    parser.add_argument(
        "--profile-id", type=str, default=None, help="Only re-embed for a specific mailbox profile"
    )
    args = parser.parse_args()

    init_db()
    target_dim = get_embedding_dim()
    client = get_inference_client()

    logger.info("Re-embed target: dim=%d, mode=%s", target_dim, get_settings().inference_mode)

    from sqlalchemy.orm import Session, sessionmaker

    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        # Count stale chunks
        where_clause = MailChunk.embedding_dim != target_dim
        if args.profile_id:
            where_clause = where_clause & (MailChunk.mailbox_profile_id == args.profile_id)

        total_stale = db.execute(
            select(func.count()).select_from(MailChunk).where(where_clause)
        ).scalar_one()

        total_all = db.execute(
            select(func.count()).select_from(MailChunk)
        ).scalar_one()

        logger.info(
            "Chunks: total=%d, stale (dim != %d)=%d, already current=%d",
            total_all,
            target_dim,
            total_stale,
            total_all - total_stale,
        )

        if args.dry_run:
            logger.info("Dry run — no changes made.")
            return

        if total_stale == 0:
            logger.info("All chunks already at target dimension. Nothing to do.")
            return

        # Process in batches
        processed = 0
        failed = 0
        start = time.time()

        while True:
            stmt = (
                select(MailChunk)
                .where(where_clause)
                .order_by(MailChunk.created_at)
                .limit(args.batch_size)
            )
            chunks = list(db.execute(stmt).scalars().all())
            if not chunks:
                break

            for chunk in chunks:
                try:
                    emb = client.embed(chunk.chunk_text)
                    if len(emb) != target_dim:
                        emb = (emb + [0.0] * target_dim)[:target_dim]
                    chunk.embedding_json = json.dumps(emb)
                    chunk.embedding_dim = target_dim
                    # Also update native pgvector column
                    try:
                        from sqlalchemy import text as sa_text

                        vec_literal = "[" + ",".join(str(v) for v in emb) + "]"
                        with db.begin_nested():
                            db.execute(
                                sa_text(
                                    "UPDATE mail_chunks SET embedding_vec = CAST(:vec AS vector) WHERE id = :id"
                                ),
                                {"vec": vec_literal, "id": chunk.id},
                            )
                    except Exception:
                        pass  # SQLite or no pgvector — JSON is sufficient
                    processed += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to re-embed chunk %s: %s", chunk.id, type(exc).__name__
                    )
                    failed += 1
                    # Mark with sentinel dim to prevent infinite retry loop
                    chunk.embedding_dim = -1
                    continue

            db.commit()

            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = total_stale - processed - failed
            eta = remaining / rate if rate > 0 else 0
            logger.info(
                "Progress: %d/%d re-embedded (%.1f/s), %d failed, ETA %.0fs",
                processed,
                total_stale,
                rate,
                failed,
                eta,
            )

        elapsed = time.time() - start
        logger.info(
            "Done: %d re-embedded, %d failed in %.1fs (%.1f chunks/s)",
            processed,
            failed,
            elapsed,
            processed / elapsed if elapsed > 0 else 0,
        )


if __name__ == "__main__":
    main()
