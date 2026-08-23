#!/usr/bin/env python3
"""#717 — gate@6 has no already-extracted delta: how much does re-dispatch re-buy?

READ-ONLY. Rerunnable. Imports the LIVE composition function
(`stage6_dispatch.district_release_input`) rather than re-spelling the send rule — #879's rule,
learned when a measurement script's hand-rolled `endswith` published a wrong corpus figure. The
prior-send set is read from the IMMUTABLE handoff receipts on disk, because the `extraction` table
is per (district, handoff) and cannot answer "which REP was bought" at all.

THE QUESTION (#717). gate@6 composition builds from the CURRENT sendable set and never subtracts
reps already extracted in a prior production run. Stage 3 has exactly this delta discipline for
capture (REQ-172, `seedFromPriorCaptures`); the dispatch layer has no sibling. So: which reps would
a dispatch re-buy today, how much has the campaign already paid for duplicates, and — the live
question — what would `batch_00043` re-buy if it were dispatched at gate@6 right now?

GRAIN. A "rep" here is `(rec_key, file)` — the identity a receipt's `records[].reps[].file` carries
and the one `school_fact.rec_key/source_file` records. District grain is useless for this question:
a 7->6 alternate-rep re-dispatch (REQ-118) re-dispatches the DISTRICT *on purpose*, sending a
DIFFERENT rep. Counting districts would score that deliberate design as waste — the #841 lesson,
"before calling a divergence a bug, check whether it is INTENTIONAL". Only a repeated
(rec_key, file) is duplicate work.

FOUR PREDICATES, REPORTED SIDE BY SIDE (the #826 pattern — a combined figure would hide that they
disagree, and the disagreement IS the design decision):

  A  sent-and-ran   the rep was sent in a prior PRODUCTION handoff that has an `extraction` row.
  B  yielded-facts  the rep has `school_fact` rows. STRICTLY NARROWER than A: a rep that ran clean
                    and found nothing has no facts, but re-buying it is still deterministic waste.
  C  clean-run      A, minus every rep from a run whose `extraction.n_errors > 0`. An errored run
                    deserves a retry; this keeps those reps sendable. Errors are recorded at the
                    (district, handoff) grain, NOT per rep, so one error re-admits ALL of that
                    run's reps.
  D  per-rep        A, minus reps that BOTH came from an errored run AND yielded no facts.
     (RECOMMENDED)  Per-rep precise where evidence exists (a fact PROVES that rep succeeded),
                    falling back to the run-level signal only where it does not.

C WAS THIS SCRIPT'S FIRST PROPOSAL AND THE MEASUREMENT OVERTURNED IT — the house pattern. Because
`n_errors` is per (district, handoff), C re-admits every rep of a run in which any ONE rep errored:
`3904378` goes A=7 -> C=0, `4222350` A=6 -> C=0. Measured, C needlessly re-buys 32 reps across 11
districts that demonstrably succeeded. D re-admits exactly the 8 reps corpus-wide that both errored
and yielded nothing — the true retry population — and is what the implementation should use.

WHAT THIS DOES *NOT* MEASURE. Per-rep cost is not recorded anywhere: `extraction.cost_usd` is one
number per (district, handoff). C2's duplicate spend is therefore PRORATED (cost_usd x dup/n_reps),
and is an attribution, not a receipt. It is also a FLOOR on the waste, not a forecast of savings:
the corpus is 27 benchmark districts and a partial campaign, so the fleet-scale number this issue
is really about cannot be extrapolated from it.

REPLAY ROWS. The #716 replay re-persisted facts from receipts with `n_calls = 0, cost_usd = 0` and
`run_kind = 'production'`. Those rows prove a rep was extracted (so they COUNT for the delta) while
buying no council (so they must NOT count as spend). C2 excludes them explicitly; a measurement
that let them through would report replays as duplicate purchases.

  C1  the four predicates side by side across the corpus, and where they disagree.
  C2  duplicate spend the campaign has ALREADY paid, prorated, replays excluded.
  C3  THE LIVE QUESTION — batch_00043 composed through the real `district_release_input` today.
  C4  the acceptance specimens: districts that compose to ZERO new reps (the issue's "must fail
      today" case), and the strand-risk check — would the delta ever empty a district that has
      genuinely new work?

Usage:  python3 docs/technical-notes/production-quality-control-research/2026-08-23-already-extracted-delta-measure.py
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import stage6_dispatch as D6

NOTHING = "NOTHING MEASURED"

# The 7 included districts of batch_00043 (the #620 recovery batch). Union Hill is excluded
# upstream (0 slot_assignment), so it never composes and is not listed here.
BATCH_00043 = ["0509000", "0626910", "0902790", "1906540", "3200480", "3631800", "5605302"]


def load_extraction_index():
    """(handoff_hash, district_id) -> dict of the run's aggregates, production runs only."""
    idx = {}
    with gdb.session_scope() as s:
        rows = s.execute(text(
            "SELECT handoff_hash, district_id, n_errors, n_calls, cost_usd, n_reps, created_at "
            "FROM extraction WHERE run_kind = 'production'"))
        for h, d, err, calls, cost, nreps, at in rows:
            cur = idx.setdefault((h, d), {"n_errors": 0, "n_calls": 0, "cost_usd": 0.0,
                                          "n_reps": 0, "created_at": at})
            cur["n_errors"] += err or 0
            cur["n_calls"] += calls or 0
            cur["cost_usd"] += float(cost or 0.0)
            cur["n_reps"] = max(cur["n_reps"], nreps or 0)
    return idx


