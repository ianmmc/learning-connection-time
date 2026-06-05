#!/usr/bin/env python3
"""
run_benchmark.py - Main orchestrator for model extraction benchmark

PURPOSE:
    Runs a specified Ollama model against all districts with ground_truth.json,
    scores the results, and produces per-model reports. Uses the same extraction
    pipeline as production (ExtractionService) with only the model changed.

CONTEXT:
    Part of Phase 10: Model Benchmark. This is the main entry point.
    Requires ground truth files created by create_ground_truth.py.

USAGE:
    # Run benchmark for a specific model
    python infrastructure/scripts/benchmark/run_benchmark.py --model command-r:latest

    # Run with custom output directory
    python infrastructure/scripts/benchmark/run_benchmark.py --model qwen2:7b --output-dir data/benchmark_results/

    # Run only specific districts
    python infrastructure/scripts/benchmark/run_benchmark.py --model llama3.1:8b --districts 4659820,0804800

    # Dry run - show what would be tested
    python infrastructure/scripts/benchmark/run_benchmark.py --model llama3.1:8b --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.api.services.extraction_service import ExtractionService
from infrastructure.api.services.ollama_launcher import ensure_ollama_running
from infrastructure.scripts.benchmark.score_extraction import (
    score_district,
    format_district_score,
    DistrictScore,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PDF_BASE_DIR = PROJECT_ROOT / "data" / "raw" / "bell_schedule_pdfs"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "benchmark_results"


def find_ground_truth_districts() -> list[Path]:
    """Find all district directories that have ground_truth.json."""
    districts = []
    for state_dir in sorted(PDF_BASE_DIR.iterdir()):
        if not state_dir.is_dir():
            continue
        for district_dir in sorted(state_dir.iterdir()):
            if not district_dir.is_dir():
                continue
            if (district_dir / "ground_truth.json").exists():
                districts.append(district_dir)
    return districts


def read_district_text(district_dir: Path) -> tuple[str, list[str]]:
    """
    Read all txt files from a district's active directory.
    Matches the production pipeline's concatenation logic.

    Returns:
        (combined_text, list_of_source_filenames)
    """
    active_dir = district_dir / "active"
    if not active_dir.exists():
        return "", []

    # Collect txt files from active/ and active/converted/
    txt_files = list(active_dir.glob("*.txt")) + list(active_dir.glob("**/*.txt"))
    # Deduplicate preserving order
    seen = set()
    unique_files = []
    for f in txt_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    txt_files = sorted(unique_files)

    if not txt_files:
        return "", []

    combined_text = ""
    source_files = []
    for txt_file in txt_files:
        try:
            with open(txt_file, errors="replace") as f:
                combined_text += f"\n--- From {txt_file.name} ---\n"
                combined_text += f.read()
            source_files.append(txt_file.name)
        except Exception as e:
            logger.warning(f"Error reading {txt_file}: {e}")

    return combined_text, source_files


def sanitize_model_name(model: str) -> str:
    """Convert model name to filesystem-safe directory name."""
    return model.replace(":", "_").replace("/", "_")


def generate_report_md(model: str, district_scores: list[DistrictScore],
                       total_time: float) -> str:
    """Generate markdown report for a model's benchmark results."""
    lines = []
    lines.append(f"# Benchmark Report: {model}")
    lines.append(f"Run date: {datetime.utcnow().isoformat()[:19]}")
    lines.append(f"Districts tested: {len(district_scores)}")
    lines.append(f"Total extraction time: {total_time:.0f}s "
                 f"(avg {total_time / max(len(district_scores), 1):.1f}s/district)")

    # Summary metrics
    total_score = sum(ds.total_score for ds in district_scores)
    total_max = sum(ds.max_score for ds in district_scores)
    overall_pct = round(total_score / max(total_max, 1) * 100, 1)

    json_ok = sum(1 for ds in district_scores if not ds.json_parse_failed)
    json_pct = round(json_ok / max(len(district_scores), 1) * 100, 1)

    all_expected = 0
    all_found = 0
    for ds in district_scores:
        # Count expected grade levels (excluding missing_ok)
        all_expected += len(ds.missing_grade_levels) + ds.matched_count
        all_found += ds.matched_count
    grade_pct = round(all_found / max(all_expected, 1) * 100, 1)

    total_fp = sum(ds.false_positive_count for ds in district_scores)
    fp_rate = round(total_fp / max(len(district_scores), 1), 2)

    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Overall accuracy | {overall_pct}% |")
    lines.append(f"| JSON parse success | {json_pct}% |")
    lines.append(f"| Grade coverage rate | {grade_pct}% |")
    lines.append(f"| False positive rate | {fp_rate}/district |")
    lines.append(f"| Mean time/extraction | {total_time / max(len(district_scores), 1):.1f}s |")

    # Per-district table
    lines.append("")
    lines.append("## Per-District Scores")
    lines.append("")
    lines.append("| District | State | Score | Max | Pct | Penalties | Notes |")
    lines.append("|----------|-------|-------|-----|-----|-----------|-------|")

    for ds in sorted(district_scores, key=lambda d: d.pct, reverse=True):
        penalty_str = ", ".join(f"{p['type']}" for p in ds.penalties[:3])
        if len(ds.penalties) > 3:
            penalty_str += f" (+{len(ds.penalties) - 3} more)"
        notes = ""
        if ds.json_parse_failed:
            notes = "JSON failure"
        elif ds.output_truncated:
            notes = "Output truncated"

        lines.append(f"| {ds.district_name[:30]} | {ds.state} | "
                     f"{ds.total_score} | {ds.max_score} | {ds.pct}% | "
                     f"{penalty_str} | {notes} |")

    # Detailed scoring
    lines.append("")
    lines.append("## Detailed Scoring")
    for ds in district_scores:
        lines.append(format_district_score(ds))

    return "\n".join(lines)


