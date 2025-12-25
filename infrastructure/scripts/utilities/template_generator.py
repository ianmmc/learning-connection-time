#!/usr/bin/env python3
"""
Bell Schedule JSON Template Generator

Generates pre-filled JSON templates for manual bell schedule data entry.

Usage:
    # Single district by ID
    python template_generator.py --id 3800014 --year 2024-25

    # Multiple districts by ID
    python template_generator.py --ids 3800014,3819410,3806780 --year 2024-25

    # From district names (with state)
    python template_generator.py --name "BISMARCK 1" --state ND --year 2024-25

    # From file (one district ID or "Name, STATE" per line)
    python template_generator.py --file districts.txt --year 2024-25

    # Output to file
    python template_generator.py --ids 3800014,3819410,3806780 --year 2024-25 -o north_dakota.json
"""

import pandas as pd
import json
import argparse
import sys
from pathlib import Path


def load_reference_data():
    """Load the enrichment reference CSV."""
    ref_path = Path('data/processed/normalized/enrichment_reference.csv')

    if not ref_path.exists():
        print(f"Error: Reference file not found at {ref_path}", file=sys.stderr)
        sys.exit(1)

    return pd.read_csv(ref_path)


def create_template(district_id, district_name, state, year, enrollment=None):
    """Create a bell schedule JSON template for a district."""
    template = {
        str(district_id): {
            "district_id": str(district_id),
            "district_name": district_name,
            "state": state,
            "year": year,
            "elementary": {
                "instructional_minutes": None,
                "start_time": "",
                "end_time": "",
                "lunch_duration": None,
                "passing_periods": None,
                "schools_sampled": [],
                "source_urls": [],
                "confidence": "",  # high, medium, low
                "method": "human_provided",
                "source": ""
            },
            "middle": {
                "instructional_minutes": None,
                "start_time": "",
                "end_time": "",
                "lunch_duration": None,
                "passing_periods": None,
                "schools_sampled": [],
                "source_urls": [],
                "confidence": "",
                "method": "human_provided",
                "source": ""
            },
            "high": {
                "instructional_minutes": None,
                "start_time": "",
                "end_time": "",
                "lunch_duration": None,
                "passing_periods": None,
                "schools_sampled": [],
                "source_urls": [],
                "confidence": "",
                "method": "human_provided",
                "source": ""
            },
            "enriched": True
        }
    }

    # Add enrollment as a comment if provided
    if enrollment:
        template[str(district_id)]["_comment_enrollment"] = f"{int(enrollment):,} students"

    return template


def lookup_district(df, district_id=None, name=None, state=None):
    """Look up district metadata from reference CSV."""
    if district_id:
        result = df[df['district_id'].astype(str) == str(district_id)]
    elif name and state:
        result = df[(df['district_name'].str.lower() == name.lower()) &
                   (df['state'] == state.upper())]
    else:
        return None

    if result.empty:
        return None

    row = result.iloc[0]
    return {
        'district_id': row['district_id'],
        'district_name': row['district_name'],
        'state': row['state'],
        'enrollment': row.get('enrollment_total', row.get('enrollment', None))
    }


def main():
    parser = argparse.ArgumentParser(
        description='Generate JSON templates for bell schedule data entry',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--id', dest='district_id', help='Single district ID')
    parser.add_argument('--ids', help='Comma-separated district IDs')
    parser.add_argument('--name', help='District name')
    parser.add_argument('--state', help='Two-letter state code (with --name)')
    parser.add_argument('--file', dest='input_file', help='File with district IDs or "Name, STATE" (one per line)')
    parser.add_argument('--year', required=True, help='School year (e.g., 2024-25)')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON (default: True)', default=True)

    args = parser.parse_args()

    # Load reference data
    df = load_reference_data()

    # Collect all districts to process
    districts_to_process = []

    if args.district_id:
        # Single district by ID
        districts_to_process.append({'district_id': args.district_id})

    elif args.ids:
        # Multiple districts by ID
        for did in args.ids.split(','):
            districts_to_process.append({'district_id': did.strip()})

    elif args.name and args.state:
        # Single district by name
        districts_to_process.append({'name': args.name, 'state': args.state})

    elif args.input_file:
        # Read from file
        with open(args.input_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Try to parse as "Name, STATE" or just ID
                if ',' in line:
                    parts = [p.strip() for p in line.split(',')]
                    districts_to_process.append({'name': parts[0], 'state': parts[1]})
                else:
                    districts_to_process.append({'district_id': line})

    else:
        parser.print_help()
        sys.exit(1)

    # Generate templates
    all_templates = {}

    for spec in districts_to_process:
        district_info = lookup_district(
            df,
            district_id=spec.get('district_id'),
            name=spec.get('name'),
            state=spec.get('state')
        )

        if not district_info:
            print(f"Warning: Could not find district: {spec}", file=sys.stderr)
            continue

        template = create_template(
            district_id=district_info['district_id'],
            district_name=district_info['district_name'],
            state=district_info['state'],
            year=args.year,
            enrollment=district_info.get('enrollment')
        )

        all_templates.update(template)

        print(f"✓ Created template for {district_info['district_name']} ({district_info['state']})",
              file=sys.stderr)

    # Output JSON
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(all_templates, f, indent=2 if args.pretty else None)
        print(f"\n✓ Wrote {len(all_templates)} templates to {output_path}", file=sys.stderr)
    else:
        print(json.dumps(all_templates, indent=2 if args.pretty else None))


if __name__ == '__main__':
    main()
