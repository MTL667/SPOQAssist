from __future__ import annotations

from tests.conftest import ADMIN_OID, OTHER_OID, OWNER_OID


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _connect(client, token: str, email: str, kind: str) -> str:
    response = client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": email, "kind": kind},
    )
    assert response.status_code == 200, response.text
    return response.json()["mailbox_profile"]["id"]


def test_analyze_returns_suggestion_dto(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "me@contoso.com", "personal")
    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-1",
            "include_draft": True,
            "subject": "Urgent invoice please route",
            "body": "Please forward this invoice ASAP",
            "sender": "vendor@example.com",
            "attachment_names": ["notes.txt", "virus.exe"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["suggestion_id"]
    assert body["category"]
    assert body["confidence"] in {"high", "medium", "low"}
    assert body["priority"]
    assert any(w["name"] == "virus.exe" for w in body["attachment_warnings"])
    # Keyword forward/route must not invent Contoso demo recipients
    # and must not set primary category to forward without a learned route.
    assert body.get("suggested_route") is None
    assert "forward" not in (body.get("actions") or [])
    assert body["category"] != "forward"
    blob = str(body).lower()
    assert "desk@contoso.com" not in blob
    assert "service desk" not in blob


def test_analyze_directed_mail_not_forward_without_route(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "kevin@contoso.com", "personal")
    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-directed",
            "include_draft": False,
            "subject": "Re: product adjustments",
            "body": (
                "Hi Kevin, a few things still need work for SPOQ: "
                "team needs report access, inspector upload, and ACEG invoicing. "
                "Can you pick this up?"
            ),
            "sender": "lieselot@example.com",
            "attachment_names": [],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("suggested_route") is None
    assert "forward" not in (body.get("actions") or [])
    assert body["category"] != "forward"


def test_analyze_meeting_no_invented_route(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "meet@contoso.com", "personal")
    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-meet",
            "include_draft": False,
            "subject": "Call next week?",
            "body": "Can we schedule a meeting to discuss?",
            "sender": "sales@example.com",
            "attachment_names": [],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "meeting"
    assert body.get("suggested_route") is None
    assert "forward" not in (body.get("actions") or [])


def test_index_and_retrieve_scoped(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    a = _connect(app_client, token, "a@contoso.com", "personal")
    b = _connect(app_client, token, "b@contoso.com", "personal")
    idx = app_client.post(
        f"/v1/mailbox_profiles/{a}/index",
        headers=_auth(token),
        json={"items": [{"message_id": "s1", "text": "Thanks for your invoice update"}]},
    )
    assert idx.status_code == 200
    assert idx.json()["embedding_dim"] == 1024
    assert idx.json()["indexed_count"] == 1

    # Analyze on profile A can use history; profile B must not see A's chunks via cross-id
    other_token = make_token(oid=OTHER_OID)
    denied = app_client.post(
        f"/v1/mailbox_profiles/{a}/index",
        headers=_auth(other_token),
        json={"items": [{"message_id": "x", "text": "leak"}]},
    )
    assert denied.status_code == 403
    assert b  # connected


def test_index_sync_from_sent_items(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "history@contoso.com", "personal")
    synced = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 10, "wait": True},
    )
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert body["indexed_count"] >= 1
    assert (body.get("total_chunks") or 0) >= body["indexed_count"]
    assert body["history_status"] == "ready"
    assert body.get("last_history_sync_at")

    chunks_after_first = body["total_chunks"]
    # Incremental second sync should not duplicate; typically indexes 0 new messages.
    again = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index/sync",
        headers=_auth(token),
        json={"max_messages": 10, "wait": True},
    )
    assert again.status_code == 200, again.text
    assert again.json()["history_status"] == "ready"
    assert again.json()["indexed_count"] == 0
    assert again.json()["total_chunks"] == chunks_after_first

    analyzed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-after-sync",
            "subject": "invoice question",
            "body": "Can you help with this invoice?",
            "sender": "vendor@example.com",
            "attachment_names": [],
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["history_status"] in {"limited", "sufficient"}
    assert analyzed.json()["draft"]
    assert analyzed.json().get("draft_error") in (None, "")