def generate_report_json(model: str, district_scores: list[DistrictScore],
                         total_time: float, district_times: dict[str, float]) -> dict:
    """Generate JSON report for a model's benchmark results."""
    total_score = sum(ds.total_score for ds in district_scores)
    total_max = sum(ds.max_score for ds in district_scores)

    json_ok = sum(1 for ds in district_scores if not ds.json_parse_failed)
    total_fp = sum(ds.false_positive_count for ds in district_scores)

    return {
        "model": model,
        "run_date": datetime.utcnow().isoformat(),
        "config": {
            "temperature": 0.1,
            "num_predict": 1000,
            "max_text_len": 6000,
        },
        "summary": {
            "districts_tested": len(district_scores),
            "overall_accuracy_pct": round(total_score / max(total_max, 1) * 100, 1),
            "json_success_rate": round(json_ok / max(len(district_scores), 1) * 100, 1),
            "false_positive_rate": round(total_fp / max(len(district_scores), 1), 2),
            "total_time_seconds": round(total_time, 1),
            "mean_time_seconds": round(total_time / max(len(district_scores), 1), 1),
        },
        "districts": [
            {
                "district_id": ds.district_id,
                "district_name": ds.district_name,
                "state": ds.state,
                "score": ds.total_score,
                "max_score": ds.max_score,
                "pct": ds.pct,
                "extraction_time_seconds": round(district_times.get(ds.district_id, 0), 1),
                "json_parse_failed": ds.json_parse_failed,
                "false_positive_count": ds.false_positive_count,
                "missing_grade_levels": ds.missing_grade_levels,
                "penalties": ds.penalties,
                "entry_scores": [
                    {
                        "ground_truth": f"{es.ground_truth_grade} {es.ground_truth_start}-{es.ground_truth_end}",
                        "extracted": f"{es.extracted_grade} {es.extracted_start}-{es.extracted_end}" if es.matched else "MISSED",
                        "total": es.total,
                        "max": es.max_score,
                        "start_diff_min": es.start_time_diff_min,
                        "end_diff_min": es.end_time_diff_min,
                    }
                    for es in ds.entry_scores
                ],
            }
            for ds in district_scores
        ],
    }


async def run_single_extraction(service: ExtractionService, text: str,
                                metadata: dict) -> dict:
    """Run extraction and return result as dict."""
    result = await service.extract_times(
        pdf_text=text,
        district_id=metadata["district_id"],
        district_name=metadata["district_name"],
        state=metadata["state"],
    )
    return result.to_dict()


