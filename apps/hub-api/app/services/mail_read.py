"""Message read path for analyze — Graph or client-provided fallback (Story 2.2)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.enums import MailboxKind
from app.services.mail_graph import get_mail_graph_client

logger = logging.getLogger(__name__)


@dataclass
class LoadedMessage:
    message_id: str
    subject: str
    body: str
    sender: str
    attachment_names: list[str] = field(default_factory=list)
    attachment_sizes: list[int] = field(default_factory=list)


def load_message_for_analyze(
    *,
    user_assertion: str,
    tenant_id: str,
    message_id: str,
    mailbox_kind: str,
    mailbox_email: str,
    graph_mailbox_id: str | None,
    fallback_subject: str | None,
    fallback_body: str | None,
    fallback_sender: str | None,
    attachment_names: list[str],
) -> LoadedMessage:
    settings = get_settings()
    if settings.graph_mode.lower() == "obo":
        client = get_mail_graph_client()
        # D1: fail-closed — never substitute client body when OBO is configured.
        msg = client.get_message(
            user_assertion=user_assertion,
            tenant_id=tenant_id,
            message_id=message_id,
            mailbox_kind=MailboxKind(mailbox_kind),
            mailbox_email=mailbox_email,
            graph_mailbox_id=graph_mailbox_id,
        )
        logger.info("message_loaded_via_graph message_id=%s", message_id)
        return LoadedMessage(
            message_id=message_id,
            subject=msg.subject,
            body=msg.body,
            sender=msg.sender,
            attachment_names=msg.attachment_names or attachment_names,
            attachment_sizes=list(msg.attachment_sizes or []),
        )

    # Stub mode — Office.js / test payload path
    if not (fallback_subject or fallback_body or fallback_sender or attachment_names):
        raise AppError(
            code="VALIDATION_ERROR",
            message="Message content is required when Graph OBO is not enabled.",
            status_code=422,
            retryable=False,
        )
    return LoadedMessage(
        message_id=message_id,
        subject=fallback_subject or "(no subject)",
        body=fallback_body or "",
        sender=fallback_sender or "unknown@example.com",
        attachment_names=list(attachment_names),
        attachment_sizes=[],
    )
