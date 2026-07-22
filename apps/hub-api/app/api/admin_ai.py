from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.core.errors import AppError
from app.db.repositories import ai_store, mailboxes as mailbox_repo
from app.domain.policies import assert_shared_admin_config_access
from app.domain.schemas import (
    RetentionPolicyIn,
    RetentionPolicyOut,
    RetentionRunOut,
    SharedAiSettingsIn,
    SharedAiSettingsOut,
)
from app.services.retention import get_or_default_policy, run_retention

router = APIRouter(prefix="/v1/admin", tags=["admin_ai"])


def _load_shared_admin(db, principal, mailbox_profile_id: str):
    profile = mailbox_repo.get_profile(db, mailbox_profile_id)
    if profile is None:
        raise AppError(code="NOT_FOUND", message="Mailbox profile not found.", status_code=404)
    entitlement = mailbox_repo.get_entitlement(
        db, mailbox_profile_id=profile.id, principal_oid=principal.subject
    )
    assert_shared_admin_config_access(principal, profile, entitlement)
    return profile


@router.get(
    "/mailbox_profiles/{mailbox_profile_id}/ai_settings",
    response_model=SharedAiSettingsOut,
)
async def get_ai_settings(
    mailbox_profile_id: str,
    principal: CurrentPrincipal,
    db: DbSession,
) -> SharedAiSettingsOut:
    profile = _load_shared_admin(db, principal, mailbox_profile_id)
    row = ai_store.get_ai_settings(db, profile.id)
    if row is None:
        return SharedAiSettingsOut(
            mailbox_profile_id=profile.id,
            enabled=True,
            auto_analyze=True,
            default_forward_hint=None,
            notes="",
        )
    return SharedAiSettingsOut(
        mailbox_profile_id=profile.id,
        enabled=row.enabled,
        auto_analyze=row.auto_analyze,
        default_forward_hint=row.default_forward_hint,
        notes=row.notes,
    )


@router.put(
    "/mailbox_profiles/{mailbox_profile_id}/ai_settings",
    response_model=SharedAiSettingsOut,
)
async def put_ai_settings(
    mailbox_profile_id: str,
    body: SharedAiSettingsIn,
    principal: CurrentPrincipal,
    db: DbSession,
) -> SharedAiSettingsOut:
    profile = _load_shared_admin(db, principal, mailbox_profile_id)
    row = ai_store.upsert_ai_settings(
        db,
        mailbox_profile_id=profile.id,
        enabled=body.enabled,
        auto_analyze=body.auto_analyze,
        default_forward_hint=body.default_forward_hint,
        notes=body.notes,
    )
    return SharedAiSettingsOut(
        mailbox_profile_id=row.mailbox_profile_id,
        enabled=row.enabled,
        auto_analyze=row.auto_analyze,
        default_forward_hint=row.default_forward_hint,
        notes=row.notes,
    )


@router.get(
    "/mailbox_profiles/{mailbox_profile_id}/retention",
    response_model=RetentionPolicyOut,
)
async def get_retention(
    mailbox_profile_id: str,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RetentionPolicyOut:
    profile = _load_shared_admin(db, principal, mailbox_profile_id)
    row = get_or_default_policy(db, profile.id)
    return RetentionPolicyOut(
        mailbox_profile_id=row.mailbox_profile_id,
        retain_days=row.retain_days,
        purge_audit_with_indexes=row.purge_audit_with_indexes,
    )


@router.put(
    "/mailbox_profiles/{mailbox_profile_id}/retention",
    response_model=RetentionPolicyOut,
)
async def put_retention(
    mailbox_profile_id: str,
    body: RetentionPolicyIn,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RetentionPolicyOut:
    profile = _load_shared_admin(db, principal, mailbox_profile_id)
    row = ai_store.upsert_retention(
        db,
        mailbox_profile_id=profile.id,
        retain_days=body.retain_days,
        purge_audit_with_indexes=body.purge_audit_with_indexes,
    )
    return RetentionPolicyOut(
        mailbox_profile_id=row.mailbox_profile_id,
        retain_days=row.retain_days,
        purge_audit_with_indexes=row.purge_audit_with_indexes,
    )


@router.post(
    "/mailbox_profiles/{mailbox_profile_id}/retention/run",
    response_model=RetentionRunOut,
)
async def retention_run(
    mailbox_profile_id: str,
    principal: CurrentPrincipal,
    db: DbSession,
) -> RetentionRunOut:
    profile = _load_shared_admin(db, principal, mailbox_profile_id)
    stats = run_retention(db, profile.id)
    return RetentionRunOut(mailbox_profile_id=profile.id, **stats)
