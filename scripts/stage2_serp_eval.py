#!/usr/bin/env python3
"""Stage 2 SERP-provider evaluation — unified head-to-head harness (REQ-104).

Measures any dedicated search/SERP provider on the SAME known-positive corpus (batch_00001's 53
schools) the Claude-CLI and OpenRouter evals used, so recall/precision/cost/latency are directly
comparable across providers. Each provider returns candidate URLs, which are GATED exactly as the
pipeline does (D2.gate_urls, domain-scoped), then scored vs the 47% subagent-Wave-1 baseline.

Providers (all keys in config/secrets.local.json, same file as OPENROUTER_API_KEY):
  serper      — SERPER_API_KEY              · real Google, `site:` in query · ~$0.001/req
  brightdata  — BRIGHTDATA_API_KEY + BRIGHTDATA_SERP_ZONE · real Google proxy, `site:` · ~$0.0015/req
  perplexity  — PERPLEXITY_API_KEY          · Perplexity Search API, native search_domain_filter · ~est

Usage (from repo root):
    python3 scripts/stage2_serp_eval.py --provider serper --smoke      # 1 call, dump raw URLs
    python3 scripts/stage2_serp_eval.py --provider serper              # all 53
    python3 scripts/stage2_serp_eval.py --provider brightdata
    python3 scripts/stage2_serp_eval.py --provider perplexity

Report (incremental): data/acquisition/diagnostics/stage2_<provider>_<UTC>.md (+ .json sidecar).
Writes NOTHING to data/raw or the registry. NOTE: brightdata/perplexity cost REAL money; serper's
53 calls fit the free 2,500-credit trial.
"""
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

import requests

from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import discover as DISC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage2_cli_reliability import load_baseline, sample  # noqa: E402

SCHED_KW = ("bell", "schedule", "schoolday", "school-day", "hours", "calendar", "start", "dismiss",
            "arrival", "class")
OUT_DIR = paths.ACQUISITION / "diagnostics"
# Indicative $/request for the cost ESTIMATE column (reconcile against each provider's billing page).
COST_PER_REQ = {"serper": 0.001, "brightdata": 0.0015, "perplexity": 0.005}


def _secret(name):
    return os.getenv(name) or _from_secrets(name)


def _from_secrets(name):
    try:
        return json.loads(DISC.SECRETS_FILE.read_text()).get(name)
    except Exception:
        return None


def _halt_if_billing(status, text):
    if status in DISC.BILLING_AUTH_STATUS_CODES:
        raise SystemExit(f"CONTROL FAILURE: HTTP {status} (billing/auth/rate) — halting. {text[:160]}")


# --------------------------------------------------------------------- providers
# each returns a list of candidate URLs (raw, ungated); raises SystemExit on billing/auth.
def call_serper(query, domain, cfg):
    q = f"{query} site:{domain}" if domain else query
    r = requests.post("https://google.serper.dev/search",
                      headers={"X-API-KEY": cfg["key"], "Content-Type": "application/json"},
                      json={"q": q, "num": 10, "gl": "us"}, timeout=30)
    _halt_if_billing(r.status_code, r.text)
    r.raise_for_status()
    return [o["link"] for o in r.json().get("organic", []) if o.get("link")]


# Bright Data is multi-engine — you switch engines by changing the search URL passed to /request.
# US-English K-12 realistically only benefits from Google + Bing (Yahoo/DuckDuckGo are Bing-powered;
# Yandex/Baidu/Naver are foreign-market). `brd_json=1` returns Bright Data's parsed structured output.
ENGINE_URL = {
    "google":     lambda q: f"https://www.google.com/search?q={q}&hl=en&gl=us",
    "bing":       lambda q: f"https://www.bing.com/search?q={q}&setLang=en-US&cc=US",
    "duckduckgo": lambda q: f"https://duckduckgo.com/?q={q}",
    "yahoo":      lambda q: f"https://search.yahoo.com/search?p={q}",
    "yandex":     lambda q: f"https://yandex.com/search/?text={q}",
    "baidu":      lambda q: f"https://www.baidu.com/s?wd={q}",
}


