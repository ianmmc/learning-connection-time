"""
enrich.py - FastAPI routes for bell schedule enrichment pipeline

PURPOSE:
    Provides HTTP endpoints for the Phase 8 Enrichment Pipeline, primarily
    the POST /enrich/extract endpoint that triggers Ollama-based time extraction
    from PDF text.

CONTEXT - ENRICHMENT PIPELINE POSITION:
    This router provides the API interface for Step 1 of the enrichment pipeline:
    1. Ollama extraction (POST /enrich/extract) → extraction_result.json  <-- THIS ROUTER
    2. Claude verification → verified_extraction.json
    3. calculate_minutes.py → enrichment_ready.json
    4. import_bell_schedules.py → database + import_result.json
    5. verify_enrichment.py → verification_report.json

ENDPOINTS:
    POST /enrich/extract - Extract times from PDF text using Ollama
    GET /enrich/status/{district_id} - Check extraction status for a district
    GET /enrich/files/{district_id} - List enrichment files for a district

INPUT:
    POST /enrich/extract expects JSON body:
    {
        "district_id": "1200390",
        "district_name": "Pasco County",
        "state": "FL",
        "pdf_file": "page_001.txt"  // Optional: specific file in active/
    }

OUTPUT:
    - extraction_result.json written to district's PDF folder
    - JSON response with extraction summary

USAGE:
    curl -X POST localhost:8000/enrich/extract \\
      -H "Content-Type: application/json" \\
      -d '{"district_id": "1200390", "pdf_file": "page_001.txt"}'

SEE ALSO:
    - Plan: ~/.claude/plans/crispy-brewing-blanket.md (Phase 8)
    - Related: extraction_service.py (Ollama extraction logic)
"""

import logging
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure.api.services.extraction_service import extraction_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Base directory for bell schedule PDFs
PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"


class ExtractRequest(BaseModel):
    """Request body for extraction endpoint."""
    district_id: str
    district_name: Optional[str] = None
    state: Optional[str] = None
    pdf_file: Optional[str] = None  # Specific file to extract from


class ExtractResponse(BaseModel):
    """Response from extraction endpoint."""
    success: bool
    district_id: str
    schedules_extracted: int
    output_file: Optional[str] = None
    error: Optional[str] = None


class EnrichmentFile(BaseModel):
    """Info about an enrichment file."""
    name: str
    path: str
    exists: bool


class EnrichmentStatus(BaseModel):
    """Status of enrichment for a district."""
    district_id: str
    has_pdfs: bool
    pdf_count: int
    has_extraction: bool
    has_verified: bool
    has_enrichment_ready: bool
    has_import_result: bool
    has_verification: bool
    files: List[EnrichmentFile]


def _find_district_dir(district_id: str) -> Optional[Path]:
    """Find the district directory by ID prefix."""
    for state_dir in PDF_BASE_DIR.iterdir():
        if not state_dir.is_dir():
            continue
        for district_dir in state_dir.iterdir():
            if district_dir.is_dir() and district_dir.name.startswith(district_id):
                return district_dir
    return None


def _get_district_metadata(district_dir: Path) -> dict:
    """Get district metadata from metadata.json."""
    import json
    metadata_file = district_dir / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file) as f:
            return json.load(f)
    return {}


def _read_pdf_text(district_dir: Path, pdf_file: Optional[str] = None) -> tuple[str, str]:
    """
    Read PDF text from active directory.

    Returns:
        Tuple of (text_content, source_filename)
    """
    active_dir = district_dir / "active"

    if not active_dir.exists():
        raise HTTPException(404, f"No active directory found: {active_dir}")

    # Find text files in active directory and subdirectories (e.g., active/converted/)
    txt_files = list(active_dir.glob("*.txt")) + list(active_dir.glob("**/*.txt"))
    # Remove duplicates while preserving order
    seen = set()
    txt_files = [f for f in txt_files if f not in seen and not seen.add(f)]

    if not txt_files:
        raise HTTPException(404, "No .txt files found in active directory")

    # Use specific file if provided
    if pdf_file:
        # Handle both .pdf and .txt extensions
        txt_name = pdf_file.replace(".pdf", ".txt") if pdf_file.endswith(".pdf") else pdf_file
        txt_path = active_dir / txt_name
        if not txt_path.exists():
            raise HTTPException(404, f"File not found: {txt_name}")
        txt_files = [txt_path]

    # Concatenate all text files
    combined_text = ""
    source_files = []
    for txt_file in txt_files:
        with open(txt_file) as f:
            combined_text += f"\n--- From {txt_file.name} ---\n"
            combined_text += f.read()
        source_files.append(txt_file.name)

    return combined_text, ", ".join(source_files)


