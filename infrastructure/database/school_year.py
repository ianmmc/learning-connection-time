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

# --- The years -------------------------------------------------------------------------------

CURRENT_SCHOOL_YEAR = "2025-26"     # bump once per year; the only place it is written
NCES_PRIMARY_YEAR = "2023-24"       # primary NCES CCD enrollment/staffing dataset (CLAUDE.md)
SPED_BASELINE_YEAR = "2017-18"      # IDEA 618 / CRDC baseline — EXEMPT from the blend window
PRE_COVID_FALLBACK_YEAR = "2018-19" # preferred over any COVID year when nothing recent exists

# Rule #2: never use COVID-era data (abnormal schedules).
COVID_EXCLUDED_YEARS = frozenset({"2019-20", "2020-21", "2021-22", "2022-23"})

# Bell-schedule search order: current first, all post-COVID years interchangeable.
ACCEPTABLE_BELL_YEARS = ("2025-26", "2024-25", "2023-24")

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
