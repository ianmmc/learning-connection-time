#!/usr/bin/env python3
"""
Calculate LCT variants for districts with granular staff data.

LCT Scopes (5 base scopes):
1. LCT-Teachers: K-12 teachers (elem + sec + kinder, NO ungraded, NO prek)
2. LCT-Core: K-12 teachers + ungraded (NO prek)
3. LCT-Instructional: core + coordinators + paraprofessionals
4. LCT-Support: instructional + counselors + psychologists + student support
5. LCT-All: all staff except Pre-K teachers

Teacher-Level Variants (3 additional):
- LCT-Teachers-Elementary: elementary + kindergarten teachers / K-5 enrollment
- LCT-Teachers-Secondary: secondary teachers / 6-12 enrollment

SPED Segmentation Variants (January 2026):
- LCT-Core-SPED: estimated SPED teachers / estimated SPED enrollment (for audit)
- LCT-Teachers-GenEd: estimated GenEd teachers / estimated GenEd enrollment
- LCT-Instructional-SPED: (SPED teachers + paras) / estimated SPED enrollment
  (Uses 2017-18 baseline ratios from IDEA 618 + CRDC to estimate SPED/GenEd split)

State-Specific Data Integration (January 2026):
- California: Uses actual SPED self-contained enrollment from CA CDE when available
  - DATA PRECEDENCE: CA actual (2023-24) > Federal estimate (2017-18)
  - Applies to 990 CA districts with actual SPED environment data
  - Note: Requires CA staff data in NCES (currently unavailable for 2023-24)
  - Teacher estimates still use 2017-18 federal ratios

Key Decisions (December 2025):
- ALL scopes use K-12 enrollment (exclude Pre-K)
- ALL scopes exclude Pre-K teachers
- Ungraded teachers EXCLUDED from LCT-Teachers variants
- Ungraded teachers INCLUDED in other scopes

Usage:
    # Default: Blended mode - uses most recent data within REQ-026 3-year window
    python calculate_lct_variants.py [--output-dir path]

    # Target year mode: Enrollment anchored to target year, staff/bell blended
    python calculate_lct_variants.py --target-year 2023-24 [--output-dir path]

Reference: docs/STAFFING_DATA_ENHANCEMENT_PLAN.md
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Optional: Parquet support
try:
    import pyarrow
    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False


def get_utc_timestamp() -> str:
    """
    Generate ISO 8601 UTC timestamp for filenames.

    Format: YYYYMMDDTHHMMSSZ (filesystem-safe, sortable)
    Example: 20251227T170900Z
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def compute_input_hash(session) -> str:
    """
    Compute hash of input data state for change detection.

    Used to determine if incremental calculation is needed.
    """
    from infrastructure.database.models import StaffCountsEffective, EnrollmentByGrade

    # Get counts and max update times as proxy for data state
    staff_count = session.query(StaffCountsEffective).count()
    enrollment_count = session.query(EnrollmentByGrade).count()

    hash_input = f"{staff_count}:{enrollment_count}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:16]


from infrastructure.database.connection import session_scope, get_engine
from infrastructure.database.models import (
    District,
    BellSchedule,
    StateRequirement,
    StaffCountsEffective,
    EnrollmentByGrade,
    CalculationRun,
    CalculationMode,
    SpedEstimate,
    CASpedDistrictEnvironments,
    LCTCalculation,
)


# LCT scope definitions - base scopes
BASE_SCOPES = [
    "teachers_only",
    "teachers_core",
    "instructional",
    "instructional_plus_support",
    "all",
]

# Teacher-level variants
TEACHER_LEVEL_SCOPES = [
    "teachers_elementary",
    "teachers_secondary",
]

# SPED segmentation variants (January 2026)
# core_sped: SPED teachers / SPED students (for audit/reconciliation)
# teachers_gened: GenEd teachers / GenEd students
# instructional_sped: (SPED teachers + paras) / SPED students
SPED_SCOPES = [
    "core_sped",
    "teachers_gened",
    "instructional_sped",
]


def get_instructional_minutes(
    session,
    district_id: str,
    state: str,
    grade_level: str = "high"
) -> tuple[int, str, str]:
    """
    Get instructional minutes for a district.

    Priority:
    1. Bell schedule for requested grade level (enriched data)
    2. Bell schedule for any available grade level (K-8 districts, etc.)
    3. State requirement (statutory fallback)
    4. Default (360 minutes)

    Returns:
        Tuple of (minutes, source, year)
    """
    # Try bell schedule for requested grade level first
    bell = session.query(BellSchedule).filter(
        BellSchedule.district_id == district_id,
        BellSchedule.grade_level == grade_level
    ).order_by(BellSchedule.year.desc()).first()

    if bell and bell.instructional_minutes:
        return bell.instructional_minutes, "bell_schedule", bell.year

    # Try any available bell schedule (for K-8 districts, etc.)
    # Priority: high > middle > elementary
    for fallback_level in ["high", "middle", "elementary"]:
        if fallback_level == grade_level:
            continue  # Already tried this one
        bell = session.query(BellSchedule).filter(
            BellSchedule.district_id == district_id,
            BellSchedule.grade_level == fallback_level
        ).order_by(BellSchedule.year.desc()).first()
        if bell and bell.instructional_minutes:
            return bell.instructional_minutes, f"bell_schedule_{fallback_level}", bell.year

    # Fall back to state requirement
    state_req = session.query(StateRequirement).filter(
        StateRequirement.state == state
    ).first()

    if state_req:
        minutes = state_req.get_minutes(grade_level)
        if minutes:
            return minutes, "state_requirement", "2023-24"

    # Ultimate fallback
    return 360, "default", "2023-24"


def calculate_lct(
    instructional_minutes: int,
    staff_count: float,
    enrollment: int
) -> Optional[float]:
    """Calculate LCT value."""
    if not staff_count or staff_count <= 0:
        return None
    if not enrollment or enrollment <= 0:
        return None

    # Convert to float to handle Decimal types from database
    return (float(instructional_minutes) * float(staff_count)) / float(enrollment)


