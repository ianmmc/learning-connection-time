#!/usr/bin/env python3
"""Stage 2 headless CLI EVALUATION — reliability + RECALL + precision spot-check (REQ-104).

Run in a PLAIN terminal (nested `claude` is blocked inside a Claude Code session).

Discovery quality compounds downstream, so we measure more than the structured-output flake. Against
a KNOWN-POSITIVE corpus (default batch_00001: 53 schools, all with domains, all `found` in the
validated subagent run — i.e. a findable page provably exists for each), this runs the real headless
Wave-1 `claude -p` call per (effort × schema) cell, RETRIES OFF, and per cell reports:

  - reliability:  OK% (raw single-shot), projected retried% (1-(1-p)^2), flake count, errors
  - RECALL:       wave1_found / n  AFTER gating (D2.gate_urls) — of schools where a page exists,
                  how many this config's Wave-1 actually recovers. The reference line is the SAME
                  schools' subagent Wave-1 found-rate (from the on-disk discovery.json baseline).
  - did-it-search: WebSearch-actually-fired count (silent-no-search guard, separate from the flake)
  - cost / latency / turns
  - precision spot-check: the actual GATED URLs per call are written to the report appendix so a
    human can eyeball whether they're the right pages (precision can't be auto-scored without
    per-URL verification — this is the manual check).

Writes an incremental report (rewritten after EVERY cell, so Ctrl-C keeps completed cells):
    data/acquisition/diagnostics/stage2_eval_<UTC>.md   (+ .json sidecar)

Usage (from repo root):
    python3 scripts/stage2_cli_reliability.py                         # all 53 batch_00001 schools × {low,med,high} × {strict,loose}
    python3 scripts/stage2_cli_reliability.py --efforts low,medium    # trim cells
    python3 scripts/stage2_cli_reliability.py --n 20                  # cap the sample
    python3 scripts/stage2_cli_reliability.py --reps 2               # repeat each school (flake variance)

Writes NOTHING to data/raw or the registry — pure measurement. Cost is subscription quota.
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.stage2_discover import headless as H
from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
from infrastructure.acquisition.common import paths

# Loosened WAVE1_SCHEMA: same required fields (validate_wave1_result re-checks the real contract) but
# WITHOUT additionalProperties:false / strict item closure — the strictness most likely to trip
# structured-output emission.
LOOSE_SCHEMA = {
    "type": "object",
    "required": ["district_id", "domain", "schools"],
    "properties": {
        "district_id": {"type": "string"}, "domain": {"type": "string"},
        "schools": {"type": "array", "items": {
            "type": "object", "required": ["school_id", "urls"],
            "properties": {"school_id": {"type": "string"},
                           "urls": {"type": "array", "items": {"type": "string"}}}}},
    },
}
# `none` = NO --json-schema at all: the SKILL.md / batch_00001 approach — the model returns the JSON as
# fenced response text and we parse it ourselves (validate_wave1_result re-checks the real contract).
# This sidesteps the CLI structured-output retry mechanism that produces error_max_structured_output_retries.
SCHEMAS = {"strict": H.WAVE1_SCHEMA, "loose": LOOSE_SCHEMA, "none": None}
OUT_DIR = paths.ACQUISITION / "diagnostics"


def parse_freetext_json(result_text: str):
    """Pull the Wave-1 JSON object out of the agent's free-text response (the no-schema arm). Prefer a
    ```json fenced block, else the outermost {...} span. Returns a dict or None."""
    if not result_text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", result_text, re.DOTALL)
    cand = m.group(1) if m else None
    if cand is None:
        s, e = result_text.find("{"), result_text.rfind("}")
        cand = result_text[s:e + 1] if (s != -1 and e > s) else None
    if cand is None:
        return None
    try:
        return json.loads(cand)
    except json.JSONDecodeError:
        return None


def load_baseline(batch: dict) -> dict:
    """Per-school subagent baseline from the on-disk discovery.json (the validated run): did the
    subagent's Wave 1 find a gated URL for this school? {school_id: {"w1": bool, "urls": [...]}}.
    The reference line the headless Wave-1 recall is measured against (apples-to-apples: Wave-1 vs
    Wave-1, since some baseline schools were only recovered by Wave-2)."""
    base = {}
    for d in batch["districts"]:
        disc = D2.lea_dir(d["district_id"], d["name"]) / "discovery.json"
        if not disc.exists():
            continue
        for s in json.loads(disc.read_text()).get("schools", []):
            kept = [g["url"] for g in s.get("wave1_gated", []) if g.get("kept")]
            base[s["school_id"]] = {"w1": bool(kept), "urls": kept}
    return base


def sample(batch: dict, n: int | None) -> list:
    """Deterministic (district, single-school-roster) units across the batch — one school per call so
    the recall denominator is clean. n caps it; default = every school."""
    units = []
    for d in batch["districts"]:
        for r in D2.build_roster(d):
            units.append((d, r))
    return units[:n] if n else units


def one_call(district, school_row, schema, effort):
    """One isolated single-school `claude -p` WebSearch call, retries OFF, then GATE the URLs the way
    the real pipeline does (D2.gate_urls with the district domain). Returns a metrics dict including
    the gated-kept URLs for the precision spot-check."""
    prompt = H.build_wave1_prompt(district, [school_row])
    cmd = ["claude", "-p", "--model", "haiku", "--effort", effort,
           "--output-format", "json", "--allowedTools", "WebSearch",
           "--strict-mcp-config", "--disable-slash-commands"]
    if schema is not None:   # the `none` arm omits --json-schema entirely (SKILL-style free-text JSON)
        cmd += ["--json-schema", json.dumps(schema)]
    t0 = time.time()
    base = {"searches": 0, "turns": None, "cost": 0.0, "raw_urls": 0, "found": False, "gated_urls": []}
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              timeout=420, cwd=str(paths.REPO_ROOT))
    except subprocess.TimeoutExpired:
        return {**base, "outcome": "timeout", "dur_s": round(time.time() - t0, 1)}
    base["dur_s"] = round(time.time() - t0, 1)
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {**base, "outcome": "non_json"}
    mu = env.get("modelUsage", {}) or {}
    base["searches"] = sum((v or {}).get("webSearchRequests", 0) for v in mu.values())
    base["cost"] = round(env.get("total_cost_usd", 0.0) or 0.0, 5)
    base["turns"] = env.get("num_turns")
    if env.get("subtype") == H.STRUCTURED_RETRY_SUBTYPE:
        return {**base, "outcome": "flake"}
    if env.get("is_error"):
        return {**base, "outcome": f"err:{env.get('subtype') or 'unknown'}"}
    if schema is None:                                  # no-schema arm: parse the free-text response
        payload = parse_freetext_json(env.get("result", ""))
        if payload is None:
            return {**base, "outcome": "unparseable"}
    else:
        try:
            payload = H._extract_result_payload(env)
        except Exception:
            return {**base, "outcome": "unparseable"}
    domain = district.get("domain", "") or ""
    sch = next((s for s in payload.get("schools", []) if s.get("school_id") == school_row["school_id"]),
               (payload.get("schools") or [{}])[0])
    raw = sch.get("urls", []) or []
    base["raw_urls"] = len(raw)
    kept = [g["url"] for g in D2.gate_urls(raw, domain) if g["kept"]]   # gate exactly as the pipeline does
    base["gated_urls"] = kept
    base["found"] = bool(kept)
    return {**base, "outcome": "ok"}


def cell_stats(rows: list) -> dict:
    n = len(rows)
    ok = [r for r in rows if r["outcome"] == "ok"]
    okp = len(ok) / n if n else 0
    found = sum(1 for r in rows if r.get("found"))
    mean = lambda k, src=rows: round(statistics.mean([r[k] for r in src]), 3) if src else None
    return {
        "n": n, "ok": len(ok), "ok_pct": round(100 * okp, 1),
        "retried_pct": round(100 * (1 - (1 - okp) ** 2), 1),
        "flake": sum(1 for r in rows if r["outcome"] == "flake"),
        "errors": sum(1 for r in rows if r["outcome"] not in ("ok", "flake")),
        "recall_found": found, "recall_pct": round(100 * found / n, 1) if n else 0,
        "searched": sum(1 for r in rows if r["searches"] > 0),
        "mean_dur_s": mean("dur_s"), "mean_turns": mean("turns", ok), "mean_cost": mean("cost"),
        "total_cost": round(sum(r["cost"] for r in rows), 4),
    }


def write_report(md_path: Path, meta: dict, results: dict, baseline_ref: dict):
    js = {"meta": meta, "baseline_ref": baseline_ref,
          "cells": {c: {"rows": rows, "stats": cell_stats(rows)} for c, rows in results.items()}}
    md_path.with_suffix(".json").write_text(json.dumps(js, indent=2))

    L = ["# Stage 2 headless CLI — reliability + recall evaluation", "",
         f"- generated: {meta['generated_at']}",
         f"- corpus: `{meta['batch']}` (known-positive: every sampled school was `found` in the validated run)",
         f"- sample: **{meta['n']} schools** × reps {meta['reps']}  ·  model: haiku  ·  retries OFF (raw single-shot)",
         f"- matrix: efforts={meta['efforts']} × schemas={meta['schemas']}",
         f"- **reference line** — subagent Wave-1 found {baseline_ref['w1_found']}/{baseline_ref['n']} "
         f"({baseline_ref['w1_pct']}%) of these same schools (the rest needed Wave-2). Headless Wave-1 "
         f"recall below is measured against the same known-positive denominator.", "",
         "`recall%` = schools where headless Wave-1 returned a URL that PASSES THE GATE (the metric that "
         "compounds downstream). `retried%` projects the runner's retries=1 as 1-(1-p)². `searched` = "
         "WebSearch actually fired.", "",
         "## Summary", "",
         "| cell | n | OK% | retried% | flake | err | **recall%** | searched | mean dur | mean turns | mean $ | total $ |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cell, rows in results.items():
        s = cell_stats(rows)
        L.append(f"| {cell} | {s['n']} | {s['ok_pct']} | {s['retried_pct']} | {s['flake']} | {s['errors']} "
                 f"| **{s['recall_pct']}** ({s['recall_found']}/{s['n']}) | {s['searched']}/{s['n']} "
                 f"| {s['mean_dur_s']}s | {s['mean_turns']} | ${s['mean_cost']} | ${s['total_cost']} |")
    L += ["", "## Raw calls (precision spot-check — eyeball the gated URLs)", ""]
    for cell, rows in results.items():
        L += [f"### {cell}", "",
              "| # | district | school | outcome | found | searches | dur | $ | gated URLs |",
              "|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            urls = "<br>".join(r.get("gated_urls", [])) or "—"
            L.append(f"| {i} | {r.get('district_id','')} | {r.get('school','')} | {r['outcome']} | "
                     f"{'✓' if r.get('found') else '·'} | {r['searches']} | {r['dur_s']}s | ${r['cost']} | {urls} |")
        L.append("")
    md_path.write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="batch_00001", help="known-positive corpus (default batch_00001)")
    ap.add_argument("--n", type=int, default=None, help="cap sample to N schools (default: all)")
    ap.add_argument("--reps", type=int, default=1, help="repeat each school (flake variance)")
    ap.add_argument("--efforts", default="low,medium,high")
    ap.add_argument("--schemas", default="strict,loose")
    a = ap.parse_args()

    batch = H.load_batch_any(a.batch)
    baseline = load_baseline(batch)
    units = sample(batch, a.n)
    units = [u for u in units for _ in range(a.reps)]
    efforts = [e.strip() for e in a.efforts.split(",") if e.strip()]
    schema_names = [s.strip() for s in a.schemas.split(",") if s.strip()]

    base_w1 = sum(1 for d, r in units if baseline.get(r["school_id"], {}).get("w1"))
    baseline_ref = {"n": len(units), "w1_found": base_w1,
                    "w1_pct": round(100 * base_w1 / len(units), 1) if units else 0}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = OUT_DIR / f"stage2_eval_{stamp}.md"
    meta = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "batch": a.batch, "n": len(units), "reps": a.reps, "efforts": efforts, "schemas": schema_names}

    total = len(units) * len(efforts) * len(schema_names)
    print(f"Stage 2 eval -> {md_path}\n  {len(units)} school-calls × efforts={efforts} × schemas={schema_names} "
          f"= {total} calls (retries OFF)\n  reference: subagent Wave-1 found {base_w1}/{len(units)} of these\n",
          file=sys.stderr)

    results = {}
    for sname in schema_names:
        for effort in efforts:
            cell = f"effort={effort} schema={sname}"
            print(f"\n=== {cell} ({len(units)} calls) ===", file=sys.stderr)
            rows = []
            for i, (d, r) in enumerate(units, 1):
                m = one_call(d, r, SCHEMAS[sname], effort)
                m["district_id"], m["school"] = d["district_id"], r["school"][:34]
                rows.append(m)
                print(f"  {i:2d}/{len(units)} {d['district_id']} {r['school'][:26]:26} -> {m['outcome']:12} "
                      f"found={'Y' if m.get('found') else 'n'} {m['searches']}srch {m['dur_s']}s ${m['cost']}",
                      file=sys.stderr)
            results[cell] = rows
            write_report(md_path, meta, results, baseline_ref)
            print(f"  [cell done] report updated: {md_path}", file=sys.stderr)

    print(f"\nDONE. Report: {md_path}\n      JSON:   {md_path.with_suffix('.json')}", file=sys.stderr)


if __name__ == "__main__":
    main()
