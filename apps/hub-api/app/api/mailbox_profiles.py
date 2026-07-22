"""Mailbox connect + entitlement-gated profile endpoints (Stories 1.3–1.4)."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.deps import AuthCtx, DbSession, MailboxContentAccess
from app.core.errors import AppError
from app.db.repositories import ai_store, mailboxes as mailbox_repo
from app.domain.enums import HistoryProfileStatus, MailboxRole
from app.domain.schemas import (
    ConnectMailboxRequest,
    ConnectMailboxResponse,
    ContentStubOut,
    MailboxProfileOut,
    ProfileInspectOut,
)
from app.services.mail_graph import get_mail_graph_client
from app.services.profile_inspect import build_profile_inspect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/mailbox_profiles", tags=["mailbox_profiles"])


def _to_out(profile, db=None) -> MailboxProfileOut:  # type: ignore[no-untyped-def]
    chunks = ai_store.count_chunks(db, profile.id) if db is not None else None
    last = getattr(profile, "last_history_sync_at", None)
    return MailboxProfileOut(
        id=profile.id,
        tenant_id=profile.tenant_id,
        email=profile.email,
        kind=profile.kind,
        owner_oid=profile.owner_oid,
        connection_status=profile.connection_status,
        connection_error=profile.connection_error,
        graph_mailbox_id=profile.graph_mailbox_id,
        history_status=getattr(profile, "history_status", None)
        or HistoryProfileStatus.NOT_STARTED,
        last_history_sync_at=last.isoformat() if last else None,
        history_sync_error=getattr(profile, "history_sync_error", None),
        history_chunk_count=chunks,
    )


@router.post("/connect", response_model=ConnectMailboxResponse)
async def connect_mailbox(
    body: ConnectMailboxRequest,
    auth: AuthCtx,
    db: DbSession,
) -> ConnectMailboxResponse:
    """Connect personal or shared mailbox via Graph. Secrets stay on the hub."""
    client = get_mail_graph_client()
    try:
        info = client.connect_mailbox(
            user_assertion=auth.user_assertion,
            tenant_id=auth.principal.tenant_id,
            email=body.email,
            kind=body.kind,
        )
    except AppError as exc:
        mailbox_repo.mark_connect_failed(
            db,
            tenant_id=auth.principal.tenant_id,
            email=body.email,
            kind=body.kind,
            owner_oid=auth.principal.subject,
            error_message=exc.message,
        )
        logger.info(
            "mailbox_connect_failed code=%s kind=%s",
            exc.code,
            body.kind.value,
        )
        raise

    profile, entitlement = mailbox_repo.upsert_connected_mailbox(
        db,
        tenant_id=auth.principal.tenant_id,
        email=info.email,
        kind=body.kind,
        owner_oid=auth.principal.subject,
        graph_mailbox_id=info.graph_mailbox_id,
    )
    logger.info(
        "mailbox_connected kind=%s mailbox_profile_id=%s",
        body.kind.value,
        profile.id,
    )
    return ConnectMailboxResponse(
        mailbox_profile=_to_out(profile, db),
        role=MailboxRole(entitlement.role),
    )


@router.get("/{mailbox_profile_id}", response_model=MailboxProfileOut)
async def get_mailbox_profile(access: MailboxContentAccess, db: DbSession) -> MailboxProfileOut:
    return _to_out(access.profile, db)


@router.get("/{mailbox_profile_id}/inspect", response_model=ProfileInspectOut)
def inspect_mailbox_profile(
    access: MailboxContentAccess,
    db: DbSession,
    include_summary: bool = True,
) -> ProfileInspectOut:
    """User-facing profile inspector: stats, learned routes, hub-side behavior summary.

    Sync def on purpose: summary may call local Ollama (~45s) and must not block
    the asyncio loop the way an ``async def`` wrapping sync HTTP would.
    """
    return build_profile_inspect(
        db, access.profile, include_summary=include_summary
    )


@router.get("/{mailbox_profile_id}/content_stub", response_model=ContentStubOut)
async def content_stub(access: MailboxContentAccess) -> ContentStubOut:
    """AI/content-shaped endpoint used to prove personal admin-blind entitlement (FR6)."""
    return ContentStubOut(
        mailbox_profile_id=access.profile.id,
        kind=access.profile.kind,
    )
