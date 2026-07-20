"""
Enrichment Verification Module

This module provides safeguards against AI hallucination of enrichment work.
Added after "The Case of the Missing Bell Schedules" investigation (Jan 24, 2026)
which revealed that AI instances had documented work that was never performed.

Key safeguards:
1. get_verified_enrichment_count() - Always query database, never trust memory
2. detect_count_discrepancy() - Alert when documented != actual
3. validate_handoff_claims() - Verify handoff documents against database
4. verify_audit_completeness() - Ensure DataLineage trail exists

Usage:
    from infrastructure.database.verification import (
        detect_count_discrepancy,
        generate_handoff_report,
        validate_handoff_claims,
        verify_audit_completeness
    )

    # Before documenting any enrichment count:
    from infrastructure.database.queries import get_enrichment_summary
    with session_scope() as session:
        summary = get_enrichment_summary(session)
        verified_count = summary['enriched_districts']
        # Use ONLY verified_count in documentation

    # Before committing handoff documents:
    result = validate_handoff_claims(claims)
    if not result['valid']:
        print(format_validation_warning(result))
"""

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from infrastructure.database.models import BellSchedule, DataLineage, District


def _utcnow() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow is deprecated and naive)."""
    return datetime.now(timezone.utc)


# Below this count the normal approximation is too narrow and the exact
# Poisson (Garwood) interval is used instead (issue #414).
_NORMAL_APPROX_MIN_COUNT = 30


def _poisson_cdf(k: int, mu: float) -> float:
    """P(X <= k) for X ~ Poisson(mu), by direct summation (small k only)."""
    term = math.exp(-mu)
    total = term
    for i in range(1, k + 1):
        term *= mu / i
        total += term
    return min(total, 1.0)


def _solve_mu(target_cdf: float, k: int, lo: float, hi: float) -> float:
    """Find mu with _poisson_cdf(k, mu) == target_cdf by bisection.

    The CDF is strictly decreasing in mu, so plain bisection converges."""
    for _ in range(60):
        mid = (lo + hi) / 2
        if _poisson_cdf(k, mid) > target_cdf:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _calculate_confidence_interval(count: int, confidence_level: float = 0.95) -> Tuple[int, int]:
    """
    Calculate Poisson-based confidence interval for count data.

    Uses normal approximation for larger counts (n >= 30), exact Poisson
    (Garwood) for smaller — the normal approximation is over-narrow at small
    counts and produced false alerts (issue #414).

    Args:
        count: Observed count
        confidence_level: Confidence level (0.95 or 0.99)

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if count < 0:
        return (0, 0)

    alpha = 1 - confidence_level

    if count == 0:
        # Special case: 0 observed, CI is [0, upper]
        # Using Poisson: upper = -ln(alpha)
        upper = -math.log(alpha)
        return (0, int(math.ceil(upper)))

    if count < _NORMAL_APPROX_MIN_COUNT:
        # Exact Poisson (Garwood): lower solves P(X >= count | mu) = alpha/2,
        # i.e. CDF(count-1, mu) = 1 - alpha/2; upper solves CDF(count, mu) = alpha/2.
        lower = _solve_mu(1 - alpha / 2, count - 1, 0.0, float(count))
        upper = _solve_mu(alpha / 2, count, float(count), 5.0 * count + 20.0)
        return (int(lower), int(math.ceil(upper)))

    # Z-scores for confidence levels
    z_scores = {0.95: 1.96, 0.99: 2.576}
    z = z_scores.get(confidence_level, 1.96)

    # For Poisson, variance ≈ count, so std dev ≈ sqrt(count)
    std_dev = math.sqrt(count)

    lower = max(0, int(count - z * std_dev))
    upper = int(math.ceil(count + z * std_dev))

    return (lower, upper)


def detect_count_discrepancy(
    documented: int,
    actual: int,
    tolerance_percent: float = 5.0,  # Kept for backward compatibility
    use_confidence_interval: bool = True
) -> Dict:
    """
    Detect discrepancy between documented and actual enrichment counts.

    Uses confidence interval-based thresholds per Watson's recommendation (Jan 24, 2026).
    This provides statistically sound detection that adapts to count size:
    - Small counts: wider tolerance (single errors less critical)
    - Large counts: tighter tolerance (percentage-based)

    Args:
        documented: Count claimed in documentation
        actual: Count verified from database
        tolerance_percent: Fallback percentage tolerance (default 5%)
        use_confidence_interval: Use CI-based detection (recommended)

    Returns:
        Dict with discrepancy analysis:
        - has_discrepancy: bool
        - discrepancy_percent: float
        - severity: 'info' | 'warning' | 'critical'
        - message: str
        - confidence_interval: Tuple[int, int] (if CI-based)
    """
    if actual == 0 and documented == 0:
        return {
            'has_discrepancy': False,
            'discrepancy_percent': 0.0,
            'severity': 'info',
            'message': 'Both counts are zero',
            'documented': documented,
            'actual': actual
        }

    if actual == 0:
        return {
            'has_discrepancy': True,
            'discrepancy_percent': 100.0,
            'severity': 'critical',
            'message': f'Database has 0 records but documentation claims {documented}',
            'documented': documented,
            'actual': actual,
            'alert': True
        }

    discrepancy_percent = abs(documented - actual) / actual * 100

    if use_confidence_interval:
        # Calculate 95% CI for warning threshold
        ci_95_lower, ci_95_upper = _calculate_confidence_interval(actual, 0.95)
        # Calculate 99% CI for critical threshold
        ci_99_lower, ci_99_upper = _calculate_confidence_interval(actual, 0.99)

        # Check against confidence intervals
        within_95_ci = ci_95_lower <= documented <= ci_95_upper
        within_99_ci = ci_99_lower <= documented <= ci_99_upper

        if within_95_ci:
            severity = 'info'
            has_discrepancy = False
            message = f'Documented {documented} within 95% CI [{ci_95_lower}, {ci_95_upper}]'
        elif within_99_ci:
            severity = 'warning'
            has_discrepancy = True
            message = (
                f'Documented {documented} outside 95% CI [{ci_95_lower}, {ci_95_upper}] '
                f'but within 99% CI [{ci_99_lower}, {ci_99_upper}]'
            )
        else:
            severity = 'critical'
            has_discrepancy = True
            message = (
                f'CRITICAL: Documented {documented} outside 99% CI [{ci_99_lower}, {ci_99_upper}]. '
                f'Actual: {actual}, difference: {discrepancy_percent:.1f}%'
            )

        return {
            'has_discrepancy': has_discrepancy,
            'discrepancy_percent': discrepancy_percent,
            'severity': severity,
            'message': message,
            'documented': documented,
            'actual': actual,
            'alert': severity == 'critical',
            'confidence_interval_95': (ci_95_lower, ci_95_upper),
            'confidence_interval_99': (ci_99_lower, ci_99_upper),
            'method': 'confidence_interval'
        }
    else:
        # Fallback to percentage-based (backward compatible)
        if discrepancy_percent <= tolerance_percent:
            severity = 'info'
            has_discrepancy = False
            message = f'Counts within {tolerance_percent}% tolerance'
        elif discrepancy_percent <= 20:
            severity = 'warning'
            has_discrepancy = True
            message = f'Documented {documented}, actual {actual} ({discrepancy_percent:.1f}% difference)'
        else:
            severity = 'critical'
            has_discrepancy = True
            message = f'CRITICAL: Documented {documented}, actual {actual} ({discrepancy_percent:.1f}% difference)'

        return {
            'has_discrepancy': has_discrepancy,
            'discrepancy_percent': discrepancy_percent,
            'severity': severity,
            'message': message,
            'documented': documented,
            'actual': actual,
            'alert': severity == 'critical',
            'method': 'percentage'
        }


def generate_handoff_report(session: Optional[Session] = None) -> Dict:
    """
    Generate handoff report with verified database counts.

    This function MUST be used for any handoff documentation to ensure
    counts come from the database, not from AI memory.

    Args:
        session: Optional database session (creates one if not provided)

    Returns:
        Dict with verified counts and metadata
    """
    from infrastructure.database.connection import session_scope
    from infrastructure.database.queries import get_enrichment_summary

    close_session = False
    if session is None:
        # Create session context
        from infrastructure.database.connection import get_session
        session = get_session()
        close_session = True

    try:
        summary = get_enrichment_summary(session)

        # Get date distribution
        date_dist = session.query(
            func.date(BellSchedule.created_at).label('date'),
            func.count(BellSchedule.id).label('count')
        ).group_by(func.date(BellSchedule.created_at)).all()

        date_distribution = {str(row.date): row.count for row in date_dist}

        # Get state coverage
        state_counts = session.query(
            District.state,
            func.count(func.distinct(BellSchedule.district_id)).label('count')
        ).join(
            BellSchedule, District.nces_id == BellSchedule.district_id
        ).group_by(District.state).all()

        states_enriched = {row.state: row.count for row in state_counts}

        return {
            'database_snapshot_at': _utcnow().isoformat(),
            'verified_at': _utcnow().isoformat(),
            'enriched_districts': summary.get('enriched_districts', 0),
            'total_bell_schedules': summary.get('total_bell_schedules', 0),
            'states_with_enrichment': len(states_enriched),
            'states_enriched': states_enriched,
            'date_distribution': date_distribution,
            'summary': f"Verified {summary.get('enriched_districts', 0)} districts enriched"
        }
    finally:
        if close_session:
            session.close()


def validate_handoff_claims(claims: Dict, session: Optional[Session] = None) -> Dict:
    """
    Validate handoff claims against database state.

    Args:
        claims: Dict with claimed enrichment data:
            - date: str (YYYY-MM-DD)
            - districts_added: List[str] (NCES IDs)
            - total_enriched: int
        session: Optional database session

    Returns:
        Dict with validation results:
        - valid: bool
        - mismatches: List[str]
        - details: Dict
    """
    from infrastructure.database.connection import session_scope

    close_session = False
    if session is None:
        from infrastructure.database.connection import get_session
        session = get_session()
        close_session = True

    try:
        mismatches = []
        details = {}

        # Check claimed districts exist in database
        claimed_districts = claims.get('districts_added', [])
        for nces_id in claimed_districts:
            count = session.query(BellSchedule).filter(
                BellSchedule.district_id == nces_id
            ).count()

            if count == 0:
                mismatches.append(f'District {nces_id} not found in database')
                details[nces_id] = {'found': False, 'records': 0}
            else:
                details[nces_id] = {'found': True, 'records': count}

        # Check total count
        claimed_total = claims.get('total_enriched', 0)
        actual_total = session.query(
            func.count(func.distinct(BellSchedule.district_id))
        ).scalar()

        if claimed_total != actual_total:
            discrepancy = detect_count_discrepancy(claimed_total, actual_total)
            if discrepancy['has_discrepancy']:
                mismatches.append(
                    f"Total count mismatch: claimed {claimed_total}, actual {actual_total}"
                )

        # Check date has records (if date provided)
        claimed_date = claims.get('date')
        if claimed_date:
            from datetime import datetime
            try:
                date_obj = datetime.strptime(claimed_date, '%Y-%m-%d').date()
                date_count = session.query(BellSchedule).filter(
                    func.date(BellSchedule.created_at) == date_obj
                ).count()

                if date_count == 0 and len(claimed_districts) > 0:
                    mismatches.append(
                        f"No records created on {claimed_date} but {len(claimed_districts)} districts claimed"
                    )
                details['date_records'] = date_count
            except (ValueError, TypeError):
                # TypeError: a non-string date claim (issue #373) is a bad
                # claim, not a crash
                mismatches.append(f"Invalid date format: {claimed_date!r}")

        return {
            'valid': len(mismatches) == 0,
            'mismatches': mismatches,
            'details': details,
            'documented_count': claimed_total,
            'actual_count': actual_total,
            'validated_at': _utcnow().isoformat()
        }
    finally:
        if close_session:
            session.close()


def format_validation_warning(result: Dict) -> str:
    """
    Format warning banner for failed validation.

    Args:
        result: Validation result from validate_handoff_claims()

    Returns:
        Formatted warning string for documentation
    """
    if result.get('valid', True):
        return ""

    lines = [
        "> **WARNING - VALIDATION FAILED**",
        ">",
        "> This handoff document failed automated validation against the database.",
        "> The claims below may be hallucinated or incorrect.",
        ">"
    ]

    for mismatch in result.get('mismatches', []):
        lines.append(f"> - {mismatch}")

    lines.extend([
        ">",
        f"> Documented count: {result.get('documented_count', 'N/A')}",
        f"> Actual database count: {result.get('actual_count', 'N/A')}",
        f"> Validated at: {result.get('validated_at', 'N/A')}",
        ">",
        "> See: ~/Development/221B-baker-street/CASE_FILE.md"
    ])

    return "\n".join(lines)


def _bell_lineage_ids(session: Session) -> set:
    """All DataLineage entity_ids recorded for bell_schedules."""
    return {
        row[0] for row in session.query(DataLineage.entity_id).filter(
            DataLineage.entity_type == 'bell_schedule'
        ).all()
    }


def _bell_entity_keys(bell_row) -> Tuple[str, str]:
    """The two entity_id conventions a bell_schedule row may be recorded under.

    Legacy writers (import_all_data) log the numeric row id; add_bell_schedule
    logs the composite "{district}/{year}/{grade}" key. The audit layer must
    accept BOTH or every row written by one convention reads as a gap/orphan
    under the other (found during the #294 fix)."""
    bell_id, district_id, year, grade_level = (
        bell_row.id, bell_row.district_id, bell_row.year, bell_row.grade_level
    )
    return str(bell_id), f"{district_id}/{year}/{grade_level}"


def verify_audit_completeness(session: Session) -> Dict:
    """
    Verify audit trail completeness for bell_schedules.

    Args:
        session: Database session

    Returns:
        Dict with completeness metrics
    """
    bells = session.query(
        BellSchedule.id, BellSchedule.district_id,
        BellSchedule.year, BellSchedule.grade_level
    ).all()
    total_bell = len(bells)

    lineage_ids = _bell_lineage_ids(session)

    with_lineage = sum(
        1 for b in bells
        if lineage_ids.intersection(_bell_entity_keys(b))
    )

    missing = total_bell - with_lineage
    completeness = with_lineage / total_bell if total_bell > 0 else 1.0

    return {
        'total_bell_schedules': total_bell,
        'with_lineage': with_lineage,
        'missing_lineage': missing,
        'completeness_percent': completeness * 100,
        'verified_at': _utcnow().isoformat()
    }


def find_lineage_gaps(session: Session) -> List[Dict]:
    """
    Find bell_schedules without corresponding DataLineage entries.

    Args:
        session: Database session

    Returns:
        List of dicts with district_id and created_at for gaps
    """
    all_bells = session.query(
        BellSchedule.id, BellSchedule.district_id, BellSchedule.created_at,
        BellSchedule.year, BellSchedule.grade_level
    ).all()

    lineage_ids = _bell_lineage_ids(session)

    # A bell row is covered if EITHER of its entity_id conventions is recorded
    gaps = []
    for bell in all_bells:
        keys = {str(bell.id), f"{bell.district_id}/{bell.year}/{bell.grade_level}"}
        if not lineage_ids.intersection(keys):
            gaps.append({
                'id': bell.id,
                'district_id': bell.district_id,
                'created_at': bell.created_at.isoformat() if bell.created_at else None
            })

    return gaps


def validate_date_range(session: Session, start_date: datetime, end_date: datetime) -> Dict:
    """
    Validate records exist for a date range.

    Args:
        session: Database session
        start_date: Start of date range
        end_date: End of date range

    Returns:
        Dict with daily counts and gap analysis
    """
    current = start_date.date() if hasattr(start_date, 'date') else start_date
    end = end_date.date() if hasattr(end_date, 'date') else end_date

    # One GROUP BY over the whole range — the per-day COUNT loop was an
    # unbounded N+1 (issue #293); zero-days are filled in Python below.
    rows = session.query(
        func.date(BellSchedule.created_at).label('date'),
        func.count(BellSchedule.id).label('count')
    ).filter(
        func.date(BellSchedule.created_at) >= current,
        func.date(BellSchedule.created_at) <= end,
    ).group_by(func.date(BellSchedule.created_at)).all()
    counts_by_date = {str(row.date): row.count for row in rows}

    daily_counts = {}
    while current <= end:
        daily_counts[str(current)] = counts_by_date.get(str(current), 0)
        current += timedelta(days=1)

    # Identify gaps (dates with zero records)
    gaps = [date for date, count in daily_counts.items() if count == 0]

    return {
        'start_date': str(start_date),
        'end_date': str(end_date),
        'daily_counts': daily_counts,
        'dates_with_records': [d for d, c in daily_counts.items() if c > 0],
        'gap_dates': gaps,
        'has_gaps': len(gaps) > 0
    }


def generate_audit_report(session: Session) -> Dict:
    """
    Generate comprehensive audit report with date distribution.

    Args:
        session: Database session

    Returns:
        Dict with audit information
    """
    # Date distribution
    date_dist = session.query(
        func.date(BellSchedule.created_at).label('date'),
        func.count(BellSchedule.id).label('count')
    ).group_by(func.date(BellSchedule.created_at)).order_by('date').all()

    date_distribution = {str(row.date): row.count for row in date_dist}

    # Get completeness
    completeness = verify_audit_completeness(session)

    # Get total stats
    total_districts = session.query(
        func.count(func.distinct(BellSchedule.district_id))
    ).scalar()

    total_records = session.query(func.count(BellSchedule.id)).scalar()

    return {
        'generated_at': _utcnow().isoformat(),
        'total_enriched_districts': total_districts,
        'total_bell_schedule_records': total_records,
        'date_distribution': date_distribution,
        'records_by_date': date_distribution,  # Alias for compatibility
        'audit_completeness': completeness,
        'earliest_record': min(date_distribution.keys()) if date_distribution else None,
        'latest_record': max(date_distribution.keys()) if date_distribution else None
    }


def check_audit_integrity(session: Session) -> Dict:
    """
    Check audit trail integrity for data integrity violations.

    Args:
        session: Database session

    Returns:
        Dict with integrity status and violations
    """
    violations = []

    # Check completeness
    completeness = verify_audit_completeness(session)

    if completeness['missing_lineage'] > 0:
        violations.append({
            'type': 'MISSING_LINEAGE',
            'count': completeness['missing_lineage'],
            'message': f"{completeness['missing_lineage']} bell_schedules without DataLineage entries"
        })

    # Check for orphaned lineage (lineage without bell_schedule). Compare
    # against BOTH entity_id conventions (numeric row id and the composite
    # "{district}/{year}/{grade}" key) — the old code hard-coded 0 here, so the
    # check never fired (issue #294).
    bells = session.query(
        BellSchedule.id, BellSchedule.district_id,
        BellSchedule.year, BellSchedule.grade_level
    ).all()
    valid_keys = set()
    for b in bells:
        valid_keys.update(_bell_entity_keys(b))
    orphan_count = sum(
        1 for eid in _bell_lineage_ids(session) if eid not in valid_keys
    )

    if orphan_count and orphan_count > 0:
        violations.append({
            'type': 'ORPHANED_LINEAGE',
            'count': orphan_count,
            'message': f"{orphan_count} DataLineage entries without corresponding bell_schedules"
        })

    integrity_status = 'ok' if len(violations) == 0 else 'violation'

    return {
        'integrity_status': integrity_status,
        'violations': violations,
        'missing_lineage_count': completeness['missing_lineage'],
        'completeness_percent': completeness['completeness_percent'],
        'checked_at': _utcnow().isoformat()
    }


# =============================================================================
# REQ-038: Content Plausibility Validation
# =============================================================================

import re

# Valid grade levels per REQ-038 (expanded per Watson's review)
VALID_GRADE_LEVELS = {
    'elementary', 'middle', 'high',
    'k-8', 'k-12', '6-12',
    'pre-k', 'prek', 'early-childhood', 'preschool',  # Added per Watson
    'primary', 'intermediate', 'secondary', 'junior-high'  # Aliases
}

# Time format patterns: 12-hour with AM/PM, and 24-hour HH:MM (issue #66 —
# the acquisition pipeline emits 24-hour times like '08:00' / '14:20')
TIME_PATTERN = re.compile(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$', re.IGNORECASE)
TIME_24H_PATTERN = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')

from infrastructure.database.school_year import (  # noqa: E402
    GROSS_MINUTES_MIN,
    GROSS_MINUTES_MAX,
    DB_CHECK_MINUTES_MIN,
    DB_CHECK_MINUTES_MAX,
)

# Plausible ranges (per Watson's review)
PLAUSIBLE_START_RANGE = (6 * 60, 10 * 60 + 30)  # 6:00 AM - 10:30 AM in minutes from midnight
PLAUSIBLE_END_RANGE = (14 * 60, 17 * 60 + 30)    # 2:00 PM - 5:30 PM in minutes from midnight
# The ONE gross plausibility band (REQ-055 / issue #72): warn outside 240-510.
# Hard error bounds stay the DB outer sanity band (100-600, chk_instructional_minutes).
PLAUSIBLE_INSTRUCTIONAL_RANGE = (GROSS_MINUTES_MIN, GROSS_MINUTES_MAX)


def _time_to_minutes(time_str: str) -> Optional[int]:
    """Convert 'HH:MM AM/PM' or 24-hour 'HH:MM' to minutes from midnight.

    Non-string input is unparseable, not a crash (issue #460)."""
    if not isinstance(time_str, str):
        return None
    time_str = time_str.strip()

    match = TIME_PATTERN.match(time_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        period = match.group(3).upper()

        if hours == 12:
            hours = 0 if period == 'AM' else 12
        elif period == 'PM':
            hours += 12

        return hours * 60 + minutes

    # 24-hour fallback (e.g. '08:00', '14:20')
    match = TIME_24H_PATTERN.match(time_str)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))

    return None


def validate_schedule_plausibility(schedule: Dict) -> Dict:
    """
    Validate a single bell schedule for plausibility (REQ-038).

    Args:
        schedule: Dict with keys: start_time, end_time, grade_level, instructional_minutes

    Returns:
        Dict with:
        - valid: bool
        - errors: List[str] - validation errors if any
        - warnings: List[str] - non-fatal issues
    """
    errors = []
    warnings = []

    start_time = schedule.get('start_time') or ''
    end_time = schedule.get('end_time') or ''
    grade_level = (schedule.get('grade_level') or '').lower()
    instructional_minutes = schedule.get('instructional_minutes')

    # 1. Validate time format. Times are OPTIONAL (issue #68): an enrichment may
    # carry only instructional_minutes — absent times skip the time checks
    # entirely rather than failing on a placeholder.
    start_minutes = _time_to_minutes(start_time) if start_time else None
    end_minutes = _time_to_minutes(end_time) if end_time else None

    if start_time and start_minutes is None:
        errors.append(f"Invalid start_time format: '{start_time}'. Expected HH:MM AM/PM or 24-hour HH:MM")

    if end_time and end_minutes is None:
        errors.append(f"Invalid end_time format: '{end_time}'. Expected HH:MM AM/PM or 24-hour HH:MM")

    # 2. Validate grade level. A missing value gets its own clear error rather
    # than the confusing "Invalid grade_level: ''" the ''-default produced
    # (issue #459).
    if not grade_level:
        errors.append("grade_level is required")
    elif grade_level not in VALID_GRADE_LEVELS:
        errors.append(f"Invalid grade_level: '{grade_level}'. Valid: {VALID_GRADE_LEVELS}")

    # 3. Validate temporal order (start before end)
    if start_minutes is not None and end_minutes is not None:
        if start_minutes >= end_minutes:
            errors.append(f"Start time ({start_time}) must be before end time ({end_time})")

    # 4. Validate plausible start time range
    if start_minutes is not None:
        if not (PLAUSIBLE_START_RANGE[0] <= start_minutes <= PLAUSIBLE_START_RANGE[1]):
            warnings.append(f"Start time {start_time} outside typical range (6:00 AM - 10:30 AM)")

    # 5. Validate plausible end time range
    if end_minutes is not None:
        if not (PLAUSIBLE_END_RANGE[0] <= end_minutes <= PLAUSIBLE_END_RANGE[1]):
            warnings.append(f"End time {end_time} outside typical range (2:00 PM - 5:30 PM)")

    # 6. Validate instructional minutes range. Parse ONCE — a non-numeric value is
    # a single validation error, never an exception (issue #66: step 7 previously
    # re-cast with a bare int() and crashed on input step 6 had already flagged).
    stated_minutes: Optional[int] = None
    if instructional_minutes is not None:
        try:
            stated_minutes = int(instructional_minutes)
        except (ValueError, TypeError):
            errors.append(f"Invalid instructional_minutes: '{instructional_minutes}'. Must be integer.")

    if stated_minutes is not None:
        if not (DB_CHECK_MINUTES_MIN <= stated_minutes <= DB_CHECK_MINUTES_MAX):
            errors.append(
                f"Instructional minutes ({stated_minutes}) outside sanity bounds "
                f"({DB_CHECK_MINUTES_MIN}-{DB_CHECK_MINUTES_MAX})"
            )
        elif not (PLAUSIBLE_INSTRUCTIONAL_RANGE[0] <= stated_minutes <= PLAUSIBLE_INSTRUCTIONAL_RANGE[1]):
            warnings.append(
                f"Instructional minutes ({stated_minutes}) outside gross plausibility band "
                f"({PLAUSIBLE_INSTRUCTIONAL_RANGE[0]}-{PLAUSIBLE_INSTRUCTIONAL_RANGE[1]})"
            )

    # 7. Cross-validate: calculated duration vs stated instructional minutes
    if start_minutes is not None and end_minutes is not None and stated_minutes is not None:
        calculated_duration = end_minutes - start_minutes

        # Allow some variance for lunch/passing time (30-90 minutes typically)
        max_expected = calculated_duration
        min_expected = calculated_duration - 90  # Subtract max lunch/passing

        if stated_minutes > max_expected:
            errors.append(
                f"Instructional minutes ({stated_minutes}) exceeds total duration ({calculated_duration} min)"
            )
        elif stated_minutes < min_expected:
            warnings.append(
                f"Instructional minutes ({stated_minutes}) unusually low for duration ({calculated_duration} min)"
            )

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'schedule': schedule
    }


