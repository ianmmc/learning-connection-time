#!/usr/bin/env python3
"""
Batch File Converter for Bell Schedule Collection

Automatically converts PDFs and HTML files to text for easier data extraction.

Usage:
    # Convert all files in a directory
    python batch_convert.py "data/raw/manual_import_files/Alabama/Baldwin County/"

    # Specify output directory
    python batch_convert.py input_dir/ -o output_dir/

    # Process specific file types only
    python batch_convert.py input_dir/ --pdf-only
    python batch_convert.py input_dir/ --html-only

    # Verbose mode
    python batch_convert.py input_dir/ -v
"""

import argparse
import subprocess
import sys
from pathlib import Path


def convert_pdf(pdf_path, output_dir, verbose=False):
    """Convert PDF to text using pdftotext."""
    output_file = output_dir / f"{pdf_path.stem}.txt"

    try:
        result = subprocess.run(
            ['pdftotext', '-layout', str(pdf_path), str(output_file)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            if verbose:
                print(f"✓ Converted PDF: {pdf_path.name}")
            return True, output_file
        else:
            print(f"✗ Failed to convert {pdf_path.name}: {result.stderr}", file=sys.stderr)
            return False, None

    except FileNotFoundError:
        print("Error: pdftotext not found. Install poppler-utils.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"✗ Timeout converting {pdf_path.name}", file=sys.stderr)
        return False, None


def convert_html(html_path, output_dir, verbose=False):
    """Convert HTML to text using html2text."""
    output_file = output_dir / f"{html_path.stem}.txt"

    try:
        result = subprocess.run(
            ['html2text', '-nobs', '-ascii', str(html_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            with open(output_file, 'w') as f:
                f.write(result.stdout)

            if verbose:
                print(f"✓ Converted HTML: {html_path.name}")
            return True, output_file
        else:
            print(f"✗ Failed to convert {html_path.name}: {result.stderr}", file=sys.stderr)
            return False, None

    except FileNotFoundError:
        print("Error: html2text not found. Run: brew install html2text", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"✗ Timeout converting {html_path.name}", file=sys.stderr)
        return False, None


def process_directory(input_dir, output_dir, pdf_only=False, html_only=False, verbose=False):
    """Process all files in a directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        print(f"Error: Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Collect files
    pdf_files = list(input_path.glob('*.pdf')) + list(input_path.glob('*.PDF'))
    html_files = list(input_path.glob('*.html')) + list(input_path.glob('*.htm'))
    image_files = (
        list(input_path.glob('*.png')) + list(input_path.glob('*.PNG')) +
        list(input_path.glob('*.jpg')) + list(input_path.glob('*.JPG')) +
        list(input_path.glob('*.jpeg')) + list(input_path.glob('*.JPEG'))
    )

    stats = {
        'pdf_success': 0,
        'pdf_failed': 0,
        'html_success': 0,
        'html_failed': 0,
        'images': len(image_files)
    }

    # Process PDFs
    if not html_only and pdf_files:
        print(f"\nProcessing {len(pdf_files)} PDF files...")
        for pdf_file in pdf_files:
            success, _ = convert_pdf(pdf_file, output_path, verbose)
            if success:
                stats['pdf_success'] += 1
            else:
                stats['pdf_failed'] += 1

    # Process HTML files
    if not pdf_only and html_files:
        print(f"\nProcessing {len(html_files)} HTML files...")
        for html_file in html_files:
            success, _ = convert_html(html_file, output_path, verbose)
            if success:
                stats['html_success'] += 1
            else:
                stats['html_failed'] += 1

    # Report on image files
    if not pdf_only and not html_only and image_files:
        print(f"\nFound {len(image_files)} image files (require manual review):")
        for img in image_files:
            print(f"  - {img.name}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Batch convert PDFs and HTML files for bell schedule extraction',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('input_dir', help='Directory containing files to convert')
    parser.add_argument('-o', '--output', help='Output directory (default: input_dir/converted)',
                       dest='output_dir')
    parser.add_argument('--pdf-only', action='store_true', help='Convert only PDF files')
    parser.add_argument('--html-only', action='store_true', help='Convert only HTML files')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Default output directory
    if not args.output_dir:
        args.output_dir = Path(args.input_dir) / 'converted'

    print(f"Input directory: {args.input_dir}")
    print(f"Output directory: {args.output_dir}")

    # Process files
    stats = process_directory(
        args.input_dir,
        args.output_dir,
        pdf_only=args.pdf_only,
        html_only=args.html_only,
        verbose=args.verbose
    )

    # Summary
    print("\n" + "=" * 50)
    print("CONVERSION SUMMARY")
    print("=" * 50)
    print(f"PDFs converted: {stats['pdf_success']}")
    if stats['pdf_failed'] > 0:
        print(f"PDFs failed: {stats['pdf_failed']}")
    print(f"HTML converted: {stats['html_success']}")
    if stats['html_failed'] > 0:
        print(f"HTML failed: {stats['html_failed']}")
    if stats['images'] > 0:
        print(f"Images found (manual review): {stats['images']}")

    total_converted = stats['pdf_success'] + stats['html_success']
    print(f"\n✓ Total files converted: {total_converted}")
    print(f"✓ Output saved to: {args.output_dir}")


if __name__ == '__main__':
    main()
