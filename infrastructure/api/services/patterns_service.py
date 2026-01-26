"""
Patterns Service

Manages URL patterns for Crawlee filtering with learning loop support.
Uses semantic keyword extraction for cross-district generalization.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Patterns file location
PATTERNS_FILE = Path(__file__).parent.parent.parent.parent / "data" / "config" / "crawlee_patterns.json"

# Promotion thresholds
PROMOTION_MIN_DISTRICTS = 3  # Must be seen in 3+ districts
PROMOTION_MIN_SUCCESS_RATE = 0.7  # 70% success rate required

# Semantic keywords for bell schedule detection
# These are the ONLY words we extract from URLs for pattern learning
POSITIVE_KEYWORDS = {
    # Primary indicators
    'bell', 'schedule', 'schedules',
    # Time-related
    'hours', 'times', 'time', 'start', 'end', 'dismissal',
    # Schedule types
    'daily', 'regular', 'modified', 'early', 'late',
    # School day
    'period', 'periods', 'block', 'blocks',
}

NEGATIVE_KEYWORDS = {
    # Sports/activities
    'athletic', 'athletics', 'sports', 'game', 'games',
    # Food
    'lunch', 'breakfast', 'menu', 'cafeteria', 'nutrition',
    # Transportation
    'bus', 'buses', 'transportation', 'routes',
    # Testing
    'test', 'testing', 'exam', 'exams', 'assessment',
    # Calendar/events
    'calendar', 'event', 'events', 'news', 'announcement',
    # Other
    'job', 'jobs', 'career', 'employment', 'staff',
}


@dataclass
class EffectivePatterns:
    """Patterns ready for use by Crawlee."""
    include_globs: List[str]
    exclude_globs: List[str]
    learned_positive_count: int
    learned_negative_count: int


@dataclass
class PatternStats:
    """Statistics for a learned pattern."""
    pattern: str
    keywords: List[str]
    districts_seen: List[str]
    matches: int = 0      # URLs matched by this pattern
    confirmed: int = 0    # User confirmed as bell schedule
    rejected: int = 0     # User rejected as not bell schedule
    pending: int = 0      # Not yet reviewed
    success_rate: float = 0.0
    last_seen: str = ""
    status: str = "learning"  # learning, review, approved, rejected


def load_patterns() -> Dict[str, Any]:
    """Load patterns from file or return defaults."""
    default_patterns = {
        "version": "2.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
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

    if PATTERNS_FILE.exists():
        try:
            with open(PATTERNS_FILE) as f:
                data = json.load(f)
                # Migrate v1 to v2 if needed
                if data.get("version") == "1.0":
                    data["version"] = "2.0"
                return data
        except Exception as e:
            logger.error(f"Error loading patterns file: {e}")
            return default_patterns

    return default_patterns


def save_patterns(patterns: Dict[str, Any]):
    """Save patterns to file."""
    PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    patterns["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(PATTERNS_FILE, "w") as f:
        json.dump(patterns, f, indent=2)


def extract_keywords_from_url(url: str) -> Tuple[Set[str], Set[str]]:
    """
    Extract semantic keywords from a URL.

    Returns:
        Tuple of (positive_keywords_found, negative_keywords_found)
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    # Combine path and any query params
    text = parsed.path.lower()

    # Split on common delimiters
    segments = re.split(r'[-_/.]', text)

    positive_found = set()
    negative_found = set()

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # Check for positive keywords
        for kw in POSITIVE_KEYWORDS:
            if kw in segment or segment in kw:
                positive_found.add(kw)

        # Check for negative keywords
        for kw in NEGATIVE_KEYWORDS:
            if kw in segment or segment in kw:
                negative_found.add(kw)

    return positive_found, negative_found


def keywords_to_pattern(keywords: Set[str]) -> Optional[str]:
    """
    Convert a set of keywords to a glob pattern.

    Returns patterns like:
        {'bell', 'schedule'} -> '**/bell*schedule*' or '**/schedule*bell*'
    """
    if not keywords:
        return None

    # Sort for consistency
    sorted_kw = sorted(keywords)

    if len(sorted_kw) == 1:
        return f"**/*{sorted_kw[0]}*"

    # Create pattern with wildcards between keywords
    # Use first two keywords to avoid overly specific patterns
    kw1, kw2 = sorted_kw[0], sorted_kw[1]
    return f"**/*{kw1}*{kw2}*"


