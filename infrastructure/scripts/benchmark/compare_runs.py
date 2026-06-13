#!/usr/bin/env python3
"""
compare_runs.py - Aggregate all benchmark report.json files into one leaderboard.

Scans data/benchmark_results/<model>__<mode>/report.json and emits a sorted leaderboard
(overall accuracy, JSON-parse success, false-positive rate, mean time). Writes
data/benchmark_results/leaderboard.md and prints it.

Usage: python infrastructure/scripts/benchmark/compare_runs.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "data" / "benchmark_results"


def main():
    rows = []
    for rep in sorted(RESULTS.glob("*/report.json")):
        try:
            d = json.loads(rep.read_text())
        except Exception:
            continue
        s = d.get("summary", {})
        dirname = rep.parent.name
        mode = dirname.rsplit("__", 1)[1] if "__" in dirname else "?"
        rows.append({
            "model": d.get("model", dirname),
            "mode": mode,
            "districts": s.get("districts_tested", 0),
            "overall": s.get("overall_accuracy_pct", 0.0),
            "json_ok": s.get("json_success_rate", 0.0),
            "fp": s.get("false_positive_rate", 0.0),
            "mean_s": s.get("mean_time_seconds", 0.0),
        })
    rows.sort(key=lambda r: r["overall"], reverse=True)

    lines = ["# Benchmark Leaderboard", ""]
    lines.append("| Rank | Model | Mode | Districts | Overall % | JSON % | FP/dist | Mean s |")
    lines.append("|-----:|-------|------|----------:|----------:|-------:|--------:|-------:|")
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['model']} | {r['mode']} | {r['districts']} | "
                     f"{r['overall']} | {r['json_ok']} | {r['fp']} | {r['mean_s']} |")
    if not rows:
        lines.append("| - | (no report.json found yet) | | | | | | |")
    out = "\n".join(lines)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "leaderboard.md").write_text(out + "\n")
    print(out)
    print(f"\nWrote {RESULTS / 'leaderboard.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