def call_brightdata(query, domain, cfg):
    from urllib.parse import quote_plus
    q = f"{query} site:{domain}" if domain else query
    base = ENGINE_URL[cfg.get("engine", "google")](quote_plus(q))
    gurl = base + ("&" if "?" in base else "?") + "brd_json=1"
    r = requests.post("https://api.brightdata.com/request",
                      headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
                      json={"zone": cfg["zone"], "url": gurl, "format": "raw"}, timeout=60)
    _halt_if_billing(r.status_code, r.text)
    r.raise_for_status()
    try:
        body = r.json()
        if isinstance(body, str):       # some zones return the brd_json payload as a JSON string
            body = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        # A non-JSON body almost always means BRIGHTDATA_SERP_ZONE points at the wrong zone TYPE
        # (e.g. a residential proxy zone, not a SERP API zone) — surface that, don't crash.
        raise RuntimeError(f"BrightData returned non-JSON (is BRIGHTDATA_SERP_ZONE a SERP API zone? "
                           f"got: {r.text[:120]!r})")
    org = body.get("organic") or body.get("organic_results") or []
    return [o.get("link") or o.get("url") for o in org if (o.get("link") or o.get("url"))]


def call_perplexity(query, domain, cfg):
    body = {"query": query, "max_results": 10, "country": "US"}
    if domain:
        body["search_domain_filter"] = [domain]      # native domain scoping (no site: needed)
    r = requests.post("https://api.perplexity.ai/search",
                      headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
                      json=body, timeout=45)
    _halt_if_billing(r.status_code, r.text)
    r.raise_for_status()
    return [x["url"] for x in r.json().get("results", []) if x.get("url")]


CALLERS = {"serper": call_serper, "brightdata": call_brightdata, "perplexity": call_perplexity}


