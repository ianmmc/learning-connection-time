#!/usr/bin/env python3
"""
Migration Script: Manual Import Files to New PDF Structure

Migrates existing manually collected bell schedule files from:
    data/raw/manual_import_files/{State Name}/{District Name (STATE)}/

To the new organized structure:
    data/raw/bell_schedule_pdfs/{STATE}/{district_id}/

Preserves provenance by setting acquisition_method: "manual" in metadata.

Usage:
    # Dry run (show what would be migrated)
    python migrate_manual_pdfs.py --dry-run

    # Migrate all
    python migrate_manual_pdfs.py

    # Migrate specific state
    python migrate_manual_pdfs.py --state Colorado
"""

import argparse
import json
import logging
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Directories
MANUAL_IMPORT_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "manual_import_files"
PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"

# State name to code mapping
STATE_NAME_TO_CODE = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
    "Washington D.C.": "DC", "Puerto Rico": "PR",
    # Handle Hawaii DOE special case
    "Hawaii Department of Education (HI)": "HI",
}


class ManualPDFMigrator:
    """Migrate manual import files to new structure"""

    def __init__(
        self,
        source_dir: Path = MANUAL_IMPORT_DIR,
        target_dir: Path = PDF_BASE_DIR,
        dry_run: bool = False
    ):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.dry_run = dry_run
        self.district_cache: Dict[str, District] = {}

    def migrate_all(self, state_filter: str = None) -> Dict:
        """
        Migrate all manual import files.

        Args:
            state_filter: Optional state name to filter

        Returns:
            Migration summary
        """
        stats = {
            "states_processed": 0,
            "districts_migrated": 0,
            "files_copied": 0,
            "districts_skipped_no_id": [],
            "districts_skipped_no_files": [],
            "errors": []
        }

        for state_dir in sorted(self.source_dir.iterdir()):
            if not state_dir.is_dir():
                continue
            if state_dir.name.startswith("."):
                continue

            state_name = state_dir.name

            # Apply filter
            if state_filter and state_name != state_filter:
                continue

            # Get state code
            state_code = self._get_state_code(state_name)
            if not state_code:
                logger.warning(f"Unknown state: {state_name}")
                continue

            logger.info(f"Processing state: {state_name} ({state_code})")
            stats["states_processed"] += 1

            # Process each district in state
            for district_dir in sorted(state_dir.iterdir()):
                if not district_dir.is_dir():
                    continue
                if district_dir.name.startswith("."):
                    continue

                result = self._migrate_district(district_dir, state_code)

                if result["success"]:
                    stats["districts_migrated"] += 1
                    stats["files_copied"] += result["files_copied"]
                elif result.get("error") == "no_nces_id":
                    stats["districts_skipped_no_id"].append(district_dir.name)
                elif result.get("error") == "no_files":
                    stats["districts_skipped_no_files"].append(district_dir.name)
                else:
                    stats["errors"].append({
                        "district": district_dir.name,
                        "error": result.get("error")
                    })

        return stats

    def _get_state_code(self, state_name: str) -> Optional[str]:
        """Get state code from state name"""
        # Direct lookup
        if state_name in STATE_NAME_TO_CODE:
            return STATE_NAME_TO_CODE[state_name]

        # Try to find state code in parentheses
        match = re.search(r'\(([A-Z]{2})\)', state_name)
        if match:
            return match.group(1)

        return None

    def _migrate_district(self, district_dir: Path, state_code: str) -> Dict:
        """
        Migrate a single district directory.

        Args:
            district_dir: Source district directory
            state_code: State code (e.g., "CO")

        Returns:
            Migration result
        """
        district_name = district_dir.name
        logger.info(f"  Processing: {district_name}")

        # Find NCES ID for this district
        nces_id = self._lookup_nces_id(district_name, state_code)
        if not nces_id:
            logger.warning(f"    No NCES ID found for: {district_name}")
            return {"success": False, "error": "no_nces_id"}

        # Find files to migrate
        files_to_copy = self._find_migratable_files(district_dir)
        if not files_to_copy:
            logger.info(f"    No migratable files found")
            return {"success": False, "error": "no_files"}

        # Create target directory
        target_dir = self.target_dir / state_code / nces_id
        if not self.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        # Copy files
        copied_files = []
        for src_path in files_to_copy:
            # Generate target filename
            ext = src_path.suffix.lower()
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            target_filename = f"manual_{src_path.stem[:30]}_{timestamp}{ext}"
            target_path = target_dir / target_filename

            if self.dry_run:
                logger.info(f"    [DRY RUN] Would copy: {src_path.name} -> {target_filename}")
            else:
                shutil.copy2(src_path, target_path)
                logger.info(f"    Copied: {src_path.name} -> {target_filename}")

            copied_files.append({
                "filename": target_filename,
                "original_filename": src_path.name,
                "original_path": str(src_path.relative_to(self.source_dir)),
                "grade_level": self._infer_grade_level(src_path.name),
            })

        # Create metadata
        if not self.dry_run and copied_files:
            self._create_metadata(
                target_dir, nces_id, district_name, state_code, copied_files
            )

        return {
            "success": True,
            "nces_id": nces_id,
            "files_copied": len(copied_files)
        }

    def _lookup_nces_id(self, district_name: str, state_code: str) -> Optional[str]:
        """Look up NCES ID from database"""
        # Clean district name for matching
        clean_name = district_name

        # Remove state code in parentheses
        clean_name = re.sub(r'\s*\([A-Z]{2}\)\s*$', '', clean_name)

        # Remove common suffixes
        clean_name = re.sub(r'\s*(School District|Public Schools|Schools|District|ISD|USD|SD).*$',
                          '', clean_name, flags=re.IGNORECASE)

        clean_name = clean_name.strip()

        with session_scope() as session:
            # Try exact match first
            district = session.query(District).filter(
                District.state == state_code,
                District.name.ilike(f"%{clean_name}%")
            ).first()

            if district:
                return district.nces_id

            # Try with "Public Schools" added
            district = session.query(District).filter(
                District.state == state_code,
                District.name.ilike(f"%{clean_name}%Public Schools%")
            ).first()

            if district:
                return district.nces_id

            # Try first few words
            first_words = ' '.join(clean_name.split()[:2])
            if len(first_words) > 3:
                district = session.query(District).filter(
                    District.state == state_code,
                    District.name.ilike(f"{first_words}%")
                ).first()

                if district:
                    return district.nces_id

        return None

    def _find_migratable_files(self, district_dir: Path) -> List[Path]:
        """Find files that can be migrated (PDFs, DOCXs, HTMLs)"""
        migratable_extensions = {'.pdf', '.docx', '.doc', '.html', '.htm'}
        files = []

        for item in district_dir.iterdir():
            if item.is_file() and item.suffix.lower() in migratable_extensions:
                files.append(item)

        # Also check "converted" subdirectory
        converted_dir = district_dir / "converted"
        if converted_dir.exists():
            for item in converted_dir.iterdir():
                if item.is_file() and item.suffix.lower() == '.pdf':
                    files.append(item)

        return files

    def _infer_grade_level(self, filename: str) -> str:
        """Infer grade level from filename"""
        filename_lower = filename.lower()

        if any(kw in filename_lower for kw in ['elementary', 'primary', 'k-5', 'k-4']):
            return 'elementary'
        if any(kw in filename_lower for kw in ['middle', 'junior', 'intermediate']):
            return 'middle'
        if any(kw in filename_lower for kw in ['high', 'secondary', 'senior']):
            return 'high'

        return 'district'  # Assume district-level if not specific

    def _create_metadata(
        self,
        target_dir: Path,
        nces_id: str,
        district_name: str,
        state_code: str,
        files: List[Dict]
    ):
        """Create metadata.json for migrated district"""
        metadata_path = target_dir / "metadata.json"

        # Load existing metadata if present
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
            # Append files
            existing_files = {s["filename"] for s in metadata.get("sources", [])}
            for f in files:
                if f["filename"] not in existing_files:
                    metadata["sources"].append(f)
            metadata["updated_at"] = datetime.utcnow().isoformat()
        else:
            metadata = {
                "district_id": nces_id,
                "district_name": district_name,
                "state": state_code,
                "captured_at": datetime.utcnow().isoformat(),
                "sources": files,
                "acquisition_method": "manual",
                "acquisition_details": {
                    "tool": "human_browser",
                    "migrated_from": f"data/raw/manual_import_files/",
                    "migrated_at": datetime.utcnow().isoformat()
                },
                "extraction_status": "pending"
            }

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Migrate manual import files to new PDF structure"
    )
    parser.add_argument(
        "--state",
        help="Only migrate this state (by name, e.g., 'Colorado')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without copying files"
    )
    parser.add_argument(
        "--list-states",
        action="store_true",
        help="List available states to migrate"
    )

    args = parser.parse_args()

    if args.list_states:
        print("Available states in manual_import_files:")
        for state_dir in sorted(MANUAL_IMPORT_DIR.iterdir()):
            if state_dir.is_dir() and not state_dir.name.startswith("."):
                code = STATE_NAME_TO_CODE.get(state_dir.name, "??")
                num_districts = len([d for d in state_dir.iterdir()
                                   if d.is_dir() and not d.name.startswith(".")])
                print(f"  {state_dir.name} ({code}) - {num_districts} districts")
        return

    migrator = ManualPDFMigrator(dry_run=args.dry_run)

    print(f"Source: {MANUAL_IMPORT_DIR}")
    print(f"Target: {PDF_BASE_DIR}")
    print(f"Dry run: {args.dry_run}")
    print()

    stats = migrator.migrate_all(state_filter=args.state)

    print(f"\n{'='*60}")
    print(f"MIGRATION {'PREVIEW' if args.dry_run else 'COMPLETE'}")
    print(f"{'='*60}")
    print(f"States processed: {stats['states_processed']}")
    print(f"Districts migrated: {stats['districts_migrated']}")
    print(f"Files copied: {stats['files_copied']}")

    if stats['districts_skipped_no_id']:
        print(f"\nDistricts skipped (no NCES ID found): {len(stats['districts_skipped_no_id'])}")
        for d in stats['districts_skipped_no_id'][:10]:
            print(f"  - {d}")
        if len(stats['districts_skipped_no_id']) > 10:
            print(f"  ... and {len(stats['districts_skipped_no_id']) - 10} more")

    if stats['errors']:
        print(f"\nErrors: {len(stats['errors'])}")
        for e in stats['errors'][:5]:
            print(f"  - {e['district']}: {e['error']}")


if __name__ == "__main__":
    main()
