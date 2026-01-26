#!/usr/bin/env python3
"""
Bell Schedule PDF Extraction Pipeline

Processes PDFs captured by the acquisition pipeline (FastAPI + Crawlee):
1. Extract text from PDFs using pdftotext
2. OCR fallback for scanned documents (tesseract)
3. Parse text for bell schedule patterns
4. Save extracted data for database import

Usage:
    # Process all pending PDFs
    python extract_from_pdfs.py

    # Process specific state
    python extract_from_pdfs.py --state CO

    # Process specific district
    python extract_from_pdfs.py --district 0622710

    # Dry run
    python extract_from_pdfs.py --dry-run
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"


@dataclass
class ExtractedSchedule:
    """Extracted bell schedule data"""
    grade_level: str  # 'elementary', 'middle', 'high', 'district'
    start_time: str
    end_time: str
    instructional_minutes: int
    school_name: Optional[str] = None
    confidence: float = 0.5


@dataclass
class ExtractionResult:
    """Result of extracting from a single PDF"""
    filename: str
    success: bool
    schedules: List[ExtractedSchedule]
    text_extracted: bool
    ocr_used: bool
    raw_text_length: int
    error: Optional[str] = None


class PDFExtractor:
    """
    Extract bell schedule data from PDFs.

    Uses:
    - pdftotext for text-based PDFs
    - tesseract/ocrmypdf for scanned documents
    - Pattern matching for time extraction
    """

    # Time pattern: matches 7:30 AM, 8:00 am, 3:30 PM, etc.
    TIME_PATTERN = re.compile(
        r'(\d{1,2}):(\d{2})\s*([AaPp]\.?[Mm]\.?)',
        re.IGNORECASE
    )

    # Common schedule indicators
    SCHEDULE_KEYWORDS = [
        "bell schedule", "school hours", "start time", "end time",
        "dismissal", "arrival", "first bell", "tardy bell",
        "school day", "instructional hours"
    ]

    # Grade level indicators
    GRADE_PATTERNS = {
        'elementary': [
            r'elementary', r'primary', r'k-5', r'k-4', r'k-6',
            r'grades?\s*k', r'grades?\s*1-5', r'grades?\s*1-4'
        ],
        'middle': [
            r'middle\s*school', r'junior\s*high', r'intermediate',
            r'grades?\s*6-8', r'grades?\s*7-8', r'6th\s*grade'
        ],
        'high': [
            r'high\s*school', r'secondary', r'senior\s*high',
            r'grades?\s*9-12', r'grades?\s*10-12', r'9th\s*grade'
        ]
    }

    def __init__(self, pdf_base_dir: Path = PDF_BASE_DIR):
        self.pdf_base_dir = pdf_base_dir
        self._check_tools()

    def _check_tools(self):
        """Check if extraction tools are available"""
        self.pdftotext_available = self._command_exists("pdftotext")
        self.tesseract_available = self._command_exists("tesseract")
        self.ocrmypdf_available = self._command_exists("ocrmypdf")

        logger.info(f"Tools: pdftotext={self.pdftotext_available}, "
                   f"tesseract={self.tesseract_available}, "
                   f"ocrmypdf={self.ocrmypdf_available}")

    def _command_exists(self, cmd: str) -> bool:
        """Check if command exists"""
        try:
            subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                timeout=5
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def extract_text(self, pdf_path: Path) -> Tuple[str, bool]:
        """
        Extract text from PDF.

        Returns:
            Tuple of (text, ocr_used)
        """
        # Try pdftotext first
        if self.pdftotext_available:
            text = self._extract_with_pdftotext(pdf_path)
            if text and len(text.strip()) > 100:
                return text, False

        # Fall back to OCR
        if self.tesseract_available:
            text = self._extract_with_ocr(pdf_path)
            if text:
                return text, True

        return "", False

    def _extract_with_pdftotext(self, pdf_path: Path) -> str:
        """Extract text using pdftotext"""
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), "-"],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.stdout
        except subprocess.SubprocessError as e:
            logger.debug(f"pdftotext failed: {e}")
            return ""

    def _extract_with_ocr(self, pdf_path: Path) -> str:
        """Extract text using OCR (tesseract via ocrmypdf)"""
        if self.ocrmypdf_available:
            try:
                # Use ocrmypdf to create searchable PDF, then extract
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp_path = Path(tmp.name)

                subprocess.run(
                    ["ocrmypdf", "--skip-text", str(pdf_path), str(tmp_path)],
                    capture_output=True,
                    timeout=120
                )

                # Extract text from OCR'd PDF
                text = self._extract_with_pdftotext(tmp_path)
                tmp_path.unlink()
                return text

            except subprocess.SubprocessError as e:
                logger.debug(f"ocrmypdf failed: {e}")

        # Direct tesseract on first page
        if self.tesseract_available:
            try:
                # Convert first page to image, then OCR
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = Path(tmp.name)

                # Use pdftoppm to convert to image
                subprocess.run(
                    ["pdftoppm", "-f", "1", "-l", "1", "-png",
                     str(pdf_path), str(tmp_path.with_suffix(""))],
                    capture_output=True,
                    timeout=60
                )

                # The output will be tmp_path-1.png
                img_path = tmp_path.parent / f"{tmp_path.stem}-1.png"
                if img_path.exists():
                    result = subprocess.run(
                        ["tesseract", str(img_path), "-", "-l", "eng"],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    img_path.unlink()
                    return result.stdout

            except subprocess.SubprocessError as e:
                logger.debug(f"tesseract failed: {e}")

        return ""

    def parse_schedules(
        self,
        text: str,
        grade_level_hint: str = None
    ) -> List[ExtractedSchedule]:
        """
        Parse bell schedule information from extracted text.

        Args:
            text: Extracted PDF text
            grade_level_hint: Optional hint from filename/metadata

        Returns:
            List of extracted schedules
        """
        if not text:
            return []

        schedules = []
        text_lower = text.lower()

        # Find all time mentions
        times = self.TIME_PATTERN.findall(text)
        if len(times) < 2:
            return []  # Need at least start and end time

        # Try to find paired start/end times
        lines = text.split('\n')
        for line in lines:
            line_times = self.TIME_PATTERN.findall(line)
            if len(line_times) >= 2:
                # Potential start/end pair
                start = self._format_time(line_times[0])
                end = self._format_time(line_times[-1])

                # Calculate minutes
                minutes = self._calculate_minutes(start, end)
                if 180 <= minutes <= 540:  # 3-9 hours is reasonable
                    # Determine grade level
                    grade_level = self._detect_grade_level(line, text_lower)
                    if not grade_level and grade_level_hint:
                        grade_level = grade_level_hint

                    schedules.append(ExtractedSchedule(
                        grade_level=grade_level or "unknown",
                        start_time=start,
                        end_time=end,
                        instructional_minutes=minutes,
                        confidence=0.6
                    ))

        # Deduplicate by grade level
        seen = set()
        unique_schedules = []
        for s in schedules:
            key = (s.grade_level, s.start_time, s.end_time)
            if key not in seen:
                seen.add(key)
                unique_schedules.append(s)

        return unique_schedules

    def _format_time(self, time_tuple: Tuple[str, str, str]) -> str:
        """Format time tuple to string"""
        hour, minute, ampm = time_tuple
        ampm_clean = ampm.replace(".", "").upper()
        return f"{hour}:{minute} {ampm_clean}"

    def _calculate_minutes(self, start: str, end: str) -> int:
        """Calculate minutes between start and end times"""
        def parse_time(t: str) -> int:
            match = re.match(r'(\d+):(\d+)\s*([AaPp])', t)
            if not match:
                return 0
            hour = int(match.group(1))
            minute = int(match.group(2))
            is_pm = match.group(3).lower() == 'p'

            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0

            return hour * 60 + minute

        start_mins = parse_time(start)
        end_mins = parse_time(end)

        if end_mins < start_mins:
            # Handle overnight (unlikely for schools)
            end_mins += 24 * 60

        return end_mins - start_mins

    def _detect_grade_level(self, line: str, full_text: str) -> Optional[str]:
        """Detect grade level from context"""
        line_lower = line.lower()

        for level, patterns in self.GRADE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    return level

        return None

    def process_pdf(
        self,
        pdf_path: Path,
        grade_level_hint: str = None
    ) -> ExtractionResult:
        """
        Process a single PDF file.

        Args:
            pdf_path: Path to PDF file
            grade_level_hint: Optional grade level hint from metadata

        Returns:
            ExtractionResult with extracted schedules
        """
        logger.info(f"Processing: {pdf_path.name}")

        try:
            # Extract text
            text, ocr_used = self.extract_text(pdf_path)

            if not text:
                return ExtractionResult(
                    filename=pdf_path.name,
                    success=False,
                    schedules=[],
                    text_extracted=False,
                    ocr_used=ocr_used,
                    raw_text_length=0,
                    error="No text could be extracted"
                )

            # Parse schedules
            schedules = self.parse_schedules(text, grade_level_hint)

            return ExtractionResult(
                filename=pdf_path.name,
                success=len(schedules) > 0,
                schedules=schedules,
                text_extracted=True,
                ocr_used=ocr_used,
                raw_text_length=len(text)
            )

        except Exception as e:
            logger.error(f"Error processing {pdf_path}: {e}")
            return ExtractionResult(
                filename=pdf_path.name,
                success=False,
                schedules=[],
                text_extracted=False,
                ocr_used=False,
                raw_text_length=0,
                error=str(e)
            )

    def process_district(
        self,
        district_dir: Path,
        dry_run: bool = False
    ) -> Dict:
        """
        Process all PDFs in a district directory.

        Args:
            district_dir: Directory containing district PDFs
            dry_run: If True, don't save results

        Returns:
            Dict with processing results
        """
        metadata_path = district_dir / "metadata.json"

        if not metadata_path.exists():
            logger.warning(f"No metadata.json in {district_dir}")
            return {"error": "no_metadata"}

        with open(metadata_path) as f:
            metadata = json.load(f)

        # Get grade level hints from sources
        source_hints = {
            s["filename"]: s.get("grade_level", "unknown")
            for s in metadata.get("sources", [])
        }

        results = []
        for pdf_path in district_dir.glob("*.pdf"):
            hint = source_hints.get(pdf_path.name)
            result = self.process_pdf(pdf_path, grade_level_hint=hint)
            results.append(result)

            # Save extracted text
            if result.text_extracted and not dry_run:
                extracted_dir = district_dir / "extracted"
                extracted_dir.mkdir(exist_ok=True)

                # Save extraction result
                result_path = extracted_dir / f"{pdf_path.stem}.json"
                with open(result_path, "w") as f:
                    json.dump({
                        "filename": result.filename,
                        "success": result.success,
                        "schedules": [asdict(s) for s in result.schedules],
                        "ocr_used": result.ocr_used,
                        "extracted_at": datetime.utcnow().isoformat()
                    }, f, indent=2)

        # Update metadata
        if not dry_run:
            successful = [r for r in results if r.success]
            if successful:
                metadata["extraction_status"] = "extracted"
                metadata["extraction_date"] = datetime.utcnow().isoformat()
                metadata["schedules_found"] = sum(len(r.schedules) for r in successful)
            else:
                metadata["extraction_status"] = "failed"

            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

        return {
            "district_id": metadata.get("district_id"),
            "district_name": metadata.get("district_name"),
            "pdfs_processed": len(results),
            "successful": len([r for r in results if r.success]),
            "schedules_found": sum(len(r.schedules) for r in results),
            "results": results
        }

    def process_all(
        self,
        state: str = None,
        district_id: str = None,
        dry_run: bool = False
    ) -> List[Dict]:
        """
        Process all PDFs matching criteria.

        Args:
            state: Optional state filter
            district_id: Optional district filter
            dry_run: If True, don't save results

        Returns:
            List of processing results per district
        """
        all_results = []

        # Find directories to process
        if district_id:
            # Find specific district
            for state_dir in self.pdf_base_dir.iterdir():
                if state_dir.is_dir():
                    for d_dir in state_dir.iterdir():
                        if d_dir.name.startswith(district_id):
                            results = self.process_district(d_dir, dry_run)
                            all_results.append(results)
                            return all_results

        elif state:
            # Process specific state
            state_dir = self.pdf_base_dir / state
            if state_dir.exists():
                for district_dir in state_dir.iterdir():
                    if district_dir.is_dir():
                        results = self.process_district(district_dir, dry_run)
                        all_results.append(results)

        else:
            # Process all pending
            for state_dir in self.pdf_base_dir.iterdir():
                if state_dir.is_dir():
                    for district_dir in state_dir.iterdir():
                        if district_dir.is_dir():
                            # Check if already extracted
                            metadata_path = district_dir / "metadata.json"
                            if metadata_path.exists():
                                with open(metadata_path) as f:
                                    metadata = json.load(f)
                                if metadata.get("extraction_status") == "pending":
                                    results = self.process_district(district_dir, dry_run)
                                    all_results.append(results)

        return all_results


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Bell Schedule PDF Extraction Pipeline"
    )
    parser.add_argument(
        "--state",
        help="Process only this state (e.g., CO)"
    )
    parser.add_argument(
        "--district",
        help="Process only this district ID"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be extracted without saving"
    )

    args = parser.parse_args()

    extractor = PDFExtractor()

    print(f"Processing PDFs from: {PDF_BASE_DIR}")

    results = extractor.process_all(
        state=args.state,
        district_id=args.district,
        dry_run=args.dry_run
    )

    # Summary
    total_districts = len(results)
    total_pdfs = sum(r.get("pdfs_processed", 0) for r in results)
    total_successful = sum(r.get("successful", 0) for r in results)
    total_schedules = sum(r.get("schedules_found", 0) for r in results)

    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Districts processed: {total_districts}")
    print(f"PDFs processed: {total_pdfs}")
    print(f"Successful extractions: {total_successful}")
    print(f"Schedules found: {total_schedules}")

    if args.dry_run:
        print("\n[DRY RUN - no files were actually saved]")


if __name__ == "__main__":
    main()
