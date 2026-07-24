from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tests.conftest import OWNER_OID

TZ = ZoneInfo("Europe/Brussels")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _connect(client, token: str, email: str, kind: str = "personal") -> str:
    response = client.post(
        "/v1/mailbox_profiles/connect",
        headers=_auth(token),
        json={"email": email, "kind": kind},
    )
    assert response.status_code == 200, response.text
    return response.json()["mailbox_profile"]["id"]


def _index_history(client, token: str, profile_id: str) -> None:
    idx = client.post(
        f"/v1/mailbox_profiles/{profile_id}/index",
        headers=_auth(token),
        json={
            "items": [
                {
                    "message_id": "sent-1",
                    "text": "Thanks for your note. Happy to schedule a call next week.",
                },
                {
                    "message_id": "sent-2",
                    "text": "Please find a couple of slots that work on my side.",
                },
            ]
        },
    )
    assert idx.status_code == 200, idx.text


def test_meeting_free_window_proposes_slots(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "free@contoso.com")
    _index_history(app_client, token, profile_id)

    from app.services.mail_graph import StubMailGraphClient, set_mail_graph_client

    stub = StubMailGraphClient()
    set_mail_graph_client(stub)

    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-meet-free",
            "include_draft": True,
            "subject": "Moment vóór 31/8?",
            "body": "Can we schedule a meeting before 31/8 for the opleiding?",
            "sender": "lieselot@example.com",
            "attachment_names": [],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "meeting"
    assert body["proposed_slots"], body
    assert len(body["proposed_slots"]) <= 3
    assert body.get("availability_note") in (None, "")
    assert stub.get_busy_calls, "calendar consult must run for meeting+draft"
    assert body.get("draft")
    assert "Available time:" in (body["draft"] or "")
    assert "schedule" in (body.get("actions") or [])


def test_meeting_blocked_august_proposes_outside(app_client, make_token, monkeypatch):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "busy-august@contoso.com")
    _index_history(app_client, token, profile_id)

    from app.services.mail_graph import StubMailGraphClient, set_mail_graph_client

    stub = StubMailGraphClient()
    set_mail_graph_client(stub)

    monkeypatch.setattr(
        "app.services.analyze.parse_meeting_window",
        lambda subject, body, now=None: (
            datetime(2026, 8, 1, 9, 0, tzinfo=TZ),
            datetime(2026, 8, 31, 17, 0, tzinfo=TZ),
        ),
    )

    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-meet-blocked",
            "include_draft": True,
            "subject": "Moment vóór 31/8 voor opleiding",
            "body": "Can we schedule a meeting before August 31 for training?",
            "sender": "lieselot@example.com",
            "attachment_names": [],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "meeting"
    assert body.get("availability_note")
    assert "unavailable" in body["availability_note"].lower()
    assert body["proposed_slots"], body
    for slot in body["proposed_slots"]:
        start = datetime.fromisoformat(slot["start"])
        # Slots must be outside the August block.
        assert start.month != 8 or start.year != 2026
    draft = body.get("draft") or ""
    assert "unavailable" in draft.lower() or "Available time:" in draft


def test_non_meeting_skips_calendar(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "fyi@contoso.com")
    _index_history(app_client, token, profile_id)

    from app.services.mail_graph import StubMailGraphClient, set_mail_graph_client

    stub = StubMailGraphClient()
    set_mail_graph_client(stub)

    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-fyi",
            "include_draft": True,
            "subject": "FYI newsletter",
            "body": "Just an FYI update, no action needed.",
            "sender": "news@example.com",
            "attachment_names": [],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] != "meeting"
    assert stub.get_busy_calls == []
    assert body.get("proposed_slots") in (None, [])


def test_confirm_schedule_creates_event(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "sched@contoso.com")
    _index_history(app_client, token, profile_id)

    from app.services.mail_graph import StubMailGraphClient, set_mail_graph_client

    stub = StubMailGraphClient()
    set_mail_graph_client(stub)

    analyzed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-sched",
            "include_draft": True,
            "subject": "Inventaris opleiding call",
            "body": "Can we schedule a meeting next week?",
            "sender": "lieselot@example.com",
            "attachment_names": [],
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["proposed_slots"]
    slot = body["proposed_slots"][0]
    suggestion_id = body["suggestion_id"]

    scheduled = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/confirm-schedule",
        headers=_auth(token),
        json={
            "suggestion_id": suggestion_id,
            "slot_start": slot["start"],
            "slot_end": slot["end"],
            "idempotency_key": "sched-key-12345678",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    out = scheduled.json()
    assert out["status"] == "ok"
    assert out["graph_event_id"]
    assert out["idempotent_replay"] is False
    assert len(stub.create_event_calls) == 1
    assert "lieselot@example.com" in stub.create_event_calls[0]["attendees"]

    again = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/confirm-schedule",
        headers=_auth(token),
        json={
            "suggestion_id": suggestion_id,
            "slot_start": slot["start"],
            "slot_end": slot["end"],
            "idempotency_key": "sched-key-12345678",
        },
    )
    assert again.status_code == 200
    assert again.json()["idempotent_replay"] is True
    assert len(stub.create_event_calls) == 1


def test_calendar_consent_unavailable_on_consult(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "owner@calendar-consent.example")
    _index_history(app_client, token, profile_id)

    from app.services.mail_graph import StubMailGraphClient, set_mail_graph_client

    stub = StubMailGraphClient()
    set_mail_graph_client(stub)

    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-consent",
            "include_draft": True,
            "subject": "Call next week?",
            "body": "Can we schedule a meeting?",
            "sender": "sales@example.com",
            "attachment_names": [],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "meeting"
    assert body.get("proposed_slots") in (None, [])
    why_codes = {w["code"] for w in body.get("why") or []}
    assert "calendar_unavailable" in why_codes
    # Draft may still exist without invented holds / availability lines.
    draft = body.get("draft") or ""
    assert "Available time:" not in draft


