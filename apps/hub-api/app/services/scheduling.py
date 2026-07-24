"""Office-hours free-slot finder (Europe/Brussels Mon–Fri 09:00–17:00)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Brussels")
OFFICE_START = time(9, 0)
OFFICE_END = time(17, 0)
DEFAULT_DURATION_MINUTES = 60
DEFAULT_OFFICE_DAYS = 14
SIDE_SEARCH_OFFICE_DAYS = 10

_MONTH_NAMES = {
    "january": 1,
    "januari": 1,
    "february": 2,
    "februari": 2,
    "march": 3,
    "maart": 3,
    "april": 4,
    "may": 5,
    "mei": 5,
    "june": 6,
    "juni": 6,
    "july": 7,
    "juli": 7,
    "august": 8,
    "augustus": 8,
    "september": 9,
    "october": 10,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class BusyInterval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ProposedSlot:
    start_iso: str
    end_iso: str
    label: str


@dataclass
class AvailabilityPlan:
    requested_window_blocked: bool
    unavailability_note: str | None
    slots: list[ProposedSlot]
    prompt_block: str


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _is_office_day(d: date) -> bool:
    return d.weekday() < 5  # Mon–Fri


def _office_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, OFFICE_START, tzinfo=TZ)
    end = datetime.combine(d, OFFICE_END, tzinfo=TZ)
    return start, end


def _add_office_days(start: date, count: int) -> date:
    """Advance `count` office days from `start` (inclusive of start if office day)."""
    if count <= 0:
        return start
    d = start
    seen = 0
    while True:
        if _is_office_day(d):
            seen += 1
            if seen >= count:
                return d
        d += timedelta(days=1)


def _iter_office_days(start: date, end: date):
    d = start
    while d <= end:
        if _is_office_day(d):
            yield d
        d += timedelta(days=1)


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _normalize_busy(busy: list[BusyInterval]) -> list[BusyInterval]:
    intervals: list[BusyInterval] = []
    for item in busy:
        start = _ensure_aware(item.start)
        end = _ensure_aware(item.end)
        if end <= start:
            continue
        intervals.append(BusyInterval(start=start, end=end))
    intervals.sort(key=lambda x: x.start)
    return intervals


def _slot_label(start: datetime, end: datetime) -> str:
    start = _ensure_aware(start)
    end = _ensure_aware(end)
    day = start.strftime("%a %d %b")
    return f"{day} {start.strftime('%H:%M')}–{end.strftime('%H:%M')} (Europe/Brussels)"


def _collect_slots(
    *,
    busy: list[BusyInterval],
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int,
    limit: int,
    now: datetime,
) -> list[ProposedSlot]:
    if limit <= 0 or window_end <= window_start:
        return []
    duration = timedelta(minutes=duration_minutes)
    now = _ensure_aware(now)
    window_start = _ensure_aware(window_start)
    window_end = _ensure_aware(window_end)
    busy_n = _normalize_busy(busy)
    slots: list[ProposedSlot] = []
    for day in _iter_office_days(window_start.date(), window_end.date()):
        day_start, day_end = _office_day_bounds(day)
        cursor = max(day_start, window_start, now)
        # Snap to next 30-minute boundary for cleaner proposals.
        if cursor.minute not in (0, 30) or cursor.second or cursor.microsecond:
            add = 30 - (cursor.minute % 30)
            cursor = cursor.replace(second=0, microsecond=0) + timedelta(minutes=add)
        day_limit = min(day_end, window_end)
        while cursor + duration <= day_limit and len(slots) < limit:
            slot_end = cursor + duration
            conflict = any(_overlaps(cursor, slot_end, b.start, b.end) for b in busy_n)
            if not conflict:
                slots.append(
                    ProposedSlot(
                        start_iso=cursor.isoformat(),
                        end_iso=slot_end.isoformat(),
                        label=_slot_label(cursor, slot_end),
                    )
                )
            cursor += timedelta(minutes=30)
        if len(slots) >= limit:
            break
    return slots


def _detect_deadline(text: str, *, now: datetime) -> date | None:
    """Parse common deadline forms: 31/8, 31/08, August 31, 31 August."""
    now = _ensure_aware(now)
    year = now.year

    for m in re.finditer(
        r"\b(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?\b",
        text,
    ):
        day_i, month_i = int(m.group(1)), int(m.group(2))
        # Swap US-style month/day first (e.g. "8/13" → day 13, month 8).
        if month_i > 12 and day_i <= 12:
            day_i, month_i = month_i, day_i
        if not m.group(3):
            # No explicit year: require a plausible day/month, and skip common
            # non-date ratios like "24/7" (round-the-clock, not July 24).
            if not (1 <= month_i <= 12 and 1 <= day_i <= 31):
                continue
            if day_i == 24 and month_i == 7:
                continue
        y = year
        if m.group(3):
            y = int(m.group(3))
            if y < 100:
                y += 2000
        try:
            d = date(y, month_i, day_i)
        except ValueError:
            continue
        if d < now.date() and not m.group(3):
            try:
                d = date(y + 1, month_i, day_i)
            except ValueError:
                continue
        return d

    for name, month_i in _MONTH_NAMES.items():
        m = re.search(
            rf"\b(?:{name})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            day_i = int(m.group(1))
            try:
                d = date(year, month_i, day_i)
            except ValueError:
                continue
            if d < now.date():
                d = date(year + 1, month_i, day_i)
            return d
        m = re.search(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:{name})\b",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            day_i = int(m.group(1))
            try:
                d = date(year, month_i, day_i)
            except ValueError:
                continue
            if d < now.date():
                d = date(year + 1, month_i, day_i)
            return d

    return None


_DURATION_KEYWORDS = (
    r"\b(?:meeting|afspraak|call|gesprek|duur|duration|vergadering|meet)\b"
)


def _near_duration_keyword(text: str, span: tuple[int, int], *, window: int = 40) -> bool:
    """True when a duration-context keyword sits close to the matched span.

    Avoids reading phrases like "in 2 hours" / "within 30 minutes" (a delay or
    deadline, not the meeting length) as an explicit duration.
    """
    start, end = span
    ctx = text[max(0, start - window) : min(len(text), end + window)]
    return re.search(_DURATION_KEYWORDS, ctx, flags=re.IGNORECASE) is not None


def parse_duration_minutes(subject: str, body: str) -> int:
    """Parse an explicit duration from mail text; default 60 minutes.

    Only honours a duration when it appears near a meeting/duration keyword;
    otherwise falls back to the default.
    """
    text = f"{subject or ''}\n{body or ''}"
    m = re.search(
        r"\b(\d{1,2}(?:[.,]\d+)?)\s*(?:uur|uren|hours?|hrs?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if m and _near_duration_keyword(text, m.span()):
        raw = m.group(1).replace(",", ".")
        try:
            hours = float(raw)
        except ValueError:
            hours = 0.0
        if hours > 0:
            return max(15, min(480, int(round(hours * 60))))
    m = re.search(
        r"\b(\d{1,3})\s*(?:min(?:ute)?s?|minuten)\b",
        text,
        flags=re.IGNORECASE,
    )
    if m and _near_duration_keyword(text, m.span()):
        try:
            mins = int(m.group(1))
        except ValueError:
            mins = 0
        if mins > 0:
            return max(15, min(480, mins))
    return DEFAULT_DURATION_MINUTES


# Strong scheduling signals (NL+EN). Deliberately excludes bare "gesprek"/"sessie"
# and the mere presence of a date, to avoid needless calendar/Graph consults.
_SCHEDULING_PATTERNS = (
    r"meetings?",
    r"\bmeet\b",
    r"\bcall\b",
    r"video\s*call",
    r"conference call",
    r"afspra(?:ak|ken)",
    r"vergader",
    r"uitnodig",
    r"\binvit(?:e|ation)\b",
    r"\bagenda\b",
    r"calendar",
    r"kalender",
    r"inplann",
    r"inboeken",
    # No leading \b so "reschedule" / "rescheduling" also match.
    r"schedul",
    r"verzet(?:ten)?",
    r"verplaats",
    r"appointment",
    r"moment\s+(?:voorzien|vinden|inplannen|prikken|zoeken)",
    r"tijd\s+(?:vinden|voorzien|prikken|zoeken)",
    r"datum\s+prikken",
    # Availability only when phrased as scheduling, not "product is beschikbaar".
    r"beschikbaarheid",
    r"availabilit",
    r"(?:ben|bent|zijn)\s+(?:je|jij|jullie|u|we|wij)\b[^.?!]{0,30}\bbeschikbaar",
    r"(?:are|is|you)\b[^.?!]{0,20}\bavailable\b",
    r"past het",
    r"schikt (?:het|dit|dat|je|jou|u)",
    r"wanneer (?:kan|kun|past|schikt|ben je|zou)",
    r"welk(?:e)? (?:datum|tijdstip|moment|uur)",
    r"let'?s meet",
    r"let us meet",
    r"find a time",
    r"\bbook a\b",
    r"boek een",
)
_SCHEDULING_RE = re.compile("|".join(_SCHEDULING_PATTERNS), re.IGNORECASE)


def has_scheduling_intent(subject: str, body: str) -> bool:
    """Conservative detector for genuine meeting/appointment scheduling intent.

    Matches scheduling verbs/nouns/phrases (NL+EN), NOT the mere presence of a
    date. Used to trigger the calendar consult even when the classifier labels a
    scheduling mail as something other than "meeting".
    """
    text = f"{subject or ''}\n{body or ''}"
    return _SCHEDULING_RE.search(text) is not None


def parse_meeting_window(
    subject: str,
    body: str,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return (window_start, window_end) in Europe/Brussels."""
    now = _ensure_aware(now or datetime.now(TZ))
    text = f"{subject or ''}\n{body or ''}"
    deadline = _detect_deadline(text, now=now)
    if deadline is not None:
        window_start = now
        _, window_end = _office_day_bounds(deadline)
        if window_end <= window_start:
            # Deadline already passed today — keep a minimal same-day office slice.
            window_end = window_start + timedelta(hours=1)
        return window_start, window_end

    # Default: next 14 office days from now.
    start_day = now.date()
    if not _is_office_day(start_day) or now.time() >= OFFICE_END:
        start_day = start_day + timedelta(days=1)
        while not _is_office_day(start_day):
            start_day += timedelta(days=1)
    end_day = _add_office_days(start_day, DEFAULT_OFFICE_DAYS)
    window_start = max(now, _office_day_bounds(start_day)[0])
    window_end = _office_day_bounds(end_day)[1]
    return window_start, window_end


