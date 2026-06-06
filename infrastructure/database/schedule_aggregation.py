"""
schedule_aggregation.py - Per-school schedules -> district grade-band instructional minutes.

Two responsibilities:
  1. compute_instructional_minutes(): the canonical times -> daily instructional minutes
     conversion (gross day minus lunch and passing time). This is the single quantity LCT needs.
  2. aggregate_grade_band() / aggregate_district(): collapse a SAMPLE of schools into one
     district grade-band value using the MODE (most common instructional-minutes value among
     the sampled schools) — chosen over a weighted mean to avoid needing per-school enrollment.
     Always returns the distribution (min, mode, max) for transparency.

These are pure functions (no DB) so they're unit-testable and reusable by the enrichment
pipeline and by any reprocessing of already-captured school documents.
"""

from __future__ import annotations

from statistics import multimode
from typing import Optional


def _to_minutes(hhmm: str) -> Optional[int]:
    if not hhmm or ":" not in str(hhmm):
        return None
    try:
        h, m = str(hhmm).strip().split(":")[:2]
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except (ValueError, IndexError):
        return None
    return None


def compute_instructional_minutes(start: str, end: str,
                                  lunch_minutes: int = 0,
                                  passing_minutes: int = 0) -> Optional[int]:
    """Daily instructional minutes = (end - start) - lunch - passing. None if unparseable.

    Times are HH:MM 24-hour. lunch/passing are optional deductions (default 0 = gross day).
    Returns None on bad input or non-positive duration.
    """
    s, e = _to_minutes(start), _to_minutes(end)
    if s is None or e is None or e <= s:
        return None
    net = (e - s) - max(0, lunch_minutes or 0) - max(0, passing_minutes or 0)
    return net if net > 0 else None


def aggregate_grade_band(schools: list[dict]) -> Optional[dict]:
    """Collapse a sample of schools (same grade band) to one district value + distribution.

    The district grade-band value is the MODE of the sampled schools' instructional minutes
    (most common value; ties resolve to the smallest, conservatively). The (min, max) are kept
    for transparency. Each school dict needs 'instructional_minutes' (int). Returns None if no
    usable minutes. aggregation_method is one of: mode_of_sample | single_school.
    """
    mins = [s["instructional_minutes"] for s in schools
            if s.get("instructional_minutes") is not None]
    if not mins:
        return None
    mode = min(multimode(mins))  # most common; tie -> smallest
    return {
        "value": mode,                      # the district grade-band instructional minutes
        "mode": mode,
        "min": min(mins),
        "max": max(mins),
        "n_schools": len(mins),
        "aggregation_method": "single_school" if len(mins) == 1 else "mode_of_sample",
    }


def aggregate_district(schools: list[dict]) -> dict[str, dict]:
    """Group a district's sampled schools by grade_level and aggregate each band."""
    by_band: dict[str, list[dict]] = {}
    for s in schools:
        by_band.setdefault(s.get("grade_level", "unknown"), []).append(s)
    out = {}
    for band, rows in by_band.items():
        agg = aggregate_grade_band(rows)
        if agg is not None:
            out[band] = agg
    return out
