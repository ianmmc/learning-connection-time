"""School-year constants and temporal rules — the single source of truth (issue #24 / #72).

Every year default, COVID check, blend-window test, and plausibility band in the LCT layer
reads from here. Before this module, five different "current year" literals and five different
plausibility bands were scattered across defaults (fable review §3.1 M-5 / §4.6).

School years are fiscal-year-like: "2025-26" runs roughly July 1 2025 – June 30 2026, and is
identified everywhere by its START year (2025). String ordering happens to sort correctly for
the YYYY-YY format, but code should compare via start_year(), never lexicographically.
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import date


def _format_year(start: int) -> str:
    return f"{start}-{(start + 1) % 100:02d}"


def current_school_year(today: date | None = None) -> str:
    """The school year in effect on `today` (default: now). Fiscal-year-like: July 1 rolls it
    over, so 2026-06-30 -> '2025-26' and 2026-07-01 -> '2026-27'. Derived, never hand-bumped —
    the pre-2026-07 manual constant went stale exactly one rollover after it was written."""
    d = today or date.today()
    start = d.year if d.month >= 7 else d.year - 1
    return _format_year(start)


# --- The years -------------------------------------------------------------------------------

CURRENT_SCHOOL_YEAR = current_school_year()  # derived at import; call current_school_year() in long-lived processes
NCES_PRIMARY_YEAR = "2024-25"       # primary NCES CCD enrollment/staffing dataset — bump on INGEST
                                    # (a data event, not a calendar event), verified against
                                    # lct_calculations rows on the new year (CLAUDE.md Rule 6)
SPED_BASELINE_YEAR = "2017-18"      # IDEA 618 / CRDC baseline — EXEMPT from the blend window
PRE_COVID_FALLBACK_YEAR = "2018-19" # preferred over any COVID year when nothing recent exists

# Rule #2: never use COVID-era data (abnormal schedules).
COVID_EXCLUDED_YEARS = frozenset({"2019-20", "2020-21", "2021-22", "2022-23"})

# Bell-schedule search order: current first, all post-COVID years interchangeable, floored at
# 2023-24 (the first post-COVID year). Derived so it self-rolls with the current year. The blend
# window still arbitrates the actual combination per calculation (e.g. a 2026-27 bell schedule
# needs a CCD within span 2).
_BELL_FLOOR_START = 2023
ACCEPTABLE_BELL_YEARS = tuple(
    _format_year(y) for y in range(int(CURRENT_SCHOOL_YEAR[:4]), _BELL_FLOOR_START - 1, -1)
)

# --- The blend window (REQ-026, semantics decided by Ian 2026-07-01) --------------------------
# Data blended for one calculation may span at most THREE CONSECUTIVE school years:
# {2023-24, 2024-25, 2025-26} is acceptable; {2022-23, ..., 2025-26} is not. Expressed as the
# max difference between start years: span <= 2. (COVID exclusion applies FIRST — a COVID year
# is never admitted for the window to even consider. The SPED baseline year is exempt: it is a
# ratio proxy, not blended data.)
MAX_BLEND_SPAN = 2

# --- Daily-minutes plausibility (REQ-055) ------------------------------------------------------
# The ONE plausibility band for gross bell-to-bell daily minutes. The DB CHECK (100-600) is a
# deliberately looser outer sanity bound, not a second opinion.
GROSS_MINUTES_MIN = 240
GROSS_MINUTES_MAX = 510
DB_CHECK_MINUTES_MIN = 100
DB_CHECK_MINUTES_MAX = 600

_YEAR_RE = re.compile(r"^(\d{4})-(\d{2})$")


def start_year(year: str) -> int:
    """'2025-26' -> 2025. Raises ValueError on malformed or non-consecutive years."""
    m = _YEAR_RE.match(year or "")
    if not m:
        raise ValueError(f"not a school year: {year!r} (expected 'YYYY-YY')")
    start = int(m.group(1))
    if int(m.group(2)) != (start + 1) % 100:
        raise ValueError(f"school year is not consecutive: {year!r}")
    return start


def year_span(a: str, b: str) -> int:
    """Absolute difference in start years: ('2023-24', '2025-26') -> 2."""
    return abs(start_year(a) - start_year(b))


def is_covid_year(year: str) -> bool:
    return year in COVID_EXCLUDED_YEARS


def is_acceptable_data_year(year: str) -> bool:
    """Not COVID-era and parseable. (2018-19 and older pre-COVID years pass; recency preference
    is the caller's precedence logic, not a validity question.)"""
    try:
        start_year(year)
    except ValueError:
        return False
    return not is_covid_year(year)


def within_blend_window(years) -> bool:
    """True when the non-exempt years used by one calculation fit the 3-consecutive-year window.
    COVID years are invalid input here, not merely out-of-window — reject them upstream via
    is_acceptable_data_year(); this function treats their presence as a window failure too."""
    considered = [y for y in years if y and y != SPED_BASELINE_YEAR]
    if not considered:
        return True
    if any(is_covid_year(y) for y in considered):
        return False
    starts = [start_year(y) for y in considered]
    return max(starts) - min(starts) <= MAX_BLEND_SPAN


def plausible_gross_minutes(minutes) -> bool:
    """REQ-055 gate: gross bell-to-bell daily minutes in [240, 510]."""
    try:
        m = float(minutes)
    except (TypeError, ValueError):
        return False
    return GROSS_MINUTES_MIN <= m <= GROSS_MINUTES_MAX


# --- Content school-year extraction from URLs/filenames (REQ-044 / #107 / #241) ----------------
# A DETERMINISTIC read of a document's school year from its URL / filename — never today's date,
# never inferred (REQ-054). Feeds the Stage-5 `content_school_year` signal that #107's prefer-recent
# dispatch ranking and #241's pre-2017-18 validity floor consume. Caveats measured the hard way
# (STAGE5_FILTER_DESIGN §3a obs. 6): URL-DECODE first; require a CONSECUTIVE pair (a bare YYYY is an
# upload path, not a vintage; a plan span 2020-2023 is not a year); guard GUID/asset-id digit runs and
# M-DD-YY dates. The range is DELIBERATELY WIDE (unlike ACCEPTABLE_BELL_YEARS) — #241 must SEE old
# years (2001) to flag them; validity/COVID judgments belong to the CONSUMERS, not this reader.
_CONTENT_YEAR_FLOOR = 1990
# 4-digit-anchored consecutive pair: 2018-2019 / 2018-19 / 2025/26 (separator required — a contiguous
# digit run like an asset id has none, so it never matches):
_CY_FULL = re.compile(r"(?<!\d)((?:19|20)\d{2})[-–—/](\d{4}|\d{2})(?!\d)")
# 2-digit-only pair: 25-26 (needs the bad-prefix guard below — a bare 2-digit pair is ambiguous):
_CY_SHORT = re.compile(r"(?<!\d)(\d{2})[-–—/](\d{2})(?!\d)")
# A bare "NN-NN" pair is a school year ONLY when nothing identifies it as something else. Reject it
# when the token immediately before it marks it as a numeric date tail (4-20-21), a month-name date
# (March-20-21), or a labelled range/index (grades-06-07, page-12-13, v12-13, room-22-23) — the
# false-positive classes a code review surfaced. The month/label word must be a WHOLE token (bounded),
# else it over-rejects (e.g. "marshall-25-26" must NOT match "mar"); the separator is optional so a
# glued form ("v12-13") is caught too.
_CY_MONTHS = (r"january|february|march|april|may|june|july|august|september|october|november|december"
              r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_CY_NONYEAR_LABELS = (r"grades?|pages?|pg|ver|version|vol|volume|room|rm|bldg|building|section|sec"
                      r"|num|chapter|lesson|unit|part|step|figure|table|tbl|v|no|ch|fig")
_CY_BAD_SHORT_PREFIX = re.compile(
    rf"(?i)(?:\d{{1,2}}[-–—/]|(?<![a-z])(?:{_CY_MONTHS}|{_CY_NONYEAR_LABELS})(?![a-z])[-–—/_ ]?)$")


def _cy_consecutive(y1: int, y2: int) -> int | None:
    """y1 if (y1, y2) is a consecutive, in-range school-year pair, else None."""
    if y2 != y1 + 1:
        return None
    if not (_CONTENT_YEAR_FLOOR <= y1 <= date.today().year + 1):
        return None
    return y1


def _cy_short_year(a: int, b: int) -> int | None:
    """A 2-digit pair (a, b) → a full consecutive in-range start year, or None. Picks the century that
    lands in range so a turn-of-century year reads correctly ('99-00' → 1999-00, not 2099)."""
    if b != (a + 1) % 100:                     # consecutive on the 2-digit values (handles 99→00)
        return None
    for century in (2000, 1900):
        if _CONTENT_YEAR_FLOOR <= century + a <= date.today().year + 1:
            return century + a
    return None


# A month-word + year date (December98, April 2000, October%2004) → the school year CONTAINING that month
# (#531): the newsletter/board-minutes shape a consecutive pair can't see (obs. 6). NOT a full M-DD-YY date
# (a third `-NN` after the year is guarded out — that's a calendar date, handled/rejected by the pair path).
_CY_MONTH_NUM = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
                 "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
                 "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
                 "sept": 9, "oct": 10, "nov": 11, "dec": 12}
_CY_MONTH_DATE = re.compile(
    rf"(?<![a-z])({_CY_MONTHS})(?![a-z])[-_/ ]?(\d{{4}}|\d{{2}})(?![-/]?\d)", re.IGNORECASE)


def _cy_month_word_years(text: str):
    """Yield the start-year of the school year that CONTAINS each month-word date in `text` (July-1
    rollover, `current_school_year`'s rule): December 1998 → SY 1998-99; April 2000 → SY 1999-00."""
    for m in _CY_MONTH_DATE.finditer(text):
        month = _CY_MONTH_NUM[m.group(1).lower()]
        yr = m.group(2)
        full = int(yr) if len(yr) == 4 else next(
            (c + int(yr) for c in (2000, 1900) if _CONTENT_YEAR_FLOOR <= c + int(yr) <= date.today().year + 1), None)
        if full is None or not (_CONTENT_YEAR_FLOOR <= full <= date.today().year + 1):
            continue
        yield full if month >= 7 else full - 1     # Jul–Dec → SY starts this year; Jan–Jun → previous year


def _cy_candidates(text: str):
    for m in _CY_FULL.finditer(text):
        y1 = int(m.group(1))
        g2 = m.group(2)
        y2 = int(g2) if len(g2) == 4 else (y1 // 100) * 100 + int(g2)
        y = _cy_consecutive(y1, y2)
        if y is not None:
            yield y
    for m in _CY_SHORT.finditer(text):
        if _CY_BAD_SHORT_PREFIX.search(text[:m.start()]):   # a date tail / month date / labelled index
            continue
        y = _cy_short_year(int(m.group(1)), int(m.group(2)))
        if y is not None:
            yield y
    yield from _cy_month_word_years(text)                    # a month-word + year date (#531)


def content_school_year(*sources: str) -> str | None:
    """The school year read from the FIRST of `sources` (a URL, final URL, or filename) that yields any
    year, as canonical 'YYYY-YY', or None. Deterministic — never inferred from today's date or the capture
    time (REQ-054). Source order matters: the primary URL wins over a redirect/CDN `final_url` whose
    upload-date path segment (e.g. `/files/2025-26/`) is unrelated to the document's actual vintage —
    otherwise a spurious recent year there could clear #241's validity floor for a genuinely stale doc.
    Within one source, multiple distinct years ⇒ the MOST RECENT (prefer-recent ranks on it; #241 flags a
    doc stale only when even its newest referenced year is pre-floor). Caveats: STAGE5_FILTER_DESIGN §3a obs. 6."""
    for s in sources:
        if not s:
            continue
        years = list(_cy_candidates(urllib.parse.unquote(str(s))))
        if years:
            return _format_year(max(years))
    return None
