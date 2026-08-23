#!/usr/bin/env python3
"""Stage-4 tool redundancy: which harvesters earn their place, and which are (near-)subsets?

READ-ONLY. Rerunnable. Imports the LIVE time predicate (`build_signals.time_positions` /
`TIME_RE`) rather than re-spelling it — #879's rule, learned when a measurement script's hand-rolled
`endswith` published a wrong corpus figure. Text is read FROM DISK, because `representation` stores
only aggregate `n_chars`/`n_times`; the per-tool overlap questions cannot be answered from the DB.

THE QUESTION (Ian, 2026-08-23). Stage 4 runs five tools on every PDF (pdftotext, pdfplumber_lines,
camelot_stream, camelot_hybrid, tesseract_raster) plus tesseract on screenshots/images. If a tool's
output is always a subset — or near-subset — of another's, it is paying processing time for nothing.

SCOPE, as directed: the WHOLE corpus, undifferentiated (benchmark and production alike), every
record regardless of whether it was labeled as carrying bell-schedule information.

WHAT THIS DOES *NOT* MEASURE — state it plainly rather than let the reader assume otherwise.
Stage 4 records NO per-tool timing anywhere: not in the DB, not in the receipts, not in the
state_event log. So this script ranks tools by REDUNDANCY, never by seconds saved. "camelot_hybrid
is droppable" here means "it contributes almost nothing unique", NOT "dropping it is the biggest
speedup available". Ranking the speedup requires instrumenting `process_stage4.TOOLS` and re-running
over a stratified sample — deliberately out of scope for this pass (Ian's call), and the reason no
section below quotes a time saving.

  C1  inventory: reps per tool, and the PAIRED subset (records carrying all five PDF tools) that
      makes the comparison apples-to-apples.
  C2  UNIQUE CLOCK TIMES — the pipeline's actual product. Per tool, the times it found that NO
      sibling tool on the same record found. A tool with ~zero unique times is a drop candidate.
  C3  SOLE-USABLE RESCUES — records where this tool is the ONLY usable representation. The
      reader-routing ladder's premise: a rarely-useful tool still earns its place as sole reader
      for a document class.
  C4  TEXT CONTAINMENT — per ordered pair (A,B), what fraction of A's content shingles appear in B.
      A ~1.0 containment of A in B is the literal "A is a subset of B" case Ian asked about.
  C5  the synthesis: each tool scored on all three axes, with an explicit KEEP / CANDIDATE verdict
      and the measured loss of dropping it.

Usage:  python3 docs/technical-notes/production-quality-control-research/2026-08-23-tool-redundancy-measure.py
        LIMIT=300 …  # sample N records instead of the full corpus (default: all)
"""
from __future__ import annotations

import os
import random
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths as P
from infrastructure.acquisition.stage5_filter.build_signals import time_positions

NOTHING = "NOTHING MEASURED"

# The five tools every PDF record gets (process_stage4.TOOLS) plus the image-side tesseracts.
PDF_TOOLS = ["pdftotext", "pdfplumber_lines", "camelot_stream", "camelot_hybrid", "tesseract_raster"]
OTHER_TEXT = ["tesseract_screenshot", "tesseract_image", "txt", "md", "csv"]
ALL_TOOLS = PDF_TOOLS + OTHER_TEXT

SHINGLE = 5          # word-level shingle width for containment
TIME_TOL = 0         # a "same time" is the same minute-of-day; tools disagree by parse, not clock


def _raw_dir() -> Path:
    for attr in ("RAW_DIR", "LEA_CAPTURES_DIR", "CAPTURES_DIR"):
        v = getattr(P, attr, None)
        if v:
            return Path(v)
    return Path("data/raw/lea-website-captures")


def load_reps(limit: int | None):
    """{rec_key: {source: text}} read from disk, plus the DB's usable flags."""
    with gdb.session_scope() as s:
        rows = list(s.execute(text(
            """SELECT r.rec_key, r.district_dir, r.hash, rep.source, rep.filename, rep.usable
                 FROM representation rep JOIN record r ON r.rec_key = rep.rec_key
                WHERE rep.source = ANY(:t) AND rep.filename IS NOT NULL""" ),
            {"t": ALL_TOOLS}).mappings())
    by_rec: dict = defaultdict(dict)
    usable: dict = defaultdict(dict)
    for r in rows:
        by_rec[r["rec_key"]][r["source"]] = (r["district_dir"], r["hash"], r["filename"])
        usable[r["rec_key"]][r["source"]] = bool(r["usable"])
    keys = sorted(by_rec)
    if limit and limit < len(keys):
        random.Random(20260823).shuffle(keys)
        keys = sorted(keys[:limit])
    root = _raw_dir()
    texts: dict = {}
    missing = 0
    for k in keys:
        t = {}
        for src, (ddir, h, fn) in by_rec[k].items():
            p = root / ddir / "captures" / h / fn
            try:
                t[src] = p.read_text(errors="replace")
            except OSError:
                missing += 1
        if t:
            texts[k] = t
    return texts, usable, missing


