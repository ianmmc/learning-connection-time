"""Per-page Path-1 council extraction -> per-page band values -> district aggregation -> score vs GT.

Path-1 council: voters = mistral-small-24b + gemini-2.5-flash-lite + qwen3-235b (3 families);
judge = deepseek-v3.2 (4th family) re-reads the page on no-consensus. Accept rule + aggregation
from aggregate.py. Each distinct captured page is extracted ONCE; its band values fan out to the
schools it covers; bands aggregate across pages (modal->mean). Usage: council_extract.py <id>"""
import os, sys, json, re, subprocess
from pathlib import Path
sys.path.insert(0, "infrastructure/scripts/benchmark")
sys.path.insert(0, "infrastructure/scripts/benchmark/discovery")
from extractors import make_extractor
from score_minutes import gt_minutes_by_band
import aggregate as A

PS = Path("data/benchmark_results/per_school")
TIME = re.compile(r"\b\d{1,2}:\d{2}")
VOTERS = {"mistral-small-24b": "openrouter:mistralai/mistral-small-24b-instruct-2501",
          "gemini-2.5-flash-lite": "openrouter:google/gemini-2.5-flash-lite",
          "qwen3-235b": "openrouter:qwen/qwen3-235b-a22b-2507"}
JUDGE = ("deepseek-v3.2", "openrouter:deepseek/deepseek-v3.2")

def page_text(capdir, rec):
    f = rec.get("files", {})
    def run(c):
        try: return subprocess.run(c, capture_output=True, text=True, timeout=90).stdout
        except Exception: return ""
    cands = []
    if f.get("txt") and (capdir/f["txt"]).exists(): cands.append(open(capdir/f["txt"]).read())
    if f.get("bin") and (capdir/f["bin"]).exists():
        p = str(capdir/f["bin"]); cands.append(run(["pdftotext","-layout",p,"-"]) if p.endswith(".pdf") else run(["tesseract",p,"-"]))
    if f.get("png") and (capdir/f["png"]).exists(): cands.append(run(["tesseract", str(capdir/f["png"]), "-"]))
    return max(cands, key=lambda t: len(TIME.findall(t)), default="")

def band_vals(extractor, text, did, name, state):
    """Run one extractor on text -> {band: net_minutes (mode within page)}."""
    try:
        out = extractor.extract(text, did, name, state)
        from score_minutes import model_band_values
        return model_band_values(out.get("schedules", []), "mode")
    except Exception as e:
        return {}

def main():
    did = sys.argv[1].zfill(7)
    man = {d["district_id"]: d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]}
    d = man[did]; name = d["district_name"]; state = d["state"]
    gtb = gt_minutes_by_band(d)
    cand = json.load(open(PS/did/"candidates.json"))
    caps = {c["hash"]: c for c in json.load(open(PS/did/"captures.json"))}
    capdir = PS/did/"captures"
    # map captured page -> candidate (for school coverage); align by url
    by_url = {c["url"]: c for c in cand["candidates"]}

    voters = {k: make_extractor(v) for k, v in VOTERS.items()}
    judge_ex = make_extractor(JUDGE[1])

    per_page = []   # one accepted {band:val} per distinct page
    escalations = 0; pages_used = 0
    for rec in caps.values():
        if not rec.get("ok"): continue
        text = page_text(capdir, rec)
        if len(TIME.findall(text)) < 3: continue   # not a schedule-bearing page
        pages_used += 1
        votes = {k: band_vals(ex, text, did, name, state) for k, ex in voters.items()}
        def judge(band):
            jb = band_vals(judge_ex, text, did, name, state); return jb.get(band)
        decided = A.council_school(votes, judge=judge)
        if any(v["method"] in ("judge", "judge_implausible") for v in decided.values()): escalations += 1
        accepted = {b: decided[b]["value"] for b in A.BANDS if decided[b]["value"] is not None}
        if accepted:
            per_page.append({"url": rec["url"], **accepted,
                             "methods": {b: decided[b]["method"] for b in A.BANDS}})

    district = A.aggregate_district(per_page)
    # score
    matched = sum(1 for b, g in gtb.items() if district[b]["value"] is not None and abs(district[b]["value"]-g) <= A.TOL)
    print(f"\n=== {did} {name} (per-school council) ===")
    print(f"distinct pages: {len(caps)} | schedule-bearing used: {pages_used} | judge escalations: {escalations}")
    print(f"{'band':<12}{'GT':>6}{'district':>10}{'method':>16}{'n_pages':>8}")
    for b in A.BANDS:
        g = gtb.get(b); dd = district[b]
        hit = "" if g is None else (" HIT" if dd["value"] is not None and abs(dd["value"]-g) <= A.TOL else " miss")
        print(f"{b:<12}{(g if g is not None else '-'):>6}{(dd['value'] if dd['value'] is not None else '-'):>10}{dd['method']:>16}{dd['n']:>8}{hit}")
    print(f"\nBANDS MATCHED vs GT: {matched}/{len(gtb)}  ({100*matched/len(gtb) if gtb else 0:.0f}%)")
    (PS/did/"council_result.json").write_text(json.dumps(
        {"district": district, "per_page": per_page, "gt": gtb,
         "pages_used": pages_used, "escalations": escalations, "matched": matched, "gt_bands": len(gtb)}, indent=2))

if __name__ == "__main__":
    main()