def validate_level_lct(
    lct_teachers: Optional[float],
    lct_elementary: Optional[float],
    lct_secondary: Optional[float],
    teachers_k12: Optional[float],
    teachers_elem: Optional[float],
    teachers_sec: Optional[float],
    enrollment_k12: Optional[int],
    enrollment_elem: Optional[int],
    enrollment_sec: Optional[int],
) -> tuple[bool, bool, List[str]]:
    """
    Validate level-based LCT calculations.

    Returns:
        Tuple of (elem_valid, sec_valid, notes)
    """
    notes = []
    elem_valid = True
    sec_valid = True

    # Check for impossible LCT values (> 360 minutes)
    if lct_elementary and lct_elementary > 360:
        elem_valid = False
        notes.append(f"LCT-Elementary ({lct_elementary:.1f}) exceeds 360 min")

    if lct_secondary and lct_secondary > 360:
        sec_valid = False
        notes.append(f"LCT-Secondary ({lct_secondary:.1f}) exceeds 360 min")

    # Check for mismatched teacher/enrollment (teachers but no students or vice versa)
    if teachers_elem and teachers_elem > 0 and (not enrollment_elem or enrollment_elem == 0):
        elem_valid = False
        notes.append("Elementary teachers but no elementary enrollment")

    if not teachers_elem or teachers_elem == 0:
        if enrollment_elem and enrollment_elem > 0:
            elem_valid = False
            notes.append("Elementary enrollment but no elementary teachers")

    if teachers_sec and teachers_sec > 0 and (not enrollment_sec or enrollment_sec == 0):
        sec_valid = False
        notes.append("Secondary teachers but no secondary enrollment")

    if not teachers_sec or teachers_sec == 0:
        if enrollment_sec and enrollment_sec > 0:
            sec_valid = False
            notes.append("Secondary enrollment but no secondary teachers")

    # Check for consistency: elem + sec teachers should roughly equal total
    if teachers_k12 and teachers_elem and teachers_sec:
        level_sum = float(teachers_elem or 0) + float(teachers_sec or 0)
        if level_sum > 0 and teachers_k12 > 0:
            ratio = level_sum / float(teachers_k12)
            if ratio < 0.8 or ratio > 1.2:
                notes.append(f"Teacher sum mismatch: elem+sec={level_sum:.1f} vs total={teachers_k12:.1f}")

    return elem_valid, sec_valid, notes


def get_most_recent_enrollment(session, target_year: Optional[str] = None) -> Dict[str, Any]:
    """
    Get enrollment data, preferring target_year if specified, else most recent.

    Args:
        session: Database session
        target_year: If specified, filter to this year (TARGET_YEAR mode)

    Returns:
        Dict mapping district_id to (enrollment_record, source_year)
    """
    from sqlalchemy import func

    if target_year:
        # TARGET_YEAR mode: enrollment anchored to specific year
        enrollments = session.query(EnrollmentByGrade).filter(
            EnrollmentByGrade.source_year == target_year
        ).all()
        return {e.district_id: (e, target_year) for e in enrollments}

    # BLENDED mode: get most recent enrollment per district
    # Subquery to find max year per district
    subq = session.query(
        EnrollmentByGrade.district_id,
        func.max(EnrollmentByGrade.source_year).label('max_year')
    ).group_by(EnrollmentByGrade.district_id).subquery()

    enrollments = session.query(EnrollmentByGrade).join(
        subq,
        (EnrollmentByGrade.district_id == subq.c.district_id) &
        (EnrollmentByGrade.source_year == subq.c.max_year)
    ).all()

    return {e.district_id: (e, e.source_year) for e in enrollments}


def get_most_recent_sped(session, target_year: Optional[str] = None) -> Dict[str, Any]:
    """
    Get SPED estimates, preferring target_year if specified, else most recent.

    Args:
        session: Database session
        target_year: If specified, prefer this year but allow blending

    Returns:
        Dict mapping district_id to (sped_record, source_year)
    """
    from sqlalchemy import func

    if target_year:
        # First try target year
        sped_estimates = session.query(SpedEstimate).filter(
            SpedEstimate.estimate_year == target_year
        ).all()
        if sped_estimates:
            return {s.district_id: (s, target_year) for s in sped_estimates}

    # Get most recent SPED per district
    subq = session.query(
        SpedEstimate.district_id,
        func.max(SpedEstimate.estimate_year).label('max_year')
    ).group_by(SpedEstimate.district_id).subquery()

    sped_estimates = session.query(SpedEstimate).join(
        subq,
        (SpedEstimate.district_id == subq.c.district_id) &
        (SpedEstimate.estimate_year == subq.c.max_year)
    ).all()

    return {s.district_id: (s, s.estimate_year) for s in sped_estimates}


def get_most_recent_ca_sped(session, target_year: Optional[str] = None) -> Dict[str, Any]:
    """
    Get CA actual SPED data, preferring target_year if specified, else most recent.

    Args:
        session: Database session
        target_year: If specified, prefer this year but allow blending

    Returns:
        Dict mapping nces_id to (ca_sped_record, source_year)
    """
    from sqlalchemy import func

    if target_year:
        ca_sped = session.query(CASpedDistrictEnvironments).filter(
            CASpedDistrictEnvironments.year == target_year
        ).all()
        if ca_sped:
            return {ca.nces_id: (ca, target_year) for ca in ca_sped}

    # Get most recent CA SPED per district
    subq = session.query(
        CASpedDistrictEnvironments.nces_id,
        func.max(CASpedDistrictEnvironments.year).label('max_year')
    ).group_by(CASpedDistrictEnvironments.nces_id).subquery()

    ca_sped = session.query(CASpedDistrictEnvironments).join(
        subq,
        (CASpedDistrictEnvironments.nces_id == subq.c.nces_id) &
        (CASpedDistrictEnvironments.year == subq.c.max_year)
    ).all()

    return {ca.nces_id: (ca, ca.year) for ca in ca_sped}


def calculate_year_span(years: List[str]) -> int:
    """
    Calculate year span from a list of school year strings.

    Args:
        years: List of school year strings like '2023-24', '2024-25'

    Returns:
        Absolute difference between max and min start years
    """
    if not years:
        return 0

    def extract_start_year(year_str: str) -> int:
        return int(year_str.split('-')[0])

    numeric_years = [extract_start_year(y) for y in years if y]
    if len(numeric_years) < 2:
        return 0

    return max(numeric_years) - min(numeric_years)