def _build_prompt_block(
    *,
    slots: list[ProposedSlot],
    unavailability_note: str | None,
) -> str:
    lines = [
        "Calendar availability (authoritative — use ONLY these free times; "
        "do NOT invent other slots, booked holds, or Teams links):"
    ]
    if unavailability_note:
        lines.append(f"Unavailability: {unavailability_note}")
    if slots:
        lines.append("Proposed free slots:")
        for idx, slot in enumerate(slots, start=1):
            lines.append(f"  {idx}. {slot.label} ({slot.start_iso} – {slot.end_iso})")
    else:
        lines.append("No free office-hour slots found in the searchable range.")
    return "\n".join(lines)


def find_free_slots(
    busy: list[BusyInterval],
    window_start: datetime,
    window_end: datetime,
    *,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    limit: int = 3,
    now: datetime | None = None,
) -> AvailabilityPlan:
    now = _ensure_aware(now or datetime.now(TZ))
    window_start = _ensure_aware(window_start)
    window_end = _ensure_aware(window_end)
    duration_minutes = max(15, int(duration_minutes or DEFAULT_DURATION_MINUTES))
    limit = max(1, int(limit or 3))

    in_window = _collect_slots(
        busy=busy,
        window_start=window_start,
        window_end=window_end,
        duration_minutes=duration_minutes,
        limit=limit,
        now=now,
    )
    if in_window:
        return AvailabilityPlan(
            requested_window_blocked=False,
            unavailability_note=None,
            slots=in_window,
            prompt_block=_build_prompt_block(slots=in_window, unavailability_note=None),
        )

    # Blocked: search before and after the requested window (~10 office days each).
    before_end = window_start
    before_start_day = window_start.date()
    # Walk back ~10 office days.
    office_back = 0
    d = before_start_day - timedelta(days=1)
    while office_back < SIDE_SEARCH_OFFICE_DAYS:
        if _is_office_day(d):
            office_back += 1
            if office_back >= SIDE_SEARCH_OFFICE_DAYS:
                break
        d -= timedelta(days=1)
    before_start = _office_day_bounds(d)[0]

    after_start = window_end
    after_end_day = _add_office_days(window_end.date() + timedelta(days=1), SIDE_SEARCH_OFFICE_DAYS)
    after_end = _office_day_bounds(after_end_day)[1]

    before_slots = _collect_slots(
        busy=busy,
        window_start=before_start,
        window_end=before_end,
        duration_minutes=duration_minutes,
        limit=limit,
        now=now,
    )
    after_slots = _collect_slots(
        busy=busy,
        window_start=after_start,
        window_end=after_end,
        duration_minutes=duration_minutes,
        limit=limit,
        now=now,
    )

    # Interleave before/after; prefer a mix, cap at limit.
    mixed: list[ProposedSlot] = []
    bi = ai = 0
    # Prefer latest before slots first (closest to the block).
    before_slots = list(reversed(before_slots))
    while len(mixed) < limit and (bi < len(before_slots) or ai < len(after_slots)):
        if bi < len(before_slots):
            mixed.append(before_slots[bi])
            bi += 1
        if len(mixed) >= limit:
            break
        if ai < len(after_slots):
            mixed.append(after_slots[ai])
            ai += 1

    note = (
        f"The mailbox owner is unavailable during the requested window "
        f"({window_start.strftime('%Y-%m-%d %H:%M')} – {window_end.strftime('%Y-%m-%d %H:%M')} "
        f"Europe/Brussels). Propose times before and/or after that block."
    )
    return AvailabilityPlan(
        requested_window_blocked=True,
        unavailability_note=note,
        slots=mixed,
        prompt_block=_build_prompt_block(slots=mixed, unavailability_note=note),
    )


def extract_attendee_emails(
    sender: str,
    to_recipients: list[str] | None,
    cc_recipients: list[str] | None,
    owner_email: str,
) -> list[str]:
    owner = (owner_email or "").strip().lower()
    seen: set[str] = set()
    out: list[str] = []
    for raw in [sender, *(to_recipients or []), *(cc_recipients or [])]:
        email = (raw or "").strip().lower()
        if not email or "@" not in email:
            continue
        if email == owner:
            continue
        if email in seen:
            continue
        seen.add(email)
        out.append(email)
    return out
