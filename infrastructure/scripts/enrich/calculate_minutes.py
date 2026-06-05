#!/usr/bin/env python3
"""
calculate_minutes.py - Calculate instructional minutes from extracted times

PURPOSE:
    Reads verified_extraction.json containing start/end times and calculates
    instructional_minutes for each schedule entry. This is pure Python datetime
    math - no LLM involvement to avoid hallucinated calculations.

CONTEXT - ENRICHMENT PIPELINE POSITION:
    This script is Step 3 of 5 in the Phase 8 Enrichment Pipeline:
    1. Ollama extraction (POST /enrich/extract) → extraction_result.json
    2. Claude verification → verified_extraction.json
    3. calculate_minutes.py → enrichment_ready.json  <-- THIS SCRIPT
    4. import_bell_schedules.py → database + import_result.json
    5. verify_enrichment.py → verification_report.json

    This script handles step 3: Deterministic calculation of instructional time
    from verified start/end times. LLMs should NOT do math - this script ensures
    accurate calculations.

INPUT:
    - File: data/raw/bell_schedule_pdfs/{state}/{district}/verified_extraction.json
    - Schema: Same as extraction_result.json but with Claude corrections
    - Source: Created by Claude during verification step

OUTPUT:
    - File: data/raw/bell_schedule_pdfs/{state}/{district}/enrichment_ready.json
    - Schema: Same as input but with instructional_minutes added to each schedule
    - Consumed by: import_bell_schedules.py (step 4)

CALCULATION LOGIC:
    1. Parse start_time and end_time as datetime objects (HH:MM format)
    2. Calculate: total_minutes = (end_time - start_time).total_seconds() / 60
    3. Subtract lunch (30 min default) if not already accounted for
    4. Validate: 300 <= instructional_minutes <= 480 (reasonable school day range)
    5. Flag any calculations outside this range for review

USAGE:
    python infrastructure/scripts/enrich/calculate_minutes.py \\
        --input data/raw/bell_schedule_pdfs/FL/1200390_Pasco_County/verified_extraction.json \\
        --output data/raw/bell_schedule_pdfs/FL/1200390_Pasco_County/enrichment_ready.json

    # Or process by district ID (auto-find directory):
    python infrastructure/scripts/enrich/calculate_minutes.py \\
        --district 1200390

    # With custom lunch deduction:
    python infrastructure/scripts/enrich/calculate_minutes.py \\
        --district 1200390 --lunch-minutes 45

DEPENDENCIES:
    - Python standard library only (json, datetime, argparse, pathlib)

SEE ALSO:
    - Plan: ~/.claude/plans/crispy-brewing-blanket.md (Phase 8)
    - Related: extraction_service.py (step 1), import_bell_schedules.py (step 4)
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Base directory for bell schedule PDFs
PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"

# Validation ranges for instructional minutes
MIN_INSTRUCTIONAL_MINUTES = 300  # ~5 hours
MAX_INSTRUCTIONAL_MINUTES = 480  # ~8 hours

# Default lunch deduction (minutes)
DEFAULT_LUNCH_MINUTES = 30


def find_district_dir(district_id: str) -> Optional[Path]:
    """
    Find the district directory by ID prefix.

    Args:
        district_id: NCES district ID

    Returns:
        Path to district directory or None if not found
    """
    for state_dir in PDF_BASE_DIR.iterdir():
        if not state_dir.is_dir():
            continue
        for district_dir in state_dir.iterdir():
            if district_dir.is_dir() and district_dir.name.startswith(district_id):
                return district_dir
    return None


def parse_time(time_str: str) -> Optional[datetime]:
    """
    Parse HH:MM time string to datetime object.

    Args:
        time_str: Time in "HH:MM" 24-hour format

    Returns:
        datetime object for comparison, or None if invalid
    """
    try:
        return datetime.strptime(time_str, "%H:%M")
    except (ValueError, TypeError):
        logger.warning(f"Invalid time format: {time_str}")
        return None


def calculate_minutes(start_time: str, end_time: str, lunch_minutes: int = DEFAULT_LUNCH_MINUTES) -> Dict[str, Any]:
    """
    Calculate instructional minutes from start and end times.

    Args:
        start_time: School start time in HH:MM format
        end_time: School end time in HH:MM format
        lunch_minutes: Minutes to subtract for lunch

    Returns:
        Dict with:
            - instructional_minutes: Calculated minutes
            - total_minutes: Raw duration without lunch deduction
            - lunch_deducted: Whether lunch was deducted
            - valid: Whether the result is within expected range
            - warning: Any warning message
    """
    result = {
        "instructional_minutes": None,
        "total_minutes": None,
        "lunch_deducted": False,
        "valid": False,
        "warning": None,
    }

    start = parse_time(start_time)
    end = parse_time(end_time)

    if not start or not end:
        result["warning"] = f"Could not parse times: {start_time} - {end_time}"
        return result

    # Calculate total minutes
    delta = end - start
    total_minutes = int(delta.total_seconds() / 60)

    # Handle case where end time is before start (overnight schedule - unlikely for schools)
    if total_minutes < 0:
        result["warning"] = f"End time before start time: {start_time} - {end_time}"
        return result

    result["total_minutes"] = total_minutes

    # Deduct lunch if total seems to include it (> 5.5 hours)
    if total_minutes > 330:  # 5.5 hours
        instructional = total_minutes - lunch_minutes
        result["lunch_deducted"] = True
    else:
        instructional = total_minutes

    result["instructional_minutes"] = instructional

    # Validate range
    if MIN_INSTRUCTIONAL_MINUTES <= instructional <= MAX_INSTRUCTIONAL_MINUTES:
        result["valid"] = True
    else:
        result["warning"] = f"Instructional minutes ({instructional}) outside expected range ({MIN_INSTRUCTIONAL_MINUTES}-{MAX_INSTRUCTIONAL_MINUTES})"

    return result


def process_extraction(
    input_data: Dict[str, Any],
    lunch_minutes: int = DEFAULT_LUNCH_MINUTES
) -> Dict[str, Any]:
    """
    Process extraction data and add instructional_minutes to each schedule.

    Args:
        input_data: Verified extraction JSON data
        lunch_minutes: Minutes to subtract for lunch

    Returns:
        Updated data with instructional_minutes added
    """
    output_data = input_data.copy()
    output_data["calculation_date"] = datetime.utcnow().isoformat()
    output_data["lunch_minutes_deducted"] = lunch_minutes

    schedules_processed = 0
    schedules_valid = 0
    warnings = []

    for schedule in output_data.get("schedules", []):
        start_time = schedule.get("start_time")
        end_time = schedule.get("end_time")

        if not start_time or not end_time:
            schedule["instructional_minutes"] = None
            schedule["calculation_warning"] = "Missing start or end time"
            warnings.append(f"Schedule missing times: {schedule}")
            continue

        calc_result = calculate_minutes(start_time, end_time, lunch_minutes)

        schedule["instructional_minutes"] = calc_result["instructional_minutes"]
        schedule["total_minutes"] = calc_result["total_minutes"]
        schedule["lunch_deducted"] = calc_result["lunch_deducted"]
        schedule["calculation_valid"] = calc_result["valid"]

        if calc_result["warning"]:
            schedule["calculation_warning"] = calc_result["warning"]
            warnings.append(f"{schedule.get('grade_level', 'unknown')}: {calc_result['warning']}")

        schedules_processed += 1
        if calc_result["valid"]:
            schedules_valid += 1

    output_data["calculation_summary"] = {
        "schedules_processed": schedules_processed,
        "schedules_valid": schedules_valid,
        "schedules_with_warnings": len(warnings),
        "warnings": warnings,
    }

    return output_data


def main():
    parser = argparse.ArgumentParser(
        description="Calculate instructional minutes from verified extraction data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process specific files:
  python calculate_minutes.py --input verified_extraction.json --output enrichment_ready.json

  # Process by district ID (auto-find directory):
  python calculate_minutes.py --district 1200390

  # Custom lunch deduction:
  python calculate_minutes.py --district 1200390 --lunch-minutes 45
        """
    )

    parser.add_argument(
        "--input", "-i",
        type=Path,
        help="Input file (verified_extraction.json)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file (enrichment_ready.json)"
    )
    parser.add_argument(
        "--district", "-d",
        help="District ID (auto-find directory and use default filenames)"
    )
    parser.add_argument(
        "--lunch-minutes", "-l",
        type=int,
        default=DEFAULT_LUNCH_MINUTES,
        help=f"Minutes to deduct for lunch (default: {DEFAULT_LUNCH_MINUTES})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate and print results without saving"
    )

    args = parser.parse_args()

    # Determine input/output paths
    if args.district:
        district_dir = find_district_dir(args.district)
        if not district_dir:
            logger.error(f"District directory not found for {args.district}")
            sys.exit(1)

        input_path = district_dir / "verified_extraction.json"
        output_path = district_dir / "enrichment_ready.json"

        # Fall back to extraction_result.json if verified doesn't exist
        if not input_path.exists():
            fallback = district_dir / "extraction_result.json"
            if fallback.exists():
                logger.warning(f"verified_extraction.json not found, using {fallback.name}")
                input_path = fallback
            else:
                logger.error(f"No extraction file found in {district_dir}")
                sys.exit(1)
    else:
        if not args.input or not args.output:
            parser.error("Either --district or both --input and --output are required")
        input_path = args.input
        output_path = args.output

    # Read input
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    logger.info(f"Reading: {input_path}")
    with open(input_path) as f:
        input_data = json.load(f)

    # Process
    logger.info(f"Calculating instructional minutes (lunch deduction: {args.lunch_minutes} min)")
    output_data = process_extraction(input_data, args.lunch_minutes)

    # Report summary
    summary = output_data.get("calculation_summary", {})
    logger.info(f"Processed: {summary.get('schedules_processed', 0)} schedules")
    logger.info(f"Valid: {summary.get('schedules_valid', 0)} schedules")

    if summary.get("warnings"):
        logger.warning("Warnings:")
        for warning in summary["warnings"]:
            logger.warning(f"  - {warning}")

    # Preview results
    for schedule in output_data.get("schedules", []):
        grade = schedule.get("grade_level", "unknown")
        start = schedule.get("start_time", "?")
        end = schedule.get("end_time", "?")
        minutes = schedule.get("instructional_minutes", "?")
        valid = "OK" if schedule.get("calculation_valid") else "WARN"
        logger.info(f"  {grade}: {start}-{end} = {minutes} min [{valid}]")

    # Save output
    if args.dry_run:
        logger.info("Dry run - not saving output")
        print(json.dumps(output_data, indent=2))
    else:
        logger.info(f"Writing: {output_path}")
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        logger.info("Done!")


if __name__ == "__main__":
    main()
