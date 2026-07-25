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

**Caveat — the Δ is a full-recompute delta, not a minutes-only delta.** `legacy_sec_lct` is the stored
row's `lct_value`, baked from the staff/enrollment that were current when it was last calculated;
`per_grade_sec_lct` is computed from the staff/enrollment that are current NOW. That is the RIGHT
"before vs after a recompute" framing — the recompute refreshes staff/enrollment too — but it means the
Δ can include staff/enrollment drift, not just the per-grade-minutes change. When the stored row's
denominator years differ from today's picks, the row is flagged `denom refreshed` so a reviewer never
mistakes a data-vintage shift for a pure methodology effect.

Districts are listed in a stable order (district_id ascending) so a `--limit N` sample is the same
N districts on every run.

    python -m infrastructure.scripts.analyze.per_grade_lct_sample [--limit N]
"""
from __future__ import annotations

import argparse

from sqlalchemy import nullslast

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
    get_all_district_grade_minutes,
    weighted_scope_minutes,
)


def _legacy_secondary_by_district(s, district_ids: list) -> dict:
    """Bulk-fetch the CURRENT stored `teachers_secondary` lct_calculations row per district — the
    real, live production baseline, unaffected by any Stage-9 write since it was calculated. ONE query
    (mirrors the `get_most_recent_enrollment`/`get_most_recent_staff` bulk-dict pattern used in
    `sample()`), not one query per district (PR #610 review — N+1).

    "Current" = highest `year` first, tie-broken by most-recent `calculated_at` (NULLs last). Ordering
    by `year` (a NOT-NULL column) BEFORE `calculated_at` matters: a TARGET_YEAR recompute clears only
    its own year's rows, so multiple years can coexist for a district+scope — an out-of-order
    recompute of a STALE year (a later wall-clock `calculated_at` on an older `year`) must not outrank
    the newest year (PR #610 review). `grade_level IS NULL` restricts to the scope-level row: a future
    grade-level-scoped `teachers_secondary` row must not be picked here. Missing key = never computed."""
    if not district_ids:
        return {}
    rows = (s.query(LCTCalculation)
            .filter(LCTCalculation.district_id.in_(district_ids),
                    LCTCalculation.staff_scope == "teachers_secondary",
                    LCTCalculation.grade_level.is_(None))
            .order_by(LCTCalculation.district_id,
                      LCTCalculation.year.desc(),
                      nullslast(LCTCalculation.calculated_at.desc()))
            .all())
    out: dict = {}
    for r in rows:
        out.setdefault(r.district_id, r)   # first per district = highest year, then latest calc
    return out


def sample(limit: int | None = None) -> list:
    rows = []
    with session_scope() as s:
        dids = [r[0] for r in (s.query(DistrictGradeMinutes.district_id).distinct()
                               .order_by(DistrictGradeMinutes.district_id).all())]
        # The REAL pipeline's pickers (COVID exclusion, zero-staff fallback), bulk dicts.
        # #637: EVERYTHING per-district is bulk-fetched before the loop — the District rows, the
        # grade-minutes projection, and ONE shared statutory memo (it was rebuilt per iteration,
        # throwing its (state, band) cache away each district).
        enrollment_with_years = get_most_recent_enrollment(s)
        staff_with_years = get_most_recent_staff(s)
        legacy_by_district = _legacy_secondary_by_district(s, dids)
        districts_by_id = {d.nces_id: d for d in
                           s.query(District).filter(District.nces_id.in_(dids)).all()}
        gm_by_district = get_all_district_grade_minutes(s)
        stat = cached_statutory(get_statutory_minutes)
        for did in dids:
            d = districts_by_id.get(did)
            enr, enroll_yr = enrollment_with_years.get(did, (None, None))
            staff, staff_yr = staff_with_years.get(did, (None, None))
            if not (d and enr):
                continue
            legacy = legacy_by_district.get(did)
            gm = gm_by_district.get(did) or {}
            pg = weighted_scope_minutes(s, d.state, SEC_GRADES, enr, gm,
                                        [staff_yr, enroll_yr], stat)
            pg_min, pg_src = (pg[0], pg[1]) if pg else (None, None)
            sec_enr = enr.enrollment_secondary or 0
            t_sec = (float(staff.teachers_secondary_6_12)
                     if staff is not None and staff.teachers_secondary_6_12 else None)
            pg_lct = calculate_lct(pg_min, t_sec, sec_enr) if (pg_min and t_sec and sec_enr) else None
            # Denominator-vintage flag: the stored row's staff/enrollment years vs today's picks. When
            # they differ, part of the Δ is a data refresh, not the per-grade methodology (see docstring).
            denom_refreshed = bool(legacy and (
                (legacy.staff_source_year and staff_yr and legacy.staff_source_year != staff_yr) or
                (legacy.enrollment_source_year and enroll_yr
                 and legacy.enrollment_source_year != enroll_yr)))
            rows.append({"district_id": did, "name": d.name, "state": d.state,
                         "legacy_sec_min": legacy.instructional_minutes if legacy else None,
                         "legacy_source": legacy.instructional_minutes_source if legacy else "never_computed",
                         "per_grade_sec_min": pg_min, "source": pg_src,
                         "legacy_sec_lct": float(legacy.lct_value) if legacy else None,
                         "per_grade_sec_lct": pg_lct,
                         "denom_refreshed": denom_refreshed})
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
        # Both operands can be None: legacy_sec_min is None for a never-computed district (this is
        # exactly the "BEFORE the recompute lands" case the tool exists for), pg is None when no
        # per-grade secondary enrollment — guard BOTH, or `int - None` crashes the whole report.
        dmin = (r["per_grade_sec_min"] - r["legacy_sec_min"]) \
            if (r["per_grade_sec_min"] is not None and r["legacy_sec_min"] is not None) else None
        name = f"{r['name']}  [!] denom refreshed" if r.get("denom_refreshed") else r["name"]
        print(f"{r['district_id']:<9} {r['state']:<5} {str(r['legacy_sec_min']):>10} "
              f"{str(r['per_grade_sec_min']):>7} {str(dmin):>6}  "
              f"{('%.2f' % r['legacy_sec_lct']) if r['legacy_sec_lct'] is not None else '—':>10} "
              f"{('%.2f' % r['per_grade_sec_lct']) if r['per_grade_sec_lct'] is not None else '—':>7}  "
              f"{str(r['source']):<17} {name}")
    print(f"\n{len(rows)} incorporated district(s). Review before recomputing lct_calculations.")
    if any(r.get("denom_refreshed") for r in rows):
        print("[!] denom refreshed = the stored 'legacy' row used older staff/enrollment than today's "
              "picks; part of that row's Δ is a data refresh, not the per-grade change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
