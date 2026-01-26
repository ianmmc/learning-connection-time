"""
Patterns Routes

Endpoints for managing learning patterns with human review support.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure.api.services.patterns_service import (
    load_patterns,
    save_patterns,
    get_effective_patterns,
    learn_from_url,
    record_feedback,
    get_patterns_for_review,
    approve_pattern,
    reject_pattern,
    get_patterns_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class LearnRequest(BaseModel):
    """Request body for learning from feedback."""
    url: str
    is_bell_schedule: bool
    district_id: Optional[str] = None
    confidence: float = 0.9


class FeedbackRequest(BaseModel):
    """Request body for recording user feedback on a URL."""
    url: str
    is_bell_schedule: bool
    district_id: Optional[str] = None


class PatternActionRequest(BaseModel):
    """Request body for approving/rejecting a pattern."""
    pattern: str


class PatternsResponse(BaseModel):
    """Response with current patterns."""
    version: str
    updated_at: str
    url_include_globs: List[str]
    url_exclude_globs: List[str]
    learned_positive: List[dict]
    learned_negative: List[dict]


class EffectivePatternsResponse(BaseModel):
    """Response with effective patterns for crawling."""
    include_globs: List[str]
    exclude_globs: List[str]
    learned_positive_count: int
    learned_negative_count: int


@router.get("", response_model=PatternsResponse)
async def get_patterns():
    """Get current learning patterns (raw)."""
    patterns = load_patterns()
    return PatternsResponse(**patterns)


@router.get("/effective", response_model=EffectivePatternsResponse)
async def get_effective():
    """
    Get effective patterns for Crawlee crawling.

    This merges base patterns with approved and high-confidence learned patterns.
    """
    effective = get_effective_patterns()
    return EffectivePatternsResponse(
        include_globs=effective.include_globs,
        exclude_globs=effective.exclude_globs,
        learned_positive_count=effective.learned_positive_count,
        learned_negative_count=effective.learned_negative_count,
    )


@router.get("/summary")
async def get_summary():
    """
    Get a summary of patterns state.

    Includes counts by status and number of patterns needing review.
    """
    return get_patterns_summary()


@router.get("/review")
async def get_review_list():
    """
    Get patterns that need human review.

    Returns patterns sorted by priority:
    1. Status = 'review' (ready for approval, seen in 3+ districts with good success)
    2. Status = 'flagged' (low success rate, may need removal)
    3. Patterns with concerning metrics
    """
    return get_patterns_for_review()


@router.post("/learn")
async def learn_from_url_feedback(request: LearnRequest):
    """
    Learn a new pattern from a URL.

    Extracts semantic keywords (bell, schedule, hours, etc.) from the URL
    to create generalizable patterns that work across districts.
    """
    pattern = learn_from_url(
        url=request.url,
        is_bell_schedule=request.is_bell_schedule,
        district_id=request.district_id,
        confidence=request.confidence,
    )

    if not pattern:
        return {
            "success": False,
            "message": "No semantic keywords found in URL",
        }

    learned_key = "learned_positive" if request.is_bell_schedule else "learned_negative"
    return {
        "success": True,
        "message": f"Pattern '{pattern}' added to {learned_key}",
        "pattern": pattern,
        "learned_list": learned_key,
    }


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """
    Record user feedback on a URL (confirmed or rejected as bell schedule).

    Updates success tracking for matching patterns. Patterns with high
    success rates across multiple districts become eligible for approval.
    Patterns with low success rates get flagged for removal.
    """
    result = record_feedback(
        url=request.url,
        is_bell_schedule=request.is_bell_schedule,
        district_id=request.district_id,
    )
    return result


@router.post("/approve")
async def approve_learned_pattern(request: PatternActionRequest):
    """
    Approve a learned pattern for permanent inclusion.

    Approved patterns are always included in effective patterns
    regardless of occurrence count.
    """
    result = approve_pattern(request.pattern)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/reject")
async def reject_learned_pattern(request: PatternActionRequest):
    """
    Reject and remove a learned pattern.

    The pattern is deleted from learned lists and will not be used.
    """
    result = reject_pattern(request.pattern)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/reset")
async def reset_patterns():
    """Reset patterns to defaults (clears all learned patterns)."""
    default_patterns = {
        "version": "2.0",
        "url_include_globs": [
            "**/bell*schedule*",
            "**/school*hours*",
            "**/daily*schedule*",
            "**/start*time*",
        ],
        "url_exclude_globs": [
            "**/news/**",
            "**/calendar/**",
            "**/athletics/**",
            "**/sports/**",
            "**/lunch*menu*",
            "**/bus*schedule*",
            "**/testing*schedule*",
        ],
        "learned_positive": [],
        "learned_negative": [],
    }
    save_patterns(default_patterns)
    return {
        "success": True,
        "message": "Patterns reset to defaults",
    }
