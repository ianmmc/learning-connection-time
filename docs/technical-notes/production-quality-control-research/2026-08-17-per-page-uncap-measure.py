"""Pass A — verification for removing the 60-page per-page scan cap.

RERUNNABLE, READ-ONLY. Imports the LIVE functions (never re-implements the rule — PR #705 review
[4]: a hand copy silently drifts from what the scorer actually stores).

    python3 docs/technical-notes/production-quality-control-research/2026-08-17-per-page-uncap-measure.py [--limit N]

A1  For pages <= the old cap, the recomputed per-page n_times must match the STORED value EXACTLY.
    This is the load-bearing check: if it holds, every non-capped record's `pages` (and therefore
    harvest_pages / is_handbook / lf_no_times / tier) is unchanged BY CONSTRUCTION, and only the
    capped docs need downstream analysis.
A2  The capped docs: pages/times before vs after, and harvest_pages before vs after — flagging
    every doc whose harvest set SHRANK (a bigger peak past p60 raises cut = max(6, peak*0.5)).
A3  is_handbook before vs after. Expected delta ZERO, and provably so: is_handbook_doc only tests
    `n_pages > 1`, and a capped doc already had 60 > 1. Asserted, not assumed.
A4  For capped docs, whether lf_no_times' arming flips (it is disarmed by a non-empty harvest_pages)
    — the one way this change could suppress a record out of dispatch.
A5  Wall-clock old (per-page loop) vs new (one call), and peak RSS on the largest doc.
"""
import argparse
import json
import resource
import time
from collections import Counter

from sqlalchemy import text

from infrastructure.acquisition.common import paths as P
from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.stage5_filter import build_signals as BS

OLD_CAP = 60          # the constant this change removes; kept here to scope A1's comparison

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=0)
args = ap.parse_args()


def load():
    with session_scope() as s:
        recs = s.execute(text(
            "SELECT rec_key, district_id, district_dir, signals_json FROM record")).fetchall()
        pdfs = dict(s.execute(text(
            "SELECT rec_key, MIN(filename) FROM representation "
            "WHERE file_kind='pdf' AND filename IS NOT NULL GROUP BY rec_key")).fetchall())
    out = []
    for rk, did, ddir, sj in recs:
        try:
            sig = json.loads(sj or "{}")
        except Exception:
            continue
        if not sig.get("pages"):
            continue
        fn = pdfs.get(rk)
        if not fn:
            continue
        pdf = P.RAW_CAPTURES / ddir / "captures" / rk.split(":")[-1] / fn
        if pdf.exists():
            out.append((rk, did, sig, pdf))
    return out


pop = load()
if args.limit:
    pop = pop[:args.limit]
print(f"records with a stored per-page signal and a readable PDF: {len(pop)}\n")

a1_checked = a1_mismatch = 0
mismatches = []
capped, timing = [], []
biggest = (0, None)

for i, (rk, did, sig, pdf) in enumerate(pop):
    if i % 100 == 0:
        print(f"  ...{i}/{len(pop)}", flush=True)
    stored = sig["pages"]
    t0 = time.time()
    texts_ = BS.pdf_page_texts(pdf)
    t_new = time.time() - t0
    fresh = BS.page_time_signals(texts_)

    # ---- A1: exact per-page agreement below the old cap ----
    for old in stored:
        p = old["page"]
        if p > OLD_CAP or p > len(fresh):
            continue
        a1_checked += 1
        if fresh[p - 1]["n_times"] != old["n_times"]:
            a1_mismatch += 1
            if len(mismatches) < 20:
                mismatches.append((rk, p, old["n_times"], fresh[p - 1]["n_times"],
                                   (texts_[p - 1] or "")[:160].replace("\n", " ")))

    if len(fresh) > biggest[0]:
        biggest = (len(fresh), rk)

    # ---- A2/A3/A4: only the capped docs can change ----
    if len(stored) >= OLD_CAP:
        hp_old = sig.get("harvest_pages") or []
        hp_new = BS.harvest_schedule_pages(fresh)
        capped.append(dict(
            rk=rk, did=did,
            pages_old=len(stored), pages_new=len(fresh),
            times_old=sum(p["n_times"] for p in stored),
            times_new=sum(p["n_times"] for p in fresh),
            hp_old=hp_old, hp_new=hp_new,
            hp_shrank=bool(set(hp_old) - set(hp_new)),
            # lf_no_times is DISARMED by a non-empty harvest_pages; a flip to empty could suppress
            # the record out of dispatch entirely (detectors.py).
            armed_old=not hp_old, armed_new=not hp_new,
            instr_pages=[p["page"] for p in fresh if p["instr"] and not p["n_times"]]))
        t0 = time.time()
        for p in range(1, min(len(fresh), OLD_CAP) + 1):
            BS.pdf_page_text(pdf, p)
        timing.append((rk, len(fresh), time.time() - t0, t_new))

