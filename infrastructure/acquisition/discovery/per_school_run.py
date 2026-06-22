"""Per-school discovery in WAVES (matches ACQUISITION_PIPELINE.md spec).

Wave order: (1) Claude WebSearch via Haiku subagent  ->  (2) OpenRouter gpt-4o-mini-search on the
RESIDUAL (schools wave 1 didn't satisfy)  ->  (3) flag for manual. Perplexity DROPPED (lowest
full-41 coverage 31/41, fewest pages, hub-skewed reach — see EXTRACTION_AND_DISCOVERY_LEARNINGS).

Wave 1 (Claude) can't run from pure Python — it needs the Claude Code agent to spawn a WebSearch
subagent. So this script has THREE entry points the SKILL (or the agent) orchestrates:

  roster   : emit {district -> [{school, schid, bands, query}]}  -> roster.json
             (the agent feeds these queries to a Haiku WebSearch subagent, which writes
              claude_urls.json: {school -> [urls]})
  wave2    : read claude_urls.json, gate it; for schools with NO satisfied candidate, run
             OpenRouter gpt-4o-mini-search on the residual; merge+dedup -> per_school_candidates.json
  flatten  : dedup candidates across schools -> candidates.json for capture_discovery.mjs

Usage:
  per_school_run.py roster  <ids> [--max-schools 12]
  per_school_run.py wave2   <ids> [--cap 3]
  per_school_run.py flatten <ids>
"""
import os, sys, csv, json, argparse
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, "infrastructure/acquisition/discovery")
import school_sampling as S
import discover as D

SCH = "data/raw/federal/nces-ccd/2024_25/ccd_sch_029_2425_w_1a_073025.csv"
OUT = Path("data/acquisition/per_school")
MAN = {d["district_id"]: d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]}

