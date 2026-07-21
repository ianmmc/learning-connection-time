"""Per-grade → scope minutes for the LCT calc (#606, epic #92).

Reads Stage 9's `district_grade_minutes` projection (the LEA-level per-grade minutes) and collapses it
to any staffing scope by an **enrollment-weighted sum over grades** — dissolving the 3-band-minutes vs
2-band-staffing mismatch. `minutes_scope = Σ_g (minutes[g] · enroll[g]) / Σ_g enroll[g]`.

LCT-side (reads the TABLE, never the acquisition code — the import-linter boundary holds). Grades not
in the projection fall back to per-grade statutory (their canonical band's state minimum), so a scope
always has a value. The `_is_statutory` distinguishability the reader relies on (#582) is preserved:
an all-statutory scope reports `per_grade_statutory` / year=None; a scope with any measured grade
reports `per_grade_bell` (all measured) or `per_grade_mixed`.
"""
from __future__ import annotations

from collections import Counter
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


def get_district_grade_minutes(session, district_id: str) -> dict:
    """{grade: (minutes, method, minutes_basis, year)} from the Stage-9 projection. Empty ⇒ the
    district was never incorporated → the caller keeps the legacy band cascade (no behavior change)."""
    rows = (session.query(DistrictGradeMinutes)
            .filter(DistrictGradeMinutes.district_id == district_id).all())
    return {r.grade: (r.instructional_minutes, r.method, r.minutes_basis, r.year) for r in rows}


def _enroll(enr, grade: str) -> int:
    return getattr(enr, _ENROLL_ATTR[grade], 0) or 0


def weighted_scope_minutes(session, state: str, scope_grades: list, enr, gm_map: dict,
                           blend_years: list,
                           get_statutory: Callable) -> Optional[tuple]:
    """Enrollment-weighted minutes for one scope. Returns (minutes, source, year) or None (no
    enrollment). `get_statutory(session, state, band) -> (minutes, source, year)` supplies the
    per-grade statutory fallback (passed in to avoid a circular import)."""
    def _weighted(force_statutory: bool):
        num = den = 0
        measured_years, n_measured, n_statutory = [], 0, 0
        for g in scope_grades:
            e = _enroll(enr, g)
            if e <= 0:
                continue
            m = gm_map.get(g)
            if not force_statutory and m and m[2] == "gross_bell_to_bell" and m[0]:
                minutes_g, yr = m[0], m[3]
                n_measured += 1
                if yr:
                    measured_years.append(yr)
            else:
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

    rep_year = Counter(measured_years).most_common(1)[0][0] if measured_years else None
    # Temporal window (REQ-026): if the measured year can't form a ≤3-consecutive-year set with the
    # staff/enrollment years, drop the whole scope to statutory (matches the legacy band behavior).
    if rep_year and not within_blend_window([y for y in blend_years if y] + [rep_year]):
        again = _weighted(force_statutory=True)
        return (again[0], "per_grade_statutory", None) if again else None

    source = "per_grade_bell" if n_statutory == 0 else "per_grade_mixed"
    return minutes, source, rep_year
