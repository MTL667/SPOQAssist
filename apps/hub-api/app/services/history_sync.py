"""Index mailbox Sent Items into local embeddings for grounded drafts."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.enums import MailboxKind
from app.services.inference import get_inference_client, plain_text_for_embed
from app.services.mail_graph import get_mail_graph_client

logger = logging.getLogger(__name__)

DEFAULT_MAX_MESSAGES = 100
# First-touch sync keeps the Outlook taskpane responsive.
INITIAL_SYNC_MAX_MESSAGES = 40


def sync_sent_history(
    db: Session,
    *,
    mailbox_profile_id: str,
    user_assertion: str,
    tenant_id: str,
    mailbox_kind: str,
    mailbox_email: str,
    graph_mailbox_id: str | None,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> int:
    """Pull Sent Items via Graph (or stub) and embed into MailChunk rows."""
    max_messages = max(1, min(int(max_messages), 300))
    existing = ai_store.indexed_source_ids(db, mailbox_profile_id)
    client = get_mail_graph_client()
    messages = client.list_sent_messages(
        user_assertion=user_assertion,
        tenant_id=tenant_id,
        mailbox_kind=MailboxKind(mailbox_kind),
        mailbox_email=mailbox_email,
        graph_mailbox_id=graph_mailbox_id,
        max_messages=max_messages,
    )
    items: list[dict[str, str]] = []
    for msg in messages:
        if msg.message_id in existing:
            continue
        text = plain_text_for_embed(f"{msg.subject}\n{msg.body}")
        if len(text) < 20:
            continue
        items.append({"message_id": msg.message_id, "text": text})

    if not items:
        logger.info(
            "history_sync_noop mailbox_profile_id=%s existing=%s fetched=%s",
            mailbox_profile_id,
            len(existing),
            len(messages),
        )
        return 0

    inference = get_inference_client()
    count = ai_store.index_chunks(
        db,
        mailbox_profile_id=mailbox_profile_id,
        items=items,
        embed_fn=inference.embed,
    )
    logger.info(
        "history_sync_done mailbox_profile_id=%s indexed=%s mode=%s",
        mailbox_profile_id,
        count,
        get_settings().graph_mode,
    )
    return count


def ensure_history_indexed(
    db: Session,
    *,
    mailbox_profile_id: str,
    user_assertion: str,
    tenant_id: str,
    mailbox_kind: str,
    mailbox_email: str,
    graph_mailbox_id: str | None,
) -> int:
    """If this mailbox has no chunks yet, run an initial Sent Items sync."""
    if ai_store.count_chunks(db, mailbox_profile_id) > 0:
        return 0
    try:
        return sync_sent_history(
            db,
            mailbox_profile_id=mailbox_profile_id,
            user_assertion=user_assertion,
            tenant_id=tenant_id,
            mailbox_kind=mailbox_kind,
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
            max_messages=INITIAL_SYNC_MAX_MESSAGES,
        )
    except AppError:
        # Do not block analyze if the first history crawl fails.
        logger.info(
            "history_sync_failed_continue mailbox_profile_id=%s",
            mailbox_profile_id,
        )
        return 0
