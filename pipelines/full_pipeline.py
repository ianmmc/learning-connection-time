#!/usr/bin/env python3
"""
Full data processing pipeline for Learning Connection Time analysis

This pipeline orchestrates the complete data flow:
1. Download data (optional)
2. Extract and combine multi-part files
3. Normalize to standard schema
4. Calculate LCT metrics
5. Generate reports

Usage:
    python full_pipeline.py --year 2023-24 [--skip-download] [--sample]
    
Example:
    python full_pipeline.py --year 2023-24 --sample
    python full_pipeline.py --year 2023-24 --skip-download
"""

import argparse
import logging
from pathlib import Path
import sys
import subprocess
from datetime import datetime

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent / "infrastructure" / "utilities"))
from common import get_project_root, setup_logging

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Orchestrate the full data processing pipeline
    """
    
    def __init__(self, year: str, sample: bool = False, skip_download: bool = False):
        """
        Initialize pipeline
        
        Args:
            year: School year (e.g., "2023-24")
            sample: Use sample data only
            skip_download: Skip download step
        """
        self.year = year
        self.sample = sample
        self.skip_download = skip_download
        
        self.root = get_project_root()
        self.scripts_dir = self.root / "infrastructure" / "scripts"
        
        self.steps_completed = []
        self.steps_failed = []
    
    def run_script(self, script_path: Path, args: list = None) -> bool:
        """
        Run a Python script and capture output
        
        Args:
            script_path: Path to script
            args: List of command-line arguments
        
        Returns:
            True if script succeeded
        """
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Log output
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        logger.info(f"  | {line}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Script failed with exit code {e.returncode}")
            if e.stderr:
                logger.error(f"Error output:\n{e.stderr}")
            return False
    
    def step_download(self) -> bool:
        """
        Step 1: Download data
        
        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 1: DOWNLOAD DATA")
        logger.info("="*60)
        
        if self.skip_download:
            logger.info("Skipping download step (--skip-download)")
            return True
        
        script = self.scripts_dir / "download" / "fetch_nces_ccd.py"
        args = ["--year", self.year]
        
        if self.sample:
            args.append("--sample")
        
        return self.run_script(script, args)
    
    def step_extract(self) -> bool:
        """
        Step 2: Extract and combine multi-part files
        
        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 2: EXTRACT AND COMBINE FILES")
        logger.info("="*60)
        
        # Check if there are multi-part files
        data_dir = self.root / "data" / "raw" / "federal" / "nces-ccd" / self.year.replace("-", "_")
        
        if not data_dir.exists():
            logger.warning(f"Data directory not found: {data_dir}")
            logger.info("Skipping extraction step")
            return True
        
        # Look for multi-part files
        multipart_files = list(data_dir.glob("*_[0-9]*.*"))
        
        if not multipart_files:
            logger.info("No multi-part files found, skipping extraction")
            return True
        
        script = self.scripts_dir / "extract" / "split_large_files.py"
        args = [str(data_dir)]
        
        return self.run_script(script, args)
    
    def step_normalize(self) -> bool:
        """
        Step 3: Normalize data to standard schema
        
        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 3: NORMALIZE DATA")
        logger.info("="*60)
        
        # Find input file
        data_dir = self.root / "data" / "raw" / "federal" / "nces-ccd" / self.year.replace("-", "_")
        
        if self.sample:
            input_file = data_dir / "sample_districts.csv"
        else:
            # Look for combined or regular files
            candidates = list(data_dir.glob("*_combined.csv")) or list(data_dir.glob("*.csv"))
            if not candidates:
                logger.error(f"No CSV files found in {data_dir}")
                return False
            input_file = candidates[0]
        
        if not input_file.exists():
            logger.error(f"Input file not found: {input_file}")
            return False
        
        script = self.scripts_dir / "transform" / "normalize_districts.py"
        args = [
            str(input_file),
            "--source", "nces",
            "--year", self.year
        ]
        
        return self.run_script(script, args)
    
    def step_calculate_lct(self) -> bool:
        """
        Step 4: Calculate Learning Connection Time
        
        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 4: CALCULATE LEARNING CONNECTION TIME")
        logger.info("="*60)
        
        # Find normalized file
        normalized_dir = self.root / "data" / "processed" / "normalized"
        input_files = list(normalized_dir.glob(f"districts_{self.year.replace('-', '_')}*.csv"))
        
        if not input_files:
            logger.error(f"No normalized files found in {normalized_dir}")
            return False
        
        input_file = input_files[0]
        
        script = self.scripts_dir / "analyze" / "calculate_lct.py"
        args = [
            str(input_file),
            "--summary"
        ]
        
        return self.run_script(script, args)
    
    def run(self) -> bool:
        """
        Run the complete pipeline
        
        Returns:
            True if all steps succeeded
        """
        start_time = datetime.now()
        
        logger.info("="*60)
        logger.info("LEARNING CONNECTION TIME DATA PIPELINE")
        logger.info("="*60)
        logger.info(f"Year: {self.year}")
        logger.info(f"Sample mode: {self.sample}")
        logger.info(f"Skip download: {self.skip_download}")
        logger.info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Run each step
        steps = [
            ("Download", self.step_download),
            ("Extract", self.step_extract),
            ("Normalize", self.step_normalize),
            ("Calculate LCT", self.step_calculate_lct),
        ]
        
        for step_name, step_func in steps:
            try:
                success = step_func()
                if success:
                    self.steps_completed.append(step_name)
                    logger.info(f"✓ {step_name} completed")
                else:
                    self.steps_failed.append(step_name)
                    logger.error(f"✗ {step_name} failed")
                    break
            except Exception as e:
                self.steps_failed.append(step_name)
                logger.error(f"✗ {step_name} failed with exception: {e}")
                break
        
        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("\n" + "="*60)
        logger.info("PIPELINE SUMMARY")
        logger.info("="*60)
        logger.info(f"Completed steps: {len(self.steps_completed)}/{len(steps)}")
        
        if self.steps_completed:
            logger.info("\n✓ Completed:")
            for step in self.steps_completed:
                logger.info(f"  - {step}")
        
        if self.steps_failed:
            logger.info("\n✗ Failed:")
            for step in self.steps_failed:
                logger.info(f"  - {step}")
        
        logger.info(f"\nDuration: {duration}")
        logger.info(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        success = len(self.steps_failed) == 0
        if success:
            logger.info("\n✓ Pipeline completed successfully!")
            
            # Show where outputs are
            logger.info("\nOutput locations:")
            logger.info(f"  Normalized: data/processed/normalized/")
            logger.info(f"  LCT results: data/processed/normalized/*_with_lct.csv")
            logger.info(f"  Summary: data/processed/normalized/*_summary.txt")
        else:
            logger.error("\n✗ Pipeline failed")
        
        return success


def main():
    parser = argparse.ArgumentParser(
        description="Run complete LCT data processing pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--year",
        required=True,
        help="School year (e.g., 2023-24)"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use sample data only"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download step (use existing data)"
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Save log to file"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_file=args.log_file)
    
    # Run pipeline
    pipeline = PipelineRunner(
        year=args.year,
        sample=args.sample,
        skip_download=args.skip_download
    )
    
    success = pipeline.run()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
