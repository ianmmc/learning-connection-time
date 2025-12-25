#!/usr/bin/env python3
"""
District Lookup Tool

Quickly find district IDs, names, and metadata for bell schedule enrichment.

Usage:
    # Single lookup by name
    python district_lookup.py "Baldwin County" AL

    # Lookup by ID
    python district_lookup.py --id 100270

    # Multiple lookups from file (one per line: "District Name, STATE")
    python district_lookup.py --file districts.txt

    # Search within a state
    python district_lookup.py --search "County" --state AL
"""

import pandas as pd
import argparse
import sys
from pathlib import Path
from difflib import get_close_matches


def load_reference_data():
    """Load the enrichment reference CSV."""
    ref_path = Path('data/processed/normalized/enrichment_reference.csv')

    if not ref_path.exists():
        print(f"Error: Reference file not found at {ref_path}", file=sys.stderr)
        print("Run the normalization script first to generate this file.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(ref_path)
    return df


def lookup_by_id(df, district_id):
    """Look up district by ID."""
    result = df[df['district_id'].astype(str) == str(district_id)]
    return result


def lookup_by_name(df, name, state=None, fuzzy=True):
    """Look up district by name with optional fuzzy matching."""
    # Filter by state first if provided
    search_df = df[df['state'] == state.upper()] if state else df

    # Try exact match first
    exact = search_df[search_df['district_name'].str.lower() == name.lower()]
    if not exact.empty:
        return exact

    # Try contains match
    contains = search_df[search_df['district_name'].str.contains(name, case=False, na=False)]
    if not contains.empty:
        return contains

    # Try fuzzy match if enabled
    if fuzzy:
        all_names = search_df['district_name'].tolist()
        matches = get_close_matches(name, all_names, n=3, cutoff=0.6)
        if matches:
            return search_df[search_df['district_name'].isin(matches)]

    return pd.DataFrame()


def format_output(df, verbose=False):
    """Format district information for display."""
    if df.empty:
        print("No districts found.", file=sys.stderr)
        return

    for _, row in df.iterrows():
        print(f"ID: {row['district_id']}")
        print(f"Name: {row['district_name']}")
        print(f"State: {row['state']}")
        enrollment = row.get('enrollment_total', row.get('enrollment', 0))
        print(f"Enrollment: {int(enrollment):,}")

        if verbose:
            print(f"Enriched: {row.get('enriched', 'Unknown')}")
            if 'instructional_staff' in row:
                print(f"Instructional Staff: {int(row['instructional_staff']):,}")

        print()  # Blank line between results


def search_districts(df, search_term, state=None):
    """Search for districts matching a term."""
    search_df = df[df['state'] == state.upper()] if state else df
    results = search_df[search_df['district_name'].str.contains(search_term, case=False, na=False)]
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Look up district metadata for bell schedule enrichment',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('name', nargs='?', help='District name to look up')
    parser.add_argument('state', nargs='?', help='Two-letter state code')
    parser.add_argument('--id', dest='district_id', help='Look up by district ID')
    parser.add_argument('--file', dest='input_file', help='File with district names (one per line)')
    parser.add_argument('--search', help='Search for districts containing this term')
    parser.add_argument('--state', dest='state_filter', help='Filter results by state')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show additional details')
    parser.add_argument('--top', type=int, metavar='N', help='Show top N districts by enrollment in state')

    args = parser.parse_args()

    # Load reference data
    df = load_reference_data()

    # Handle different lookup modes
    if args.district_id:
        # Lookup by ID
        result = lookup_by_id(df, args.district_id)
        format_output(result, args.verbose)

    elif args.input_file:
        # Batch lookup from file
        with open(args.input_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Parse "District Name, STATE" or just "District Name"
                parts = [p.strip() for p in line.split(',')]
                name = parts[0]
                state = parts[1] if len(parts) > 1 else None

                print(f"Looking up: {name} ({state or 'any state'})")
                result = lookup_by_name(df, name, state)
                format_output(result, args.verbose)
                print("-" * 50)

    elif args.search:
        # Search mode
        result = search_districts(df, args.search, args.state_filter)
        print(f"Found {len(result)} districts matching '{args.search}'")
        if args.state_filter:
            print(f"in state {args.state_filter}")
        print()
        format_output(result, args.verbose)

    elif args.top and args.state_filter:
        # Top N districts in a state
        state_df = df[df['state'] == args.state_filter.upper()]
        enrollment_col = 'enrollment_total' if 'enrollment_total' in df.columns else 'enrollment'
        top_districts = state_df.nlargest(args.top, enrollment_col)
        print(f"Top {args.top} districts in {args.state_filter}:")
        print()
        format_output(top_districts, args.verbose)

    elif args.name:
        # Name-based lookup
        result = lookup_by_name(df, args.name, args.state)
        format_output(result, args.verbose)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
