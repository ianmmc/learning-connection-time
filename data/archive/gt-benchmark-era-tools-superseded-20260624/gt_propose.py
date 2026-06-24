"""Propose GROSS per-band minutes for the hand-curated GT districts, for human verification.

Reads data/benchmark/gt_curation_<ts>/{hub,per_school}/<district>/, gathers source text (all PDFs
concatenated + OCR of images), runs the Path-1 council (models extract per-school start/end rows;
code computes the modal band value deterministically), and emits a per-district proposal table.
Target = GROSS bell-to-bell (end - start). 'I draft, you verify' — writes gt_proposals.json.

Usage: gt_propose.py <curation_dir> [district_id,...]
"""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, "infrastructure/acquisition")
sys.path.insert(0, "infrastructure/acquisition/discovery")
from extractors import make_extractor, MAX_TEXT_LEN
from score_minutes import model_band_values
import aggregate as A

PAIR = re.compile(r"\d{1,2}:\d{2}")
VOTERS = {"mistral-small-24b": "openrouter:mistralai/mistral-small-24b-instruct-2501",
          "gemini-2.5-flash-lite": "openrouter:google/gemini-2.5-flash-lite",
          "qwen3-235b": "openrouter:qwen/qwen3-235b-a22b-2507"}
JUDGE = "openrouter:deepseek/deepseek-v3.2"

def gather_text(dd):
    """Concatenate text from ALL source files in a district dir (PDFs + OCR of images)."""
    parts = []
    for f in sorted(dd.iterdir()):
        if not f.is_file(): continue
        suf = f.suffix.lower()
        try:
            if suf == ".pdf" or suf == "":   # extensionless originals: try pdftotext, then OCR
                t = subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True, timeout=40).stdout
                if len(PAIR.findall(t)) < 2:
                    t = _ocr_pdf(f)   # scanned/image-only PDF -> rasterize then OCR (tesseract can't read a PDF directly)
                parts.append(f"\n--- {f.name} ---\n" + t)
            elif suf in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                t = subprocess.run(["tesseract", str(f), "-"], capture_output=True, text=True, timeout=60).stdout
                parts.append(f"\n--- {f.name} ---\n" + t)
        except Exception:
            pass
    txt = "\n".join(parts)
    return txt[:MAX_TEXT_LEN]

def _ocr_pdf(f):
    """OCR a scanned/image-only PDF: rasterize each page to PNG (pdftoppm), tesseract each.
    tesseract cannot read a PDF directly, so the page must be rendered to an image first."""
    import tempfile, os, glob
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "200", "-png", str(f), os.path.join(tmp, "pg")],
                       capture_output=True, timeout=120)
        for png in sorted(glob.glob(os.path.join(tmp, "pg*.png"))):
            out.append(subprocess.run(["tesseract", png, "-"], capture_output=True, text=True, timeout=90).stdout)
    return "\n".join(out)

def main():
    R = Path(sys.argv[1])
    only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
    recon = json.loads((R / "CURATION_RECONCILED.json").read_text())
    voters = {k: make_extractor(v) for k, v in VOTERS.items()}
    judge_ex = make_extractor(JUDGE)
    out = []
    for bucket in ("hub", "per_school"):
        for d in recon["buckets"][bucket]:
            did = d["district_id"]
            if only and did not in only: continue
            dd = R / bucket / d["dir"]
            txt = gather_text(dd)
            if len(PAIR.findall(txt)) < 2:
                out.append({"district_id": did, "dir": d["dir"], "topology": bucket, "proposal": {}, "note": "no_readable_times"})
                print(f"{did} {d['dir'].split('_',1)[1][:26]:26} [{bucket:10}] NO READABLE TIMES"); continue
            # Each model returns RAW per-school rows (facts); we never let it compute minutes/mode.
            model_rows = {}
            for k, ex in voters.items():
                try: model_rows[k] = ex.extract(txt, did, d["dir"], "").get("schedules", [])
                except Exception: model_rows[k] = []
            try: judge_rows = {"deepseek-v3.2": judge_ex.extract(txt, did, d["dir"], "").get("schedules", [])}
            except Exception: judge_rows = {}
            # Council agrees on per-school (start,end) FACTS; code computes gross + mode.
            accepted, unresolved = A.consensus_school_facts(model_rows, judge_rows)
            bands = A.district_bands_from_facts(accepted)
            charter = S.charter_lookup(did)   # TAG charters from NCES (REQ-060) — never exclude
            # PRIMARY = per-school facts (what the user verifies against the source);
            # band rollup is DERIVED context (deterministic mode over verified schools).
            prop = {}
            for b, v in bands.items():
                for s in v["schools"]:
                    s["is_charter"] = charter.get(s["school"], "unknown")   # 'Yes'/'No'/'unknown' (not in NCES LEA)
                prop[b] = {"schools": v["schools"],          # <- verify each school's start/end here
                           "_derived_band_gross": v["gross_minutes"], "_derived_start": v["start_time"],
                           "_derived_end": v["end_time"], "_n_schools": v["n_schools"], "_method": v["method"]}
            out.append({"district_id": did, "dir": d["dir"], "topology": bucket,
                        "proposal": prop, "unresolved": unresolved})
            cells = " ".join(f"{b[:3]}:{len(prop[b]['schools'])}sch->{prop[b]['_derived_band_gross']}" for b in A.BANDS if b in prop) or "(none)"
            print(f"{did} {d['dir'].split('_',1)[1][:24]:24} [{bucket:10}] {cells}  unresolved={len(unresolved)}")
    (R / "gt_proposals.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote {R/'gt_proposals.json'} ({len(out)} districts) — for human verification")

if __name__ == "__main__":
    main()
