"""
Enrichment Attempt Tracking

Functions for logging and querying bell schedule enrichment attempts,
including security blocks, failures, and retry management.

Usage:
    from infrastructure.database.enrichment_tracking import log_attempt, should_skip_district

    # Log a scraper response
    log_attempt(session, district_id='0622710', url='https://lausd.org', response=scraper_response)

    # Check before attempting
    if should_skip_district(session, district_id='0622710'):
        print("Skipping district - previously blocked")
"""

from typing import Optional, Dict, List, Any
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
import json


def log_attempt(
    session: Session,
    district_id: str,
    url: str,
    response: Dict[str, Any],
    enrichment_tier: Optional[str] = None,
    scraper_version: str = "1.1.0",
    notes: Optional[str] = None
) -> int:
    """
    Log an enrichment attempt to the database

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID (e.g., '0622710')
        url: URL that was attempted
        response: Scraper response dict with keys: success, url, errorCode, blocked, timing, etc.
        enrichment_tier: Optional tier ('tier1', 'tier2', 'tier3')
        scraper_version: Version of scraper service
        notes: Optional notes about the attempt

    Returns:
        ID of inserted record

    Example:
        >>> response = scraper.scrape({'url': 'https://district.org'})
        >>> log_attempt(session, '0622710', 'https://district.org', response)
        123
    """
    # Map scraper errorCode to database status
    status_map = {
        None: 'success',       # No error = success
        'BLOCKED': 'blocked',
        'NOT_FOUND': 'not_found',
        'TIMEOUT': 'timeout',
        'QUEUE_FULL': 'queue_full',
        'NETWORK_ERROR': 'error',
    }

    error_code = response.get('errorCode')
    status = status_map.get(error_code, 'error')

    # Determine block type if blocked
    block_type = None
    if response.get('blocked') or status == 'blocked':
        # Try to infer from error message or response details
        error_msg = (response.get('error') or '').lower()
        if 'cloudflare' in error_msg or 'cf-browser-verification' in error_msg:
            block_type = 'cloudflare'
        elif 'captcha' in error_msg or 'recaptcha' in error_msg:
            block_type = 'captcha'
        elif 'waf' in error_msg or 'forbidden' in error_msg or response.get('statusCode') == 403:
            block_type = 'waf'

    # Insert record
    result = session.execute(
        text("""
            INSERT INTO enrichment_attempts (
                district_id,
                url,
                status,
                block_type,
                http_status_code,
                error_message,
                timing_ms,
                scraper_version,
                enrichment_tier,
                notes,
                response_details
            ) VALUES (
                :district_id,
                :url,
                :status,
                :block_type,
                :http_status_code,
                :error_message,
                :timing_ms,
                :scraper_version,
                :enrichment_tier,
                :notes,
                :response_details
            )
            RETURNING id
        """),
        {
            'district_id': district_id,
            'url': url,
            'status': status,
            'block_type': block_type,
            'http_status_code': response.get('statusCode'),
            'error_message': response.get('error'),
            'timing_ms': int(response.get('timing', 0)),
            'scraper_version': scraper_version,
            'enrichment_tier': enrichment_tier,
            'notes': notes,
            'response_details': json.dumps(response),
        }
    )

    record_id = result.scalar()
    session.commit()

    return record_id


def should_skip_district(session: Session, district_id: str) -> bool:
    """
    Check if a district should be skipped due to previous failures

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID

    Returns:
        True if district is flagged to skip, False otherwise

    Example:
        >>> if should_skip_district(session, '0622710'):
        ...     print("Skipping - previously blocked")
    """
    result = session.execute(
        text("SELECT should_skip_district(:district_id)"),
        {'district_id': district_id}
    )
    return result.scalar()


def mark_district_skip(
    session: Session,
    district_id: str,
    reason: str = "repeated_failures"
) -> int:
    """
    Mark a district to skip in future enrichment attempts

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID
        reason: Reason for skipping (e.g., 'cloudflare_block_3_attempts')

    Returns:
        Number of records updated

    Example:
        >>> mark_district_skip(session, '0622710', 'cloudflare_block_3_attempts')
        3
    """
    result = session.execute(
        text("""
            UPDATE enrichment_attempts
            SET
                skip_future_attempts = TRUE,
                skip_reason = :reason
            WHERE district_id = :district_id
            AND skip_future_attempts = FALSE
        """),
        {'district_id': district_id, 'reason': reason}
    )
    session.commit()
    return result.rowcount


