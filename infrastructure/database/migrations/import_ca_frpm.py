#!/usr/bin/env python3
"""
Import California FRPM (Free/Reduced-Price Meal) data into district_socioeconomic table.

Reads CA FRPM school-level data and aggregates to district level using NCES-CDS crosswalk
to populate socioeconomic indicators.

Data Source: CA CDE Free or Reduced-Price Meal Data
File: data/raw/state/california/2023_24/frpm_2023_24.xlsx
Format: Excel with header on row 2, data on sheet 2

Key Fields:
- Enrollment (K-12): Total enrollment
- FRPM Count (K-12): Free + Reduced eligible students
- Percent (%) Eligible FRPM (K-12): FRPM percentage
"""

import sys
from pathlib import Path
import pandas as pd
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import DistrictSocioeconomic
from infrastructure.utilities.nces_cds_crosswalk import cds_to_nces, normalize_cds_code


def load_frpm_data(file_path: Path) -> pd.DataFrame:
    """Load CA FRPM data from Excel file."""
    print(f"Loading FRPM data from: {file_path}")

    # Read Excel file - data is in sheet 2 with header on row 2
    df = pd.read_excel(
        file_path,
        sheet_name='FRPM School-Level Data',
        header=1,  # Header is on row 2 (0-indexed)
        dtype={
            'County Code': str,
            'District Code': str,
            'School Code': str,
        }
    )

    print(f"  Total records: {len(df):,}")
    print(f"  Columns: {len(df.columns)}")

    return df


def filter_district_level(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate school-level data to district level."""
    print("\nAggregating to district level...")

    # Group by County Code and District Code, summing numeric fields
    agg_dict = {
        'District Name': 'first',
        'Enrollment \n(K-12)': 'sum',
        'Free Meal \nCount \n(K-12)': 'sum',
        'FRPM Count \n(K-12)': 'sum',
        'CALPADS Fall 1 \nCertification Status': 'first',  # Keep first certification status
    }

    district_df = df.groupby(['County Code', 'District Code'], as_index=False).agg(agg_dict)

    # Calculate district-level FRPM percentage
    district_df['FRPM_Percent'] = (
        district_df['FRPM Count \n(K-12)'] / district_df['Enrollment \n(K-12)']
    ).fillna(0)

    print(f"  Unique districts: {len(district_df):,}")

    return district_df


def build_cds_code(row: pd.Series) -> str:
    """Build 7-digit CDS code from County Code and District Code."""
    county = str(row['County Code']).strip().zfill(2)
    district = str(row['District Code']).strip().zfill(5)
    return county + district


def import_frpm_record(row: pd.Series, session, year: str = "2023-24") -> Optional[DistrictSocioeconomic]:
    """
    Import a single FRPM record.

    Returns:
        DistrictSocioeconomic object if successful, None if crosswalk failed
    """
    # Build CDS code
    cds_code = build_cds_code(row)

    # Get NCES ID via crosswalk
    nces_id = cds_to_nces(cds_code, session)

    if not nces_id:
        return None

    # Parse values
    enrollment = int(row['Enrollment \n(K-12)']) if pd.notna(row['Enrollment \n(K-12)']) else None
    frpm_count = int(row['FRPM Count \n(K-12)']) if pd.notna(row['FRPM Count \n(K-12)']) else None
    frpm_percent = float(row['FRPM_Percent']) if pd.notna(row['FRPM_Percent']) else None

    # Skip if no data
    if enrollment is None or enrollment == 0:
        return None

    # Certification status
    cert_status = str(row['CALPADS Fall 1 \nCertification Status']).strip() if pd.notna(row['CALPADS Fall 1 \nCertification Status']) else None

    # Create record
    frpm_record = DistrictSocioeconomic(
        nces_id=nces_id,
        year=year,
        state="CA",

        # Core poverty indicator
        poverty_indicator_type="FRPM",
        poverty_percent=frpm_percent,
        poverty_count=frpm_count,
        enrollment=enrollment,

        # Source documentation
        data_source="ca_cde_frpm",
        source_url="https://www.cde.ca.gov/ds/ad/filessp.asp",
        collection_method="FRPM Census Day (First Wednesday in October)",

        # Quality tracking
        certification_status=cert_status,
        notes=f"District: {row.get('District Name', 'Unknown')}, Aggregated from school-level data"
    )

    return frpm_record


def import_ca_frpm(file_path: Path, year: str = "2023-24"):
    """
    Import California FRPM data.

    Args:
        file_path: Path to frpm_2023_24.xlsx file
        year: School year (default: "2023-24")
    """
    print("=" * 70)
    print("California FRPM Import")
    print("=" * 70)

    # Load data
    df = load_frpm_data(file_path)

    # Aggregate to district level
    district_df = filter_district_level(df)

    # Import records
    print("\nImporting records...")

    imported_count = 0
    failed_count = 0
    skipped_count = 0
    failed_districts = []

    with session_scope() as session:
        # Clear existing records for this year
        deleted = session.query(DistrictSocioeconomic).filter(
            DistrictSocioeconomic.year == year,
            DistrictSocioeconomic.poverty_indicator_type == "FRPM",
            DistrictSocioeconomic.data_source == "ca_cde_frpm"
        ).delete()
        print(f"  Deleted {deleted} existing FRPM records for {year}")

        for idx, row in district_df.iterrows():
            frpm_record = import_frpm_record(row, session, year)

            if frpm_record:
                session.add(frpm_record)
                imported_count += 1

                if imported_count % 100 == 0:
                    print(f"  Imported {imported_count} districts...")
                    session.flush()
            elif build_cds_code(row):
                # Check if it was skipped (no enrollment) or failed (no NCES match)
                if pd.notna(row['Enrollment \n(K-12)']) and row['Enrollment \n(K-12)'] > 0:
                    failed_count += 1
                    cds_code = build_cds_code(row)
                    district_name = row.get('District Name', 'Unknown')
                    failed_districts.append((cds_code, district_name))
                else:
                    skipped_count += 1

        session.commit()

    # Report results
    print("\n" + "=" * 70)
    print("Import Summary")
    print("=" * 70)
    print(f"Total district records processed: {len(district_df):,}")
    print(f"Successfully imported: {imported_count:,}")
    print(f"Failed (no NCES match): {failed_count:,}")
    print(f"Skipped (no enrollment): {skipped_count:,}")

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
        total_imported = session.query(DistrictSocioeconomic).filter(
            DistrictSocioeconomic.year == year,
            DistrictSocioeconomic.poverty_indicator_type == "FRPM"
        ).count()

        # Sample records
        samples = session.query(DistrictSocioeconomic).filter(
            DistrictSocioeconomic.year == year,
            DistrictSocioeconomic.poverty_indicator_type == "FRPM"
        ).order_by(DistrictSocioeconomic.poverty_percent.desc()).limit(5).all()

        print(f"Records in database: {total_imported:,}")
        print(f"\nSample records (highest poverty rates):")
        for record in samples:
            print(f"  NCES {record.nces_id} | {record.notes[:60]}")
            print(f"    Enrollment: {record.enrollment:,}")
            print(f"    FRPM Count: {record.poverty_count:,}")
            print(f"    FRPM %: {record.poverty_percent:.1%}")
            print()

    print("=" * 70)
    print("✓ Import complete!")
    print("=" * 70)


def main():
    """Main import function."""
    # Default file path
    file_path = project_root / "data" / "raw" / "state" / "california" / "2023_24" / "frpm_2023_24.xlsx"

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    import_ca_frpm(file_path)


if __name__ == "__main__":
    main()
