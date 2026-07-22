from __future__ import annotations

from tests.conftest import ADMIN_OID, OTHER_OID, OWNER_OID, TENANT_A


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _connect(client, token: str, email: str, kind: str) -> dict:
    response = client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": email, "kind": kind},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_owner_can_access_personal_content(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    connected = _connect(app_client, token, "owner@contoso.com", "personal")
    profile_id = connected["mailbox_profile"]["id"]

    response = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}/content_stub",
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is True


def test_unentitled_user_gets_403(app_client, make_token):
    owner_token = make_token(oid=OWNER_OID)
    connected = _connect(app_client, owner_token, "owner@contoso.com", "personal")
    profile_id = connected["mailbox_profile"]["id"]

    other = make_token(oid=OTHER_OID)
    response = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}/content_stub",
        headers=_auth(other),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_denied_personal_content(app_client, make_token):
    """FR6 foundation: admin cannot read personal AI/content endpoints."""
    owner_token = make_token(oid=OWNER_OID)
    connected = _connect(app_client, owner_token, "personal@contoso.com", "personal")
    profile_id = connected["mailbox_profile"]["id"]

    from app.db.repositories import mailboxes as mailbox_repo
    from app.db.session import get_engine
    from app.domain.enums import MailboxRole
    from sqlalchemy.orm import Session

    with Session(get_engine()) as db:
        mailbox_repo.add_entitlement(
            db,
            mailbox_profile_id=profile_id,
            principal_oid=ADMIN_OID,
            role=MailboxRole.ADMIN,
        )

    admin_token = make_token(oid=ADMIN_OID)
    response = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}/content_stub",
        headers=_auth(admin_token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_shared_delegate_can_access_shared(app_client, make_token):
    owner_token = make_token(oid=OWNER_OID)
    connected = _connect(app_client, owner_token, "shared@contoso.com", "shared")
    profile_id = connected["mailbox_profile"]["id"]

    from app.db.repositories import mailboxes as mailbox_repo
    from app.db.session import get_engine
    from app.domain.enums import MailboxRole
    from sqlalchemy.orm import Session

    with Session(get_engine()) as db:
        mailbox_repo.add_entitlement(
            db,
            mailbox_profile_id=profile_id,
            principal_oid=OTHER_OID,
            role=MailboxRole.SHARED_DELEGATE,
        )

    delegate = make_token(oid=OTHER_OID)
    response = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}",
        headers=_auth(delegate),
    )
    assert response.status_code == 200
    assert response.json()["kind"] == "shared"
    assert response.json()["tenant_id"] == TENANT_A