def test_analyze_does_not_require_history_sync(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "nosync@contoso.com", "personal")
    analyzed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-empty-history",
            "include_draft": True,
            "subject": "Hello",
            "body": "Need a reply without waiting for sync",
            "sender": "client@example.com",
            "attachment_names": [],
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["suggestion_id"]
    # Empty index → no grounded draft, but analyze must still succeed promptly.
    assert body["history_status"] == "none"
    assert body.get("draft") in (None, "")
    # Must not claim a draft timeout when history was never available.
    assert body.get("draft_error") in (None, "")
    profile = app_client.get(
        f"/v1/mailbox_profiles/{profile_id}",
        headers=_auth(token),
    )
    assert profile.status_code == 200
    # Analyze must not have started a Graph crawl / flipped status to syncing.
    assert profile.json()["history_status"] in {"not_started", "ready", "failed"}


def test_feedback_and_confirm_idempotent(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "send@contoso.com", "personal")
    analyzed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-2",
            "subject": "Hello",
            "body": "Need a reply",
            "sender": "client@example.com",
            "attachment_names": [],
        },
    )
    suggestion_id = analyzed.json()["suggestion_id"]

    fb = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/feedback",
        headers=_auth(token),
        json={"suggestion_id": suggestion_id, "outcome": "accept"},
    )
    assert fb.status_code == 200
    assert fb.json()["audit_id"]

    key = "idem-key-12345678"
    first = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/confirm-outbound",
        headers=_auth(token),
        json={
            "suggestion_id": suggestion_id,
            "idempotency_key": key,
            "action": "send",
            "recipients": ["client@example.com"],
            "body": "Thanks",
            "ai_assisted": True,
        },
    )
    assert first.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert first.json()["ai_disclosure_applied"] is True

    second = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/confirm-outbound",
        headers=_auth(token),
        json={
            "suggestion_id": suggestion_id,
            "idempotency_key": key,
            "action": "send",
            "recipients": ["client@example.com"],
            "body": "Thanks",
            "ai_assisted": True,
        },
    )
    assert second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert second.json()["graph_message_id"] == first.json()["graph_message_id"]


def test_shared_learning_cycle(app_client, make_token):
    owner = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, owner, "office@contoso.com", "shared")

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
    first = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(delegate),
        json={
            "message_id": "m-learn",
            "subject": "Please help",
            "body": "Question",
            "sender": "pattern@vendor.com",
            "attachment_names": [],
        },
    )
    suggestion_id = first.json()["suggestion_id"]
    reroute = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/feedback",
        headers=_auth(delegate),
        json={
            "suggestion_id": suggestion_id,
            "outcome": "reroute",
            "corrected_route_email": "finance@example.com",
            "corrected_route_name": "Finance",
            "teach": True,
        },
    )
    assert reroute.status_code == 200

    second = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(delegate),
        json={
            "message_id": "m-learn-2",
            "subject": "Another",
            "body": "Follow up",
            "sender": "pattern@vendor.com",
            "attachment_names": [],
        },
    )
    assert second.status_code == 200
    route = second.json()["suggested_route"]
    assert route is not None
    assert route["email"] == "finance@example.com"
    assert "forward" in (second.json().get("actions") or [])
    assert "contoso.com" not in str(second.json()).lower()


def test_admin_shared_settings_ok_personal_denied(app_client, make_token):
    owner = make_token(oid=OWNER_OID)
    personal = _connect(app_client, owner, "personal@contoso.com", "personal")
    shared = _connect(app_client, owner, "shared@contoso.com", "shared")

    from app.db.repositories import mailboxes as mailbox_repo
    from app.db.session import get_engine
    from app.domain.enums import MailboxRole
    from sqlalchemy.orm import Session

    with Session(get_engine()) as db:
        mailbox_repo.add_entitlement(
            db,
            mailbox_profile_id=shared,
            principal_oid=ADMIN_OID,
            role=MailboxRole.ADMIN,
        )
        mailbox_repo.add_entitlement(
            db,
            mailbox_profile_id=personal,
            principal_oid=ADMIN_OID,
            role=MailboxRole.ADMIN,
        )

    admin = make_token(oid=ADMIN_OID)
    ok = app_client.put(
        f"/v1/admin/mailbox_profiles/{shared}/ai_settings",
        headers=_auth(admin),
        json={"enabled": True, "auto_analyze": False, "notes": "pilot"},
    )
    assert ok.status_code == 200
    assert ok.json()["auto_analyze"] is False

    denied_settings = app_client.get(
        f"/v1/admin/mailbox_profiles/{personal}/ai_settings",
        headers=_auth(admin),
    )
    assert denied_settings.status_code == 403

    denied_content = app_client.post(
        f"/v1/mailbox_profiles/{personal}/analyze",
        headers=_auth(admin),
        json={"message_id": "x", "subject": "x", "body": "y", "sender": "z"},
    )
    assert denied_content.status_code == 403


