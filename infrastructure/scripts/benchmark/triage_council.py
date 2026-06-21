"""Trustworthy source triage: run the Path-1 council over each manually-collected source to PROPOSE
per-band minutes, with cross-family agreement as the confidence signal. Replaces the regex triage
(which failed at band-attribution — the extraction task the council exists for). 'I draft, you verify.'

For each district under data/raw/bell_schedule_pdfs/: best source text (pdftotext/txt/html; OCR
fallback) -> council vote -> per-band {value, method, models} + GT compare. Writes council_triage.json.
"""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, "infrastructure/scripts/benchmark")
sys.path.insert(0, "infrastructure/scripts/benchmark/discovery")
from extractors import make_extractor, MAX_TEXT_LEN
from score_minutes import model_band_values
import aggregate as A

BASE = Path("data/raw/bell_schedule_pdfs")
MAN = {d["district_id"]: d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]}
PAIR = re.compile(r"\d{1,2}:\d{2}")
VOTERS = {"mistral-small-24b": "openrouter:mistralai/mistral-small-24b-instruct-2501",
          "gemini-2.5-flash-lite": "openrouter:google/gemini-2.5-flash-lite",
          "qwen3-235b": "openrouter:qwen/qwen3-235b-a22b-2507"}
JUDGE = "openrouter:deepseek/deepseek-v3.2"

def best_text(dd):
    cands = []
    for p in list(dd.rglob("*.pdf"))[:15]:
        try: cands.append(subprocess.run(["pdftotext","-layout",str(p),"-"],capture_output=True,text=True,timeout=40).stdout)
        except Exception: pass
    for p in list(dd.rglob("*.txt"))+list(dd.rglob("*.html"))+list(dd.rglob("*.htm")):
        try: cands.append(p.read_text(errors="replace"))
        except Exception: pass
    txt = max(cands, key=lambda t: len(PAIR.findall(t)), default="")
    if len(PAIR.findall(txt)) < 4:
        for p in list(dd.rglob("*.png"))[:8]+list(dd.rglob("*.jpg"))[:4]:
            try:
                o = subprocess.run(["tesseract",str(p),"-"],capture_output=True,text=True,timeout=60).stdout
                if len(PAIR.findall(o)) > len(PAIR.findall(txt)): txt = o
            except Exception: pass
    return txt[:MAX_TEXT_LEN]

def main():
    only = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    voters = {k: make_extractor(v) for k, v in VOTERS.items()}
    judge_ex = make_extractor(JUDGE)
    rows = []
    dists = [(st, dd) for st in sorted(BASE.iterdir()) if st.is_dir()
             for dd in sorted(st.iterdir()) if dd.is_dir()]
    for st, dd in dists:
        did = dd.name.split("_")[0]
        if only and did not in only: continue
        txt = best_text(dd)
        if len(PAIR.findall(txt)) < 2:
            rows.append({"state": st.name, "district_id": did, "name": dd.name.split("_",1)[-1][:30],
                         "in_manifest": did in MAN, "proposal": {}, "note": "no_readable_times"}); continue
        # Each model EXTRACTS per-school rows; we compute the modal band value deterministically.
        votes = {}; truncated = {}
        for k, ex in voters.items():
            try:
                out = ex.extract(txt, did, MAN.get(did,{}).get("district_name","?"), MAN.get(did,{}).get("state",""))
                rows_ = out.get("schedules", [])
                votes[k] = model_band_values(rows_, "mode")   # deterministic mode over the model's rows
                truncated[k] = bool(out.get("error")) and not rows_
            except Exception:
                votes[k] = {}; truncated[k] = True
        def judge(band):
            try:
                return model_band_values(judge_ex.extract(txt, did, "?", "").get("schedules", []), "mode").get(band)
            except Exception: return None
        n_rows_max = max((len(v) for v in votes.values()), default=0)
        decided = A.council_school(votes, judge=judge)
        gt = {s["grade_level"]: s.get("instructional_minutes") for s in MAN.get(did,{}).get("schedules", [])}
        prop = {}
        for b in A.BANDS:
            d = decided[b]
            g = gt.get(b)
            prop[b] = {"value": d["value"], "method": d["method"],
                       "models": d["consensus_models"],
                       "gt": g, "match": (None if (g is None or d["value"] is None) else abs(d["value"]-g) <= 15)}
        rows.append({"state": st.name, "district_id": did, "name": dd.name.split("_",1)[-1][:30],
                     "in_manifest": did in MAN, "proposal": prop,
                     "rows_per_model": {k: len(v) for k, v in votes.items()},
                     "truncated_models": [k for k, t in truncated.items() if t]})
        bands = [b for b in A.BANDS if prop[b]["value"] is not None]
        print(f"{st.name:3}{did:8}{'M' if did in MAN else '+':2} "
              + " ".join(f"{b[:3]}={prop[b]['value']}({prop[b]['method'][:4]}{'' if prop[b]['match'] is None else '/GT'+('OK' if prop[b]['match'] else 'X')})"
                         for b in bands) + f"  {dd.name.split('_',1)[-1][:24]}")
    Path("data/benchmark/council_triage.json").write_text(json.dumps(rows, indent=2))
    print(f"\nwritten data/benchmark/council_triage.json ({len(rows)} districts)")

if __name__ == "__main__":
    main()
