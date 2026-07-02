#!/usr/bin/env python3
"""
Bell Schedule Database Import

Imports extracted bell schedule data from PDFs to the database.

Reads from:
    data/raw/bell_schedule_pdfs/{STATE}/{district_id}/extracted/*.json

Writes to:
    bell_schedules table

Usage:
    # Import all extracted schedules
    python import_bell_schedules_from_pdfs.py

    # Import specific state
    python import_bell_schedules_from_pdfs.py --state CO

    # Import specific district
    python import_bell_schedules_from_pdfs.py --district 0622710

    # Dry run
    python import_bell_schedules_from_pdfs.py --dry-run
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, BellSchedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PDF_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"


class BellScheduleImporter:
    """Import extracted bell schedules to database"""

    def __init__(
        self,
        pdf_base_dir: Path = PDF_BASE_DIR,
        dry_run: bool = False
    ):
        self.pdf_base_dir = pdf_base_dir
        self.dry_run = dry_run

    def import_all(
        self,
        state: str = None,
        district_id: str = None
    ) -> Dict:
        """
        Import all extracted schedules matching criteria.

        Args:
            state: Optional state code filter
            district_id: Optional district ID filter

        Returns:
            Import statistics
        """
        stats = {
            "districts_processed": 0,
            "schedules_imported": 0,
            "schedules_skipped_duplicate": 0,
            "districts_skipped_no_extraction": 0,
            "errors": []
        }

        # Find directories to process
        if district_id:
            # Find specific district
            for state_dir in self.pdf_base_dir.iterdir():
                if state_dir.is_dir():
                    district_dir = state_dir / district_id
                    if district_dir.exists():
                        result = self._import_district(district_dir)
                        self._accumulate_stats(stats, result)
                        return stats

            logger.warning(f"District {district_id} not found")
            return stats

        # Process states
        for state_dir in sorted(self.pdf_base_dir.iterdir()):
            if not state_dir.is_dir():
                continue

            state_code = state_dir.name
            if state and state_code != state:
                continue

            logger.info(f"Processing state: {state_code}")

            # Process each district in state
            for district_dir in sorted(state_dir.iterdir()):
                if not district_dir.is_dir():
                    continue

                result = self._import_district(district_dir)
                self._accumulate_stats(stats, result)

        return stats

    def _import_district(self, district_dir: Path) -> Dict:
        """
        Import extracted schedules for a single district.

        Args:
            district_dir: Directory containing extracted/*.json files

        Returns:
            Import result for this district
        """
        result = {
            "district_id": district_dir.name,
            "schedules_imported": 0,
            "schedules_skipped": 0,
            "error": None
        }

        # Check for metadata
        metadata_path = district_dir / "metadata.json"
        if not metadata_path.exists():
            logger.debug(f"No metadata.json in {district_dir}")
            result["error"] = "no_metadata"
            return result

        with open(metadata_path) as f:
            metadata = json.load(f)

        district_id = metadata.get("district_id")
        if not district_id:
            result["error"] = "no_district_id"
            return result

        # Check extraction status
        if metadata.get("extraction_status") != "extracted":
            result["error"] = "not_extracted"
            return result

        # Check for extracted files
        extracted_dir = district_dir / "extracted"
        if not extracted_dir.exists():
            result["error"] = "no_extracted_dir"
            return result

        extraction_files = list(extracted_dir.glob("*.json"))
        if not extraction_files:
            result["error"] = "no_extraction_files"
            return result

        logger.info(f"  Importing: {metadata.get('district_name', district_id)}")

        # Get acquisition method
        acquisition_method = metadata.get("acquisition_method", "automated")
        source_urls = [s.get("url") for s in metadata.get("sources", []) if s.get("url")]

        # Process each extraction file
        with session_scope() as session:
            # Verify district exists
            district = session.query(District).filter_by(nces_id=district_id).first()
            if not district:
                logger.warning(f"    District {district_id} not in database")
                result["error"] = "district_not_found"
                return result

            for extraction_path in extraction_files:
                with open(extraction_path) as f:
                    extraction = json.load(f)

                if not extraction.get("success"):
                    continue

                schedules = extraction.get("schedules", [])
                for schedule_data in schedules:
                    try:
                        imported = self._import_schedule(
                            session,
                            district_id,
                            schedule_data,
                            acquisition_method,
                            source_urls
                        )
                        if imported:
                            result["schedules_imported"] += 1
                        else:
                            result["schedules_skipped"] += 1
                    except Exception as e:
                        logger.error(f"    Error importing schedule: {e}")
                        result["error"] = str(e)

            if not self.dry_run and result["schedules_imported"] > 0:
                session.commit()
                logger.info(f"    Imported {result['schedules_imported']} schedules")

                # Update metadata
                metadata["import_status"] = "imported"
                metadata["import_date"] = datetime.utcnow().isoformat()
                metadata["schedules_imported"] = result["schedules_imported"]
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)

        return result

    def _import_schedule(
        self,
        session,
        district_id: str,
        schedule_data: Dict,
        acquisition_method: str,
        source_urls: List[str]
    ) -> bool:
        """
        Import a single schedule record.

        Args:
            session: Database session
            district_id: NCES district ID
            schedule_data: Extracted schedule data
            acquisition_method: 'manual' or 'automated'
            source_urls: Source URLs from metadata

        Returns:
            True if imported, False if skipped (duplicate)
        """
        grade_level = schedule_data.get("grade_level", "unknown")
        start_time = schedule_data.get("start_time")
        end_time = schedule_data.get("end_time")
        minutes = schedule_data.get("instructional_minutes")

        if not start_time or not end_time:
            return False

        # Check for existing schedule with same parameters
        existing = session.query(BellSchedule).filter_by(
            district_id=district_id,
            grade_level=grade_level,
            start_time=start_time,
            end_time=end_time
        ).first()

        if existing:
            logger.debug(f"    Duplicate schedule for {grade_level}: {start_time}-{end_time}")
            return False

        if self.dry_run:
            logger.info(f"    [DRY RUN] Would import {grade_level}: {start_time}-{end_time}")
            return True

        # Determine method string
        method = f"pdf_{acquisition_method}"

        # Create new schedule
        schedule = BellSchedule(
            district_id=district_id,
            grade_level=grade_level,
            start_time=start_time,
            end_time=end_time,
            instructional_minutes=minutes,
            source_url=source_urls[0] if source_urls else None,
            method=method,
            confidence=schedule_data.get("confidence", 0.6),
            school_year="2024-25",
            created_at=datetime.utcnow()
        )

        session.add(schedule)
        logger.debug(f"    Added {grade_level}: {start_time}-{end_time} ({minutes} min)")
        return True

    def _accumulate_stats(self, stats: Dict, result: Dict):
        """Accumulate results into stats"""
        stats["districts_processed"] += 1
        stats["schedules_imported"] += result.get("schedules_imported", 0)
        stats["schedules_skipped_duplicate"] += result.get("schedules_skipped", 0)

        error = result.get("error")
        if error == "not_extracted" or error == "no_extracted_dir":
            stats["districts_skipped_no_extraction"] += 1
        elif error:
            stats["errors"].append({
                "district": result.get("district_id"),
                "error": error
            })


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Import extracted bell schedules to database"
    )
    parser.add_argument(
        "--state",
        help="Only import this state (e.g., CO)"
    )
    parser.add_argument(
        "--district",
        help="Only import this district ID"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without database changes"
    )

    args = parser.parse_args()

    importer = BellScheduleImporter(dry_run=args.dry_run)

    print(f"Source: {PDF_BASE_DIR}")
    print(f"Dry run: {args.dry_run}")
    print()

    stats = importer.import_all(state=args.state, district_id=args.district)

    print(f"\n{'='*60}")
    print(f"IMPORT {'PREVIEW' if args.dry_run else 'COMPLETE'}")
    print(f"{'='*60}")
    print(f"Districts processed: {stats['districts_processed']}")
    print(f"Schedules imported: {stats['schedules_imported']}")
    print(f"Schedules skipped (duplicate): {stats['schedules_skipped_duplicate']}")
    print(f"Districts skipped (no extraction): {stats['districts_skipped_no_extraction']}")

    if stats['errors']:
        print(f"\nErrors: {len(stats['errors'])}")
        for e in stats['errors'][:10]:
            print(f"  - {e['district']}: {e['error']}")

    if args.dry_run:
        print("\n[DRY RUN - no database changes made]")


if __name__ == "__main__":
    main()
