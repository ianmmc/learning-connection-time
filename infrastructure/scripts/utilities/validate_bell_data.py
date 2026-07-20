#!/usr/bin/env python3
"""
Bell Schedule Data Validator

Validates extracted bell schedule data before merging into consolidated file.

Usage:
    # Validate a JSON file
    python validate_bell_data.py new_districts.json

    # Validate with strict mode (errors on warnings)
    python validate_bell_data.py new_districts.json --strict

    # Output validation report
    python validate_bell_data.py new_districts.json --report validation_report.txt
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infrastructure.database.school_year import (  # noqa: E402
    GROSS_MINUTES_MIN,
    GROSS_MINUTES_MAX,
    DB_CHECK_MINUTES_MIN,
    DB_CHECK_MINUTES_MAX,
)


class BellScheduleValidator:
    """Validates bell schedule data quality."""

    # Valid values (methods mirror chk_method in the DB, incl. the migration-019
    # additions — this validator predated the gross-minutes era and rejected
    # values the DB accepts)
    VALID_CONFIDENCE = ['high', 'medium', 'low']
    VALID_METHODS = ['human_provided', 'web_scraping', 'pdf_extraction',
                     'school_sample', 'district_policy', 'automated_enrichment',
                     'manual_data_collection', 'state_statutory',
                     'council_extraction', 'statutory_fallback']
    VALID_STATES = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
                   'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
                   'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
                   'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
                   'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
                   'DC', 'PR']

    def __init__(self, strict=False):
        self.strict = strict
        self.errors = []
        self.warnings = []

    def validate_time_format(self, time_str):
        """Check if time string is a valid clock time (e.g., '8:00 AM').

        Numeric + range validation included — '99:99 AM' used to pass on
        format shape alone (issue #394)."""
        minutes = self.time_to_minutes(time_str)
        return minutes is not None

    @staticmethod
    def time_to_minutes(time_str):
        """'H:MM AM/PM' -> minutes from midnight, or None if invalid."""
        if not time_str or not isinstance(time_str, str):
            return None

        parts = time_str.split()
        if len(parts) != 2:
            return None

        time_part, meridiem = parts
        if meridiem not in ['AM', 'PM']:
            return None

        hour_str, _, minute_str = time_part.partition(':')
        if not (hour_str.isdigit() and minute_str.isdigit()):
            return None

        hour, minute = int(hour_str), int(minute_str)
        if not (1 <= hour <= 12) or minute > 59:
            return None

        if hour == 12:
            hour = 0
        if meridiem == 'PM':
            hour += 12
        return hour * 60 + minute

    def validate_minutes(self, minutes, grade_level):
        """Validate instructional minutes are reasonable."""
        if minutes is None:
            return "Missing", "instructional_minutes is null"

        if not isinstance(minutes, (int, float)):
            return "Error", f"instructional_minutes must be numeric, got {type(minutes)}"

        # Bands align with the DB + REQ-055 (the old 180/480 hard bounds
        # predated gross-minutes semantics and errored on values the DB
        # accepts): hard error outside the DB sanity band, warn outside the
        # gross plausibility band.
        if minutes < DB_CHECK_MINUTES_MIN:
            return "Error", (
                f"instructional_minutes ({minutes}) below DB sanity bound "
                f"({DB_CHECK_MINUTES_MIN})"
            )

        if minutes > DB_CHECK_MINUTES_MAX:
            return "Error", (
                f"instructional_minutes ({minutes}) above DB sanity bound "
                f"({DB_CHECK_MINUTES_MAX})"
            )

        if minutes < GROSS_MINUTES_MIN:
            return "Warning", (
                f"instructional_minutes ({minutes}) below gross plausibility "
                f"band ({GROSS_MINUTES_MIN}-{GROSS_MINUTES_MAX}) for {grade_level}"
            )

        if minutes > GROSS_MINUTES_MAX:
            return "Warning", (
                f"instructional_minutes ({minutes}) above gross plausibility "
                f"band ({GROSS_MINUTES_MIN}-{GROSS_MINUTES_MAX}) for {grade_level}"
            )

        return None, None

    def validate_grade_level(self, district_id, district_name, grade_level, data):
        """Validate a single grade level's data."""
        prefix = f"District {district_id} ({district_name}) - {grade_level}"

        if data is None:
            self.warnings.append(f"{prefix}: No data provided")
            return

        # Check instructional minutes
        severity, msg = self.validate_minutes(data.get('instructional_minutes'), grade_level)
        if severity == "Error":
            self.errors.append(f"{prefix}: {msg}")
        elif severity == "Warning":
            self.warnings.append(f"{prefix}: {msg}")
        elif severity == "Missing":
            self.warnings.append(f"{prefix}: {msg}")

        # Check times
        start_time = data.get('start_time', '')
        end_time = data.get('end_time', '')

        start_minutes = self.time_to_minutes(start_time) if start_time else None
        end_minutes = self.time_to_minutes(end_time) if end_time else None

        if start_time and start_minutes is None:
            self.warnings.append(f"{prefix}: Invalid start_time format: '{start_time}'")

        if end_time and end_minutes is None:
            self.warnings.append(f"{prefix}: Invalid end_time format: '{end_time}'")

        # Temporal order: start must precede end (issue #468 — reversed times
        # passed validation entirely)
        if start_minutes is not None and end_minutes is not None and start_minutes >= end_minutes:
            self.errors.append(
                f"{prefix}: start_time ({start_time}) must be before end_time ({end_time})"
            )

        # Check confidence
        confidence = data.get('confidence', '')
        if confidence and confidence not in self.VALID_CONFIDENCE:
            self.warnings.append(
                f"{prefix}: Invalid confidence '{confidence}' "
                f"(should be: {', '.join(self.VALID_CONFIDENCE)})"
            )

        # Check method
        method = data.get('method', '')
        if method and method not in self.VALID_METHODS:
            self.warnings.append(
                f"{prefix}: Invalid method '{method}' "
                f"(should be one of: {', '.join(self.VALID_METHODS)})"
            )

        # Check for source documentation
        if not data.get('source') and not data.get('source_urls'):
            self.warnings.append(f"{prefix}: Missing source documentation")

    def validate_district(self, district_id, district_data):
        """Validate a single district's data."""
        # Null/type guard (issue #435): a {"id": null} or scalar entry is a
        # data error, not an AttributeError
        if not isinstance(district_data, dict):
            self.errors.append(
                f"District {district_id}: entry must be an object, got "
                f"{type(district_data).__name__}"
            )
            return

        district_name = district_data.get('district_name', 'Unknown')

        # Check required fields
        if not district_data.get('state'):
            self.errors.append(f"District {district_id}: Missing 'state' field")
        elif district_data.get('state') not in self.VALID_STATES:
            self.errors.append(
                f"District {district_id}: Invalid state '{district_data.get('state')}'"
            )

        if not district_data.get('year'):
            self.warnings.append(f"District {district_id}: Missing 'year' field")

        # Validate each grade level
        for grade_level in ['elementary', 'middle', 'high']:
            if grade_level in district_data:
                self.validate_grade_level(
                    district_id,
                    district_name,
                    grade_level,
                    district_data[grade_level]
                )

        # Check enriched flag
        if 'enriched' not in district_data:
            self.warnings.append(f"District {district_id}: Missing 'enriched' flag")
        elif district_data.get('enriched') is not True:
            self.warnings.append(
                f"District {district_id}: enriched flag is {district_data.get('enriched')}, "
                "should be true for manually collected data"
            )

    def validate_file(self, filepath):
        """Validate a JSON file containing bell schedule data."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON: {e}")
            return False
        except FileNotFoundError:
            self.errors.append(f"File not found: {filepath}")
            return False

        if not isinstance(data, dict):
            self.errors.append("Root element must be a dictionary")
            return False

        # Validate each district
        for district_id, district_data in data.items():
            self.validate_district(district_id, district_data)

        return True

    def report(self):
        """Generate validation report."""
        lines = []
        lines.append("=" * 60)
        lines.append("BELL SCHEDULE DATA VALIDATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        if not self.errors and not self.warnings:
            lines.append("✓ ALL CHECKS PASSED")
            lines.append("")
            return "\n".join(lines)

        if self.errors:
            lines.append(f"ERRORS: {len(self.errors)}")
            lines.append("-" * 60)
            for error in self.errors:
                lines.append(f"✗ {error}")
            lines.append("")

        if self.warnings:
            lines.append(f"WARNINGS: {len(self.warnings)}")
            lines.append("-" * 60)
            for warning in self.warnings:
                lines.append(f"⚠ {warning}")
            lines.append("")

        # Summary
        lines.append("=" * 60)
        lines.append("SUMMARY")
        lines.append("=" * 60)
        lines.append(f"Errors: {len(self.errors)}")
        lines.append(f"Warnings: {len(self.warnings)}")

        if self.errors:
            lines.append("\n❌ VALIDATION FAILED - Fix errors before proceeding")
        elif self.warnings and self.strict:
            lines.append("\n❌ STRICT MODE - Fix warnings before proceeding")
        elif self.warnings:
            lines.append("\n⚠ VALIDATION PASSED WITH WARNINGS - Review recommended")
        else:
            lines.append("\n✓ VALIDATION PASSED")

        lines.append("")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Validate bell schedule data before merging',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('input_file', help='JSON file to validate')
    parser.add_argument('--strict', action='store_true',
                       help='Treat warnings as errors')
    parser.add_argument('--report', dest='report_file',
                       help='Write validation report to file')

    args = parser.parse_args()

    # Validate
    validator = BellScheduleValidator(strict=args.strict)
    validator.validate_file(args.input_file)

    # Generate report
    report = validator.report()
    print(report)

    # Write report to file if requested
    if args.report_file:
        with open(args.report_file, 'w') as f:
            f.write(report)
        print(f"\n✓ Report written to {args.report_file}")

    # Exit code
    if validator.errors:
        sys.exit(1)
    elif validator.warnings and args.strict:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
