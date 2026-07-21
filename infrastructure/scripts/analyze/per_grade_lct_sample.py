"""Before/after sample for #606 sign-off.

For every INCORPORATED district (one with a Stage-9 `district_grade_minutes` projection), show the
**legacy** secondary instructional minutes (the high-band-only stopgap) next to the **per-grade
enrollment-weighted** secondary minutes, plus the resulting `teachers_secondary` LCT delta. Read-only:
it computes nothing into `lct_calculations` — it is the artifact to review BEFORE the recompute lands.

Selection fidelity (PR #607 review): the sample reuses the REAL pipeline's pickers —
`get_most_recent_enrollment` / `get_most_recent_staff` (COVID exclusion + zero-staff fallback
included) — and applies the same REQ-026 blend-window downgrade to the legacy value that
`calculate_all_variants` applies, so the reviewed deltas match what the recompute would produce.
Districts are listed in a stable order (district_id ascending) so a `--limit N` sample is the same
N districts on every run.

    python -m infrastructure.scripts.analyze.per_grade_lct_sample [--limit N]
"""
from __future__ import annotations

import argparse

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, DistrictGradeMinutes
from infrastructure.database.school_year import within_blend_window
from infrastructure.scripts.analyze.calculate_lct_variants import (
    calculate_lct,
    get_instructional_minutes,
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


def sample(limit: int | None = None) -> list:
    rows = []
    with session_scope() as s:
        dids = [r[0] for r in (s.query(DistrictGradeMinutes.district_id).distinct()
                               .order_by(DistrictGradeMinutes.district_id).all())]
        if limit:
            dids = dids[:limit]
        # The REAL pipeline's pickers (COVID exclusion, zero-staff fallback), bulk dicts
        enrollment_with_years = get_most_recent_enrollment(s)
        staff_with_years = get_most_recent_staff(s)
        for did in dids:
            d = s.query(District).filter(District.nces_id == did).first()
            enr, enroll_yr = enrollment_with_years.get(did, (None, None))
            staff, staff_yr = staff_with_years.get(did, (None, None))
            if not (d and enr):
                continue
            # Legacy value with the same REQ-026 downgrade the real calc applies
            legacy_min, legacy_src, legacy_yr = get_instructional_minutes(s, did, d.state, "high")
            if legacy_yr and not within_blend_window([legacy_yr, staff_yr, enroll_yr]):
                legacy_min, legacy_src, legacy_yr = get_statutory_minutes(s, d.state, "high")
            gm = get_district_grade_minutes(s, did)
            pg = weighted_scope_minutes(s, d.state, SEC_GRADES, enr, gm,
                                        [staff_yr, enroll_yr],
                                        cached_statutory(get_statutory_minutes))
            pg_min, pg_src = (pg[0], pg[1]) if pg else (None, None)
            sec_enr = enr.enrollment_secondary or 0
            t_sec = (float(staff.teachers_secondary_6_12)
                     if staff is not None and staff.teachers_secondary_6_12 else None)
            legacy_lct = calculate_lct(legacy_min, t_sec, sec_enr) if t_sec and sec_enr else None
            pg_lct = calculate_lct(pg_min, t_sec, sec_enr) if (pg_min and t_sec and sec_enr) else None
            rows.append({"district_id": did, "name": d.name, "state": d.state,
                         "legacy_sec_min": legacy_min, "legacy_source": legacy_src,
                         "per_grade_sec_min": pg_min, "source": pg_src,
                         "legacy_sec_lct": legacy_lct, "per_grade_sec_lct": pg_lct})
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
