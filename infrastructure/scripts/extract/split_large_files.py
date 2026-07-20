#!/usr/bin/env python3
"""
Handle multi-part files (_1, _2, _3, etc.)
Concatenate them into single files for processing

Usage:
    python split_large_files.py <directory> [--output-dir <path>] [--pattern <separator>]
    
Example:
    python split_large_files.py data/raw/federal/nces-ccd/2023-24/
    python split_large_files.py data/raw/federal/crdc/2021-22/ --pattern "_part"
"""

import argparse
import logging
from pathlib import Path
import pandas as pd
import sys
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_multipart_files(directory, pattern="_"):
    """
    Find sets of files with pattern: filename_1, filename_2, etc.
    
    Args:
        directory: Path to search for multi-part files
        pattern: Separator pattern (default: "_")
    
    Returns:
        Dictionary mapping base filenames to list of part files
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    
    multipart_sets = {}
    
    # Pattern to match files ending with separator + number
    part_pattern = re.compile(rf'{re.escape(pattern)}(\d+)$')
    
    for file in dir_path.rglob("*"):
        if not file.is_file():
            continue
            
        # Check if filename (without extension) matches pattern
        stem = file.stem
        match = part_pattern.search(stem)
        
        if match:
            # Extract base name (without the _N part)
            base_name = stem[:match.start()]
            part_number = int(match.group(1))
            
            if base_name not in multipart_sets:
                multipart_sets[base_name] = []
            
            multipart_sets[base_name].append((part_number, file))
    
    # Sort each set by part number
    for base_name in multipart_sets:
        multipart_sets[base_name].sort(key=lambda x: x[0])
        # Convert to just file paths (remove part numbers from tuples)
        multipart_sets[base_name] = [file for _, file in multipart_sets[base_name]]
    
    return multipart_sets


def concatenate_csv_files(file_list, output_path):
    """
    Concatenate multiple CSV files into one
    
    Args:
        file_list: List of Path objects to concatenate
        output_path: Path where combined file will be saved
    
    Returns:
        Number of total rows in combined file
    """
    logger.info(f"Concatenating {len(file_list)} CSV files...")
    
    # Append part-by-part — building a list of every part's DataFrame held
    # the whole multi-GB dataset in memory at once (issue #464)
    total_rows = 0
    for i, file in enumerate(file_list):
        try:
            df = pd.read_csv(file, low_memory=False)
            df.to_csv(output_path, index=False, mode='w' if i == 0 else 'a',
                      header=(i == 0))
            total_rows += len(df)
            logger.info(f"  ✓ Read {file.name}: {len(df):,} rows")
        except Exception as e:
            logger.error(f"  ✗ Error reading {file.name}: {e}")
            raise

    logger.info(f"✓ Combined file created: {total_rows:,} rows → {output_path.name}")
    return total_rows


def concatenate_text_files(file_list, output_path):
    """
    Concatenate multiple text files into one
    
    Args:
        file_list: List of Path objects to concatenate
        output_path: Path where combined file will be saved
    
    Returns:
        Number of total lines in combined file
    """
    logger.info(f"Concatenating {len(file_list)} text files...")
    
    total_lines = 0
    header_line = None

    with open(output_path, 'w', encoding='utf-8') as outfile:
        for i, file in enumerate(file_list):
            try:
                with open(file, 'r', encoding='utf-8') as infile:
                    lines = infile.readlines()

                    if i == 0:
                        header_line = lines[0] if lines else None
                    # Skip a repeated header in later parts ONLY if it matches
                    # the first file's header — the old isdigit() guess dropped
                    # the first DATA row of any part whose leading field wasn't
                    # purely numeric (issue #304)
                    elif lines and header_line is not None and lines[0] == header_line:
                        lines = lines[1:]

                    outfile.writelines(lines)
                    total_lines += len(lines)
                    logger.info(f"  ✓ Read {file.name}: {len(lines):,} lines")
            except Exception as e:
                logger.error(f"  ✗ Error reading {file.name}: {e}")
                raise
    
    logger.info(f"✓ Combined file created: {total_lines:,} lines → {output_path.name}")
    return total_lines


def process_multipart_set(base_name, files, output_dir):
    """
    Process a set of multi-part files
    
    Args:
        base_name: Base filename (without part numbers)
        files: List of file paths in order
        output_dir: Directory for output file
    
    Returns:
        Path to created combined file
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {base_name}")
    logger.info(f"Found {len(files)} parts")
    
    # Determine output path
    first_file = files[0]
    output_path = output_dir / f"{base_name}_combined{first_file.suffix}"
    
    # Check if output already exists
    if output_path.exists():
        logger.warning(f"Output file already exists: {output_path.name}")
        if not sys.stdin.isatty():
            # Non-interactive: input() hung or raised EOFError (issue #303)
            logger.info("Non-interactive session; keeping existing file")
            return None
        response = input("Overwrite? (y/n): ").strip().lower()
        if response != 'y':
            logger.info("Skipping...")
            return None
    
    # Process based on file type
    if first_file.suffix.lower() in ['.csv']:
        concatenate_csv_files(files, output_path)
    elif first_file.suffix.lower() in ['.txt', '.dat']:
        concatenate_text_files(files, output_path)
    else:
        logger.warning(f"Unsupported file type: {first_file.suffix}")
        logger.info("Attempting text concatenation...")
        concatenate_text_files(files, output_path)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Handle multi-part files and concatenate them",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python split_large_files.py data/raw/federal/nces-ccd/2023-24/
  python split_large_files.py data/raw/federal/crdc/ --pattern "_part"
  python split_large_files.py data/raw/ --output-dir data/processed/normalized/
        """
    )
    
    parser.add_argument(
        "directory",
        help="Directory containing multi-part files"
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for combined files (default: same as input)"
    )
    parser.add_argument(
        "--pattern",
        default="_",
        help="Part number separator pattern (default: '_')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it"
    )
    
    args = parser.parse_args()
    
    # Find multi-part files
    try:
        multipart_sets = find_multipart_files(args.directory, args.pattern)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    
    if not multipart_sets:
        logger.info("No multi-part files found.")
        return 0
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Found {len(multipart_sets)} multi-part file set(s)")
    logger.info(f"{'='*60}")
    
    # Set output directory
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.directory)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Process each set
    results = []
    for base_name, files in multipart_sets.items():
        if args.dry_run:
            logger.info(f"\n[DRY RUN] Would process: {base_name}")
            logger.info(f"  Parts: {len(files)}")
            for i, f in enumerate(files, 1):
                logger.info(f"    {i}. {f.name}")
        else:
            output_path = process_multipart_set(base_name, files, output_dir)
            if output_path:
                results.append(output_path)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    if args.dry_run:
        logger.info(f"Would process {len(multipart_sets)} file set(s)")
    else:
        logger.info(f"Successfully combined {len(results)} file set(s)")
        for result in results:
            logger.info(f"  ✓ {result}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
