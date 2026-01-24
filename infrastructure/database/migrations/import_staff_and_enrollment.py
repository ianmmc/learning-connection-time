#!/usr/bin/env python3
"""
Import NCES CCD staff counts and grade-level enrollment data.

This script:
1. Reads the NCES CCD staff file (long format) and pivots to wide format
2. Reads the NCES CCD membership file and aggregates enrollment by grade
3. Imports data into staff_counts and enrollment_by_grade tables
4. Populates staff_counts_effective with calculated scope values

Usage:
    python import_staff_and_enrollment.py [--year 2023-24]

Reference: docs/STAFFING_DATA_ENHANCEMENT_PLAN.md
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope, get_engine
from infrastructure.database.models import (
    District,
    StaffCounts,
    StaffCountsEffective,
    EnrollmentByGrade,
    DataLineage,
)


# NCES Staff Category Mappings (from staff file STAFF column to our schema)
STAFF_CATEGORY_MAPPING = {
    # Tier 1: Classroom Teachers
    "Teachers": "teachers_total",
    "Elementary Teachers": "teachers_elementary",
    "Kindergarten Teachers": "teachers_kindergarten",
    "Secondary Teachers": "teachers_secondary",
    "Pre-kindergarten Teachers": "teachers_prek",
    "Ungraded Teachers": "teachers_ungraded",

    # Tier 2: Instructional Support
    "Instructional Coordinators and Supervisors to the Staff": "instructional_coordinators",
    "Librarians/media specialists": "librarians",
    "Library/Media Support Staff": "library_support",
    "Paraprofessionals/Instructional Aides": "paraprofessionals",

    # Tier 3: Student Support
    "Guidance Counselors": "counselors_total",
    "Elementary School Counselors": "counselors_elementary",
    "Secondary School Counselors": "counselors_secondary",
    "School Psychologists": "psychologists",
    "Student Support Services Staff (w/o Psychology)": "student_support_services",

    # Tier 4: Administrative
    "LEA Administrators": "lea_administrators",
    "School administrators": "school_administrators",
    "LEA Administrative Support Staff": "lea_admin_support",
    "School Administrative Support Staff": "school_admin_support",

    # Aggregates
    "LEA Staff": "lea_staff_total",
    "School Staff": "school_staff_total",
    "Other Staff": "other_staff",
    "All Other Support Staff": "all_other_support_staff",
}

# Grade level mappings (from membership file GRADE column to our schema)
GRADE_MAPPING = {
    "Pre-Kindergarten": "enrollment_prek",
    "Kindergarten": "enrollment_kindergarten",
    "Grade 1": "enrollment_grade_1",
    "Grade 2": "enrollment_grade_2",
    "Grade 3": "enrollment_grade_3",
    "Grade 4": "enrollment_grade_4",
    "Grade 5": "enrollment_grade_5",
    "Grade 6": "enrollment_grade_6",
    "Grade 7": "enrollment_grade_7",
    "Grade 8": "enrollment_grade_8",
    "Grade 9": "enrollment_grade_9",
    "Grade 10": "enrollment_grade_10",
    "Grade 11": "enrollment_grade_11",
    "Grade 12": "enrollment_grade_12",
    "Grade 13": "enrollment_grade_13",
    "Ungraded": "enrollment_ungraded",
    "Adult Education": "enrollment_adult_ed",
}


def load_staff_data(staff_file: Path, year: str) -> pd.DataFrame:
    """
    Load and pivot NCES CCD staff data from long to wide format.

    Args:
        staff_file: Path to the staff CSV file
        year: School year (e.g., "2023-24")

    Returns:
        DataFrame with one row per district and staff categories as columns
    """
    print(f"Loading staff data from {staff_file}...")

    # Read the file
    df = pd.read_csv(staff_file, dtype={"LEAID": str})

    print(f"  Loaded {len(df):,} rows")

    # Filter to only rows we can map
    df = df[df["STAFF"].isin(STAFF_CATEGORY_MAPPING.keys())]
    print(f"  {len(df):,} rows after filtering to mapped categories")

    # Map category names to our column names
    df["category"] = df["STAFF"].map(STAFF_CATEGORY_MAPPING)

    # Pivot to wide format
    pivot_df = df.pivot_table(
        index="LEAID",
        columns="category",
        values="STAFF_COUNT",
        aggfunc="sum"  # In case of duplicates
    ).reset_index()

    # Rename LEAID to district_id
    pivot_df = pivot_df.rename(columns={"LEAID": "district_id"})

    # Normalize district_id: strip leading zeros to match Districts table format
    # NCES files sometimes have 7-char LEAIDs (0600001) but Districts uses 6-char (600001)
    pivot_df["district_id"] = pivot_df["district_id"].apply(lambda x: str(int(x)) if x else x)

    # Add metadata columns
    pivot_df["source_year"] = year
    pivot_df["data_source"] = "nces_ccd"

    print(f"  Pivoted to {len(pivot_df):,} districts")

    return pivot_df


def load_enrollment_data(membership_file: Path, year: str) -> pd.DataFrame:
    """
    Load and aggregate NCES CCD membership data by grade.

    Args:
        membership_file: Path to the membership CSV file
        year: School year (e.g., "2023-24")

    Returns:
        DataFrame with one row per district and enrollment by grade
    """
    print(f"Loading enrollment data from {membership_file}...")

    # Read the file
    df = pd.read_csv(membership_file, dtype={"LEAID": str})

    print(f"  Loaded {len(df):,} rows")

    # Filter to only rows we can map
    df = df[df["GRADE"].isin(GRADE_MAPPING.keys())]
    print(f"  {len(df):,} rows after filtering to mapped grades")

    # CRITICAL: Exclude "No Category Codes" rows - these are subtotals that would double-count
    # The file has both detailed (race × sex) rows AND "Subtotal 4 - By Grade" rows
    df = df[df["RACE_ETHNICITY"] != "No Category Codes"]
    print(f"  {len(df):,} rows after excluding subtotal rows")

    # Map grade names to our column names
    df["grade_column"] = df["GRADE"].map(GRADE_MAPPING)

    # Aggregate by district and grade (sum across race/ethnicity and sex)
    agg_df = df.groupby(["LEAID", "grade_column"])["STUDENT_COUNT"].sum().reset_index()

    # Pivot to wide format
    pivot_df = agg_df.pivot_table(
        index="LEAID",
        columns="grade_column",
        values="STUDENT_COUNT",
        aggfunc="sum"
    ).reset_index()

    # Rename LEAID to district_id
    pivot_df = pivot_df.rename(columns={"LEAID": "district_id"})

    # Normalize district_id: strip leading zeros to match Districts table format
    # NCES files sometimes have 7-char LEAIDs (0600001) but Districts uses 6-char (600001)
    pivot_df["district_id"] = pivot_df["district_id"].apply(lambda x: str(int(x)) if x else x)

    # Calculate totals
    grade_columns = [col for col in pivot_df.columns if col.startswith("enrollment_")]
    pivot_df["enrollment_total"] = pivot_df[grade_columns].sum(axis=1)

    # Calculate K-12 (total minus Pre-K)
    prek_col = "enrollment_prek"
    if prek_col in pivot_df.columns:
        pivot_df["enrollment_k12"] = pivot_df["enrollment_total"] - pivot_df[prek_col].fillna(0)
    else:
        pivot_df["enrollment_k12"] = pivot_df["enrollment_total"]

    # Add metadata columns
    pivot_df["source_year"] = year
    pivot_df["data_source"] = "nces_ccd"

    print(f"  Aggregated to {len(pivot_df):,} districts")

    return pivot_df


def import_staff_counts(staff_df: pd.DataFrame, session) -> int:
    """
    Import staff counts to database.

    Args:
        staff_df: DataFrame with staff counts
        session: SQLAlchemy session

    Returns:
        Number of records imported
    """
    print("Importing staff counts to database...")

    # Get existing district IDs
    existing_districts = {d.nces_id for d in session.query(District.nces_id).all()}

    # Filter to only districts that exist
    staff_df = staff_df[staff_df["district_id"].isin(existing_districts)]
    print(f"  {len(staff_df):,} districts match existing records")

    imported = 0
    batch_size = 1000

    for i in range(0, len(staff_df), batch_size):
        batch = staff_df.iloc[i:i+batch_size]

        for _, row in batch.iterrows():
            staff_count = StaffCounts(
                district_id=row["district_id"],
                source_year=row["source_year"],
                data_source=row["data_source"],
                # Tier 1
                teachers_total=row.get("teachers_total"),
                teachers_elementary=row.get("teachers_elementary"),
                teachers_kindergarten=row.get("teachers_kindergarten"),
                teachers_secondary=row.get("teachers_secondary"),
                teachers_prek=row.get("teachers_prek"),
                teachers_ungraded=row.get("teachers_ungraded"),
                # Tier 2
                instructional_coordinators=row.get("instructional_coordinators"),
                librarians=row.get("librarians"),
                library_support=row.get("library_support"),
                paraprofessionals=row.get("paraprofessionals"),
                # Tier 3
                counselors_total=row.get("counselors_total"),
                counselors_elementary=row.get("counselors_elementary"),
                counselors_secondary=row.get("counselors_secondary"),
                psychologists=row.get("psychologists"),
                student_support_services=row.get("student_support_services"),
                # Tier 4
                lea_administrators=row.get("lea_administrators"),
                school_administrators=row.get("school_administrators"),
                lea_admin_support=row.get("lea_admin_support"),
                school_admin_support=row.get("school_admin_support"),
                # Aggregates
                lea_staff_total=row.get("lea_staff_total"),
                school_staff_total=row.get("school_staff_total"),
                other_staff=row.get("other_staff"),
                all_other_support_staff=row.get("all_other_support_staff"),
            )
            session.merge(staff_count)
            imported += 1

        session.flush()
        print(f"  Processed {min(i+batch_size, len(staff_df)):,} / {len(staff_df):,}")

    session.commit()
    print(f"  Imported {imported:,} staff count records")
    return imported


def import_enrollment_data(enrollment_df: pd.DataFrame, session) -> int:
    """
    Import enrollment by grade to database.

    Args:
        enrollment_df: DataFrame with enrollment data
        session: SQLAlchemy session

    Returns:
        Number of records imported
    """
    print("Importing enrollment data to database...")

    # Get existing district IDs
    existing_districts = {d.nces_id for d in session.query(District.nces_id).all()}

    # Filter to only districts that exist
    enrollment_df = enrollment_df[enrollment_df["district_id"].isin(existing_districts)]
    print(f"  {len(enrollment_df):,} districts match existing records")

    imported = 0
    batch_size = 1000

    for i in range(0, len(enrollment_df), batch_size):
        batch = enrollment_df.iloc[i:i+batch_size]

        for _, row in batch.iterrows():
            enrollment = EnrollmentByGrade(
                district_id=row["district_id"],
                source_year=row["source_year"],
                data_source=row["data_source"],
                enrollment_prek=int(row["enrollment_prek"]) if pd.notna(row.get("enrollment_prek")) else None,
                enrollment_kindergarten=int(row["enrollment_kindergarten"]) if pd.notna(row.get("enrollment_kindergarten")) else None,
                enrollment_grade_1=int(row["enrollment_grade_1"]) if pd.notna(row.get("enrollment_grade_1")) else None,
                enrollment_grade_2=int(row["enrollment_grade_2"]) if pd.notna(row.get("enrollment_grade_2")) else None,
                enrollment_grade_3=int(row["enrollment_grade_3"]) if pd.notna(row.get("enrollment_grade_3")) else None,
                enrollment_grade_4=int(row["enrollment_grade_4"]) if pd.notna(row.get("enrollment_grade_4")) else None,
                enrollment_grade_5=int(row["enrollment_grade_5"]) if pd.notna(row.get("enrollment_grade_5")) else None,
                enrollment_grade_6=int(row["enrollment_grade_6"]) if pd.notna(row.get("enrollment_grade_6")) else None,
                enrollment_grade_7=int(row["enrollment_grade_7"]) if pd.notna(row.get("enrollment_grade_7")) else None,
                enrollment_grade_8=int(row["enrollment_grade_8"]) if pd.notna(row.get("enrollment_grade_8")) else None,
                enrollment_grade_9=int(row["enrollment_grade_9"]) if pd.notna(row.get("enrollment_grade_9")) else None,
                enrollment_grade_10=int(row["enrollment_grade_10"]) if pd.notna(row.get("enrollment_grade_10")) else None,
                enrollment_grade_11=int(row["enrollment_grade_11"]) if pd.notna(row.get("enrollment_grade_11")) else None,
                enrollment_grade_12=int(row["enrollment_grade_12"]) if pd.notna(row.get("enrollment_grade_12")) else None,
                enrollment_grade_13=int(row["enrollment_grade_13"]) if pd.notna(row.get("enrollment_grade_13")) else None,
                enrollment_ungraded=int(row["enrollment_ungraded"]) if pd.notna(row.get("enrollment_ungraded")) else None,
                enrollment_adult_ed=int(row["enrollment_adult_ed"]) if pd.notna(row.get("enrollment_adult_ed")) else None,
                enrollment_total=int(row["enrollment_total"]) if pd.notna(row.get("enrollment_total")) else None,
                enrollment_k12=int(row["enrollment_k12"]) if pd.notna(row.get("enrollment_k12")) else None,
            )

            # Calculate aggregate columns from individual grades
            # Elementary = K-5
            elem_grades = ['enrollment_kindergarten', 'enrollment_grade_1', 'enrollment_grade_2',
                          'enrollment_grade_3', 'enrollment_grade_4', 'enrollment_grade_5']
            enrollment.enrollment_elementary = sum(
                int(row.get(g, 0)) if pd.notna(row.get(g)) else 0 for g in elem_grades
            )

            # Secondary = 6-12
            sec_grades = ['enrollment_grade_6', 'enrollment_grade_7', 'enrollment_grade_8',
                         'enrollment_grade_9', 'enrollment_grade_10', 'enrollment_grade_11', 'enrollment_grade_12']
            enrollment.enrollment_secondary = sum(
                int(row.get(g, 0)) if pd.notna(row.get(g)) else 0 for g in sec_grades
            )

            session.merge(enrollment)
            imported += 1

        session.flush()
        print(f"  Processed {min(i+batch_size, len(enrollment_df)):,} / {len(enrollment_df):,}")

    session.commit()
    print(f"  Imported {imported:,} enrollment records")
    return imported


def populate_effective_staff_counts(session, year: str) -> int:
    """
    Populate staff_counts_effective table with calculated scope values.

    Args:
        session: SQLAlchemy session
        year: School year to use as effective year

    Returns:
        Number of records created
    """
    print("Populating effective staff counts with scope calculations...")

    # Get all staff counts for the year
    staff_counts = session.query(StaffCounts).filter(
        StaffCounts.source_year == year,
        StaffCounts.data_source == "nces_ccd"
    ).all()

    print(f"  Found {len(staff_counts):,} staff count records for {year}")

    created = 0

    for sc in staff_counts:
        # Create or update effective record
        effective = StaffCountsEffective(
            district_id=sc.district_id,
            effective_year=year,
            primary_source="nces_ccd",
            sources_used=[{"source": "nces_ccd", "year": year}],
            # Copy all staff counts
            teachers_total=sc.teachers_total,
            teachers_elementary=sc.teachers_elementary,
            teachers_kindergarten=sc.teachers_kindergarten,
            teachers_secondary=sc.teachers_secondary,
            teachers_prek=sc.teachers_prek,
            teachers_ungraded=sc.teachers_ungraded,
            instructional_coordinators=sc.instructional_coordinators,
            librarians=sc.librarians,
            library_support=sc.library_support,
            paraprofessionals=sc.paraprofessionals,
            counselors_total=sc.counselors_total,
            counselors_elementary=sc.counselors_elementary,
            counselors_secondary=sc.counselors_secondary,
            psychologists=sc.psychologists,
            student_support_services=sc.student_support_services,
            lea_administrators=sc.lea_administrators,
            school_administrators=sc.school_administrators,
            lea_admin_support=sc.lea_admin_support,
            school_admin_support=sc.school_admin_support,
            lea_staff_total=sc.lea_staff_total,
            school_staff_total=sc.school_staff_total,
            other_staff=sc.other_staff,
        )

        # Calculate scope values
        effective.calculate_scopes()

        session.merge(effective)
        created += 1

        if created % 1000 == 0:
            session.flush()
            print(f"  Processed {created:,} / {len(staff_counts):,}")

    session.commit()
    print(f"  Created {created:,} effective staff count records")
    return created


def main():
    parser = argparse.ArgumentParser(description="Import NCES CCD staff and enrollment data")
    parser.add_argument("--year", default="2023-24", help="School year (e.g., 2023-24)")
    parser.add_argument("--staff-file", type=Path, help="Path to staff CSV file")
    parser.add_argument("--enrollment-file", type=Path, help="Path to membership CSV file")
    args = parser.parse_args()

    # Default file paths
    data_dir = project_root / "data" / "raw" / "federal" / "nces-ccd" / args.year.replace("-", "_")

    staff_file = args.staff_file or data_dir / "ccd_lea_059_2324_l_1a_073124.csv"
    enrollment_file = args.enrollment_file or data_dir / "ccd_lea_052_2324_l_1a_073124.csv"

    # Verify files exist
    if not staff_file.exists():
        print(f"Error: Staff file not found: {staff_file}")
        sys.exit(1)

    if not enrollment_file.exists():
        print(f"Error: Enrollment file not found: {enrollment_file}")
        sys.exit(1)

    print(f"=" * 60)
    print(f"NCES CCD Staff and Enrollment Import")
    print(f"=" * 60)
    print(f"Year: {args.year}")
    print(f"Staff file: {staff_file}")
    print(f"Enrollment file: {enrollment_file}")
    print()

    # Load data
    staff_df = load_staff_data(staff_file, args.year)
    enrollment_df = load_enrollment_data(enrollment_file, args.year)

    print()

    # Import to database
    with session_scope() as session:
        # Import staff counts
        staff_imported = import_staff_counts(staff_df, session)

        # Import enrollment
        enrollment_imported = import_enrollment_data(enrollment_df, session)

        # Populate effective staff counts
        effective_created = populate_effective_staff_counts(session, args.year)

        # Log lineage
        DataLineage.log(
            session,
            entity_type="staff_counts",
            entity_id="bulk_import",
            operation="import",
            source_file=str(staff_file),
            details={
                "year": args.year,
                "staff_imported": staff_imported,
                "enrollment_imported": enrollment_imported,
                "effective_created": effective_created,
            },
            created_by="import_staff_and_enrollment.py"
        )

    print()
    print(f"=" * 60)
    print(f"IMPORT COMPLETE")
    print(f"=" * 60)
    print(f"Staff counts imported: {staff_imported:,}")
    print(f"Enrollment records imported: {enrollment_imported:,}")
    print(f"Effective staff counts created: {effective_created:,}")


if __name__ == "__main__":
    main()
