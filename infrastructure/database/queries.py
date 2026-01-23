# infrastructure/database/queries.py
"""
Database query utilities for Learning Connection Time project.

Provides high-level functions for common database operations,
replacing file-based workflows with efficient database queries.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from .models import BellSchedule, DataLineage, District, LCTCalculation, StateRequirement


# =============================================================================
# DISTRICT QUERIES
# =============================================================================


def get_district_by_id(session: Session, nces_id: str) -> Optional[District]:
    """Get a single district by NCES ID."""
    # Try with and without leading zeros
    normalized_id = nces_id.lstrip("0") or nces_id
    district = session.query(District).filter(
        or_(District.nces_id == nces_id, District.nces_id == normalized_id)
    ).first()
    return district


def get_districts_by_state(session: Session, state: str) -> List[District]:
    """Get all districts in a state, ordered by enrollment."""
    return (
        session.query(District)
        .filter(District.state == state.upper())
        .order_by(desc(District.enrollment))
        .all()
    )


def get_top_districts(
    session: Session, limit: int = 100, state: Optional[str] = None
) -> List[District]:
    """Get top districts by enrollment."""
    query = session.query(District).filter(District.enrollment.isnot(None))
    if state:
        query = query.filter(District.state == state.upper())
    return query.order_by(desc(District.enrollment)).limit(limit).all()


def search_districts(
    session: Session, name_pattern: str, state: Optional[str] = None
) -> List[District]:
    """Search districts by name pattern (case-insensitive)."""
    query = session.query(District).filter(
        District.name.ilike(f"%{name_pattern}%")
    )
    if state:
        query = query.filter(District.state == state.upper())
    return query.order_by(desc(District.enrollment)).limit(50).all()


def get_unenriched_districts(
    session: Session,
    limit: int = 100,
    min_enrollment: int = 1000,
    state: Optional[str] = None,
) -> List[District]:
    """Get districts without bell schedules, ordered by enrollment."""
    # Subquery for districts with schedules
    enriched_ids = (
        select(BellSchedule.district_id)
        .distinct()
        .scalar_subquery()
    )

    query = (
        session.query(District)
        .filter(District.nces_id.not_in(enriched_ids))
        .filter(District.enrollment >= min_enrollment)
    )

    if state:
        query = query.filter(District.state == state.upper())

    return query.order_by(desc(District.enrollment)).limit(limit).all()


# =============================================================================
# BELL SCHEDULE QUERIES
# =============================================================================


def get_bell_schedule(
    session: Session,
    district_id: str,
    year: str = "2024-25",
    grade_level: Optional[str] = None,
):
    """
    Get bell schedule(s) for a district.

    Returns:
        - If grade_level specified: Single BellSchedule or None
        - If grade_level not specified: List of BellSchedule objects
    """
    normalized_id = district_id.lstrip("0") or district_id

    query = session.query(BellSchedule).filter(
        or_(
            BellSchedule.district_id == district_id,
            BellSchedule.district_id == normalized_id,
        ),
        BellSchedule.year == year,
    )

    if grade_level:
        query = query.filter(BellSchedule.grade_level == grade_level)
        return query.first()  # Return single object or None

    return query.all()  # Return list


def get_enriched_districts(
    session: Session, year: str = "2024-25"
) -> List[Tuple[District, int]]:
    """Get all districts with bell schedules and count of grade levels."""
    results = (
        session.query(District, func.count(BellSchedule.id))
        .join(BellSchedule, District.nces_id == BellSchedule.district_id)
        .filter(BellSchedule.year == year)
        .group_by(District.nces_id)
        .order_by(desc(District.enrollment))
        .all()
    )
    return results


def get_enrichment_by_state(session: Session, year: str = "2024-25") -> List[Dict]:
    """Get enrichment statistics by state."""
    results = (
        session.query(
            District.state,
            func.count(func.distinct(District.nces_id)).label("total_districts"),
            func.count(func.distinct(BellSchedule.district_id)).label("enriched_districts"),
        )
        .outerjoin(
            BellSchedule,
            and_(
                District.nces_id == BellSchedule.district_id,
                BellSchedule.year == year,
            ),
        )
        .group_by(District.state)
        .order_by(District.state)
        .all()
    )

    return [
        {
            "state": r.state,
            "total_districts": r.total_districts,
            "enriched_districts": r.enriched_districts or 0,
            "enrichment_pct": round(
                100.0 * (r.enriched_districts or 0) / r.total_districts, 2
            )
            if r.total_districts > 0
            else 0,
        }
        for r in results
    ]


def add_bell_schedule(
    session: Session,
    district_id: str,
    year: str,
    grade_level: str,
    instructional_minutes: int,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    lunch_duration: Optional[int] = None,
    passing_periods: Optional[int] = None,
    recess_duration: Optional[int] = None,
    schools_sampled: Optional[List[str]] = None,
    source_urls: Optional[List[str]] = None,
    confidence: str = "high",
    method: str = "human_provided",
    source_description: Optional[str] = None,
    notes: Optional[str] = None,
    created_by: str = "claude",
) -> BellSchedule:
    """
    Add or update a bell schedule record.

    Returns the created/updated BellSchedule instance.
    """
    # Normalize district ID
    normalized_id = district_id.lstrip("0") or district_id

    # Verify district exists
    district = get_district_by_id(session, normalized_id)
    if not district:
        raise ValueError(f"District {district_id} not found in database")

    # Check for existing record
    existing = (
        session.query(BellSchedule)
        .filter(
            BellSchedule.district_id == district.nces_id,
            BellSchedule.year == year,
            BellSchedule.grade_level == grade_level,
        )
        .first()
    )

    if existing:
        # Update existing record
        existing.instructional_minutes = instructional_minutes
        existing.start_time = start_time
        existing.end_time = end_time
        existing.lunch_duration = lunch_duration
        existing.passing_periods = passing_periods
        existing.recess_duration = recess_duration
        existing.schools_sampled = schools_sampled or []
        existing.source_urls = source_urls or []
        existing.confidence = confidence
        existing.method = method
        existing.source_description = source_description
        existing.notes = notes
        existing.updated_at = datetime.utcnow()
        schedule = existing
        operation = "update"
    else:
        # Create new record
        schedule = BellSchedule(
            district_id=district.nces_id,
            year=year,
            grade_level=grade_level,
            instructional_minutes=instructional_minutes,
            start_time=start_time,
            end_time=end_time,
            lunch_duration=lunch_duration,
            passing_periods=passing_periods,
            recess_duration=recess_duration,
            schools_sampled=schools_sampled or [],
            source_urls=source_urls or [],
            confidence=confidence,
            method=method,
            source_description=source_description,
            notes=notes,
        )
        session.add(schedule)
        operation = "create"

    # Log lineage
    DataLineage.log(
        session,
        entity_type="bell_schedule",
        entity_id=f"{district.nces_id}/{year}/{grade_level}",
        operation=operation,
        details={
            "instructional_minutes": instructional_minutes,
            "method": method,
            "confidence": confidence,
        },
        created_by=created_by,
    )

    session.flush()
    return schedule


def add_district_bell_schedules(
    session: Session,
    district_id: str,
    year: str,
    schedules: Dict[str, Dict],
    method: str = "human_provided",
    created_by: str = "claude",
) -> List[BellSchedule]:
    """
    Add bell schedules for all grade levels of a district.

    Args:
        session: Database session
        district_id: NCES district ID
        year: School year (e.g., "2024-25")
        schedules: Dict with keys 'elementary', 'middle', 'high' containing schedule data
        method: Collection method
        created_by: Attribution

    Returns:
        List of created/updated BellSchedule instances
    """
    results = []

    for grade_level in ["elementary", "middle", "high"]:
        if grade_level not in schedules or schedules[grade_level] is None:
            continue

        data = schedules[grade_level]
        if not data.get("instructional_minutes"):
            continue

        schedule = add_bell_schedule(
            session=session,
            district_id=district_id,
            year=year,
            grade_level=grade_level,
            instructional_minutes=data["instructional_minutes"],
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            lunch_duration=data.get("lunch_duration"),
            passing_periods=data.get("passing_periods"),
            recess_duration=data.get("recess_duration"),
            schools_sampled=data.get("schools_sampled"),
            source_urls=data.get("source_urls"),
            confidence=data.get("confidence", "high"),
            method=method,
            source_description=data.get("source"),
            notes=data.get("notes"),
            created_by=created_by,
        )
        results.append(schedule)

    return results


# =============================================================================
# STATE REQUIREMENTS QUERIES
# =============================================================================


def get_state_requirement(session: Session, state: str) -> Optional[StateRequirement]:
    """Get state requirement by state code."""
    return (
        session.query(StateRequirement)
        .filter(StateRequirement.state == state.upper())
        .first()
    )


def get_instructional_minutes(
    session: Session, state: str, grade_level: str
) -> Optional[int]:
    """Get statutory instructional minutes for a state and grade level."""
    req = get_state_requirement(session, state)
    if req:
        return req.get_minutes(grade_level)
    return None


# =============================================================================
# LCT CALCULATION QUERIES
# =============================================================================


def calculate_and_store_lct(
    session: Session,
    district_id: str,
    year: str = "2024-25",
    use_statutory_fallback: bool = True,
) -> List[LCTCalculation]:
    """
    Calculate LCT for a district and store results.

    Uses actual bell schedule data where available,
    falls back to state statutory requirements if enabled.
    """
    district = get_district_by_id(session, district_id)
    if not district:
        raise ValueError(f"District {district_id} not found")

    if not district.enrollment or district.enrollment <= 0:
        raise ValueError(f"District {district_id} has no valid enrollment data")

    if not district.instructional_staff or district.instructional_staff <= 0:
        raise ValueError(f"District {district_id} has no valid staff data")

    results = []
    bell_schedules = get_bell_schedule(session, district_id, year)

    for grade_level in ["elementary", "middle", "high"]:
        # Find matching bell schedule
        schedule = next(
            (s for s in bell_schedules if s.grade_level == grade_level), None
        )

        if schedule:
            # Use actual bell schedule data
            instructional_minutes = schedule.instructional_minutes
            data_tier = 1 if schedule.method == "human_provided" else 2
            bell_schedule_id = schedule.id
        elif use_statutory_fallback:
            # Fall back to state requirements
            instructional_minutes = get_instructional_minutes(
                session, district.state, grade_level
            )
            if not instructional_minutes:
                continue
            data_tier = 3
            bell_schedule_id = None
        else:
            continue

        # Calculate LCT
        lct_value = LCTCalculation.calculate_lct(
            instructional_minutes=instructional_minutes,
            enrollment=district.enrollment,
            instructional_staff=float(district.instructional_staff),
        )

        # Check for existing calculation
        existing = (
            session.query(LCTCalculation)
            .filter(
                LCTCalculation.district_id == district.nces_id,
                LCTCalculation.year == year,
                LCTCalculation.grade_level == grade_level,
            )
            .first()
        )

        if existing:
            existing.instructional_minutes = instructional_minutes
            existing.enrollment = district.enrollment
            existing.instructional_staff = district.instructional_staff
            existing.lct_value = lct_value
            existing.data_tier = data_tier
            existing.bell_schedule_id = bell_schedule_id
            existing.calculated_at = datetime.utcnow()
            calc = existing
        else:
            calc = LCTCalculation(
                district_id=district.nces_id,
                year=year,
                grade_level=grade_level,
                instructional_minutes=instructional_minutes,
                enrollment=district.enrollment,
                instructional_staff=district.instructional_staff,
                lct_value=lct_value,
                data_tier=data_tier,
                bell_schedule_id=bell_schedule_id,
            )
            session.add(calc)

        results.append(calc)

    session.flush()
    return results


# =============================================================================
# EXPORT UTILITIES
# =============================================================================


def export_bell_schedules_to_json(
    session: Session, year: str = "2024-25", pretty: bool = True
) -> str:
    """
    Export all bell schedules to JSON format.

    Returns JSON string matching the original consolidated file format.
    """
    schedules = (
        session.query(BellSchedule)
        .filter(BellSchedule.year == year)
        .order_by(BellSchedule.district_id)
        .all()
    )

    # Group by district
    by_district: Dict[str, Dict] = {}

    for schedule in schedules:
        district = session.query(District).filter(
            District.nces_id == schedule.district_id
        ).first()

        if schedule.district_id not in by_district:
            by_district[schedule.district_id] = {
                "district_id": schedule.district_id,
                "district_name": district.name if district else "Unknown",
                "state": district.state if district else "Unknown",
                "year": year,
            }

        by_district[schedule.district_id][schedule.grade_level] = {
            "instructional_minutes": schedule.instructional_minutes,
            "start_time": schedule.start_time,
            "end_time": schedule.end_time,
            "lunch_duration": schedule.lunch_duration,
            "passing_periods": schedule.passing_periods,
            "recess_duration": schedule.recess_duration,
            "schools_sampled": schedule.schools_sampled,
            "source_urls": schedule.source_urls,
            "confidence": schedule.confidence,
            "method": schedule.method,
            "source": schedule.source_description,
            "notes": schedule.notes,
        }

    if pretty:
        return json.dumps(by_district, indent=2)
    return json.dumps(by_district)


def export_enriched_districts_csv(
    session: Session, year: str = "2024-25"
) -> str:
    """Export enriched districts summary as CSV."""
    results = get_enriched_districts(session, year)

    lines = [
        "district_id,district_name,state,enrollment,instructional_staff,grade_levels_enriched"
    ]

    for district, grade_count in results:
        lines.append(
            f"{district.nces_id},"
            f'"{district.name}",'
            f"{district.state},"
            f"{district.enrollment or ''},"
            f"{district.instructional_staff or ''},"
            f"{grade_count}"
        )

    return "\n".join(lines)


# =============================================================================
# LCT VARIANT QUERIES
# =============================================================================


def get_lct_summary_by_scope(
    session: Session, scope: str = "teachers_only", year: str = "2023-24"
) -> Dict:
    """Get LCT summary statistics for a specific scope."""
    from sqlalchemy import func as sqlfunc
    from .models import StaffCountsEffective, EnrollmentByGrade

    # Map scope to column
    scope_map = {
        "teachers_only": StaffCountsEffective.scope_teachers_only,
        "teachers_core": StaffCountsEffective.scope_teachers_core,
        "instructional": StaffCountsEffective.scope_instructional,
        "instructional_plus_support": StaffCountsEffective.scope_instructional_plus_support,
        "all": StaffCountsEffective.scope_all,
    }

    staff_col = scope_map.get(scope)
    if not staff_col:
        raise ValueError(f"Unknown scope: {scope}")

    # Get count of districts with this scope
    count = (
        session.query(sqlfunc.count(StaffCountsEffective.district_id))
        .filter(staff_col.isnot(None))
        .filter(staff_col > 0)
        .scalar()
    )

    return {
        "scope": scope,
        "year": year,
        "districts_with_data": count,
    }


def get_districts_needing_calculation(
    session: Session,
    last_run_id: Optional[str] = None,
    year: str = "2023-24",
) -> List[str]:
    """
    Get districts that need LCT recalculation.

    If last_run_id is provided, returns only districts modified since that run.
    """
    from .models import StaffCountsEffective, EnrollmentByGrade, CalculationRun

    # Get districts with staff and enrollment data
    query = (
        session.query(StaffCountsEffective.district_id)
        .join(
            EnrollmentByGrade,
            StaffCountsEffective.district_id == EnrollmentByGrade.district_id,
        )
        .filter(EnrollmentByGrade.source_year == year)
        .filter(StaffCountsEffective.scope_teachers_only.isnot(None))
    )

    if last_run_id:
        # Get the last run timestamp
        last_run = (
            session.query(CalculationRun)
            .filter(CalculationRun.run_id == last_run_id)
            .first()
        )
        if last_run:
            # Filter to districts modified after last run
            query = query.filter(
                or_(
                    StaffCountsEffective.last_resolved_at > last_run.completed_at,
                    EnrollmentByGrade.updated_at > last_run.completed_at,
                )
            )

    return [r[0] for r in query.all()]


def get_state_campaign_progress(session: Session, year: str = "2024-25") -> List[Dict]:
    """
    Get state-by-state enrichment progress for campaign tracking.

    Returns states sorted by enrichment completion, with target of 3 per state.
    """
    from sqlalchemy import case, func as sqlfunc

    results = (
        session.query(
            District.state,
            sqlfunc.count(sqlfunc.distinct(District.nces_id)).label("total_districts"),
            sqlfunc.count(sqlfunc.distinct(BellSchedule.district_id)).label("enriched"),
            sqlfunc.sum(District.enrollment).label("total_enrollment"),
        )
        .outerjoin(
            BellSchedule,
            and_(
                District.nces_id == BellSchedule.district_id,
                BellSchedule.year == year,
            ),
        )
        .group_by(District.state)
        .order_by(sqlfunc.count(sqlfunc.distinct(BellSchedule.district_id)).desc())
        .all()
    )

    return [
        {
            "state": r.state,
            "total_districts": r.total_districts,
            "enriched": r.enriched or 0,
            "target": 3,
            "complete": (r.enriched or 0) >= 3,
            "total_enrollment": r.total_enrollment or 0,
        }
        for r in results
    ]


def get_next_enrichment_candidates(
    session: Session,
    state: str,
    year: str = "2024-25",
    limit: int = 9,
) -> List[District]:
    """
    Get next candidates for enrichment in a state.

    Returns top districts by enrollment that don't have bell schedules.
    """
    # Subquery for districts with schedules
    enriched_ids = (
        select(BellSchedule.district_id)
        .filter(BellSchedule.year == year)
        .distinct()
        .scalar_subquery()
    )

    return (
        session.query(District)
        .filter(District.state == state.upper())
        .filter(District.nces_id.not_in(enriched_ids))
        .filter(District.enrollment.isnot(None))
        .order_by(desc(District.enrollment))
        .limit(limit)
        .all()
    )


# =============================================================================
# STATISTICS & REPORTING
# =============================================================================


def get_enrichment_summary(session: Session, year: str = "2024-25") -> Dict:
    """Get overall enrichment statistics."""
    total_districts = session.query(func.count(District.nces_id)).scalar()

    enriched_count = (
        session.query(func.count(func.distinct(BellSchedule.district_id)))
        .filter(BellSchedule.year == year)
        .scalar()
    )

    schedule_count = (
        session.query(func.count(BellSchedule.id))
        .filter(BellSchedule.year == year)
        .scalar()
    )

    state_count = (
        session.query(func.count(func.distinct(District.state)))
        .join(BellSchedule, District.nces_id == BellSchedule.district_id)
        .filter(BellSchedule.year == year)
        .scalar()
    )

    by_method = (
        session.query(BellSchedule.method, func.count(BellSchedule.id))
        .filter(BellSchedule.year == year)
        .group_by(BellSchedule.method)
        .all()
    )

    return {
        "year": year,
        "total_districts": total_districts,
        "enriched_districts": enriched_count,
        "enrichment_rate": round(100.0 * enriched_count / total_districts, 4)
        if total_districts > 0
        else 0,
        "schedule_records": schedule_count,
        "states_represented": state_count,
        "by_method": {m: c for m, c in by_method},
    }


def print_enrichment_report(session: Session, year: str = "2024-25"):
    """Print a formatted enrichment report."""
    summary = get_enrichment_summary(session, year)

    print("=" * 60)
    print(f"Bell Schedule Enrichment Report - {year}")
    print("=" * 60)
    print(f"Total U.S. districts:     {summary['total_districts']:,}")
    print(f"Enriched districts:       {summary['enriched_districts']:,}")
    print(f"Enrichment rate:          {summary['enrichment_rate']:.2f}%")
    print(f"Bell schedule records:    {summary['schedule_records']:,}")
    print(f"States represented:       {summary['states_represented']}")
    print()
    print("By Collection Method:")
    for method, count in sorted(summary["by_method"].items()):
        print(f"  {method}: {count}")
    print("=" * 60)


# =============================================================================
# CAMPAIGN TARGETING QUERIES
# =============================================================================


def get_target_districts(
    session: Session,
    state: str,
    size_range: Tuple[int, int],
    limit: int = 15,
    exclude_large: bool = True,
    year: str = "2024-25",
) -> List[District]:
    """
    Get unenriched districts in a specific size range for campaign targeting.

    This function supports size-stratified enrichment campaigns by filtering
    districts to specific enrollment ranges, ensuring representation across
    district sizes (not just the largest districts).

    Args:
        session: Database session
        state: Two-letter state code (e.g., 'MI', 'CA')
        size_range: Tuple of (min_enrollment, max_enrollment)
        limit: Maximum number of districts to return (default 15)
        exclude_large: If True, cap enrollment at 50,000 regardless of size_range
        year: School year for bell schedule check (default "2024-25")

    Returns:
        List of District objects ordered by enrollment (descending)

    Example:
        >>> # Get medium-sized districts (1K-50K) in Michigan
        >>> districts = get_target_districts(session, 'MI', (1000, 50000), limit=4)
        >>> for d in districts:
        ...     print(f"{d.name}: {d.enrollment:,} students")
    """
    from sqlalchemy import text, exists

    min_enroll, max_enroll = size_range

    # Cap at 50K if exclude_large is True
    if exclude_large and max_enroll > 50000:
        max_enroll = 50000

    # Subquery for districts with existing bell schedules
    enriched_ids = (
        select(BellSchedule.district_id)
        .filter(BellSchedule.year == year)
        .distinct()
        .scalar_subquery()
    )

    # Build query with all filters
    query = (
        session.query(District)
        .filter(District.state == state.upper())
        .filter(District.enrollment.isnot(None))
        .filter(District.enrollment >= min_enroll)
        .filter(District.enrollment <= max_enroll)
        .filter(District.nces_id.not_in(enriched_ids))
    )

    # Exclude districts flagged to skip from previous failures
    # Using raw SQL to call the database function
    skip_subquery = text(
        "NOT EXISTS (SELECT 1 FROM enrichment_attempts ea "
        "WHERE ea.district_id = districts.nces_id AND ea.skip_future_attempts = TRUE)"
    )
    query = query.filter(skip_subquery)

    # Order by enrollment descending and limit
    return query.order_by(desc(District.enrollment)).limit(limit).all()


def get_campaign_targets_by_state(
    session: Session,
    size_range: Tuple[int, int],
    districts_per_state: int = 4,
    exclude_single_district_states: bool = True,
    year: str = "2024-25",
) -> Dict[str, List[District]]:
    """
    Get campaign targets for all states, returning a dict keyed by state.

    Args:
        session: Database session
        size_range: Tuple of (min_enrollment, max_enrollment)
        districts_per_state: Target districts per state (default 4)
        exclude_single_district_states: Skip HI and PR (single-district states)
        year: School year for bell schedule check

    Returns:
        Dict mapping state codes to lists of District objects

    Example:
        >>> targets = get_campaign_targets_by_state(session, (1000, 50000))
        >>> for state, districts in targets.items():
        ...     print(f"{state}: {len(districts)} targets")
    """
    # Single-district states at 100% coverage - cannot add more
    SINGLE_DISTRICT_STATES = {'HI', 'PR'}

    # Get all states with districts
    all_states = (
        session.query(District.state)
        .distinct()
        .order_by(District.state)
        .all()
    )

    results = {}

    for (state,) in all_states:
        if exclude_single_district_states and state in SINGLE_DISTRICT_STATES:
            continue

        districts = get_target_districts(
            session=session,
            state=state,
            size_range=size_range,
            limit=districts_per_state,
            exclude_large=True,
            year=year,
        )

        if districts:
            results[state] = districts

    return results


def get_size_distribution_summary(session: Session, year: str = "2024-25") -> Dict:
    """
    Get summary of enrichment coverage by district size category.

    Returns breakdown of large (>50K), medium (1K-50K), and small (<1K) districts.

    Args:
        session: Database session
        year: School year for bell schedule check

    Returns:
        Dict with size categories and their enrichment statistics
    """
    from sqlalchemy import case, func as sqlfunc

    # Define size categories
    size_case = case(
        (District.enrollment > 50000, 'Large (>50K)'),
        (District.enrollment >= 1000, 'Medium (1K-50K)'),
        else_='Small (<1K)'
    )

    results = (
        session.query(
            size_case.label('size_category'),
            sqlfunc.count(sqlfunc.distinct(District.nces_id)).label('total'),
            sqlfunc.count(sqlfunc.distinct(BellSchedule.district_id)).label('enriched'),
        )
        .outerjoin(
            BellSchedule,
            and_(
                District.nces_id == BellSchedule.district_id,
                BellSchedule.year == year,
            ),
        )
        .filter(District.enrollment.isnot(None))
        .group_by(size_case)
        .order_by(size_case)
        .all()
    )

    return {
        r.size_category: {
            'total': r.total,
            'enriched': r.enriched or 0,
            'coverage_pct': round(100.0 * (r.enriched or 0) / r.total, 2) if r.total > 0 else 0,
        }
        for r in results
    }
