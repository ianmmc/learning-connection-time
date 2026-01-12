#!/usr/bin/env python3
"""
Import California LCFF (Local Control Funding Formula) data.

Populates both:
1. district_funding table (generic multi-state funding)
2. ca_lcff_funding table (California-specific LCFF details)

Data Source: CA CDE LCFF Summary Data
File: data/raw/state/california/2023_24/lcff_2023_24.xlsx
Format: Excel with multiple sheets (using AN R1 - First Annual Recertification)
"""

import sys
from pathlib import Path
import pandas as pd
from typing import Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import DistrictFunding, CALCFFFunding
from infrastructure.utilities.nces_cds_crosswalk import cds_to_nces


def load_lcff_data(file_path: Path) -> pd.DataFrame:
    """Load CA LCFF data from Excel file."""
    print(f"Loading LCFF data from: {file_path}")

    # Use AN R1 (First Annual Recertification) sheet - most recent data
    # Header is on row 6 (0-indexed row 5)
    df = pd.read_excel(
        file_path,
        sheet_name='LCFF Summary 23-24 AN R1',
        header=5,
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
    """Filter to district-level records only."""
    print("\nFiltering to district-level records...")

    # District-level records have School Code = '0000000'
    district_df = df[df['School Code'] == '0000000'].copy()

    print(f"  District-level records: {len(district_df):,}")

    return district_df


def build_cds_code(row: pd.Series) -> str:
    """Build 7-digit CDS code from County Code and District Code."""
    county = str(row['County Code']).strip().zfill(2)
    district = str(row['District Code']).strip().zfill(5)
    return county + district


def import_lcff_record(row: pd.Series, session, year: str = "2023-24") -> Tuple[Optional[DistrictFunding], Optional[CALCFFFunding]]:
    """
    Import a single LCFF record.

    Returns:
        Tuple of (DistrictFunding, CALCFFFunding) if successful, (None, None) if crosswalk failed
    """
    # Build CDS code
    cds_code = build_cds_code(row)

    # Get NCES ID via crosswalk
    nces_id = cds_to_nces(cds_code, session)

    if not nces_id:
        return None, None

    # Parse numeric values
    def safe_float(value):
        if pd.isna(value) or value == 0:
            return None
        return float(value)

    # LCFF components
    base_grant = safe_float(row.get('LCFF Base Grant + NSS Allowance'))
    supplemental_grant = safe_float(row.get('Total LCFF Supplemental Grant'))
    concentration_grant = safe_float(row.get('Total LCFF Concentration Grant'))
    total_lcff = safe_float(row.get('Total LCFF Entitlement'))

    # Funded ADA
    total_ada = safe_float(row.get('Total Funded ADA or Alternative Education Grant ADA'))
    ada_tk_3 = safe_float(row.get('Funded TK/K-3 ADA'))
    ada_4_6 = safe_float(row.get('Funded 4 - 6 ADA'))
    ada_7_8 = safe_float(row.get('Funded 7 - 8 ADA'))
    ada_9_12 = safe_float(row.get('Funded 9 - 12 ADA'))

    # Skip if no funding data
    if total_lcff is None:
        return None, None

    # Create generic DistrictFunding record
    funding_record = DistrictFunding(
        nces_id=nces_id,
        year=year,
        state="CA",

        # State funding
        state_formula_type="LCFF",
        base_allocation=base_grant,
        equity_adjustment=(supplemental_grant or 0) + (concentration_grant or 0) if (supplemental_grant or concentration_grant) else None,
        equity_adjustment_type="Supplemental + Concentration Grants",
        total_state_funding=total_lcff,

        # Source documentation
        data_source="ca_cde_lcff",
        source_url="https://www.cde.ca.gov/fg/aa/pa/lcffsumdata.asp",
        fiscal_year="2023-24",

        notes=f"LEA: {row.get('Local Educational Agency ', 'Unknown')}"
    )

    # Create California-specific CALCFFFunding record
    lcff_record = CALCFFFunding(
        nces_id=nces_id,
        year=year,

        # LCFF Components
        base_grant=base_grant,
        supplemental_grant=supplemental_grant,
        concentration_grant=concentration_grant,
        total_lcff=total_lcff,

        # Funded ADA
        funded_ada=total_ada,

        # Grade span breakdowns
        base_tk_3=ada_tk_3,
        base_4_6=ada_4_6,
        base_7_8=ada_7_8,
        base_9_12=ada_9_12,

        # Source
        data_source="ca_cde_lcff",
        source_url="https://www.cde.ca.gov/fg/aa/pa/lcffsumdata.asp"
    )

    return funding_record, lcff_record


def import_ca_lcff(file_path: Path, year: str = "2023-24"):
    """
    Import California LCFF data.

    Args:
        file_path: Path to lcff_2023_24.xlsx file
        year: School year (default: "2023-24")
    """
    print("=" * 70)
    print("California LCFF Import")
    print("=" * 70)

    # Load data
    df = load_lcff_data(file_path)

    # Filter to district level
    district_df = filter_district_level(df)

    # Import records
    print("\nImporting records...")

    imported_count = 0
    failed_count = 0
    skipped_count = 0
    failed_districts = []

    with session_scope() as session:
        # Clear existing records for this year
        deleted_funding = session.query(DistrictFunding).filter(
            DistrictFunding.year == year,
            DistrictFunding.data_source == "ca_cde_lcff"
        ).delete()
        deleted_lcff = session.query(CALCFFFunding).filter(
            CALCFFFunding.year == year
        ).delete()
        print(f"  Deleted {deleted_funding} existing DistrictFunding records")
        print(f"  Deleted {deleted_lcff} existing CALCFFFunding records")

        for idx, row in district_df.iterrows():
            funding_record, lcff_record = import_lcff_record(row, session, year)

            if funding_record and lcff_record:
                session.add(funding_record)
                session.add(lcff_record)
                imported_count += 1

                if imported_count % 100 == 0:
                    print(f"  Imported {imported_count} districts...")
                    session.flush()
            elif build_cds_code(row):
                # Check if it was skipped (no funding) or failed (no NCES match)
                if pd.notna(row.get('Total LCFF Entitlement')) and row.get('Total LCFF Entitlement') > 0:
                    failed_count += 1
                    cds_code = build_cds_code(row)
                    lea_name = row.get('Local Educational Agency ', 'Unknown')
                    failed_districts.append((cds_code, lea_name))
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
    print(f"Skipped (no funding data): {skipped_count:,}")

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
        total_funding = session.query(DistrictFunding).filter(
            DistrictFunding.year == year,
            DistrictFunding.data_source == "ca_cde_lcff"
        ).count()

        total_lcff = session.query(CALCFFFunding).filter(
            CALCFFFunding.year == year
        ).count()

        # Sample records
        samples = session.query(CALCFFFunding).filter(
            CALCFFFunding.year == year
        ).order_by(CALCFFFunding.total_lcff.desc()).limit(5).all()

        print(f"DistrictFunding records: {total_funding:,}")
        print(f"CALCFFFunding records: {total_lcff:,}")
        print(f"\nSample records (highest funding):")
        for record in samples:
            print(f"  NCES {record.nces_id}")
            print(f"    Total LCFF: ${record.total_lcff:,.0f}")
            print(f"    Base Grant: ${record.base_grant:,.0f}" if record.base_grant else "    Base Grant: None")
            print(f"    Supplemental: ${record.supplemental_grant:,.0f}" if record.supplemental_grant else "    Supplemental: None")
            print(f"    Concentration: ${record.concentration_grant:,.0f}" if record.concentration_grant else "    Concentration: None")
            print(f"    Funded ADA: {record.funded_ada:,.1f}" if record.funded_ada else "    Funded ADA: None")
            print()

    print("=" * 70)
    print("✓ Import complete!")
    print("=" * 70)


def main():
    """Main import function."""
    # Default file path
    file_path = project_root / "data" / "raw" / "state" / "california" / "2023_24" / "lcff_2023_24.xlsx"

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    import_ca_lcff(file_path)


if __name__ == "__main__":
    main()