def calculate_all_variants(
    session,
    calculation_mode: CalculationMode = CalculationMode.BLENDED,
    target_year: Optional[str] = None
) -> tuple[pd.DataFrame, str, str]:
    """
    Calculate all LCT variants for all districts with staff data.

    Args:
        session: Database session
        calculation_mode: BLENDED or TARGET_YEAR
        target_year: Required for TARGET_YEAR mode, optional for BLENDED

    Returns:
        Tuple of (DataFrame with LCT calculations, data_year_min, data_year_max)
    """
    print("Calculating LCT variants...")
    mode_str = f"{calculation_mode.value}"
    if target_year:
        mode_str += f" (target: {target_year})"
    print(f"  Mode: {mode_str}")

    # Track all years used for data range reporting
    all_years_used = set()

    # Get all effective staff counts (excluding shared service entities)
    # Shared service entities (CTCs, BOCES, cooperatives, etc.) serve students part-time
    # from multiple districts, causing artificially inflated teacher-to-student ratios
    staff_records = session.query(StaffCountsEffective).join(
        District,
        StaffCountsEffective.district_id == District.nces_id
    ).filter(
        District.is_shared_service_entity == False
    ).all()
    print(f"  Found {len(staff_records):,} districts with staff data (excluding shared service entities)")

    # Get enrollment (mode-aware)
    enrollment_with_years = get_most_recent_enrollment(
        session,
        target_year if calculation_mode == CalculationMode.TARGET_YEAR else None
    )
    enrollment_map = {k: v[0] for k, v in enrollment_with_years.items()}
    enrollment_years = {k: v[1] for k, v in enrollment_with_years.items()}
    print(f"  Found {len(enrollment_map):,} districts with grade-level enrollment")

    # Get SPED estimates (mode-aware - can blend in both modes)
    sped_with_years = get_most_recent_sped(session, target_year)
    sped_map = {k: v[0] for k, v in sped_with_years.items()}
    sped_years = {k: v[1] for k, v in sped_with_years.items()}
    print(f"  Found {len(sped_map):,} districts with SPED estimates")

    # Get CA actual SPED data (mode-aware - can blend in both modes)
    ca_sped_with_years = get_most_recent_ca_sped(session, target_year)
    ca_sped_map = {k: v[0] for k, v in ca_sped_with_years.items()}
    ca_sped_years = {k: v[1] for k, v in ca_sped_with_years.items()}
    print(f"  Found {len(ca_sped_map):,} CA districts with actual SPED data")

    # Get districts for state info
    district_map = {}
    districts = session.query(District).all()
    for d in districts:
        district_map[d.nces_id] = d

    results = []
    processed = 0
    qa_issues = 0

    for staff in staff_records:
        district = district_map.get(staff.district_id)
        if not district:
            continue

        # Get instructional minutes
        minutes, minutes_source, minutes_year = get_instructional_minutes(
            session, staff.district_id, district.state, "high"
        )

        # Get enrollments from enrollment_by_grade table
        grade_enrollment = enrollment_map.get(staff.district_id)
        if not grade_enrollment:
            continue  # Skip districts without grade-level enrollment data

        # Track years used for this district
        enroll_year = enrollment_years.get(staff.district_id)
        staff_eff_year = staff.effective_year
        if enroll_year:
            all_years_used.add(enroll_year)
        if staff_eff_year:
            all_years_used.add(staff_eff_year)
        if minutes_year:
            all_years_used.add(minutes_year)

        # ALL scopes now use K-12 enrollment (exclude Pre-K)
        k12_enrollment = grade_enrollment.enrollment_k12 or 0
        elem_enrollment = grade_enrollment.enrollment_elementary or 0
        sec_enrollment = grade_enrollment.enrollment_secondary or 0

        if k12_enrollment <= 0:
            continue  # Skip districts with no K-12 enrollment

        # Get teacher counts for level variants
        teachers_k12 = float(staff.teachers_k12) if staff.teachers_k12 else None
        teachers_elem = float(staff.teachers_elementary_k5) if staff.teachers_elementary_k5 else None
        teachers_sec = float(staff.teachers_secondary_6_12) if staff.teachers_secondary_6_12 else None

        # Calculate level LCT values for validation
        lct_elementary = calculate_lct(minutes, teachers_elem, elem_enrollment) if teachers_elem and elem_enrollment else None
        lct_secondary = calculate_lct(minutes, teachers_sec, sec_enrollment) if teachers_sec and sec_enrollment else None
        lct_teachers = calculate_lct(minutes, teachers_k12, k12_enrollment) if teachers_k12 else None

        # Validate level calculations
        elem_valid, sec_valid, notes = validate_level_lct(
            lct_teachers, lct_elementary, lct_secondary,
            teachers_k12, teachers_elem, teachers_sec,
            k12_enrollment, elem_enrollment, sec_enrollment
        )

        level_lct_notes = "; ".join(notes) if notes else ""
        if notes:
            qa_issues += 1

        # Calculate base scopes
        for scope in BASE_SCOPES:
            # Get the appropriate staff count - ALL use K-12 enrollment now
            if scope == "teachers_only":
                staff_count = float(staff.scope_teachers_only) if staff.scope_teachers_only else None
            elif scope == "teachers_core":
                staff_count = float(staff.scope_teachers_core) if staff.scope_teachers_core else None
            elif scope == "instructional":
                staff_count = float(staff.scope_instructional) if staff.scope_instructional else None
            elif scope == "instructional_plus_support":
                staff_count = float(staff.scope_instructional_plus_support) if staff.scope_instructional_plus_support else None
            elif scope == "all":
                staff_count = float(staff.scope_all) if staff.scope_all else None
            else:
                continue

            # Calculate LCT using K-12 enrollment for all scopes
            lct_value = calculate_lct(minutes, staff_count, k12_enrollment)

            if lct_value is not None:
                results.append({
                    "district_id": staff.district_id,
                    "district_name": district.name,
                    "state": district.state,
                    "staff_scope": scope,
                    "lct_value": round(lct_value, 2),
                    "instructional_minutes": minutes,
                    "instructional_minutes_source": minutes_source,
                    "instructional_minutes_year": minutes_year,
                    "staff_count": staff_count,
                    "staff_source": staff.primary_source,
                    "staff_year": staff.effective_year,
                    "enrollment": k12_enrollment,
                    "enrollment_type": "k12",
                    "level_lct_notes": "",  # No level notes for base scopes
                })

        # Calculate teacher-level variants
        # LCT-Teachers-Elementary
        if elem_valid and lct_elementary is not None:
            results.append({
                "district_id": staff.district_id,
                "district_name": district.name,
                "state": district.state,
                "staff_scope": "teachers_elementary",
                "lct_value": round(lct_elementary, 2),
                "instructional_minutes": minutes,
                "instructional_minutes_source": minutes_source,
                "instructional_minutes_year": minutes_year,
                "staff_count": teachers_elem,
                "staff_source": staff.primary_source,
                "staff_year": staff.effective_year,
                "enrollment": elem_enrollment,
                "enrollment_type": "elementary_k5",
                "level_lct_notes": level_lct_notes,
            })

        # LCT-Teachers-Secondary
        if sec_valid and lct_secondary is not None:
            results.append({
                "district_id": staff.district_id,
                "district_name": district.name,
                "state": district.state,
                "staff_scope": "teachers_secondary",
                "lct_value": round(lct_secondary, 2),
                "instructional_minutes": minutes,
                "instructional_minutes_source": minutes_source,
                "instructional_minutes_year": minutes_year,
                "staff_count": teachers_sec,
                "staff_source": staff.primary_source,
                "staff_year": staff.effective_year,
                "enrollment": sec_enrollment,
                "enrollment_type": "secondary_6_12",
                "level_lct_notes": level_lct_notes,
            })

        # === SPED/GenEd Segmentation Variants (January 2026) ===
        # Three metrics:
        # - core_sped: SPED teachers / Self-Contained SPED students (for audit/reconciliation)
        # - teachers_gened: GenEd teachers / GenEd students (includes mainstreamed SPED)
        # - instructional_sped: (SPED teachers + paras) / Self-Contained SPED students

        # DATA PRECEDENCE: CA actual (year-matched) > Federal estimate
        ca_actual = ca_sped_map.get(staff.district_id)
        sped_estimate = sped_map.get(staff.district_id)

        # Determine enrollment source and values
        sped_enrollment = None
        gened_enrollment = None
        enrollment_source = None
        enrollment_confidence = None

        if ca_actual and ca_actual.confidence != "low":
            # Use CA actual self-contained SPED enrollment (2023-24 or later)
            sped_enrollment = ca_actual.sped_self_contained
            # Calculate GenEd as total K-12 minus self-contained SPED
            gened_enrollment = k12_enrollment - (sped_enrollment or 0) if sped_enrollment else None
            ca_sped_year = ca_sped_years.get(staff.district_id, "unknown")
            enrollment_source = f"ca_actual_{ca_sped_year}"
            enrollment_confidence = ca_actual.confidence
            all_years_used.add(ca_sped_year)
        elif sped_estimate and sped_estimate.confidence != "low":
            # Fallback to Federal estimate (2017-18 baseline)
            sped_enrollment = sped_estimate.estimated_self_contained_sped
            gened_enrollment = sped_estimate.estimated_gened_enrollment
            enrollment_source = "sped_estimate_2017-18"
            enrollment_confidence = sped_estimate.confidence

        # Teacher estimates: Always use 2017-18 federal ratios (we don't have CA actual teacher splits)
        if sped_estimate and sped_estimate.confidence != "low":
            sped_teachers = float(sped_estimate.estimated_sped_teachers) if sped_estimate.estimated_sped_teachers else None
            sped_instructional = float(sped_estimate.estimated_sped_instructional) if sped_estimate.estimated_sped_instructional else None
            gened_teachers = float(sped_estimate.estimated_gened_teachers) if sped_estimate.estimated_gened_teachers else None

            # LCT-Core-SPED: teachers only (for audit/reconciliation with teachers_gened)
            if sped_teachers and sped_teachers > 0 and sped_enrollment and sped_enrollment > 0:
                lct_core_sped = calculate_lct(minutes, sped_teachers, sped_enrollment)
                # Cap at 360 but flag if it would exceed (high SPED teacher ratio)
                sped_capped = False
                if lct_core_sped is not None and lct_core_sped > 360:
                    sped_capped = True
                    lct_core_sped = 360.0  # Cap at school day maximum
                if lct_core_sped is not None and lct_core_sped <= 360:
                    # Build notes, including cap flag if applicable
                    core_sped_notes = f"Self-contained SPED enrollment: {enrollment_source}, confidence: {enrollment_confidence}"
                    if sped_capped:
                        core_sped_notes += "; WARN_SPED_RATIO_CAP: LCT capped at 360 (high teacher-to-student ratio)"
                    sped_year = sped_years.get(staff.district_id, "2017-18")
                    all_years_used.add(sped_year)
                    results.append({
                        "district_id": staff.district_id,
                        "district_name": district.name,
                        "state": district.state,
                        "staff_scope": "core_sped",
                        "lct_value": round(lct_core_sped, 2),
                        "instructional_minutes": minutes,
                        "instructional_minutes_source": minutes_source,
                        "instructional_minutes_year": minutes_year,
                        "staff_count": sped_teachers,
                        "staff_source": "sped_estimate_2017-18",
                        "staff_year": sped_year,
                        "enrollment": sped_enrollment,
                        "enrollment_type": "self_contained_sped",
                        "enrollment_source": enrollment_source,
                        "level_lct_notes": core_sped_notes,
                    })

            # LCT-Teachers-GenEd
            if gened_teachers and gened_teachers > 0 and gened_enrollment and gened_enrollment > 0:
                lct_gened = calculate_lct(minutes, gened_teachers, gened_enrollment)
                if lct_gened is not None and lct_gened <= 360:  # Sanity check
                    gened_sped_year = sped_years.get(staff.district_id, "2017-18")
                    all_years_used.add(gened_sped_year)
                    results.append({
                        "district_id": staff.district_id,
                        "district_name": district.name,
                        "state": district.state,
                        "staff_scope": "teachers_gened",
                        "lct_value": round(lct_gened, 2),
                        "instructional_minutes": minutes,
                        "instructional_minutes_source": minutes_source,
                        "instructional_minutes_year": minutes_year,
                        "staff_count": gened_teachers,
                        "staff_source": "sped_estimate_2017-18",
                        "staff_year": gened_sped_year,
                        "enrollment": gened_enrollment,
                        "enrollment_type": "gened",
                        "enrollment_source": enrollment_source,
                        "level_lct_notes": f"GenEd enrollment: {enrollment_source}, confidence: {enrollment_confidence}",
                    })

            # LCT-Instructional-SPED: teachers + paras (fuller picture of SPED support)
            if sped_instructional and sped_instructional > 0 and sped_enrollment and sped_enrollment > 0:
                lct_instr_sped = calculate_lct(minutes, sped_instructional, sped_enrollment)
                # Cap at 360 but flag if it would exceed (high SPED instructional ratio)
                instr_sped_capped = False
                if lct_instr_sped is not None and lct_instr_sped > 360:
                    instr_sped_capped = True
                    lct_instr_sped = 360.0  # Cap at school day maximum
                if lct_instr_sped is not None and lct_instr_sped <= 360:
                    # Build notes, including cap flag if applicable
                    instr_sped_notes = f"Self-contained SPED enrollment: {enrollment_source}, instructional staff confidence: {enrollment_confidence}"
                    if instr_sped_capped:
                        instr_sped_notes += "; WARN_SPED_RATIO_CAP: LCT capped at 360 (high instructional-to-student ratio)"
                    instr_sped_year = sped_years.get(staff.district_id, "2017-18")
                    all_years_used.add(instr_sped_year)
                    results.append({
                        "district_id": staff.district_id,
                        "district_name": district.name,
                        "state": district.state,
                        "staff_scope": "instructional_sped",
                        "lct_value": round(lct_instr_sped, 2),
                        "instructional_minutes": minutes,
                        "instructional_minutes_source": minutes_source,
                        "instructional_minutes_year": minutes_year,
                        "staff_count": sped_instructional,
                        "staff_source": "sped_estimate_2017-18",
                        "staff_year": instr_sped_year,
                        "enrollment": sped_enrollment,
                        "enrollment_type": "self_contained_sped",
                        "enrollment_source": enrollment_source,
                        "level_lct_notes": instr_sped_notes,
                    })

        processed += 1
        if processed % 1000 == 0:
            print(f"  Processed {processed:,} / {len(staff_records):,}")

    print(f"  Calculated {len(results):,} LCT values")
    print(f"  Districts with QA notes: {qa_issues:,}")

    # Compute data year range
    def extract_start_year(year_str: str) -> int:
        """Extract numeric start year from school year string."""
        try:
            return int(year_str.split('-')[0])
        except (ValueError, AttributeError):
            return 0

    valid_years = [y for y in all_years_used if y and extract_start_year(y) > 2000]
    if valid_years:
        year_nums = [extract_start_year(y) for y in valid_years]
        data_year_min = min(valid_years, key=extract_start_year)
        data_year_max = max(valid_years, key=extract_start_year)
        year_span = max(year_nums) - min(year_nums)
        print(f"  Data year range: {data_year_min} to {data_year_max} (span: {year_span} years)")
    else:
        data_year_min = None
        data_year_max = None

    return pd.DataFrame(results), data_year_min, data_year_max


