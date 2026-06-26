"""
Triage Routes

Endpoints for PDF triage and scoring.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure.api.services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

router = APIRouter()


class TriageRequest(BaseModel):
    """Request body for PDF triage."""
    pdf_text: str


class TriageResponse(BaseModel):
    """Response from PDF triage."""
    score: float
    reason: str
    times_found: list[str]
    is_bell_schedule: bool
    recommendation: str


@router.post("/pdf", response_model=TriageResponse)
async def triage_pdf(request: TriageRequest):
    """
    Score PDF text for bell schedule content.

    Returns a score 0.0-1.0 indicating likelihood of bell schedule content.
    """
    if not request.pdf_text or len(request.pdf_text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="pdf_text must be non-empty and at least 10 characters"
        )

    ollama_svc = OllamaService()
    result = await ollama_svc.triage_pdf(request.pdf_text)

    # Determine recommendation based on score
    if result.score >= 0.7:
        recommendation = "active - likely contains bell schedule"
    elif result.score >= 0.3:
        recommendation = "quarantine - review manually"
    else:
        recommendation = "rejected - unlikely to contain bell schedule"

    return TriageResponse(
        score=result.score,
        reason=result.reason,
        times_found=result.times_found,
        is_bell_schedule=result.is_bell_schedule,
        recommendation=recommendation,
    )
