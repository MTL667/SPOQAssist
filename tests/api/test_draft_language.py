from __future__ import annotations

from app.services.draft_language import (
    detect_reply_language,
    fallback_ack_draft,
    is_thread_parrot,
)


def test_detect_dutch_latest():
    latest = "Beste,\n\nAl nieuws van?\n\nMet vriendelijke groeten,"
    assert detect_reply_language(latest) == "nl"


def test_detect_english_latest():
    latest = "Hi,\n\nAny update on this?\n\nThanks,"
    assert detect_reply_language(latest) == "en"


def test_detect_falls_back_to_profile_dutch_hints():
    latest = "OK."
    profile = "Tone is professional yet informal, with frequent use of Dutch phrases like 'Dag collega's'."
    assert detect_reply_language(latest, profile) == "nl"


def test_dutch_fallback_not_english_stub():
    draft = fallback_ack_draft(lang="nl", greet_name="Jean")
    assert "Bedankt voor je bericht" in draft
    assert "Thanks for your message" not in draft
    assert "Dag Jean" in draft


def test_english_fallback_remains():
    draft = fallback_ack_draft(lang="en", greet_name="Jean")
    assert "Thanks for your message" in draft
    assert "Hi Jean" in draft


def test_parrot_keeps_draft_with_common_dutch_closing():
    draft = (
        "Dag Jean,\n\n"
        "Ik kijk dit even na en laat iets weten.\n\n"
        "Met vriendelijke groet"
    )
    thread = (
        "-----Original Message-----\n"
        "Top dank u, ook nog op haha\n\n"
        "Met vriendelijke groet,\n"
        "Kevin Van Hoecke\n"
    )
    assert not is_thread_parrot(draft, thread_context=thread, style_snippets=[])


def test_parrot_rejects_long_verbatim_owner_line():
    distinctive = (
        "We hebben de laptop al besteld en de factuur volgt later deze week"
    )
    draft = f"Dag Jean,\n\n{distinctive}.\n\nMet vriendelijke groet"
    thread = f"-----Original Message-----\n{distinctive}.\n\nMet vriendelijke groet,\nKevin\n"
    assert is_thread_parrot(draft, thread_context=thread, style_snippets=[])


def test_parrot_rejects_short_distinctive_18_char_paste():
    distinctive = "laptop al besteld hier"
    assert len(distinctive) >= 18
    draft = f"Dag Jean,\n\n{distinctive}\n\nMet vriendelijke groet"
    thread = f"-----Original Message-----\n{distinctive}\nKevin\n"
    assert is_thread_parrot(draft, thread_context=thread, style_snippets=[])
