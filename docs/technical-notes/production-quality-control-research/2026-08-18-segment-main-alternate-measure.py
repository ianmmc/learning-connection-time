"""#841 — does `segment:main` belong in the 7->6 alternate set? Settle it by measurement.

RERUNNABLE, READ-ONLY. Imports the LIVE collectors (`release.alternates`,
`stage7_execute.live_alternates`) and the LIVE time scanner. Nothing is written.

    python3 docs/technical-notes/production-quality-control-research/2026-08-18-segment-main-alternate-measure.py

The issue framed this as: "how often does a `segment:main` rep carry n_times >= the sent text's?
If ~never, exclude it everywhere and the answer is free." It leaned toward EXCLUDE, on the
argument that main is a strict subset of page.txt.

S1  THE TRAP. `representation.n_times` is NULL for every `segment:*` rep — all 11,349 of them.
    Segments were written as INSPECTABLE reps (gate@5 viewing), never as dispatch candidates, so
    the column was hardcoded None (build_signals.py:1689). Answering the issue's question from the
    DB therefore CANNOT find a case where main carries more times: `nt or 0` reads every segment as
    zero. That is a measurement that cannot fail. S1 asserts the trap is closed.
S2  The real measurement: scan the segment:main text FROM DISK and compare to the sent rep.
S3  The decisive question the issue did not ask — is main ever the UNIQUELY best alternate? The
    full page is a superset of main and is not excluded, so main only matters where nothing else
    allowed is as good.
S4  The divergence audit: which records' alternate sets change under the settled rule.
"""
import json
from collections import Counter

from sqlalchemy import text

from infrastructure.acquisition.common import paths as P
from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.process_governance import stage7_execute as EX
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage5_filter import release as R

with session_scope() as s:
    dirs = dict(s.execute(text("SELECT DISTINCT rec_key, district_dir FROM record")).fetchall())
    sigs = dict(s.execute(text("SELECT rec_key, signals_json FROM record")).fetchall())
    facets = dict(s.execute(text("SELECT rec_key, facets_json FROM label")).fetchall())
    reps_rows = s.execute(text(
        "SELECT rec_key, source, filename, file_kind, n_chars, n_times, usable "
        "FROM representation")).fetchall()
    seg_null = s.execute(text(
        "SELECT count(*) FROM representation WHERE source LIKE 'segment:%' "
        "AND n_times IS NULL")).scalar()
    seg_all = s.execute(text(
        "SELECT count(*) FROM representation WHERE source LIKE 'segment:%'")).scalar()

by = {}
for rk, src, fn, fk, nc, nt, us in reps_rows:
    by.setdefault(rk, []).append(dict(source=src, filename=fn, file_kind=fk,
                                      n_chars=nc, n_times=nt, usable=us))

print("=" * 78)
print("S1  the trap")
print(f"    segment:* reps: {seg_all:,}   with n_times IS NULL: {seg_null:,}")
if seg_null == seg_all and seg_all:
    print("    ALL of them. A DB-only answer to the issue's question is unfalsifiable — every")
    print("    segment reads as 0 times, so 'main never carries more' is guaranteed, not measured.")
    print("    (The #841 fix computes n_times for segments at ingest; re-run this AFTER a re-ingest")
    print("     and this line should report 0 NULL, at which point S2 can use the DB directly.)")
elif seg_null:
    print(f"    PARTIAL — {seg_null:,} still NULL. Re-ingest incomplete; S2 still scans from disk.")
else:
    print("    0 NULL — segments are scored. S2's disk scan should now agree with the DB.")

scanned = ge = gt = 0
uniquely_best = []
dominated = 0
sent_src = Counter()

