#!/usr/bin/env python3
"""
Download NCES Common Core of Data (CCD) files

NCES CCD provides comprehensive annual data about all public schools and school districts.

Usage:
    python fetch_nces_ccd.py --year 2023-24 [--tables district_directory district_staff]
    python fetch_nces_ccd.py --year 2022-23 --sample
    
Available tables:
    - district_directory: Basic district information
    - district_membership: Student enrollment data
    - district_staff: Staff counts by role
    - school_directory: School-level data
"""

import argparse
import logging
from pathlib import Path
import sys
import requests
from typing import List, Dict
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# NCES CCD Data Catalog
# Note: URLs need to be updated based on actual NCES data releases
CCD_CATALOG = {
    "2023-24": {
        "district_directory": {
            "url": "https://nces.ed.gov/ccd/data/zip/ccd_lea_directory_2024.zip",
            "description": "Local Education Agency (District) Directory"
        },
        "district_membership": {
            "url": "https://nces.ed.gov/ccd/data/zip/ccd_lea_membership_2024.zip",
            "description": "District Membership (Enrollment)"
        },
        "district_staff": {
            "url": "https://nces.ed.gov/ccd/data/zip/ccd_lea_staff_2024.zip",
            "description": "District Staff Counts"
        },
        "school_directory": {
            "url": "https://nces.ed.gov/ccd/data/zip/ccd_sch_directory_2024.zip",
            "description": "School Directory"
        }
    },
    "2022-23": {
        "district_directory": {
            "url": "https://nces.ed.gov/ccd/data/zip/ccd_lea_directory_2023.zip",
            "description": "Local Education Agency (District) Directory"
        },
        "district_membership": {
            "url": "https://nces.ed.gov/ccd/data/zip/ccd_lea_membership_2023.zip",
            "description": "District Membership (Enrollment)"
        },
        "district_staff": {
            "url": "https://nces.ed.gov/ccd/data/zip/ccd_lea_staff_2023.zip",
            "description": "District Staff Counts"
        }
    }
}


def get_output_directory(year: str, base_path: Path = None) -> Path:
    """
    Get the output directory for a given year
    
    Args:
        year: School year (e.g., "2023-24")
        base_path: Base path for data storage
    
    Returns:
        Path object for the output directory
    """
    if base_path is None:
        # Default to project structure
        script_dir = Path(__file__).parent
        base_path = script_dir.parent.parent.parent / "data" / "raw" / "federal" / "nces-ccd"
    
    output_dir = base_path / year.replace("-", "_")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    return output_dir


def download_file(url: str, output_path: Path) -> bool:
    """
    Download a file from a URL
    
    Args:
        url: URL to download from
        output_path: Where to save the file
    
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Downloading: {url}")
        
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        # Get file size if available
        total_size = int(response.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = (downloaded / total_size) * 100
                    logger.info(f"  Progress: {percent:.1f}%")
        
        logger.info(f"✓ Saved to: {output_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Download failed: {e}")
        return False


def create_metadata_file(output_dir: Path, year: str, tables: List[str]):
    """
    Create a README with metadata about the downloaded files
    
    Args:
        output_dir: Directory containing the files
        year: School year
        tables: List of tables downloaded
    """
    readme_path = output_dir / "README.md"
    
    content = f"""# NCES Common Core of Data (CCD) - {year}

## Source
National Center for Education Statistics
https://nces.ed.gov/ccd/

## Downloaded Tables

"""
    
    for table in tables:
        if year in CCD_CATALOG and table in CCD_CATALOG[year]:
            info = CCD_CATALOG[year][table]
            content += f"### {table}\n"
            content += f"- **Description**: {info['description']}\n"
            content += f"- **URL**: {info['url']}\n\n"
    
    content += f"""
## Download Information
- **Date**: {Path(__file__).stat().st_mtime}
- **Script**: fetch_nces_ccd.py

## Next Steps
1. Extract ZIP files if present
2. Check for multi-part files (_1, _2, etc.)
3. Run data validation scripts
4. Process into normalized format

## Notes
- CCD data is released annually, typically in fall
- Data represents the prior school year
- Some files may be split into multiple parts due to size
"""
    
    with open(readme_path, 'w') as f:
        f.write(content)
    
    logger.info(f"✓ Metadata file created: {readme_path}")


def download_sample_data(output_dir: Path, year: str) -> bool:
    """
    Download a sample dataset for testing
    
    For now, this creates a stub file. In production, you would
    download a real sample or create synthetic data.
    
    Args:
        output_dir: Where to save sample data
        year: School year
    
    Returns:
        True if successful
    """
    logger.info("Creating sample data for testing...")
    
    sample_file = output_dir / "sample_districts.csv"
    
    # Create a simple CSV with sample data
    sample_content = """leaid,lea_name,state,total_students,total_teachers,daily_minutes
0100001,Sample District 1,AL,5000,250,360
0100002,Sample District 2,AL,8000,400,360
0100003,Sample District 3,AL,3000,180,360
"""
    
    with open(sample_file, 'w') as f:
        f.write(sample_content)
    
    logger.info(f"✓ Sample data created: {sample_file}")
    
    # Create README
    readme_path = output_dir / "README.md"
    with open(readme_path, 'w') as f:
        f.write(f"""# Sample Data - {year}

This is synthetic sample data for testing the pipeline.

## Contents
- sample_districts.csv: 3 sample districts with basic metrics

## Usage
Use this to test data processing scripts before downloading full datasets.
""")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Download NCES Common Core of Data",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--year",
        required=True,
        choices=list(CCD_CATALOG.keys()),
        help="School year to download"
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        help="Specific tables to download (default: all available)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Custom output directory"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Download sample data only for testing"
    )
    
    args = parser.parse_args()
    
    # Get output directory
    output_dir = get_output_directory(args.year, args.output_dir)
    logger.info(f"Output directory: {output_dir}")
    
    # Handle sample data
    if args.sample:
        success = download_sample_data(output_dir, args.year)
        return 0 if success else 1
    
    # Determine which tables to download
    available_tables = CCD_CATALOG[args.year].keys()
    tables_to_download = args.tables if args.tables else list(available_tables)
    
    # Validate requested tables
    invalid_tables = set(tables_to_download) - set(available_tables)
    if invalid_tables:
        logger.error(f"Invalid table(s): {', '.join(invalid_tables)}")
        logger.info(f"Available tables: {', '.join(available_tables)}")
        return 1
    
    logger.info(f"\nDownloading {len(tables_to_download)} table(s) for {args.year}")
    logger.info("="*60)
    
    # Download each table
    results = []
    for table in tables_to_download:
        info = CCD_CATALOG[args.year][table]
        
        logger.info(f"\n{table}: {info['description']}")
        
        # Determine output filename
        filename = Path(info['url']).name
        output_path = output_dir / filename
        
        # Check if already exists
        if output_path.exists():
            logger.warning(f"File already exists: {output_path.name}")
            response = input("Re-download? (y/n): ").strip().lower()
            if response != 'y':
                logger.info("Skipping...")
                continue
        
        # Download
        success = download_file(info['url'], output_path)
        results.append((table, success))
    
    # Create metadata
    successful_tables = [t for t, s in results if s]
    if successful_tables:
        create_metadata_file(output_dir, args.year, successful_tables)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("DOWNLOAD SUMMARY")
    logger.info("="*60)
    
    for table, success in results:
        status = "✓" if success else "✗"
        logger.info(f"{status} {table}")
    
    successful_count = sum(1 for _, s in results if s)
    logger.info(f"\nSuccessful: {successful_count}/{len(results)}")
    
    return 0 if successful_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
