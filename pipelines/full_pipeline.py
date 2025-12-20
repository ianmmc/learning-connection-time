#!/usr/bin/env python3
"""
Full data processing pipeline for Learning Connection Time analysis

This pipeline orchestrates the complete data flow:
1. Download data (optional)
2. Enrich with bell schedules (optional)
3. Extract and combine multi-part files
4. Normalize to standard schema
5. Calculate LCT metrics
6. Generate reports

Usage:
    python full_pipeline.py --year 2023-24 [--skip-download] [--sample] [--enrich-bell-schedules]

Example:
    python full_pipeline.py --year 2023-24 --sample
    python full_pipeline.py --year 2023-24 --skip-download
    python full_pipeline.py --year 2023-24 --enrich-bell-schedules --tier 1
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
    
    def __init__(self, year: str, sample: bool = False, skip_download: bool = False,
                 enrich_bell_schedules: bool = False, tier: int = 2):
        """
        Initialize pipeline

        Args:
            year: School year (e.g., "2023-24")
            sample: Use sample data only
            skip_download: Skip download step
            enrich_bell_schedules: Fetch bell schedules from websites
            tier: Bell schedule quality tier (1=detailed, 2=automated, 3=statutory)
        """
        self.year = year
        self.sample = sample
        self.skip_download = skip_download
        self.enrich_bell_schedules = enrich_bell_schedules
        self.tier = tier

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

    def step_enrich_bell_schedules(self) -> bool:
        """
        Step 2: Enrich with bell schedules (optional)

        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 2: ENRICH WITH BELL SCHEDULES")
        logger.info("="*60)

        if not self.enrich_bell_schedules:
            logger.info("Skipping bell schedule enrichment (not enabled)")
            logger.info("Use --enrich-bell-schedules to enable")
            return True

        # Find normalized file to enrich
        normalized_dir = self.root / "data" / "processed" / "normalized"

        # Look for latest normalized file
        input_files = list(normalized_dir.glob(f"districts_{self.year.replace('-', '_')}*.csv"))

        if not input_files:
            logger.warning("No normalized files found yet, skipping enrichment")
            logger.info("Note: Bell schedule enrichment should run after normalization")
            return True

        input_file = input_files[0]

        script = self.scripts_dir / "enrich" / "fetch_bell_schedules.py"
        args = [
            str(input_file),
            "--year", self.year,
            "--tier", str(self.tier)
        ]

        return self.run_script(script, args)

    def step_extract(self) -> bool:
        """
        Step 3: Extract and combine multi-part files

        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 3: EXTRACT AND COMBINE FILES")
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
        Step 4: Normalize data to standard schema

        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 4: NORMALIZE DATA")
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
        Step 5: Calculate Learning Connection Time

        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 5: CALCULATE LEARNING CONNECTION TIME")
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
            "--summary",
            "--filter-invalid"  # Create filtered file for publication
        ]

        return self.run_script(script, args)

    def step_export_deliverables(self) -> bool:
        """
        Step 6: Export final deliverables to outputs/datasets/

        Copies key results to a clean directory for easy sharing

        Returns:
            True if successful
        """
        logger.info("\n" + "="*60)
        logger.info("STEP 6: EXPORT DELIVERABLES")
        logger.info("="*60)

        import shutil

        # Create outputs directory structure
        outputs_dir = self.root / "outputs" / "datasets" / self.year.replace("-", "_")
        outputs_dir.mkdir(parents=True, exist_ok=True)

        # Create README for the outputs
        readme_path = outputs_dir / "README.md"

        # Find files to copy
        normalized_dir = self.root / "data" / "processed" / "normalized"
        enriched_dir = self.root / "data" / "enriched" / "bell-schedules"

        files_copied = []

        # Copy filtered LCT results (publication-ready, valid districts only)
        lct_files = list(normalized_dir.glob(f"districts_{self.year.replace('-', '_')}*_with_lct_valid.csv"))
        for file in lct_files:
            dest = outputs_dir / file.name
            shutil.copy2(file, dest)
            files_copied.append(file.name)
            logger.info(f"  Copied: {file.name} (publication-ready)")

        # Copy validation report
        validation_files = list(normalized_dir.glob(f"districts_{self.year.replace('-', '_')}*_validation_report.txt"))
        for file in validation_files:
            dest = outputs_dir / file.name
            shutil.copy2(file, dest)
            files_copied.append(file.name)
            logger.info(f"  Copied: {file.name}")

        # Copy LCT summary
        summary_files = list(normalized_dir.glob(f"districts_{self.year.replace('-', '_')}*_with_lct_summary.txt"))
        for file in summary_files:
            dest = outputs_dir / file.name
            shutil.copy2(file, dest)
            files_copied.append(file.name)
            logger.info(f"  Copied: {file.name}")

        # Copy normalized data
        normalized_files = list(normalized_dir.glob(f"districts_{self.year.replace('-', '_')}_nces.csv"))
        for file in normalized_files:
            dest = outputs_dir / file.name
            shutil.copy2(file, dest)
            files_copied.append(file.name)
            logger.info(f"  Copied: {file.name}")

        # Copy bell schedule enrichment summary if exists
        if self.enrich_bell_schedules:
            enriched_files = list(enriched_dir.glob(f"*enriched_{self.year.replace('-', '_')}_summary.txt"))
            for file in enriched_files:
                dest = outputs_dir / f"bell_schedules_{file.name}"
                shutil.copy2(file, dest)
                files_copied.append(f"bell_schedules_{file.name}")
                logger.info(f"  Copied: bell_schedules_{file.name}")

        # Create README
        readme_content = f"""# Learning Connection Time Analysis - {self.year}

## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This directory contains publication-ready datasets for sharing and discussion.

## Files in This Directory

"""

        for file_name in sorted(files_copied):
            if "with_lct_valid.csv" in file_name:
                readme_content += f"""
### {file_name}
**LCT Analysis Results - Publication Ready** ✨
- **VALIDATED DISTRICTS ONLY** - Data quality filters applied
- Excludes districts with: zero enrollment, zero staff, impossible ratios
- Includes: LCT minutes/hours, student-teacher ratios, percentiles, categories
- Ready for: Presentations, policy discussions, public sharing
- **Use this file for all external communications**
"""
            elif "validation_report.txt" in file_name:
                readme_content += f"""
### {file_name}
**Data Quality Validation Report**
- How many districts were filtered and why
- Validation criteria applied
- Data quality statistics
- Transparency documentation for methodology
"""
            elif "summary.txt" in file_name and "bell" not in file_name:
                readme_content += f"""
### {file_name}
**Summary Statistics**
- Overall statistics for valid districts
- State-by-state averages
- Distribution information
"""
            elif "nces.csv" in file_name and "with_lct" not in file_name:
                readme_content += f"""
### {file_name}
**Normalized District Data**
- Standardized district information
- Enrollment and staff counts
- Before LCT calculation (all districts, unfiltered)
"""
            elif "bell_schedules" in file_name:
                readme_content += f"""
### {file_name}
**Bell Schedule Enrichment Summary**
- Actual vs. statutory instructional time
- Confidence levels and data sources
- Quality tier information
"""

        readme_content += f"""

## Data Source
- **NCES Common Core of Data**: {self.year} school year
- **Directory**: District identification and characteristics
- **Membership**: Student enrollment counts
- **Staff**: Teacher and staff FTE counts

## Methodology
- See: `docs/METHODOLOGY.md` for LCT calculation details
- See: `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md` for enrichment methodology

## Usage Notes

### For Presentations and Public Sharing
**Use the `*_with_lct_valid.csv` file** - This contains only validated districts that passed all data quality checks. This is the publication-ready dataset.

### For Quick Reference
Check the `*_summary.txt` file for overall statistics and distributions.

### For Transparency
Review the `*_validation_report.txt` to see what data was filtered out and why. This supports methodological transparency in discussions.

### For Validation
Compare the normalized data (`*_nces.csv`) with the LCT results to verify calculations.

## Key Metrics in LCT File

- **lct_minutes**: Learning Connection Time in minutes per student per day
- **lct_hours**: LCT converted to hours
- **student_teacher_ratio**: Traditional metric for comparison
- **lct_percentile**: Where this district ranks (0-100)
- **lct_category**: Qualitative category (Very Low, Low, Moderate, High, Very High)

## Next Steps

1. **Review summary statistics** in the summary.txt file
2. **Open CSV in spreadsheet** for detailed district analysis
3. **Filter/sort by state or LCT** to find patterns
4. **Compare districts** to identify equity gaps
5. **Create visualizations** to support policy discussions

## Contact

For questions about methodology or data quality, see project documentation in the main repository.

---

**Project**: Learning Connection Time Analysis
**Mission**: Reframing student-teacher ratios into tangible equity metrics
**Part of**: "Reducing the Ratio" educational equity initiative
"""

        with open(readme_path, 'w') as f:
            f.write(readme_content)

        logger.info(f"  Created: README.md")
        logger.info(f"\n✓ Exported {len(files_copied)} files to outputs/datasets/{self.year.replace('-', '_')}/")

        return True

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
        logger.info(f"Enrich bell schedules: {self.enrich_bell_schedules}")
        if self.enrich_bell_schedules:
            logger.info(f"Bell schedule tier: {self.tier}")
        logger.info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Run each step
        steps = [
            ("Download", self.step_download),
            ("Enrich Bell Schedules", self.step_enrich_bell_schedules),
            ("Extract", self.step_extract),
            ("Normalize", self.step_normalize),
            ("Calculate LCT", self.step_calculate_lct),
            ("Export Deliverables", self.step_export_deliverables),
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
            logger.info(f"  📊 SHARE-READY: outputs/datasets/{self.year.replace('-', '_')}/")
            logger.info(f"  📁 Full data: data/processed/normalized/")
            logger.info(f"  🔔 Enrichment: data/enriched/bell-schedules/")
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
        "--enrich-bell-schedules",
        action="store_true",
        help="Fetch bell schedules from district/school websites"
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        default=2,
        help="Bell schedule quality tier: 1=detailed, 2=automated, 3=statutory (default: 2)"
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
        skip_download=args.skip_download,
        enrich_bell_schedules=args.enrich_bell_schedules,
        tier=args.tier
    )
    
    success = pipeline.run()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
