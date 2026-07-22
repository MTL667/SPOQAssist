from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import ConnectionStatus, MailboxKind, MailboxRole
from app.domain.models import MailboxEntitlement, MailboxProfile, OpsConnectorConfig


def get_profile(db: Session, mailbox_profile_id: str) -> MailboxProfile | None:
    return db.get(MailboxProfile, mailbox_profile_id)


def get_entitlement(
    db: Session, *, mailbox_profile_id: str, principal_oid: str
) -> MailboxEntitlement | None:
    stmt = select(MailboxEntitlement).where(
        MailboxEntitlement.mailbox_profile_id == mailbox_profile_id,
        MailboxEntitlement.principal_oid == principal_oid,
    )
    return db.execute(stmt).scalar_one_or_none()


def find_by_tenant_email(db: Session, *, tenant_id: str, email: str) -> MailboxProfile | None:
    stmt = select(MailboxProfile).where(
        MailboxProfile.tenant_id == tenant_id,
        MailboxProfile.email == email.lower(),
    )
    return db.execute(stmt).scalar_one_or_none()


def upsert_connected_mailbox(
    db: Session,
    *,
    tenant_id: str,
    email: str,
    kind: MailboxKind,
    owner_oid: str,
    graph_mailbox_id: str,
) -> tuple[MailboxProfile, MailboxEntitlement]:
    existing = find_by_tenant_email(db, tenant_id=tenant_id, email=email.lower())
    if existing is None:
        profile = MailboxProfile(
            tenant_id=tenant_id,
            email=email.lower(),
            kind=kind.value,
            owner_oid=owner_oid,
            graph_mailbox_id=graph_mailbox_id,
            connection_status=ConnectionStatus.CONNECTED.value,
            connection_error=None,
        )
        db.add(profile)
        db.flush()
        role = MailboxRole.OWNER
    else:
        profile = existing
        # Do not steal ownership or flip personal↔shared behind the original owner.
        if profile.owner_oid != owner_oid:
            if profile.kind == MailboxKind.PERSONAL.value:
                raise AppError(
                    code="FORBIDDEN",
                    message="This personal mailbox is already owned by another user.",
                    status_code=403,
                    retryable=False,
                )
            if kind.value != profile.kind:
                raise AppError(
                    code="FORBIDDEN",
                    message="Mailbox kind cannot be changed by a non-owner reconnect.",
                    status_code=403,
                    retryable=False,
                )
            profile.graph_mailbox_id = graph_mailbox_id
            profile.connection_status = ConnectionStatus.CONNECTED.value
            profile.connection_error = None
            role = MailboxRole.SHARED_DELEGATE
        else:
            if kind.value != profile.kind and profile.connection_status == ConnectionStatus.CONNECTED.value:
                raise AppError(
                    code="VALIDATION_ERROR",
                    message="Mailbox kind is already set; disconnect before changing kind.",
                    status_code=422,
                    retryable=False,
                )
            profile.kind = kind.value
            profile.graph_mailbox_id = graph_mailbox_id
            profile.connection_status = ConnectionStatus.CONNECTED.value
            profile.connection_error = None
            role = MailboxRole.OWNER

    entitlement = get_entitlement(
        db, mailbox_profile_id=profile.id, principal_oid=owner_oid
    )
    if entitlement is None:
        entitlement = MailboxEntitlement(
            mailbox_profile_id=profile.id,
            principal_oid=owner_oid,
            role=role.value,
        )
        db.add(entitlement)
    elif profile.owner_oid == owner_oid:
        entitlement.role = MailboxRole.OWNER.value
    # Non-owner reconnect keeps existing role (or newly created shared_delegate).

    db.commit()
    db.refresh(profile)
    db.refresh(entitlement)
    return profile, entitlement


def mark_connect_failed(
    db: Session,
    *,
    tenant_id: str,
    email: str,
    kind: MailboxKind,
    owner_oid: str,
    error_message: str,
) -> MailboxProfile:
    existing = find_by_tenant_email(db, tenant_id=tenant_id, email=email.lower())
    if existing is None:
        profile = MailboxProfile(
            tenant_id=tenant_id,
            email=email.lower(),
            kind=kind.value,
            owner_oid=owner_oid,
            connection_status=ConnectionStatus.FAILED.value,
            connection_error=error_message[:512],
        )
        db.add(profile)
    else:
        profile = existing
        profile.connection_status = ConnectionStatus.FAILED.value
        profile.connection_error = error_message[:512]
    db.commit()
    db.refresh(profile)
    return profile


def add_entitlement(
    db: Session,
    *,
    mailbox_profile_id: str,
    principal_oid: str,
    role: MailboxRole,
) -> MailboxEntitlement:
    row = MailboxEntitlement(
        mailbox_profile_id=mailbox_profile_id,
        principal_oid=principal_oid,
        role=role.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_ops_config(db: Session, tenant_id: str) -> OpsConnectorConfig | None:
    stmt = select(OpsConnectorConfig).where(OpsConnectorConfig.tenant_id == tenant_id)
    return db.execute(stmt).scalar_one_or_none()


def upsert_ops_config(
    db: Session,
    *,
    tenant_id: str,
    graph_scopes: str,
    notes: str,
) -> OpsConnectorConfig:
    row = get_ops_config(db, tenant_id)
    if row is None:
        row = OpsConnectorConfig(
            tenant_id=tenant_id, graph_scopes=graph_scopes, notes=notes
        )
        db.add(row)
    else:
        row.graph_scopes = graph_scopes
        row.notes = notes
    db.commit()
    db.refresh(row)
    return row