def validate_schedules_batch(schedules: List[Dict]) -> Dict:
    """
    Validate a batch of bell schedules (REQ-038).

    Args:
        schedules: List of schedule dicts

    Returns:
        Dict with:
        - all_valid: bool
        - valid_count: int
        - invalid_count: int
        - results: List of individual validation results
        - summary: str
    """
    results = [validate_schedule_plausibility(s) for s in schedules]

    valid_count = sum(1 for r in results if r['valid'])
    invalid_count = len(results) - valid_count
    warning_count = sum(1 for r in results if r['warnings'])

    return {
        'all_valid': invalid_count == 0,
        'valid_count': valid_count,
        'invalid_count': invalid_count,
        'warning_count': warning_count,
        'results': results,
        'summary': f"{valid_count}/{len(results)} schedules valid, {warning_count} with warnings"
    }


# =============================================================================
# REQ-039: Override Audit Trail (Improved per Watson's security review)
# =============================================================================

# Valid override types (prevents arbitrary strings)
VALID_OVERRIDE_TYPES = {
    'count_discrepancy',
    'content_validation',
    'date_range_gap',
    'missing_lineage',
    'plausibility_warning',
    'other'  # Requires detailed reason
}

OVERRIDE_ALERT_THRESHOLD = 5
MAX_REASON_LENGTH = 500  # Prevent excessive input