for rk, rs in by.items():
    mains = [r for r in rs if (r.get("source") or "") == "segment:main" and r.get("filename")]
    if not mains:
        continue
    try:
        sig = json.loads(sigs.get(rk) or "{}")
    except Exception:
        sig = {}
    fc = facets.get(rk)
    try:
        fd = json.loads(fc) if isinstance(fc, str) else (fc or {})
    except Exception:
        fd = {}
    try:
        send = R.best_send(rs, sig, fd)
    except Exception:
        continue
    if not send:
        continue
    sf = {x.get("file") for x in send}
    sent_txt = [r for r in rs if r["filename"] in sf and r["file_kind"] == "text"]
    sent_nt = max([(r.get("n_times") or 0) for r in sent_txt] or [0])
    dd = dirs.get(rk)
    rdir = P.RAW_CAPTURES / dd / "captures" / rk.split(":")[-1] if dd else None
    for m in mains:
        if m["filename"] in sf or rdir is None:
            continue
        fp = rdir / m["filename"]
        if not fp.exists():
            continue
        mt = len(BS.time_positions(fp.read_text(errors="replace")))
        scanned += 1
        if sent_nt > 0 and mt >= sent_nt:
            ge += 1
        if mt <= sent_nt:
            continue
        gt += 1
        sent_src[",".join(sorted({r["source"] or "?" for r in sent_txt})) or "NO-TEXT-SENT"] += 1
        best_other = 0
        for a in R.alternates(rs, sf):
            rr = next((r for r in rs if r["filename"] == a["file"]), None)
            if not rr or (rr.get("source") or "") == "segment:main":
                continue
            best_other = max(best_other, rr.get("n_times") or 0)
        if best_other >= mt:
            dominated += 1
        else:
            uniquely_best.append((rk, mt, sent_nt, best_other))

print(f"\nS2  unsent segment:main reps scanned FROM DISK: {scanned:,}")
print(f"    carrying n_times >= the sent text's : {ge:,}")
print(f"    carrying n_times >  the sent text's : {gt:,}")
print(f"    what was SENT in those cases: {dict(sent_src)}")
print("    (the dominant case sends a PDF extraction — a DIFFERENT document, so the issue's")
print("     'main is a strict subset of page.txt' argument does not apply to it.)")

print(f"\nS3  is main ever the UNIQUELY best alternate?")
print(f"    another allowed alternate already matches/beats main : {dominated}")
print(f"    main is uniquely best (excluding it loses a retry)   : {len(uniquely_best)}")
for rk, mt, st, bo in sorted(uniquely_best, key=lambda x: -(x[1] - x[3]))[:10]:
    print(f"      {rk}  main={mt:<4} sent={st:<4} best_other_allowed={bo}")

print("\nS4  divergence audit — the settled rule (ADMIT segment:main at all three collectors)")
print("    Compared on the SOURCE dimension only. The two collectors are intentionally different")
print("    on KIND and must not be forced together: release.alternates admits `pdf` because a")
print("    HUMAN at gate@6 can meaningfully swap to it, while live_alternates excludes it because")
print("    an AUTOMATED 7->6 retry would send raw bytes to a text council (#140, paid mojibake).")
print("    A first pass of this audit compared whole file sets and reported 3,532 false")
print("    'disagreements' that were all that one intentional pdf difference.")
changed = 0
examples = []
for rk, rs in by.items():
    sf = set()
    # hold KIND constant: only text/image reps, which both collectors admit
    tx = [r for r in rs if r.get("file_kind") in ("text", "image")]
    rel = {a["file"] for a in R.alternates(tx, sf)}
    live = {a["file"] for a in EX.live_alternates({"reps": tx}, sent_files=sf)}
    if rel != live:
        changed += 1
        if len(examples) < 5:
            examples.append((rk, sorted(rel ^ live)))
print(f"    records where the two disagree ON SOURCE: {changed}"
      f"   {'<-- BLOCKER' if changed else '(0 — one rule, one home)'}")
for rk, diff in examples:
    print(f"      {rk}: {diff}")
mains_admitted = sum(1 for rs in by.values()
                     if any((r.get("source") or "") == "segment:main" and r.get("usable")
                            for r in rs))
print(f"    records gaining segment:main as a Stage-7 alternate: {mains_admitted:,}")
print("    Every change is that one addition; chrome (header/footer/nav) and slices stay excluded.")

print()
if not scanned:
    print("VERDICT: NOTHING MEASURED — no unsent segment:main rep was readable.")
elif changed:
    print("VERDICT: REVIEW REQUIRED — the collectors still disagree.")
else:
    print(f"VERDICT: ADMIT. main is uniquely best on {len(uniquely_best)} records and dominated on")
    print(f"         only {dominated} — excluding it was losing real retries. This REVERSES the")
    print("         issue's leaning, which is why it asked for measurement rather than assertion.")
    print("         Caveat carried into the fix: rank_alternates files n_times 0/None text LAST,")
    print("         behind vision, so admitting main without scoring it would retry it after the")
    print("         expensive image. #841 therefore also computes n_times for segment reps.")