def load_fact_reps():
    """district_id -> {(rec_key, source_file)} that produced at least one school_fact row."""
    out = defaultdict(set)
    with gdb.session_scope() as s:
        for d, rk, sf in s.execute(text(
                "SELECT district_id, rec_key, source_file FROM school_fact")):
            out[d].add((rk, sf))
    return out


def load_receipts(ex_idx):
    """Walk the immutable receipts once. Returns:
         sends[(hash, did)] -> {(rec_key, file)}   every rep SENT, for a run that actually ran
         order[hash]        -> created_at          for chronological replay
    """
    sends, order = defaultdict(set), {}
    for path in sorted(glob.glob("data/acquisition/handoffs/handoff_*.json")):
        try:
            j = json.load(open(path))
        except Exception:  # noqa: BLE001 — a malformed receipt must not abort the sweep
            continue
        hh = j.get("handoff_hash")
        order[hh] = j.get("created_at") or path
        for d in j.get("districts") or []:
            did = d.get("district_id")
            if (hh, did) not in ex_idx:
                continue          # composed but never run — bought nothing
            for rec in d.get("records") or []:
                if rec.get("decision") != "send":
                    continue
                for rp in rec.get("reps") or []:
                    sends[(hh, did)].add((rec["rec_key"], rp.get("file")))
    return sends, order


def predicates(sends, ex_idx, fact_reps):
    """district -> (A, B, C, D) sets of already-extracted (rec_key, file).

    D is the recommended one: a rep is already-extracted unless it BOTH came from an errored run
    AND left no fact behind. A fact is per-rep PROOF that this rep succeeded, so it outranks the
    run-level error flag; absent that proof, an errored run means the rep may never have been read.
    """
    A, C, D = defaultdict(set), defaultdict(set), defaultdict(set)
    for (hh, did), reps in sends.items():
        clean = not ex_idx[(hh, did)]["n_errors"]
        A[did] |= reps
        if clean:
            C[did] |= reps
        for r in reps:
            if clean or r in fact_reps.get(did, set()):
                D[did].add(r)
    return A, fact_reps, C, D


