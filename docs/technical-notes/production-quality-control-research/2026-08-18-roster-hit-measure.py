"""#826 — roster_school_names_hit: measure the ACTUAL defect before fixing it.

RERUNNABLE, READ-ONLY. Imports the LIVE functions (`build_signals.text_bases`,
`school_match.norm_school`) and replays the real roster-hit computation over the real corpus.
Nothing is written; no DB row is touched.

    python3 docs/technical-notes/production-quality-control-research/2026-08-18-roster-hit-measure.py [--limit N]

R1  reproduce TODAY's count, and locate the defect precisely. The issue says the signal "matches
    roster names without going through norm_school" — but build_signals.py:1545 already normalizes
    the ROSTER side. What is un-normalized is the DOCUMENT side (`all_lc = all_text.lower()`), so a
    normalized key ('st marys') is searched for inside raw lowercased text ("st. mary's"). The
    asymmetry, not the absence, is the bug. R1 confirms which.
R2  the three districts the issue pins (Memphis 4700148 -> 27, Broward 1200180 -> 42,
    Orange 1201440 -> 36) — do they reach those numbers under the candidate fix?
R3  the district-name COLLISION the issue warns about: roster entries normalizing to the
    district's own normalized name, which would make every mention of the district a school hit.
R4  corpus-wide before/after distribution, and the tier-change blast radius.
R5  Northwestern 1730540:bcd9c539fb — the 886-page policy book reading 3,211 clock times in a
    3-school district. Does a roster-anchored count actually separate it from a real hub?
"""
import argparse
import json
import re
from collections import Counter

from sqlalchemy import text

from infrastructure.acquisition.common import paths as P
from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.common import school_match as SM
from infrastructure.acquisition.common.school_match import norm_school
from infrastructure.acquisition.stage5_filter import build_signals as BS

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=0)
args = ap.parse_args()

# The issue's filed targets were 27/42/36 — NOT reproducible: its "hits today" column matched RAW
# school names against raw text, a computation the code has never performed (the roster side always
# went through norm_school), so its before/after came from two different bases. Ian re-specified P1
# on 2026-08-19 to the counts measured under the LIVE functions. The filed figures stay here as
# FILED so a re-run can still show how far off the original premise was.
FILED = {"4700148": 27, "1200180": 42, "1201440": 36}
PINNED = {"4700148": 23, "1200180": 22, "1201440": 29}      # P1 as re-specified (Ian, 2026-08-19)


def hits_today(roster_norm, all_text):
    """The PRE-#826 behaviour, kept here as the baseline: normalized keys searched inside raw
    lowercased text. Reconstructed deliberately (not imported) — this is the thing being compared
    against, and it no longer exists in the codebase."""
    lc = all_text.lower()
    return sum(1 for rn in roster_norm if rn and rn in lc)


def hits_normalized(roster_old, all_text):
    """Half one IN ISOLATION: normalized document, UNguarded roster keys. Reported separately
    because the two halves move the number in opposite directions and a combined figure hides
    both — normalization can only ADD matches, the collision guard can only REMOVE them."""
    return sum(1 for rn in roster_old if rn and rn in SM.norm_document(all_text))


def hits_fixed(roster_norm, all_text):
    """Both halves — the LIVE functions. Imported, never re-expressed."""
    doc = SM.norm_document(all_text)
    return sum(1 for rn in roster_norm if rn and rn in doc)


with session_scope() as s:
    # district_dir is the on-disk name ('4700148_memphis...'), NOT the bare id — the first run of
    # this script assumed the id and scanned 0 records. It said NOTHING MEASURED rather than
    # printing a green zero, which is the only reason the mistake was visible.
    rows = s.execute(text(
        "SELECT DISTINCT district_id, district_dir FROM record ORDER BY district_id")).fetchall()
    districts = [(r[0], r[1]) for r in rows]
    if args.limit:
        districts = districts[:args.limit]
    dmeta = dict(s.execute(text("SELECT district_id, name FROM district")).fetchall())

print(f"districts: {len(districts)}\n")

per_district = {}
deltas = []
collisions = []
total_before = total_mid = total_after = 0
monotone_violations = []
n_records = 0

for i, (did, ddir_name) in enumerate(districts):
    if i % 25 == 0:
        print(f"  ...{i}/{len(districts)}", flush=True)
    ddir = P.RAW_CAPTURES / ddir_name
    dj, cj, pj = ddir / "discovery.json", ddir / "captures.json", ddir / "processed.json"
    if not (dj.exists() and pj.exists()):
        continue
    disc = json.loads(dj.read_text())
    names = [sc.get("school", "") for sc in disc.get("schools", [])]
    roster_old = sorted({rn for sc in names if len(rn := norm_school(sc)) >= 4})   # pre-#826
    roster_norm = SM.roster_match_keys(names, disc.get("name"))                    # LIVE
    # R3: which roster entries collapse onto the DISTRICT's own normalized name?
    dnorm = norm_school(disc.get("name") or dmeta.get(did) or "")
    collide = [rn for rn in roster_old if rn and rn == dnorm]
    if collide:
        collisions.append((did, dmeta.get(did), dnorm, len(roster_norm), collide))
    processed = {r["hash"]: r for r in json.loads(pj.read_text())}
    d_before = d_mid = d_after = 0
    for h, prec in processed.items():
        rdir = ddir / "captures" / h
        if not rdir.exists():
            continue
        mp = rdir / "page.main.txt"
        main_text = mp.read_text(errors="replace") if mp.exists() else None
        try:
            tb = BS.text_bases(rdir, prec.get("texts", []), main_text)
        except Exception:
            continue
        at = tb["all_text"]
        if not at:
            continue
        b = hits_today(roster_old, at)
        m = hits_normalized(roster_old, at)          # normalization only
        a = hits_fixed(roster_norm, at)              # normalization + collision guard
        n_records += 1
        total_before += b
        total_mid += m
        total_after += a
        if m < b:
            monotone_violations.append((did, h, b, m))
        d_before, d_mid, d_after = max(d_before, b), max(d_mid, m), max(d_after, a)
        if a != b:
            deltas.append((did, h, b, a, len(roster_norm)))
    per_district[did] = (d_before, d_mid, d_after, len(roster_norm))

