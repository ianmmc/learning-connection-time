"""#863 — `page.txt` and the DOM segments are read at DIFFERENT INSTANTS; measure the disagreement.

RERUNNABLE, READ-ONLY. Reads the live governance DB (and, for the specimen section, the capture
files on disk). Nothing is written.

    python3 docs/technical-notes/production-quality-control-research/2026-08-21-read-timing-split-measure.py

Why this exists: #863's table was measured once, by hand, on 2026-08-19 and lives only in the issue
body. Per the repo's standing lesson (a fix's measured blast radius is part of the fix; commit the
rerunnable script, never the recollection — #870), the BEFORE state has to be reproducible so the
AFTER state means something. This script IS the before-table, and re-running it after the Stage-3
change is what closes #863's first acceptance box.

The property under test
-----------------------
`page.main.txt` is `body.innerText` with the landmark (chrome) elements removed; `page.txt` is
`body.innerText` over every frame. Main is therefore a SUBSET of page.txt **by construction — if
the two are read at the same instant.** They are not:

    page.txt : capture_discovery.mjs, after `domcontentloaded` + waitForTimeout(2500) + dismissModals
    segments : capture_discovery.mjs, at END of capture — after the full-page screenshot and page.pdf()

Anything that renders lazily in between (Finalsite tab/accordion widgets, deferred content) makes
main a STRICT SUPERSET of the thing it is supposedly a subset of. Every `main > page.txt` record
below is a page that changed between the two reads.

C1  the before-table: the five size/time relations between page.txt and page.main.txt.
C2  the acceptance property, stated as a live check — `main_chars <= page_txt_chars` on every
    record carrying both. This is the box #863 asks to flip; today it FAILS by design, and after
    the Stage-3 fix it must pass on every NEWLY captured record. Old captures keep their split
    reads until re-captured, so the script reports old/new separately once a phase marker exists.
C3  the consequence that actually costs money: records where page.txt holds ZERO clock times and
    main holds some. These are pages whose entire time-bearing content arrived after the early
    read. Cross-referenced against `best_send` so the report says whether the later read is what
    the pipeline actually ships.
C4  the specimens named in the issue, re-read from disk, so a reader can see one concrete page
    rather than a count.

Every section prints an explicit NOTHING MEASURED verdict rather than a green zero, because an
empty sweep and a clean sweep are not the same result (the repo's seventh-shape lesson).
"""
import collections
import json
import re

from sqlalchemy import text

from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.stage5_filter import release as R
from infrastructure.acquisition.stage5_filter.build_signals import TIME_RE

PAGE_TXT_SOURCE = "txt"           # filename page.txt
MAIN_SOURCE = "segment:main"      # filename page.main.txt

DISTRICT_DIRS = paths.RAW_CAPTURES

SPECIMENS = ("4700148:29413d6cfb", "0900450:bc8b552337", "3901302:e26f3c6d06")


def verdict(name, n_scanned, lines):
    """Print a section, refusing to report a green zero on an empty sweep."""
    print(f"\n=== {name} ===")
    if not n_scanned:
        print("  NOTHING MEASURED — the sweep scanned 0 records. This is NOT a pass; the "
              "query or the corpus is wrong. Fix the script before reading any number below.")
        return
    print(f"  scanned: {n_scanned} records")
    for ln in lines:
        print(f"  {ln}")


with session_scope() as s:
    reps = collections.defaultdict(dict)
    for rk, src, nc, nt, us in s.execute(text(
            "SELECT rec_key, source, n_chars, n_times, usable FROM representation "
            "WHERE source IN (:a, :b)"), {"a": PAGE_TXT_SOURCE, "b": MAIN_SOURCE}).fetchall():
        reps[rk][src] = dict(n_chars=nc or 0, n_times=nt, usable=us)

    decisions, sends = {}, {}
    for (did,) in s.execute(text("SELECT DISTINCT district_id FROM record")).fetchall():
        for rec in R.load_district_records(s, did):
            # `decide` is the live entry point; its `send` already ran `best_send` with the same
            # signals/facets the pipeline uses. Calling best_send separately here would be a
            # second call site reconstructing the inputs — exactly the drift class #846 named.
            d = R.decide(rec)
            decisions[rec["rec_key"]] = d["decision"]
            sends[rec["rec_key"]] = {e.get("file") for e in (d.get("send") or [])}

    canonical = {r[0] for r in s.execute(text(
        f"SELECT rec_key FROM record r WHERE {R.CANONICAL_RECORD_WHERE}")).fetchall()}

# ---- records carrying BOTH reads -------------------------------------------------------------
both = {rk: v for rk, v in reps.items() if PAGE_TXT_SOURCE in v and MAIN_SOURCE in v}

# `n_times` is NULL-free for text reps since the #841 re-ingest, but a NULL here would silently
# read as 0 and manufacture a clean result — the exact failure #841 was. Refuse to coerce.
null_times = [rk for rk, v in both.items()
              if v[PAGE_TXT_SOURCE]["n_times"] is None or v[MAIN_SOURCE]["n_times"] is None]

rel = collections.Counter()
zero_early = []          # page.txt 0 times, main > 0
main_bigger = []         # main has more chars than page.txt
for rk, v in both.items():
    if rk in null_times:
        continue
    p, m = v[PAGE_TXT_SOURCE], v[MAIN_SOURCE]
    if m["n_chars"] > p["n_chars"]:
        rel["main has MORE chars than page.txt"] += 1
        main_bigger.append((rk, p["n_chars"], m["n_chars"]))
    if m["n_times"] > p["n_times"]:
        rel["main has MORE clock times than page.txt"] += 1
    elif m["n_times"] < p["n_times"]:
        rel["main has FEWER clock times (chrome removed — expected)"] += 1
    else:
        rel["equal clock times"] += 1
    if p["n_times"] == 0 and m["n_times"] > 0:
        zero_early.append(rk)

