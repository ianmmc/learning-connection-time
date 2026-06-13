#!/usr/bin/env python3
"""
score_minutes.py - Re-score saved benchmark extractions on the LCT-relevant metric:
grade-band MODAL instructional minutes (robust to which schools a model happened to pick).

For each model run dir, for each district:
  - model: per extracted schedule, minutes = end - start; group by grade band; take the MODE
  - ground truth: the manifest's grade-band minutes (end - start)
  - a band is "matched" if |model_mode - gt_minutes| <= TOL
Aggregates per model: band match rate, median |error| minutes, districts with any match.

Reads the saved extraction_result.json files (no model re-running). Prints a leaderboard.
Usage: python infrastructure/scripts/benchmark/score_minutes.py [--tol 15]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from infrastructure.database.schedule_aggregation import compute_instructional_minutes

RESULTS = ROOT / "data" / "benchmark_results"
MANIFEST = ROOT / "data" / "benchmark" / "ground_truth_manifest.json"


def gt_minutes_by_band(district: dict) -> dict[str, int]:
    out = {}
    for s in district["schedules"]:
        m = compute_instructional_minutes(s["start_time"], s["end_time"])
        if m is not None:
            out[s["grade_level"]] = m  # one grade-band value per band in GT
    return out


def model_band_values(schedules: list[dict], agg: str = "mode") -> dict[str, int]:
    by_band: dict[str, list[int]] = {}
    for s in schedules:
        m = compute_instructional_minutes(s.get("start_time", ""), s.get("end_time", ""))
        if m is not None and 120 <= m <= 600:  # plausibility guard
            by_band.setdefault(s.get("grade_level", "unknown"), []).append(m)
    out = {}
    for b, v in by_band.items():
        if not v:
            continue
        if agg == "max":        # "pick the longest day" = normal day (avoids early-release shorts)
            out[b] = max(v)
        elif agg == "median":
            out[b] = int(statistics.median(v))
        else:                    # mode (most common); tie -> smallest
            out[b] = min(statistics.multimode(v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=int, default=15, help="minutes tolerance for a band match")
    ap.add_argument("--agg", choices=["mode", "max", "median"], default="mode",
                    help="how to aggregate a model's per-band minutes (max = 'pick longest day')")
    ap.add_argument("--districts", default=None, help="comma-separated district IDs to restrict to")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    gt = {d["district_id"]: d for d in manifest["districts"]}
    only = set(args.districts.split(",")) if args.districts else None

    rows = []
    dirs = sorted(set(RESULTS.glob("*__text")) | set(RESULTS.glob("*__vision")) | set(RESULTS.glob("*__tables")))
    for mdir in dirs:
        bands_total = bands_matched = 0
        errs = []
        districts_scored = districts_hit = 0
        for sub in mdir.iterdir():
            res = sub / "extraction_result.json"
            if not sub.is_dir() or not res.exists() or sub.name not in gt:
                continue
            if only is not None and sub.name not in only:
                continue
            try:
                ex = json.loads(res.read_text())
            except Exception:
                continue
            gtb = gt_minutes_by_band(gt[sub.name])
            if not gtb:
                continue
            districts_scored += 1
            mb = model_band_values(ex.get("schedules", []), args.agg)
            hit = False
            for band, gtm in gtb.items():
                bands_total += 1
                if band in mb:
                    e = abs(mb[band] - gtm)
                    errs.append(e)
                    if e <= args.tol:
                        bands_matched += 1
                        hit = True
            districts_hit += 1 if hit else 0
        rows.append({
            "model": mdir.name.replace("ollama_", ""),
            "districts": districts_scored,
            "band_match_rate": round(100 * bands_matched / bands_total, 1) if bands_total else 0.0,
            "bands": f"{bands_matched}/{bands_total}",
            "median_err": round(statistics.median(errs), 1) if errs else None,
            "districts_hit_pct": round(100 * districts_hit / districts_scored, 1) if districts_scored else 0.0,
        })

    rows.sort(key=lambda r: r["band_match_rate"], reverse=True)
    print(f"\n=== Modal-minutes leaderboard (tol +/-{args.tol} min) ===")
    print(f"{'model':<22}{'districts':>10}{'band match%':>13}{'bands':>10}{'med|err|':>10}{'dist hit%':>11}")
    print("-" * 76)
    for r in rows:
        print(f"{r['model']:<22}{r['districts']:>10}{r['band_match_rate']:>13}{r['bands']:>10}"
              f"{str(r['median_err']):>10}{r['districts_hit_pct']:>11}")
    (RESULTS / "leaderboard_minutes.md").write_text(
        "# Modal-minutes leaderboard\n\n" +
        "| model | districts | band match % | bands | median |err| | district hit % |\n"
        "|---|---:|---:|---:|---:|---:|\n" +
        "".join(f"| {r['model']} | {r['districts']} | {r['band_match_rate']} | {r['bands']} | "
                f"{r['median_err']} | {r['districts_hit_pct']} |\n" for r in rows))
    print(f"\nWrote {RESULTS/'leaderboard_minutes.md'}")


if __name__ == "__main__":
    main()