print("\n" + "=" * 78)
print("R1  where the defect actually is")
print(f"    records scanned: {n_records:,}")
print(f"    (a) TODAY               raw-lowercase doc, unguarded keys : {total_before:,}")
print(f"    (b) + doc normalization only                              : {total_mid:,}"
      f"   ({total_mid - total_before:+,})")
print(f"    (c) + district-name collision guard  (SHIPPED)            : {total_after:,}"
      f"   ({total_after - total_mid:+,})")
print(f"    records whose final count changes: {len(deltas):,}")
print(f"    monotonicity of (b): records where normalization LOST a match: "
      f"{len(monotone_violations)}"
      f"   {'<-- BLOCKER' if monotone_violations else '(0 — as it must be: same keys, strictly more findable doc)'}")
print("    The roster side ALWAYS went through norm_school (build_signals.py:1545) — the issue's")
print("    premise that it did not is false. The un-normalized side was the DOCUMENT.")

print("\nR2  the three pinned districts")
for did, want in PINNED.items():
    if did not in per_district:
        print(f"    {did}: NOT IN CORPUS  <-- cannot verify")
        continue
    b, m, a, rsize = per_district[did]
    mark = "" if a == want else f"   <-- P1 target {want}, MEASURED {a}"
    print(f"    {did} {str(dmeta.get(did))[:26]:<26} roster={rsize:>4}  today={b:>3}"
          f"  +norm={m:>3}  shipped={a:>3}  (filed {FILED[did]}){mark}")

print("\nR3  district-name collision (a roster entry normalizing to the district's own name)")
print(f"    districts affected: {len(collisions)}")
for did, nm, dnorm, rsize, cols in collisions[:12]:
    print(f"    {did} {str(nm)[:30]:<30} dnorm={dnorm!r:<22} roster={rsize:<4} colliding={cols}")
if not collisions:
    print("    (none in this corpus — the guard is still required: it is a property of the RULE,")
    print("     not of today's sample, and a small district added tomorrow would trip it.)")

print("\nR4  distribution shift")
bb = Counter(v[0] for v in per_district.values())
aa = Counter(v[2] for v in per_district.values())
print(f"    districts with max-record hits == 0 : today {bb[0]:>4}   shipped {aa[0]:>4}")
print("    (the rise is the guard zeroing single-school districts whose one school shares the")
print("     district name — inert: both consumers threshold at >=2 (hub) / >=3 (homepage), which")
print("     a 1-school roster could never reach, so the count was unusable before and absent now.)")
gained = [(d, v[0], v[2]) for d, v in per_district.items() if v[2] > v[0]]
lost = [(d, v[0], v[2]) for d, v in per_district.items() if v[2] < v[0]]
print(f"    districts gaining hits: {len(gained)}   losing hits: {len(lost)}")
print("    (losses are the collision guard working, NOT a regression — see the monotonicity")
print("     check in R1, which is the assertion that normalization alone never loses a match.)")
for d, b, a in sorted(gained, key=lambda x: x[2] - x[1], reverse=True)[:10]:
    print(f"      {d} {str(dmeta.get(d))[:28]:<28} {b:>3} -> {a:>3}")

print("\nR5  Northwestern 1730540 — the scope-error case")
nw = per_district.get("1730540")
if nw:
    print(f"    roster size {nw[3]} · max-record roster hits today={nw[0]} shipped={nw[2]}")
    print("    A 3-school district cannot produce a high roster-hit count no matter how many clock")
    print("    times its policy book holds — which is exactly why the hit count, not n_times,")
    print("    is the signal that separates a scope error from a real hub.")
else:
    print("    not in corpus")

print()
if not n_records:
    print("VERDICT: NOTHING MEASURED — no record produced an all_text basis.")
elif monotone_violations:
    print("VERDICT: REVIEW REQUIRED — normalization LOST a match; that half must be monotone.")
else:
    hit = [d for d in PINNED if d in per_district and per_district[d][2] == PINNED[d]]
    print(f"VERDICT: mechanism CONFIRMED (R1). {len(hit)}/{len(PINNED)} pinned districts reach the")
    print("         P1 target — see R2. Reconciliation (2026-08-18): the issue's 'hits today' column")
    print("         matched RAW school names vs raw text, a computation the code has never performed;")
    print("         its before/after came from two different bases, so the filed 27/42/36 were not")
    print("         achievable. P1 was RE-SPECIFIED to the measured 23/22/29 (Ian, 2026-08-19).")
    if len(hit) != len(PINNED):
        print("         <-- BLOCKER: a pinned district no longer reaches its re-specified target.")
