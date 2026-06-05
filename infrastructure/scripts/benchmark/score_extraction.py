#!/usr/bin/env python3
"""
score_extraction.py - Scoring logic for bell schedule extraction benchmark

PURPOSE:
    Compares model extraction results against human-transcribed ground truth.
    Produces per-entry scores, per-district scores with penalties, and
    aggregate model-level metrics.

CONTEXT:
    Part of Phase 10: Model Benchmark. Called by run_benchmark.py after each
    extraction. Can also be used standalone for scoring.

SCORING RUBRIC:
    Per-entry (max 10 points):
      - Start time exact match: 3 pts (within 5 min: 1 pt)
      - End time exact match: 3 pts (within 5 min: 1 pt)
      - Grade level correct: 2 pts
      - School name present & correct: 1 pt
      - Confidence calibrated: 1 pt (bonus)

    Penalties (per district):
      - False positive schedule: -3
      - Duplicate extraction: -2
      - Missing expected grade level: -2
      - JSON parse failure: -5
      - Truncated output: -3

USAGE:
    from infrastructure.scripts.benchmark.score_extraction import score_district

    result = score_district(extracted_result, ground_truth)
    print(result["district_pct"])
"""

import json
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


@dataclass
class EntryScore:
    """Score for a single matched extraction entry."""
    ground_truth_grade: str
    ground_truth_start: str
    ground_truth_end: str
    ground_truth_school: Optional[str]
    extracted_grade: Optional[str] = None
    extracted_start: Optional[str] = None
    extracted_end: Optional[str] = None
    extracted_school: Optional[str] = None
    start_time_points: int = 0
    end_time_points: int = 0
    grade_level_points: int = 0
    school_name_points: int = 0
    confidence_points: int = 0
    start_time_diff_min: Optional[int] = None
    end_time_diff_min: Optional[int] = None
    matched: bool = False

    @property
    def total(self) -> int:
        return (self.start_time_points + self.end_time_points +
                self.grade_level_points + self.school_name_points +
                self.confidence_points)

    @property
    def max_score(self) -> int:
        return 10


@dataclass
class DistrictScore:
    """Score for a full district extraction."""
    district_id: str
    district_name: str
    state: str
    entry_scores: list[EntryScore] = field(default_factory=list)
    penalties: list[dict] = field(default_factory=list)
    ground_truth_count: int = 0
    extracted_count: int = 0
    matched_count: int = 0
    false_positive_count: int = 0
    missing_grade_levels: list[str] = field(default_factory=list)
    json_parse_failed: bool = False
    output_truncated: bool = False

    @property
    def entry_total(self) -> int:
        return sum(e.total for e in self.entry_scores)

    @property
    def penalty_total(self) -> int:
        return sum(p["points"] for p in self.penalties)

    @property
    def total_score(self) -> int:
        return max(0, self.entry_total + self.penalty_total)

    @property
    def max_score(self) -> int:
        return self.ground_truth_count * 10

    @property
    def pct(self) -> float:
        if self.max_score == 0:
            return 0.0
        return round(self.total_score / self.max_score * 100, 1)


def time_to_minutes(time_str: str) -> int | None:
    """Convert HH:MM to total minutes since midnight."""
    if not time_str or ":" not in time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except (ValueError, IndexError):
        pass
    return None


def time_distance_minutes(t1: str, t2: str) -> int | None:
    """Calculate absolute difference in minutes between two HH:MM times."""
    m1 = time_to_minutes(t1)
    m2 = time_to_minutes(t2)
    if m1 is None or m2 is None:
        return None
    return abs(m1 - m2)


def school_name_similarity(name1: str | None, name2: str | None) -> float:
    """Fuzzy match score between two school names (0.0-1.0)."""
    if not name1 or not name2:
        return 0.0
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()


def match_entry(gt_entry: dict, extracted: dict) -> float:
    """Score how well an extracted entry matches a ground truth entry (0.0-1.0)."""
    score = 0.0

    # Grade level match is most important
    if gt_entry.get("grade_level") == extracted.get("grade_level"):
        score += 0.5

    # School name similarity
    name_sim = school_name_similarity(
        gt_entry.get("school_name"),
        extracted.get("school_name")
    )
    score += name_sim * 0.3

    # Time proximity
    start_diff = time_distance_minutes(
        gt_entry.get("start_time", ""),
        extracted.get("start_time", "")
    )
    end_diff = time_distance_minutes(
        gt_entry.get("end_time", ""),
        extracted.get("end_time", "")
    )

    if start_diff is not None and start_diff <= 30:
        score += 0.1 * (1 - start_diff / 30)
    if end_diff is not None and end_diff <= 30:
        score += 0.1 * (1 - end_diff / 30)

    return score


