#!/usr/bin/env python3
"""
LEDGER NOTE (2026-07-02, issue #21): this is a DATA backfill — it computes/UPDATEs sped_estimates rows (rebuild phase 5) — NOT a schema migration; it deliberately does not write schema_migrations. All DDL lives in the numbered NNN_*.sql files (migrate.py status = the ledger).

Apply SPED baseline ratios to current year district data.

This script:
1. Loads ONE baseline vintage's ratios (state and LEA level; --baseline-year, #999)
2. For each current-year district, estimates:
   - SPED enrollment (using LEA proportion or state average)
   - GenEd enrollment (total - SPED)
   - SPED teachers (SPED enrollment × state ratio)
   - GenEd teachers (total teachers - SPED teachers)
3. Stores estimates in sped_estimates table

Usage:
    python apply_sped_estimates.py            # defaults to NCES_PRIMARY_YEAR
    python apply_sped_estimates.py --year 2023-24
    python apply_sped_estimates.py --baseline-year 2017-18 --year 2024-25
"""

import argparse
import sys
from pathlib import Path
from decimal import Decimal
from typing import NamedTuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.queries import distinct_years
from infrastructure.utilities.data_guards import DataGuardError, require_nonempty_selection
from infrastructure.utilities.school_year import COVID_EXCLUDED_YEARS, NCES_PRIMARY_YEAR, SPED_BASELINE_YEAR
from infrastructure.database.models import (
    District, SpedStateBaseline, SpedLeaBaseline, SpedEstimate, DataLineage,
    EnrollmentByGrade, StaffCountsEffective,
)


class YearTotals(NamedTuple):
    """Per-district totals for ONE school year, sourced from the year-keyed tables (#972)."""
    nces_id: str
    state: str
    enrollment: int
    instructional_staff: float


NCES_SOURCE = "nces_ccd"
# #993: healthy runs skip ~1% (176 of 17,102 on 2024-25 — districts in neither LEA baseline nor a
# state with an LEA average); a share far above that is a baseline/state mismatch, not a workload.
MAX_SKIPPED_SHARE = 0.05


def select_year_totals(session, year: str) -> list[YearTotals]:
    """The districts to estimate for `year`, on the HEADLINE scope's own base (#974): K-12 enrollment
    (enrollment_by_grade.enrollment_k12, NCES CCD) and K-12 teachers (staff_counts_effective.
    scope_teachers_only = elementary + secondary + kindergarten, no Pre-K, no ungraded), both > 0.

    That is exactly what calculate_lct_variants divides for `teachers_only`, so the SPED partition
    (core_sped + teachers_gened) sums to the headline number by construction — the audit identity
    METHODOLOGY states, now evaluated by tests/test_sped_segmentation.py::TestSpedPartitionIdentity.
    It replaced teachers_total / enrollment_total (all teachers incl. Pre-K and ungraded, ~8% larger),
    under which the identity held for 23% of districts.

    scope_teachers_only is read from staff_counts_effective, yet stays independent of the SEA merge:
    merge_sea_precedence rewrites ONLY teachers_total there (never the per-level fields or any scope_*;
    the #979/#986 concern), and the table is keyed (district_id, effective_year), so no fan-out.
    `districts` itself is a single-vintage snapshot and is used only for identity (#972).
    """
    if year in COVID_EXCLUDED_YEARS:
        raise DataGuardError(f"apply_sped_estimates: {year} is a COVID-excluded year (REQ-007)")
    rows = (
        session.query(
            District.nces_id, District.state,
            EnrollmentByGrade.enrollment_k12, StaffCountsEffective.scope_teachers_only,
        )
        .join(EnrollmentByGrade, EnrollmentByGrade.district_id == District.nces_id)
        .join(StaffCountsEffective, StaffCountsEffective.district_id == District.nces_id)
        .filter(
            EnrollmentByGrade.source_year == year,
            EnrollmentByGrade.data_source == NCES_SOURCE,
            StaffCountsEffective.effective_year == year,
            EnrollmentByGrade.enrollment_k12 > 0,
            StaffCountsEffective.scope_teachers_only > 0,
        )
        .all()
    )
    totals = [YearTotals(n, st, int(e), float(t)) for n, st, e, t in rows]
    ids = [t.nces_id for t in totals]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})[:5]
        raise DataGuardError(f"apply_sped_estimates: {len(ids) - len(set(ids))} district(s) selected twice "
                             f"for {year} (duplicate nces_ccd rows, e.g. {dupes}) — refusing to fan out")
    return totals


