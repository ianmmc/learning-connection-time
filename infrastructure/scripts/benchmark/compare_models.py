#!/usr/bin/env python3
"""
compare_models.py - Cross-model comparison report generator

PURPOSE:
    Reads all model benchmark reports from data/benchmark_results/ and
    produces a unified comparison matrix with rankings, per-district heatmap,
    and failure mode analysis.

CONTEXT:
    Part of Phase 10: Model Benchmark. Run after all models have been
    benchmarked with run_benchmark.py.

USAGE:
    # Generate comparison from all available reports
    python infrastructure/scripts/benchmark/compare_models.py

    # Custom results directory
    python infrastructure/scripts/benchmark/compare_models.py --results-dir data/benchmark_results/
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "data" / "benchmark_results"


def load_reports(results_dir: Path) -> list[dict]:
    """Load all report.json files from model subdirectories."""
    reports = []
    for model_dir in sorted(results_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        report_path = model_dir / "report.json"
        if report_path.exists():
            with open(report_path) as f:
                reports.append(json.load(f))
    return reports


def generate_comparison_md(reports: list[dict]) -> str:
    """Generate cross-model comparison markdown."""
    if not reports:
        return "# No benchmark reports found.\n"

    lines = []
    lines.append("# Model Comparison: Bell Schedule Extraction Benchmark")
    lines.append(f"Generated from {len(reports)} model reports")
    lines.append("")

    # Overall rankings
    ranked = sorted(reports, key=lambda r: r["summary"]["overall_accuracy_pct"], reverse=True)

    lines.append("## Overall Rankings")
    lines.append("")
    lines.append("| Rank | Model | Accuracy | JSON OK | FP Rate | Avg Time |")
    lines.append("|------|-------|----------|---------|---------|----------|")

    for i, r in enumerate(ranked, 1):
        s = r["summary"]
        lines.append(
            f"| {i} | {r['model']} | {s['overall_accuracy_pct']}% | "
            f"{s['json_success_rate']}% | {s['false_positive_rate']}/district | "
            f"{s['mean_time_seconds']}s |"
        )

    # Per-district heatmap
    # Collect all district IDs across all reports
    all_districts = {}
    for r in reports:
        for d in r.get("districts", []):
            did = d["district_id"]
            if did not in all_districts:
                all_districts[did] = {
                    "name": d.get("district_name", did)[:25],
                    "state": d.get("state", ""),
                }

    if all_districts:
        lines.append("")
        lines.append("## Per-District Heatmap")
        lines.append("")

        # Header
        model_names = [r["model"] for r in ranked]
        header = "| District | State | " + " | ".join(model_names) + " |"
        separator = "|----------|-------|" + "|".join(["--------"] * len(model_names)) + "|"
        lines.append(header)
        lines.append(separator)

        # Build lookup: model -> district_id -> pct
        model_district_pct = {}
        for r in ranked:
            model_district_pct[r["model"]] = {}
            for d in r.get("districts", []):
                model_district_pct[r["model"]][d["district_id"]] = d.get("pct", 0)

        for did, info in sorted(all_districts.items(), key=lambda x: x[1]["name"]):
            row = f"| {info['name']} | {info['state']} |"
            for model in model_names:
                pct = model_district_pct.get(model, {}).get(did)
                if pct is not None:
                    row += f" {pct}% |"
                else:
                    row += " - |"
            lines.append(row)

    # Failure mode analysis
    lines.append("")
    lines.append("## Failure Mode Analysis")
    lines.append("")

    failure_modes = ["json_parse_failed", "false_positive", "missing_grade_level",
                     "duplicate_extraction", "truncated_output"]
    mode_labels = {
        "json_parse_failed": "JSON parse failure",
        "false_positive": "Office hours extracted",
        "missing_grade_level": "Missing grade levels",
        "duplicate_extraction": "Duplicate entries",
        "truncated_output": "Output truncation",
    }

    header = "| Failure Mode | " + " | ".join(r["model"] for r in ranked) + " |"
    separator = "|-------------|" + "|".join(["-----"] * len(ranked)) + "|"
    lines.append(header)
    lines.append(separator)

    for mode in failure_modes:
        row = f"| {mode_labels.get(mode, mode)} |"
        for r in ranked:
            count = 0
            for d in r.get("districts", []):
                if mode == "json_parse_failed":
                    count += 1 if d.get("json_parse_failed") else 0
                else:
                    count += sum(1 for p in d.get("penalties", []) if p.get("type") == mode)
            row += f" {count} |"
        lines.append(row)

    # Recommendation
    if ranked:
        best = ranked[0]
        lines.append("")
        lines.append("## Recommendation")
        lines.append("")
        lines.append(f"**{best['model']}** achieved the highest overall accuracy "
                     f"({best['summary']['overall_accuracy_pct']}%) with "
                     f"{best['summary']['json_success_rate']}% JSON parse success rate.")

        if len(ranked) > 1:
            runner_up = ranked[1]
            diff = best["summary"]["overall_accuracy_pct"] - runner_up["summary"]["overall_accuracy_pct"]
            speed_ratio = best["summary"]["mean_time_seconds"] / max(runner_up["summary"]["mean_time_seconds"], 0.1)

            if diff < 5 and speed_ratio > 2:
                lines.append(f"\nHowever, **{runner_up['model']}** is within {diff:.1f}% accuracy "
                             f"and {speed_ratio:.1f}x faster. Consider the speed/accuracy tradeoff.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate cross-model comparison report")
    parser.add_argument("--results-dir", type=str, default=str(DEFAULT_RESULTS_DIR),
                        help="Directory containing model benchmark results")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}")
        sys.exit(1)

    reports = load_reports(results_dir)
    if not reports:
        print("No report.json files found in model subdirectories.")
        sys.exit(1)

    print(f"Found {len(reports)} model reports: {[r['model'] for r in reports]}")

    comparison_md = generate_comparison_md(reports)

    output_path = results_dir / "comparison.md"
    with open(output_path, "w") as f:
        f.write(comparison_md)

    print(f"Comparison report saved to: {output_path}")
    print()
    print(comparison_md)


if __name__ == "__main__":
    main()