def c1_predicate_comparison(A, B, C, D):
    print("\n" + "=" * 78)
    print("C1  the four predicates, side by side")
    print("=" * 78)
    dids = sorted(set(A) | set(C) | set(D))
    if not dids:
        print(f"  {NOTHING}: no production handoff receipts pair with an extraction row.")
        return
    ta = sum(len(A[d]) for d in dids)
    tb = sum(len(B.get(d, set()) & A[d]) for d in dids)
    tc = sum(len(C[d]) for d in dids)
    td = sum(len(D[d]) for d in dids)
    print(f"  districts with >=1 already-extracted rep : {len([d for d in dids if A[d]])}")
    print(f"  A  sent-and-ran   : {ta} reps   (too broad — strands genuine retries)")
    print(f"  B  yielded-facts  : {tb} reps   (subset of A; the gap ran clean or errored)")
    print(f"  C  clean-run      : {tc} reps   (too blunt — see below)")
    print(f"  D  per-rep        : {td} reps   <-- RECOMMENDED")
    worse = [d for d in dids if len(D[d]) > len(C[d])]
    lost = sum(len(D[d]) - len(C[d]) for d in worse)
    print("\n  WHY NOT C: `n_errors` is per (district, handoff), so one errored rep re-admits the")
    print(f"  whole run. C needlessly re-buys {lost} reps across {len(worse)} districts that")
    print("  demonstrably succeeded (they left facts):")
    for d in worse[:12]:
        print(f"    {d}  A={len(A[d]):3d}  C={len(C[d]):3d}  D={len(D[d]):3d}"
              f"  (+{len(D[d]) - len(C[d])} correctly suppressed by D)")
    retry = sum(len(A[d]) - len(D[d]) for d in dids)
    ndist = len([d for d in dids if len(A[d]) != len(D[d])])
    print(f"\n  D re-admits {retry} rep(s) across {ndist} district(s) — errored AND no facts,")
    print("  i.e. the true retry population. That is the whole difference between D and A.")


def c2_duplicate_spend(sends, ex_idx, order):
    print("\n" + "=" * 78)
    print("C2  duplicate council spend ALREADY paid (prorated; replays excluded)")
    print("=" * 78)
    by_d = defaultdict(list)
    for (hh, did), reps in sends.items():
        by_d[did].append((order.get(hh, ""), hh, reps))
    tot_dup, tot_spend, rows = 0, 0.0, []
    for did, runs in by_d.items():
        seen, dup, spend = set(), 0, 0.0
        for _, hh, reps in sorted(runs):
            info = ex_idx[(hh, did)]
            overlap = reps & seen
            if overlap and info["n_calls"] > 0:      # a replay bought nothing
                dup += len(overlap)
                per_rep = info["cost_usd"] / max(len(reps), 1)
                spend += per_rep * len(overlap)
            elif overlap:
                dup += len(overlap)                   # counted as duplicate work, $0 spend
            seen |= reps
        if dup:
            rows.append((did, dup, spend))
            tot_dup += dup
            tot_spend += spend
    if not rows:
        print(f"  {NOTHING}: no rep was sent twice across production runs.")
        return
    print(f"  {'district':10s} {'dup reps':>9s} {'prorated $':>12s}")
    for did, dup, spend in sorted(rows, key=lambda r: -r[1]):
        print(f"  {did:10s} {dup:9d} {spend:12.4f}")
    print(f"  {'TOTAL':10s} {tot_dup:9d} {tot_spend:12.4f}")
    print(f"\n  {len(rows)} districts re-bought {tot_dup} reps for ${tot_spend:.4f}.")
    print("  Prorated from a per-(district,handoff) cost — an attribution, not a receipt.")
    print("  A FLOOR on waste over a partial campaign, NOT a fleet-scale forecast.")


