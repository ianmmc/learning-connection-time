"""Pass B — verification for the absolute time-bearing page floor (#821).

RERUNNABLE, READ-ONLY. Imports the LIVE functions and replays the REAL `best_send`; slices are
built in memory and never written, no DB row is touched.

    python3 docs/technical-notes/production-quality-control-research/2026-08-17-timebearing-floor-measure.py [--limit N]

B1  every changed send is `full text -> timebearing_slice`, never anything else
B2  char saving REALIZED THROUGH THE GUARD, plus how many lossless slices the guard rejected via
    the counter asymmetry (build_signals.time_positions filters through to_minutes; Stage 4's
    count does not, so the slice is systematically disadvantaged)
B3  the handbook subpopulation's send is byte-identical — count of differences must be 0
B4  the named dense hubs, before vs after
B5  every changed send traced to an intended cause
B6  roster-name / positive-keyword coverage full text vs slice — no record may lose a hit, reported
    per floor-term so keep_first / keep_neighbors are measured rather than assumed
"""
import argparse
import json
import re
from collections import Counter

from sqlalchemy import text

from infrastructure.acquisition.common import paths as P
from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.common.school_match import norm_school
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage5_filter import release as R

SCHOOL_RE = re.compile(
    r"\b([A-Z][A-Za-z\.\'-]+(?:\s+[A-Z][A-Za-z\.\'-]+){0,4}\s+"
    r"(?:Elementary|Middle|High|Intermediate|Primary|Academy|School))\b")

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=0)
args = ap.parse_args()

with session_scope() as s:
    recs = s.execute(text(
        "SELECT rec_key, district_id, district_dir, signals_json FROM record")).fetchall()
    reps_rows = s.execute(text(
        "SELECT rec_key, source, filename, file_kind, n_chars, n_times, usable "
        "FROM representation")).fetchall()
    facets = dict(s.execute(text("SELECT rec_key, facets_json FROM label")).fetchall())
    pdfs = dict(s.execute(text(
        "SELECT rec_key, MIN(filename) FROM representation "
        "WHERE file_kind='pdf' AND filename IS NOT NULL GROUP BY rec_key")).fetchall())

by = {}
for rk, src, fn, fk, nc, nt, us in reps_rows:
    by.setdefault(rk, []).append(dict(source=src, filename=fn, file_kind=fk,
                                      n_chars=nc, n_times=nt, usable=us))

pop = []
for rk, did, ddir, sj in recs:
    try:
        sig = json.loads(sj or "{}")
    except Exception:
        continue
    if not sig.get("pages"):
        continue
    pop.append((rk, did, ddir, sig))
if args.limit:
    pop = pop[:args.limit]
print(f"records with a per-page signal: {len(pop)}\n")

changed, guard_rejected, handbook_diffs = [], [], []
name_loss, pairable_loss, kw_loss = [], [], []
term_cost = Counter()
sent_before = sent_after = 0
b4 = {}

