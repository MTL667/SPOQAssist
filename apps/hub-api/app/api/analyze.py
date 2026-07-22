from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AuthCtx, DbSession, MailboxContentAccess
from app.core.errors import AppError
from app.db.repositories import ai_store
from app.domain.schemas import AnalyzeRequest, IndexRequest, IndexResponse, SuggestionOut
from app.services.analyze import run_analyze
from app.services.inference import EMBEDDING_DIM, get_inference_client

router = APIRouter(prefix="/v1/mailbox_profiles", tags=["analyze"])

MAX_INDEX_ITEMS = 100


@router.post("/{mailbox_profile_id}/messages/{message_id}/analyze", response_model=SuggestionOut)
async def analyze_message(
    mailbox_profile_id: str,
    message_id: str,
    body: AnalyzeRequest,
    access: MailboxContentAccess,
    auth: AuthCtx,
    db: DbSession,
) -> SuggestionOut:
    del mailbox_profile_id
    return run_analyze(
        db,
        mailbox_profile_id=access.profile.id,
        message_id=message_id,
        actor_oid=auth.principal.subject,
        user_assertion=auth.user_assertion,
        tenant_id=auth.principal.tenant_id,
        mailbox_kind=access.profile.kind,
        mailbox_email=access.profile.email,
        graph_mailbox_id=access.profile.graph_mailbox_id,
        body=body,
    )


@router.post("/{mailbox_profile_id}/index", response_model=IndexResponse)
async def index_history(
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
    return IndexResponse(
        mailbox_profile_id=access.profile.id,
        indexed_count=count,
        embedding_dim=EMBEDDING_DIM,
    )
