#!/usr/bin/env python3
"""
NCES-to-CDS Crosswalk Utility

Handles conversion between:
- NCES IDs (LEAID): National Center for Education Statistics identifiers
- California CDS Codes: 14-digit County-District-School codes (7-digit for LEA)
- ST_LEAID: State-assigned LEA ID (contains CDS code for California)

California CDS Format:
- 14 digits: CCDDDDDSSSSSSS
  - CC: County code (2 digits)
  - DDDDD: District code (5 digits)
  - SSSSSSS: School code (7 digits, 0000000 for district-level)
- 7 digits (LEA): CCCDDDD (county + district only)

NCES ST_LEAID Format for California:
- "CA-CCCDDDD" (state prefix + 7-digit CDS code)

Data Source:
- Uses state_district_crosswalk table as single source of truth
- Crosswalk populated from NCES CCD ST_LEAID field

Usage:
    from infrastructure.utilities.nces_cds_crosswalk import cds_to_nces, nces_to_cds

    # Convert CDS to NCES
    nces_id = cds_to_nces("6275796", session)

    # Convert NCES to CDS
    cds_code = nces_to_cds("0622710", session)
"""

import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from infrastructure.database.models import District


def validate_cds_code(cds_code: str, allow_school_level: bool = False) -> bool:
    """
    Validate California CDS code format.

    Args:
        cds_code: CDS code to validate
        allow_school_level: If True, accepts 14-digit codes; if False, only 7-digit LEA codes

    Returns:
        True if valid, False otherwise
    """
    if not cds_code or not isinstance(cds_code, str):
        return False

    # Remove any leading/trailing whitespace
    cds_code = cds_code.strip()

    # Check length
    if allow_school_level:
        if len(cds_code) not in (7, 14):
            return False
    else:
        if len(cds_code) != 7:
            return False

    # Check all digits
    if not cds_code.isdigit():
        return False

    return True


def normalize_cds_code(cds_code: str) -> str:
    """
    Normalize CDS code to 7-digit LEA format.

    If 14-digit code provided, extracts first 7 digits (county + district).
    Removes any "CA-" prefix if present.

    Args:
        cds_code: CDS code in any format

    Returns:
        7-digit normalized CDS code

    Raises:
        ValueError: If code is invalid
    """
    if not cds_code:
        raise ValueError("CDS code cannot be empty")

    # Remove whitespace
    cds_code = cds_code.strip()

    # Remove "CA-" prefix if present
    if cds_code.startswith("CA-"):
        cds_code = cds_code[3:]

    # Extract first 7 digits if 14-digit code
    if len(cds_code) == 14:
        cds_code = cds_code[:7]

    # Validate
    if not validate_cds_code(cds_code, allow_school_level=False):
        raise ValueError(f"Invalid CDS code: {cds_code}")

    return cds_code


def cds_to_st_leaid(cds_code: str) -> str:
    """
    Convert CDS code to NCES ST_LEAID format.

    Args:
        cds_code: 7-digit or 14-digit CDS code

    Returns:
        ST_LEAID in format "CA-CCCDDDD"

    Example:
        >>> cds_to_st_leaid("6275796")
        'CA-6275796'
        >>> cds_to_st_leaid("62757960000000")
        'CA-6275796'
    """
    normalized = normalize_cds_code(cds_code)
    return f"CA-{normalized}"


def st_leaid_to_cds(st_leaid: str) -> str:
    """
    Convert NCES ST_LEAID to CDS code.

    Args:
        st_leaid: ST_LEAID in format "CA-CCCDDDD" or just "CCCDDDD"

    Returns:
        7-digit CDS code

    Example:
        >>> st_leaid_to_cds("CA-6275796")
        '6275796'
        >>> st_leaid_to_cds("6275796")
        '6275796'
    """
    return normalize_cds_code(st_leaid)


def cds_to_nces(cds_code: str, session: Session) -> Optional[str]:
    """
    Find NCES ID for a California CDS code.

    Uses state_district_crosswalk table as single source of truth.

    Args:
        cds_code: California CDS code (7 or 14 digits)
        session: SQLAlchemy session

    Returns:
        NCES ID (LEAID) if found, None otherwise

    Example:
        >>> with session_scope() as session:
        ...     nces_id = cds_to_nces("6275796", session)
        ...     print(nces_id)  # "0622710"
    """
    # Normalize CDS code
    normalized_cds = normalize_cds_code(cds_code)

    # Query crosswalk table using state_district_id
    result = session.execute(text("""
        SELECT nces_id
        FROM state_district_crosswalk
        WHERE state = 'CA'
          AND state_district_id = :cds
          AND id_system = 'st_leaid'
    """), {"cds": normalized_cds})
    row = result.fetchone()

    return row[0] if row else None


def nces_to_cds(nces_id: str, session: Session) -> Optional[str]:
    """
    Find CDS code for an NCES ID.

    Uses state_district_crosswalk table as single source of truth.

    Args:
        nces_id: NCES LEAID
        session: SQLAlchemy session

    Returns:
        7-digit CDS code if found, None otherwise

    Example:
        >>> with session_scope() as session:
        ...     cds_code = nces_to_cds("0622710", session)
        ...     print(cds_code)  # "6275796"
    """
    # Query crosswalk table
    result = session.execute(text("""
        SELECT state_district_id
        FROM state_district_crosswalk
        WHERE nces_id = :nces_id
          AND state = 'CA'
          AND id_system = 'st_leaid'
    """), {"nces_id": nces_id})
    row = result.fetchone()

    return row[0] if row else None