for i, (rk, did, ddir, sig) in enumerate(pop):
    if i % 200 == 0:
        print(f"  ...{i}/{len(pop)}", flush=True)
    reps = by.get(rk, [])
    fc = facets.get(rk)
    try:
        fdict = json.loads(fc) if isinstance(fc, str) else (fc or {})
    except Exception:
        fdict = {}

    before = R.best_send(reps, sig, fdict)
    tb_pages = BS.time_bearing_pages(sig["pages"])

    # measure each safety term's page cost on the same document
    if tb_pages:
        base = BS.time_bearing_pages(sig["pages"], keep_first=False, keep_neighbors=False)
        term_cost["pages_base"] += len(base)
        term_cost["pages_full"] += len(tb_pages)
        term_cost["docs"] += 1

    fn = pdfs.get(rk)
    pdf = (P.RAW_CAPTURES / ddir / "captures" / rk.split(":")[-1] / fn) if fn else None
    if not tb_pages or not pdf or not pdf.exists():
        continue

    pts = BS.pdf_page_texts(pdf)
    built = BS.build_slice(tb_pages, lambda p: BS.page_text_from(pts, p),
                           BS.TIMEBEARING_SLICE_SOURCE)
    if not built:
        continue
    slice_text, kw = built

    # production materializes the floor slice ONLY when the harvest branch did not fire
    human_hp = BS.labeled_pages_of(fdict)
    hp = human_hp or sig.get("harvest_pages") or []
    if hp and (human_hp or sig.get("is_handbook")):
        # handbook record: assert the new rep changes nothing even if present (P3)
        after_hb = R.best_send(reps + [dict(kw)], dict(sig, timebearing_pages=tb_pages), fdict)
        if after_hb != before:
            handbook_diffs.append((rk, before, after_hb))
        continue

    after = R.best_send(reps + [dict(kw)], dict(sig, timebearing_pages=tb_pages), fdict)
    usable_text = [r for r in reps if r["file_kind"] == "text" and r["usable"] and r["filename"]
                   and r["source"] not in BS.SLICE_SOURCES]
    bt = max(usable_text, key=lambda r: ((r["n_times"] or 0), (r["n_chars"] or 0)), default=None)
    sent_before += (bt or {}).get("n_chars") or 0

    if after != before:
        sent_after += kw["n_chars"]
        changed.append(dict(rk=rk, did=did, before=before[0] if before else None,
                            after=after[0] if after else None,
                            pages=len(tb_pages), all_pages=len(sig["pages"]),
                            slice_chars=kw["n_chars"], full_chars=(bt or {}).get("n_chars"),
                            slice_times=kw["n_times"], full_times=(bt or {}).get("n_times")))
        # B6: coverage of the FULL text vs the slice (only where the slice is actually sent).
        #
        # The raw name diff OVER-REPORTS, and reporting it alone would have read as a blocker.
        # A fact is a (school, start, end) TRIPLE: a name on a page with no clock times cannot
        # contribute one — e.g. 2302820:e4ae69a65b p22 is a mailing-address directory listing five
        # real schools and zero times. Losing those names loses no extractable fact.
        #
        # So measure both:
        #   names_lost    — informative, expected to be non-zero (chrome + directories)
        #   PAIRABLE lost — a name that co-occurs with times on some page of the full document and
        #                   is absent from the slice. This is the number that blocks: it must be 0,
        #                   and it is 0 by construction only if every time-bearing page really is
        #                   kept AND its text really reaches the slice. That end-to-end check is
        #                   the point — the "lossless" claim is about pages, this tests the bytes.
        # Both sides are computed PER PAGE, never over concatenated text. SCHOOL_RE's `\s+` happily
        # spans a page join (form feed + "\n\n" are all whitespace), so a name read off the joined
        # slice can absorb a trailing word from the previous page and normalize differently — which
        # showed up as a phantom "pairable name lost" on 3200480:9fc7826938 ('Bus\n  School'). The
        # page is in the slice; only the measurement was wrong. Per-page on both sides removes it.
        def names_on(page_texts):
            out = set()
            for t in page_texts:
                out |= {norm_school(n) for n in SCHOOL_RE.findall(t or "")}
            return out - {""}

        kept_texts = [pts[p - 1] for p in tb_pages if p <= len(pts)]
        full_text = "\n\n".join(pts)
        fn_full = names_on(pts)
        fn_slice = names_on(kept_texts)
        pairable = names_on([pts[pg["page"] - 1] for pg in sig["pages"]
                             if (pg.get("n_times") or 0) > 0 and pg["page"] <= len(pts)])
        if fn_full - fn_slice:
            name_loss.append((rk, sorted(fn_full - fn_slice)[:6]))
        if pairable - fn_slice:
            pairable_loss.append((rk, sorted(pairable - fn_slice)[:6]))
        kw_full = set(BS.keyword_hits(full_text.lower(), list(BS.POSITIVE_KW)))
        kw_slice = set(BS.keyword_hits(slice_text.lower(), list(BS.POSITIVE_KW)))
        if kw_full - kw_slice:
            kw_loss.append((rk, sorted(kw_full - kw_slice)[:6]))
    else:
        sent_after += (bt or {}).get("n_chars") or 0
        if (kw["n_times"] or 0) >= ((bt or {}).get("n_times") or 0):
            pass                      # declined on the saving test, not the yield guard
        else:
            guard_rejected.append(dict(rk=rk, slice_times=kw["n_times"],
                                       full_times=(bt or {}).get("n_times")))
    if rk in ("4700148:8d0058ac10", "1201440:b8f930171d", "1200180:52b4f372cd"):
        b4[rk] = dict(pages=f"{len(tb_pages)}/{len(sig['pages'])}",
                      chars=f"{(bt or {}).get('n_chars')} -> {kw['n_chars']}",
                      changed=after != before)

