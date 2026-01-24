#!/usr/bin/env python3
"""
Import Bell Schedules from Manual Collection Files

Processes manually collected bell schedule files from data/raw/manual_import_files/
and imports them into the bell_schedules table.

Supports:
- PDF files (via pdftotext)
- TXT files (direct read)
- DOCX files (via pandoc)
- HTML/MHTML files (html2text)

Usage:
    python import_manual_bell_schedules.py [--dry-run] [--state XX] [--verbose]
"""

import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import BellSchedule, District
from infrastructure.scripts.enrich.content_parser import ContentParser, BellScheduleData
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Paths
MANUAL_IMPORT_DIR = PROJECT_ROOT / "data" / "raw" / "manual_import_files"

# State name to abbreviation mapping
STATE_ABBREV = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
    'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
    'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID',
    'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS',
    'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
    'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS',
    'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK',
    'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
    'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT',
    'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV',
    'Wisconsin': 'WI', 'Wyoming': 'WY',
    'Washington D.C.': 'DC',
    'Hawaii Department of Education (HI)': 'HI',
}


@dataclass
class DistrictMatch:
    """Result of matching a folder to a district."""
    folder_name: str
    folder_path: Path
    state: str
    clean_name: str
    nces_id: Optional[str] = None
    db_name: Optional[str] = None
    files: List[Path] = field(default_factory=list)