def test_retention_purge(app_client, make_token):
    owner = make_token(oid=OWNER_OID)
    shared = _connect(app_client, owner, "retain@contoso.com", "shared")
    from app.db.repositories import mailboxes as mailbox_repo
    from app.db.session import get_engine
    from app.domain.enums import MailboxRole
    from sqlalchemy.orm import Session

    with Session(get_engine()) as db:
        mailbox_repo.add_entitlement(
            db,
            mailbox_profile_id=shared,
            principal_oid=ADMIN_OID,
            role=MailboxRole.ADMIN,
        )

    admin = make_token(oid=ADMIN_OID)
    app_client.put(
        f"/v1/admin/mailbox_profiles/{shared}/retention",
        headers=_auth(admin),
        json={"retain_days": 1, "purge_audit_with_indexes": False},
    )
    run = app_client.post(
        f"/v1/admin/mailbox_profiles/{shared}/retention/run",
        headers=_auth(admin),
    )
    assert run.status_code == 200
    assert "purged_chunks" in run.json()


def test_ops_health_has_inference_no_mail(app_client):
    response = app_client.get("/v1/ops/health_detail")
    assert response.status_code == 200
    body = response.json()
    assert "inference" in body
    assert "body" not in body
    assert "subject" not in str(body).lower() or "register" in body.get("register_doc", "")


def test_personal_reconnect_cannot_steal_owner(app_client, make_token):
    owner = make_token(oid=OWNER_OID)
    _connect(app_client, owner, "owned@contoso.com", "personal")
    other = make_token(oid=OTHER_OID)
    stolen = app_client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(other),
        json={"email": "owned@contoso.com", "kind": "personal"},
    )
    assert stolen.status_code == 403


def test_idempotency_conflict_on_payload_mismatch(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "idem@contoso.com", "personal")
    analyzed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={"message_id": "msg-idem", "subject": "Hi", "body": "Body", "sender": "a@b.com"},
    )
    suggestion_id = analyzed.json()["suggestion_id"]
    key = "idem-conflict-key-01"
    first = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/confirm-outbound",
        headers=_auth(token),
        json={
            "suggestion_id": suggestion_id,
            "idempotency_key": key,
            "action": "send",
            "recipients": ["a@b.com"],
            "body": "Thanks",
            "ai_assisted": True,
        },
    )
    assert first.status_code == 200
    conflict = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/confirm-outbound",
        headers=_auth(token),
        json={
            "suggestion_id": suggestion_id,
            "idempotency_key": key,
            "action": "send",
            "recipients": ["other@b.com"],
            "body": "Different",
            "ai_assisted": True,
        },
    )
    assert conflict.status_code == 409


def test_shared_ai_disabled_blocks_analyze(app_client, make_token):
    owner = make_token(oid=OWNER_OID)
    shared = _connect(app_client, owner, "disabled@contoso.com", "shared")
    from app.db.repositories import mailboxes as mailbox_repo
    from app.db.session import get_engine
    from app.domain.enums import MailboxRole
    from sqlalchemy.orm import Session

    with Session(get_engine()) as db:
        mailbox_repo.add_entitlement(
            db,
            mailbox_profile_id=shared,
            principal_oid=ADMIN_OID,
            role=MailboxRole.ADMIN,
        )
    admin = make_token(oid=ADMIN_OID)
    app_client.put(
        f"/v1/admin/mailbox_profiles/{shared}/ai_settings",
        headers=_auth(admin),
        json={"enabled": False, "auto_analyze": False, "notes": ""},
    )
    blocked = app_client.post(
        f"/v1/mailbox_profiles/{shared}/analyze",
        headers=_auth(owner),
        json={"message_id": "x", "subject": "x", "body": "y", "sender": "z@z.com"},
    )
    assert blocked.status_code == 403
