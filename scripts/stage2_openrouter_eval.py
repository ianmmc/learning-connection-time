#!/usr/bin/env python3
"""Stage 2 OpenRouter `gpt-4o-mini-search` evaluation — the head-to-head against the Claude CLI
no-schema run (REQ-104), on the SAME known-positive corpus (batch_00001's 53 schools).

Mirrors the live Wave-2 provider exactly (infrastructure/acquisition/common/discover.openrouter_search):
model `openai/gpt-4o-mini-search-preview`, query `"<school query> site:<domain>"`, web plugin, URLs
from message annotations — then GATES the URLs (D2.gate_urls) and scores recall vs the same 47%
subagent-Wave-1 baseline. ADDITIONALLY captures REAL OpenRouter cost per call (this provider costs
out-of-pocket, unlike the subscription CLI — the whole point of the comparison).

Reliability here = API success (no schema, so no structured-output flake); the failure modes are API
errors / empty results / billing (402/429 -> SystemExit halt, same as the pipeline).

Usage (from repo root):
    python3 scripts/stage2_openrouter_eval.py --smoke      # 1 call, DUMP raw response (pin cost field)
    python3 scripts/stage2_openrouter_eval.py              # all 53 schools
    python3 scripts/stage2_openrouter_eval.py --n 10

Report (incremental): data/acquisition/diagnostics/stage2_openrouter_<UTC>.md (+ .json sidecar).
"""
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import discover as DISC
# reuse the corpus + baseline helpers from the Claude eval so the two reports are apples-to-apples.
# scripts/ isn't an installed package (only `infrastructure` is, via pip -e .), so put this file's dir
# on the path and import the sibling module directly — works regardless of cwd / invocation style.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage2_cli_reliability import load_baseline, sample  # noqa: E402

MODEL = "openai/gpt-4o-mini-search-preview"
OUT_DIR = paths.ACQUISITION / "diagnostics"


def _client():
    import openai
    return openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=DISC._openrouter_key())


def _extract_cost(resp_dump: dict) -> float | None:
    """OpenRouter returns accounting under usage.cost when usage:{include:true} is set."""
    u = resp_dump.get("usage") or {}
    for k in ("cost", "total_cost"):
        if u.get(k) is not None:
            return float(u[k])
    return None