def available_years(session) -> dict[str, list[str]]:
    """Which years each year-keyed table select_year_totals reads carries — for the fail-loud message."""
    return {
        "enrollment_by_grade": distinct_years(session, "enrollment_by_grade", "source_year",
                                              where="data_source = :src", params={"src": NCES_SOURCE}),
        "staff_counts_effective": distinct_years(session, "staff_counts_effective", "effective_year"),
    }


class BaselineRatios(NamedTuple):
    """Everything the estimator reads from ONE baseline vintage (#999)."""
    baseline_year: str
    teacher: dict[str, float]          # state -> SPED teachers per self-contained student
    instructional: dict[str, float]    # state -> SPED teachers + paras per self-contained student
    self_contained: dict[str, float]   # state -> self-contained share of school-age SPED
    national: dict[str, float]         # unweighted means of the three, for states missing them
    state_avg_proportion: dict[str, float]   # state -> mean LEA SPED share (the LEA fallback)
    lea_proportion: dict[str, float]         # lea_id -> LEA SPED share
    # lea_id -> the LEA's OWN self-contained share (IDEA LEA environments, #1004); a district absent
    # here uses its state's. None/empty = the state share for everyone (the method through 2026-10-31).
    lea_self_contained: dict[str, float] | None = None


def ratios_from_rows(baseline_year: str, state_rows, lea_rows) -> BaselineRatios:
    """Pure: baseline rows (ORM objects, saved or not) → the ratios the estimator applies. The ONE
    derivation, used by the DB run and by the T4 before/after measurement alike (#1002)."""
    teacher, instructional, self_contained = {}, {}, {}
    for r in state_rows:
        if r.ratio_sped_teachers_per_student is None:
            continue
        teacher[r.state] = float(r.ratio_sped_teachers_per_student)
        if r.ratio_sped_instructional_per_student:
            instructional[r.state] = float(r.ratio_sped_instructional_per_student)
        if r.ratio_self_contained_proportion:
            self_contained[r.state] = float(r.ratio_self_contained_proportion)
    # A national fallback computed from nothing is 0.0 and would write zero-SPED estimates at
    # "medium" confidence (#993) — refuse instead.
    if not teacher or not self_contained:
        raise DataGuardError(f"SPED baseline {baseline_year}: no state carries a teacher and self-contained "
                             f"ratio (teacher={len(teacher)}, self_contained={len(self_contained)}) — "
                             f"the national fallback would be 0.0")
    national = {
        "teacher_ratio": sum(teacher.values()) / len(teacher),
        "instructional_ratio": sum(instructional.values()) / len(instructional) if instructional else 0,
        "self_contained_ratio": sum(self_contained.values()) / len(self_contained),
    }
    # Only valid proportions (0 < p < 0.5; > 50% is an outlier). The state mean is taken in Decimal,
    # as the SQL avg(numeric) this replaced did, so the 2017-18 estimates reproduce exactly (A1).
    lea_proportion: dict[str, float] = {}
    by_state: dict[str, list[Decimal]] = {}
    for r in lea_rows:
        p = r.ratio_sped_proportion
        if p is None or not (0 < p < 0.5):
            continue
        p = Decimal(str(p))
        lea_proportion[r.lea_id] = float(p)
        by_state.setdefault(r.state, []).append(p)
    state_avg = {st: float(sum(v) / len(v)) for st, v in by_state.items()}
    return BaselineRatios(baseline_year, teacher, instructional, self_contained, national, state_avg, lea_proportion)