def score_entry(gt_entry: dict, extracted_entry: dict) -> EntryScore:
    """Score a single matched pair of ground truth and extracted entries."""
    es = EntryScore(
        ground_truth_grade=gt_entry.get("grade_level", ""),
        ground_truth_start=gt_entry.get("start_time", ""),
        ground_truth_end=gt_entry.get("end_time", ""),
        ground_truth_school=gt_entry.get("school_name"),
        extracted_grade=extracted_entry.get("grade_level"),
        extracted_start=extracted_entry.get("start_time"),
        extracted_end=extracted_entry.get("end_time"),
        extracted_school=extracted_entry.get("school_name"),
        matched=True,
    )

    # Start time scoring
    start_diff = time_distance_minutes(es.ground_truth_start, es.extracted_start or "")
    es.start_time_diff_min = start_diff
    if start_diff is not None:
        if start_diff == 0:
            es.start_time_points = 3
        elif start_diff <= 5:
            es.start_time_points = 1

    # End time scoring
    end_diff = time_distance_minutes(es.ground_truth_end, es.extracted_end or "")
    es.end_time_diff_min = end_diff
    if end_diff is not None:
        if end_diff == 0:
            es.end_time_points = 3
        elif end_diff <= 5:
            es.end_time_points = 1

    # Grade level scoring
    if es.ground_truth_grade == es.extracted_grade:
        es.grade_level_points = 2

    # School name scoring
    if es.extracted_school:
        sim = school_name_similarity(es.ground_truth_school, es.extracted_school)
        if sim >= 0.6:
            es.school_name_points = 1

    # Confidence calibration bonus
    confidence = extracted_entry.get("confidence", "")
    if start_diff is not None and end_diff is not None:
        is_accurate = start_diff <= 5 and end_diff <= 5
        if is_accurate and confidence == "high":
            es.confidence_points = 1
        elif not is_accurate and confidence == "low":
            es.confidence_points = 1

    return es


def match_schedules(extracted_list: list[dict], gt_list: list[dict]) -> tuple[list[tuple], list[dict], list[dict]]:
    """
    Match extracted entries to ground truth using greedy best-match.

    Returns:
        (matches, unmatched_extracted, unmatched_gt)
        where matches is list of (gt_entry, extracted_entry) tuples
    """
    if not extracted_list or not gt_list:
        return [], list(extracted_list), list(gt_list)

    # Build match score matrix
    scores = []
    for gi, gt in enumerate(gt_list):
        for ei, ex in enumerate(extracted_list):
            s = match_entry(gt, ex)
            scores.append((s, gi, ei))

    # Greedy best-match
    scores.sort(reverse=True, key=lambda x: x[0])
    matched_gt = set()
    matched_ex = set()
    matches = []

    for s, gi, ei in scores:
        if gi in matched_gt or ei in matched_ex:
            continue
        if s < 0.2:  # Minimum match threshold
            continue
        matches.append((gt_list[gi], extracted_list[ei]))
        matched_gt.add(gi)
        matched_ex.add(ei)

    unmatched_extracted = [extracted_list[i] for i in range(len(extracted_list)) if i not in matched_ex]
    unmatched_gt = [gt_list[i] for i in range(len(gt_list)) if i not in matched_gt]

    return matches, unmatched_extracted, unmatched_gt


