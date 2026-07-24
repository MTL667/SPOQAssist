"""Pilot-safe additive schema fixes when Alembic is not yet wired."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.services.inference import get_embedding_dim

logger = logging.getLogger(__name__)

_HISTORY_COLUMNS: dict[str, str] = {
    "history_status": "VARCHAR(32) DEFAULT 'not_started'",
    "history_sync_error": "VARCHAR(512)",
    "history_sync_started_at": "TIMESTAMP WITH TIME ZONE",
    "last_history_sync_at": "TIMESTAMP WITH TIME ZONE",
    "behavior_summary_text": "TEXT",
    "behavior_summary_updated_at": "TIMESTAMP WITH TIME ZONE",
    "history_sync_phase": "VARCHAR(32) DEFAULT 'not_started'",
    "history_messages_fetched": "INTEGER DEFAULT 0",
    "history_messages_target": "INTEGER DEFAULT 0",
}

_SUGGESTION_COLUMNS: dict[str, str] = {
    "proposed_slots_json": "TEXT DEFAULT '[]'",
    "availability_note": "TEXT",
}


def ensure_mailbox_history_columns(engine: Engine) -> None:
    """Add history-profile columns to mailbox_profiles if missing (create_all won't ALTER)."""
    try:
        insp = inspect(engine)
        if "mailbox_profiles" not in insp.get_table_names():
            return
        existing = {col["name"] for col in insp.get_columns("mailbox_profiles")}
        dialect = engine.dialect.name
        with engine.begin() as conn:
            for name, sql_type in _HISTORY_COLUMNS.items():
                if name in existing:
                    continue
                col_type = sql_type
                if dialect == "sqlite":
                    if "TIMESTAMP" in sql_type:
                        col_type = "DATETIME"
                    elif name == "history_status":
                        col_type = "VARCHAR(32) DEFAULT 'not_started'"
                conn.execute(text(f"ALTER TABLE mailbox_profiles ADD COLUMN {name} {col_type}"))
                logger.info("schema_ensure_added column=%s", name)
    except Exception:
        logger.exception("schema_ensure_history_columns_failed")


def ensure_suggestion_schedule_columns(engine: Engine) -> None:
    """Add proposed_slots / availability_note on suggestions if missing."""
    try:
        insp = inspect(engine)
        if "suggestions" not in insp.get_table_names():
            return
        existing = {col["name"] for col in insp.get_columns("suggestions")}
        with engine.begin() as conn:
            for name, sql_type in _SUGGESTION_COLUMNS.items():
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE suggestions ADD COLUMN {name} {sql_type}"))
                logger.info("schema_ensure_added column=%s", name)
    except Exception:
        logger.exception("schema_ensure_suggestion_schedule_columns_failed")


def ensure_pgvector_column(engine: Engine) -> None:
    """Add native vector column + HNSW index to mail_chunks for fast cosine search.

    Skipped on SQLite (no pgvector extension). Safe to run repeatedly.
    """
    dialect = engine.dialect.name
    if dialect == "sqlite":
        return

    try:
        insp = inspect(engine)
        if "mail_chunks" not in insp.get_table_names():
            return

        existing = {col["name"] for col in insp.get_columns("mail_chunks")}
        dim = get_embedding_dim()

        with engine.begin() as conn:
            # Ensure pgvector extension
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Add native vector column if missing
            if "embedding_vec" not in existing:
                conn.execute(
                    text(f"ALTER TABLE mail_chunks ADD COLUMN embedding_vec vector({dim})")
                )
                logger.info("schema_ensure_added column=embedding_vec dim=%d", dim)

            # Create IVFFlat index (HNSW limited to 2000 dims; we use 4096)
            # IVFFlat needs existing rows to train — skip if table is empty
            row_count = conn.execute(
                text("SELECT COUNT(*) FROM mail_chunks WHERE embedding_vec IS NOT NULL")
            ).scalar()
            if row_count and row_count > 0:
                lists = max(1, min(row_count // 10, 100))
                conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS ix_mail_chunks_embedding_vec_ivfflat "
                        f"ON mail_chunks USING ivfflat (embedding_vec vector_cosine_ops) "
                        f"WITH (lists = {lists})"
                    )
                )
                logger.info("schema_ensure_pgvector_ivfflat_index lists=%d", lists)
            else:
                logger.info("schema_ensure_pgvector_index_deferred (no data yet)")
    except Exception:
        logger.exception("schema_ensure_pgvector_column_failed")