def load_baseline_ratios(session, baseline_year: str) -> BaselineRatios:
    """The ratios of ONE baseline vintage, selected by baseline_year (#999)."""
    print(f"\n=== Loading SPED baseline {baseline_year} ===")
    state_rows = session.query(SpedStateBaseline).filter(SpedStateBaseline.baseline_year == baseline_year).all()
    lea_rows = session.query(SpedLeaBaseline).filter(SpedLeaBaseline.baseline_year == baseline_year).all()
    require_nonempty_selection(state_rows, what=f"sped_state_baseline rows for baseline_year={baseline_year}",
                               available=lambda: distinct_years(session, "sped_state_baseline", "baseline_year"))
    require_nonempty_selection(lea_rows, what=f"sped_lea_baseline rows for baseline_year={baseline_year}",
                               available=lambda: distinct_years(session, "sped_lea_baseline", "baseline_year"))
    ratios = ratios_from_rows(baseline_year, state_rows, lea_rows)
    n = ratios.national
    print(f"  Ratios for {len(ratios.teacher)} states (teacher), {len(ratios.instructional)} (instructional), "
          f"{len(ratios.self_contained)} (self-contained); {len(ratios.lea_proportion):,} LEA proportions, "
          f"{len(ratios.state_avg_proportion)} state averages")
    print(f"  National averages (fallback): teacher={n['teacher_ratio']:.4f}, "
          f"instructional={n['instructional_ratio']:.4f}, self_contained={n['self_contained_ratio']:.4f}")
    return ratios


class DistrictEstimate(NamedTuple):
    total_enrollment: int
    total_teachers: float
    teacher_ratio: float
    instructional_ratio: float | None
    self_contained_ratio: float
    sped_proportion: float
    used_state_avg: bool
    used_national: bool
    sped_enrollment: int
    self_contained: int
    gened_enrollment: int
    sped_teachers: float
    sped_instructional: float | None
    gened_teachers: float
    method: str
    confidence: str
    notes: str | None


def estimate_district(district: YearTotals, ratios: BaselineRatios) -> DistrictEstimate | None:
    """Pure: one district's SPED/GenEd split under one baseline vintage (None = no proportion).

    Method (January 2026, self-contained focus):
    1. All SPED = Total × LEA SPED Proportion (state average when the LEA has none)
    2. Self-Contained SPED = All SPED × State Self-Contained Proportion
    3. GenEd Enrollment = Total - Self-Contained (includes mainstreamed SPED)
    4. SPED Teachers = Self-Contained × State Teacher Ratio
    5. SPED Instructional = Self-Contained × State Instructional Ratio (teachers + paras)
    6. GenEd Teachers = Total Teachers - SPED Teachers
    States without a teacher or self-contained ratio use the national averages.
    """
    state = district.state
    teacher_ratio = ratios.teacher.get(state)
    self_contained_ratio = ratios.self_contained.get(state)
    instructional_ratio = ratios.instructional.get(state)
    used_national = not teacher_ratio or not self_contained_ratio
    if used_national:
        teacher_ratio = ratios.national["teacher_ratio"]
        self_contained_ratio = ratios.national["self_contained_ratio"]
        instructional_ratio = ratios.national["instructional_ratio"]

    lea_sc = (ratios.lea_self_contained or {}).get(district.nces_id)
    used_lea_self_contained = lea_sc is not None
    if used_lea_self_contained:
        self_contained_ratio = lea_sc     # a real 0.0 (no self-contained students) is a value, not missing

    if district.nces_id in ratios.lea_proportion:
        sped_proportion, used_state_avg = ratios.lea_proportion[district.nces_id], False
    elif state in ratios.state_avg_proportion:
        sped_proportion, used_state_avg = ratios.state_avg_proportion[state], True
    else:
        return None

    total_enrollment = int(district.enrollment)
    total_teachers = float(district.instructional_staff)
    sped_enrollment = int(round(total_enrollment * sped_proportion))
    self_contained = int(round(sped_enrollment * self_contained_ratio))
    sped_teachers = round(self_contained * teacher_ratio, 2)
    sped_instructional = round(self_contained * instructional_ratio, 2) if instructional_ratio else None
    gened_teachers = round(total_teachers - sped_teachers, 2)

    notes_parts = []
    confidence = "medium"
    if used_national:
        # national average is calculated from ~53 states and is statistically robust, just less
        # precise than state-specific ratios — confidence stays "medium"
        notes_parts.append(f"State {state} missing SPED ratios; used national averages")
    if gened_teachers < 0:
        notes_parts.append("WARNING: Negative GenEd teachers (ratio mismatch)")
        confidence = "low"
    return DistrictEstimate(
        total_enrollment, total_teachers, teacher_ratio, instructional_ratio, self_contained_ratio,
        sped_proportion, used_state_avg, used_national, sped_enrollment, self_contained,
        total_enrollment - self_contained, sped_teachers, sped_instructional, gened_teachers,
        ("national_average_fallback" if used_national
         else "lea_self_contained_ratio" if used_lea_self_contained else "self_contained_ratio"), confidence,
        "; ".join(notes_parts) if notes_parts else None,
    )