print("\n" + "=" * 78)
print(f"A1  per-page n_times agreement below the old {OLD_CAP}-page cap")
print(f"    pages compared : {a1_checked}")
print(f"    MISMATCHES     : {a1_mismatch}"
      f"   {'<-- BLOCKER' if a1_mismatch else '(exact — the non-capped corpus is unchanged by construction)'}")
for rk, p, o, n, snip in mismatches:
    print(f"      {rk} p{p}: stored={o} fresh={n} | {snip}")

print(f"\nA2  capped docs (stored page count >= {OLD_CAP}): {len(capped)}")
gain = sum(c["times_new"] - c["times_old"] for c in capped)
print(f"    pages recovered : {sum(c['pages_new'] - c['pages_old'] for c in capped)}")
print(f"    times recovered : {gain}")
shrank = [c for c in capped if c["hp_shrank"]]
print(f"    harvest_pages SHRANK on: {len(shrank)} doc(s)"
      f" {'(expected: a bigger peak past p60 raises the cut)' if shrank else ''}")
for c in sorted(capped, key=lambda x: -(x["times_new"] - x["times_old"]))[:12]:
    flag = "  HP-SHRANK" if c["hp_shrank"] else ""
    print(f"      {c['rk']:26} pages {c['pages_old']:4}->{c['pages_new']:4}"
          f"  times {c['times_old']:5}->{c['times_new']:5}"
          f"  hp {len(c['hp_old'])}->{len(c['hp_new'])}{flag}")

print(f"\nA3  is_handbook delta: 0 — provable, not sampled. is_handbook_doc only tests `n_pages > 1`,")
print(f"    and every capped doc already had {OLD_CAP} > 1, so a larger count cannot flip it.")
bad = [c for c in capped if not (c["pages_new"] >= c["pages_old"] >= OLD_CAP)]
assert not bad, f"A3 premise violated (a capped doc lost pages): {bad}"
print("    premise asserted for every capped doc: pages_new >= pages_old >= cap  OK")

# DIRECTION is the whole question, so count the two directions separately — a flip count alone
# would read a mass RECOVERY as identically alarming to a mass suppression.
#   armed -> disarmed : the record had no harvest_pages only because its times lived past the cap.
#                       lf_no_times stops suppressing it. This is the fix working.
#   disarmed -> armed : the record LOSES its harvest_pages and lf_no_times starts suppressing it.
#                       That is the one way this change can drop a district. Any occurrence blocks.
recovered = [c for c in capped if c["armed_old"] and not c["armed_new"]]
suppressed = [c for c in capped if not c["armed_old"] and c["armed_new"]]
print(f"\nA4  lf_no_times arming, among capped docs")
print(f"    RECOVERED (armed -> disarmed, times found past the cap): {len(recovered)}")
for c in recovered:
    print(f"      {c['rk']:26} harvest_pages {c['hp_old']} -> {c['hp_new']}"
          f"   times {c['times_old']} -> {c['times_new']}")
print(f"    NEWLY SUPPRESSED (disarmed -> armed): {len(suppressed)}"
      f"   {'<-- BLOCKER' if suppressed else '(none — the change cannot drop a record this way)'}")
for c in suppressed:
    print(f"      {c['rk']}: harvest_pages {c['hp_old']} -> {c['hp_new']}")
instr = [c for c in capped if c["instr_pages"]]
print(f"    capped docs carrying an instructional-declaration page with ZERO times: {len(instr)}"
      f"   (PR 2's `instr` floor term protects these)")
for c in instr[:5]:
    print(f"      {c['rk']}: pages {c['instr_pages'][:8]}")

print("\nA5  wall-clock, per-page loop vs one whole-doc call (capped docs)")
if timing:
    tot_old = sum(t[2] for t in timing)
    tot_new = sum(t[3] for t in timing)
    print(f"    per-page loop (first {OLD_CAP} pages only): {tot_old:.1f}s")
    print(f"    one call (the WHOLE document)            : {tot_new:.1f}s"
          f"   -> {tot_old / max(tot_new, 1e-9):.1f}x faster while reading strictly more")
    for rk, n, told, tnew in sorted(timing, key=lambda x: -x[1])[:5]:
        print(f"      {rk:26} {n:4}pp  loop(60pp)={told:5.2f}s  onecall(all)={tnew:5.2f}s")
print(f"    largest document seen: {biggest[1]} at {biggest[0]} pages")
print(f"    peak RSS this process: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6:.0f} MB")

print("\nVERDICT:", "PASS" if not a1_mismatch and not suppressed else "REVIEW REQUIRED")