def get_effective_patterns() -> EffectivePatterns:
    """
    Get the effective patterns for Crawlee crawling.

    Merges base patterns with high-confidence learned patterns.
    Only includes learned patterns that have been seen in multiple districts
    and have a good success rate.
    """
    patterns = load_patterns()

    # Start with base patterns
    include_globs = list(patterns.get("url_include_globs", []))
    exclude_globs = list(patterns.get("url_exclude_globs", []))

    # Add approved learned positive patterns
    learned_positive = patterns.get("learned_positive", [])
    for lp in learned_positive:
        pattern = lp.get("pattern")
        status = lp.get("status", "learning")
        districts = lp.get("districts_seen", [])

        # Include if approved OR if seen in 2+ districts with decent stats
        if status == "approved":
            if pattern and pattern not in include_globs:
                include_globs.append(pattern)
        elif len(districts) >= 2:
            success_rate = lp.get("success_rate", 0)
            if success_rate >= 0.5 and pattern and pattern not in include_globs:
                include_globs.append(pattern)

    # Add approved learned negative patterns
    learned_negative = patterns.get("learned_negative", [])
    for ln in learned_negative:
        pattern = ln.get("pattern")
        status = ln.get("status", "learning")
        districts = ln.get("districts_seen", [])

        if status == "approved":
            if pattern and pattern not in exclude_globs:
                exclude_globs.append(pattern)
        elif len(districts) >= 2:
            success_rate = ln.get("success_rate", 0)
            if success_rate >= 0.5 and pattern and pattern not in exclude_globs:
                exclude_globs.append(pattern)

    return EffectivePatterns(
        include_globs=include_globs,
        exclude_globs=exclude_globs,
        learned_positive_count=len(learned_positive),
        learned_negative_count=len(learned_negative),
    )


def learn_from_url(url: str, is_bell_schedule: bool,
                   district_id: Optional[str] = None,
                   confidence: float = 0.9) -> Optional[str]:
    """
    Learn a pattern from a URL based on feedback.

    Uses semantic keyword extraction to create generalizable patterns
    that work across districts.

    Args:
        url: The URL to learn from
        is_bell_schedule: True if URL contains bell schedule
        district_id: District identifier for cross-district tracking
        confidence: Confidence score for this feedback

    Returns:
        The extracted pattern, or None if no keywords found
    """
    positive_kw, negative_kw = extract_keywords_from_url(url)

    # Determine which keywords to use based on classification
    if is_bell_schedule:
        keywords = positive_kw
        learned_key = "learned_positive"
    else:
        # For negative examples, prefer negative keywords if found
        keywords = negative_kw if negative_kw else positive_kw
        learned_key = "learned_negative"

    if not keywords:
        logger.debug(f"No semantic keywords found in URL: {url}")
        return None

    pattern = keywords_to_pattern(keywords)
    if not pattern:
        return None

    # Load and update patterns
    patterns = load_patterns()
    now = datetime.now(timezone.utc).isoformat()

    # Check if pattern already exists
    existing = None
    for p in patterns[learned_key]:
        if p.get("pattern") == pattern:
            existing = p
            break

    if existing:
        # Update existing pattern
        existing["matches"] = existing.get("matches", 0) + 1
        existing["last_seen"] = now

        # Track district
        if district_id:
            districts = existing.get("districts_seen", [])
            if district_id not in districts:
                districts.append(district_id)
                existing["districts_seen"] = districts

        # Update keywords (merge sets)
        existing_kw = set(existing.get("keywords", []))
        existing_kw.update(keywords)
        existing["keywords"] = sorted(existing_kw)

        # Recalculate success rate
        confirmed = existing.get("confirmed", 0)
        rejected = existing.get("rejected", 0)
        if confirmed + rejected > 0:
            existing["success_rate"] = confirmed / (confirmed + rejected)

        # Check if needs review
        if len(existing.get("districts_seen", [])) >= PROMOTION_MIN_DISTRICTS:
            if existing.get("status") == "learning":
                existing["status"] = "review"
                logger.info(f"Pattern ready for review: {pattern}")

    else:
        # Add new pattern
        new_entry = {
            "pattern": pattern,
            "keywords": sorted(keywords),
            "districts_seen": [district_id] if district_id else [],
            "matches": 1,
            "confirmed": 0,
            "rejected": 0,
            "pending": 1,
            "success_rate": 0.0,
            "first_seen": now,
            "last_seen": now,
            "status": "learning",
        }
        patterns[learned_key].append(new_entry)

    save_patterns(patterns)
    return pattern


