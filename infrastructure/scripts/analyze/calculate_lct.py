#!/usr/bin/env python3
"""
Calculate Learning Connection Time (LCT) for districts

This script takes processed district data and calculates the Learning Connection Time metric,
which represents the potential individual attention time per student per day.

Formula: LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment

Usage:
    python calculate_lct.py <input_file> [--output <output_file>] [--state-config <yaml>]
    
Example:
    python calculate_lct.py data/processed/normalized/districts_2023-24.csv
    python calculate_lct.py data/processed/normalized/districts_2023-24.csv --output data/enriched/lct-calculations/lct_results.csv
"""

import argparse
import logging
from pathlib import Path
import pandas as pd
import sys
import yaml
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_state_requirements(config_path: Path) -> dict:
    """
    Load state instructional time requirements
    
    Args:
        config_path: Path to state requirements YAML file
    
    Returns:
        Dictionary of state requirements
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('states', {})
    except Exception as e:
        logger.warning(f"Could not load state requirements: {e}")
        return {}


def get_daily_minutes(state: str, grade_level: Optional[str], state_config: dict) -> int:
    """
    Get daily instructional minutes for a state and grade level
    
    Args:
        state: State abbreviation (e.g., 'CA', 'TX')
        grade_level: Grade level category (e.g., 'elementary', 'high_school')
        state_config: State requirements configuration
    
    Returns:
        Daily instructional minutes (returns 360 as default if not found)
    """
    state_lower = state.lower() if state else None
    
    if state_lower in state_config:
        state_data = state_config[state_lower]
        
        # Try to get specific grade level
        if grade_level and grade_level in state_data:
            return state_data[grade_level]
        
        # Try to get 'elementary' as default
        if 'elementary' in state_data:
            return state_data['elementary']
        
        # Return first numeric value found
        for value in state_data.values():
            if isinstance(value, (int, float)):
                return int(value)
    
    # Default to 6-hour day (360 minutes)
    logger.debug(f"Using default 360 minutes for state: {state}")
    return 360


def calculate_lct(
    enrollment: float,
    instructional_staff: float,
    daily_minutes: float
) -> float:
    """
    Calculate Learning Connection Time
    
    LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
    
    Args:
        enrollment: Total student enrollment
        instructional_staff: Number of instructional staff
        daily_minutes: Daily instructional minutes
    
    Returns:
        LCT in minutes per student per day (0 if enrollment is 0)
    """
    if enrollment == 0 or pd.isna(enrollment):
        return 0.0
    
    if pd.isna(instructional_staff) or pd.isna(daily_minutes):
        return 0.0
    
    total_instructional_minutes = daily_minutes * instructional_staff
    lct = total_instructional_minutes / enrollment
    
    return round(lct, 2)


def add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived metrics based on LCT
    
    Args:
        df: DataFrame with LCT calculations
    
    Returns:
        DataFrame with additional metrics
    """
    # Convert to hours
    df['lct_hours'] = (df['lct_minutes'] / 60).round(2)
    
    # Traditional student-teacher ratio for comparison
    df['student_teacher_ratio'] = (
        df['enrollment'] / df['instructional_staff']
    ).round(1)
    
    # Calculate percentile rankings
    df['lct_percentile'] = df['lct_minutes'].rank(pct=True).mul(100).round(1)
    
    # Categorize LCT levels
    def categorize_lct(minutes):
        if pd.isna(minutes) or minutes == 0:
            return 'Unknown'
        elif minutes < 15:
            return 'Very Low (<15 min)'
        elif minutes < 20:
            return 'Low (15-20 min)'
        elif minutes < 25:
            return 'Moderate (20-25 min)'
        elif minutes < 30:
            return 'High (25-30 min)'
        else:
            return 'Very High (>30 min)'
    
    df['lct_category'] = df['lct_minutes'].apply(categorize_lct)
    
    return df