def roster_for(ids):
    want = set(i.zfill(7) for i in ids); out = {i: [] for i in want}
    with open(SCH, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            did = row.get("LEAID", "").zfill(7)
            if did in want and row.get("SY_STATUS", "") == "1":
                b = S.bands_for(row.get("GSLO"), row.get("GSHI"))
                if b: out[did].append({"school": row.get("SCH_NAME", "").strip(),
                                       "schid": row.get("SCHID", ""), "bands": sorted(b)})
    return out

def pick(schools, max_schools):
    by = {"elementary": [], "middle": [], "high": []}
    for s in schools:
        for b in s["bands"]: by[b].append(s)
    picked, seen = [], set()
    for lst in by.values():
        for s in lst[:max_schools]:
            if s["schid"] not in seen: seen.add(s["schid"]); picked.append(s)
    return picked

def query(school, state): return f"{school} {state} bell schedule start and end times"
def norm(u): return D.host_of(u) + urlparse(u).path.rstrip("/")

def cmd_roster(ids, max_schools):
    """Emit per-school queries for the Claude WebSearch (Haiku subagent) wave 1."""
    rost = roster_for(ids)
    for did in ids:
        did = did.zfill(7); d = MAN.get(did, {})
        dom = D.load_domains().get(did, "")
        schools = pick(rost.get(did, []), max_schools)
        recs = [{"school": s["school"], "schid": s["schid"], "bands": s["bands"],
                 "query": query(s["school"], d.get("state", ""))} for s in schools]
        dd = OUT / did; dd.mkdir(parents=True, exist_ok=True)
        (dd / "roster.json").write_text(json.dumps(
            {"district_id": did, "name": d.get("district_name"), "domain": dom,
             "wave1_tool": "claude_websearch", "allowed_domains": [dom] if dom else [],
             "schools": recs}, indent=2))
        print(f"{did} {d.get('district_name','?')[:28]:28} {len(recs)} schools -> roster.json "
              f"(feed queries to Haiku WebSearch subagent, allowed_domains={[dom] if dom else 'unscoped'})")

def cmd_wave2(ids, cap):
    """Wave 2: gate Claude wave-1 URLs; OpenRouter on residual schools; merge."""
    for did in ids:
        did = did.zfill(7); d = MAN.get(did, {}); dom = D.load_domains().get(did, "")
        scoped = bool(dom); slug = dom.split(".")[0] if dom else ""
        dd = OUT / did
        roster = json.loads((dd / "roster.json").read_text())
        claude = {}
        cf = dd / "claude_urls.json"
        if cf.exists():
            raw = json.loads(cf.read_text())               # {school -> [urls]} (subagent output)
            claude = raw if isinstance(raw, dict) else {}
        per_school = []; w1_sat = 0; w2_called = 0
        for s in roster["schools"]:
            kept = {}
            # wave 1: gate Claude URLs for this school
            for u in claude.get(s["school"], []):
                ok, why = D.gate(u, dom, slug, scoped)
                if ok: kept.setdefault(norm(u), {"url": u, "tools": ["claude"], "gate": why})
            if kept: w1_sat += 1
            else:
                # wave 2: OpenRouter on the residual (only schools wave 1 missed)
                w2_called += 1
                try: urls = D.openrouter_search(query(s["school"], d.get("state", "")), dom)
                except Exception as e: urls = []; print(f"   [or/{s['school'][:20]}] ERR {str(e)[:50]}")
                for u in urls:
                    ok, why = D.gate(u, dom, slug, scoped)
                    if ok:
                        k = norm(u); kept.setdefault(k, {"url": u, "tools": [], "gate": why})
                        if "openrouter" not in kept[k]["tools"]: kept[k]["tools"].append("openrouter")
            ranked = sorted(kept.values(), key=D.rank_key, reverse=True)[:cap]
            per_school.append({"school": s["school"], "schid": s["schid"], "bands": s["bands"],
                               "candidates": ranked, "wave": "claude" if (kept and "claude" in next(iter(kept.values()))["tools"]) else ("openrouter" if kept else "manual_flag")})
        flagged = [p["school"] for p in per_school if not p["candidates"]]
        (dd / "per_school_candidates.json").write_text(json.dumps(
            {"district_id": did, "name": d.get("district_name"), "domain": dom, "schools": per_school}, indent=2))
        print(f"{did} {d.get('district_name','?')[:24]:24} wave1(claude) satisfied {w1_sat}/{len(per_school)}, "
              f"wave2(openrouter) ran {w2_called}, manual-flag {len(flagged)}")

def cmd_flatten(ids):
    """Dedup candidates across schools -> candidates.json for capture_discovery.mjs."""
    for did in ids:
        did = did.zfill(7); dd = OUT / did
        d = json.loads((dd / "per_school_candidates.json").read_text())
        dedup = {}
        for sc in d["schools"]:
            for c in sc["candidates"]:
                k = norm(c["url"]); dedup.setdefault(k, {"url": c["url"], "tools": c["tools"], "schools": []})
                dedup[k]["schools"].append(sc["school"])
        cands = list(dedup.values())
        (dd / "candidates.json").write_text(json.dumps(
            {"district_id": did, "name": d["name"], "domain": d["domain"], "scoped": bool(d["domain"]),
             "candidates": cands}, indent=2))
        raw = sum(len(s["candidates"]) for s in d["schools"])
        print(f"{did}: {raw} raw -> {len(cands)} distinct pages to capture")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["roster", "wave2", "flatten"])
    ap.add_argument("ids")
    ap.add_argument("--cap", type=int, default=3)
    ap.add_argument("--max-schools", type=int, default=12)
    a = ap.parse_args()
    ids = a.ids.split(",")
    if a.cmd == "roster": cmd_roster(ids, a.max_schools)
    elif a.cmd == "wave2": cmd_wave2(ids, a.cap)
    elif a.cmd == "flatten": cmd_flatten(ids)

if __name__ == "__main__":
    main()