def _dec(x):
    return Decimal(str(x)) if x is not None else None


def apply_estimates(session, year: str, ratios: BaselineRatios) -> int:
    """Apply one baseline vintage's ratios to `year`'s districts and upsert sped_estimates."""
    print(f"\n=== Applying baseline {ratios.baseline_year} to {year} Districts ===")

    # Per-district totals for the target year come from the year-keyed tables (#972)
    districts = select_year_totals(session, year)

    print(f"  Found {len(districts):,} districts with valid data")
    # G4 (#972): a year neither year-keyed table carries must fail loud, never "Updated: 0", exit 0.
    require_nonempty_selection(districts, what=f"districts with enrollment+staff for {year}",
                               available=lambda: available_years(session))

    created = updated = skipped_no_ratio = used_lea_ratio = used_state_avg = used_national_avg = negative_gened = 0
    existing_by_district = {
        e.district_id: e for e in session.query(SpedEstimate).filter(SpedEstimate.estimate_year == year)
    }

    written: set[str] = set()
    for district in districts:
        est = estimate_district(district, ratios)
        if est is None:
            skipped_no_ratio += 1
            continue
        written.add(district.nces_id)
        used_national_avg += est.used_national
        used_state_avg += est.used_state_avg
        used_lea_ratio += not est.used_state_avg
        negative_gened += est.gened_teachers < 0

        values = dict(
            baseline_year=ratios.baseline_year,
            current_total_enrollment=est.total_enrollment,
            current_total_teachers=_dec(est.total_teachers),
            ratio_state_sped_teachers_per_student=_dec(est.teacher_ratio),
            ratio_state_sped_instructional_per_student=_dec(est.instructional_ratio) if est.instructional_ratio else None,
            ratio_state_self_contained_proportion=_dec(est.self_contained_ratio),
            ratio_lea_sped_proportion=_dec(est.sped_proportion),
            used_state_average_for_proportion=est.used_state_avg,
            estimated_sped_enrollment=est.sped_enrollment,
            estimated_self_contained_sped=est.self_contained,
            estimated_gened_enrollment=est.gened_enrollment,
            estimated_sped_teachers=_dec(est.sped_teachers),
            estimated_sped_instructional=_dec(est.sped_instructional) if est.sped_instructional else None,
            estimated_gened_teachers=_dec(est.gened_teachers),
            estimation_method=est.method,
            confidence=est.confidence,
            notes=est.notes,
        )
        existing = existing_by_district.get(district.nces_id)
        if existing:
            # baseline_year is overwritten too: it records the vintage actually applied (#999)
            for k, v in values.items():
                setattr(existing, k, v)
            updated += 1
        else:
            session.add(SpedEstimate(district_id=district.nces_id, estimate_year=year, **values))
            created += 1

    # #993: a non-empty selection whose every district missed the baselines is the S2 symptom
    # ("Created: 0 / Updated: 0", exit 0) by another road. Key on WRITES (healthy runs skip ~1%).
    if created + updated == 0:
        raise DataGuardError(f"apply_sped_estimates: {len(districts):,} districts selected for {year} but 0 "
                             f"estimates written under baseline {ratios.baseline_year} — every district "
                             f"missed the baseline proportions (skipped {skipped_no_ratio:,})")
    if skipped_no_ratio / len(districts) > MAX_SKIPPED_SHARE:
        raise DataGuardError(f"apply_sped_estimates: {skipped_no_ratio:,} of {len(districts):,} districts "
                             f"({skipped_no_ratio / len(districts):.1%}) have no SPED proportion under baseline "
                             f"{ratios.baseline_year} (cap {MAX_SKIPPED_SHARE:.0%}) — a baseline/state mismatch")

    # A run REPLACES the year: an estimate this run did not write (the district left the selection,
    # or now has no proportion) was computed on another base/baseline and must not outlive it — the
    # #974 re-base measured 31 such rows that an upsert-only run would have left stale.
    stale = [e for d, e in existing_by_district.items() if d not in written]
    for e in stale:
        session.delete(e)

    DataLineage.log(
        session,
        entity_type="sped_estimates",
        entity_id=year,
        operation="apply_ratios",
        details={
            "year": year,
            "baseline_year": ratios.baseline_year,
            "created": created,
            "updated": updated,
            "removed_stale": len(stale),
            "skipped_no_ratio": skipped_no_ratio,
            "used_lea_ratio": used_lea_ratio,
            "used_state_avg": used_state_avg,
            "used_national_avg": used_national_avg,
            "negative_gened_warnings": negative_gened
        },
        created_by="apply_sped_estimates"
    )

    session.commit()

    print(f"\n  Results:")
    print(f"    Created: {created:,}")
    print(f"    Updated: {updated:,}")
    print(f"    Removed (no longer estimated for {year}): {len(stale):,}")
    print(f"    Skipped (no ratio): {skipped_no_ratio:,}")
    print(f"    Used LEA-specific ratio: {used_lea_ratio:,}")
    print(f"    Used state average: {used_state_avg:,}")
    print(f"    Used national average fallback: {used_national_avg:,}")
    print(f"    Negative GenEd warnings: {negative_gened:,}")

    return created + updated


