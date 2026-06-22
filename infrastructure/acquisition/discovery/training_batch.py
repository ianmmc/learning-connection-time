"""Pick a stratified, seeded, reproducible batch of N untouched NCES districts for the
discovery+capture TRAINING loop (per-school-acquire-training skill, steps 1-5 only).

Pool = NCES 2024-25 LEAs with a website + >=1 graded open school, EXCLUDING every district we've
already touched (the 64 hand-collected, prior discovery/per_school runs, the 41 GT manifest).
Stratified by size (band-membership count): ~2 large, ~6 mid, ~4 small per 12, so each batch
spans the hub/per-school spectrum. Seed = batch number, so batches are logged + repeatable.

Usage: training_batch.py <batch_number> [--n 12]
Writes data/acquisition/training_batches/batch_<NN>/batch.json (the roster to run).
"""
import csv, json, sys, random, argparse
from pathlib import Path
sys.path.insert(0, "infrastructure/acquisition/discovery")
import school_sampling as S
from discover import host_of

LEA = "data/raw/federal/nces-ccd/2024_25/ccd_lea_029_2425_w_1a_073025.csv"
OUT = Path("data/acquisition/training_batches")
# size strata by band-membership count (from observed quartiles: q1=2, med=4, q3=6)
def stratum(n): return "large" if n >= 12 else "mid" if n >= 4 else "small"
MIX = {"large": 2, "mid": 6, "small": 4}   # per 12

def touched_ids():
    t = set()
    raw = Path("data/raw/bell_schedule_pdfs")
    if raw.exists():
        for st in raw.iterdir():
            if st.is_dir():
                for dd in st.iterdir():
                    if dd.is_dir(): t.add(dd.name.split("_")[0].zfill(7))
    for base in ("data/acquisition/discovery", "data/acquisition/per_school"):
        p = Path(base)
        if p.exists():
            t |= {d.name.zfill(7) for d in p.iterdir() if d.is_dir() and d.name.isdigit()}
    for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]:
        t.add(d["district_id"].zfill(7))
    # exclude prior training batches too
    if OUT.exists():
        for b in OUT.glob("batch_*/batch.json"):
            for r in json.loads(b.read_text())["districts"]: t.add(r["district_id"].zfill(7))
    return t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", type=int)
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args()
    touched = touched_ids()
    counts = S.load("2024_25")
    pool = {"large": [], "mid": [], "small": []}
    with open(LEA, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            did = row.get("LEAID", "").zfill(7)
            if did in touched: continue
            web = row.get("WEBSITE", "") or ""
            c = counts.get(did, {}); nsch = sum(c.values())
            if web and nsch > 0:
                pool[stratum(nsch)].append({"district_id": did, "name": row.get("LEA_NAME", ""),
                                            "state": row.get("ST", ""), "domain": host_of(web if "//" in web else "http://"+web),
                                            "band_memberships": nsch, "stratum": stratum(nsch),
                                            "band_counts": {b: c.get(b, 0) for b in ("elementary","middle","high")}})
    rng = random.Random(a.batch)   # seed = batch number -> reproducible
    picked = []
    for strat, k in MIX.items():
        avail = pool[strat]; rng.shuffle(avail)
        picked += avail[:k]
    # top up if a stratum was short
    if len(picked) < a.n:
        rest = [d for s in pool.values() for d in s if d not in picked]; rng.shuffle(rest)
        picked += rest[: a.n - len(picked)]
    picked = picked[: a.n]
    bdir = OUT / f"batch_{a.batch:02d}"; bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "batch.json").write_text(json.dumps(
        {"batch": a.batch, "seed": a.batch, "n": len(picked), "mix": MIX,
         "config": {"waves": "claude_websearch->openrouter_gpt4o-mini-search", "perplexity": False,
                    "capture": "tiered_text_then_screenshot_ocr"},
         "districts": picked}, indent=2))
    print(f"batch_{a.batch:02d}: {len(picked)} districts (seed={a.batch})")
    for d in picked:
        print(f"  [{d['stratum']:5}] {d['district_id']} {d['name'][:30]:30} {d['state']} dom={d['domain']:24} bands={d['band_counts']}")
    print(f"\nwrote {bdir/'batch.json'} — run via per-school-acquire-training skill (steps 1-5)")

if __name__ == "__main__":
    main()
