"""Pilot-safe additive schema fixes when Alembic is not yet wired."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_HISTORY_COLUMNS: dict[str, str] = {
    "history_status": "VARCHAR(32) DEFAULT 'not_started'",
    "history_sync_error": "VARCHAR(512)",
    "history_sync_started_at": "TIMESTAMP WITH TIME ZONE",
    "last_history_sync_at": "TIMESTAMP WITH TIME ZONE",
    "behavior_summary_text": "TEXT",
    "behavior_summary_updated_at": "TIMESTAMP WITH TIME ZONE",
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
