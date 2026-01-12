#!/usr/bin/env python3
"""
Import California SPED data into ca_sped_district_environments table.

Reads CA SPED educational environment data and uses NCES-CDS crosswalk
to populate district-level SPED enrollment by educational environment.

Data Source: CA CDE Special Education Enrollment by Educational Environment
File: data/raw/state/california/2023_24/sped_2023_24.txt
Format: Tab-delimited text with header row

Educational Environment Categories:
- PS_RCGT80_N: Mainstreamed (80%+ regular class)
- PS_RC4079_N: Mainstreamed (40-79% regular class)
- PS_RCL40_N: Self-contained (<40% regular class)
- PS_SSOS_N: Separate school/other settings
- PS_PSS_N: Preschool (Ages 3-5, excluded from K-12)
- PS_MUK_N: Missing/unreported
"""

import sys
from pathlib import Path
import pandas as pd
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import CASpedDistrictEnvironments
from infrastructure.utilities.nces_cds_crosswalk import cds_to_nces, normalize_cds_code


def load_sped_data(file_path: Path) -> pd.DataFrame:
    """Load CA SPED data from tab-delimited file."""
    print(f"Loading SPED data from: {file_path}")

    # Read tab-delimited file
    df = pd.read_csv(file_path, sep='\t', dtype=str)

    print(f"  Total records: {len(df):,}")
    print(f"  Columns: {len(df.columns)}")

    return df