def get_district_by_cds(cds_code: str, session: Session, year: str = "2023-24") -> Optional[District]:
    """
    Retrieve full District object by CDS code.

    Args:
        cds_code: California CDS code (7 or 14 digits)
        session: SQLAlchemy session
        year: School year (default: "2023-24")

    Returns:
        District object if found, None otherwise

    Example:
        >>> with session_scope() as session:
        ...     district = get_district_by_cds("6275796", session)
        ...     print(district.name, district.enrollment)
    """
    st_leaid = cds_to_st_leaid(cds_code)

    return session.query(District).filter(
        District.st_leaid == st_leaid,
        District.state == "CA",
        District.year == year
    ).first()


def bulk_cds_to_nces(cds_codes: list[str], session: Session) -> dict[str, Optional[str]]:
    """
    Convert multiple CDS codes to NCES IDs in a single query.

    Uses state_district_crosswalk table as single source of truth.

    Args:
        cds_codes: List of CDS codes
        session: SQLAlchemy session

    Returns:
        Dictionary mapping CDS codes to NCES IDs (None if not found)

    Example:
        >>> with session_scope() as session:
        ...     mapping = bulk_cds_to_nces(["6275796", "1964733"], session)
        ...     print(mapping)  # {"6275796": "0622710", "1964733": "0612345"}
    """
    # Normalize all CDS codes
    normalized_codes = [normalize_cds_code(cds) for cds in cds_codes]

    # Query crosswalk table for all at once
    placeholders = ', '.join([f':cds_{i}' for i in range(len(normalized_codes))])
    params = {f'cds_{i}': cds for i, cds in enumerate(normalized_codes)}

    result = session.execute(text(f"""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'CA'
          AND state_district_id IN ({placeholders})
          AND id_system = 'st_leaid'
    """), params)

    # Build mapping
    cds_to_nces_map = {row[0]: row[1] for row in result.fetchall()}

    # Return with original keys
    return {cds: cds_to_nces_map.get(normalize_cds_code(cds)) for cds in cds_codes}


def extract_county_code(cds_code: str) -> str:
    """
    Extract county code from CDS code.

    Args:
        cds_code: CDS code (7 or 14 digits)

    Returns:
        2-digit county code

    Example:
        >>> extract_county_code("6275796")
        '62'
        >>> extract_county_code("62757960000000")
        '62'
    """
    normalized = normalize_cds_code(cds_code)
    return normalized[:2]


def extract_district_code(cds_code: str) -> str:
    """
    Extract district code from CDS code.

    Args:
        cds_code: CDS code (7 or 14 digits)

    Returns:
        5-digit district code

    Example:
        >>> extract_district_code("6275796")
        '75796'
        >>> extract_district_code("62757960000000")
        '75796'
    """
    normalized = normalize_cds_code(cds_code)
    return normalized[2:7]


# CLI testing
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Add project root to path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    from infrastructure.database.connection import session_scope

    print("NCES-to-CDS Crosswalk Utility - Interactive Test")
    print("=" * 60)

    # Test normalization
    print("\n1. Testing CDS code normalization:")
    test_codes = ["6275796", "62757960000000", "CA-6275796"]
    for code in test_codes:
        try:
            normalized = normalize_cds_code(code)
            st_leaid = cds_to_st_leaid(code)
            print(f"  {code:20s} -> {normalized} -> {st_leaid}")
        except ValueError as e:
            print(f"  {code:20s} -> ERROR: {e}")

    # Test database lookups
    print("\n2. Testing database lookups:")
    with session_scope() as session:
        # Get a sample California district
        ca_districts = session.query(District).filter(
            District.state == "CA",
            District.st_leaid.isnot(None)
        ).limit(5).all()

        if ca_districts:
            print(f"\n   Found {len(ca_districts)} sample CA districts:")
            for dist in ca_districts:
                if dist.st_leaid:
                    cds = st_leaid_to_cds(dist.st_leaid)
                    print(f"   {dist.nces_id} ({dist.st_leaid}) -> CDS: {cds}")
                    print(f"   {dist.name[:50]:50s} | Enrollment: {dist.enrollment}")

                    # Test reverse lookup
                    found_nces = cds_to_nces(cds, session)
                    if found_nces == dist.nces_id:
                        print(f"   ✓ Reverse lookup verified")
                    else:
                        print(f"   ✗ Reverse lookup failed: {found_nces} != {dist.nces_id}")
                    print()
        else:
            print("   No California districts found with ST_LEAID")

    print("\n3. Testing bulk conversion:")
    with session_scope() as session:
        # Get first 10 CA districts
        ca_dists = session.query(District).filter(
            District.state == "CA",
            District.st_leaid.isnot(None)
        ).limit(10).all()

        if ca_dists:
            cds_codes = [st_leaid_to_cds(d.st_leaid) for d in ca_dists if d.st_leaid]
            mapping = bulk_cds_to_nces(cds_codes, session)
            print(f"   Converted {len(mapping)} CDS codes:")
            for cds, nces in list(mapping.items())[:5]:
                print(f"   {cds} -> {nces}")

    print("\n" + "=" * 60)
    print("Crosswalk utility test complete!")
