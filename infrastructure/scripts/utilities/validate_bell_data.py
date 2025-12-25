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


class BellScheduleValidator:
    """Validates bell schedule data quality."""

    # Valid values
    VALID_CONFIDENCE = ['high', 'medium', 'low']
    VALID_METHODS = ['human_provided', 'web_scraping', 'pdf_extraction',
                     'school_sample', 'district_policy', 'automated_enrichment',
                     'manual_data_collection', 'state_statutory']
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
        """Check if time string is in valid format (e.g., '8:00 AM')."""
        if not time_str:
            return False

        parts = time_str.split()
        if len(parts) != 2:
            return False

        time_part, meridiem = parts
        if meridiem not in ['AM', 'PM']:
            return False

        if ':' not in time_part:
            return False

        return True

    def validate_minutes(self, minutes, grade_level):
        """Validate instructional minutes are reasonable."""
        if minutes is None:
            return "Missing", "instructional_minutes is null"

        if not isinstance(minutes, (int, float)):
            return "Error", f"instructional_minutes must be numeric, got {type(minutes)}"

        if minutes < 180:
            return "Error", f"instructional_minutes ({minutes}) is too low (< 180 min = 3 hours)"

        if minutes > 480:
            return "Error", f"instructional_minutes ({minutes}) is too high (> 480 min = 8 hours)"

        if minutes < 240:
            return "Warning", f"instructional_minutes ({minutes}) seems low for {grade_level}"

        if minutes > 420:
            return "Warning", f"instructional_minutes ({minutes}) seems high for {grade_level}"

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

        if start_time and not self.validate_time_format(start_time):
            self.warnings.append(f"{prefix}: Invalid start_time format: '{start_time}'")

        if end_time and not self.validate_time_format(end_time):
            self.warnings.append(f"{prefix}: Invalid end_time format: '{end_time}'")

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
