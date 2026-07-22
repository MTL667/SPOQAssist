"""FastAPI dependencies — auth principal + mailbox entitlement gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import AuthenticatedPrincipal, validate_access_token
from app.db.repositories import mailboxes as mailbox_repo
from app.db.session import get_db
from app.domain.models import MailboxEntitlement, MailboxProfile
from app.domain.policies import assert_mailbox_content_access

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller. user_assertion is for hub-side Graph OBO only — never log it."""

    principal: AuthenticatedPrincipal
    user_assertion: str


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AppError(
            code="UNAUTHENTICATED",
            message="Invalid or missing credentials.",
            status_code=401,
            retryable=False,
        )
    principal = validate_access_token(credentials.credentials)
    return AuthContext(principal=principal, user_assertion=credentials.credentials)


async def get_current_principal(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthenticatedPrincipal:
    return auth.principal


CurrentPrincipal = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]
AuthCtx = Annotated[AuthContext, Depends(get_auth_context)]
DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class MailboxAccess:
    profile: MailboxProfile
    entitlement: MailboxEntitlement
    principal: AuthenticatedPrincipal


def require_mailbox_content_access(
    mailbox_profile_id: str,
    principal: CurrentPrincipal,
    db: DbSession,
) -> MailboxAccess:
    profile = mailbox_repo.get_profile(db, mailbox_profile_id)
    if profile is None:
        raise AppError(
            code="NOT_FOUND",
            message="Mailbox profile not found.",
            status_code=404,
            retryable=False,
        )
    entitlement = mailbox_repo.get_entitlement(
        db, mailbox_profile_id=profile.id, principal_oid=principal.subject
    )
    allowed = assert_mailbox_content_access(principal, profile, entitlement)
    return MailboxAccess(profile=profile, entitlement=allowed, principal=principal)


MailboxContentAccess = Annotated[MailboxAccess, Depends(require_mailbox_content_access)]