def score_district(extraction_result: dict, ground_truth: dict) -> DistrictScore:
    """
    Score a full district extraction against ground truth.

    Args:
        extraction_result: The model's extraction output (extraction_result.json format)
        ground_truth: The human ground truth (ground_truth.json format)

    Returns:
        DistrictScore with full breakdown
    """
    ds = DistrictScore(
        district_id=ground_truth.get("district_id", ""),
        district_name=ground_truth.get("district_name", ""),
        state=ground_truth.get("state", ""),
    )

    gt_schedules = ground_truth.get("schedules", [])
    ds.ground_truth_count = len(gt_schedules)

    # Handle extraction failures
    if not extraction_result.get("success", True):
        error = extraction_result.get("error", "")
        if "json" in error.lower() or "parse" in error.lower():
            ds.json_parse_failed = True
            ds.penalties.append({"type": "json_parse_failure", "points": -5, "detail": error})
        elif "truncat" in error.lower():
            ds.output_truncated = True
            ds.penalties.append({"type": "truncated_output", "points": -3, "detail": error})
        else:
            ds.penalties.append({"type": "extraction_error", "points": -5, "detail": error})
        return ds

    extracted_schedules = extraction_result.get("schedules", [])
    ds.extracted_count = len(extracted_schedules)

    # Match entries
    matches, unmatched_extracted, unmatched_gt = match_schedules(extracted_schedules, gt_schedules)
    ds.matched_count = len(matches)

    # Score matched entries
    for gt_entry, ex_entry in matches:
        entry_score = score_entry(gt_entry, ex_entry)
        ds.entry_scores.append(entry_score)

    # Score unmatched ground truth (missed)
    for gt_entry in unmatched_gt:
        ds.entry_scores.append(EntryScore(
            ground_truth_grade=gt_entry.get("grade_level", ""),
            ground_truth_start=gt_entry.get("start_time", ""),
            ground_truth_end=gt_entry.get("end_time", ""),
            ground_truth_school=gt_entry.get("school_name"),
            matched=False,
        ))

    # Penalize false positives (unmatched extracted entries)
    ds.false_positive_count = len(unmatched_extracted)
    for fp in unmatched_extracted:
        ds.penalties.append({
            "type": "false_positive",
            "points": -3,
            "detail": f"{fp.get('grade_level', '?')} {fp.get('start_time', '?')}-{fp.get('end_time', '?')} ({fp.get('school_name', 'unnamed')})"
        })

    # Check for duplicate extractions (same grade + similar times)
    seen = set()
    for ex in extracted_schedules:
        key = (ex.get("grade_level"), ex.get("start_time"), ex.get("end_time"))
        if key in seen:
            ds.penalties.append({
                "type": "duplicate_extraction",
                "points": -2,
                "detail": f"Duplicate: {key}"
            })
        seen.add(key)

    # Check for missing grade levels
    expected_levels = set(ground_truth.get("expected_grade_levels", []))
    missing_ok = set(ground_truth.get("missing_grade_levels_ok", []))
    extracted_levels = {ex.get("grade_level") for ex in extracted_schedules}
    missing = expected_levels - extracted_levels - missing_ok

    ds.missing_grade_levels = list(missing)
    for level in missing:
        ds.penalties.append({
            "type": "missing_grade_level",
            "points": -2,
            "detail": f"Missing: {level}"
        })

    return ds


def format_entry_score(es: EntryScore) -> str:
    """Format an entry score as a readable line."""
    if not es.matched:
        return (f"  MISSED: {es.ground_truth_grade} "
                f"{es.ground_truth_start}-{es.ground_truth_end} "
                f"({es.ground_truth_school or 'unnamed'}) → 0/{es.max_score}")

    parts = []
    parts.append(f"start={es.start_time_points}/3")
    if es.start_time_diff_min is not None:
        parts.append(f"(Δ{es.start_time_diff_min}m)")
    parts.append(f"end={es.end_time_points}/3")
    if es.end_time_diff_min is not None:
        parts.append(f"(Δ{es.end_time_diff_min}m)")
    parts.append(f"grade={es.grade_level_points}/2")
    parts.append(f"name={es.school_name_points}/1")
    parts.append(f"conf={es.confidence_points}/1")

    return (f"  {es.ground_truth_grade} {es.ground_truth_start}-{es.ground_truth_end} → "
            f"{es.extracted_grade} {es.extracted_start}-{es.extracted_end} | "
            f"{' '.join(parts)} = {es.total}/{es.max_score}")


def format_district_score(ds: DistrictScore) -> str:
    """Format a district score as a readable block."""
    lines = []
    lines.append(f"\n{'=' * 70}")
    lines.append(f"{ds.district_name} ({ds.state}) - {ds.district_id}")
    lines.append(f"{'=' * 70}")
    lines.append(f"Ground truth: {ds.ground_truth_count} entries | "
                 f"Extracted: {ds.extracted_count} | "
                 f"Matched: {ds.matched_count}")

    if ds.json_parse_failed:
        lines.append("⚠ JSON PARSE FAILURE")
    if ds.output_truncated:
        lines.append("⚠ OUTPUT TRUNCATED")

    lines.append("\nEntry Scores:")
    for es in ds.entry_scores:
        lines.append(format_entry_score(es))

    if ds.penalties:
        lines.append("\nPenalties:")
        for p in ds.penalties:
            lines.append(f"  {p['type']}: {p['points']} ({p['detail']})")

    lines.append(f"\nTotal: {ds.entry_total} (entries) + {ds.penalty_total} (penalties) = "
                 f"{ds.total_score}/{ds.max_score} ({ds.pct}%)")

    return "\n".join(lines)
