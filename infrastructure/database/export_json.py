#!/usr/bin/env python3
"""
JSON Export Utility: Export bell schedules from database to JSON files.

Maintains backward compatibility with the original file-based workflow
by exporting database contents to the same JSON format used previously.

Usage:
    python export_json.py [--year YEAR] [--output FILE] [--individual-files]

Author: Claude (AI Assistant)
Date: December 25, 2025
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.database.connection import session_scope
from infrastructure.database.queries import export_bell_schedules_to_json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default output paths
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "enriched" / "bell-schedules"
DEFAULT_CONSOLIDATED_FILE = "bell_schedules_manual_collection_2024_25.json"


def export_consolidated(year: str, output_file: Path) -> int:
    """
    Export all bell schedules to a single consolidated JSON file.

    Args:
        year: School year to export (e.g., "2024-25")
        output_file: Path to output file

    Returns:
        Number of districts exported
    """
    logger.info(f"Exporting consolidated bell schedules for {year}...")

    with session_scope() as session:
        json_content = export_bell_schedules_to_json(session, year=year)
        data = json.loads(json_content)

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(output_file, "w") as f:
            f.write(json_content)

        district_count = len(data)
        logger.info(f"Exported {district_count} districts to {output_file}")
        return district_count


def export_individual_files(year: str, output_dir: Path) -> int:
    """
    Export bell schedules to individual JSON files per district.

    Args:
        year: School year to export (e.g., "2024-25")
        output_dir: Directory to write files

    Returns:
        Number of files created
    """
    logger.info(f"Exporting individual bell schedule files for {year}...")

    with session_scope() as session:
        json_content = export_bell_schedules_to_json(session, year=year)
        data = json.loads(json_content)

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        file_count = 0
        for district_id, district_data in data.items():
            # Create individual file for each district
            file_path = output_dir / f"{district_id}_2024-25.json"

            with open(file_path, "w") as f:
                json.dump(district_data, f, indent=2)

            file_count += 1

        logger.info(f"Exported {file_count} individual files to {output_dir}")
        return file_count


def export_enrichment_reference_csv(output_file: Path) -> int:
    """
    Export enrichment reference CSV for quick lookups.

    Args:
        output_file: Path to output file

    Returns:
        Number of rows exported
    """
    from infrastructure.database.queries import export_enriched_districts_csv

    logger.info("Exporting enrichment reference CSV...")

    with session_scope() as session:
        csv_content = export_enriched_districts_csv(session)

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            f.write(csv_content)

        row_count = len(csv_content.strip().split("\n")) - 1  # Subtract header
        logger.info(f"Exported {row_count} rows to {output_file}")
        return row_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Export bell schedules from database to JSON files"
    )
    parser.add_argument(
        "--year",
        default="2024-25",
        help="School year to export (default: 2024-25)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=f"Output file path (default: {DEFAULT_OUTPUT_DIR / DEFAULT_CONSOLIDATED_FILE})"
    )
    parser.add_argument(
        "--individual-files",
        action="store_true",
        help="Export individual JSON files per district instead of consolidated"
    )
    parser.add_argument(
        "--include-reference-csv",
        action="store_true",
        help="Also export enrichment reference CSV"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.individual_files:
            output_dir = args.output or DEFAULT_OUTPUT_DIR
            export_individual_files(args.year, output_dir)
        else:
            output_file = args.output or (DEFAULT_OUTPUT_DIR / DEFAULT_CONSOLIDATED_FILE)
            export_consolidated(args.year, output_file)

        if args.include_reference_csv:
            csv_file = PROJECT_ROOT / "data" / "processed" / "normalized" / "enrichment_reference.csv"
            export_enrichment_reference_csv(csv_file)

        logger.info("Export complete!")

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