def _sanitize_reason(reason: str) -> str:
    """Sanitize user-provided reason to prevent injection attacks."""
    if not reason:
        return ''

    # Truncate to max length
    sanitized = reason[:MAX_REASON_LENGTH]

    # Remove potentially dangerous characters FIRST (SQL injection, XSS).
    # Keep alphanumeric, spaces, basic punctuation, hyphens and colons —
    # stripping hyphens mangled legitimate audit reasons like "non-compliant"
    # (issue #292; values land in the ORM's parameterized JSON details, so
    # this whole pass is defense-in-depth, not the actual injection barrier).
    sanitized = re.sub(r'[^\w\s.,!?\'"()/:-]', '', sanitized)

    # Remove SQL-like keywords (case-insensitive)
    sql_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'SELECT', 'UNION', 'ALTER', 'CREATE', 'TRUNCATE']
    for keyword in sql_keywords:
        sanitized = re.sub(rf'\b{keyword}\b', 'BLOCKED', sanitized, flags=re.IGNORECASE)

    # Collapse multiple spaces
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()

    return sanitized


class OverrideTracker:
    """
    Session-scoped override tracker (REQ-039).

    Use as context manager or instantiate per verification run.
    Avoids global state issues identified in Watson's review.
    """

    def __init__(self, alert_threshold: int = OVERRIDE_ALERT_THRESHOLD):
        self.override_count = 0
        self.alert_threshold = alert_threshold
        self.alerts = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def log_override(
        self,
        session: Session,
        override_type: str,
        reason: str,
        context: Dict = None,
        commit: bool = True
    ) -> Dict:
        """
        Log a manual verification override.

        Args:
            session: Database session
            override_type: Must be one of VALID_OVERRIDE_TYPES
            reason: User-provided reason (will be sanitized)
            context: Additional context dict
            commit: Commit the session (default True for standalone use).
                    Pass False when the caller owns the transaction — an
                    unconditional commit here broke outer-transaction
                    atomicity (issue #291).

        Returns:
            Dict with override record details and any alerts
        """
        # Validate override type
        if override_type not in VALID_OVERRIDE_TYPES:
            raise ValueError(
                f"Invalid override_type: '{override_type}'. "
                f"Valid types: {VALID_OVERRIDE_TYPES}"
            )

        # Sanitize reason
        sanitized_reason = _sanitize_reason(reason)

        # Require detailed reason for 'other' type
        if override_type == 'other' and len(sanitized_reason) < 10:
            raise ValueError("Override type 'other' requires detailed reason (min 10 chars)")

        # Create DataLineage entry for audit trail
        # Note: DataLineage uses 'source_file', 'details', 'created_by' (not metadata/source_system)
        # entity_id carries a uuid suffix — the old timestamp+counter scheme
        # could collide across concurrent trackers (issue #412).
        now = _utcnow()
        override_number = self.override_count + 1
        lineage = DataLineage(
            entity_type='verification_override',
            entity_id=f"override_{now.strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex[:8]}",
            operation='manual_override',
            source_file='verification_cli',
            created_at=now,
            created_by='verification_system',
            details={
                'override_type': override_type,
                'reason': sanitized_reason,
                'context': context or {},
                'session_override_number': override_number,
                'original_reason_length': len(reason) if reason else 0
            }
        )
        session.add(lineage)
        if commit:
            session.commit()
        else:
            session.flush()

        # Increment only after the write succeeded — a failed commit used to
        # leave the in-memory count out of sync with the DB (issue #413)
        self.override_count = override_number

        # Check for excessive overrides
        alert = None
        if self.override_count >= self.alert_threshold:
            alert = {
                'type': 'EXCESSIVE_OVERRIDES',
                'message': f"Session has {self.override_count} overrides (threshold: {self.alert_threshold})",
                'severity': 'warning'
            }
            self.alerts.append(alert)

        return {
            'logged': True,
            'override_id': lineage.entity_id,
            'session_count': self.override_count,
            'alert': alert,
            'timestamp': _utcnow().isoformat()
        }


