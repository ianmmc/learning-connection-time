"""Per-model + per-judge effectiveness analysis over a completed run's receipts.

Answers the question Ian asked for: which finder families actually pull their weight, and how do the
judges behave — the input for tuning the roster on a later sweep. Reads a run's receipts
(`raw_findings.json`, `candidates.json`, `adjudications.json`) — no network, no re-derivation.

    python -m tools.crossfam_review.analyze 2026-07-13

Metrics per finder model:
  raw          — total findings it emitted
  candidates   — distinct deduped candidates it contributed to
  confirmed    — of those, how many the council confirmed
  precision    — confirmed / candidates it touched (its signal-to-noise)
  solo_conf    — confirmed candidates ONLY it found (unique value — bugs no other family caught)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from tools.crossfam_review.shards import REPO_ROOT


def _family(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else model_id


def _key(file: str, line, category: str) -> tuple:
    try:
        lb = int(line) // 10
    except (TypeError, ValueError):
        lb = 0
    return (file, lb, (category or "").strip().lower())


def analyze(stamp: str) -> dict:
    d = REPO_ROOT / "data" / "review" / f"crossfam-{stamp}"
    raw = json.loads((d / "raw_findings.json").read_text())
    adjs = json.loads((d / "adjudications.json").read_text())

    # Confirmed candidate keys (adjudications carry no category; match on file+line bucket, the same
    # coarse identity dedup uses, tolerating the missing category by keying on (file, line-bucket)).
    conf_keys = {(a["file"], a["line"] // 10) for a in adjs if a["confirmed"]}

    # Map each deduped candidate (file, line-bucket) → set of contributing models, from raw findings.
    cand_models: dict[tuple, set] = defaultdict(set)
    for f in raw:
        cand_models[(f["file"], f["line"] // 10)].add(f["model"])

    per_model: dict[str, dict] = defaultdict(lambda: {"raw": 0, "cands": set(), "conf": set(), "solo": 0})
    for f in raw:
        m = f["model"]
        per_model[m]["raw"] += 1
        per_model[m]["cands"].add((f["file"], f["line"] // 10))
    for (file, lb), models in cand_models.items():
        if (file, lb) in conf_keys:
            for m in models:
                per_model[m]["conf"].add((file, lb))
            if len(models) == 1:
                only = next(iter(models))
                per_model[only]["solo"] += 1

    report = {"stamp": stamp, "models": {}, "judges": {}}
    for m, s in sorted(per_model.items()):
        nc = len(s["cands"])
        report["models"][m] = {
            "family": _family(m), "raw": s["raw"], "candidates": nc,
            "confirmed": len(s["conf"]),
            "precision": round(len(s["conf"]) / nc, 3) if nc else 0.0,
            "solo_confirmed": s["solo"],
        }

    # Judge behavior: confirm/refute/error tallies per judge across all adjudications.
    jt: dict[str, dict] = defaultdict(lambda: {"confirmed": 0, "refuted": 0, "error": 0})
    for a in adjs:
        for v in a.get("verdicts", []):
            jt[v["judge"]][v["verdict"]] = jt[v["judge"]].get(v["verdict"], 0) + 1
    report["judges"] = {j: dict(t) for j, t in sorted(jt.items())}
    report["totals"] = {
        "raw_findings": len(raw), "adjudicated": len(adjs),
        "confirmed": sum(1 for a in adjs if a["confirmed"]),
    }
    return report


def _print(r: dict) -> None:
    print(f"\n── cross-family review effectiveness · {r['stamp']} ──")
    t = r["totals"]
    print(f"raw {t['raw_findings']} · adjudicated {t['adjudicated']} · confirmed {t['confirmed']}\n")
    print(f"{'finder model':34}{'raw':>5}{'cand':>6}{'conf':>6}{'prec':>7}{'solo':>6}")
    for m, s in sorted(r["models"].items(), key=lambda kv: -kv[1]["confirmed"]):
        print(f"{m:34}{s['raw']:>5}{s['candidates']:>6}{s['confirmed']:>6}"
              f"{s['precision']:>7.2f}{s['solo_confirmed']:>6}")
    print(f"\n{'judge':30}{'conf':>6}{'refu':>6}{'err':>5}")
    for j, s in r["judges"].items():
        print(f"{j:30}{s.get('confirmed', 0):>6}{s.get('refuted', 0):>6}{s.get('error', 0):>5}")


if __name__ == "__main__":
    stamp = sys.argv[1] if len(sys.argv) > 1 else "2026-07-13"
    _print(analyze(stamp))