def main():
    parser = argparse.ArgumentParser(description="Run extraction benchmark for an Ollama model")
    parser.add_argument("--model", required=True, help="Ollama model name (e.g. command-r:latest)")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help="Output directory for results")
    parser.add_argument("--districts", type=str, default=None,
                        help="Comma-separated district IDs to test (default: all with ground_truth.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be tested without running")
    parser.add_argument("--delay", type=int, default=5,
                        help="Seconds to wait between districts (default: 5)")
    args = parser.parse_args()

    # Set lowest priority
    try:
        os.nice(20)
        logger.info("Running at nice +20 (lowest priority)")
    except (OSError, AttributeError):
        pass

    # Find districts
    gt_districts = find_ground_truth_districts()
    if not gt_districts:
        logger.error("No districts with ground_truth.json found.")
        sys.exit(1)

    # Filter by specific district IDs if provided
    if args.districts:
        target_ids = set(args.districts.split(","))
        gt_districts = [d for d in gt_districts if any(d.name.startswith(tid) for tid in target_ids)]

    logger.info(f"Found {len(gt_districts)} districts with ground truth")

    if args.dry_run:
        print(f"\nDry run - Model: {args.model}")
        print(f"Districts to test ({len(gt_districts)}):\n")
        for d in gt_districts:
            meta = json.loads((d / "metadata.json").read_text()) if (d / "metadata.json").exists() else {}
            gt = json.loads((d / "ground_truth.json").read_text())
            txt_count = len(list(d.rglob("active/**/*.txt")))
            print(f"  {meta.get('state', '??')}/{meta.get('district_id', '?')}: "
                  f"{meta.get('district_name', d.name)} "
                  f"({txt_count} txt, {len(gt.get('schedules', []))} GT entries)")
        return

    # Ensure Ollama is running
    logger.info("Checking Ollama...")
    if not ensure_ollama_running():
        logger.error("Could not start Ollama. Aborting.")
        sys.exit(1)

    # Create output directory
    model_safe = sanitize_model_name(args.model)
    output_dir = Path(args.output_dir) / model_safe
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize extraction service with target model
    service = ExtractionService(model=args.model)

    # Run benchmarks
    district_scores = []
    district_times = {}
    total_start = time.time()

    for i, district_dir in enumerate(gt_districts, 1):
        gt = json.loads((district_dir / "ground_truth.json").read_text())
        meta_path = district_dir / "metadata.json"
        metadata = json.loads(meta_path.read_text()) if meta_path.exists() else {}

        district_id = gt.get("district_id", metadata.get("district_id", ""))
        district_name = gt.get("district_name", metadata.get("district_name", ""))
        state = gt.get("state", metadata.get("state", ""))

        logger.info(f"[{i}/{len(gt_districts)}] {district_name} ({state}) - {district_id}")

        # Read text files
        text, source_files = read_district_text(district_dir)
        if not text:
            logger.warning(f"  No text files found for {district_name}")
            continue

        logger.info(f"  Text: {len(text)} chars from {len(source_files)} files")

        # Run extraction
        start_time = time.time()
        try:
            extraction_result = asyncio.run(
                run_single_extraction(service, text, {
                    "district_id": district_id,
                    "district_name": district_name,
                    "state": state,
                })
            )
        except Exception as e:
            logger.error(f"  Extraction failed: {e}")
            extraction_result = {
                "success": False,
                "error": str(e),
                "schedules": [],
            }

        elapsed = time.time() - start_time
        district_times[district_id] = elapsed
        logger.info(f"  Extraction took {elapsed:.1f}s")

        # Save raw extraction result
        district_output_dir = output_dir / district_id
        district_output_dir.mkdir(parents=True, exist_ok=True)
        with open(district_output_dir / "extraction_result.json", "w") as f:
            json.dump(extraction_result, f, indent=2)

        # Score
        ds = score_district(extraction_result, gt)
        district_scores.append(ds)
        logger.info(f"  Score: {ds.total_score}/{ds.max_score} ({ds.pct}%)")

        # Delay between districts
        if i < len(gt_districts):
            logger.info(f"  Waiting {args.delay}s before next district...")
            time.sleep(args.delay)

    total_time = time.time() - total_start

    # Generate reports
    logger.info(f"\nBenchmark complete. Total time: {total_time:.0f}s")

    report_md = generate_report_md(args.model, district_scores, total_time)
    report_json = generate_report_json(args.model, district_scores, total_time, district_times)

    with open(output_dir / "report.md", "w") as f:
        f.write(report_md)
    with open(output_dir / "report.json", "w") as f:
        json.dump(report_json, f, indent=2)

    logger.info(f"Reports saved to: {output_dir}/")
    logger.info(f"  report.md")
    logger.info(f"  report.json")

    # Print summary
    total_score = sum(ds.total_score for ds in district_scores)
    total_max = sum(ds.max_score for ds in district_scores)
    overall_pct = round(total_score / max(total_max, 1) * 100, 1)
    print(f"\n{'=' * 50}")
    print(f"MODEL: {args.model}")
    print(f"OVERALL ACCURACY: {overall_pct}% ({total_score}/{total_max})")
    print(f"DISTRICTS: {len(district_scores)}")
    print(f"TIME: {total_time:.0f}s ({total_time / max(len(district_scores), 1):.1f}s avg)")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