def test_calendar_consent_fail_on_schedule(app_client, make_token):
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "ok@contoso.com")
    _index_history(app_client, token, profile_id)

    from app.services.mail_graph import StubMailGraphClient, set_mail_graph_client

    stub = StubMailGraphClient()
    set_mail_graph_client(stub)

    analyzed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-sched-consent",
            "include_draft": True,
            "subject": "Meeting please",
            "body": "Can we schedule a meeting tomorrow?",
            "sender": "peer@example.com",
            "attachment_names": [],
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["proposed_slots"]
    slot = body["proposed_slots"][0]

    # Flip consent trap after analyze consult succeeded.
    stub.stub_calendar_consent_fail = True
    failed = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/confirm-schedule",
        headers=_auth(token),
        json={
            "suggestion_id": body["suggestion_id"],
            "slot_start": slot["start"],
            "slot_end": slot["end"],
            "idempotency_key": "sched-consent-12345678",
        },
    )
    assert failed.status_code == 403, failed.text
    assert failed.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_has_scheduling_intent_unit():
    from app.services.scheduling import has_scheduling_intent

    # True: genuine scheduling verbs/nouns/phrases (NL+EN).
    assert has_scheduling_intent(
        "Re: Inventaris",
        "Kunnen we een moment voorzien voor 31/8 om Robbe opleiding te geven?",
    )
    assert has_scheduling_intent("", "Can we schedule a meeting next week?")
    assert has_scheduling_intent("Vergadering volgende week", "")
    assert has_scheduling_intent("", "Wanneer past het jou?")
    assert has_scheduling_intent("", "Laat gerust je beschikbaarheid weten.")
    assert has_scheduling_intent("", "Kan je dit inplannen?")
    assert has_scheduling_intent("", "Can we reschedule for next week?")
    assert has_scheduling_intent("", "Ben je beschikbaar volgende week?")
    assert has_scheduling_intent("", "Are you available next Tuesday?")

    # False: a mere date or unrelated content must NOT trigger a consult.
    assert not has_scheduling_intent("Factuur 123", "De factuur vervalt op 31/8. Gelieve te betalen.")
    assert not has_scheduling_intent("Nieuwsbrief", "Hier is onze update voor juli 2026.")
    assert not has_scheduling_intent("", "Bedankt voor je hulp gisteren.")
    # Review-hardening: broad tokens must not fire on non-scheduling phrasing.
    assert not has_scheduling_intent("", "I'm available to help if you need anything.")
    assert not has_scheduling_intent("Voorraad", "Het product is nu beschikbaar in de webshop.")
    assert not has_scheduling_intent("Ads", "Check our Facebook ads campaign results.")
    assert not has_scheduling_intent("Doc", "Kevin invited you to view the document.")


def test_scheduling_intent_fires_consult_when_not_category_meeting(app_client, make_token):
    """Screenshot case: mail labelled action_required but with scheduling intent."""
    token = make_token(oid=OWNER_OID)
    profile_id = _connect(app_client, token, "mislabel@contoso.com")
    _index_history(app_client, token, profile_id)

    from app.services.mail_graph import StubMailGraphClient, set_mail_graph_client

    stub = StubMailGraphClient()
    set_mail_graph_client(stub)

    response = app_client.post(
        f"/v1/mailbox_profiles/{profile_id}/analyze",
        headers=_auth(token),
        json={
            "message_id": "msg-mislabel",
            "include_draft": True,
            "subject": "Re: Inventaris 2047111",
            "body": (
                "Kunnen we een moment voorzien voor 31/8 om Robbe opleiding te geven "
                "voor het gebruik van de app voor inventarisatie aub?"
            ),
            "sender": "lieselot@example.com",
            "attachment_names": [],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The stub classifier does NOT label this "meeting" (no meeting keyword),
    # but scheduling intent must still trigger the calendar consult.
    assert body["category"] != "meeting"
    assert stub.get_busy_calls, "calendar consult must run on scheduling intent"
    assert body["proposed_slots"], body
    assert "schedule" in (body.get("actions") or [])
    assert "Available time:" in (body.get("draft") or "")


def test_parse_and_find_free_slots_unit():
    from app.services.scheduling import BusyInterval, find_free_slots, parse_meeting_window

    now = datetime(2026, 7, 24, 10, 0, tzinfo=TZ)
    start, end = parse_meeting_window(
        "Moment vóór 31/8",
        "afspraak voor opleiding",
        now=now,
    )
    assert start.date() == now.date()
    assert end.date().month == 8 and end.date().day == 31

    busy = [
        BusyInterval(
            start=datetime(2026, 8, 1, 0, 0, tzinfo=TZ),
            end=datetime(2026, 9, 1, 0, 0, tzinfo=TZ),
        )
    ]
    # Window entirely inside August block.
    plan = find_free_slots(
        busy,
        datetime(2026, 8, 3, 9, 0, tzinfo=TZ),
        datetime(2026, 8, 28, 17, 0, tzinfo=TZ),
        now=now,
    )
    assert plan.requested_window_blocked is True
    assert plan.unavailability_note
    assert plan.slots
    assert all("2026-08-" not in s.start_iso for s in plan.slots)
