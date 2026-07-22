from __future__ import annotations

from app.services.thread_split import draft_context_blocks, split_thread_body
from tests.conftest import OWNER_OID


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


THREAD_FIXTURE = """Beste,

Al nieuws van?

Met vriendelijke groeten,

-----Original Message-----
From: Kevin Van Hoecke <kevinvanhoecke@hertbelgium.be>
Sent: Wednesday, July 15, 2026
To: Jean-Francois Steux <jean@aceg.be>
Subject: Re: Laptop

Top dank u, ook nog op haha

Met vriendelijke groet,
Kevin Van Hoecke
"""


def test_split_latest_vs_quoted_thread():
    parts = split_thread_body(THREAD_FIXTURE)
    assert parts.split is True
    assert "Al nieuws van?" in parts.latest_message
    assert "Top dank u" not in parts.latest_message
    assert "Top dank u" in parts.thread_context


def test_split_single_mail_no_markers():
    parts = split_thread_body("Hallo,\n\nKunnen we morgen bellen?\n\nGroeten")
    assert parts.split is False
    assert "Kunnen we morgen bellen?" in parts.latest_message
    assert parts.thread_context == ""


def test_split_short_latest_before_original_message():
    body = "Beste,\n\nAl nieuws van?\n\n-----Original Message-----\nTop dank u, ook nog op haha\n"
    parts = split_thread_body(body)
    assert parts.split is True
    assert "Al nieuws van?" in parts.latest_message
    assert "Top dank u" not in parts.latest_message
    assert "Top dank u" in parts.thread_context


def test_draft_context_keeps_full_body_and_distinct_latest():
    latest, full = draft_context_blocks(THREAD_FIXTURE)
    assert "Al nieuws van?" in latest
    assert "Top dank u" not in latest
    # Full mail remains available as context (including older lines).
    assert full == THREAD_FIXTURE.strip() or full.startswith("Beste,")
    assert "Top dank u, ook nog op haha" in full
    assert "Al nieuws van?" in full


def test_analyze_draft_targets_latest_not_quoted_owner_line(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "thread@contoso.com", "personal")
    indexed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/index",
        headers=_auth(token),
        json={
            "items": [
                {
                    "message_id": "sent-thread-1",
                    "text": "Subject: Re: Laptop\nTop dank u, ook nog op haha\nGroeten",
                }
            ]
        },
    )
    assert indexed.status_code == 200, indexed.text

    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-thread-1",
            "include_draft": True,
            "subject": "Re: Laptop",
            "body": THREAD_FIXTURE,
            "sender": "jean@aceg.be",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    draft = body.get("draft") or ""
    assert draft
    assert "Top dank u, ook nog op haha" not in draft
    assert "Al nieuws" in draft or "nieuws" in draft.lower()
    assert any(w.get("code") == "thread_latest" for w in body.get("why") or [])
