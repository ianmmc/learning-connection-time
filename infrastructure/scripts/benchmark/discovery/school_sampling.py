"""Per-district, per-band school counts + statistical sampling envelope from NCES ccd_sch.

Bands: elementary / middle / high. A school can serve MULTIPLE bands (a K-8 covers
elementary AND middle), so we classify by GRADE SPAN (GSLO-GSHI), not the coarse LEVEL field.
For each (district, band) we report the school count N and the finite-population sample size n
for 95% confidence / 5% margin (worst-case p=0.5). Small N censuses naturally.

Usage: school_sampling.py [--year 2024_25] [--ids id,id,...] [--summary]
"""
import csv, sys, math, json, argparse
from pathlib import Path
from collections import defaultdict

GRADE_ORD = {g:i for i,g in enumerate(
    ["PK","KG","01","02","03","04","05","06","07","08","09","10","11","12"])}
# normalize NCES grade tokens
def norm(g):
    g=(g or "").strip().upper()
    return {"PREKINDERGARTEN":"PK","K":"KG","KINDERGARTEN":"KG"}.get(g, g)

# band coverage by grade number: elementary K-5, middle 6-8, high 9-12 (PK counts as elementary)
BANDS = {"elementary": range(GRADE_ORD["PK"], GRADE_ORD["05"]+1),
         "middle":     range(GRADE_ORD["06"], GRADE_ORD["08"]+1),
         "high":       range(GRADE_ORD["09"], GRADE_ORD["12"]+1)}

def bands_for(gslo, gshi):
    """Which bands a school's grade span overlaps. Returns set; {} if ungraded/unknown (M-M, etc.)."""
    lo, hi = GRADE_ORD.get(norm(gslo)), GRADE_ORD.get(norm(gshi))
    if lo is None or hi is None or hi < lo: return set()
    span = set(range(lo, hi+1))
    return {b for b, rng in BANDS.items() if span & set(rng)}

def sample_size(N, z=1.96, e=0.05, p=0.5):
    """95/5 finite-population-corrected sample size; censuses small N."""
    if N <= 0: return 0
    n0 = (z*z*p*(1-p)) / (e*e)          # ~384.16
    n = n0 / (1 + (n0-1)/N)
    return min(N, math.ceil(n))

OPEN = {"1","Open","open"}  # SY_STATUS 1 = open (filter closed/inactive)

def load(year):
    f = Path(f"data/raw/federal/nces-ccd/{year}/ccd_sch_029_{year[2:4]}{year[7:9]}_w_1a_073025.csv")
    if not f.exists():  # fall back to glob
        f = next(Path(f"data/raw/federal/nces-ccd/{year}").glob("ccd_sch_029_*_w_1a_*.csv"))
    # (district_id) -> band -> count of schools serving that band
    counts = defaultdict(lambda: defaultdict(int))
    with open(f, encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if row.get("SY_STATUS","") not in OPEN: continue
            did = row.get("LEAID","").zfill(7)
            for b in bands_for(row.get("GSLO"), row.get("GSHI")):
                counts[did][b] += 1
    return counts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="2024_25")
    ap.add_argument("--ids", default="")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    counts = load(a.year)

    if a.ids:
        man = {d["district_id"]: d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]} if Path("data/benchmark/ground_truth_manifest.json").exists() else {}
        for did in a.ids.split(","):
            did = did.zfill(7); c = counts.get(did, {})
            name = man.get(did,{}).get("district_name","?")
            row = " ".join(f"{b[:4]}={c.get(b,0)}(n{sample_size(c.get(b,0))})" for b in ("elementary","middle","high"))
            tot_n = sum(sample_size(c.get(b,0)) for b in BANDS)
            print(f"{did} {name[:28]:28} {row}  | calls/district(census-sample)={tot_n}")
        return

    # corpus-wide envelope
    nd = len(counts)
    band_school_calls = defaultdict(int); districts_with = defaultdict(int)
    census_total = 0; sample_total = 0
    dist_sample_calls = []
    for did, c in counts.items():
        dcalls = 0
        for b in BANDS:
            N = c.get(b, 0)
            if N: districts_with[b]+=1
            census_total += N
            s = sample_size(N); sample_total += s; band_school_calls[b]+=s; dcalls += s
        dist_sample_calls.append(dcalls)
    dist_sample_calls.sort()
    med = dist_sample_calls[len(dist_sample_calls)//2] if dist_sample_calls else 0
    p95 = dist_sample_calls[int(len(dist_sample_calls)*0.95)] if dist_sample_calls else 0
    print(f"districts with >=1 graded school: {nd}")
    print(f"total open graded-school band-memberships (census): {census_total:,}")
    print(f"total band-extractions if 95/5 sampled:             {sample_total:,}  ({100*sample_total/census_total:.0f}% of census)")
    print(f"per-band sampled calls: " + ", ".join(f"{b}={band_school_calls[b]:,} (in {districts_with[b]:,} dists)" for b in BANDS))
    print(f"per-district sampled calls (3 bands): median={med}  p95={p95}  max={max(dist_sample_calls) if dist_sample_calls else 0}")

if __name__ == "__main__":
    main()