@router.post("/extract", response_model=ExtractResponse)
async def extract_times(request: ExtractRequest):
    """
    Extract bell schedule times from PDF text using Ollama.

    This endpoint:
    1. Locates the district's PDF directory
    2. Reads text files from the active/ subdirectory
    3. Calls Ollama to extract structured time data
    4. Saves extraction_result.json to the district directory

    The output is meant to be verified by Claude before proceeding
    to the calculate_minutes.py step.
    """
    district_id = request.district_id

    # Find district directory
    district_dir = _find_district_dir(district_id)
    if not district_dir:
        raise HTTPException(404, f"District directory not found for {district_id}")

    # Get metadata for district name and state
    metadata = _get_district_metadata(district_dir)
    district_name = request.district_name or metadata.get("district_name", "Unknown District")
    state = request.state or metadata.get("state", "XX")

    # Read PDF text
    try:
        pdf_text, source_files = _read_pdf_text(district_dir, request.pdf_file)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error reading PDF text: {e}")

    logger.info(f"Extracting times for {district_name} ({district_id}) from {source_files}")

    # Run extraction
    result = await extraction_service.extract_times(
        pdf_text=pdf_text,
        district_id=district_id,
        district_name=district_name,
        state=state,
        source_file=source_files,
    )

    # Save result
    output_path = extraction_service.save_result(result, district_dir)

    return ExtractResponse(
        success=result.success,
        district_id=district_id,
        schedules_extracted=len(result.schedules),
        output_file=str(output_path.relative_to(PDF_BASE_DIR.parent.parent)),
        error=result.error,
    )


@router.get("/status/{district_id}", response_model=EnrichmentStatus)
async def get_enrichment_status(district_id: str):
    """
    Get enrichment pipeline status for a district.

    Shows which steps have been completed and which files exist.
    """
    district_dir = _find_district_dir(district_id)
    if not district_dir:
        raise HTTPException(404, f"District directory not found for {district_id}")

    active_dir = district_dir / "active"

    # Count PDFs
    pdf_count = 0
    if active_dir.exists():
        pdf_count = len(list(active_dir.glob("*.pdf"))) + len(list(active_dir.glob("*.txt")))

    # Check enrichment files
    enrichment_files = [
        ("extraction_result.json", "Ollama extraction output"),
        ("verified_extraction.json", "Claude verification output"),
        ("enrichment_ready.json", "After minutes calculation"),
        ("import_result.json", "Database import result"),
        ("verification_report.json", "Final verification"),
    ]

    files = []
    for filename, _ in enrichment_files:
        file_path = district_dir / filename
        files.append(EnrichmentFile(
            name=filename,
            path=str(file_path.relative_to(PDF_BASE_DIR.parent.parent)) if file_path.exists() else "",
            exists=file_path.exists(),
        ))

    return EnrichmentStatus(
        district_id=district_id,
        has_pdfs=pdf_count > 0,
        pdf_count=pdf_count,
        has_extraction=(district_dir / "extraction_result.json").exists(),
        has_verified=(district_dir / "verified_extraction.json").exists(),
        has_enrichment_ready=(district_dir / "enrichment_ready.json").exists(),
        has_import_result=(district_dir / "import_result.json").exists(),
        has_verification=(district_dir / "verification_report.json").exists(),
        files=files,
    )


@router.get("/files/{district_id}")
async def list_enrichment_files(district_id: str):
    """
    List all files in a district's enrichment directory.

    Useful for debugging and understanding pipeline state.
    """
    district_dir = _find_district_dir(district_id)
    if not district_dir:
        raise HTTPException(404, f"District directory not found for {district_id}")

    files = {
        "active": [],
        "quarantine": [],
        "rejected": [],
        "enrichment": [],
    }

    # List files in each subdirectory
    for subdir in ["active", "quarantine", "rejected"]:
        subdir_path = district_dir / subdir
        if subdir_path.exists():
            files[subdir] = [f.name for f in subdir_path.iterdir() if f.is_file()]

    # List enrichment JSON files in root
    enrichment_patterns = ["*_result.json", "*_extraction.json", "*_report.json", "metadata.json"]
    for pattern in enrichment_patterns:
        for f in district_dir.glob(pattern):
            files["enrichment"].append(f.name)

    return {
        "district_id": district_id,
        "directory": str(district_dir),
        "files": files,
    }
