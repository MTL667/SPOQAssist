"""Reply language detection and language-aware draft fallbacks (NL/EN)."""

from __future__ import annotations

import re
from typing import Literal

ReplyLang = Literal["nl", "en"]

# Word-ish tokens that lean Dutch vs English in short mail bodies.
_NL_MARKERS = (
    "het",
    "een",
    "van",
    "voor",
    "niet",
    "met",
    "zijn",
    "jij",
    "jouw",
    "jullie",
    "bedankt",
    "dank",
    "dankjewel",
    "alstublieft",
    "alsjeblieft",
    "groet",
    "groeten",
    "vriendelijke",
    "beste",
    "dag",
    "hoi",
    "hallo",
    "nieuws",
    "bericht",
    "kunnen",
    "graag",
    "morgen",
    "vandaag",
    "volgende",
    "bijlage",
    "doorsturen",
    "afspraak",
    "vraag",
    "antwoord",
    "even",
    "nog",
    "ook",
    "maar",
    "want",
    "dus",
    "hierbij",
    "mvg",
)

_EN_MARKERS = (
    "the",
    "and",
    "you",
    "your",
    "thanks",
    "thank",
    "please",
    "regards",
    "hello",
    "hi",
    "dear",
    "meeting",
    "attached",
    "following",
    "could",
    "would",
    "should",
    "about",
    "from",
    "with",
    "this",
    "that",
    "have",
    "will",
    "looking",
    "forward",
)

_PROFILE_NL_HINTS = (
    "dutch",
    "nederlands",
    "dag collega's",
    "dag collega",
    "met vriendelijke",
    "vriendelijke groet",
    "groeten",
    "beste,",
    "hoi",
)

# Normalized phrases that are normal openers/closers — must not trigger parrot reject alone.
_BOILERPLATE_PHRASES = frozenset(
    {
        "met vriendelijke groet",
        "met vriendelijke groeten",
        "vriendelijke groeten",
        "vriendelijke groet",
        "kind regards",
        "with kind regards",
        "best regards",
        "many thanks",
        "thanks for your message",
        "thanks for your note",
        "bedankt voor je bericht",
        "bedankt voor uw bericht",
        "bedankt voor je mail",
        "dank voor je bericht",
        "hi there",
        "dear all",
        "beste allen",
        "beste collega",
        "beste collega's",
        "dag collega's",
        "dag collega",
    }
)

_BOILERPLATE_PREFIXES = (
    "met vriendelijke",
    "kind regards",
    "with kind regards",
    "best regards",
    "bedankt voor",
    "thanks for your",
    "dank voor",
)


def detect_reply_language(
    latest: str,
    profile_text: str | None = None,
) -> ReplyLang:
    """Pick nl/en from LATEST segment; profile Dutch habits are a secondary signal."""
    text = (latest or "").lower()
    tokens = set(re.findall(r"[a-zà-ÿ']+", text, flags=re.IGNORECASE))
    nl_hits = sum(1 for t in _NL_MARKERS if t in tokens)
    en_hits = sum(1 for t in _EN_MARKERS if t in tokens)
    # Dutch-only pronouns. Do not boost on shared "we" (also English).
    if re.search(r"\b(ik|je|jij|u|uw|jullie|wij)\b", text):
        nl_hits += 2
    if re.search(r"\b(i|we|you|your)\b", text):
        en_hits += 1

    if nl_hits >= en_hits + 1 and nl_hits >= 1:
        return "nl"
    if en_hits >= nl_hits + 1 and en_hits >= 1:
        return "en"

    profile = (profile_text or "").lower()
    if any(h in profile for h in _PROFILE_NL_HINTS):
        return "nl"
    return "en"


def stub_reply_draft(
    *,
    lang: ReplyLang,
    greet_name: str,
    latest_snippet: str,
) -> str:
    """Deterministic stub draft that still references the latest ask (tests/CI)."""
    snippet = (latest_snippet or "").replace("\n", " ").strip()[:120]
    if lang == "nl":
        name = (greet_name or "").strip() or "daar"
        return (
            f"Dag {name},\n\n"
            f"Bedankt voor je bericht — over “{snippet}”, ik kom erop terug.\n\n"
            "Met vriendelijke groet"
        )
    name = (greet_name or "").strip() or "there"
    return (
        f"Hi {name},\n\n"
        f"Thanks for your note — regarding “{snippet}”, I will follow up shortly.\n\n"
        "Best regards"
    )


def is_boilerplate_parrot_phrase(phrase: str) -> bool:
    """True when a draft n-gram is a common greeting/closing, not distinctive content."""
    norm = re.sub(r"\s+", " ", (phrase or "").strip().lower())
    if not norm:
        return True
    if norm in _BOILERPLATE_PHRASES:
        return True
    if any(norm.startswith(p) for p in _BOILERPLATE_PREFIXES):
        return True
    # Very short greeting lines: "dag jean," / "hoi jean"
    if re.fullmatch(r"(dag|hoi|hallo|hi|dear|beste)\s+[\w'-]+,?", norm):
        return True
    return False


def _normalize_for_parrot(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9à-ÿ\s]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def is_thread_parrot(
    draft: str,
    *,
    thread_context: str,
    style_snippets: list[str],
) -> bool:
    """True if draft pastes a distinctive phrase from the incoming/quoted thread.

    Style snippets are intentionally excluded: the draft prompt asks the model to
    match the owner's Sent tone, so short overlaps with style examples are expected
    and must not wipe an otherwise usable reply.
    """
    del style_snippets  # kept in signature for call-site compatibility
    if not (draft or "").strip():
        return False
    blob = _normalize_for_parrot(thread_context or "")
    if len(blob) < 20:
        return False
    norm_draft = _normalize_for_parrot(draft)
    words = norm_draft.split()
    # Longer n-grams first. Keep the bar high so short topical overlaps with the
    # thread (common in real replies) do not wipe an otherwise usable draft.
    for i in range(len(words)):
        for width in (8, 7, 6):
            if i + width > len(words):
                continue
            phrase = " ".join(words[i : i + width])
            if len(phrase) < 36:
                continue
            if is_boilerplate_parrot_phrase(phrase):
                continue
            if phrase in blob:
                return True
    return False
