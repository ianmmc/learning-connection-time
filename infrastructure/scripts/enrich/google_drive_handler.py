#!/usr/bin/env python3
"""
Google Drive PDF Handler

Handles acquisition of PDFs from Google Drive with fallback chain:
1. Direct download via export URL
2. Playwright preview capture
3. Gemini API extraction (for authenticated content)

This module is used when bell schedule PDFs are hosted on Google Drive,
which is common for many school districts.
"""

import base64
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

import requests

logger = logging.getLogger(__name__)


class GoogleDriveHandler:
    """
    Handle Google Drive PDF acquisition with multiple fallback strategies.

    Fallback order:
    1. Direct download URL (fastest, works for public files)
    2. Playwright preview capture (works for view-only shares)
    3. Gemini API extraction (for authenticated/complex content)
    """

    # Patterns to extract file ID from various Google Drive URL formats
    DRIVE_PATTERNS = [
        r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)',
        r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)',
        r'docs\.google\.com/document/d/([a-zA-Z0-9_-]+)',
        r'docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)',
        r'docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)',
    ]

    def __init__(
        self,
        scraper_url: str = "http://localhost:3000",
        gemini_enabled: bool = True,
        timeout: int = 60
    ):
        """
        Initialize Google Drive handler.

        Args:
            scraper_url: URL of the Playwright scraper service
            gemini_enabled: Whether to use Gemini API as fallback
            timeout: Request timeout in seconds
        """
        self.scraper_url = scraper_url
        self.gemini_enabled = gemini_enabled
        self.timeout = timeout

    def is_google_drive_url(self, url: str) -> bool:
        """Check if URL is a Google Drive/Docs URL"""
        return any(pattern in url for pattern in [
            'drive.google.com',
            'docs.google.com'
        ])

    def extract_file_id(self, url: str) -> Optional[str]:
        """Extract Google file ID from URL"""
        for pattern in self.DRIVE_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Try query parameter
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if 'id' in query_params:
            return query_params['id'][0]

        return None

    def acquire_pdf(
        self,
        url: str,
        output_path: Optional[Path] = None
    ) -> Tuple[bool, Optional[bytes], str]:
        """
        Acquire PDF from Google Drive URL.

        Args:
            url: Google Drive URL
            output_path: Optional path to save PDF

        Returns:
            Tuple of (success, pdf_bytes, method_used)
        """
        if not self.is_google_drive_url(url):
            logger.warning(f"Not a Google Drive URL: {url}")
            return False, None, "not_google_drive"

        file_id = self.extract_file_id(url)
        if not file_id:
            logger.warning(f"Could not extract file ID from: {url}")
            return False, None, "no_file_id"

        # Try 1: Direct download
        logger.info(f"Attempting direct download for file: {file_id}")
        pdf_bytes = self._try_direct_download(file_id)
        if pdf_bytes:
            if output_path:
                output_path.write_bytes(pdf_bytes)
            return True, pdf_bytes, "direct_download"

        # Try 2: Playwright preview capture
        logger.info(f"Direct download failed, trying Playwright preview capture")
        pdf_bytes = self._try_playwright_preview(url)
        if pdf_bytes:
            if output_path:
                output_path.write_bytes(pdf_bytes)
            return True, pdf_bytes, "playwright_preview"

        # Try 3: Gemini API (if enabled)
        if self.gemini_enabled:
            logger.info(f"Playwright capture failed, trying Gemini API")
            pdf_bytes = self._try_gemini_api(url, file_id)
            if pdf_bytes:
                if output_path:
                    output_path.write_bytes(pdf_bytes)
                return True, pdf_bytes, "gemini_api"

        logger.warning(f"All methods failed for Google Drive file: {file_id}")
        return False, None, "all_failed"

    def _try_direct_download(self, file_id: str) -> Optional[bytes]:
        """
        Try direct download via Google Drive export URL.

        Works for:
        - Public files
        - Files shared with "anyone with the link"
        """
        # Export URL for direct download
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        try:
            # First request might redirect or show confirmation for large files
            session = requests.Session()
            response = session.get(
                download_url,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True
            )

            # Check for Google's virus scan warning (large files)
            if 'virus scan warning' in response.text.lower() or 'confirm=' in response.url:
                # Extract confirmation token and retry
                confirm_token = self._get_confirm_token(response)
                if confirm_token:
                    download_url = f"{download_url}&confirm={confirm_token}"
                    response = session.get(
                        download_url,
                        timeout=self.timeout,
                        stream=True
                    )

            # Check if we got a PDF
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' in content_type:
                return response.content

            # Check for HTML error page
            if 'text/html' in content_type:
                logger.debug("Got HTML instead of PDF, file may require authentication")
                return None

            # Try to detect PDF by magic bytes
            content = response.content
            if content[:4] == b'%PDF':
                return content

            return None

        except requests.RequestException as e:
            logger.debug(f"Direct download failed: {e}")
            return None

    def _get_confirm_token(self, response: requests.Response) -> Optional[str]:
        """Extract confirmation token from Google's virus scan warning page"""
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                return value
        return None

    def _try_playwright_preview(self, url: str) -> Optional[bytes]:
        """
        Capture Google Drive preview as PDF using Playwright.

        Works for:
        - View-only shared files
        - Files that can be previewed in browser
        """
        try:
            # Use the scraper service with PDF capture
            response = requests.post(
                f"{self.scraper_url}/scrape",
                json={
                    "url": url,
                    "timeout": self.timeout * 1000,  # ms
                    "waitFor": 3000,  # Wait for preview to load
                    "capturePdf": True,
                    "pdfOptions": {
                        "format": "Letter",
                        "scale": 1.0,
                        "margin": {
                            "top": "0.5in",
                            "bottom": "0.5in",
                            "left": "0.5in",
                            "right": "0.5in"
                        }
                    }
                },
                timeout=self.timeout + 10  # Extra buffer for scraper
            )
            response.raise_for_status()

            result = response.json()

            if result.get('success') and result.get('pdfBase64'):
                pdf_bytes = base64.b64decode(result['pdfBase64'])
                logger.info(f"Playwright captured {len(pdf_bytes)} bytes")
                return pdf_bytes

            if result.get('blocked'):
                logger.warning("Google Drive blocked by security measures")

            return None

        except requests.RequestException as e:
            logger.debug(f"Playwright preview capture failed: {e}")
            return None

    def _try_gemini_api(self, url: str, file_id: str) -> Optional[bytes]:
        """
        Use Gemini API to extract content from Google Drive.

        Works for:
        - Authenticated Google Drive content
        - Complex documents that need AI extraction

        Requires Gemini MCP server to be available.
        """
        try:
            # This would use the Gemini MCP tools
            # For now, we'll use a simpler approach via the API

            # Note: Full Gemini integration requires the MCP server
            # This is a placeholder for the integration

            logger.info("Gemini API extraction not yet implemented")
            return None

            # Future implementation would:
            # 1. Use gemini-upload-file to handle the Drive URL
            # 2. Use gemini-analyze-image or gemini-chat to extract content
            # 3. Convert extracted text/data to PDF format

        except Exception as e:
            logger.debug(f"Gemini API extraction failed: {e}")
            return None

    def get_export_url(self, url: str, format: str = "pdf") -> Optional[str]:
        """
        Get direct export URL for Google Docs/Sheets/Slides.

        Args:
            url: Google Docs URL
            format: Export format (pdf, docx, xlsx, etc.)

        Returns:
            Export URL or None
        """
        file_id = self.extract_file_id(url)
        if not file_id:
            return None

        # Determine document type and build export URL
        if 'docs.google.com/document' in url:
            return f"https://docs.google.com/document/d/{file_id}/export?format={format}"
        elif 'docs.google.com/spreadsheets' in url:
            return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format={format}"
        elif 'docs.google.com/presentation' in url:
            return f"https://docs.google.com/presentation/d/{file_id}/export?format={format}"
        elif 'drive.google.com' in url:
            return f"https://drive.google.com/uc?export=download&id={file_id}"

        return None


def main():
    """Test the Google Drive handler"""
    logging.basicConfig(level=logging.INFO)

    handler = GoogleDriveHandler()

    # Test URL extraction
    test_urls = [
        "https://drive.google.com/file/d/1ABC123xyz/view?usp=sharing",
        "https://docs.google.com/document/d/1DEF456abc/edit",
        "https://drive.google.com/open?id=1GHI789xyz",
    ]

    print("Testing file ID extraction...")
    for url in test_urls:
        file_id = handler.extract_file_id(url)
        print(f"  {url[:50]}... -> {file_id}")

    print("\nTesting export URL generation...")
    for url in test_urls:
        export_url = handler.get_export_url(url)
        print(f"  -> {export_url}")


if __name__ == '__main__':
    main()
