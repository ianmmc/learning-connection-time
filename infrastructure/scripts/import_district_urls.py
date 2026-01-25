#!/usr/bin/env python3
"""
Import district website URLs and grade span from NCES CCD data into the database.

This script reads the NCES CCD LEA (Local Education Agency) data file and
updates the districts table with:
- website_url: District website for enrichment pipeline
- grade_span_low: Lowest grade offered (PK, KG, 01-12)
- grade_span_high: Highest grade offered (PK, KG, 01-12)

Usage:
    python infrastructure/scripts/import_district_urls.py [--dry-run]
    python infrastructure/scripts/import_district_urls.py --grade-span-only [--dry-run]
"""

import argparse
import csv
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from infrastructure.database.connection import session_scope


# NCES CCD file path (2023-24 data)
NCES_CCD_FILE = project_root / "data/raw/federal/nces-ccd/2023_24/ccd_lea_029_2324_w_1a_073124.csv"

# Column indices (0-based)
LEAID_COL = 8     # Column 9 in 1-based indexing
WEBSITE_COL = 24  # Column 25 in 1-based indexing
GSLO_COL = 53     # Column 54 - Grade Span Low (PK, KG, 01-12)
GSHI_COL = 54     # Column 55 - Grade Span High (PK, KG, 01-12)


def normalize_url(url: str) -> str:
    """Normalize a URL for consistency."""
    if not url or url.strip() in ('', 'N', 'NA', 'n/a', '-'):
        return None

    url = url.strip()

    # Add https:// if no protocol
    if url and not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Remove trailing slashes for consistency
    url = url.rstrip('/')

    return url


def normalize_nces_id(nces_id: str) -> str:
    """Normalize NCES ID to 7-digit format with leading zeros (NCES standard)."""
    if not nces_id:
        return None
    # Pad to 7 digits with leading zeros (NCES standard format)
    return nces_id.strip().zfill(7)


def load_urls_from_csv() -> dict:
    """Load NCES ID -> Website URL mapping from CSV."""
    urls = {}

    with open(NCES_CCD_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header

        for row in reader:
            if len(row) > max(LEAID_COL, WEBSITE_COL):
                leaid = normalize_nces_id(row[LEAID_COL].strip())
                website = normalize_url(row[WEBSITE_COL])

                if leaid and website:
                    urls[leaid] = website

    return urls


def normalize_grade(grade: str) -> str:
    """Normalize grade code for consistency."""
    if not grade or grade.strip() in ('', 'N', 'NA', 'n/a', '-', 'M'):
        return None
    grade = grade.strip().upper()
    # Ensure 2-digit format for numeric grades
    if grade.isdigit() and len(grade) == 1:
        grade = '0' + grade
    return grade


def load_grade_spans_from_csv() -> dict:
    """Load NCES ID -> (GSLO, GSHI) mapping from CSV."""
    grade_spans = {}

    with open(NCES_CCD_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header

        for row in reader:
            if len(row) > max(LEAID_COL, GSLO_COL, GSHI_COL):
                leaid = normalize_nces_id(row[LEAID_COL].strip())
                gslo = normalize_grade(row[GSLO_COL])
                gshi = normalize_grade(row[GSHI_COL])

                if leaid and gslo and gshi:
                    grade_spans[leaid] = (gslo, gshi)

    return grade_spans


def import_urls(dry_run: bool = False):
    """Import URLs into the database."""
    print(f"Loading URLs from: {NCES_CCD_FILE}")
    urls = load_urls_from_csv()
    print(f"Found {len(urls)} districts with valid website URLs in CSV")

    updated = 0
    not_found = 0
    already_set = 0

    with session_scope() as session:
        # Get all district IDs from database
        result = session.execute(text("SELECT nces_id, website_url FROM districts"))
        districts = {row[0]: row[1] for row in result}
        print(f"Found {len(districts)} districts in database")

        # Build batch update
        updates = []
        for nces_id, existing_url in districts.items():
            if nces_id in urls:
                new_url = urls[nces_id]
                if existing_url != new_url:
                    updates.append((new_url, nces_id))
                    updated += 1
                else:
                    already_set += 1
            else:
                not_found += 1

        # Execute batch update
        if not dry_run and updates:
            for url, nces_id in updates:
                session.execute(
                    text("UPDATE districts SET website_url = :url WHERE nces_id = :id"),
                    {"url": url, "id": nces_id}
                )
            session.commit()
            print(f"Committed {len(updates)} updates")
        elif dry_run:
            print(f"DRY RUN - would update {len(updates)} districts")

    # Summary
    print("\n--- Import Summary ---")
    print(f"Districts in database: {len(districts)}")
    print(f"URLs found in CSV: {len(urls)}")
    print(f"Updated: {updated}")
    print(f"Already had URL: {already_set}")
    print(f"No URL in CSV: {not_found}")

    # Sample of updated URLs
    if updates and not dry_run:
        print("\nSample updated URLs:")
        for url, nces_id in updates[:5]:
            print(f"  {nces_id}: {url}")


def import_grade_spans(dry_run: bool = False):
    """Import grade spans into the database."""
    print(f"Loading grade spans from: {NCES_CCD_FILE}")
    grade_spans = load_grade_spans_from_csv()
    print(f"Found {len(grade_spans)} districts with valid grade spans in CSV")

    updated = 0
    not_found = 0
    already_set = 0

    with session_scope() as session:
        # Get all district IDs from database
        result = session.execute(text("SELECT nces_id, grade_span_low, grade_span_high FROM districts"))
        districts = {row[0]: (row[1], row[2]) for row in result}
        print(f"Found {len(districts)} districts in database")

        # Build batch update
        updates = []
        for nces_id, (existing_low, existing_high) in districts.items():
            if nces_id in grade_spans:
                new_low, new_high = grade_spans[nces_id]
                if existing_low != new_low or existing_high != new_high:
                    updates.append((new_low, new_high, nces_id))
                    updated += 1
                else:
                    already_set += 1
            else:
                not_found += 1

        # Execute batch update
        if not dry_run and updates:
            for gslo, gshi, nces_id in updates:
                session.execute(
                    text("UPDATE districts SET grade_span_low = :gslo, grade_span_high = :gshi WHERE nces_id = :id"),
                    {"gslo": gslo, "gshi": gshi, "id": nces_id}
                )
            session.commit()
            print(f"Committed {len(updates)} updates")
        elif dry_run:
            print(f"DRY RUN - would update {len(updates)} districts")

    # Summary
    print("\n--- Grade Span Import Summary ---")
    print(f"Districts in database: {len(districts)}")
    print(f"Grade spans found in CSV: {len(grade_spans)}")
    print(f"Updated: {updated}")
    print(f"Already had grade span: {already_set}")
    print(f"No grade span in CSV: {not_found}")

    # Sample of updated grade spans
    if updates and not dry_run:
        print("\nSample updated grade spans:")
        for gslo, gshi, nces_id in updates[:5]:
            print(f"  {nces_id}: {gslo} - {gshi}")


def main():
    parser = argparse.ArgumentParser(description="Import district data from NCES CCD")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be updated without making changes")
    parser.add_argument('--grade-span-only', action='store_true', help="Only import grade spans, not URLs")
    parser.add_argument('--urls-only', action='store_true', help="Only import URLs, not grade spans")
    args = parser.parse_args()

    if args.grade_span_only:
        import_grade_spans(dry_run=args.dry_run)
    elif args.urls_only:
        import_urls(dry_run=args.dry_run)
    else:
        # Import both
        import_urls(dry_run=args.dry_run)
        print("\n" + "=" * 50 + "\n")
        import_grade_spans(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
