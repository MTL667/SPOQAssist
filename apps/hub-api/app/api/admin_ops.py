"""Non-content ops/auth connector config (FR36 / Stories 1.6 + 4.6)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import mailboxes as mailbox_repo
from app.domain.policies import assert_ops_config_access
from app.domain.schemas import OpsConnectorConfigIn, OpsConnectorConfigOut
from app.services.inference import get_inference_client

router = APIRouter(prefix="/v1/ops", tags=["ops"])


@router.get("/health_detail")
async def health_detail() -> dict:
    """Unauthenticated non-content detail for ops — never includes mail bodies."""
    settings = get_settings()
    inference = get_inference_client().health()
    hub_status = "ok"
    if inference.get("status") == "down":
        hub_status = "degraded"
    return {
        "status": hub_status,
        "service": "spoqassist-hub-api",
        "env": settings.spoq_env,
        "graph_mode": settings.graph_mode,
        "inference": inference,
        "entra_entity_count": len(settings.entra_entities),
        "configured_tenant_ids": [e.tenant_id for e in settings.entra_entities],
        "register_doc": "docs/processing-access-register.md",
    }


def _assert_ops_tenant(principal_tenant: str, tenant_id: str) -> None:
    if principal_tenant.lower() != tenant_id.lower():
        raise AppError(
            code="FORBIDDEN",
            message="Ops connector config is limited to your Entra tenant.",
            status_code=403,
            retryable=False,
        )


@router.get("/connector_config/{tenant_id}", response_model=OpsConnectorConfigOut)
async def get_connector_config(
    tenant_id: str,
    principal: CurrentPrincipal,
    db: DbSession,
) -> OpsConnectorConfigOut:
    settings = get_settings()
    assert_ops_config_access(principal, settings.ops_oids)
    _assert_ops_tenant(principal.tenant_id, tenant_id)
    row = mailbox_repo.get_ops_config(db, tenant_id)
    if row is None:
        return OpsConnectorConfigOut(
            tenant_id=tenant_id,
            graph_scopes=settings.graph_scopes,
            notes="",
        )
    return OpsConnectorConfigOut(
        tenant_id=row.tenant_id,
        graph_scopes=row.graph_scopes,
        notes=row.notes,
    )


@router.put("/connector_config", response_model=OpsConnectorConfigOut)
async def put_connector_config(
    body: OpsConnectorConfigIn,
    principal: CurrentPrincipal,
    db: DbSession,
) -> OpsConnectorConfigOut:
    settings = get_settings()
    assert_ops_config_access(principal, settings.ops_oids)
    _assert_ops_tenant(principal.tenant_id, body.tenant_id)
    if body.tenant_id.lower() not in {e.tenant_id.lower() for e in settings.entra_entities}:
        raise AppError(
            code="NOT_FOUND",
            message="Tenant is not a configured Entra entity.",
            status_code=404,
            retryable=False,
        )
    if "secret" in body.notes.lower() or "password" in body.graph_scopes.lower():
        raise AppError(
            code="VALIDATION_ERROR",
            message="Secrets must not be submitted through ops connector config.",
            status_code=422,
            retryable=False,
        )
    row = mailbox_repo.upsert_ops_config(
        db,
        tenant_id=body.tenant_id,
        graph_scopes=body.graph_scopes,
        notes=body.notes,
    )
    return OpsConnectorConfigOut(
        tenant_id=row.tenant_id,
        graph_scopes=row.graph_scopes,
        notes=row.notes,
    )