lines = []
if null_times:
    lines.append(f"!! {len(null_times)} records have a NULL n_times on one of the two reads — "
                 "EXCLUDED, not coerced to 0. Re-ingest before trusting the rest (#841).")
for k in ("main has MORE chars than page.txt",
          "main has MORE clock times than page.txt",
          "main has FEWER clock times (chrome removed — expected)",
          "equal clock times"):
    lines.append(f"{rel[k]:>6}  {k}")
lines.append(f"{len(zero_early):>6}  page.txt has 0 clock times, main has >0")
verdict("C1 — the before-table (page.txt vs page.main.txt)", len(both), lines)

# ---- C2: the acceptance property --------------------------------------------------------------
# The fix only changes what NEW captures write, so a corpus-wide pass is not achievable without a
# full re-capture. `text_phase` (set by capture_discovery.mjs) is the discriminator: 'final' = the
# single late read, 'early' = segmentation failed and the early text stayed, absent = captured
# before the fix. It lives in the Stage-3 receipt, not the DB (ingest reads a fixed key list and
# drops unknown fields), so read it from disk. Without this split the after-run would report a
# FAIL forever and look like the fix did nothing.
phase_by_rec = {}
capfiles = sorted(DISTRICT_DIRS.glob("*/captures.json"))
if not capfiles:
    # The #826 failure mode, verbatim: a wrong district-dir assumption scanned 0 records and the
    # sweep reported a confident green zero. "0 post-fix captures" and "the path is wrong" look
    # identical from the output, so make the script say which one it is.
    raise SystemExit(f"NOTHING MEASURED — no captures.json under {DISTRICT_DIRS}. The path "
                     "assumption is wrong; every post-fix count below would be a false zero.")
for capfile in capfiles:
    did = capfile.parent.name.split("_")[0]
    try:
        recs = json.loads(capfile.read_text())
    except (OSError, ValueError):
        continue
    for r in recs if isinstance(recs, list) else recs.values():
        if r.get("hash"):
            phase_by_rec[f"{did}:{r['hash']}"] = r.get("text_phase")

post_fix = {rk for rk in both if phase_by_rec.get(rk) in ("final", "early")}
violations = len(main_bigger)
post_fix_violations = [t for t in main_bigger if t[0] in post_fix]
lines = [f"Stage-3 receipts scanned from disk: {len(capfiles)} districts / {len(phase_by_rec)} captures",
         f"captures carrying a text_phase marker (post-fix): {len(post_fix)} of {len(both)}",
         f"records where main_chars > page_txt_chars: {violations} "
         f"({len(post_fix_violations)} of them post-fix)",
         f"acceptance property 'main <= page.txt' over POST-FIX captures: "
         f"{'NOTHING MEASURED — no re-captured records yet' if not post_fix else ('PASS' if not post_fix_violations else 'FAIL')}",
         f"legacy (pre-fix) captures still violating: {violations - len(post_fix_violations)} "
         "— expected, and only a re-capture clears them"]
if violations:
    lines.append("(expected FAIL against today's Stage 3 — the two reads are taken at different")
    lines.append(" instants. After the fix this must be 0 for every newly captured record.)")
    worst = sorted(main_bigger, key=lambda t: t[2] - t[1], reverse=True)[:5]
    lines.append("worst 5 by char gap (rec_key, page.txt, main):")
    for rk, pc, mc in worst:
        lines.append(f"    {rk}  {pc:>8} -> {mc:>8}   (+{mc - pc})")
verdict("C2 — acceptance property: main is a subset of page.txt", len(both), lines)

# ---- C3: the records where the early read saw no times at all ---------------------------------
by_decision = collections.Counter(decisions.get(rk, "?") for rk in zero_early)
sends_main = [rk for rk in zero_early if "page.main.txt" in (sends.get(rk) or set())]
lines = [f"page.txt 0 times / main >0 times: {len(zero_early)} records "
         f"({sum(1 for rk in zero_early if rk in canonical)} canonical)",
         "by release decision: " + (", ".join(f"{k}={v}" for k, v in sorted(by_decision.items()))
                                    or "(none)"),
         f"of those, best_send actually ships page.main.txt on: {len(sends_main)}"]
lines.append("Reading: on these pages EVERY clock time arrived after the early read. Where the")
lines.append("decision is send and best_send picks main, #841's scoring is the only reason the")
lines.append("pipeline is not shipping a timeless page. That is a scoring rescue of a capture bug,")
lines.append("not a fix — which is why #863 exists.")
verdict("C3 — pages whose clock times exist ONLY in the later read", len(both), lines)

# ---- C4: the issue's named specimens, from the DB ----------------------------------------------
lines, n_found = [], 0
for rk in SPECIMENS:
    v = both.get(rk)
    if not v:
        lines.append(f"{rk}: NOT PRESENT in this corpus (re-ingested away, or wrong key)")
        continue
    n_found += 1
    p, m = v[PAGE_TXT_SOURCE], v[MAIN_SOURCE]
    lines.append(f"{rk}: page.txt {p['n_chars']:>7} ch / {p['n_times']:>3} times   "
                 f"main {m['n_chars']:>7} ch / {m['n_times']:>3} times   "
                 f"decision={decisions.get(rk, '?')} send={sorted(sends.get(rk) or [])}")
verdict("C4 — the specimens named on #863", n_found, lines)

nonempty = re.compile(r"\S")   # TIME_RE / nonempty imported to pin the live regex, not a copy
assert TIME_RE and nonempty, "live TIME_RE must be importable — this script never re-spells it"
print("\ndone — read-only, nothing written.")