def print_sample_estimates(session, year: str, n: int = 10):
    """Print sample estimates for verification."""
    print(f"\n=== Sample Estimates for {year} ===")

    samples = session.query(SpedEstimate).filter(
        SpedEstimate.estimate_year == year,
        SpedEstimate.confidence != 'low'  # Exclude low confidence
    ).order_by(SpedEstimate.current_total_enrollment.desc()).limit(n).all()

    for e in samples:
        district = session.query(District).filter(
            District.nces_id == e.district_id
        ).first()

        district_name = district.name if district else "Unknown"
        state = district.state if district else "??"

        sped_pct = (e.estimated_sped_enrollment / e.current_total_enrollment * 100) if e.current_total_enrollment else 0
        sped_teacher_pct = (float(e.estimated_sped_teachers) / float(e.current_total_teachers) * 100) if e.current_total_teachers else 0

        print(f"\n  {district_name} ({state})")
        print(f"    Enrollment: {e.current_total_enrollment:,} total → {e.estimated_sped_enrollment:,} SPED ({sped_pct:.1f}%) + {e.estimated_gened_enrollment:,} GenEd")
        print(f"    Teachers: {float(e.current_total_teachers):,.1f} total → {float(e.estimated_sped_teachers):,.1f} SPED ({sped_teacher_pct:.1f}%) + {float(e.estimated_gened_teachers):,.1f} GenEd")
        print(f"    Method: {'LEA-specific' if not e.used_state_average_for_proportion else 'State average'}")


def main():
    parser = argparse.ArgumentParser(description="Apply SPED ratios to current year data")
    parser.add_argument(
        "--year", default=NCES_PRIMARY_YEAR,
        help=f"Target school year (default: NCES_PRIMARY_YEAR = {NCES_PRIMARY_YEAR}; REQ-026 windows the blend downstream)",
    )
    parser.add_argument(
        "--baseline-year", default=SPED_BASELINE_YEAR,
        help=f"Baseline vintage whose ratios to apply (default: SPED_BASELINE_YEAR = {SPED_BASELINE_YEAR}; #999)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"SPED Estimate Application ({args.year}, baseline {args.baseline_year})")
    print("=" * 60)

    with session_scope() as session:
        ratios = load_baseline_ratios(session, args.baseline_year)
        total = apply_estimates(session, args.year, ratios)
        if total > 0:
            print_sample_estimates(session, args.year)

    print("\n" + "=" * 60)
    print("Estimates complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