def filter_district_level(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to district-level records and aggregate by CDS code."""
    print("\nFiltering to district-level records...")

    # District-level records have empty School Code
    district_df = df[df['School Code'].isna() | (df['School Code'] == '')].copy()

    # Filter out state-level totals (Aggregate Level = 'T')
    district_df = district_df[district_df['Aggregate Level'] != 'T'].copy()

    # Filter to TA (Total All) reporting category to get unduplicated totals
    district_df = district_df[district_df['ReportingCategory'] == 'TA'].copy()

    print(f"  District-level TA records: {len(district_df):,}")

    # Aggregate by district (sum counts across multiple programs/schools)
    print("\nAggregating by district...")

    agg_dict = {
        'District Name': 'first',  # Keep first district name
        'SPED_ENR_N': lambda x: pd.to_numeric(x, errors='coerce').sum(),
        'PS_RCGT80_N': lambda x: pd.to_numeric(x, errors='coerce').sum(),
        'PS_RC4079_N': lambda x: pd.to_numeric(x, errors='coerce').sum(),
        'PS_RCL40_N': lambda x: pd.to_numeric(x, errors='coerce').sum(),
        'PS_SSOS_N': lambda x: pd.to_numeric(x, errors='coerce').sum(),
        'PS_PSS_N': lambda x: pd.to_numeric(x, errors='coerce').sum(),
        'PS_MUK_N': lambda x: pd.to_numeric(x, errors='coerce').sum(),
    }

    aggregated_df = district_df.groupby(['County Code', 'District Code'], as_index=False).agg(agg_dict)

    print(f"  Unique districts after aggregation: {len(aggregated_df):,}")

    return aggregated_df


def build_cds_code(row: pd.Series) -> str:
    """Build 7-digit CDS code from County Code and District Code."""
    county = str(row['County Code']).strip().zfill(2)
    district = str(row['District Code']).strip().zfill(5)
    return county + district


def import_sped_record(row: pd.Series, session, year: str = "2023-24") -> Optional[CASpedDistrictEnvironments]:
    """
    Import a single SPED record.

    Returns:
        CASpedDistrictEnvironments object if successful, None if crosswalk failed
    """
    # Build CDS code
    cds_code = build_cds_code(row)

    # Get NCES ID via crosswalk
    nces_id = cds_to_nces(cds_code, session)

    if not nces_id:
        return None

    # Parse enrollment counts (already converted to numeric during aggregation)
    def safe_int(value):
        if pd.isna(value) or value == 0:
            return None
        return int(value)

    sped_total = safe_int(row.get('SPED_ENR_N'))
    mainstreamed_80_plus = safe_int(row.get('PS_RCGT80_N'))
    mainstreamed_40_79 = safe_int(row.get('PS_RC4079_N'))
    self_contained_lt_40 = safe_int(row.get('PS_RCL40_N'))
    separate_school = safe_int(row.get('PS_SSOS_N'))
    preschool = safe_int(row.get('PS_PSS_N'))
    missing = safe_int(row.get('PS_MUK_N'))

    # Calculate aggregates
    mainstreamed = None
    if mainstreamed_80_plus is not None and mainstreamed_40_79 is not None:
        mainstreamed = mainstreamed_80_plus + mainstreamed_40_79

    self_contained = None
    if self_contained_lt_40 is not None and separate_school is not None:
        self_contained = self_contained_lt_40 + separate_school

    # Create record
    sped_env = CASpedDistrictEnvironments(
        nces_id=nces_id,
        cds_code=cds_code,
        year=year,
        data_source="ca_cde_sped",

        # Totals
        sped_enrollment_total=sped_total,

        # Mainstreamed
        sped_mainstreamed=mainstreamed,
        sped_mainstreamed_80_plus=mainstreamed_80_plus,
        sped_mainstreamed_40_79=mainstreamed_40_79,

        # Self-contained
        sped_self_contained=self_contained,
        sped_self_contained_lt_40=self_contained_lt_40,
        sped_separate_school=separate_school,

        # Other
        sped_preschool=preschool,
        sped_missing=missing,

        # Quality
        confidence="high",
        notes=f"District: {row.get('District Name', 'Unknown')}"
    )

    # Calculate proportion
    sped_env.calculate_proportion()

    return sped_env


def import_ca_sped(file_path: Path, year: str = "2023-24"):
    """
    Import California SPED data.

    Args:
        file_path: Path to sped_2023_24.txt file
        year: School year (default: "2023-24")
    """
    print("=" * 70)
    print("California SPED Import")
    print("=" * 70)

    # Load data
    df = load_sped_data(file_path)

    # Filter to district level
    district_df = filter_district_level(df)

    # Import records
    print("\nImporting records...")

    imported_count = 0
    failed_count = 0
    failed_districts = []

    with session_scope() as session:
        # Clear existing records for this year
        deleted = session.query(CASpedDistrictEnvironments).filter(
            CASpedDistrictEnvironments.year == year
        ).delete()
        print(f"  Deleted {deleted} existing records for {year}")

        for idx, row in district_df.iterrows():
            sped_record = import_sped_record(row, session, year)

            if sped_record:
                session.add(sped_record)
                imported_count += 1

                if imported_count % 100 == 0:
                    print(f"  Imported {imported_count} districts...")
                    session.flush()
            else:
                failed_count += 1
                cds_code = build_cds_code(row)
                district_name = row.get('District Name', 'Unknown')
                failed_districts.append((cds_code, district_name))

        session.commit()

    # Report results
    print("\n" + "=" * 70)
    print("Import Summary")
    print("=" * 70)
    print(f"Total district records processed: {len(district_df):,}")
    print(f"Successfully imported: {imported_count:,}")
    print(f"Failed (no NCES match): {failed_count:,}")

    if failed_count > 0:
        print(f"\nSample failed districts (first 10):")
        for cds, name in failed_districts[:10]:
            print(f"  CDS {cds}: {name[:50]}")

    # Validation statistics
    print("\n" + "=" * 70)
    print("Validation Statistics")
    print("=" * 70)

    with session_scope() as session:
        # Count records
        total_imported = session.query(CASpedDistrictEnvironments).filter(
            CASpedDistrictEnvironments.year == year
        ).count()

        # Sample records
        samples = session.query(CASpedDistrictEnvironments).filter(
            CASpedDistrictEnvironments.year == year
        ).limit(5).all()

        print(f"Records in database: {total_imported:,}")
        print(f"\nSample records:")
        for record in samples:
            print(f"  NCES {record.nces_id} (CDS {record.cds_code})")
            print(f"    Total SPED: {record.sped_enrollment_total:,}")
            print(f"    Mainstreamed: {record.sped_mainstreamed} ({record.sped_mainstreamed_80_plus} + {record.sped_mainstreamed_40_79})")
            print(f"    Self-contained: {record.sped_self_contained} ({record.sped_self_contained_lt_40} + {record.sped_separate_school})")
            if record.self_contained_proportion:
                print(f"    Self-contained %: {record.self_contained_proportion:.2%}")
            print()

    print("=" * 70)
    print("✓ Import complete!")
    print("=" * 70)


def main():
    """Main import function."""
    # Default file path
    file_path = project_root / "data" / "raw" / "state" / "california" / "2023_24" / "sped_2023_24.txt"

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    import_ca_sped(file_path)


if __name__ == "__main__":
    main()