def get_districts_to_skip(session: Session) -> List[Dict[str, Any]]:
    """
    Get list of districts that should be skipped

    Returns:
        List of dicts with keys: district_id, district_name, state, last_attempt,
        attempt_count, block_types, marked_skip

    Example:
        >>> for district in get_districts_to_skip(session):
        ...     print(f"{district['district_name']} ({district['state']}) - {district['block_types']}")
    """
    result = session.execute(text("SELECT * FROM v_districts_to_skip ORDER BY state, district_name"))
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def get_recent_blocks(session: Session, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get recent security blocks detected

    Args:
        session: SQLAlchemy session
        days: Number of days to look back (default 30)

    Returns:
        List of dicts with block details

    Example:
        >>> blocks = get_recent_blocks(session, days=7)
        >>> print(f"Found {len(blocks)} blocks in last 7 days")
    """
    result = session.execute(
        text("""
            SELECT
                ea.attempted_at,
                ea.district_id,
                d.name AS district_name,
                d.state,
                ea.url,
                ea.block_type,
                ea.http_status_code,
                ea.retry_count
            FROM enrichment_attempts ea
            JOIN districts d ON ea.district_id = d.nces_id
            WHERE
                ea.status = 'blocked'
                AND ea.attempted_at > CURRENT_TIMESTAMP - INTERVAL :days DAY
            ORDER BY ea.attempted_at DESC
        """),
        {'days': days}
    )
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def get_attempt_summary(session: Session) -> List[Dict[str, Any]]:
    """
    Get summary statistics of all enrichment attempts

    Returns:
        List of dicts with summary by status and block_type

    Example:
        >>> summary = get_attempt_summary(session)
        >>> for row in summary:
        ...     print(f"{row['status']}: {row['attempt_count']} attempts, {row['unique_districts']} districts")
    """
    result = session.execute(text("SELECT * FROM v_enrichment_attempt_summary"))
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def get_district_attempt_history(
    session: Session,
    district_id: str
) -> List[Dict[str, Any]]:
    """
    Get full attempt history for a specific district

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID

    Returns:
        List of attempt records, newest first

    Example:
        >>> history = get_district_attempt_history(session, '0622710')
        >>> for attempt in history:
        ...     print(f"{attempt['attempted_at']}: {attempt['status']}")
    """
    result = session.execute(
        text("""
            SELECT
                id,
                url,
                attempted_at,
                status,
                block_type,
                http_status_code,
                error_message,
                timing_ms,
                retry_count,
                skip_future_attempts,
                skip_reason,
                notes
            FROM enrichment_attempts
            WHERE district_id = :district_id
            ORDER BY attempted_at DESC
        """),
        {'district_id': district_id}
    )
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def auto_flag_repeat_failures(
    session: Session,
    block_threshold: int = 3,
    not_found_threshold: int = 4
) -> int:
    """
    Automatically flag districts with repeated failures

    This implements the protocol from BELL_SCHEDULE_OPERATIONS_GUIDE.md:
    - 3+ blocked attempts → mark as skip
    - 4+ 404 errors → mark as skip

    Args:
        session: SQLAlchemy session
        block_threshold: Number of blocks before auto-flagging (default 3)
        not_found_threshold: Number of 404s before auto-flagging (default 4)

    Returns:
        Number of districts flagged

    Example:
        >>> flagged = auto_flag_repeat_failures(session)
        >>> print(f"Auto-flagged {flagged} districts")
    """
    # Find districts with repeated blocks
    blocked_districts = session.execute(
        text("""
            SELECT district_id
            FROM enrichment_attempts
            WHERE status = 'blocked'
            AND skip_future_attempts = FALSE
            GROUP BY district_id
            HAVING COUNT(*) >= :threshold
        """),
        {'threshold': block_threshold}
    ).fetchall()

    # Find districts with repeated 404s
    not_found_districts = session.execute(
        text("""
            SELECT district_id
            FROM enrichment_attempts
            WHERE status = 'not_found'
            AND skip_future_attempts = FALSE
            GROUP BY district_id
            HAVING COUNT(*) >= :threshold
        """),
        {'threshold': not_found_threshold}
    ).fetchall()

    count = 0

    # Flag blocked districts
    for (district_id,) in blocked_districts:
        mark_district_skip(session, district_id, f'auto_flag_{block_threshold}_blocks')
        count += 1

    # Flag not_found districts
    for (district_id,) in not_found_districts:
        mark_district_skip(session, district_id, f'auto_flag_{not_found_threshold}_not_found')
        count += 1

    return count


# Convenience function for direct use with scraper service
def log_scraper_response(
    session: Session,
    district_id: str,
    scraper_response: Dict[str, Any],
    enrichment_tier: Optional[str] = None
) -> int:
    """
    Convenience wrapper for logging a scraper service response

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID
        scraper_response: Full response dict from scraper service POST /scrape
        enrichment_tier: Optional tier identifier

    Returns:
        ID of logged attempt

    Example:
        >>> import requests
        >>> response = requests.post('http://localhost:3000/scrape', json={'url': 'https://district.org'}).json()
        >>> log_scraper_response(session, '0622710', response, enrichment_tier='tier1')
        123
    """
    return log_attempt(
        session=session,
        district_id=district_id,
        url=scraper_response.get('url', ''),
        response=scraper_response,
        enrichment_tier=enrichment_tier
    )


if __name__ == '__main__':
    # Example usage
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        # Get summary
        print("=== Attempt Summary ===")
        for row in get_attempt_summary(session):
            print(f"{row['status']}: {row['attempt_count']} attempts, {row['unique_districts']} districts")

        # Get districts to skip
        print("\n=== Districts to Skip ===")
        to_skip = get_districts_to_skip(session)
        print(f"Found {len(to_skip)} districts flagged to skip")
        for district in to_skip[:10]:  # First 10
            print(f"  {district['district_name']} ({district['state']}) - {district['block_types']}")

        # Get recent blocks
        print("\n=== Recent Blocks (Last 7 Days) ===")
        blocks = get_recent_blocks(session, days=7)
        print(f"Found {len(blocks)} blocks")
        for block in blocks[:5]:  # First 5
            print(f"  {block['attempted_at'].strftime('%Y-%m-%d %H:%M')} - {block['district_name']} ({block['block_type']})")
