#!/usr/bin/env python3
"""
run_manifest_benchmark.py - Provider-agnostic benchmark over the DB-derived ground truth.

Pipeline per district: read (doc->text or doc->images via reading.py) -> extract
(provider-agnostic extractors.py: local Ollama OR cloud API) -> score (score_extraction.py)
against the grade-band ground-truth manifest.

USAGE:
    # local text model
    python infrastructure/scripts/benchmark/run_manifest_benchmark.py --model ollama:qwen2.5:7b --mode text
    # local vision model (reads images: PDF pages + image files)
    python infrastructure/scripts/benchmark/run_manifest_benchmark.py --model ollama:qwen2.5vl:7b --mode vision
    # cloud (needs API key + SDK)
    python infrastructure/scripts/benchmark/run_manifest_benchmark.py --model anthropic:claude-haiku-4-5 --mode text
    # smoke test on a few districts
    python infrastructure/scripts/benchmark/run_manifest_benchmark.py --model ollama:qwen2.5:7b --limit 3
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.scripts.benchmark.extractors import make_extractor
from infrastructure.scripts.benchmark.reading import read_text, read_images, read_tables
from infrastructure.scripts.benchmark.score_extraction import score_district
from infrastructure.scripts.benchmark.run_benchmark import (
    generate_report_md, generate_report_json, sanitize_model_name,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

MANIFEST = PROJECT_ROOT / "data" / "benchmark" / "ground_truth_manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "benchmark_results"


def main():
    ap = argparse.ArgumentParser(description="Provider-agnostic bell-schedule extraction benchmark")
    ap.add_argument("--model", required=True, help="provider:model (e.g. ollama:qwen2.5vl:7b, anthropic:claude-haiku-4-5)")
    ap.add_argument("--mode", choices=["text", "vision", "both", "tables"], default="text")
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--districts", default=None, help="comma-separated district IDs to test")
    ap.add_argument("--limit", type=int, default=None, help="test only the first N districts")
    ap.add_argument("--delay", type=int, default=2, help="seconds between districts")
    args = ap.parse_args()

    try:
        os.nice(20)
    except (OSError, AttributeError):
        pass

    manifest = json.loads(Path(args.manifest).read_text())
    districts = manifest["districts"]
    if args.districts:
        want = set(args.districts.split(","))
        districts = [d for d in districts if d["district_id"] in want]
    if args.limit:
        districts = districts[: args.limit]
    logger.info(f"Model={args.model} mode={args.mode} districts={len(districts)}")

    extractor = make_extractor(args.model)
    out_dir = Path(args.output_dir) / f"{sanitize_model_name(args.model)}__{args.mode}"
    out_dir.mkdir(parents=True, exist_ok=True)

    district_scores, district_times = [], {}
    t0 = time.time()
    for i, d in enumerate(districts, 1):
        did, name, state = d["district_id"], d["district_name"], d["state"]
        src = PROJECT_ROOT / d["source_dir"]
        logger.info(f"[{i}/{len(districts)}] {name} ({state}) {did}  modality={d.get('modality')}")

        text, images = "", None
        if args.mode in ("text", "both"):
            text, tsrc = read_text(src)
        if args.mode == "tables":
            text, tsrc = read_tables(src)
        if args.mode in ("vision", "both"):
            images, isrc = read_images(src)
        if not text and not images:
            logger.warning("  no readable input; skipping")
            continue
        logger.info(f"  input: {len(text)} text chars, {len(images or [])} images")

        ts = time.time()
        try:
            result = extractor.extract(text, did, name, state, images=images)
        except Exception as e:  # noqa: BLE001
            logger.error(f"  extract error: {e}")
            result = {"success": False, "error": str(e), "schedules": []}
        dt = time.time() - ts
        district_times[did] = dt

        dd = out_dir / did
        dd.mkdir(exist_ok=True)
        (dd / "extraction_result.json").write_text(json.dumps(result, indent=2))

        ds = score_district(result, d)
        district_scores.append(ds)
        logger.info(f"  {dt:.1f}s  score={ds.total_score}/{ds.max_score} ({ds.pct}%)  "
                    f"extracted={ds.extracted_count} matched={ds.matched_count}")
        if i < len(districts):
            time.sleep(args.delay)

    total = time.time() - t0
    (out_dir / "report.md").write_text(generate_report_md(args.model, district_scores, total))
    (out_dir / "report.json").write_text(json.dumps(
        generate_report_json(args.model, district_scores, total, district_times), indent=2))

    tscore = sum(ds.total_score for ds in district_scores)
    tmax = sum(ds.max_score for ds in district_scores)
    pct = round(tscore / max(tmax, 1) * 100, 1)
    print(f"\n{'='*52}\nMODEL: {args.model}  MODE: {args.mode}")
    print(f"OVERALL: {pct}% ({tscore}/{tmax}) over {len(district_scores)} districts")
    print(f"TIME: {total:.0f}s ({total/max(len(district_scores),1):.1f}s avg)")
    print(f"Report: {out_dir}/report.md\n{'='*52}")


if __name__ == "__main__":
    main()
