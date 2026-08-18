"""#822 — output-overflow population sweep.

RERUNNABLE, READ-ONLY. Imports the LIVE functions (`release.decide` for the send decision,
`routing.route` for the council, `model_families.rep_overflow` for the verdict) and replays them
over the real corpus. Nothing is written; no DB row is touched.

    python3 docs/technical-notes/production-quality-control-research/2026-08-18-output-overflow-measure.py [--limit N]

O1  the overflow population: reps / records / districts whose estimated output exceeds the
    assigned council's ceiling (the starting population epic #80's experiments choose among)
O2  the four records #822 pins as having NO fitting rep — each must be flagged
O3  the UN-ASSESSABLE population, reported separately and never folded into "fits"
O4  the image council re-tested honestly. The issue reports "0 records exceed the image council's
    ceiling". With the CLAMPED estimate that figure could not have been anything else:
    size_max_tokens tops out at MAX_TOKENS_CEILING (32,000) and the image council's ceiling is
    32,768, so the comparison was unfalsifiable. Re-run against the unclamped need.
O5  overflow magnitude — how far past the ceiling, which is what says whether a higher-ceiling
    council (#823) would actually help or whether the rep needs partitioning (#824).
"""
import argparse
from collections import Counter, defaultdict

from sqlalchemy import text

from infrastructure.acquisition.common import model_families as MF
from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.stage5_filter import release as R
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import package as PKG6
from infrastructure.acquisition.stage6_handoff import routing

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=0, help="stop after N districts (fast partial run)")
args = ap.parse_args()

COUNCILS = C6.load_configs()
PINNED = ["4700148:8d0058ac10", "1200180:52b4f372cd", "0100270:e1ecbe7cfe", "3501110:ed61346ff2"]

with session_scope() as s:
    districts = [r[0] for r in s.execute(text(
        "SELECT DISTINCT district_id FROM record ORDER BY district_id")).fetchall()]
    if args.limit:
        districts = districts[:args.limit]
    print(f"districts in the corpus: {len(districts)}\n")

    overflow, unassessable, fits = [], [], []
    by_council = Counter()
    pinned_seen = defaultdict(list)
    pinned_unsent = {}
    ceilings = {}

    for i, did in enumerate(districts):
        if i % 50 == 0:
            print(f"  ...{i}/{len(districts)}", flush=True)
        for rec in R.load_district_records(s, did):
            d = R.decide(rec)
            if rec["rec_key"] in PINNED and not d["send"]:
                # A pinned record can leave the dispatch population legitimately — a human label at
                # gate@5, a hold. Record WHY, so "not flagged" is never mistaken for "missed".
                pinned_unsent[rec["rec_key"]] = f'{d["decision"]}:{d["reason"]}'
            if d["decision"] != "send":
                continue
            sig = rec.get("signals") or {}
            by_file = {r["filename"]: r for r in rec.get("reps", [])}
            for se in d["send"]:
                rr = by_file.get(se.get("file")) or {}
                n_chars, n_times = rr.get("n_chars"), rr.get("n_times")
                rt = routing.route({**se, "n_chars": n_chars, "n_times": n_times}, sig, COUNCILS)
                cid = rt["councils"][0] if rt["councils"] else None
                cfg = COUNCILS.get(cid)
                if cfg is None:
                    continue
                # #846: the SAME call site Stage 6 uses — content + system prompt, shaped by kind
                verdict = PKG6._overflow_for(cfg, {**se, "n_chars": n_chars, "n_times": n_times})
                need = MF.estimate_output_tokens(n_times)
                tot, nimg = MF.rep_prompt_size(n_chars, PKG6.system_prompt_chars(cfg),
                                               se.get("kind") or "text")
                ceil = MF.council_ceiling(cfg, MF.estimate_prompt_tokens(tot, nimg))
                row = dict(did=did, rec_key=rec["rec_key"], file=se.get("file"), kind=se.get("kind"),
                           council=cid, n_chars=n_chars, n_times=n_times, need=need, ceiling=ceil)
                if verdict is True:
                    overflow.append(row)
                    by_council[cid] += 1
                elif verdict is None:
                    unassessable.append(row)
                    by_council[f"{cid} (un-assessable)"] += 1
                else:
                    fits.append(row)
                if rec["rec_key"] in PINNED:
                    pinned_seen[rec["rec_key"]].append((verdict, cid, need, ceil))

    for cid, cfg in COUNCILS.items():
        ceilings[cid] = MF.council_ceiling(cfg, 0)