def shingles(txt: str) -> set:
    w = txt.split()
    if len(w) < SHINGLE:
        return {" ".join(w)} if w else set()
    return {" ".join(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def times_of(txt: str) -> set:
    """Minute-of-day multiset collapsed to a set — the LIVE predicate, not a re-spelling."""
    return {m for _pos, m in time_positions(txt)}


def main() -> None:
    limit = int(os.environ["LIMIT"]) if os.environ.get("LIMIT") else None
    texts, usable, missing = load_reps(limit)
    print(f"# 2026-08-23 · Stage-4 tool redundancy · {len(texts):,} records with text on disk"
          + (f" (LIMIT={limit})" if limit else " (full corpus)"))
    if missing:
        print(f"  NB {missing:,} rep files listed in the DB were unreadable on disk and skipped.")
    print("\n  COST IS NOT MEASURED HERE. Stage 4 records no per-tool timing anywhere, so every")
    print("  verdict below is about REDUNDANCY, never seconds saved. Do not read 'droppable' as")
    print("  'biggest speedup' — that ranking needs instrumentation this pass deliberately omits.\n")
    if not texts:
        print(f"C1..C5: {NOTHING} — no representation text could be read.")
        return

    # ------------------------------------------------------------------ C1 inventory + paired set
    print("## C1 — inventory and the PAIRED comparison set")
    present = defaultdict(int)
    for k, t in texts.items():
        for src in t:
            present[src] += 1
    for src in ALL_TOOLS:
        if present.get(src):
            print(f"  {src:24s} {present[src]:6,d} records")
    paired = [k for k, t in texts.items() if all(s in t for s in PDF_TOOLS)]
    print(f"\n  PAIRED set (all five PDF tools present): {len(paired):,} records — C2/C4 use this,")
    print("  so no tool is credited or penalised for simply being absent.")
    if not paired:
        print(f"  {NOTHING} — no record carries all five PDF tools; C2/C4 cannot run.")
        return

    # ------------------------------------------------------------------ C2 unique clock times
    print("\n## C2 — UNIQUE CLOCK TIMES (the pipeline's actual product)")
    uniq = defaultdict(int)          # times only this tool found
    found = defaultdict(int)         # times this tool found at all
    solo_recs = defaultdict(int)     # records where this tool was the sole source of >=1 time
    any_time_recs = 0
    for k in paired:
        per = {s: times_of(texts[k][s]) for s in PDF_TOOLS}
        allt = set().union(*per.values())
        if allt:
            any_time_recs += 1
        for s in PDF_TOOLS:
            others = set().union(*[per[o] for o in PDF_TOOLS if o != s])
            u = per[s] - others
            found[s] += len(per[s])
            uniq[s] += len(u)
            if u:
                solo_recs[s] += 1
    print(f"  over {len(paired):,} paired records ({any_time_recs:,} carry >=1 clock time)\n")
    print(f"  {'tool':24s}{'times found':>13}{'UNIQUE':>9}{'uniq %':>8}{'records it uniquely helps':>27}")
    for s in sorted(PDF_TOOLS, key=lambda x: -uniq[x]):
        pct = (100.0 * uniq[s] / found[s]) if found[s] else 0.0
        print(f"  {s:24s}{found[s]:>13,}{uniq[s]:>9,}{pct:>7.1f}%{solo_recs[s]:>27,}")

    # ------------------------------------------------------------------ C3 sole-usable rescues
    print("\n## C3 — SOLE-USABLE RESCUES (is this tool ever the only reader that works?)")
    sole = defaultdict(int)
    for k in texts:
        u = [s for s, ok in usable[k].items() if ok and s in texts[k]]
        if len(u) == 1:
            sole[u[0]] += 1
    if not sole:
        print(f"  {NOTHING} — no record has exactly one usable text representation.")
    else:
        for s, n in sorted(sole.items(), key=lambda x: -x[1]):
            print(f"  {s:24s} sole usable reader on {n:,} record(s)")
    for s in ALL_TOOLS:
        if present.get(s) and s not in sole:
            print(f"  {s:24s} sole usable reader on 0 records")

    # ------------------------------------------------------------------ C4 text containment
    print("\n## C4 — TEXT CONTAINMENT: fraction of A's shingles that also appear in B")
    print("  (read a row as: 'A is X% contained in B'. ~1.00 across the board = A is a subset.)")
    contain = defaultdict(list)
    for k in paired:
        # rebuilt per record — a dict carried across records would leak the previous record's
        # shingles into any tool missing here, silently inflating containment
        sh = {s: shingles(texts[k][s]) for s in PDF_TOOLS}
        for a in PDF_TOOLS:
            if not sh[a]:
                continue
            for b in PDF_TOOLS:
                if a == b:
                    continue
                contain[(a, b)].append(len(sh[a] & sh[b]) / len(sh[a]))
    print(f"\n  {'A (the candidate)':24s}{'B (the coverer)':24s}{'mean':>7}{'median':>8}{'>=0.95':>9}")
    rows = []
    for (a, b), v in contain.items():
        v = sorted(v)
        mean = sum(v) / len(v)
        med = v[len(v) // 2]
        hi = sum(1 for x in v if x >= 0.95) / len(v)
        rows.append((mean, a, b, med, hi, len(v)))
    for mean, a, b, med, hi, n in sorted(rows, reverse=True)[:12]:
        print(f"  {a:24s}{b:24s}{mean:>7.2f}{med:>8.2f}{hi:>8.0%}")
    print("\n  best coverer per tool (the single sibling that subsumes it most):")
    best = {}
    for mean, a, b, med, hi, n in sorted(rows, reverse=True):
        best.setdefault(a, (b, mean, hi))
    for a in PDF_TOOLS:
        if a in best:
            b, mean, hi = best[a]
            print(f"    {a:24s} -> {b:24s} mean {mean:.2f}, >=0.95 on {hi:.0%} of records")

    # ------------------------------------------------------------------ C5 synthesis
    #
    # The FIRST draft of this section asked whether a tool was redundant on ALL THREE axes,
    # including text containment >= 0.90. Nothing clears that bar — no tool's text is a literal
    # subset of a sibling's (C4 peaks at 0.55 mean) — so it printed KEEP for all five and HID the
    # actual finding. A verdict that cannot fire is not a verdict. The axis that decides this
    # question is UNIQUE CLOCK TIMES (the pipeline's product); text volume is a weak proxy that
    # measures how differently a tool words the same page, not whether it adds anything.
    print("\n## C5 — synthesis, scored on the axis that decides it: unique clock times")
    print(f"  {'tool':24s}{'uniq times':>11}{'uniq %':>8}{'sole-usable':>12}{'best coverer':>22}  verdict")
    keepers, cands = [], []
    for s in sorted(PDF_TOOLS, key=lambda x: -uniq[x]):
        b, mean, _hi = best.get(s, ("-", 0.0, 0.0))
        u, sr = uniq[s], sole.get(s, 0)
        pct = (100.0 * u / found[s]) if found[s] else 0.0
        # A tool is a retirement CANDIDATE when it contributes <1% of its own yield uniquely AND
        # is never the sole usable reader. Containment is reported, never gating (see above).
        cand = pct < 1.0 and sr == 0
        (cands if cand else keepers).append(s)
        print(f"  {s:24s}{u:>11,}{pct:>7.1f}%{sr:>12,}{b:>17s} {mean:>4.2f}  "
              f"{'CANDIDATE' if cand else 'KEEP'}")

    # The number that actually answers the question: drop every candidate AT ONCE and measure the
    # loss. Per-tool figures understate it (two candidates can each be redundant only because the
    # other is present) — so the combined drop must be measured, not summed.
    print(f"\n  COMBINED DROP — keep {{{', '.join(keepers)}}}, drop {{{', '.join(cands) or '-'}}}:")
    if not cands:
        print(f"    {NOTHING} — no tool is a retirement candidate in this corpus.")
    else:
        lost_t = lost_r = tot_t = 0
        affected = []
        for k in paired:
            per = {s: times_of(texts[k][s]) for s in PDF_TOOLS}
            keep_t = set().union(*[per[s] for s in keepers]) if keepers else set()
            only = set().union(*[per[s] for s in cands]) - keep_t
            tot_t += len(keep_t | only)
            if only:
                lost_t += len(only)
                lost_r += 1
                affected.append((len(only), k, len(keep_t)))
        print(f"    clock times lost : {lost_t:,} of {tot_t:,}  ({100.0*lost_t/max(tot_t,1):.2f}%)")
        print(f"    records affected : {lost_r:,} of {len(paired):,}  ({100.0*lost_r/len(paired):.2f}%)")
        rescues = sum(1 for n, k, nk in affected if nk == 0)
        print(f"    TRUE RESCUES (kept tools found NO time at all): {rescues}")
        if affected:
            print("    worst-affected records (a drop is only as safe as its tail):")
            for n, k, nk in sorted(affected, reverse=True)[:6]:
                print(f"      -{n:>3} times (kept {nk:>3})  {k}")
            dists = {}
            for n, k, _nk in affected:
                dists[k.split(":")[0]] = dists.get(k.split(":")[0], 0) + 1
                top = sorted(dists.items(), key=lambda x: -x[1])[:4]
            print(f"    affected records CLUSTER by district: {top}")
            print("    -> a document-family signature, not a random tail: a future district on the")
            print("       same CMS template could depend on these tools more than the % suggests.")

    print("\n  Reminder: CANDIDATE means 'contributes nothing unique in THIS corpus'. It does NOT")
    print("  rank speedup — Stage 4 is untimed (#890), and the most VALUABLE tool here")
    print("  (tesseract_raster) is likely also the most expensive, so the redundant tools may")
    print("  already be the cheap ones. And it cannot speak to document classes the corpus lacks,")
    print("  so any drop should ship as a config flag a future corpus can re-test, never a deletion.")


if __name__ == "__main__":
    sys.exit(main())
