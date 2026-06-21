"""Triage manually-collected bell-schedule sources for GT reconstruction.

For each district under data/raw/bell_schedule_pdfs/, read the best source text (pdftotext/txt/html;
OCR images as fallback), find plausible school START-END time pairs, classify into bands, and judge
whether each band is INDEPENDENTLY RECONSTRUCTABLE from the source (the strict bar). Cross-reference
the current 41-manifest GT: does the source actually support the claimed GT value (+/-15)?

Output buckets: GOLD (>=2 bands reconstructable), USABLE (1 band), DISCARD (0 / unreadable).
Writes data/benchmark/source_triage.json for review. Read-only on data/raw.
"""
import json, re, subprocess
from pathlib import Path
from collections import defaultdict

BASE = Path("data/raw/bell_schedule_pdfs")
MAN = {d["district_id"]: d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]}
PAIR = re.compile(r"(\d{1,2}:\d{2})\s*(?:[AaPp]\.?[Mm]\.?)?\s*[-–to]+\s*(\d{1,2}:\d{2})\s*(?:[AaPp]\.?[Mm]\.?)?")
ELEM = re.compile(r"\b(element|primary|\bes\b|k-?5|k-?6|k-?8|kinder|grade school)\b", re.I)
MIDD = re.compile(r"\b(middle|junior|jr\.?\s*high|\bms\b|intermediate|6-?8|7-?8)\b", re.I)
HIGH = re.compile(r"\b(high school|\bhs\b|senior high|9-?12|10-?12)\b", re.I)

def to_min(t):
    h, m = t.split(":"); return int(h) * 60 + int(m)

def best_text(dd):
    cands = []
    for p in list(dd.rglob("*.pdf"))[:15]:
        try: cands.append(subprocess.run(["pdftotext","-layout",str(p),"-"],capture_output=True,text=True,timeout=40).stdout)
        except Exception: pass
    for p in list(dd.rglob("*.txt")) + list(dd.rglob("*.html")) + list(dd.rglob("*.htm")):
        try: cands.append(p.read_text(errors="replace"))
        except Exception: pass
    txt = max(cands, key=lambda t: len(PAIR.findall(t)), default="")
    if len(PAIR.findall(txt)) < 2:   # OCR fallback on images
        for p in list(dd.rglob("*.png"))[:8] + list(dd.rglob("*.jpg"))[:4]:
            try:
                o = subprocess.run(["tesseract",str(p),"-"],capture_output=True,text=True,timeout=60).stdout
                if len(PAIR.findall(o)) > len(PAIR.findall(txt)): txt = o
            except Exception: pass
    return txt

def band_durations(txt):
    """Plausible full-day durations (4-9h) attributed to bands by nearby context line."""
    out = defaultdict(list)
    for line in txt.splitlines():
        for st, en in PAIR.findall(line):
            try: d = to_min(en) - to_min(st)
            except Exception: continue
            if d < 0: d += 720  # PM rollover guess
            if not (240 <= d <= 540): continue   # plausible school day
            b = "high" if HIGH.search(line) else "middle" if MIDD.search(line) else "elementary" if ELEM.search(line) else None
            if b: out[b].append(d)
    return out

def main():
    rows = []
    for st in sorted(BASE.iterdir()):
        if not st.is_dir(): continue
        for dd in sorted(st.iterdir()):
            if not dd.is_dir(): continue
            did = dd.name.split("_")[0]
            txt = best_text(dd)
            durs = band_durations(txt)
            bands_found = [b for b in ("elementary","middle","high") if durs.get(b)]
            in_man = did in MAN
            gt = {s["grade_level"]: s.get("instructional_minutes") for s in MAN[did].get("schedules", [])} if in_man else {}
            # does source support each GT band within +/-15?
            gt_support = {}
            for b, v in gt.items():
                if v is None: gt_support[b] = "no_gt_val"; continue
                gt_support[b] = "supported" if any(abs(d - v) <= 15 for d in durs.get(b, [])) else "UNSUPPORTED"
            bucket = ("GOLD" if len(bands_found) >= 2 else "USABLE" if len(bands_found) == 1 else "DISCARD")
            rows.append({"state": st.name, "district_id": did, "name": dd.name.split("_",1)[-1][:30],
                         "in_manifest": in_man, "gt_bands": list(gt.keys()),
                         "bands_reconstructable": bands_found, "gt_support": gt_support,
                         "n_pairs": len(PAIR.findall(txt)), "bucket": bucket})
    rows.sort(key=lambda r: ({"GOLD":0,"USABLE":1,"DISCARD":2}[r["bucket"]], not r["in_manifest"], -r["n_pairs"]))
    Path("data/benchmark/source_triage.json").write_text(json.dumps(rows, indent=2))
    # report
    print(f"{'bucket':8}{'ST':3}{'id':8}{'M?':3}{'recon-bands':22}{'GT support':26}{'pairs':6} name")
    for r in rows:
        sup = ",".join(f"{b[:3]}:{v[:11]}" for b,v in r["gt_support"].items()) if r["in_manifest"] else "(expansion)"
        print(f"{r['bucket']:8}{r['state']:3}{r['district_id']:8}{'Y' if r['in_manifest'] else '-':3}"
              f"{','.join(b[:4] for b in r['bands_reconstructable']) or '-':22}{sup:26}{r['n_pairs']:<6}{r['name']}")
    from collections import Counter
    c = Counter(r["bucket"] for r in rows)
    unsup = sum(1 for r in rows if r["in_manifest"] and "UNSUPPORTED" in r["gt_support"].values())
    print(f"\nbuckets: {dict(c)}  | manifest districts with an UNSUPPORTED GT band: {unsup}")
    print("written: data/benchmark/source_triage.json")

if __name__ == "__main__":
    main()
