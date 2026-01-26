"""
Acquisition Routes

Endpoints for acquiring bell schedule PDFs from district websites.
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from infrastructure.api.services.crawlee_client import CrawleeClient, PageData
from infrastructure.api.services.ollama_service import OllamaService
from infrastructure.api.services.patterns_service import (
    get_effective_patterns,
    learn_from_ollama_scores,
    get_patterns_summary,
)
from infrastructure.scripts.enrich.google_drive_handler import GoogleDriveHandler

logger = logging.getLogger(__name__)

router = APIRouter()

# Base directory for PDFs
PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"

# Acquisition status storage (in-memory for now)
_acquisition_status: Dict[str, Dict[str, Any]] = {}


class AcquireRequest(BaseModel):
    """Request body for acquisition."""
    district_id: str
    district_name: str
    state: str
    website_url: str
    max_requests: int = 100
    max_depth: int = 4
    top_urls_to_capture: int = 5


class AcquireResponse(BaseModel):
    """Response from acquisition."""
    success: bool
    district_id: str
    status: str
    message: str
    output_dir: Optional[str] = None
    pages_mapped: int = 0
    urls_scored: int = 0
    pdfs_captured: int = 0
    error: Optional[str] = None


def _get_output_dir(state: str, district_id: str, district_name: str) -> Path:
    """Get output directory for a district's PDFs."""
    # Clean district name for filesystem
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in district_name)
    safe_name = safe_name.replace(" ", "_")[:50]
    dir_name = f"{district_id}_{safe_name}"
    return PDF_BASE_DIR / state / dir_name


def _page_data_to_dict(page: PageData) -> Dict[str, Any]:
    """Convert PageData to dict for Ollama."""
    return {
        "url": page.url,
        "title": page.title,
        "depth": page.depth,
        "meta_description": page.meta_description,
        "h1": page.h1,
        "breadcrumb": page.breadcrumb,
        "link_text_used_to_reach_page": page.link_text_used_to_reach_page,
        "time_pattern_count": page.time_pattern_count,
        "has_schedule_pdf_link": page.has_schedule_pdf_link,
        "keyword_match_count": page.keyword_match_count,
    }


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF using pdftotext."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        else:
            logger.warning(f"pdftotext failed for {pdf_path}: {result.stderr}")
            return ""
    except FileNotFoundError:
        logger.error("pdftotext not found. Install with: brew install poppler")
        return ""
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return ""


def _is_direct_pdf_url(url: str) -> bool:
    """Check if URL points directly to a PDF file."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    return path_lower.endswith('.pdf') or '.pdf?' in url.lower()


def _is_google_drive_url(url: str) -> bool:
    """Check if URL is a Google Drive or Google Docs URL."""
    return 'drive.google.com' in url or 'docs.google.com' in url


def _download_direct_pdf(url: str, output_path: Path, timeout: int = 60) -> Tuple[bool, str]:
    """
    Download a PDF directly from a URL.

    Returns:
        Tuple of (success, error_message)
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()

        # Verify it's a PDF
        content_type = response.headers.get('content-type', '').lower()
        content = response.content

        if 'application/pdf' in content_type or content[:4] == b'%PDF':
            output_path.write_bytes(content)
            logger.info(f"Downloaded PDF directly: {url} -> {output_path}")
            return True, ""
        else:
            return False, f"Not a PDF (content-type: {content_type})"

    except requests.RequestException as e:
        return False, str(e)


