#!/usr/bin/env python3
"""
Merge bell schedule data with normalized district data

This script enriches district data by merging manually collected bell schedules
with normalized district data. Where actual bell schedules are available, it uses
those instructional minutes; otherwise, it falls back to state statutory requirements.

Usage:
    python merge_bell_schedules.py <districts_file> [options]

    Options:
        --bell-schedules PATH   Path to bell schedules JSON (default: data/enriched/bell-schedules/bell_schedules_manual_collection_2024_25.json)
        --output PATH           Output file path (default: auto-generated)
        --year YEAR            School year (e.g., "2024-25")

Examples:
    # Merge bell schedules with normalized district data
    python merge_bell_schedules.py data/processed/normalized/districts_2023_24_nces.csv

    # Specify custom bell schedules file
    python merge_bell_schedules.py data/processed/normalized/districts_2023_24_nces.csv \
        --bell-schedules data/enriched/bell-schedules/custom_schedules.json
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
        """Load bell schedule data from JSON file"""
        if not self.bell_schedules_path.exists():
            logger.warning(f"Bell schedules file not found: {self.bell_schedules_path}")
            return

        logger.info(f"Loading bell schedules from {self.bell_schedules_path}")
        with open(self.bell_schedules_path, 'r') as f:
            data = json.load(f)

        # The JSON has district IDs as keys
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
            self.state_requirements = config.get('states', {})

        logger.info(f"  Loaded state requirements for {len(self.state_requirements)} states")

    def get_instructional_minutes(
        self,
        district_id: str,
        state: str,
        grade_level: str = 'elementary'
    ) -> tuple[Optional[int], str, str]:
        """
        Get instructional minutes for a district, preferring actual bell schedules

        Args:
            district_id: District ID
            state: State abbreviation
            grade_level: Grade level (elementary, middle, high)

        Returns:
            Tuple of (minutes, source, confidence)
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
                    return minutes, source, confidence

        # Fall back to state statutory requirements
        state_lower = state.lower() if state else None
        if state_lower in self.state_requirements:
            state_data = self.state_requirements[state_lower]

            # Try to get specific grade level
            level_key = grade_level if grade_level == 'elementary' else f"{grade_level}_school"
            if level_key in state_data:
                minutes = state_data[level_key]
                source = state_data.get('source', 'State statute')
                return minutes, source, 'statutory'

            # Try elementary as default
            if 'elementary' in state_data:
                minutes = state_data['elementary']
                source = state_data.get('source', 'State statute')
                return minutes, source, 'statutory'

        # Default to 360 minutes
        return 360, 'Default assumption (6-hour day)', 'assumed'

    def merge_data(self, districts_df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge bell schedule data with district data

        Args:
            districts_df: DataFrame with normalized district data

        Returns:
            DataFrame with daily_instructional_minutes added
        """
        logger.info("Merging bell schedule data with district data...")

        # Ensure district_id is string for matching
        districts_df['district_id'] = districts_df['district_id'].astype(str)

        # Add columns for instructional minutes and metadata
        districts_df['daily_instructional_minutes'] = None
        districts_df['minutes_source'] = None
        districts_df['minutes_confidence'] = None

        # Track statistics
        actual_count = 0
        statutory_count = 0
        assumed_count = 0

        # Process each district
        for idx, row in districts_df.iterrows():
            district_id = str(row['district_id'])
            state = row.get('state', '')

            # Determine grade level (default to elementary for district-level data)
            grade_level = row.get('grade_level', 'elementary')

            # Get instructional minutes
            minutes, source, confidence = self.get_instructional_minutes(
                district_id, state, grade_level
            )

            # Update dataframe
            districts_df.at[idx, 'daily_instructional_minutes'] = minutes
            districts_df.at[idx, 'minutes_source'] = source
            districts_df.at[idx, 'minutes_confidence'] = confidence

            # Track statistics
            if confidence == 'high':
                actual_count += 1
            elif confidence == 'statutory':
                statutory_count += 1
            else:
                assumed_count += 1

        # Report statistics
        total = len(districts_df)
        logger.info(f"\nData source breakdown:")
        logger.info(f"  Actual bell schedules: {actual_count:,} ({actual_count/total*100:.1f}%)")
        logger.info(f"  State statutory: {statutory_count:,} ({statutory_count/total*100:.1f}%)")
        logger.info(f"  Assumed (default): {assumed_count:,} ({assumed_count/total*100:.1f}%)")

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

        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("BELL SCHEDULE ENRICHMENT SUMMARY\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Total districts processed: {len(df)}\n\n")

            f.write("DATA SOURCE BREAKDOWN:\n")
            if 'minutes_confidence' in df.columns:
                counts = df['minutes_confidence'].value_counts()
                for conf, count in counts.items():
                    pct = count / len(df) * 100
                    f.write(f"  {conf}: {count:,} ({pct:.1f}%)\n")

            f.write("\nINSTRUCTIONAL MINUTES STATISTICS:\n")
            if 'daily_instructional_minutes' in df.columns:
                f.write(f"  Mean: {df['daily_instructional_minutes'].mean():.1f}\n")
                f.write(f"  Median: {df['daily_instructional_minutes'].median():.1f}\n")
                f.write(f"  Min: {df['daily_instructional_minutes'].min():.1f}\n")
                f.write(f"  Max: {df['daily_instructional_minutes'].max():.1f}\n")
                f.write(f"  Std Dev: {df['daily_instructional_minutes'].std():.1f}\n")

            f.write("\n" + "=" * 80 + "\n")

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
        help='Path to bell schedules JSON file (default: data/enriched/bell-schedules/bell_schedules_manual_collection_2024_25.json)'
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

    # Determine bell schedules file
    if args.bell_schedules:
        bell_schedules_path = args.bell_schedules
    else:
        bell_schedules_path = Path("data/enriched/bell-schedules/bell_schedules_manual_collection_2024_25.json")

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