print("\n" + "=" * 78)
print(f"O1  reps sent (assessable + not): {len(overflow) + len(fits) + len(unassessable):,}")
print(f"    OVERFLOW     : {len(overflow):,} reps"
      f"  ·  {len({r['rec_key'] for r in overflow}):,} records"
      f"  ·  {len({r['did'] for r in overflow}):,} districts")
print(f"    fits         : {len(fits):,} reps")
print(f"    UN-ASSESSABLE: {len(unassessable):,} reps"
      f"  ·  {len({r['rec_key'] for r in unassessable}):,} records"
      f"  ·  {len({r['did'] for r in unassessable}):,} districts")
for cid, n in by_council.most_common():
    print(f"      {cid:<28} {n:>6}")

print(f"\nO2  the four pinned no-fitting-rep records")
missing = [k for k in PINNED if k not in pinned_seen]
for k in PINNED:
    seen = pinned_seen.get(k)
    if not seen:
        why = pinned_unsent.get(k, "not found among canonical records")
        print(f"    {k}: NOT DISPATCHED — {why}")
        print(f"        (the rep still overflows on its own numbers; it has simply left the")
        print(f"         dispatch population, so there is no dispatch-time flag to assert.)")
        continue
    flagged = all(v is True for v, _, _, _ in seen)
    print(f"    {k}: {len(seen)} sent rep(s), all flagged={flagged}"
          f"   {'' if flagged else '<-- BLOCKER'}")
    for v, cid, need, ceil in seen:
        print(f"        overflow={v} council={cid} need={need} ceiling={ceil}")

print(f"\nO3  un-assessable is reported, never folded into 'fits'")
kinds = Counter(r["kind"] for r in unassessable)
print(f"    by rep kind: {dict(kinds)}")
print(f"    (these carry no n_times — `representation.n_times` is NULL for binaries. Scoring them")
print(f"     'fits' would report the vision tier clean when it is merely unmeasured.)")

print(f"\nO4  the image council, re-tested against the UNCLAMPED need")
print(f"    council ceilings at prompt=0: {ceilings}")
print(f"    MAX_TOKENS_CEILING (the clamp) = {MF.MAX_TOKENS_CEILING}")
for cid, ceil in ceilings.items():
    if ceil is not None and MF.MAX_TOKENS_CEILING < ceil:
        print(f"    NOTE: '{cid}' ceiling {ceil} > clamp {MF.MAX_TOKENS_CEILING} — a CLAMPED estimate")
        print(f"          could never exceed it, so any '0 overflow' measured that way was a")
        print(f"          tautology, not a finding. This sweep uses the unclamped need.")
img_over = [r for r in overflow if r["council"] == "image"]
img_unass = [r for r in unassessable if r["council"] == "image"]
print(f"    image-council reps: {len(img_over)} overflow · {len(img_unass)} un-assessable")
if not img_over and img_unass:
    print(f"    => '0 exceed the image council' is NOT established: {len(img_unass)} of its reps")
    print(f"       are un-assessable (no countable n_times), so the population is unmeasured,")
    print(f"       not clean. That is the corrected input epic #80 needs.")

print(f"\nO5  overflow magnitude (need ÷ ceiling), the #823-vs-#824 discriminator")
ratios = sorted(((r["need"] / r["ceiling"], r) for r in overflow
                 if r["ceiling"] and r["ceiling"] > 0), reverse=True)
neg = [r for r in overflow if r["ceiling"] is not None and r["ceiling"] <= 0]
print(f"    reps whose ceiling is already <= 0 (prompt alone fills the window): {len(neg)}")
print(f"       — these are ALSO caught today by the pre-flight refusal; overflow names the cause.")
for ratio, r in ratios[:10]:
    print(f"    {ratio:>5.2f}x  {r['rec_key']:<26} n_times={r['n_times']:>5} "
          f"need={r['need']:>7} ceiling={r['ceiling']:>6}  {r['council']}")

print()
if not (overflow or unassessable):
    print("VERDICT: NOTHING MEASURED — no rep was assessable and none overflowed. Check that the")
    print("         release decision is producing sends at all before reading this as clean.")
else:
    blocked = [k for k, v in pinned_seen.items() if not all(x[0] is True for x in v)]
    unexplained = [k for k in missing if k not in pinned_unsent]
    if blocked or unexplained:
        print(f"VERDICT: REVIEW REQUIRED — unflagged pinned: {blocked}; "
              f"unexplained absences: {unexplained}")
    else:
        print("VERDICT: PASS")
        if missing:
            print(f"         ({len(missing)} pinned record(s) have left the dispatch population "
                  f"via an explained gate@5 decision — see O2.)")
