"""Per-grade → scope minutes for the LCT calc (#606, epic #92).

Reads Stage 9's `district_grade_minutes` projection (the LEA-level per-grade minutes) and collapses it
to any staffing scope by an **enrollment-weighted sum over grades** — dissolving the 3-band-minutes vs
2-band-staffing mismatch. `minutes_scope = Σ_g (minutes[g] · enroll[g]) / Σ_g enroll[g]`.

LCT-side (reads the TABLE, never the acquisition code — the import-linter boundary holds). A grade's
statutory value is NEVER re-derived from its canonical band when Stage 9 already resolved it against
the grade's REAL serving band (PR #607 review finding: a floating 7-9 middle's grade 9 must weight the
MIDDLE statutory rate Stage 9 stored, not the canonical high rate). Grades absent from the projection
fall back to their canonical band's statutory minimum, so a scope always has a value. The
`_is_statutory` distinguishability the reader relies on (#582) is preserved: an all-statutory scope
reports `per_grade_statutory` / year=None; a scope with any measured grade reports `per_grade_bell`
(all measured) or `per_grade_mixed`.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable, Optional

from infrastructure.database.models import DistrictGradeMinutes
from infrastructure.database.school_year import within_blend_window

GRADES = ["KG"] + [f"{n:02d}" for n in range(1, 13)]          # KG, 01..12 (LCT range)
ELEM_GRADES = ["KG", "01", "02", "03", "04", "05"]           # K-5
SEC_GRADES = ["06", "07", "08", "09", "10", "11", "12"]      # 6-12
K12_GRADES = GRADES

_ENROLL_ATTR = {"KG": "enrollment_kindergarten",
                **{f"{n:02d}": f"enrollment_grade_{n}" for n in range(1, 13)}}
_CANON_BAND = {**{g: "elementary" for g in ELEM_GRADES},
               "06": "middle", "07": "middle", "08": "middle",
               "09": "high", "10": "high", "11": "high", "12": "high"}


def _row_tuple(r) -> tuple:
    """(minutes, method, minutes_basis, year, source_band) for one projection row."""
    return (r.instructional_minutes, r.method, r.minutes_basis, r.year, r.source_band)


def get_district_grade_minutes(session, district_id: str) -> dict:
    """{grade: (minutes, method, minutes_basis, year, source_band)} from the Stage-9 projection.
    Empty ⇒ the district was never incorporated → the caller keeps the legacy band cascade (no
    behavior change)."""
    rows = (session.query(DistrictGradeMinutes)
            .filter(DistrictGradeMinutes.district_id == district_id).all())
    return {r.grade: _row_tuple(r) for r in rows}


def get_all_district_grade_minutes(session) -> dict:
    """{district_id: {grade: (...)}} — ONE bulk query for the whole corpus, matching the
    fetch-once-before-the-loop convention of get_most_recent_staff/enrollment (PR #607 review:
    the per-district variant inside calculate_all_variants' loop was an N+1 pattern)."""
    out: dict = defaultdict(dict)
    for r in session.query(DistrictGradeMinutes).all():
        out[r.district_id][r.grade] = _row_tuple(r)
    return dict(out)


def cached_statutory(get_statutory: Callable) -> Callable:
    """Memoize a get_statutory(session, state, band) callable by (state, band) — one district's
    three scope calls (K12/elem/sec) share grades and need at most 3 distinct band lookups, not
    up to ~26 identical single-row queries (PR #607 review)."""
    cache: dict = {}
    def wrapped(session, state, band):
        key = (state, band)
        if key not in cache:
            cache[key] = get_statutory(session, state, band)
        return cache[key]
    return wrapped


def _enroll(enr, grade: str) -> int:
    return getattr(enr, _ENROLL_ATTR[grade], 0) or 0


def weighted_scope_minutes(session, state: str, scope_grades: list, enr, gm_map: dict,
                           blend_years: list,
                           get_statutory: Callable) -> Optional[tuple]:
    """Enrollment-weighted minutes for one scope. Returns (minutes, source, year) or None (no
    enrollment). `get_statutory(session, state, band) -> (minutes, source, year)` supplies the
    statutory fallback for grades OUTSIDE the projection (passed in to avoid a circular import;
    wrap with cached_statutory() at the call site)."""
    def _weighted(force_statutory: bool):
        num = den = 0
        measured_years, n_measured, n_statutory = [], 0, 0
        for g in scope_grades:
            e = _enroll(enr, g)
            if e <= 0:
                continue
            m = gm_map.get(g)
            if m and m[2] == "gross_bell_to_bell" and m[0] and not force_statutory:
                minutes_g, yr = m[0], m[3]
                n_measured += 1
                if yr:
                    measured_years.append(yr)
            elif m and m[2] == "statutory" and m[0]:
                # Stage 9 already resolved this grade's statutory value against its REAL serving
                # band — reuse it verbatim, never re-derive via the canonical band.
                minutes_g = m[0]
                n_statutory += 1
            elif m:
                # a measured grade dropped by the blend window (or a degenerate row): statutory
                # for the grade's REAL serving band, canonical only as the last resort.
                minutes_g = get_statutory(session, state, m[4] or _CANON_BAND[g])[0]
                n_statutory += 1
            else:
                # grade absent from the projection entirely: canonical-band statutory fallback.
                minutes_g = get_statutory(session, state, _CANON_BAND[g])[0]
                n_statutory += 1
            num += minutes_g * e
            den += e
        if den == 0:
            return None
        return round(num / den), n_measured, n_statutory, measured_years

    first = _weighted(force_statutory=False)
    if first is None:
        return None
    minutes, n_measured, n_statutory, measured_years = first
    if n_measured == 0:
        return minutes, "per_grade_statutory", None

    # Temporal window (REQ-026): EVERY distinct measured year feeding the weighted average must form
    # a ≤3-consecutive-year set with the staff/enrollment years — not just the modal one (PR #607
    # review: a minority-share band from an out-of-window year must not blend in silently).
    years = sorted(set(measured_years))
    if not within_blend_window([y for y in blend_years if y] + years):
        again = _weighted(force_statutory=True)
        return (again[0], "per_grade_statutory", None) if again else None

    rep_year = Counter(measured_years).most_common(1)[0][0] if measured_years else None
    source = "per_grade_bell" if n_statutory == 0 else "per_grade_mixed"
    return minutes, source, rep_year
