from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AuthCtx, DbSession, MailboxContentAccess
from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.enums import HistoryProfileStatus, HistorySyncPhase
from app.domain.schemas import (
    AnalyzeRequest,
    IndexRequest,
    IndexResponse,
    SuggestionOut,
    SyncIndexRequest,
)
from app.services.analyze import run_analyze
from app.services.history_sync import profile_history_snapshot, request_history_sync
from app.services.inference import EMBEDDING_DIM, get_inference_client

router = APIRouter(prefix="/v1/mailbox_profiles", tags=["analyze"])

MAX_INDEX_ITEMS = 100


def _index_response(
    db: DbSession,
    *,
    mailbox_profile_id: str,
    indexed_count: int,
    started: bool = True,
) -> IndexResponse:
    snap = profile_history_snapshot(db, mailbox_profile_id)
    return IndexResponse(
        mailbox_profile_id=mailbox_profile_id,
        indexed_count=indexed_count,
        embedding_dim=EMBEDDING_DIM,
        total_chunks=snap["total_chunks"],
        history_status=snap["history_status"] or HistoryProfileStatus.NOT_STARTED,
        last_history_sync_at=snap["last_history_sync_at"],
        history_sync_error=snap["history_sync_error"],
        started=started,
        history_sync_phase=snap.get("history_sync_phase") or HistorySyncPhase.NOT_STARTED,
        history_messages_fetched=int(snap.get("history_messages_fetched") or 0),
        history_messages_target=int(snap.get("history_messages_target") or 0),
        history_sync_started_at=snap.get("history_sync_started_at"),
    )


@router.post("/{mailbox_profile_id}/analyze", response_model=SuggestionOut)
def analyze_message(
    mailbox_profile_id: str,
    body: AnalyzeRequest,
    access: MailboxContentAccess,
    auth: AuthCtx,
    db: DbSession,
) -> SuggestionOut:
    del mailbox_profile_id
    # History profile sync is owned by Outlook-open /index/sync — never block analyze.
    return run_analyze(
        db,
        mailbox_profile_id=access.profile.id,
        message_id=body.message_id,
        actor_oid=auth.principal.subject,
        user_assertion=auth.user_assertion,
        tenant_id=auth.principal.tenant_id,
        mailbox_kind=access.profile.kind,
        mailbox_email=access.profile.email,
        graph_mailbox_id=access.profile.graph_mailbox_id,
        body=body,
    )


@router.post("/{mailbox_profile_id}/index", response_model=IndexResponse)
def index_history(
    body: IndexRequest,
    access: MailboxContentAccess,
    db: DbSession,
) -> IndexResponse:
    if len(body.items) > MAX_INDEX_ITEMS:
        raise AppError(
            code="VALIDATION_ERROR",
            message=f"Index batch exceeds maximum of {MAX_INDEX_ITEMS} items.",
            status_code=422,
            retryable=False,
        )
    client = get_inference_client()
    count = ai_store.index_chunks(
        db,
        mailbox_profile_id=access.profile.id,
        items=body.items,
        embed_fn=client.embed,
    )
    return _index_response(db, mailbox_profile_id=access.profile.id, indexed_count=count)


@router.post("/{mailbox_profile_id}/index/sync", response_model=IndexResponse)
def sync_index_from_graph(
    body: SyncIndexRequest,
    access: MailboxContentAccess,
    auth: AuthCtx,
    db: DbSession,
) -> IndexResponse:
    """Bootstrap/refresh Sent Items embeddings for the mailbox history profile."""
    count, started = request_history_sync(
        db,
        mailbox_profile_id=access.profile.id,
        user_assertion=auth.user_assertion,
        tenant_id=auth.principal.tenant_id,
        mailbox_kind=access.profile.kind,
        mailbox_email=access.profile.email,
        graph_mailbox_id=access.profile.graph_mailbox_id,
        max_messages=body.max_messages,
        wait=body.wait,
    )
    # Refresh profile after sync (or after marking syncing for background).
    db.refresh(access.profile)
    return _index_response(
        db,
        mailbox_profile_id=access.profile.id,
        indexed_count=count,
        started=started,
    )