def apply_data_safeguards(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply cross-scope data safeguards to flag questionable data.

    Safeguards (based on Gemini analysis, January 2026):
    - ERR_FLAT_STAFF: All 5 base scopes have identical staff counts
    - ERR_IMPOSSIBLE_SSR: Staff-to-student ratio > 0.5 (more than 1 staff per 2 students)
    - ERR_VOLATILE: K-12 enrollment < 50 (high statistical volatility)
    - ERR_RATIO_CEILING: Teachers = 100% of all staff (incomplete reporting)
    - WARN_LCT_LOW: LCT < 5 minutes (very high enrollment relative to staff)
    - WARN_LCT_HIGH: LCT > 120 minutes for teachers_only scope

    Flags are appended to level_lct_notes column, not used for filtering.
    This maintains transparency while identifying suspect data.

    Returns:
        DataFrame with safeguard flags added to level_lct_notes
    """
    print("\nApplying data safeguards...")

    # Make a copy to avoid modifying original during iteration
    df = df.copy()

    # Initialize counters
    safeguard_counts = {
        'ERR_FLAT_STAFF': 0,
        'ERR_IMPOSSIBLE_SSR': 0,
        'ERR_VOLATILE': 0,
        'ERR_RATIO_CEILING': 0,
        'WARN_LCT_LOW': 0,
        'WARN_LCT_HIGH': 0,
        'WARN_SPED_RATIO_CAP': 0,
    }

    # Group by district to check cross-scope conditions
    base_scopes = ['teachers_only', 'teachers_core', 'instructional',
                   'instructional_plus_support', 'all']

    # Build district-level lookup for cross-scope checks
    district_staff = {}  # district_id -> {scope: staff_count}
    district_flags = {}  # district_id -> set of flags

    for _, row in df.iterrows():
        did = row['district_id']
        scope = row['staff_scope']

        if did not in district_staff:
            district_staff[did] = {}
            district_flags[did] = set()

        if scope in base_scopes:
            district_staff[did][scope] = row['staff_count']

    # Check flat staffing and ratio ceiling per district
    for did, scopes in district_staff.items():
        if len(scopes) >= 5:  # Has all 5 base scopes
            staff_values = [scopes.get(s) for s in base_scopes if s in scopes]

            # Flat staffing: all values identical and not None
            if len(set(v for v in staff_values if v is not None)) == 1:
                district_flags[did].add('ERR_FLAT_STAFF')
                safeguard_counts['ERR_FLAT_STAFF'] += 1

            # Ratio ceiling: teachers_only = all (100% teachers)
            teachers = scopes.get('teachers_only')
            all_staff = scopes.get('all')
            if teachers and all_staff and teachers > 0 and all_staff > 0:
                if abs(teachers - all_staff) < 0.01:  # Effectively equal
                    district_flags[did].add('ERR_RATIO_CEILING')
                    safeguard_counts['ERR_RATIO_CEILING'] += 1

    # Apply flags to individual rows
    def add_safeguard_flags(row):
        flags = []
        did = row['district_id']
        scope = row['staff_scope']
        enrollment = float(row['enrollment']) if row['enrollment'] else 0
        staff_count = float(row['staff_count']) if row['staff_count'] else 0
        lct_value = float(row['lct_value']) if row['lct_value'] else 0
        enrollment_type = row['enrollment_type']

        # Add district-level flags (only to base scopes to avoid duplicates)
        if scope in base_scopes:
            flags.extend(district_flags.get(did, set()))

        # SSR check: staff/enrollment > 0.5 (only for base scopes, not SPED which has high ratios by design)
        if scope in base_scopes and staff_count and enrollment and enrollment > 0:
            ssr = staff_count / enrollment
            if ssr > 0.5:
                flags.append('ERR_IMPOSSIBLE_SSR')

        # Volatility check: k12 enrollment < 50
        if enrollment_type == 'k12' and enrollment and enrollment < 50:
            flags.append('ERR_VOLATILE')

        # LCT outlier checks
        if lct_value and lct_value < 5:
            flags.append('WARN_LCT_LOW')

        if scope == 'teachers_only' and lct_value and lct_value > 120:
            flags.append('WARN_LCT_HIGH')

        # Combine with existing notes
        existing = row['level_lct_notes'] or ''
        if flags:
            flag_str = '; '.join(sorted(set(flags)))
            if existing:
                return f"{existing}; {flag_str}"
            return flag_str
        return existing

    # Apply flags
    df['level_lct_notes'] = df.apply(add_safeguard_flags, axis=1)

    # Count safeguards in final data (convert to Python int for JSON serialization)
    for flag in safeguard_counts.keys():
        count = df['level_lct_notes'].str.contains(flag, na=False).sum()
        safeguard_counts[flag] = int(count)

    # Print summary
    print("  Safeguard flags applied:")
    for flag, count in safeguard_counts.items():
        if count > 0:
            print(f"    {flag}: {count:,} records")

    total_flagged = df[df['level_lct_notes'].str.len() > 0]['district_id'].nunique()
    print(f"  Total districts with any flag: {total_flagged:,}")

    return df, safeguard_counts


def generate_summary_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Generate summary statistics by scope."""
    summary = df.groupby("staff_scope").agg({
        "lct_value": ["count", "mean", "median", "std", "min", "max"],
        "district_id": "nunique"
    }).round(2)

    summary.columns = ["count", "mean", "median", "std", "min", "max", "districts"]
    summary = summary.reset_index()

    return summary


def generate_state_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Generate summary statistics by state and scope."""
    summary = df.groupby(["state", "staff_scope"]).agg({
        "lct_value": ["count", "mean", "median", "std"],
    }).round(2)

    summary.columns = ["count", "mean", "median", "std"]
    summary = summary.reset_index()

    return summary


def generate_qa_report(
    df: pd.DataFrame,
    valid_df: pd.DataFrame,
    summary: pd.DataFrame,
    timestamp: str,
    year: str,
    safeguard_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Generate comprehensive QA report for calculation run.

    Returns structured dict suitable for JSON export and database storage.
    """
    # Scope order for validation
    scope_order = [
        "teachers_only", "teachers_elementary", "teachers_secondary",
        "core_sped", "teachers_gened", "instructional_sped",  # SPED segmentation (January 2026)
        "teachers_core", "instructional", "instructional_plus_support", "all"
    ]

    # Data quality metrics
    total_calculations = len(df)
    valid_calculations = len(valid_df)
    invalid_calculations = total_calculations - valid_calculations

    # Districts with QA notes
    qa_notes_df = df[df['level_lct_notes'] != '']
    districts_with_notes = qa_notes_df['district_id'].nunique() if len(qa_notes_df) > 0 else 0

    # Hierarchy validation (each broader scope should have higher LCT)
    hierarchy_checks = {}
    scope_means = {
        row['staff_scope']: row['mean']
        for _, row in summary.iterrows()
    }

    hierarchy_pairs = [
        ("teachers_secondary", "teachers_only", "Secondary < Overall Teachers"),
        ("teachers_only", "teachers_elementary", "Teachers < Elementary"),
        ("teachers_only", "teachers_core", "Teachers < Core"),
        ("teachers_core", "instructional", "Core < Instructional"),
        ("instructional", "instructional_plus_support", "Instructional < Support"),
        ("instructional_plus_support", "all", "Support < All"),
    ]

    for lower, higher, description in hierarchy_pairs:
        lower_val = scope_means.get(lower)
        higher_val = scope_means.get(higher)
        if lower_val is not None and higher_val is not None:
            hierarchy_checks[description] = {
                "passed": lower_val < higher_val,
                "lower": {"scope": lower, "mean": round(lower_val, 2)},
                "higher": {"scope": higher, "mean": round(higher_val, 2)},
            }

    # State coverage
    states_with_data = valid_df['state'].nunique()
    all_states = df['state'].unique().tolist()

    # Outlier detection
    outliers = []
    for scope in scope_order:
        scope_df = valid_df[valid_df['staff_scope'] == scope]
        if len(scope_df) == 0:
            continue

        # Extremely low LCT (< 5 min)
        low_lct = scope_df[scope_df['lct_value'] < 5]
        for _, row in low_lct.head(5).iterrows():
            outliers.append({
                "district_id": row['district_id'],
                "district_name": row['district_name'],
                "scope": scope,
                "issue": f"Very low LCT: {row['lct_value']:.1f} min",
                "severity": "warning",
            })

        # Extremely high LCT (> 200 min)
        high_lct = scope_df[scope_df['lct_value'] > 200]
        for _, row in high_lct.head(5).iterrows():
            outliers.append({
                "district_id": row['district_id'],
                "district_name": row['district_name'],
                "scope": scope,
                "issue": f"Very high LCT: {row['lct_value']:.1f} min",
                "severity": "info",
            })

    # Build report
    report = {
        "metadata": {
            "timestamp": timestamp,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "year": year,
            "version": "3.0",  # Updated for safeguards
        },
        "data_quality": {
            "total_calculations": total_calculations,
            "valid_calculations": valid_calculations,
            "invalid_calculations": invalid_calculations,
            "pass_rate": round(valid_calculations / total_calculations * 100, 2) if total_calculations > 0 else 0,
            "districts_with_qa_notes": districts_with_notes,
        },
        "safeguards": safeguard_counts or {},
        "safeguard_definitions": {
            "ERR_FLAT_STAFF": "All 5 base scopes have identical staff counts (incomplete reporting)",
            "ERR_IMPOSSIBLE_SSR": "Staff-to-student ratio > 0.5 (more than 1 staff per 2 students)",
            "ERR_VOLATILE": "K-12 enrollment < 50 (high statistical volatility)",
            "ERR_RATIO_CEILING": "Teachers = 100% of all staff (incomplete reporting)",
            "WARN_LCT_LOW": "LCT < 5 minutes (very high enrollment relative to staff)",
            "WARN_LCT_HIGH": "LCT > 120 minutes for teachers_only scope",
            "WARN_SPED_RATIO_CAP": "SPED LCT capped at 360 (high teacher-to-student ratio in self-contained SPED)",
        },
        "scope_summary": {
            row['staff_scope']: {
                "districts": int(row['districts']),
                "mean": round(row['mean'], 2),
                "median": round(row['median'], 2),
                "min": round(row['min'], 2),
                "max": round(row['max'], 2),
            }
            for _, row in summary.iterrows()
        },
        "hierarchy_validation": hierarchy_checks,
        "state_coverage": {
            "states_with_data": states_with_data,
            "states": sorted(all_states),
        },
        "outliers": outliers[:20],  # Limit to 20 outliers
        "overall_status": "PASS" if all(
            check.get("passed", True) for check in hierarchy_checks.values()
        ) else "WARNING",
    }

    return report


def save_parquet(df: pd.DataFrame, filepath: Path) -> bool:
    """Save DataFrame to Parquet format if available."""
    if not PARQUET_AVAILABLE:
        return False

    try:
        parquet_path = filepath.with_suffix('.parquet')
        df.to_parquet(parquet_path, compression='snappy', index=False)
        return True
    except Exception as e:
        print(f"  Warning: Could not save Parquet: {e}")
        return False


def clear_lct_calculations(session, run_id: Optional[str] = None) -> int:
    """
    Clear existing LCT calculations.

    Args:
        session: Database session
        run_id: If provided, only clear calculations for this run.
                If None, clear ALL calculations.

    Returns:
        Number of records deleted
    """
    if run_id:
        deleted = session.query(LCTCalculation).filter(
            LCTCalculation.run_id == run_id
        ).delete()
    else:
        deleted = session.query(LCTCalculation).delete()

    return deleted


def write_calculations_to_db(
    session,
    results: List[Dict[str, Any]],
    run_id: str,
    year: str,
) -> int:
    """
    Write LCT calculation results to the database.

    Args:
        session: Database session
        results: List of calculation result dicts from calculate_all_variants
        run_id: The calculation run ID
        year: The target year (or 'blended')

    Returns:
        Number of records inserted
    """
    print(f"\nWriting {len(results):,} calculations to database...")

    # Determine data tier based on minutes source
    def get_data_tier(minutes_source: str) -> int:
        if minutes_source == "bell_schedule":
            return 1
        elif minutes_source.startswith("bell_schedule_"):
            return 2
        else:
            return 3

    inserted = 0
    batch_size = 1000

    for i in range(0, len(results), batch_size):
        batch = results[i:i + batch_size]

        for result in batch:
            calc = LCTCalculation(
                district_id=result['district_id'],
                year=year if year != 'blended' else result.get('staff_year', '2023-24'),
                grade_level=None,  # Scope-based calculations don't have traditional grade levels
                staff_scope=result['staff_scope'],
                run_id=run_id,
                instructional_minutes=result['instructional_minutes'],
                instructional_minutes_source=result['instructional_minutes_source'],
                instructional_minutes_year=result['instructional_minutes_year'],
                enrollment=result['enrollment'],
                enrollment_type=result['enrollment_type'],
                instructional_staff=result['staff_count'],
                staff_source=result['staff_source'],
                staff_year=result['staff_year'],
                lct_value=result['lct_value'],
                data_tier=get_data_tier(result['instructional_minutes_source']),
                notes=result.get('level_lct_notes', ''),
            )
            session.add(calc)
            inserted += 1

        # Flush batch
        session.flush()
        if (i + batch_size) % 5000 == 0:
            print(f"  Inserted {i + batch_size:,} / {len(results):,}")

    print(f"  Inserted {inserted:,} LCT calculations")
    return inserted


def export_lct_from_db(
    session,
    run_id: str,
    output_dir: Path,
    timestamp: str,
    year_str: str = "",
) -> tuple[pd.DataFrame, List[str]]:
    """
    Export LCT calculations from database to CSV files.

    Args:
        session: Database session
        run_id: The calculation run ID to export
        output_dir: Directory for output files
        timestamp: Timestamp string for filenames
        year_str: Year prefix for filenames (empty for blended mode)

    Returns:
        Tuple of (DataFrame with all calculations, list of output file paths)
    """
    print(f"\nExporting LCT calculations from database (run_id: {run_id})...")

    # Query all calculations for this run, joining with districts for names
    calculations = session.query(
        LCTCalculation,
        District.name.label('district_name'),
        District.state
    ).join(
        District,
        LCTCalculation.district_id == District.nces_id
    ).filter(
        LCTCalculation.run_id == run_id
    ).all()

    print(f"  Found {len(calculations):,} calculations in database")

    # Convert to DataFrame
    records = []
    for calc, district_name, state in calculations:
        records.append({
            "district_id": calc.district_id,
            "district_name": district_name,
            "state": state,
            "staff_scope": calc.staff_scope,
            "lct_value": float(calc.lct_value),
            "instructional_minutes": calc.instructional_minutes,
            "instructional_minutes_source": calc.instructional_minutes_source,
            "instructional_minutes_year": calc.instructional_minutes_year,
            "staff_count": float(calc.instructional_staff),
            "staff_source": calc.staff_source,
            "staff_year": calc.staff_year,
            "enrollment": calc.enrollment,
            "enrollment_type": calc.enrollment_type,
            "level_lct_notes": calc.notes or "",
        })

    df = pd.DataFrame(records)
    output_files = []

    if len(df) == 0:
        print("  No data to export")
        return df, output_files

    # Save detailed results
    detail_file = output_dir / f"lct_all_variants_{year_str}{timestamp}.csv"
    df.to_csv(detail_file, index=False)
    print(f"  Saved detailed results to {detail_file}")
    output_files.append(str(detail_file))

    # Filter for valid LCT (0 < LCT <= 360)
    valid_df = df[(df['lct_value'] > 0) & (df['lct_value'] <= 360)]
    valid_file = output_dir / f"lct_all_variants_{year_str}valid_{timestamp}.csv"
    valid_df.to_csv(valid_file, index=False)
    print(f"  Saved valid results to {valid_file}")
    output_files.append(str(valid_file))

    return df, output_files


def main():
    parser = argparse.ArgumentParser(
        description="Calculate LCT variants",
        epilog="""
Examples:
  # Default: Blended mode - uses most recent data within REQ-026 3-year window
  python calculate_lct_variants.py

  # Target year mode: Enrollment anchored to target year, staff/bell blended
  python calculate_lct_variants.py --target-year 2023-24
        """
    )
    parser.add_argument(
        "--target-year",
        default=None,
        help="Anchor enrollment to specific year (TARGET_YEAR mode). Without this flag, uses most recent data (BLENDED mode)."
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    parser.add_argument("--parquet", action="store_true", help="Also save Parquet files")
    parser.add_argument("--incremental", action="store_true", help="Only recalculate changed districts")
    parser.add_argument("--no-track", action="store_true", help="Don't track run in database")
    args = parser.parse_args()

    # Determine calculation mode
    if args.target_year:
        calculation_mode = CalculationMode.TARGET_YEAR
        mode_display = f"TARGET_YEAR (enrollment anchored to {args.target_year})"
    else:
        calculation_mode = CalculationMode.BLENDED
        mode_display = "BLENDED (most recent data within REQ-026 window)"

    # Default output directory
    output_dir = args.output_dir or project_root / "data" / "enriched" / "lct-calculations"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("LCT VARIANT CALCULATIONS")
    print("=" * 60)
    print(f"Mode: {mode_display}")
    print(f"Output: {output_dir}")
    print()
    print("SCOPE DEFINITIONS (December 2025):")
    print("-" * 40)
    print("All scopes use K-12 enrollment (exclude Pre-K)")
    print("All scopes exclude Pre-K teachers")
    print()
    print("BASE SCOPES:")
    print("  teachers_only:    K-12 teachers (elem+sec+kinder, NO ungraded)")
    print("  teachers_core:    K-12 teachers + ungraded")
    print("  instructional:    core + coordinators + paras")
    print("  instructional_plus_support: above + counselors + psych + support")
    print("  all:              All staff except Pre-K teachers")
    print()
    print("TEACHER-LEVEL VARIANTS:")
    print("  teachers_elementary: elem+kinder teachers / K-5 enrollment")
    print("  teachers_secondary:  secondary teachers / 6-12 enrollment")
    print()
    print("SPED SEGMENTATION (January 2026):")
    print("  core_sped:          SPED teachers / SPED enrollment (for audit)")
    print("  teachers_gened:     GenEd teachers / GenEd enrollment")
    print("  instructional_sped: (SPED teachers+paras) / SPED enrollment")
    print()

    # Generate timestamp for all output files
    timestamp = get_utc_timestamp()
    # File naming: include year only for TARGET_YEAR mode
    if args.target_year:
        year_str = args.target_year.replace('-', '_') + "_"
    else:
        year_str = ""  # No year in filename for BLENDED mode
    print(f"Timestamp: {timestamp}")
    print()

    with session_scope() as session:
        # Start calculation run tracking (do this early to get run_id)
        run = None
        if not args.no_track:
            try:
                run = CalculationRun.start_run(
                    session,
                    calculation_mode=calculation_mode,
                    target_year=args.target_year,
                    run_type="full",
                )
                session.flush()
                print(f"Started calculation run: {run.run_id}")
            except Exception as e:
                print(f"Warning: Could not start run tracking: {e}")
                run = None

        run_id = run.run_id if run else timestamp

        # Calculate all variants
        df, data_year_min, data_year_max = calculate_all_variants(
            session,
            calculation_mode=calculation_mode,
            target_year=args.target_year
        )

        if len(df) == 0:
            print("No LCT values calculated. Check data availability.")
            if run:
                run.fail("No LCT values calculated")
                session.commit()
            sys.exit(1)

        # Apply data safeguards (January 2026)
        df, safeguard_counts = apply_data_safeguards(df)

        # === DB-FIRST APPROACH (January 2026) ===
        # Write calculations to database first, then export CSVs from DB

        # Convert DataFrame to list of dicts for database insertion
        results_list = df.to_dict('records')

        # Write to database
        year_for_db = args.target_year if args.target_year else 'blended'
        inserted_count = write_calculations_to_db(
            session, results_list, run_id, year_for_db
        )

        # Export CSVs from database
        df_from_db, output_files = export_lct_from_db(
            session, run_id, output_dir, timestamp, year_str
        )

        # Use the database export as our source of truth
        df = df_from_db

        # Filter for valid LCT (0 < LCT <= 360 for all scopes)
        # SPED scopes that would exceed 360 are capped with WARN_SPED_RATIO_CAP flag
        valid_df = df[(df['lct_value'] > 0) & (df['lct_value'] <= 360)]
        valid_file = output_dir / f"lct_all_variants_{year_str}valid_{timestamp}.csv"
        # Note: valid_file is already created by export_lct_from_db

        # Generate and save summary statistics
        summary = generate_summary_statistics(valid_df)
        summary_file = output_dir / f"lct_variants_summary_{year_str}{timestamp}.csv"
        summary.to_csv(summary_file, index=False)
        print(f"Saved summary to {summary_file}")

        # Generate state-level summary
        state_summary = generate_state_summary(valid_df)
        state_file = output_dir / f"lct_variants_by_state_{year_str}{timestamp}.csv"
        state_summary.to_csv(state_file, index=False)
        print(f"Saved state summary to {state_file}")

        # Print summary report
        print("\n" + "=" * 60)
        print("LCT VARIANTS SUMMARY (Valid: 0 < LCT <= 360)")
        print("=" * 60)
        print()

        # Order scopes for display
        scope_order = ["teachers_only", "teachers_elementary", "teachers_secondary",
                       "core_sped", "teachers_gened", "instructional_sped",
                       "teachers_core", "instructional", "instructional_plus_support", "all"]

        for scope in scope_order:
            row = summary[summary['staff_scope'] == scope]
            if len(row) == 0:
                continue
            row = row.iloc[0]
            print(f"{scope.upper()}:")
            print(f"  Districts: {int(row['districts']):,}")
            print(f"  Mean LCT:  {row['mean']:.1f} minutes")
            print(f"  Median:   {row['median']:.1f} minutes")
            print(f"  Std Dev:   {row['std']:.1f} minutes")
            print(f"  Range:    {row['min']:.1f} - {row['max']:.1f} minutes")
            print()

        # Generate comparison text report
        report_file = output_dir / f"lct_variants_report_{year_str}{timestamp}.txt"
        utc_now = datetime.now(timezone.utc)
        with open(report_file, "w") as f:
            f.write("=" * 60 + "\n")
            f.write("LCT VARIANT COMPARISON REPORT\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Generated: {utc_now.strftime('%Y-%m-%dT%H:%M:%SZ')} (UTC)\n")
            f.write(f"Mode: {mode_display}\n")
            if data_year_min and data_year_max:
                f.write(f"Data Range: {data_year_min} to {data_year_max}\n")
            if args.target_year:
                f.write(f"Target Year: {args.target_year}\n")
            f.write("\n")

            f.write("KEY METHODOLOGY DECISIONS (December 2025):\n")
            f.write("-" * 40 + "\n")
            f.write("- ALL scopes use K-12 enrollment (Pre-K excluded)\n")
            f.write("- ALL scopes exclude Pre-K teachers\n")
            f.write("- Ungraded teachers EXCLUDED from teachers_only variants\n")
            f.write("- Ungraded teachers INCLUDED in other scopes\n\n")

            f.write("SCOPE DEFINITIONS:\n")
            f.write("-" * 40 + "\n")
            f.write("teachers_only:           K-12 teachers (elem+sec+kinder, NO ungraded)\n")
            f.write("teachers_elementary:     Elementary+Kinder teachers / K-5 enrollment\n")
            f.write("teachers_secondary:      Secondary teachers / 6-12 enrollment\n")
            f.write("core_sped:               SPED teachers / SPED enrollment (for audit)\n")
            f.write("teachers_gened:          GenEd teachers / GenEd enrollment\n")
            f.write("instructional_sped:      (SPED teachers+paras) / SPED enrollment\n")
            f.write("teachers_core:           K-12 teachers + ungraded\n")
            f.write("instructional:           core + coordinators + paraprofessionals\n")
            f.write("instructional_plus_support: above + counselors + psychologists + support\n")
            f.write("all:                     All staff except Pre-K teachers\n\n")

            f.write("SUMMARY STATISTICS:\n")
            f.write("-" * 40 + "\n")

            for scope in scope_order:
                row = summary[summary['staff_scope'] == scope]
                if len(row) == 0:
                    continue
                row = row.iloc[0]
                f.write(f"\n{scope.upper()}:\n")
                f.write(f"  Districts with valid LCT: {int(row['districts']):,}\n")
                f.write(f"  Mean LCT:   {row['mean']:.1f} minutes\n")
                f.write(f"  Median:    {row['median']:.1f} minutes\n")
                f.write(f"  Std Dev:   {row['std']:.1f} minutes\n")
                f.write(f"  Range:     {row['min']:.1f} - {row['max']:.1f} minutes\n")

            f.write("\n" + "=" * 60 + "\n")
            f.write("INTERPRETATION NOTES:\n")
            f.write("=" * 60 + "\n\n")
            f.write("- Higher LCT values indicate more theoretical one-on-one time\n")
            f.write("- 'teachers_only' is the most conservative K-12 measure\n")
            f.write("- 'teachers_elementary' vs 'teachers_secondary' shows level differences\n")
            f.write("- 'instructional' is recommended for policy discussions\n")
            f.write("- 'all' shows maximum resource investment\n")
            f.write("- Compare across scopes to understand staffing mix impact\n")

        print(f"Saved report to {report_file}")

        # Summary of QA issues
        qa_df = df[df['level_lct_notes'] != '']
        if len(qa_df) > 0:
            print(f"\nDistricts with level LCT QA notes: {qa_df['district_id'].nunique()}")

        # Add summary files to output_files (detail and valid already added by export_lct_from_db)
        output_files.extend([
            str(summary_file),
            str(state_file),
            str(report_file),
        ])

        # Generate and save QA report (JSON)
        # Pass data range info instead of single year
        data_range_str = f"{data_year_min} to {data_year_max}" if data_year_min and data_year_max else "unknown"
        qa_report = generate_qa_report(df, valid_df, summary, timestamp, data_range_str, safeguard_counts)
        qa_report['calculation_mode'] = calculation_mode.value
        qa_report['target_year'] = args.target_year
        qa_report['data_year_min'] = data_year_min
        qa_report['data_year_max'] = data_year_max
        qa_file = output_dir / f"lct_qa_report_{year_str}{timestamp}.json"
        with open(qa_file, 'w') as f:
            json.dump(qa_report, f, indent=2)
        print(f"Saved QA report to {qa_file}")
        output_files.append(str(qa_file))

        # Print QA summary
        print("\n" + "=" * 60)
        print("QA DASHBOARD")
        print("=" * 60)
        print(f"Status: {qa_report['overall_status']}")
        print(f"Pass Rate: {qa_report['data_quality']['pass_rate']}%")
        print(f"Hierarchy Checks:")
        for check, result in qa_report['hierarchy_validation'].items():
            status = "✓" if result['passed'] else "✗"
            print(f"  {status} {check}")
        if qa_report['outliers']:
            print(f"Outliers Detected: {len(qa_report['outliers'])}")

        # Print safeguard summary (January 2026)
        print("\nData Safeguards (flagged records):")
        safeguards = qa_report.get('safeguards', {})
        for flag, count in sorted(safeguards.items()):
            if count > 0:
                flag_type = "ERR" if flag.startswith("ERR") else "WARN"
                print(f"  [{flag_type}] {flag}: {count:,}")
        total_safeguard_flags = sum(safeguards.values())
        if total_safeguard_flags == 0:
            print("  No safeguard flags triggered")

        # Parquet export (optional)
        if args.parquet:
            print("\nSaving Parquet files...")
            if PARQUET_AVAILABLE:
                # Get file paths from output_files list
                detail_file_path = Path(output_files[0]) if output_files else None
                valid_file_path = Path(output_files[1]) if len(output_files) > 1 else None
                if detail_file_path and save_parquet(df, detail_file_path):
                    parquet_file = detail_file_path.with_suffix('.parquet')
                    print(f"  Saved {parquet_file}")
                    output_files.append(str(parquet_file))
                if valid_file_path and save_parquet(valid_df, valid_file_path):
                    parquet_file = valid_file_path.with_suffix('.parquet')
                    print(f"  Saved {parquet_file}")
                    output_files.append(str(parquet_file))
            else:
                print("  Parquet not available. Install pyarrow: pip install pyarrow")

        # Complete calculation run tracking
        if run:
            try:
                run.complete(
                    districts_processed=df['district_id'].nunique(),
                    calculations_created=len(df),
                    output_files=output_files,
                    qa_summary=qa_report,
                    data_year_min=data_year_min,
                    data_year_max=data_year_max,
                )
                session.commit()
                print(f"\nCalculation run completed: {run.run_id}")
                print(f"  Calculations in database: {inserted_count:,}")
            except Exception as e:
                print(f"\nWarning: Could not complete run tracking: {e}")

        print("\n" + "=" * 60)
        print("CALCULATION COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