# Convenience function for simple use cases (creates single-use tracker)
def log_verification_override(
    session: Session,
    override_type: str,
    reason: str,
    context: Dict = None,
    tracker: OverrideTracker = None,
    commit: bool = True
) -> Dict:
    """
    Log a manual verification override (REQ-039).

    For multiple overrides in a session, pass a shared OverrideTracker instance
    to properly track cumulative override counts.

    Args:
        session: Database session
        override_type: Type of override (must be in VALID_OVERRIDE_TYPES)
        reason: User-provided reason for override (will be sanitized)
        context: Additional context dict
        tracker: Optional OverrideTracker for session-scoped counting
        commit: Pass False when the caller owns the transaction (issue #291)

    Returns:
        Dict with override record details and any alerts
    """
    if tracker is None:
        tracker = OverrideTracker()

    return tracker.log_override(session, override_type, reason, context, commit=commit)


def get_override_history(session: Session, days: int = 30) -> List[Dict]:
    """
    Get override history for reporting (REQ-039).

    Args:
        session: Database session
        days: Number of days to look back

    Returns:
        List of override records
    """
    cutoff = _utcnow() - timedelta(days=days)

    overrides = session.query(DataLineage).filter(
        DataLineage.entity_type == 'verification_override',
        DataLineage.created_at >= cutoff
    ).order_by(DataLineage.created_at.desc()).all()

    return [
        {
            'id': o.entity_id,
            'timestamp': o.created_at.isoformat() if o.created_at else None,
            'override_type': o.details.get('override_type') if o.details else None,
            'reason': o.details.get('reason') if o.details else None
        }
        for o in overrides
    ]


