#!/usr/bin/env python3
"""
Tier 3 Processor: Local PDF/OCR Extraction
Extracts bell schedules from PDF documents and images using local tools

Tasks:
    - Download PDF documents (handle Google Drive links)
    - Extract text with pdftotext
    - OCR with tesseract if text extraction fails
    - Parse extracted text for time patterns
    - Handle common PDF layouts (tables, lists)

Tools Used:
    - pdftotext: PDF text extraction
    - tesseract: OCR for scanned documents
    - ocrmypdf: PDF OCR preprocessing

Cost: $0 (local compute only)

Usage:
    from tier_3_processor import Tier3Processor
    from connection import session_scope

    with session_scope() as session:
        processor = Tier3Processor(session)
        result = processor.process_district('0622710', tier_2_result={...})
"""

import logging
import re
import subprocess
import tempfile
import os
import requests
from typing import Dict, Optional, List, Tuple
from datetime import datetime, time as dt_time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from sqlalchemy.orm import Session

from infrastructure.database.models import District, EnrichmentQueue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Tier3Processor:
    """Tier 3: Local PDF/OCR Extraction"""

    # Time pattern regex (matches HH:MM AM/PM, H:MM AM/PM)
    TIME_PATTERN = re.compile(
        r'\b(\d{1,2}):(\d{2})\s*([AaPp][Mm])\b'
    )

    # Alternative time patterns (for more flexible matching)
    TIME_PATTERNS_ALT = [
        re.compile(r'\b(\d{1,2}):(\d{2})\s*([AaPp]\.?[Mm]\.?)\b'),  # With periods
        re.compile(r'\b(\d{1,2}):(\d{2})([AaPp])\b'),  # No space before meridiem
        re.compile(r'\b(\d{1,2})(\d{2})\s*([AaPp][Mm])\b'),  # No colon
    ]

    def __init__(self, session: Session, temp_dir: str = None):
        """
        Initialize Tier 3 processor

        Args:
            session: SQLAlchemy database session
            temp_dir: Temporary directory for downloads (default: system temp)
        """
        self.session = session
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if required CLI tools are available"""
        tools = {
            'pdftotext': 'brew install poppler',
            'tesseract': 'brew install tesseract',
            'ocrmypdf': 'brew install ocrmypdf'
        }

        missing = []
        for tool, install_cmd in tools.items():
            try:
                subprocess.run(
                    [tool, '--version'],
                    capture_output=True,
                    check=True,
                    timeout=5
                )
                logger.debug(f"Found {tool}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.warning(f"Missing {tool} - install with: {install_cmd}")
                missing.append(tool)

        if missing:
            logger.warning(f"Some tools are missing: {missing}. "
                         f"PDF/OCR extraction may be limited.")

    # =========================================================================
    # Main Processing
    # =========================================================================

    def process_district(
        self,
        district_id: str,
        tier_2_result: Dict
    ) -> Dict:
        """
        Process a single district through Tier 3

        Args:
            district_id: NCES district ID
            tier_2_result: Results from Tier 2 (extraction)

        Returns:
            Result dictionary with PDF/OCR extraction findings
        """
        logger.info(f"Processing district {district_id} at Tier 3")
        start_time = datetime.now()

        # Get district from database
        district = self.session.query(District).filter_by(
            nces_id=district_id
        ).first()

        if not district:
            logger.error(f"District {district_id} not found in database")
            return {
                'success': False,
                'error': 'district_not_found',
                'district_id': district_id
            }

        # Get PDF/image URLs from Tier 2
        pdf_links = tier_2_result.get('pdf_links_found', [])
        image_links = tier_2_result.get('image_links_found', [])

        if not pdf_links and not image_links:
            logger.warning(f"No PDF/image links from Tier 2 results")
            return {
                'success': False,
                'error': 'no_documents_to_process',
                'district_id': district_id,
                'escalation_needed': True,
                'escalation_reason': 'no_documents_available'
            }

        # Process PDFs
        extraction_results = []

        for pdf_url in pdf_links:
            try:
                result = self._process_pdf(pdf_url)
                extraction_results.append(result)

                # If we got a valid schedule, we're done
                if result.get('schedule_found') and result.get('start_time'):
                    logger.info(f"Successfully extracted schedule from PDF: {pdf_url}")
                    break

            except Exception as e:
                logger.error(f"PDF processing failed for {pdf_url}: {e}")
                extraction_results.append({
                    'url': pdf_url,
                    'success': False,
                    'error': str(e)
                })

        # Process images (if no PDF success)
        if not any(r.get('schedule_found') for r in extraction_results):
            for image_url in image_links:
                try:
                    result = self._process_image(image_url)
                    extraction_results.append(result)

                    if result.get('schedule_found') and result.get('start_time'):
                        logger.info(f"Successfully extracted schedule from image: {image_url}")
                        break

                except Exception as e:
                    logger.error(f"Image processing failed for {image_url}: {e}")
                    extraction_results.append({
                        'url': image_url,
                        'success': False,
                        'error': str(e)
                    })

        # Compile best result
        best_result = self._select_best_result(extraction_results)

        processing_time = int((datetime.now() - start_time).total_seconds())

        result = {
            'success': best_result.get('schedule_found', False),
            'district_id': district_id,
            'district_name': district.name,
            'extraction_attempts': len(extraction_results),
            'schedule_found': best_result.get('schedule_found', False),
            'start_time': best_result.get('start_time'),
            'end_time': best_result.get('end_time'),
            'total_minutes': best_result.get('total_minutes'),
            'confidence': best_result.get('confidence', 0.0),
            'source_url': best_result.get('url'),
            'extraction_method': best_result.get('method'),
            'ocr_used': best_result.get('ocr_used', False),
            'processing_time_seconds': processing_time,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Determine escalation
        result['escalation_needed'] = self._should_escalate(result)
        result['escalation_reason'] = self._get_escalation_reason(result)

        logger.info(f"Tier 3 completed for {district_id}: "
                   f"schedule_found={result['schedule_found']}, "
                   f"confidence={result['confidence']}, "
                   f"escalate={result['escalation_needed']}")

        return result

    # =========================================================================
    # PDF Processing
    # =========================================================================

    def _process_pdf(self, pdf_url: str) -> Dict:
        """
        Process a PDF document

        Steps:
            1. Download PDF (handle Google Drive)
            2. Extract text with pdftotext
            3. If text extraction fails, OCR with tesseract
            4. Parse for time patterns
        """
        logger.info(f"Processing PDF: {pdf_url}")

        try:
            # Download PDF
            pdf_path = self._download_pdf(pdf_url)

            if not pdf_path or not os.path.exists(pdf_path):
                return {
                    'url': pdf_url,
                    'schedule_found': False,
                    'error': 'download_failed'
                }

            # Try text extraction first
            text = self._extract_text_from_pdf(pdf_path)

            ocr_used = False
            if not text or len(text.strip()) < 50:
                # Text extraction failed - try OCR
                logger.info(f"Text extraction sparse, trying OCR for {pdf_url}")
                text = self._ocr_pdf(pdf_path)
                ocr_used = True

            # Clean up
            try:
                os.remove(pdf_path)
            except Exception:
                pass

            if not text:
                return {
                    'url': pdf_url,
                    'schedule_found': False,
                    'error': 'no_text_extracted',
                    'ocr_used': ocr_used
                }

            # Parse times from extracted text
            return self._parse_schedule_from_text(text, pdf_url, 'pdf', ocr_used)

        except Exception as e:
            logger.error(f"PDF processing failed: {e}")
            return {
                'url': pdf_url,
                'schedule_found': False,
                'error': str(e)
            }

    def _download_pdf(self, url: str) -> Optional[str]:
        """
        Download PDF to temporary file

        Handles:
            - Regular PDF URLs
            - Google Drive share links
        """
        # Check if Google Drive URL
        if 'drive.google.com' in url:
            url = self._convert_google_drive_url(url)

        try:
            response = requests.get(url, timeout=60, allow_redirects=True)
            response.raise_for_status()

            # Create temp file
            temp_file = tempfile.NamedTemporaryFile(
                suffix='.pdf',
                dir=self.temp_dir,
                delete=False
            )

            temp_file.write(response.content)
            temp_file.close()

            logger.info(f"Downloaded PDF to {temp_file.name}")
            return temp_file.name

        except Exception as e:
            logger.error(f"PDF download failed from {url}: {e}")
            return None

    def _convert_google_drive_url(self, url: str) -> str:
        """
        Convert Google Drive view link to direct download link

        From: https://drive.google.com/file/d/ABC123/view
        To:   https://drive.google.com/uc?export=download&id=ABC123
        """
        patterns = [
            r'drive\.google\.com/file/d/([^/]+)',
            r'drive\.google\.com/open\?id=([^&]+)',
        ]

        file_id = None
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                file_id = match.group(1)
                break

        if not file_id:
            logger.warning(f"Could not extract Google Drive file ID from: {url}")
            return url

        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        logger.info(f"Converted Google Drive URL: {download_url}")
        return download_url

    def _extract_text_from_pdf(self, pdf_path: str) -> Optional[str]:
        """Extract text from PDF using pdftotext"""
        try:
            result = subprocess.run(
                ['pdftotext', '-layout', pdf_path, '-'],
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            logger.error(f"pdftotext failed: {e.stderr}")
            return None
        except FileNotFoundError:
            logger.error("pdftotext not found - install with: brew install poppler")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"pdftotext timed out for {pdf_path}")
            return None

    def _ocr_pdf(self, pdf_path: str) -> Optional[str]:
        """OCR PDF using ocrmypdf + pdftotext"""
        try:
            # Create temp file for OCR output
            ocr_output = tempfile.NamedTemporaryFile(
                suffix='.pdf',
                dir=self.temp_dir,
                delete=False
            )
            ocr_output.close()

            # Run OCR
            subprocess.run(
                ['ocrmypdf', '--force-ocr', pdf_path, ocr_output.name],
                capture_output=True,
                timeout=60,
                check=True
            )

            # Extract text from OCR'd PDF
            text = self._extract_text_from_pdf(ocr_output.name)

            # Clean up
            try:
                os.remove(ocr_output.name)
            except Exception:
                pass

            return text

        except subprocess.CalledProcessError as e:
            logger.error(f"OCR failed: {e.stderr}")
            return None
        except FileNotFoundError:
            logger.error("ocrmypdf not found - install with: brew install ocrmypdf")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"OCR timed out for {pdf_path}")
            return None

    # =========================================================================
    # Image Processing
    # =========================================================================

    def _process_image(self, image_url: str) -> Dict:
        """
        Process an image using tesseract OCR

        Steps:
            1. Download image
            2. OCR with tesseract
            3. Parse for time patterns
        """
        logger.info(f"Processing image: {image_url}")

        try:
            # Download image
            image_path = self._download_image(image_url)

            if not image_path or not os.path.exists(image_path):
                return {
                    'url': image_url,
                    'schedule_found': False,
                    'error': 'download_failed'
                }

            # OCR image
            text = self._ocr_image(image_path)

            # Clean up
            try:
                os.remove(image_path)
            except Exception:
                pass

            if not text:
                return {
                    'url': image_url,
                    'schedule_found': False,
                    'error': 'ocr_failed',
                    'ocr_used': True
                }

            # Parse times
            return self._parse_schedule_from_text(text, image_url, 'image_ocr', True)

        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            return {
                'url': image_url,
                'schedule_found': False,
                'error': str(e),
                'ocr_used': True
            }

    def _download_image(self, url: str) -> Optional[str]:
        """Download image to temporary file"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Determine file extension
            ext = Path(urlparse(url).path).suffix or '.png'

            temp_file = tempfile.NamedTemporaryFile(
                suffix=ext,
                dir=self.temp_dir,
                delete=False
            )

            temp_file.write(response.content)
            temp_file.close()

            logger.info(f"Downloaded image to {temp_file.name}")
            return temp_file.name

        except Exception as e:
            logger.error(f"Image download failed from {url}: {e}")
            return None

    def _ocr_image(self, image_path: str) -> Optional[str]:
        """OCR image using tesseract"""
        try:
            result = subprocess.run(
                ['tesseract', image_path, 'stdout'],
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            logger.error(f"tesseract failed: {e.stderr}")
            return None
        except FileNotFoundError:
            logger.error("tesseract not found - install with: brew install tesseract")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"tesseract timed out for {image_path}")
            return None

    # =========================================================================
    # Text Parsing
    # =========================================================================

    def _parse_schedule_from_text(
        self,
        text: str,
        url: str,
        method: str,
        ocr_used: bool
    ) -> Dict:
        """
        Parse bell schedule from extracted text

        Args:
            text: Extracted text content
            url: Source URL
            method: Extraction method ('pdf', 'image_ocr')
            ocr_used: Whether OCR was used

        Returns:
            Result dictionary
        """
        # Find all time patterns
        matches = self.TIME_PATTERN.findall(text)

        # Try alternative patterns if primary pattern found nothing
        if not matches:
            for pattern in self.TIME_PATTERNS_ALT:
                matches = pattern.findall(text)
                if matches:
                    break

        if len(matches) < 2:
            return {
                'url': url,
                'schedule_found': False,
                'method': method,
                'ocr_used': ocr_used,
                'error': 'insufficient_time_patterns'
            }

        # Parse times
        times_found = []
        for match in matches:
            time_obj = self._parse_time(match)
            if time_obj:
                times_found.append(time_obj)

        if len(times_found) < 2:
            return {
                'url': url,
                'schedule_found': False,
                'method': method,
                'ocr_used': ocr_used,
                'error': 'could_not_parse_times'
            }

        # Sort and get start/end
        times_sorted = sorted(times_found)
        start_time = times_sorted[0]
        end_time = times_sorted[-1]

        total_minutes = self._calculate_minutes(start_time, end_time)

        # Sanity check
        if not (180 <= total_minutes <= 540):
            return {
                'url': url,
                'schedule_found': False,
                'method': method,
                'ocr_used': ocr_used,
                'error': 'unreasonable_schedule_length',
                'total_minutes': total_minutes
            }

        # Confidence based on method
        confidence = 0.7 if not ocr_used else 0.5

        return {
            'url': url,
            'schedule_found': True,
            'method': method,
            'start_time': start_time.strftime('%I:%M %p'),
            'end_time': end_time.strftime('%I:%M %p'),
            'total_minutes': total_minutes,
            'confidence': confidence,
            'ocr_used': ocr_used
        }

    def _parse_time(self, time_match: Tuple[str, str, str]) -> Optional[dt_time]:
        """Parse time from regex match"""
        try:
            hour, minute, meridiem = time_match
            hour = int(hour)
            minute = int(minute)

            # Convert to 24-hour format
            meridiem_upper = meridiem.upper().replace('.', '')
            if meridiem_upper == 'PM' and hour != 12:
                hour += 12
            elif meridiem_upper == 'AM' and hour == 12:
                hour = 0

            return dt_time(hour, minute)

        except (ValueError, OverflowError):
            return None

    def _calculate_minutes(
        self,
        start_time: dt_time,
        end_time: dt_time
    ) -> int:
        """Calculate minutes between start and end times"""
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute

        if end_minutes < start_minutes:
            end_minutes += 24 * 60

        return end_minutes - start_minutes

    # =========================================================================
    # Result Selection
    # =========================================================================

    def _select_best_result(self, results: List[Dict]) -> Dict:
        """Select best extraction result from multiple attempts"""
        valid_results = [
            r for r in results
            if r.get('schedule_found') and r.get('start_time')
        ]

        if not valid_results:
            return results[0] if results else {}

        # Sort by confidence
        valid_results.sort(key=lambda r: r.get('confidence', 0), reverse=True)
        return valid_results[0]

    # =========================================================================
    # Escalation Logic
    # =========================================================================

    def _should_escalate(self, result: Dict) -> bool:
        """
        Determine if district should escalate to Tier 4

        Escalate if:
            - Schedule found but confidence < 0.7
            - No schedule found despite having documents
            - OCR quality poor
        """
        if result.get('schedule_found') and result.get('confidence', 0) >= 0.7:
            return False

        # Escalate if low confidence or no success
        return True

    def _get_escalation_reason(self, result: Dict) -> Optional[str]:
        """Get human-readable escalation reason"""
        if not result.get('escalation_needed'):
            return None

        if result.get('schedule_found') and result.get('confidence', 0) < 0.7:
            return "schedule_extracted_but_low_confidence"

        if result.get('ocr_used'):
            return "ocr_extraction_failed_need_advanced_processing"

        return "pdf_extraction_failed_need_advanced_processing"


def main():
    """Example usage"""
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        processor = Tier3Processor(session)

        # Example Tier 2 result with PDF links
        tier_2_result = {
            'pdf_links_found': [
                'https://example.org/bell-schedule.pdf'
            ]
        }

        test_district_id = '0622710'  # LA Unified
        result = processor.process_district(test_district_id, tier_2_result)

        import json
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
