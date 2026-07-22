"""Before/after sample for #606 sign-off.

For every INCORPORATED district (one with a Stage-9 `district_grade_minutes` projection), show the
**legacy** secondary `teachers_secondary` LCT — read STRAIGHT FROM THE STORED `lct_calculations` row,
never re-derived — next to the **per-grade** enrollment-weighted secondary result. Read-only: it
computes nothing into `lct_calculations` — it is the artifact to review BEFORE the recompute lands.

**Why "legacy" is a stored-row read, not a live re-derivation (bug found 2026-07-22).** An earlier
version called `get_instructional_minutes(s, did, d.state, "high")` live to reconstruct what the legacy
formula would produce. That function's existing REQ-024 fallback ("high -> middle -> elementary, for K-8
districts etc.") means it picks up ANY measured `bell_schedules` row — including one Stage 9 had *just*
written for the district being sampled. So the moment a district was incorporated, "legacy" silently
stopped meaning "what's actually live in `lct_calculations` right now" and started meaning "what the old
formula would compute today, contaminated by today's own Stage-9 write" — a materially different, and
misleadingly LOWER-delta, number (caught reviewing district 3601002: the live re-derivation returned
12.88, matching the per-grade result exactly and reporting Δ=0, while the actual stored production value
was 9.35 — a real +3.53 change the contaminated comparison hid entirely). Reading the stored row sidesteps
the whole class of bug: it is exactly what a user of the dataset sees today, unaffected by anything Stage
9 writes to `bell_schedules` in the meantime.

Districts are listed in a stable order (district_id ascending) so a `--limit N` sample is the same
N districts on every run.

    python -m infrastructure.scripts.analyze.per_grade_lct_sample [--limit N]
"""
from __future__ import annotations

import argparse

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, DistrictGradeMinutes, LCTCalculation
from infrastructure.scripts.analyze.calculate_lct_variants import (
    calculate_lct,
    get_most_recent_enrollment,
    get_most_recent_staff,
    get_statutory_minutes,
)
from infrastructure.scripts.analyze.per_grade_lct import (
    SEC_GRADES,
    cached_statutory,
    get_district_grade_minutes,
    weighted_scope_minutes,
)


def _legacy_secondary(s, district_id: str):
    """The CURRENTLY STORED `teachers_secondary` lct_calculations row — the real, live production
    baseline, unaffected by any Stage-9 write since it was calculated. None if never computed."""
    return (s.query(LCTCalculation)
            .filter(LCTCalculation.district_id == district_id,
                    LCTCalculation.staff_scope == "teachers_secondary")
            .order_by(LCTCalculation.calculated_at.desc())
            .first())


def sample(limit: int | None = None) -> list:
    rows = []
    with session_scope() as s:
        dids = [r[0] for r in (s.query(DistrictGradeMinutes.district_id).distinct()
                               .order_by(DistrictGradeMinutes.district_id).all())]
        # The REAL pipeline's pickers (COVID exclusion, zero-staff fallback), bulk dicts
        enrollment_with_years = get_most_recent_enrollment(s)
        staff_with_years = get_most_recent_staff(s)
        for did in dids:
            d = s.query(District).filter(District.nces_id == did).first()
            enr, enroll_yr = enrollment_with_years.get(did, (None, None))
            staff, staff_yr = staff_with_years.get(did, (None, None))
            if not (d and enr):
                continue
            legacy = _legacy_secondary(s, did)
            gm = get_district_grade_minutes(s, did)
            pg = weighted_scope_minutes(s, d.state, SEC_GRADES, enr, gm,
                                        [staff_yr, enroll_yr],
                                        cached_statutory(get_statutory_minutes))
            pg_min, pg_src = (pg[0], pg[1]) if pg else (None, None)
            sec_enr = enr.enrollment_secondary or 0
            t_sec = (float(staff.teachers_secondary_6_12)
                     if staff is not None and staff.teachers_secondary_6_12 else None)
            pg_lct = calculate_lct(pg_min, t_sec, sec_enr) if (pg_min and t_sec and sec_enr) else None
            rows.append({"district_id": did, "name": d.name, "state": d.state,
                         "legacy_sec_min": legacy.instructional_minutes if legacy else None,
                         "legacy_source": legacy.instructional_minutes_source if legacy else "never_computed",
                         "per_grade_sec_min": pg_min, "source": pg_src,
                         "legacy_sec_lct": float(legacy.lct_value) if legacy else None,
                         "per_grade_sec_lct": pg_lct})
            if limit and len(rows) >= limit:
                break   # cap the ELIGIBLE rows at N (not the pre-filter did list), stable by did order
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    rows = sample(args.limit)
    if not rows:
        print("No incorporated districts (no district_grade_minutes rows) — nothing to sample yet.")
        return 0
    print(f"{'district':<9} {'state':<5} {'legacy_min':>10} {'pg_min':>7} {'Δmin':>6}  "
          f"{'legacy_lct':>10} {'pg_lct':>7}  source            name")
    for r in rows:
        dmin = (r["per_grade_sec_min"] - r["legacy_sec_min"]) if r["per_grade_sec_min"] else None
        print(f"{r['district_id']:<9} {r['state']:<5} {str(r['legacy_sec_min']):>10} "
              f"{str(r['per_grade_sec_min']):>7} {str(dmin):>6}  "
              f"{('%.2f' % r['legacy_sec_lct']) if r['legacy_sec_lct'] else '—':>10} "
              f"{('%.2f' % r['per_grade_sec_lct']) if r['per_grade_sec_lct'] else '—':>7}  "
              f"{str(r['source']):<17} {r['name']}")
    print(f"\n{len(rows)} incorporated district(s). Review before recomputing lct_calculations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
