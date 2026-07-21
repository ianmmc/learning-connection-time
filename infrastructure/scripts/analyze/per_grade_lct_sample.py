"""Before/after sample for #606 sign-off.

For every INCORPORATED district (one with a Stage-9 `district_grade_minutes` projection), show the
**legacy** secondary instructional minutes (the high-band-only stopgap) next to the **per-grade
enrollment-weighted** secondary minutes, plus the resulting `teachers_secondary` LCT delta. Read-only:
it computes nothing into `lct_calculations` — it is the artifact to review BEFORE the recompute lands.

    python -m infrastructure.scripts.analyze.per_grade_lct_sample [--limit N]
"""
from __future__ import annotations

import argparse

from infrastructure.database.connection import session_scope
from infrastructure.database.models import (
    DistrictGradeMinutes, District, EnrollmentByGrade, StaffCountsEffective)
from infrastructure.scripts.analyze.calculate_lct_variants import (
    calculate_lct, get_instructional_minutes, get_statutory_minutes)
from infrastructure.scripts.analyze.per_grade_lct import (
    SEC_GRADES, get_district_grade_minutes, weighted_scope_minutes)


def sample(limit: int | None = None) -> list:
    rows = []
    with session_scope() as s:
        dids = [r[0] for r in s.query(DistrictGradeMinutes.district_id).distinct().all()]
        for did in dids:
            d = s.query(District).filter(District.nces_id == did).first()
            enr = (s.query(EnrollmentByGrade).filter(EnrollmentByGrade.district_id == did)
                   .order_by(EnrollmentByGrade.source_year.desc()).first())
            staff = (s.query(StaffCountsEffective).filter(StaffCountsEffective.district_id == did)
                     .order_by(StaffCountsEffective.effective_year.desc()).first())
            if not (d and enr):
                continue
            legacy_min = get_instructional_minutes(s, did, d.state, "high")[0]
            gm = get_district_grade_minutes(s, did)
            blend = [staff.effective_year if staff else None, enr.source_year]
            pg = weighted_scope_minutes(s, d.state, SEC_GRADES, enr, gm, blend, get_statutory_minutes)
            pg_min, pg_src = (pg[0], pg[1]) if pg else (None, None)
            sec_enr = enr.enrollment_secondary or 0
            t_sec = float(staff.teachers_secondary_6_12) if staff and staff.teachers_secondary_6_12 else None
            legacy_lct = calculate_lct(legacy_min, t_sec, sec_enr) if t_sec and sec_enr else None
            pg_lct = calculate_lct(pg_min, t_sec, sec_enr) if (pg_min and t_sec and sec_enr) else None
            rows.append({"district_id": did, "name": d.name, "state": d.state,
                         "legacy_sec_min": legacy_min, "per_grade_sec_min": pg_min, "source": pg_src,
                         "legacy_sec_lct": legacy_lct, "per_grade_sec_lct": pg_lct})
            if limit and len(rows) >= limit:
                break
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
