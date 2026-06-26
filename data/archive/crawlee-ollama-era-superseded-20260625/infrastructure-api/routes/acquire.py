"""
Acquisition Routes

Endpoints for acquiring bell schedule PDFs from district websites.
Includes queue management for serial processing.
"""

import asyncio
import json
import logging
import os
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
    learn_from_triage_results,
    get_patterns_summary,
)
from infrastructure.api.services.queue_service import acquisition_queue
from infrastructure.scripts.enrich.google_drive_handler import GoogleDriveHandler

logger = logging.getLogger(__name__)

router = APIRouter()

# Base directory for PDFs
PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"

# Acquisition status storage (in-memory for now)
_acquisition_status: Dict[str, Dict[str, Any]] = {}

# Queue processing state
_current_task: Optional[asyncio.Task] = None
_stop_requested = False
_processing_active = False


class AcquireRequest(BaseModel):
    """Request body for acquisition."""
    district_id: str
    district_name: str
    state: str
    website_url: str
    max_requests: int = 30  # Reduced from 100 for faster response
    max_depth: int = 4
    top_urls_to_capture: int = 5
    use_school_discovery: bool = True  # Enable school-level mapping by default
    schools_per_band: int = 4  # Schools to sample per grade band


class QueueRequest(BaseModel):
    """Request body for adding to queue."""
    districts: List[AcquireRequest]


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

        # Step 2: Map website(s)
        # If school discovery is enabled, first discover schools then map each
        all_pages = []
        schools_mapped = []

        if request.use_school_discovery:
            # Step 2a: Discover schools
            _acquisition_status[district_id]["step"] = "discovering_schools"
            logger.info(f"Discovering schools for {district_id} ({request.website_url})")

            discovery_result = await crawlee.discover_schools(
                district_url=request.website_url,
                state=request.state,
                per_band=request.schools_per_band,
            )

            if not discovery_result.success or not discovery_result.sample:
                logger.warning(f"School discovery failed or found no schools, falling back to district mapping")
                # Fall back to district-level mapping
                request.use_school_discovery = False
            else:
                _acquisition_status[district_id]["schools_discovered"] = len(discovery_result.schools)
                _acquisition_status[district_id]["schools_sampled"] = len(discovery_result.sample)

                # Log discovery results
                levels = {"elementary": 0, "middle": 0, "high": 0, "unknown": 0}
                for s in discovery_result.sample:
                    levels[s.level or "unknown"] += 1
                logger.info(f"Discovered {len(discovery_result.schools)} schools, "
                           f"sampling {len(discovery_result.sample)}: "
                           f"elem={levels['elementary']}, middle={levels['middle']}, "
                           f"high={levels['high']}, unknown={levels['unknown']}")

                # Step 2b: Map each sampled school using async jobs
                _acquisition_status[district_id]["step"] = "mapping_schools"

                # Start all jobs in parallel
                job_ids = []
                for school in discovery_result.sample:
                    job_id = await crawlee.start_map_job(
                        url=school.url,
                        max_requests=request.max_requests,
                        max_depth=request.max_depth,
                        exclude_globs=effective_patterns.exclude_globs,
                    )
                    if job_id:
                        job_ids.append((school, job_id))
                        logger.info(f"Started mapping job {job_id} for {school.name} ({school.url})")

                # Wait for all jobs to complete
                for school, job_id in job_ids:
                    _acquisition_status[district_id]["step"] = f"mapping_{school.level or 'school'}_{len(schools_mapped)+1}"

                    result = await crawlee.wait_for_job(job_id, timeout=180.0)

                    if result.success:
                        all_pages.extend(result.pages)
                        schools_mapped.append({
                            "name": school.name,
                            "url": school.url,
                            "level": school.level,
                            "pages_mapped": result.pages_visited,
                            "pages_with_time_patterns": result.pages_with_time_patterns,
                        })
                        logger.info(f"Mapped {result.pages_visited} pages from {school.name}")
                    else:
                        logger.warning(f"Failed to map {school.name}: {result.error}")

                _acquisition_status[district_id]["schools_mapped_details"] = schools_mapped

        # Fall back to district-level mapping if school discovery not used or failed
        if not request.use_school_discovery or not all_pages:
            _acquisition_status[district_id]["step"] = "mapping_website"
            map_result = await crawlee.map_website(
                url=request.website_url,
                max_requests=request.max_requests,
                max_depth=request.max_depth,
                exclude_globs=effective_patterns.exclude_globs,
            )

            if not map_result.success:
                error_msg = map_result.error or "Unknown error"
                raise Exception(f"Website mapping failed: {error_msg}")

            all_pages = map_result.pages
            _acquisition_status[district_id]["mapping_mode"] = "district"
        else:
            _acquisition_status[district_id]["mapping_mode"] = "school_level"

        _acquisition_status[district_id]["pages_mapped"] = len(all_pages)
        logger.info(f"Mapped {len(all_pages)} total pages for {district_id}")

        # Step 3: Rank URLs with Ollama
        _acquisition_status[district_id]["step"] = "ranking_urls"
        pages_for_ranking = [_page_data_to_dict(p) for p in all_pages]
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

        # Step 5.5: Feed triage results to learning loop
        # This automatically updates patterns for future acquisitions
        learn_from_triage_results(triage_results, district_id=district_id)

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
            "mapping_mode": _acquisition_status[district_id].get("mapping_mode", "district"),
            "pages_mapped": len(all_pages),
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

        # Add school-level mapping details if used
        if schools_mapped:
            metadata["schools_mapped"] = schools_mapped
            metadata["schools_discovered"] = _acquisition_status[district_id].get("schools_discovered", 0)
            metadata["schools_sampled"] = _acquisition_status[district_id].get("schools_sampled", 0)

        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Update status
        _acquisition_status[district_id] = {
            "status": "completed",
            "started_at": _acquisition_status[district_id]["started_at"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(output_dir),
            "mapping_mode": metadata["mapping_mode"],
            "pages_mapped": len(all_pages),
            "urls_scored": len(url_scores),
            "pdfs_captured": successful_captures,
            "capture_methods": metadata["capture_methods"],
            "triage_results": metadata["triage_results"],
        }
        if schools_mapped:
            _acquisition_status[district_id]["schools_mapped"] = len(schools_mapped)

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


# ============================================================================
# Queue Management Endpoints
# ============================================================================

@router.get("/queue")
async def get_queue():
    """
    Get current queue status.

    Returns pending districts, currently running district, and counts.
    """
    status = acquisition_queue.get_status()
    status["processing_active"] = _processing_active
    return status


@router.post("/queue")
async def add_to_queue(request: AcquireRequest):
    """
    Add a single district to the acquisition queue.

    Use POST /acquire/start to begin processing the queue.
    """
    position = acquisition_queue.add(request.model_dump())
    return {
        "status": "queued",
        "district_id": request.district_id,
        "position": position,
    }


@router.post("/queue/batch")
async def add_batch_to_queue(request: QueueRequest):
    """
    Add multiple districts to the acquisition queue.

    Use POST /acquire/start to begin processing the queue.
    """
    districts = [d.model_dump() for d in request.districts]
    new_length = acquisition_queue.add_batch(districts)
    return {
        "status": "queued",
        "districts_added": len(districts),
        "queue_length": new_length,
    }


@router.delete("/queue/{district_id}")
async def remove_from_queue(district_id: str):
    """
    Remove a district from the pending queue.

    Does not affect currently running acquisition.
    Use POST /acquire/cancel/{district_id} to cancel a running acquisition.
    """
    if acquisition_queue.remove(district_id):
        return {"status": "removed", "district_id": district_id}
    raise HTTPException(404, f"District {district_id} not in queue")


@router.post("/cancel/{district_id}")
async def cancel_acquisition(district_id: str):
    """
    Cancel a running acquisition.

    If the district is currently processing, cancels it.
    If pending in queue, removes it from queue.
    """
    global _current_task

    # Check if it's the current running acquisition
    current = acquisition_queue.get_current()
    if current and current.get("district_id") == district_id:
        if _current_task and not _current_task.done():
            _current_task.cancel()
            return {"status": "cancellation_requested", "district_id": district_id}
        return {"status": "already_completed", "district_id": district_id}

    # Check if it's in the pending queue
    if acquisition_queue.remove(district_id):
        return {"status": "removed_from_queue", "district_id": district_id}

    raise HTTPException(404, f"District {district_id} not found in queue or running")


@router.post("/start")
async def start_processing(background_tasks: BackgroundTasks):
    """
    Start processing the queue serially.

    Districts are processed one at a time in FIFO order.
    Use GET /acquire/queue to check progress.
    Use POST /acquire/stop to stop after current completes.
    """
    global _stop_requested, _processing_active

    if _processing_active:
        return {"status": "already_running"}

    _stop_requested = False
    background_tasks.add_task(_process_queue)

    return {"status": "started"}


@router.post("/stop")
async def stop_processing():
    """
    Stop queue processing after current acquisition completes.

    Does not cancel the current acquisition - it will finish.
    Pending items remain in queue for next start.
    """
    global _stop_requested
    _stop_requested = True
    return {"status": "stop_requested"}


@router.get("/queue/history")
async def get_queue_history(limit: int = 10):
    """Get recent acquisition history."""
    return {"history": acquisition_queue.get_history(limit)}


async def _process_queue():
    """
    Process queue items serially (one at a time).

    This runs as a background task and processes districts
    from the queue until it's empty or stop is requested.
    """
    global _current_task, _stop_requested, _processing_active

    _processing_active = True
    logger.info("Queue processing started")

    try:
        while not _stop_requested:
            # Get next district from queue
            district = acquisition_queue.get_next()
            if not district:
                logger.info("Queue empty, stopping")
                break

            district_id = district.get("district_id")
            logger.info(f"Processing district from queue: {district_id}")

            # Mark as current
            acquisition_queue.set_current(district, os.getpid())

            # Create request object
            request = AcquireRequest(**district)

            try:
                # Run acquisition as cancellable task
                _current_task = asyncio.create_task(_run_acquisition(request))
                await _current_task

                # Move to history with success
                acquisition_queue.move_to_history(
                    district_id,
                    status=_acquisition_status.get(district_id, {}).get("status", "completed"),
                )

            except asyncio.CancelledError:
                logger.info(f"Acquisition cancelled: {district_id}")
                acquisition_queue.move_to_history(district_id, status="cancelled")
                # Continue processing next item unless stop was requested
                if _stop_requested:
                    break

            except Exception as e:
                logger.error(f"Acquisition failed: {district_id} - {e}")
                acquisition_queue.move_to_history(district_id, status="failed", error=str(e))

            finally:
                acquisition_queue.clear_current()
                _current_task = None

    finally:
        _processing_active = False
        logger.info("Queue processing stopped")
