#!/usr/bin/env python3
"""
Import district website URLs from NCES CCD data into the database.

Reads the NCES CCD LEA (Local Education Agency) file and updates `districts.website_url`.

Vintage (#567): the file is DERIVED from `NCES_PRIMARY_YEAR` (the single hand-bumped vintage
authority in infrastructure/utilities/school_year.py) — this script was previously pinned to the
2023-24 file and got left behind when the 2024-25 CCD was ingested as primary, leaving 2,051
districts URL-less against a vintage the sampler had already rolled past. File resolution
(glob + exactly-one) raises FileNotFoundError, never SystemExit — a SystemExit slips past every
`except Exception` best-effort guard (the same lesson common/school_sampling._lea_file already
encodes; NOT reused directly because infrastructure.scripts must never import
infrastructure.acquisition — see pyproject.toml's layering contract). Called lazily at
report/import-urls time, not at module-import time. Columns are resolved BY HEADER NAME
(csv.DictReader), not position, so a layout shift in a future vintage fails loudly instead of
silently reading the wrong field.

Retention semantics (#567, Ian 2026-07-29): update-only, KEEP-LAST-KNOWN — a district absent from
the new vintage's file (or with a blank WEBSITE) simply retains its existing DB value; nothing is
ever blanked here. That is deliberate: URLs are transient by nature, and the durable record is the
extracted facts + captures + receipts (REQ-026/REQ-165), which persist regardless of URL
availability. A district that disappears from the NCES dataset entirely is a RETIREMENT question
(lct_db retire, gov_db records persist) — tracked separately as #699, not this script's job.

Grade-span import was REMOVED (#567, 2026-07-29 review): the live `districts` table carries no
grade_span_low/high columns — that half targeted a schema that no longer exists (grade spans are
read LIVE from the CCD by common/school_sampling), so a guard-and-skip would have kept ~90 lines of
permanently-dead code live. Deleted rather than guarded.

Usage:
    python infrastructure/scripts/import_district_urls.py [--dry-run]
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
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR


def nces_ccd_lea_file(primary_year: str = NCES_PRIMARY_YEAR) -> Path:
    """The LEA directory file (ccd_lea_029) for the given NCES vintage ('2024-25' by default, from
    NCES_PRIMARY_YEAR). Resolved lazily (not at module-import time) — glob + exactly-one, same
    check as common/school_sampling._lea_file but NOT imported from it: infrastructure.scripts must
    never import infrastructure.acquisition (pyproject.toml layering contract)."""
    vdir = project_root / "data/raw/federal/nces-ccd" / primary_year.replace("-", "_")
    hits = sorted(vdir.glob("ccd_lea_029_*.csv"))
    if len(hits) != 1:
        raise FileNotFoundError(
            f"expected exactly one ccd_lea_029_*.csv under {vdir} for NCES_PRIMARY_YEAR="
            f"{primary_year!r}; found {[h.name for h in hits]} — has the new CCD been dropped in, "
            f"or was NCES_PRIMARY_YEAR bumped before the file landed?")
    return hits[0]


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
    """Load NCES ID -> Website URL mapping from the primary-vintage LEA CSV. Columns resolved by
    HEADER NAME via csv.DictReader (#567) — a future vintage's layout shift fails on a KeyError
    lookup of a real header, not a silently-wrong positional offset."""
    urls = {}
    with open(nces_ccd_lea_file(), 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            leaid = normalize_nces_id(row["LEAID"].strip())
            website = normalize_url(row["WEBSITE"])
            if leaid and website:
                urls[leaid] = website
    return urls


def import_urls(dry_run: bool = False):
    """Import URLs into the database."""
    ccd_file = nces_ccd_lea_file()
    print(f"Loading URLs from: {ccd_file}")
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

        # Execute batch update — one executemany round-trip, not a per-row
        # UPDATE loop (issue #465)
        if not dry_run and updates:
            session.execute(
                text("UPDATE districts SET website_url = :url WHERE nces_id = :id"),
                [{"url": url, "id": nces_id} for url, nces_id in updates],
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


def main():
    parser = argparse.ArgumentParser(description="Import district website URLs from the NCES CCD")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be updated without making changes")
    args = parser.parse_args()
    import_urls(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
