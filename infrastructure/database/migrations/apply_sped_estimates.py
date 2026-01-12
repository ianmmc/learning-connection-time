#!/usr/bin/env python3
"""
Apply SPED baseline ratios to current year district data.

This script:
1. Loads 2017-18 baseline ratios (state and LEA level)
2. For each current-year district, estimates:
   - SPED enrollment (using LEA proportion or state average)
   - GenEd enrollment (total - SPED)
   - SPED teachers (SPED enrollment × state ratio)
   - GenEd teachers (total teachers - SPED teachers)
3. Stores estimates in sped_estimates table

Usage:
    python apply_sped_estimates.py --year 2023-24
"""

import argparse
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from infrastructure.database.connection import session_scope
from infrastructure.database.models import (
    District, SpedStateBaseline, SpedLeaBaseline, SpedEstimate, DataLineage
)


def get_state_ratios(session) -> tuple[dict, dict, dict, dict]:
    """Load state SPED teacher, instructional, and self-contained ratios.

    Returns:
        Tuple of (teacher_ratios, instructional_ratios, self_contained_ratios, national_averages)
    """
    print("\n=== Loading State SPED Ratios ===")

    teacher_ratios = {}
    instructional_ratios = {}
    self_contained_ratios = {}
    records = session.query(SpedStateBaseline).filter(
        SpedStateBaseline.ratio_sped_teachers_per_student.isnot(None)
    ).all()

    for r in records:
        teacher_ratios[r.state] = float(r.ratio_sped_teachers_per_student)
        if r.ratio_sped_instructional_per_student:
            instructional_ratios[r.state] = float(r.ratio_sped_instructional_per_student)
        if r.ratio_self_contained_proportion:
            self_contained_ratios[r.state] = float(r.ratio_self_contained_proportion)

    print(f"  Loaded teacher ratios for {len(teacher_ratios)} states")
    print(f"  Loaded instructional ratios for {len(instructional_ratios)} states")
    print(f"  Loaded self-contained ratios for {len(self_contained_ratios)} states")

    # Calculate national averages as fallback for states missing data
    # (ME, VT, WI don't have 2017-18 IDEA 618 staffing data)
    national_averages = {
        "teacher_ratio": sum(teacher_ratios.values()) / len(teacher_ratios) if teacher_ratios else 0,
        "instructional_ratio": sum(instructional_ratios.values()) / len(instructional_ratios) if instructional_ratios else 0,
        "self_contained_ratio": sum(self_contained_ratios.values()) / len(self_contained_ratios) if self_contained_ratios else 0,
    }
    print(f"  National averages (fallback): teacher={national_averages['teacher_ratio']:.4f}, "
          f"instructional={national_averages['instructional_ratio']:.4f}, "
          f"self_contained={national_averages['self_contained_ratio']:.4f}")

    return teacher_ratios, instructional_ratios, self_contained_ratios, national_averages


def get_state_avg_sped_proportions(session) -> dict:
    """Calculate average SPED proportion per state from LEA data."""
    print("\n=== Calculating State Average SPED Proportions ===")

    # Calculate average for each state (excluding outliers)
    results = session.query(
        SpedLeaBaseline.state,
        func.avg(SpedLeaBaseline.ratio_sped_proportion).label('avg_proportion'),
        func.count(SpedLeaBaseline.lea_id).label('lea_count')
    ).filter(
        SpedLeaBaseline.ratio_sped_proportion.isnot(None),
        SpedLeaBaseline.ratio_sped_proportion > 0,  # Exclude negative
        SpedLeaBaseline.ratio_sped_proportion < 0.5  # Exclude > 50% (outliers)
    ).group_by(SpedLeaBaseline.state).all()

    state_avgs = {}
    for state, avg, count in results:
        state_avgs[state] = float(avg)

    print(f"  Calculated averages for {len(state_avgs)} states")
    return state_avgs