async def _handle_special_urls(
    urls: List[str],
    output_dir: Path,
    crawlee: CrawleeClient,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Handle Google Drive URLs and direct PDF URLs separately from normal page capture.

    Returns:
        Tuple of (results_list, remaining_urls_for_crawlee)
    """
    results = []
    remaining_urls = []
    gdrive_handler = GoogleDriveHandler()

    for i, url in enumerate(urls):
        filename_base = f"page_{i+1:03d}"

        if _is_google_drive_url(url):
            # Handle Google Drive URL
            logger.info(f"Detected Google Drive URL: {url}")
            output_path = output_dir / f"{filename_base}_gdrive.pdf"

            success, pdf_bytes, method = gdrive_handler.acquire_pdf(url, output_path)

            if success:
                results.append({
                    "url": url,
                    "success": True,
                    "filepath": str(output_path),
                    "filename": output_path.name,
                    "method": f"google_drive_{method}",
                })
            else:
                results.append({
                    "url": url,
                    "success": False,
                    "filepath": None,
                    "filename": None,
                    "error": f"Google Drive acquisition failed: {method}",
                })

        elif _is_direct_pdf_url(url):
            # Handle direct PDF URL
            logger.info(f"Detected direct PDF URL: {url}")

            # Create filename from URL path
            parsed = urlparse(url)
            url_filename = Path(parsed.path).stem[:30] or "document"
            safe_filename = "".join(c if c.isalnum() or c in "_-" else "_" for c in url_filename)
            output_path = output_dir / f"{filename_base}_{safe_filename}.pdf"

            success, error = _download_direct_pdf(url, output_path)

            if success:
                results.append({
                    "url": url,
                    "success": True,
                    "filepath": str(output_path),
                    "filename": output_path.name,
                    "method": "direct_download",
                })
            else:
                # Fall back to Crawlee capture if direct download fails
                logger.info(f"Direct PDF download failed ({error}), falling back to Crawlee")
                remaining_urls.append(url)
        else:
            # Normal HTML page - use Crawlee
            remaining_urls.append(url)

    return results, remaining_urls


async def _run_acquisition(request: AcquireRequest):
    """
    Run the full acquisition pipeline for a district.

    Steps:
    1. Map website with Crawlee
    2. Rank URLs with Ollama
    3. Capture top URLs as PDFs
    4. Extract text with pdftotext
    5. Triage PDFs with Ollama
    6. Organize into active/quarantine/rejected
    """
    district_id = request.district_id
    _acquisition_status[district_id] = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "step": "initializing",
    }

    crawlee = CrawleeClient()
    ollama_svc = OllamaService()
    output_dir = _get_output_dir(request.state, request.district_id, request.district_name)

    try:
        # Step 1: Check Crawlee health
        _acquisition_status[district_id]["step"] = "checking_crawlee"
        if not await crawlee.health_check():
            raise Exception("Crawlee service not available")

        # Step 1.5: Load URL patterns for filtering
        # Note: Include patterns are used for SCORING not crawl filtering
        # We crawl broadly and filter results; only exclude patterns limit crawling
        effective_patterns = get_effective_patterns()
        logger.info(f"Using patterns: {len(effective_patterns.include_globs)} include (for scoring), "
                   f"{len(effective_patterns.exclude_globs)} exclude (for crawl filtering) "
                   f"(learned: +{effective_patterns.learned_positive_count}, "
                   f"-{effective_patterns.learned_negative_count})")

        # Step 2: Map website - crawl broadly, only exclude obvious non-targets
        _acquisition_status[district_id]["step"] = "mapping_website"
        map_result = await crawlee.map_website(
            url=request.website_url,
            max_requests=request.max_requests,
            max_depth=request.max_depth,
            # Don't pass include_globs - we want broad crawling, not filtered
            exclude_globs=effective_patterns.exclude_globs,
        )

        if not map_result.success:
            raise Exception(f"Website mapping failed: {map_result.error}")

        _acquisition_status[district_id]["pages_mapped"] = map_result.pages_visited
        logger.info(f"Mapped {map_result.pages_visited} pages for {district_id}")

        # Step 3: Rank URLs with Ollama
        _acquisition_status[district_id]["step"] = "ranking_urls"
        pages_for_ranking = [_page_data_to_dict(p) for p in map_result.pages]
        url_scores = await ollama_svc.rank_urls(pages_for_ranking, request.district_name)

        _acquisition_status[district_id]["urls_scored"] = len(url_scores)

        # Step 3.5: Learn from URL scores (updates patterns for future runs)
        score_dicts = [{"url": s.url, "score": s.score, "reason": s.reason} for s in url_scores]
        learn_from_ollama_scores(score_dicts, district_id=district_id)

        # Get top URLs for capture
        top_urls = [s.url for s in url_scores[:request.top_urls_to_capture] if s.score >= 0.3]

        if not top_urls:
            logger.warning(f"No URLs scored above threshold for {district_id}")
            _acquisition_status[district_id]["status"] = "completed_no_candidates"
            _acquisition_status[district_id]["message"] = "No high-scoring URLs found"
            return

        logger.info(f"Top {len(top_urls)} URLs for capture: {top_urls}")

        # Step 4: Capture PDFs
        _acquisition_status[district_id]["step"] = "capturing_pdfs"

        # Create directory structure
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "active").mkdir(exist_ok=True)
        (output_dir / "quarantine").mkdir(exist_ok=True)
        (output_dir / "rejected").mkdir(exist_ok=True)

        # Step 4a: Handle special URLs (Google Drive, direct PDFs)
        special_results, remaining_urls = await _handle_special_urls(
            top_urls, output_dir, crawlee
        )

        # Log special URL handling
        gdrive_count = len([r for r in special_results if "google_drive" in r.get("method", "")])
        direct_count = len([r for r in special_results if r.get("method") == "direct_download"])
        if gdrive_count or direct_count:
            logger.info(f"Handled {gdrive_count} Google Drive URLs, {direct_count} direct PDFs")

        # Step 4b: Capture remaining URLs with Crawlee
        all_capture_results = list(special_results)

        if remaining_urls:
            capture_result = await crawlee.capture_pages(
                urls=remaining_urls,
                output_dir=str(output_dir),
            )

            # Convert Crawlee results to our format
            for result in capture_result.results:
                all_capture_results.append({
                    "url": result.url,
                    "success": result.success,
                    "filepath": result.filepath,
                    "filename": result.filename,
                    "method": "crawlee_capture",
                    "error": result.error,
                })

        successful_captures = len([r for r in all_capture_results if r.get("success")])
        _acquisition_status[district_id]["pdfs_captured"] = successful_captures
        logger.info(f"Captured {successful_captures}/{len(all_capture_results)} PDFs")

        # Step 5: Extract text and triage
        _acquisition_status[district_id]["step"] = "triaging_pdfs"
        triage_results = []

        for result in all_capture_results:
            if not result.get("success") or not result.get("filepath"):
                continue

            pdf_path = Path(result["filepath"])
            if not pdf_path.exists():
                continue

            # Extract text
            pdf_text = _extract_pdf_text(pdf_path)

            # Save extracted text
            txt_path = pdf_path.with_suffix(".txt")
            txt_path.write_text(pdf_text)

            # Triage with Ollama
            triage = await ollama_svc.triage_pdf(pdf_text)

            # Move to appropriate directory
            if triage.score >= 0.7:
                dest_dir = output_dir / "active"
            elif triage.score >= 0.3:
                dest_dir = output_dir / "quarantine"
            else:
                dest_dir = output_dir / "rejected"

            # Move PDF and text file
            new_pdf_path = dest_dir / pdf_path.name
            new_txt_path = dest_dir / txt_path.name
            pdf_path.rename(new_pdf_path)
            txt_path.rename(new_txt_path)

            triage_results.append({
                "url": result["url"],
                "filename": result.get("filename"),
                "method": result.get("method", "unknown"),
                "score": triage.score,
                "reason": triage.reason,
                "status": "active" if triage.score >= 0.7 else "quarantine" if triage.score >= 0.3 else "rejected",
            })

        # Step 6: Save metadata
        _acquisition_status[district_id]["step"] = "saving_metadata"

        metadata = {
            "district_id": request.district_id,
            "district_name": request.district_name,
            "state": request.state,
            "website_url": request.website_url,
            "acquisition_started": _acquisition_status[district_id]["started_at"],
            "acquisition_completed": datetime.now(timezone.utc).isoformat(),
            "status": "triaged",
            "pages_mapped": map_result.pages_visited,
            "urls_scored": len(url_scores),
            "pdfs_captured": successful_captures,
            "capture_methods": {
                "google_drive": gdrive_count,
                "direct_download": direct_count,
                "crawlee_capture": len(remaining_urls),
            },
            "triage_results": {
                "active": len([t for t in triage_results if t["status"] == "active"]),
                "quarantine": len([t for t in triage_results if t["status"] == "quarantine"]),
                "rejected": len([t for t in triage_results if t["status"] == "rejected"]),
            },
            "sources": [
                {
                    "url": s.url,
                    "ollama_url_score": s.score,
                    "ollama_url_reason": s.reason,
                }
                for s in url_scores[:request.top_urls_to_capture]
            ],
            "triage_details": triage_results,
        }

        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Update status
        _acquisition_status[district_id] = {
            "status": "completed",
            "started_at": _acquisition_status[district_id]["started_at"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(output_dir),
            "pages_mapped": map_result.pages_visited,
            "urls_scored": len(url_scores),
            "pdfs_captured": successful_captures,
            "capture_methods": metadata["capture_methods"],
            "triage_results": metadata["triage_results"],
        }

        logger.info(f"Acquisition complete for {district_id}")

    except Exception as e:
        logger.error(f"Acquisition failed for {district_id}: {e}")
        _acquisition_status[district_id] = {
            "status": "failed",
            "started_at": _acquisition_status[district_id].get("started_at"),
            "error": str(e),
            "step": _acquisition_status[district_id].get("step"),
        }

    finally:
        await crawlee.close()


@router.post("/district/{district_id}", response_model=AcquireResponse)
async def acquire_district(
    district_id: str,
    request: AcquireRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start acquisition for a district.

    This endpoint starts the acquisition process in the background and returns immediately.
    Use GET /acquire/status/{district_id} to check progress.
    """
    # Validate district_id matches request
    if district_id != request.district_id:
        raise HTTPException(
            status_code=400,
            detail="district_id in URL must match request body"
        )

    # Check if already running
    if district_id in _acquisition_status:
        status = _acquisition_status[district_id]
        if status.get("status") == "running":
            return AcquireResponse(
                success=False,
                district_id=district_id,
                status="already_running",
                message="Acquisition already in progress",
            )

    # Start acquisition in background
    background_tasks.add_task(_run_acquisition, request)

    return AcquireResponse(
        success=True,
        district_id=district_id,
        status="started",
        message="Acquisition started in background",
    )


@router.get("/status/{district_id}")
async def get_acquisition_status(district_id: str):
    """Get the status of an acquisition."""
    if district_id not in _acquisition_status:
        raise HTTPException(
            status_code=404,
            detail=f"No acquisition found for district {district_id}"
        )

    return _acquisition_status[district_id]