def one_call(provider, district, school_row, cfg):
    domain = district.get("domain", "") or ""
    base = {"raw_urls": 0, "found": False, "gated_urls": [], "sched_kw": False}
    t0 = time.time()
    try:
        raw = CALLERS[provider](school_row["query"], domain, cfg)
    except SystemExit:
        raise
    except requests.HTTPError as e:
        return {**base, "outcome": f"err:{e.response.status_code}", "dur_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {**base, "outcome": f"err:{type(e).__name__}", "dur_s": round(time.time() - t0, 1)}
    base["dur_s"] = round(time.time() - t0, 1)
    base["raw_urls"] = len(raw)
    kept = [g["url"] for g in D2.gate_urls(raw, domain) if g["kept"]]
    base["gated_urls"] = kept
    base["found"] = bool(kept)
    base["sched_kw"] = any(any(k in u.lower() for k in SCHED_KW) for u in kept)
    return {**base, "outcome": "ok"}


def cell_stats(rows, provider):
    n = len(rows)
    ok = [r for r in rows if r["outcome"] == "ok"]
    found = sum(1 for r in rows if r.get("found"))
    sched = sum(1 for r in rows if r.get("sched_kw"))
    mean = lambda v: round(statistics.mean(v), 3) if v else None
    return {"n": n, "ok": len(ok), "ok_pct": round(100 * len(ok) / n, 1) if n else 0,
            "errors": sum(1 for r in rows if r["outcome"] != "ok"),
            "recall_found": found, "recall_pct": round(100 * found / n, 1) if n else 0,
            "sched_kw": sched, "sched_pct": round(100 * sched / n, 1) if n else 0,
            "mean_dur_s": mean([r["dur_s"] for r in rows]),
            "est_cost_usd": round(len(ok) * COST_PER_REQ.get(provider.split("-")[0], 0), 4)}


def write_report(md_path, meta, rows, baseline_ref):
    s = cell_stats(rows, meta["provider"])
    md_path.with_suffix(".json").write_text(json.dumps(
        {"meta": meta, "baseline_ref": baseline_ref, "stats": s, "rows": rows}, indent=2))
    L = [f"# Stage 2 — {meta['provider']} SERP evaluation", "",
         f"- generated: {meta['generated_at']}  ·  provider: **{meta['provider']}**",
         f"- corpus: `{meta['batch']}` (known-positive) · {s['n']} schools",
         f"- reference: subagent Wave-1 {baseline_ref['w1_found']}/{baseline_ref['n']} "
         f"({baseline_ref['w1_pct']}%) · prior runs: OpenRouter 100%/~75%, Claude-low/none 66%/60%", "",
         "## Summary", "",
         "| n | OK% | err | gate-pass recall | schedule-kw | mean dur | est cost |",
         "|---|---|---|---|---|---|---|",
         f"| {s['n']} | {s['ok_pct']} | {s['errors']} | **{s['recall_pct']}%** ({s['recall_found']}/{s['n']}) "
         f"| {s['sched_pct']}% ({s['sched_kw']}/{s['n']}) | {s['mean_dur_s']}s | ~${s['est_cost_usd']} |", "",
         "## Raw calls (precision spot-check — eyeball the gated URLs)", "",
         "| # | district | school | outcome | found | sched | raw | dur | gated URLs |",
         "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        urls = "<br>".join(r.get("gated_urls", [])) or "—"
        L.append(f"| {i} | {r.get('district_id','')} | {r.get('school','')} | {r['outcome']} | "
                 f"{'✓' if r.get('found') else '·'} | {'✓' if r.get('sched_kw') else '·'} | "
                 f"{r['raw_urls']} | {r['dur_s']}s | {urls} |")
    md_path.write_text("\n".join(L))


def _load_cfg(provider):
    key_env = {"serper": "SERPER_API_KEY", "brightdata": "BRIGHTDATA_API_KEY",
               "perplexity": "PERPLEXITY_API_KEY"}[provider]
    key = _secret(key_env)
    if not key:
        raise SystemExit(f"{key_env} not found in env or config/secrets.local.json.")
    cfg = {"key": key}
    if provider == "brightdata":
        cfg["zone"] = _secret("BRIGHTDATA_SERP_ZONE")
        if not cfg["zone"]:
            raise SystemExit("BRIGHTDATA_SERP_ZONE not found — add your SERP zone name to secrets.")
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=list(CALLERS))
    ap.add_argument("--engine", default="google", choices=list(ENGINE_URL),
                    help="Bright Data only: which search engine to query (default google)")
    ap.add_argument("--batch", default="batch_00001")
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--smoke", action="store_true", help="1 call, print raw URLs")
    a = ap.parse_args()

    cfg = _load_cfg(a.provider)
    cfg["engine"] = a.engine
    # label runs by engine so e.g. a Bing run doesn't overwrite/!confuse the Google one
    label = a.provider if (a.provider != "brightdata" or a.engine == "google") else f"brightdata-{a.engine}"
    from infrastructure.acquisition.stage2_discover import headless as H
    batch = H.load_batch_any(a.batch)
    baseline = load_baseline(batch)
    units = sample(batch, a.n)

    if a.smoke:
        d, r = units[0]
        print(f"SMOKE [{a.provider}]: {d['district_id']} {r['school']} domain={d.get('domain')!r}",
              file=sys.stderr)
        try:
            raw = CALLERS[a.provider](r["query"], d.get("domain", "") or "", cfg)
        except Exception as e:
            raise SystemExit(f"smoke failed: {type(e).__name__}: {e}")
        print(f"raw URLs ({len(raw)}):")
        for u in raw:
            print("  ", u)
        kept = [g["url"] for g in D2.gate_urls(raw, d.get("domain", "") or "") if g["kept"]]
        print(f"gated-kept ({len(kept)}):", kept)
        return

    base_w1 = sum(1 for d, r in units if baseline.get(r["school_id"], {}).get("w1"))
    baseline_ref = {"n": len(units), "w1_found": base_w1,
                    "w1_pct": round(100 * base_w1 / len(units), 1) if units else 0}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = OUT_DIR / f"stage2_{label}_{stamp}.md"
    meta = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "batch": a.batch, "provider": label}
    print(f"{label} eval -> {md_path}\n  {len(units)} calls\n", file=sys.stderr)

    rows = []
    for i, (d, r) in enumerate(units, 1):
        m = one_call(a.provider, d, r, cfg)
        m["district_id"], m["school"] = d["district_id"], r["school"][:34]
        rows.append(m)
        print(f"  {i:2d}/{len(units)} {d['district_id']} {r['school'][:26]:26} -> {m['outcome']:10} "
              f"found={'Y' if m.get('found') else 'n'} sched={'Y' if m.get('sched_kw') else 'n'} "
              f"{m['raw_urls']}url {m['dur_s']}s", file=sys.stderr)
        write_report(md_path, meta, rows, baseline_ref)
    print(f"\nDONE. Report: {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