def get_lea_proportions(session) -> dict:
    """Load LEA-specific SPED proportions."""
    print("\n=== Loading LEA-Specific SPED Proportions ===")

    # Only include valid proportions (0 < p < 0.5)
    records = session.query(SpedLeaBaseline).filter(
        SpedLeaBaseline.ratio_sped_proportion.isnot(None),
        SpedLeaBaseline.ratio_sped_proportion > 0,
        SpedLeaBaseline.ratio_sped_proportion < 0.5
    ).all()

    proportions = {}
    for r in records:
        proportions[r.lea_id] = float(r.ratio_sped_proportion)

    print(f"  Loaded proportions for {len(proportions):,} LEAs")
    return proportions


def apply_estimates(session, year: str, teacher_ratios: dict, instructional_ratios: dict,
                    self_contained_ratios: dict, national_averages: dict,
                    state_avgs: dict, lea_proportions: dict):
    """
    Apply ratios to current year districts using self-contained SPED approach.

    Method (January 2026):
    1. All SPED = Total × LEA SPED Proportion
    2. Self-Contained SPED = All SPED × State Self-Contained Proportion
    3. GenEd Enrollment = Total - Self-Contained (includes mainstreamed SPED)
    4. SPED Teachers = Self-Contained × State Teacher Ratio
    5. GenEd Teachers = Total Teachers - SPED Teachers

    For states without 2017-18 SPED staffing data (ME, VT, WI), uses national
    average ratios as fallback.
    """
    print(f"\n=== Applying Estimates to {year} Districts ===")

    # Get all districts for the target year
    districts = session.query(District).filter(
        District.year == year,
        District.enrollment.isnot(None),
        District.enrollment > 0,
        District.instructional_staff.isnot(None),
        District.instructional_staff > 0
    ).all()

    print(f"  Found {len(districts):,} districts with valid data")

    created = 0
    updated = 0
    skipped_no_ratio = 0
    used_lea_ratio = 0
    used_state_avg = 0
    used_national_avg = 0
    negative_gened = 0

    for district in districts:
        state = district.state
        lea_id = district.nces_id

        # Get state ratios - fall back to national average if not available
        teacher_ratio = teacher_ratios.get(state)
        self_contained_ratio = self_contained_ratios.get(state)
        instructional_ratio = instructional_ratios.get(state)
        used_national_fallback = False

        if not teacher_ratio or not self_contained_ratio:
            # Use national averages as fallback (for ME, VT, WI, etc.)
            teacher_ratio = national_averages["teacher_ratio"]
            self_contained_ratio = national_averages["self_contained_ratio"]
            instructional_ratio = national_averages["instructional_ratio"]
            used_national_fallback = True
            used_national_avg += 1

        # Get SPED proportion - prefer LEA-specific, fall back to state average
        if lea_id in lea_proportions:
            sped_proportion = lea_proportions[lea_id]
            used_state_avg_flag = False
            used_lea_ratio += 1
        elif state in state_avgs:
            sped_proportion = state_avgs[state]
            used_state_avg_flag = True
            used_state_avg += 1
        else:
            skipped_no_ratio += 1
            continue

        # Calculate estimates using self-contained approach
        total_enrollment = int(district.enrollment)
        total_teachers = float(district.instructional_staff)

        # Step 1: All SPED enrollment
        estimated_sped_enrollment = int(round(total_enrollment * sped_proportion))

        # Step 2: Self-contained SPED (subset)
        estimated_self_contained = int(round(estimated_sped_enrollment * self_contained_ratio))

        # Step 3: GenEd = Total - Self-Contained (includes mainstreamed SPED)
        estimated_gened_enrollment = total_enrollment - estimated_self_contained

        # Step 4: SPED teachers (per self-contained student)
        estimated_sped_teachers = round(estimated_self_contained * teacher_ratio, 2)

        # Step 5: SPED instructional (teachers + paras, per self-contained student)
        estimated_sped_instructional = round(estimated_self_contained * instructional_ratio, 2) if instructional_ratio else None

        # Step 6: GenEd teachers
        estimated_gened_teachers = round(total_teachers - estimated_sped_teachers, 2)

        # Determine confidence and notes
        notes_parts = []
        confidence = "medium"

        if used_national_fallback:
            notes_parts.append(f"State {state} missing SPED ratios; used national averages")
            # Keep confidence at "medium" - national average is calculated from 53 states
            # and is statistically robust, just less precise than state-specific ratios

        if estimated_gened_teachers < 0:
            notes_parts.append("WARNING: Negative GenEd teachers (ratio mismatch)")
            confidence = "low"
            negative_gened += 1

        notes = "; ".join(notes_parts) if notes_parts else None
        estimation_method = "national_average_fallback" if used_national_fallback else "self_contained_ratio"

        # Create or update estimate
        existing = session.query(SpedEstimate).filter(
            SpedEstimate.district_id == lea_id,
            SpedEstimate.estimate_year == year
        ).first()

        if existing:
            # Update existing
            existing.current_total_enrollment = total_enrollment
            existing.current_total_teachers = Decimal(str(total_teachers))
            existing.ratio_state_sped_teachers_per_student = Decimal(str(teacher_ratio))
            existing.ratio_state_sped_instructional_per_student = Decimal(str(instructional_ratio)) if instructional_ratio else None
            existing.ratio_state_self_contained_proportion = Decimal(str(self_contained_ratio))
            existing.ratio_lea_sped_proportion = Decimal(str(sped_proportion))
            existing.used_state_average_for_proportion = used_state_avg_flag
            existing.estimated_sped_enrollment = estimated_sped_enrollment
            existing.estimated_self_contained_sped = estimated_self_contained
            existing.estimated_gened_enrollment = estimated_gened_enrollment
            existing.estimated_sped_teachers = Decimal(str(estimated_sped_teachers))
            existing.estimated_sped_instructional = Decimal(str(estimated_sped_instructional)) if estimated_sped_instructional else None
            existing.estimated_gened_teachers = Decimal(str(estimated_gened_teachers))
            existing.estimation_method = estimation_method
            existing.confidence = confidence
            existing.notes = notes
            updated += 1
        else:
            # Create new
            estimate = SpedEstimate(
                district_id=lea_id,
                estimate_year=year,
                baseline_year="2017-18",
                current_total_enrollment=total_enrollment,
                current_total_teachers=Decimal(str(total_teachers)),
                ratio_state_sped_teachers_per_student=Decimal(str(teacher_ratio)),
                ratio_state_sped_instructional_per_student=Decimal(str(instructional_ratio)) if instructional_ratio else None,
                ratio_state_self_contained_proportion=Decimal(str(self_contained_ratio)),
                ratio_lea_sped_proportion=Decimal(str(sped_proportion)),
                used_state_average_for_proportion=used_state_avg_flag,
                estimated_sped_enrollment=estimated_sped_enrollment,
                estimated_self_contained_sped=estimated_self_contained,
                estimated_gened_enrollment=estimated_gened_enrollment,
                estimated_sped_teachers=Decimal(str(estimated_sped_teachers)),
                estimated_sped_instructional=Decimal(str(estimated_sped_instructional)) if estimated_sped_instructional else None,
                estimated_gened_teachers=Decimal(str(estimated_gened_teachers)),
                estimation_method=estimation_method,
                confidence=confidence,
                notes=notes
            )
            session.add(estimate)
            created += 1

    # Log lineage
    DataLineage.log(
        session,
        entity_type="sped_estimates",
        entity_id=year,
        operation="apply_ratios",
        details={
            "year": year,
            "created": created,
            "updated": updated,
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
    parser.add_argument("--year", default="2023-24", help="Target school year (default: 2023-24)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"SPED Estimate Application ({args.year})")
    print("=" * 60)

    with session_scope() as session:
        # Load baseline ratios
        teacher_ratios, instructional_ratios, self_contained_ratios, national_averages = get_state_ratios(session)
        state_avgs = get_state_avg_sped_proportions(session)
        lea_proportions = get_lea_proportions(session)

        # Apply to current year
        total = apply_estimates(session, args.year, teacher_ratios, instructional_ratios,
                                self_contained_ratios, national_averages, state_avgs, lea_proportions)

        # Show samples
        if total > 0:
            print_sample_estimates(session, args.year)

    print("\n" + "=" * 60)
    print("Estimates complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