def record_feedback(url: str, is_bell_schedule: bool,
                    district_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Record user feedback on a URL (confirmed or rejected as bell schedule).

    This updates the success tracking for matching patterns.

    Args:
        url: The URL being reviewed
        is_bell_schedule: User's determination
        district_id: Optional district ID

    Returns:
        Dict with updated pattern info
    """
    positive_kw, negative_kw = extract_keywords_from_url(url)
    keywords = positive_kw if positive_kw else negative_kw

    if not keywords:
        return {"success": False, "message": "No keywords in URL"}

    pattern = keywords_to_pattern(keywords)
    patterns = load_patterns()

    # Find the pattern in learned lists
    for learned_key in ["learned_positive", "learned_negative"]:
        for p in patterns[learned_key]:
            if p.get("pattern") == pattern:
                # Update counts
                p["pending"] = max(0, p.get("pending", 1) - 1)

                if is_bell_schedule:
                    p["confirmed"] = p.get("confirmed", 0) + 1
                else:
                    p["rejected"] = p.get("rejected", 0) + 1

                # Recalculate success rate
                confirmed = p.get("confirmed", 0)
                rejected = p.get("rejected", 0)
                if confirmed + rejected > 0:
                    p["success_rate"] = confirmed / (confirmed + rejected)

                # Track district
                if district_id:
                    districts = p.get("districts_seen", [])
                    if district_id not in districts:
                        districts.append(district_id)
                        p["districts_seen"] = districts

                # Auto-promote or flag for review
                if len(p.get("districts_seen", [])) >= PROMOTION_MIN_DISTRICTS:
                    if p["success_rate"] >= PROMOTION_MIN_SUCCESS_RATE:
                        if p.get("status") != "approved":
                            p["status"] = "review"  # Ready for human approval
                    elif p["success_rate"] < 0.3 and confirmed + rejected >= 5:
                        p["status"] = "flagged"  # Low success, may need removal

                save_patterns(patterns)
                return {
                    "success": True,
                    "pattern": pattern,
                    "success_rate": p["success_rate"],
                    "status": p["status"],
                    "districts_seen": len(p.get("districts_seen", [])),
                }

    # Pattern not found, learn it
    learn_from_url(url, is_bell_schedule, district_id)
    return {
        "success": True,
        "pattern": pattern,
        "message": "New pattern learned",
    }


def get_patterns_for_review() -> List[Dict[str, Any]]:
    """
    Get patterns that need human review.

    Returns patterns sorted by priority:
    1. Status = 'review' (ready for approval)
    2. Status = 'flagged' (low success rate, needs attention)
    3. Learning patterns with many matches but low success
    """
    patterns = load_patterns()
    review_list = []

    for learned_key in ["learned_positive", "learned_negative"]:
        pattern_type = "positive" if learned_key == "learned_positive" else "negative"

        for p in patterns[learned_key]:
            status = p.get("status", "learning")
            districts = len(p.get("districts_seen", []))
            confirmed = p.get("confirmed", 0)
            rejected = p.get("rejected", 0)
            total_reviewed = confirmed + rejected

            # Calculate priority score
            priority = 0
            if status == "review":
                priority = 100
            elif status == "flagged":
                priority = 90
            elif total_reviewed >= 3 and p.get("success_rate", 0) < 0.5:
                priority = 80
            elif districts >= 2:
                priority = 50

            if priority > 0 or status != "learning":
                review_list.append({
                    "pattern": p.get("pattern"),
                    "type": pattern_type,
                    "keywords": p.get("keywords", []),
                    "districts_seen": districts,
                    "matches": p.get("matches", 0),
                    "confirmed": confirmed,
                    "rejected": rejected,
                    "pending": p.get("pending", 0),
                    "success_rate": p.get("success_rate", 0),
                    "status": status,
                    "priority": priority,
                    "last_seen": p.get("last_seen"),
                })

    # Sort by priority descending
    review_list.sort(key=lambda x: x["priority"], reverse=True)
    return review_list


def approve_pattern(pattern: str) -> Dict[str, Any]:
    """Approve a learned pattern, moving it to permanent status."""
    patterns = load_patterns()

    for learned_key in ["learned_positive", "learned_negative"]:
        for p in patterns[learned_key]:
            if p.get("pattern") == pattern:
                p["status"] = "approved"
                p["approved_at"] = datetime.now(timezone.utc).isoformat()
                save_patterns(patterns)
                return {
                    "success": True,
                    "pattern": pattern,
                    "message": "Pattern approved",
                }

    return {"success": False, "message": "Pattern not found"}


def reject_pattern(pattern: str) -> Dict[str, Any]:
    """Reject and remove a learned pattern."""
    patterns = load_patterns()

    for learned_key in ["learned_positive", "learned_negative"]:
        original_len = len(patterns[learned_key])
        patterns[learned_key] = [
            p for p in patterns[learned_key]
            if p.get("pattern") != pattern
        ]
        if len(patterns[learned_key]) < original_len:
            save_patterns(patterns)
            return {
                "success": True,
                "pattern": pattern,
                "message": "Pattern removed",
            }

    return {"success": False, "message": "Pattern not found"}


def learn_from_ollama_scores(url_scores: List[Dict[str, Any]],
                             district_id: Optional[str] = None,
                             threshold_high: float = 0.8,
                             threshold_low: float = 0.2):
    """
    Learn patterns from Ollama URL ranking scores.

    Only learns from URLs with strong signals (very high or very low scores).
    Uses semantic keyword extraction for generalization.

    Args:
        url_scores: List of {url, score, reason} from Ollama
        district_id: District being processed
        threshold_high: Score above which to learn as positive
        threshold_low: Score below which to learn as negative
    """
    for score_data in url_scores:
        url = score_data.get("url", "")
        score = score_data.get("score", 0.5)

        if score >= threshold_high:
            learn_from_url(url, is_bell_schedule=True,
                          district_id=district_id, confidence=score)
        elif score <= threshold_low:
            learn_from_url(url, is_bell_schedule=False,
                          district_id=district_id, confidence=1.0 - score)


def get_patterns_summary() -> Dict[str, Any]:
    """Get a summary of current patterns state."""
    patterns = load_patterns()
    effective = get_effective_patterns()

    # Count by status
    positive_by_status = {}
    for p in patterns.get("learned_positive", []):
        status = p.get("status", "learning")
        positive_by_status[status] = positive_by_status.get(status, 0) + 1

    negative_by_status = {}
    for p in patterns.get("learned_negative", []):
        status = p.get("status", "learning")
        negative_by_status[status] = negative_by_status.get(status, 0) + 1

    # Count patterns needing review
    review_needed = len([
        p for p in get_patterns_for_review()
        if p["status"] in ("review", "flagged")
    ])

    return {
        "version": patterns.get("version"),
        "updated_at": patterns.get("updated_at"),
        "base_include_count": len(patterns.get("url_include_globs", [])),
        "base_exclude_count": len(patterns.get("url_exclude_globs", [])),
        "learned_positive_count": len(patterns.get("learned_positive", [])),
        "learned_negative_count": len(patterns.get("learned_negative", [])),
        "learned_positive_by_status": positive_by_status,
        "learned_negative_by_status": negative_by_status,
        "effective_include_count": len(effective.include_globs),
        "effective_exclude_count": len(effective.exclude_globs),
        "review_needed": review_needed,
        "promotion_threshold": {
            "min_districts": PROMOTION_MIN_DISTRICTS,
            "min_success_rate": PROMOTION_MIN_SUCCESS_RATE,
        },
        "keywords": {
            "positive": sorted(POSITIVE_KEYWORDS),
            "negative": sorted(NEGATIVE_KEYWORDS),
        },
    }
