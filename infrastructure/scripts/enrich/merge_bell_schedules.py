#!/usr/bin/env python3
"""
Merge bell schedule data with normalized district data

This script enriches district data by merging manually collected bell schedules
with normalized district data. Where actual bell schedules are available, it uses
those instructional minutes; otherwise, it falls back to state statutory requirements.

Supports loading bell schedules from:
- A single consolidated JSON file with district IDs as keys
- A directory containing individual district JSON files (loads all .json files)
- Mixed: directory can contain both consolidated and individual files

Usage:
    python merge_bell_schedules.py <districts_file> [options]

    Options:
        --bell-schedules PATH   Path to bell schedules JSON file or directory (default: data/enriched/bell-schedules/)
        --output PATH           Output file path (default: auto-generated)
        --year YEAR            School year (e.g., "2024-25")

Examples:
    # Merge all bell schedules from directory (default)
    python merge_bell_schedules.py data/processed/normalized/districts_2023_24_nces.csv

    # Specify custom bell schedules file
    python merge_bell_schedules.py data/processed/normalized/districts_2023_24_nces.csv \
        --bell-schedules data/enriched/bell-schedules/custom_schedules.json

    # Load from specific directory
    python merge_bell_schedules.py data/processed/normalized/districts_2023_24_nces.csv \
        --bell-schedules data/enriched/bell-schedules/
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import yaml
import json

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "utilities"))
from common import DataProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BellScheduleMerger(DataProcessor):
    """Merges bell schedule data with normalized district data"""

    def __init__(self, bell_schedules_path: Path, year: str = "2024-25"):
        """
        Initialize the bell schedule merger.

        Args:
            bell_schedules_path: Path to bell schedules JSON file
            year: School year for bell schedules
        """
        super().__init__()
        self.bell_schedules_path = bell_schedules_path
        self.year = year
        self.bell_schedules = {}
        self.state_requirements = {}

    def load_bell_schedules(self):
        """Load bell schedule data from JSON file or directory

        Supports two modes:
        1. Single consolidated JSON file with district IDs as keys
        2. Directory containing individual district JSON files
        """
        if not self.bell_schedules_path.exists():
            logger.warning(f"Bell schedules path not found: {self.bell_schedules_path}")
            return

        self.bell_schedules = {}

        # If it's a directory, load all JSON files
        if self.bell_schedules_path.is_dir():
            logger.info(f"Loading bell schedules from directory: {self.bell_schedules_path}")
            json_files = list(self.bell_schedules_path.glob("*.json"))

            # Filter out files we don't want to load
            excluded_patterns = ['manual_followup', 'tier3_statutory_fallback']
            json_files = [
                f for f in json_files
                if not any(pattern in f.name for pattern in excluded_patterns)
            ]

            for json_file in json_files:
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)

                    # Check if this is an individual district file or consolidated file
                    if 'district_id' in data:
                        # Individual district file
                        # Skip if this is statutory fallback data (enriched=False)
                        if data.get('enriched', True) == False:
                            continue

                        district_id = str(data['district_id'])
                        self.bell_schedules[district_id] = data
                    elif isinstance(data, dict):
                        # Consolidated file with district IDs as keys - merge it
                        for district_id, district_data in data.items():
                            # Skip statutory fallback entries
                            if district_data.get('enriched', True) == False:
                                continue
                            self.bell_schedules[str(district_id)] = district_data
                    else:
                        logger.warning(f"Skipping {json_file.name}: unexpected format")

                except Exception as e:
                    logger.warning(f"Error loading {json_file.name}: {e}")
                    continue

            logger.info(f"  Loaded bell schedules for {len(self.bell_schedules)} districts from {len(json_files)} files")

        # If it's a file, load the single consolidated JSON
        else:
            logger.info(f"Loading bell schedules from file: {self.bell_schedules_path}")
            with open(self.bell_schedules_path, 'r') as f:
                data = json.load(f)

            # Check format
            if 'district_id' in data:
                # Individual district file
                district_id = str(data['district_id'])
                self.bell_schedules[district_id] = data
                logger.info(f"  Loaded bell schedule for 1 district")
            else:
                # Consolidated file with district IDs as keys
                self.bell_schedules = data
                logger.info(f"  Loaded bell schedules for {len(self.bell_schedules)} districts")

    def load_state_requirements(self):
        """Load state statutory requirements as fallback"""
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "state-requirements.yaml"

        if not config_path.exists():
            logger.warning(f"State requirements not found: {config_path}")
            return

        logger.info(f"Loading state requirements from {config_path}")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            states_by_name = config.get('states', {})

        # Create lookup by state code (AL, CA, etc.) for easier access
        self.state_requirements = {}
        for state_name, state_data in states_by_name.items():
            state_code = state_data.get('code', '').upper()
            if state_code:
                self.state_requirements[state_code] = state_data

        logger.info(f"  Loaded state requirements for {len(self.state_requirements)} states")

    def get_instructional_minutes(
        self,
        district_id: str,
        state: str,
        grade_level: str = 'elementary'
    ) -> tuple[Optional[int], str, str, str]:
        """
        Get instructional minutes for a district, preferring actual bell schedules

        Args:
            district_id: District ID
            state: State abbreviation
            grade_level: Grade level (elementary, middle, high)

        Returns:
            Tuple of (minutes, source, confidence, method)
        """
        # First, try to get from bell schedules
        if str(district_id) in self.bell_schedules:
            district_data = self.bell_schedules[str(district_id)]

            # Map grade_level to expected keys
            level_key = grade_level
            if grade_level == 'middle':
                level_key = 'middle'
            elif grade_level == 'high':
                level_key = 'high'

            if level_key in district_data and district_data[level_key] is not None:
                level_data = district_data[level_key]
                minutes = level_data.get('instructional_minutes')
                if minutes:
                    source = level_data.get('source', 'Actual bell schedule')
                    confidence = level_data.get('confidence', 'high')
                    method = level_data.get('method', 'unknown')
                    return minutes, source, confidence, method

        # Fall back to state statutory requirements
        # Handle NaN values (which are floats)
        if pd.isna(state) or not isinstance(state, str):
            state_upper = None
        else:
            state_upper = state.upper()

        if state_upper and state_upper in self.state_requirements:
            state_data = self.state_requirements[state_upper]

            # Try to get specific grade level
            level_key = grade_level if grade_level == 'elementary' else f"{grade_level}_school"
            if level_key in state_data:
                minutes = state_data[level_key]
                source = state_data.get('reference', 'State statute')
                return minutes, source, 'statutory', 'state_statutory'

            # Try elementary as default
            if 'elementary' in state_data:
                minutes = state_data['elementary']
                source = state_data.get('reference', 'State statute')
                return minutes, source, 'statutory', 'state_statutory'

        # Default to 300 minutes
        return 300, 'Default assumption (5-hour day)', 'assumed', 'default'

    def merge_data(self, districts_df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge bell schedule data with district data

        Args:
            districts_df: DataFrame with normalized district data

        Returns:
            DataFrame with grade-level instructional minutes added
        """
        logger.info("Merging bell schedule data with district data...")

        # Ensure district_id is string for matching
        districts_df['district_id'] = districts_df['district_id'].astype(str)

        # Add columns for instructional minutes by grade level
        grade_levels = ['elementary', 'middle', 'high']

        for grade_level in grade_levels:
            districts_df[f'daily_instructional_minutes_{grade_level}'] = None
            districts_df[f'minutes_source_{grade_level}'] = None
            districts_df[f'minutes_confidence_{grade_level}'] = None
            districts_df[f'minutes_method_{grade_level}'] = None

        # Track statistics by grade level
        stats = {
            'elementary': {'actual': 0, 'statutory': 0, 'assumed': 0},
            'middle': {'actual': 0, 'statutory': 0, 'assumed': 0},
            'high': {'actual': 0, 'statutory': 0, 'assumed': 0}
        }

        # Process each district for all grade levels
        for idx, row in districts_df.iterrows():
            district_id = str(row['district_id'])
            state = row.get('state', '')

            # Get instructional minutes for each grade level
            for grade_level in grade_levels:
                minutes, source, confidence, method = self.get_instructional_minutes(
                    district_id, state, grade_level
                )

                # Update dataframe
                districts_df.at[idx, f'daily_instructional_minutes_{grade_level}'] = minutes
                districts_df.at[idx, f'minutes_source_{grade_level}'] = source
                districts_df.at[idx, f'minutes_confidence_{grade_level}'] = confidence
                districts_df.at[idx, f'minutes_method_{grade_level}'] = method

                # Track statistics - CRITICAL: Check method, not confidence
                # This ensures statutory data isn't counted as "actual" even if confidence is high/medium
                if method != 'state_statutory' and method != 'default':
                    stats[grade_level]['actual'] += 1
                elif method == 'state_statutory':
                    stats[grade_level]['statutory'] += 1
                else:
                    stats[grade_level]['assumed'] += 1

        # Report statistics by grade level
        total = len(districts_df)
        logger.info(f"\nData source breakdown by grade level:")
        for grade_level in grade_levels:
            logger.info(f"\n{grade_level.capitalize()}:")
            logger.info(f"  Actual bell schedules: {stats[grade_level]['actual']:,} ({stats[grade_level]['actual']/total*100:.1f}%)")
            logger.info(f"  State statutory: {stats[grade_level]['statutory']:,} ({stats[grade_level]['statutory']/total*100:.1f}%)")
            logger.info(f"  Assumed (default): {stats[grade_level]['assumed']:,} ({stats[grade_level]['assumed']/total*100:.1f}%)")

        return districts_df

    def process_districts_file(
        self,
        input_file: Path,
        output_file: Path
    ):
        """
        Process districts file and merge bell schedule data

        Args:
            input_file: Path to CSV with normalized district data
            output_file: Path to output CSV with enriched data
        """
        logger.info(f"Processing districts from {input_file}")

        # Load bell schedules and state requirements
        self.load_bell_schedules()
        self.load_state_requirements()

        # Read districts
        df = pd.read_csv(input_file)
        logger.info(f"  Loaded {len(df):,} districts")

        # Validate required columns
        required_cols = ['district_id', 'state']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Merge data
        enriched_df = self.merge_data(df)

        # Save to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        enriched_df.to_csv(output_file, index=False)
        logger.info(f"\nSaved enriched data to {output_file}")

        # Generate summary
        self._generate_summary(enriched_df, output_file)

    def _generate_summary(self, df: pd.DataFrame, output_file: Path):
        """Generate summary statistics for the enrichment process"""
        summary_file = output_file.with_suffix('.txt').with_name(
            output_file.stem + '_summary.txt'
        )

        grade_levels = ['elementary', 'middle', 'high']

        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("BELL SCHEDULE ENRICHMENT SUMMARY\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Total districts processed: {len(df)}\n\n")

            # Summary by grade level
            for grade_level in grade_levels:
                conf_col = f'minutes_confidence_{grade_level}'
                min_col = f'daily_instructional_minutes_{grade_level}'

                f.write("=" * 80 + "\n")
                f.write(f"{grade_level.upper()} SCHOOLS\n")
                f.write("=" * 80 + "\n\n")

                if conf_col in df.columns:
                    f.write("DATA SOURCE BREAKDOWN:\n")
                    counts = df[conf_col].value_counts()
                    for conf, count in counts.items():
                        pct = count / len(df) * 100
                        f.write(f"  {conf}: {count:,} ({pct:.1f}%)\n")

                if min_col in df.columns:
                    f.write("\nINSTRUCTIONAL MINUTES STATISTICS:\n")
                    f.write(f"  Mean: {df[min_col].mean():.1f}\n")
                    f.write(f"  Median: {df[min_col].median():.1f}\n")
                    f.write(f"  Min: {df[min_col].min():.1f}\n")
                    f.write(f"  Max: {df[min_col].max():.1f}\n")
                    f.write(f"  Std Dev: {df[min_col].std():.1f}\n\n")

            f.write("=" * 80 + "\n")

        logger.info(f"Summary saved to {summary_file}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Merge bell schedule data with normalized district data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'districts_file',
        type=Path,
        help='CSV file with normalized district data'
    )

    parser.add_argument(
        '--bell-schedules',
        type=Path,
        help='Path to bell schedules JSON file or directory (default: data/enriched/bell-schedules/ - loads all JSON files)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: auto-generated in data/enriched/)'
    )

    parser.add_argument(
        '--year',
        type=str,
        default='2024-25',
        help='School year (default: 2024-25)'
    )

    args = parser.parse_args()

    # Validate input file
    if not args.districts_file.exists():
        logger.error(f"Input file not found: {args.districts_file}")
        sys.exit(1)

    # Determine bell schedules path (file or directory)
    if args.bell_schedules:
        bell_schedules_path = args.bell_schedules
    else:
        # Default to directory to load all bell schedule files
        bell_schedules_path = Path("data/enriched/bell-schedules/")

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        # Auto-generate output filename
        stem = args.districts_file.stem
        output_file = Path(f"data/enriched/lct-calculations/{stem}_enriched_bell_schedules.csv")

    # Initialize merger
    merger = BellScheduleMerger(
        bell_schedules_path=bell_schedules_path,
        year=args.year
    )

    # Process districts
    merger.process_districts_file(
        input_file=args.districts_file,
        output_file=output_file
    )

    logger.info("\n✓ Bell schedule merge complete!")
    logger.info(f"Output: {output_file}")


if __name__ == '__main__':
    main()