def c3_live_batch(A, B, C, D):
    print("\n" + "=" * 78)
    print("C3  THE LIVE QUESTION — batch_00043 composed through district_release_input today")
    print("=" * 78)
    print(f"  {'district':9s} {'today':>6s} {'A':>4s} {'B':>4s} {'C':>4s} {'D':>4s} "
          f"{'new(D)':>7s}  name")
    tot = defaultdict(int)
    empties = []
    with gdb.session_scope() as s:
        for did in BATCH_00043:
            r = D6.district_release_input(s, did)
            if not r:
                print(f"  {did:9s}  (no release input — not in the DB)")
                continue
            meta, recs = r
            today = {(rd["rec_key"], rp.get("file"))
                     for rd in recs if rd["decision"] == "send"
                     for rp in (rd.get("send") or [])}
            a, b = today & A[did], today & B.get(did, set())
            c, d = today & C[did], today & D[did]
            tot["today"] += len(today)
            tot["A"] += len(a)
            tot["C"] += len(c)
            tot["D"] += len(d)
            new_d = len(today) - len(d)
            if today and new_d == 0:
                empties.append((did, meta.get("name", ""), len(today)))
            print(f"  {did:9s} {len(today):6d} {len(a):4d} {len(b):4d} {len(c):4d} {len(d):4d} "
                  f"{new_d:7d}  {(meta.get('name') or '')[:32]}")
    print(f"  {'TOTAL':9s} {tot['today']:6d} {tot['A']:4d} {'':4s} {tot['C']:4d} {tot['D']:4d} "
          f"{tot['today'] - tot['D']:7d}")
    if not tot["today"]:
        print(f"\n  {NOTHING}: batch_00043 composes no sendable reps at all.")
        return empties
    pct = 100.0 * tot["D"] / tot["today"]
    print(f"\n  {tot['D']} of {tot['today']} sendable reps ({pct:.0f}%) are already extracted.")
    print("  Dispatching this batch at gate@6 today re-buys every one of them.")
    return empties


def c4_acceptance(empties, A, D):
    print("\n" + "=" * 78)
    print("C4  acceptance specimens + strand-risk")
    print("=" * 78)
    print("  The issue's 'must fail today' case: a district whose sendables were ALL extracted")
    print("  in a prior run. Today they price and send as new; after the fix they must compose")
    print("  to an empty (or explicitly overridden) send set.\n")
    if not empties:
        print(f"  {NOTHING}: no district in batch_00043 composes to zero new reps — the")
        print("  acceptance test needs a specimen from another batch.")
    else:
        print(f"  {len(empties)} LIVE specimen(s) in batch_00043 alone:")
        for did, name, n in empties:
            print(f"    {did}  {name[:38]:40s} all {n} sendable rep(s) already extracted")
    print("\n  STRAND-RISK — the fix must never empty a district that has genuinely new work.")
    print("  By construction it cannot: the delta only ever SUBTRACTS reps that a prior")
    print("  production run already bought, so a rep never sent is never held. The failure")
    print("  mode worth guarding is the opposite one — an errored run being treated as")
    print("  'extracted' and its reps suppressed — which is exactly what predicate D prevents,")
    print("  per rep, using a fact as proof that THAT rep succeeded.")
    both = [d for d in A if len(A[d]) != len(D[d])]
    print(f"  Districts where that guard actually bites (A != D): {len(both)}")


def main():
    ex_idx = load_extraction_index()
    fact_reps = load_fact_reps()
    sends, order = load_receipts(ex_idx)
    print(f"corpus: {len(ex_idx)} (handoff, district) production runs, "
          f"{len(sends)} with parsed receipts")
    if not sends:
        print(f"\n{NOTHING}: no production receipts pair with an extraction row. "
              f"Check data/acquisition/handoffs/ and the governance DB.")
        return
    A, B, C, D = predicates(sends, ex_idx, fact_reps)
    c1_predicate_comparison(A, B, C, D)
    c2_duplicate_spend(sends, ex_idx, order)
    empties = c3_live_batch(A, B, C, D)
    c4_acceptance(empties, A, D)


if __name__ == "__main__":
    main()