def get_override_statistics(session: Session, days: int = 30) -> Dict:
    """Get override statistics for monitoring dashboard."""
    history = get_override_history(session, days)

    by_type = {}
    for record in history:
        otype = record.get('override_type', 'unknown')
        by_type[otype] = by_type.get(otype, 0) + 1

    return {
        'total_overrides': len(history),
        'by_type': by_type,
        'period_days': days,
        'average_per_day': len(history) / days if days > 0 else 0
    }


# =============================================================================
# CLI Verification Commands
# =============================================================================

def print_verification_report(session: Session = None):
    """Print a human-readable verification report."""
    from infrastructure.database.connection import session_scope

    if session is None:
        with session_scope() as session:
            _print_report(session)
    else:
        _print_report(session)


def _print_report(session: Session):
    """Internal report printer."""
    print("=" * 60)
    print("ENRICHMENT VERIFICATION REPORT")
    print("=" * 60)
    print()

    # Get verified counts
    report = generate_handoff_report(session)

    print(f"Database Snapshot: {report['verified_at']}")
    print(f"Enriched Districts: {report['enriched_districts']}")
    print(f"Total Bell Schedules: {report['total_bell_schedules']}")
    print(f"States with Enrichment: {report['states_with_enrichment']}")
    print()

    # Date distribution
    print("Records by Date:")
    for date, count in sorted(report['date_distribution'].items()):
        print(f"  {date}: {count} records")
    print()

    # Audit integrity
    integrity = check_audit_integrity(session)
    print(f"Audit Integrity: {integrity['integrity_status'].upper()}")
    print(f"Completeness: {integrity['completeness_percent']:.1f}%")

    if integrity['violations']:
        print("\nViolations:")
        for v in integrity['violations']:
            print(f"  - {v['type']}: {v['message']}")

    print()
    print("=" * 60)


if __name__ == '__main__':
    # Run verification report
    print_verification_report()