@dataclass
class ImportResult:
    """Result of importing a district's bell schedules."""
    nces_id: str
    district_name: str
    schedules_imported: int
    grade_levels: List[str]
    source_files: List[str]
    errors: List[str] = field(default_factory=list)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using pdftotext."""
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', str(pdf_path), '-'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout
        logger.warning(f"pdftotext failed for {pdf_path.name}: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning(f"pdftotext timeout for {pdf_path.name}")
    except FileNotFoundError:
        logger.error("pdftotext not found - install poppler-utils")
    return ""


def extract_text_from_docx(docx_path: Path) -> str:
    """Extract text from DOCX using pandoc."""
    try:
        result = subprocess.run(
            ['pandoc', '-t', 'plain', str(docx_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout
        logger.warning(f"pandoc failed for {docx_path.name}: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning(f"pandoc timeout for {docx_path.name}")
    except FileNotFoundError:
        logger.error("pandoc not found - install pandoc")
    return ""


def extract_text_from_html(html_path: Path) -> str:
    """Extract text from HTML using html2text."""
    try:
        result = subprocess.run(
            ['html2text', str(html_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout
        logger.warning(f"html2text failed for {html_path.name}: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning(f"html2text timeout for {html_path.name}")
    except FileNotFoundError:
        # Fallback: read raw and strip tags
        try:
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # Basic tag stripping
            content = re.sub(r'<[^>]+>', ' ', content)
            return content
        except Exception as e:
            logger.warning(f"Failed to read HTML {html_path.name}: {e}")
    return ""


def get_file_text(file_path: Path) -> str:
    """Extract text content from a file based on its extension."""
    suffix = file_path.suffix.lower()

    if suffix == '.pdf':
        return extract_text_from_pdf(file_path)
    elif suffix == '.txt':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read TXT {file_path.name}: {e}")
            return ""
    elif suffix == '.docx':
        return extract_text_from_docx(file_path)
    elif suffix in ['.html', '.htm', '.mhtml']:
        return extract_text_from_html(file_path)
    else:
        return ""


def discover_districts() -> List[DistrictMatch]:
    """
    Discover all districts in the manual import directory.

    Returns:
        List of DistrictMatch objects with folder info
    """
    districts = []

    for state_dir in MANUAL_IMPORT_DIR.iterdir():
        if not state_dir.is_dir() or state_dir.name.startswith('.'):
            continue

        state_name = state_dir.name
        state_abbrev = STATE_ABBREV.get(state_name)

        for district_dir in state_dir.iterdir():
            if not district_dir.is_dir() or district_dir.name.startswith('.'):
                continue

            # Extract state from folder name if present (e.g., "District Name (AK)")
            match = re.search(r'\(([A-Z]{2})\)$', district_dir.name)
            folder_abbrev = match.group(1) if match else state_abbrev

            # Clean district name
            clean_name = re.sub(r'\s*\([A-Z]{2}\)$', '', district_dir.name).strip()

            # Find content files (skip mhtml/html - slow and contain embedded web assets)
            content_files = []
            for ext in ['*.pdf', '*.txt', '*.docx']:
                content_files.extend(district_dir.glob(ext))
                # Also check converted/ subdirectory
                converted_dir = district_dir / 'converted'
                if converted_dir.exists():
                    content_files.extend(converted_dir.glob(ext))

            # Filter out web asset files
            content_files = [f for f in content_files if not any(
                x in f.name.lower() for x in ['css', 'js', '.ds_store']
            )]

            districts.append(DistrictMatch(
                folder_name=district_dir.name,
                folder_path=district_dir,
                state=folder_abbrev,
                clean_name=clean_name,
                files=content_files
            ))

    return districts


def normalize_district_name(name: str) -> str:
    """Normalize district name for matching by removing common suffixes."""
    # Remove common suffixes
    suffixes = [
        ' School District',
        ' Public Schools',
        ' Schools',
        ' Unified School District',
        ' Independent Comm School District',
        ' Comm School District',
        ' Community School District',
        ' School District No. R-1',
        ' School District No. Re 1',
        ' Area Schools',
        ' Area School District',
        ' County Public Schools',
        ' County Schools',
        ' School District 49-5',
    ]
    normalized = name
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
    return normalized.strip()


def match_districts_to_db(districts: List[DistrictMatch], session) -> List[DistrictMatch]:
    """
    Match discovered districts to database records.

    Args:
        districts: List of DistrictMatch objects
        session: Database session

    Returns:
        List of DistrictMatch objects with nces_id populated
    """
    matched = []

    for item in districts:
        state = item.state
        name = item.clean_name

        if not state:
            logger.warning(f"No state for {item.folder_name}")
            continue

        # Try exact match first
        district = session.query(District).filter(
            District.state == state,
            District.name == name
        ).first()

        if not district:
            # Try contains match
            district = session.query(District).filter(
                District.state == state,
                District.name.ilike(f'%{name}%')
            ).first()

        if not district:
            # Try normalized name match (strip suffixes)
            normalized = normalize_district_name(name)
            if normalized != name:
                district = session.query(District).filter(
                    District.state == state,
                    District.name.ilike(f'{normalized}%')
                ).first()

        if not district:
            # Try first two words match (e.g., "Los Angeles" from "Los Angeles Unified School District")
            words = name.split()[:2]
            if len(words) >= 2:
                prefix = ' '.join(words)
                district = session.query(District).filter(
                    District.state == state,
                    District.name.ilike(f'{prefix}%')
                ).first()

        if not district:
            # Try first word match
            first_word = name.split()[0] if name else ""
            if first_word and len(first_word) > 3:
                district = session.query(District).filter(
                    District.state == state,
                    District.name.ilike(f'{first_word}%')
                ).first()

        if district:
            item.nces_id = district.nces_id
            item.db_name = district.name
            matched.append(item)
        else:
            logger.warning(f"No match for {state}: {name}")

    return matched


def process_district_files(
    district: DistrictMatch,
    parser: ContentParser
) -> Tuple[List[BellScheduleData], List[str]]:
    """
    Process all files for a district and extract bell schedules.

    Args:
        district: DistrictMatch with files to process
        parser: ContentParser instance

    Returns:
        Tuple of (bell schedule data list, source files used)
    """
    all_schedules = []
    source_files = []

    # Combine text from all files
    combined_text = ""
    for file_path in district.files:
        text = get_file_text(file_path)
        if text:
            combined_text += f"\n\n--- {file_path.name} ---\n\n{text}"
            source_files.append(file_path.name)

    if not combined_text:
        return [], []

    # Try to extract schedules for all grade levels
    schedules = parser.parse_all(combined_text, "", expected_levels=['elementary', 'middle', 'high'])

    if schedules:
        return schedules, source_files

    # If no structured extraction worked, try processing files individually
    for file_path in district.files:
        text = get_file_text(file_path)
        if not text:
            continue

        # Detect grade level from filename
        filename_lower = file_path.name.lower()
        if any(x in filename_lower for x in ['elem', 'primary', 'k-5', 'k-6']):
            expected = ['elementary']
        elif any(x in filename_lower for x in ['middle', 'junior', 'ms', '6-8', '7-8']):
            expected = ['middle']
        elif any(x in filename_lower for x in ['high', 'hs', 'secondary', '9-12']):
            expected = ['high']
        else:
            expected = None

        file_schedules = parser.parse_all(text, "", expected_levels=expected)

        for sched in file_schedules:
            # Check if we already have this grade level
            if not any(s.grade_level == sched.grade_level for s in all_schedules):
                sched.schools_sampled = [file_path.name]
                all_schedules.append(sched)

    return all_schedules, source_files


def import_bell_schedule(
    session,
    nces_id: str,
    schedule: BellScheduleData,
    source_files: List[str],
    dry_run: bool = False
) -> bool:
    """
    Import a single bell schedule into the database.

    Args:
        session: Database session
        nces_id: District NCES ID
        schedule: Bell schedule data
        source_files: List of source file names
        dry_run: If True, don't commit

    Returns:
        True if successful
    """
    year = "2025-26"  # Default year for manual collection

    # Check for existing schedule
    existing = session.query(BellSchedule).filter(
        BellSchedule.district_id == nces_id,
        BellSchedule.year == year,
        BellSchedule.grade_level == schedule.grade_level
    ).first()

    if existing:
        logger.debug(f"  Skipping {schedule.grade_level} - already exists")
        return False

    if dry_run:
        logger.info(f"  [DRY RUN] Would import {schedule.grade_level}: {schedule.start_time} - {schedule.end_time} ({schedule.instructional_minutes} min)")
        return True

    # Create new bell schedule
    bell_schedule = BellSchedule(
        district_id=nces_id,
        year=year,
        grade_level=schedule.grade_level,
        instructional_minutes=schedule.instructional_minutes,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        confidence="high",  # Manual collection is high confidence
        method="human_provided",
        source_description=f"Manual collection from: {', '.join(source_files[:3])}",
        schools_sampled=schedule.schools_sampled[:5] if schedule.schools_sampled else [],
        source_urls=[],
        raw_import={
            'source_method': schedule.source_method,
            'extraction_confidence': schedule.confidence,
            'source_files': source_files
        }
    )

    session.add(bell_schedule)
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Import manual bell schedule files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without committing")
    parser.add_argument("--state", type=str, help="Filter to specific state (e.g., FL)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Manual Bell Schedule Import")
    logger.info("=" * 60)

    # Discover districts
    logger.info("Discovering district folders...")
    districts = discover_districts()
    logger.info(f"Found {len(districts)} district folders")

    # Filter by state if specified
    if args.state:
        districts = [d for d in districts if d.state == args.state.upper()]
        logger.info(f"Filtered to {len(districts)} districts in {args.state.upper()}")

    # Match to database
    with session_scope() as session:
        logger.info("Matching to database districts...")
        matched = match_districts_to_db(districts, session)
        logger.info(f"Matched {len(matched)} districts to database")

    # Process and import
    content_parser = ContentParser(use_llm=False)  # Don't use LLM for manual files

    results = []
    total_imported = 0

    with session_scope() as session:
        for district in matched:
            if not district.files:
                logger.debug(f"No content files for {district.folder_name}")
                continue

            logger.info(f"\nProcessing: {district.db_name} ({district.state})")
            logger.info(f"  Files: {len(district.files)}")

            # Extract schedules
            schedules, source_files = process_district_files(district, content_parser)

            if not schedules:
                logger.warning(f"  No schedules extracted")
                continue

            # Import schedules
            imported = 0
            grade_levels = []

            for sched in schedules:
                if import_bell_schedule(session, district.nces_id, sched, source_files, args.dry_run):
                    imported += 1
                    grade_levels.append(sched.grade_level)
                    logger.info(f"  Imported {sched.grade_level}: {sched.start_time} - {sched.end_time} ({sched.instructional_minutes} min)")

            if imported > 0:
                results.append(ImportResult(
                    nces_id=district.nces_id,
                    district_name=district.db_name,
                    schedules_imported=imported,
                    grade_levels=grade_levels,
                    source_files=source_files
                ))
                total_imported += imported

        if not args.dry_run:
            session.commit()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Import Summary")
    logger.info("=" * 60)
    logger.info(f"Districts processed: {len(matched)}")
    logger.info(f"Districts with schedules: {len(results)}")
    logger.info(f"Total schedules imported: {total_imported}")

    if results:
        logger.info("\nBy grade level:")
        elem = sum(1 for r in results if 'elementary' in r.grade_levels)
        middle = sum(1 for r in results if 'middle' in r.grade_levels)
        high = sum(1 for r in results if 'high' in r.grade_levels)
        logger.info(f"  Elementary: {elem}")
        logger.info(f"  Middle: {middle}")
        logger.info(f"  High: {high}")

    if args.dry_run:
        logger.info("\n[DRY RUN - No changes made]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