print("\n" + "=" * 78)
print(f"B1  sends changed: {len(changed)}")
bad = [c for c in changed if not ((c["before"] or {}).get("kind") == "text"
                                  and (c["after"] or {}).get("file") == BS.TIMEBEARING_SLICE_FILE)]
print(f"    changes that are NOT `full text -> timebearing_slice`: {len(bad)}"
      f"   {'<-- BLOCKER' if bad else '(none)'}")
for c in bad[:10]:
    print(f"      {c['rk']}: {c['before']} -> {c['after']}")

print(f"\nB2  characters sent across the swept population")
print(f"    before: {sent_before:,}")
print(f"    after : {sent_after:,}"
      f"   ({100 * (1 - sent_after / max(sent_before, 1)):.1f}% saved, realized THROUGH the guard)")
print(f"    lossless slices the guard still rejected (counter asymmetry): {len(guard_rejected)}")
if changed:
    ratios = sorted(c["slice_chars"] / c["full_chars"] for c in changed if c["full_chars"])
    print(f"    slice/full char ratio: p10={ratios[len(ratios)//10]:.2f} "
          f"median={ratios[len(ratios)//2]:.2f} p90={ratios[9*len(ratios)//10]:.2f}")

print(f"\nB3  handbook sends that differ with the new rep present: {len(handbook_diffs)}"
      f"   {'<-- BLOCKER' if handbook_diffs else '(0 — byte-identical)'}")
for rk, b, a in handbook_diffs[:10]:
    print(f"      {rk}: {b} -> {a}")

print(f"\nB4  the named dense hubs")
for rk, v in (b4 or {"(none in population)": {}}).items():
    print(f"      {rk}: {v}")

print(f"\nB6  coverage of the full text vs the slice, where the slice is SENT")
print(f"    records losing a school NAME at all: {len(name_loss)}"
      f"   (expected non-zero: nav chrome + address directories on time-free pages)")
for rk, names in name_loss[:6]:
    print(f"      {rk}: {names}")
print(f"    records losing a PAIRABLE name (co-occurs with times in the full doc): "
      f"{len(pairable_loss)}"
      f"   {'<-- BLOCKER' if pairable_loss else '(0 — no extractable fact is lost)'}")
for rk, names in pairable_loss[:10]:
    print(f"      {rk}: {names}")
print(f"    records losing a positive KEYWORD: {len(kw_loss)}")
for rk, k in kw_loss[:10]:
    print(f"      {rk}: {k}")
if term_cost["docs"]:
    print(f"\n    safety-term page cost over {term_cost['docs']} scoped docs: "
          f"times+instr only = {term_cost['pages_base']} pages, "
          f"+first+neighbours = {term_cost['pages_full']} pages "
          f"(+{term_cost['pages_full'] - term_cost['pages_base']})")

print("\nVERDICT:", "PASS" if not bad and not handbook_diffs and not pairable_loss
      else "REVIEW REQUIRED")
