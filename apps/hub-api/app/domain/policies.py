"""Mailbox authorization — enforced on the hub (NFR-S3 / FR3–FR6)."""

from __future__ import annotations

from app.core.errors import AppError
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import MailboxKind, MailboxRole
from app.domain.models import MailboxEntitlement, MailboxProfile


CONTENT_ROLES_SHARED = frozenset(
    {
        MailboxRole.OWNER,
        MailboxRole.SHARED_DELEGATE,
        MailboxRole.ADMIN,
    }
)

ADMIN_SHARED_CONFIG_ROLES = frozenset({MailboxRole.ADMIN, MailboxRole.OWNER})


def _forbidden(message: str = "Not entitled to this mailbox.") -> AppError:
    return AppError(
        code="FORBIDDEN",
        message=message,
        status_code=403,
        retryable=False,
    )


def assert_mailbox_content_access(
    principal: AuthenticatedPrincipal,
    profile: MailboxProfile,
    entitlement: MailboxEntitlement | None,
) -> MailboxEntitlement:
    """Authorize AI/content access for a mailbox profile.

    Personal: owner only (admins denied — FR5/FR6).
    Shared: owner, shared_delegate, or admin.
    """
    if profile.tenant_id.lower() != principal.tenant_id.lower():
        raise _forbidden()

    if entitlement is None:
        raise _forbidden()

    if entitlement.principal_oid != principal.subject:
        raise _forbidden()

    role = MailboxRole(entitlement.role)

    if profile.kind == MailboxKind.PERSONAL:
        if role != MailboxRole.OWNER or profile.owner_oid != principal.subject:
            raise _forbidden(
                "Personal mailbox content is available only to the mailbox owner."
            )
        return entitlement

    if role not in CONTENT_ROLES_SHARED:
        raise _forbidden()
    return entitlement


def assert_shared_admin_config_access(
    principal: AuthenticatedPrincipal,
    profile: MailboxProfile,
    entitlement: MailboxEntitlement | None,
) -> MailboxEntitlement:
    """FR4 — admins may configure AI settings for shared mailboxes only."""
    if profile.kind != MailboxKind.SHARED:
        raise _forbidden("AI settings are admin-configurable only for shared mailboxes.")
    if entitlement is None or entitlement.principal_oid != principal.subject:
        raise _forbidden()
    role = MailboxRole(entitlement.role)
    if role not in ADMIN_SHARED_CONFIG_ROLES:
        raise _forbidden("Shared AI settings require admin or owner role.")
    if profile.tenant_id.lower() != principal.tenant_id.lower():
        raise _forbidden()
    return entitlement


def assert_ops_config_access(principal: AuthenticatedPrincipal, ops_oids: set[str]) -> None:
    if principal.subject in ops_oids:
        return
    raise AppError(
        code="FORBIDDEN",
        message="Ops configuration requires an authorized operator.",
        status_code=403,
        retryable=False,
    )