def generate_summary_stats(df: pd.DataFrame) -> dict:
    """
    Generate summary statistics for LCT analysis
    
    Args:
        df: DataFrame with LCT calculations
    
    Returns:
        Dictionary of summary statistics
    """
    valid_lct = df[df['lct_minutes'] > 0]['lct_minutes']
    
    stats = {
        'total_districts': len(df),
        'districts_with_lct': len(valid_lct),
        'min_lct': valid_lct.min() if len(valid_lct) > 0 else 0,
        'max_lct': valid_lct.max() if len(valid_lct) > 0 else 0,
        'mean_lct': valid_lct.mean() if len(valid_lct) > 0 else 0,
        'median_lct': valid_lct.median() if len(valid_lct) > 0 else 0,
        'std_lct': valid_lct.std() if len(valid_lct) > 0 else 0,
    }
    
    # State-level summaries
    if 'state' in df.columns:
        state_stats = df[df['lct_minutes'] > 0].groupby('state')['lct_minutes'].agg([
            ('mean', 'mean'),
            ('median', 'median'),
            ('count', 'count')
        ]).round(2)
        stats['by_state'] = state_stats.to_dict('index')
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Calculate Learning Connection Time (LCT) for districts",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "input_file",
        type=Path,
        help="Processed district data file (CSV)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for results (default: adds '_with_lct' suffix)"
    )
    parser.add_argument(
        "--state-config",
        type=Path,
        help="Path to state requirements YAML (default: config/state-requirements.yaml)"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Generate summary statistics report"
    )
    
    args = parser.parse_args()
    
    # Load input data
    if not args.input_file.exists():
        logger.error(f"Input file not found: {args.input_file}")
        return 1
    
    logger.info(f"Loading district data from {args.input_file}")
    try:
        df = pd.read_csv(args.input_file)
        logger.info(f"  Loaded {len(df):,} districts")
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return 1
    
    # Load state requirements
    if args.state_config:
        config_path = args.state_config
    else:
        # Default to project structure
        script_dir = Path(__file__).parent
        config_path = script_dir.parent.parent.parent / "config" / "state-requirements.yaml"
    
    state_config = load_state_requirements(config_path)
    logger.info(f"  Loaded state requirements for {len(state_config)} states")
    
    # Ensure required columns exist
    required_cols = ['enrollment', 'instructional_staff']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        logger.error(f"Missing required columns: {', '.join(missing_cols)}")
        logger.info(f"Available columns: {', '.join(df.columns)}")
        return 1
    
    # Add daily_minutes if not present
    if 'daily_instructional_minutes' not in df.columns:
        logger.info("Calculating daily instructional minutes from state requirements...")
        
        if 'state' not in df.columns:
            logger.error("Need either 'daily_instructional_minutes' or 'state' column")
            return 1
        
        df['daily_instructional_minutes'] = df.apply(
            lambda row: get_daily_minutes(
                row.get('state'),
                row.get('grade_level'),
                state_config
            ),
            axis=1
        )
    
    # Calculate LCT
    logger.info("Calculating Learning Connection Time...")
    df['lct_minutes'] = df.apply(
        lambda row: calculate_lct(
            row['enrollment'],
            row['instructional_staff'],
            row['daily_instructional_minutes']
        ),
        axis=1
    )
    
    # Add derived metrics
    logger.info("Adding derived metrics...")
    df = add_derived_metrics(df)
    
    # Determine output path
    if args.output:
        output_file = args.output
    else:
        output_file = args.input_file.parent / f"{args.input_file.stem}_with_lct.csv"
    
    # Create output directory if needed
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Save results
    df.to_csv(output_file, index=False)
    logger.info(f"✓ Results saved to: {output_file}")
    
    # Generate summary statistics
    stats = generate_summary_stats(df)
    
    logger.info("\n" + "="*60)
    logger.info("LEARNING CONNECTION TIME ANALYSIS")
    logger.info("="*60)
    logger.info(f"Total Districts: {stats['total_districts']:,}")
    logger.info(f"Districts with LCT: {stats['districts_with_lct']:,}")
    logger.info(f"\nLCT Statistics:")
    logger.info(f"  Minimum: {stats['min_lct']:.1f} minutes ({stats['min_lct']/60:.1f} hours)")
    logger.info(f"  Maximum: {stats['max_lct']:.1f} minutes ({stats['max_lct']/60:.1f} hours)")
    logger.info(f"  Mean:    {stats['mean_lct']:.1f} minutes ({stats['mean_lct']/60:.1f} hours)")
    logger.info(f"  Median:  {stats['median_lct']:.1f} minutes ({stats['median_lct']/60:.1f} hours)")
    logger.info(f"  Std Dev: {stats['std_lct']:.1f} minutes")
    
    # Save summary if requested
    if args.summary:
        summary_file = output_file.parent / f"{output_file.stem}_summary.txt"
        with open(summary_file, 'w') as f:
            f.write("="*60 + "\n")
            f.write("LEARNING CONNECTION TIME ANALYSIS SUMMARY\n")
            f.write("="*60 + "\n\n")
            f.write(f"Total Districts: {stats['total_districts']:,}\n")
            f.write(f"Districts with LCT: {stats['districts_with_lct']:,}\n\n")
            f.write("LCT Statistics:\n")
            f.write(f"  Minimum: {stats['min_lct']:.1f} minutes\n")
            f.write(f"  Maximum: {stats['max_lct']:.1f} minutes\n")
            f.write(f"  Mean:    {stats['mean_lct']:.1f} minutes\n")
            f.write(f"  Median:  {stats['median_lct']:.1f} minutes\n")
            f.write(f"  Std Dev: {stats['std_lct']:.1f} minutes\n")
            
            if 'by_state' in stats:
                f.write("\n" + "="*60 + "\n")
                f.write("STATE-LEVEL SUMMARY\n")
                f.write("="*60 + "\n\n")
                for state, state_stats in stats['by_state'].items():
                    f.write(f"{state}:\n")
                    f.write(f"  Mean LCT:   {state_stats['mean']:.1f} minutes\n")
                    f.write(f"  Median LCT: {state_stats['median']:.1f} minutes\n")
                    f.write(f"  Districts:  {state_stats['count']}\n\n")
        
        logger.info(f"✓ Summary saved to: {summary_file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