def one_call(district, school_row, client):
    """One gpt-4o-mini-search call, mirroring openrouter_search + usage accounting. Gates the URLs
    the way the pipeline does. Returns a metrics dict."""
    import openai
    domain = district.get("domain", "") or ""
    query = f"{school_row['query']} site:{domain}" if domain else school_row["query"]
    base = {"searches": None, "cost": None, "raw_urls": 0, "found": False, "gated_urls": []}
    t0 = time.time()
    try:
        r = client.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": query}], max_tokens=600,
            extra_body={"plugins": [{"id": "web"}], "usage": {"include": True}})
    except openai.APIStatusError as e:
        if e.status_code in DISC.BILLING_AUTH_STATUS_CODES:
            raise SystemExit(f"CONTROL FAILURE: OpenRouter HTTP {e.status_code} (billing/auth/rate) — "
                             f"halting. {str(e)[:160]}")
        return {**base, "outcome": f"err:{e.status_code}", "dur_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {**base, "outcome": f"err:{type(e).__name__}", "dur_s": round(time.time() - t0, 1)}
    base["dur_s"] = round(time.time() - t0, 1)
    dump = r.model_dump()
    base["cost"] = _extract_cost(dump)
    ann = getattr(r.choices[0].message, "annotations", None) or []
    raw = []
    for a in ann:
        ad = a if isinstance(a, dict) else a.model_dump()
        u = (ad.get("url_citation") or {}).get("url") or ad.get("url")
        if u:
            raw.append(u)
    base["raw_urls"] = len(raw)
    kept = [g["url"] for g in D2.gate_urls(raw, domain) if g["kept"]]
    base["gated_urls"] = kept
    base["found"] = bool(kept)
    return {**base, "outcome": "ok"}


def cell_stats(rows):
    n = len(rows)
    ok = [r for r in rows if r["outcome"] == "ok"]
    found = sum(1 for r in rows if r.get("found"))
    costs = [r["cost"] for r in rows if r.get("cost") is not None]
    mean = lambda v: round(statistics.mean(v), 5) if v else None
    return {"n": n, "ok": len(ok), "ok_pct": round(100 * len(ok) / n, 1) if n else 0,
            "errors": sum(1 for r in rows if r["outcome"] != "ok"),
            "recall_found": found, "recall_pct": round(100 * found / n, 1) if n else 0,
            "mean_dur_s": mean([r["dur_s"] for r in rows]),
            "mean_cost": mean(costs), "total_cost": round(sum(costs), 4) if costs else None,
            "cost_known": len(costs)}


def write_report(md_path, meta, rows, baseline_ref):
    s = cell_stats(rows)
    md_path.with_suffix(".json").write_text(json.dumps(
        {"meta": meta, "baseline_ref": baseline_ref, "stats": s, "rows": rows}, indent=2))
    L = ["# Stage 2 — OpenRouter gpt-4o-mini-search evaluation", "",
         f"- generated: {meta['generated_at']}  ·  model: `{MODEL}`",
         f"- corpus: `{meta['batch']}` (known-positive) · {s['n']} schools · **REAL out-of-pocket cost**",
         f"- reference: subagent Wave-1 found {baseline_ref['w1_found']}/{baseline_ref['n']} "
         f"({baseline_ref['w1_pct']}%) of these schools", "",
         "## Summary", "",
         "| n | OK% | err | **recall%** | mean dur | mean $ | total $ | cost-known |",
         "|---|---|---|---|---|---|---|---|",
         f"| {s['n']} | {s['ok_pct']} | {s['errors']} | **{s['recall_pct']}** ({s['recall_found']}/{s['n']}) "
         f"| {s['mean_dur_s']}s | ${s['mean_cost']} | ${s['total_cost']} | {s['cost_known']}/{s['n']} |",
         "", "## Raw calls (precision spot-check)", "",
         "| # | district | school | outcome | found | raw | dur | $ | gated URLs |",
         "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        urls = "<br>".join(r.get("gated_urls", [])) or "—"
        L.append(f"| {i} | {r.get('district_id','')} | {r.get('school','')} | {r['outcome']} | "
                 f"{'✓' if r.get('found') else '·'} | {r['raw_urls']} | {r['dur_s']}s | "
                 f"${r.get('cost')} | {urls} |")
    md_path.write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="batch_00001")
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--smoke", action="store_true", help="1 call, dump raw response (pin cost field)")
    a = ap.parse_args()

    from infrastructure.acquisition.stage2_discover import headless as H
    batch = H.load_batch_any(a.batch)
    baseline = load_baseline(batch)
    units = sample(batch, a.n)
    client = _client()

    if a.smoke:
        d, r = units[0]
        domain = d.get("domain", "") or ""
        query = f"{r['query']} site:{domain}" if domain else r["query"]
        print(f"SMOKE: {d['district_id']} {r['school']} | query={query!r}", file=sys.stderr)
        import openai
        resp = client.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": query}], max_tokens=600,
            extra_body={"plugins": [{"id": "web"}], "usage": {"include": True}})
        dump = resp.model_dump()
        print("usage:", json.dumps(dump.get("usage"), indent=2))
        print("extracted cost:", _extract_cost(dump))
        ann = getattr(resp.choices[0].message, "annotations", None) or []
        print(f"annotations: {len(ann)} url citations")
        return

    base_w1 = sum(1 for d, r in units if baseline.get(r["school_id"], {}).get("w1"))
    baseline_ref = {"n": len(units), "w1_found": base_w1,
                    "w1_pct": round(100 * base_w1 / len(units), 1) if units else 0}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = OUT_DIR / f"stage2_openrouter_{stamp}.md"
    meta = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "batch": a.batch, "model": MODEL}
    print(f"OpenRouter eval -> {md_path}\n  {len(units)} calls (REAL cost) · reference Wave-1 {base_w1}/{len(units)}\n",
          file=sys.stderr)

    rows = []
    for i, (d, r) in enumerate(units, 1):
        m = one_call(d, r, client)
        m["district_id"], m["school"] = d["district_id"], r["school"][:34]
        rows.append(m)
        print(f"  {i:2d}/{len(units)} {d['district_id']} {r['school'][:26]:26} -> {m['outcome']:10} "
              f"found={'Y' if m.get('found') else 'n'} {m['raw_urls']}url {m['dur_s']}s ${m.get('cost')}",
              file=sys.stderr)
        write_report(md_path, meta, rows, baseline_ref)
    print(f"\nDONE. Report: {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
