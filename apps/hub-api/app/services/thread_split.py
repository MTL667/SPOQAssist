"""Split Outlook/Graph mail bodies into latest message vs quoted thread context."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Strong markers: text ABOVE the first match is treated as the latest inbound segment.
_SPLIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?im)^[ \t]*-{2,}\s*Original Message\s*-{2,}\s*$"),
    re.compile(r"(?im)^[ \t]*-{2,}\s*Doorgestuurd bericht\s*-{2,}\s*$"),
    re.compile(r"(?im)^[ \t]*From:\s+\S"),
    re.compile(r"(?im)^[ \t]*Van:\s+\S"),
    re.compile(r"(?im)^[ \t]*Verzonden:\s+"),
    re.compile(r"(?im)^[ \t]*Sent:\s+"),
    re.compile(r"(?im)^[ \t]*Op .+ schreef .+:\s*$"),
    re.compile(r"(?im)^[ \t]*On .+ wrote:\s*$"),
    re.compile(r"(?im)^[ \t]*_{5,}\s*$"),
    # Outlook often inserts a blank line then a quoted block starting with >
    re.compile(r"(?m)^(?:>[ \t].*\n){2,}"),
]


@dataclass(frozen=True)
class ThreadParts:
    latest_message: str
    thread_context: str
    split: bool


def split_thread_body(body: str) -> ThreadParts:
    """Return latest inbound text + remaining quoted/history context."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ThreadParts(latest_message="", thread_context="", split=False)

    cut: int | None = None
    for pattern in _SPLIT_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        idx = match.start()
        # Ignore a marker at the very start of the body only.
        if idx == 0:
            continue
        if cut is None or idx < cut:
            cut = idx

    if cut is None:
        logger.info("thread_split_fallback reason=no_marker")
        return ThreadParts(latest_message=text, thread_context="", split=False)

    latest = text[:cut].strip()
    context = text[cut:].strip()
    if not latest:
        logger.info("thread_split_fallback reason=empty_latest")
        return ThreadParts(latest_message=text, thread_context="", split=False)

    return ThreadParts(latest_message=latest, thread_context=context, split=True)
