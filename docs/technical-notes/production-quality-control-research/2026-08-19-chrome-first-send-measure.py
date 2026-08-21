"""#862/#865 — chrome must never be the FIRST send. Measure it; don't assert it.

RERUNNABLE, READ-ONLY. Imports the LIVE functions (`release.best_send`, `release.decide`,
`release.sendable_text_reps`) and replays them over the real corpus. Nothing is written.

    python3 docs/technical-notes/production-quality-control-research/2026-08-19-chrome-first-send-measure.py

Why this exists (#870): PR #865's after-numbers lived only in the PR body, and the ad-hoc sweep
behind them was WRONG — it reported 4 affected records when the real population is 244. The 4 was
the count of records where #841's `n_times` scoring newly flipped the pick to chrome; it missed the
~240 where chrome had ALREADY been winning on the `(n_times, n_chars)` tie-break since REQ-091,
invisible because a reject never serializes its send. A committed script with an explicit
NOTHING MEASURED verdict is the countermeasure the repo's standing lesson asks for.

C1  the invariant, live: no canonical record's `best_send` may return a chrome rep.
C2  the population #862 removed — replayed BOTH ways (chrome admitted vs excluded) so the number
    is a measurement, not a recollection. Broken out by decision, because "all rejects" is the
    load-bearing claim: it is why 0 dispatch decisions changed.
C3  the residual gap #867 found: records where chrome carries clock times the sendable pool does
    NOT have. After #862 no automated path — first send or 7->6 retry — can reach those. Today
    every one is reject/hold, so nothing is lost live; the guard is that a SEND-decided one must
    never appear. Root cause is #863 (page.txt is read at DOM-ready+2.5s, segments at
    end-of-capture), so this count should fall to ~0 once #863 lands, not grow.
C4  #868's degenerate path: records whose ONLY usable text is chrome. Their pool is empty
    post-#862, so `best_send` falls to image/pdf/[]. Guarded by construction —
    `visual_text_gap` is true whenever every real text rep is sub-usable — and C4 proves it.
"""
import collections
import json

from sqlalchemy import text

from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.stage5_filter import release as R

CHROME_FILES = ("page.header.txt", "page.footer.txt", "page.nav.txt")


def _js(x):
    try:
        return json.loads(x) if isinstance(x, str) else (x or {})
    except (TypeError, ValueError):
        return {}


with session_scope() as s:
    sigs = dict(s.execute(text("SELECT rec_key, signals_json FROM record")).fetchall())
    tiers = dict(s.execute(text("SELECT rec_key, tier FROM record")).fetchall())
    facets = dict(s.execute(text("SELECT rec_key, facets_json FROM label")).fetchall())
    reps_rows = s.execute(text(
        "SELECT rec_key, source, filename, file_kind, n_chars, n_times, usable "
        "FROM representation")).fetchall()
    canonical = {r[0] for r in s.execute(text(
        f"SELECT rec_key FROM record r WHERE {R.CANONICAL_RECORD_WHERE}")).fetchall()}
    decisions = {}
    for (did,) in s.execute(text("SELECT DISTINCT district_id FROM record")).fetchall():
        for rec in R.load_district_records(s, did):
            decisions[rec["rec_key"]] = R.decide(rec)["decision"]

by = {}
for rk, src, fn, fk, nc, nt, us in reps_rows:
    by.setdefault(rk, []).append(dict(source=src, filename=fn, file_kind=fk,
                                      n_chars=nc, n_times=nt, usable=us))

# Replay both ways. `best_send` reads NON_SWAPPABLE_SOURCES at CALL time, so swapping the module
# constant reconstructs the pre-#862 pool exactly — no second copy of the ranking logic here.
REAL = R.NON_SWAPPABLE_SOURCES
PRE_862 = frozenset(REAL) - set(R.CHROME_SOURCES)          # slices only, as before the fix


def replay(non_swappable):
    R.NON_SWAPPABLE_SOURCES = non_swappable
    out = {}
    for rk in canonical:
        try:
            out[rk] = tuple(x["file"] for x in
                            R.best_send(by.get(rk, []), _js(sigs.get(rk)), _js(facets.get(rk))))
        except Exception:                                   # noqa: BLE001 — a bad row must not end the sweep
            continue
    return out


pre, post = replay(PRE_862), replay(REAL)
R.NON_SWAPPABLE_SOURCES = REAL                              # never leave the module mutated

is_chrome = lambda files: any(f in CHROME_FILES for f in files)   # noqa: E731

print("=" * 78)
print(f"corpus: {len(canonical):,} canonical records ({len(by):,} with representations)")

print("\nC1  the invariant — chrome as the first send")
now = [rk for rk, v in post.items() if is_chrome(v)]
print(f"    records whose best_send returns a CHROME rep: {len(now)}"
      f"   {'<-- BLOCKER' if now else '(0 — the #862 invariant holds)'}")
for rk in now[:10]:
    print(f"      {rk} -> {post[rk]}")

print("\nC2  the population #862 removed (replayed, not recalled)")
was = [rk for rk, v in pre.items() if is_chrome(v)]
changed = [rk for rk in post if pre.get(rk) != post.get(rk)]
print(f"    chrome was the send PRE-fix on : {len(was):,}")
print(f"    best_send output changed on    : {len(changed):,}")
bydec = collections.Counter(decisions.get(rk, "?") for rk in was)
print(f"    those records by DECISION      : {dict(bydec)}")
send_affected = [rk for rk in was if decisions.get(rk) == "send"]
print(f"    SEND-decided among them        : {len(send_affected)}"
      f"   {'<-- a dispatch decision changed' if send_affected else '(0 — no dispatch changed)'}")
byfile = collections.Counter(f for rk in was for f in pre[rk] if f in CHROME_FILES)
print(f"    by file: {dict(byfile)}")
tie = sum(1 for rk in was
          if not max((r.get("n_times") or 0) for r in by[rk] if r["filename"] in pre[rk]))
print(f"    won the pool on the n_chars TIE-BREAK (0 clock times): {tie:,}")
print("    (that split is the point: only a handful came from #841 scoring the segments — the rest")
print("     had been picking nav menus since REQ-091, unseen because rejects never serialize a send.)")

print("\nC3  the residual gap (#867) — chrome holds times the sendable pool does not")
gap = []
for rk in canonical:
    rs = by.get(rk, [])
    pool_t = max([(r.get("n_times") or 0) for r in R.sendable_text_reps(rs)] or [0])
    ch = [(r["filename"], r.get("n_times") or 0) for r in rs
          if (r.get("source") or "") in R.CHROME_SOURCES and (r.get("n_times") or 0) > pool_t]
    if ch:
        gap.append((rk, decisions.get(rk, "?"), tiers.get(rk), pool_t, ch))
print(f"    records where a chrome rep out-counts the whole sendable pool: {len(gap)}")
gap_send = [g for g in gap if g[1] == "send"]
print(f"    of those, SEND-decided: {len(gap_send)}"
      f"   {'<-- BLOCKER: evidence no automated path can reach' if gap_send else '(0 — nothing live is losing evidence)'}")
for rk, dec, tier, pool_t, ch in gap[:8]:
    print(f"      {rk} [{dec}/tier {tier}] pool_max={pool_t}  chrome={ch}")
print("    Root cause is #863 (page.txt read at DOM-ready+2.5s, segments at end-of-capture), so")
print("    this count should FALL toward 0 when #863 lands. A rise means the timing split widened.")

print("\nC4  #868 — records whose ONLY usable text is chrome (the degenerate fallback)")
chrome_only = []
for rk in canonical:
    rs = by.get(rk, [])
    raw_usable = [r for r in rs if r.get("file_kind") == "text" and r.get("usable") and r.get("filename")]
    if raw_usable and not R.sendable_text_reps(rs) and any(
            (r.get("source") or "") in R.CHROME_SOURCES for r in raw_usable):
        sig = _js(sigs.get(rk))
        chrome_only.append((rk, decisions.get(rk, "?"), tiers.get(rk),
                            bool(sig.get("visual_text_gap")), post.get(rk)))
print(f"    records with a chrome-ONLY usable text pool: {len(chrome_only)}")
unguarded = [c for c in chrome_only if not c[3]]
print(f"    of those NOT already routed by visual_text_gap: {len(unguarded)}"
      f"   {'<-- check the fallback is intended' if unguarded else '(0 — vision routes them one branch earlier)'}")
for c in chrome_only[:8]:
    print(f"      {c[0]} [{c[1]}/tier {c[2]}] visual_text_gap={c[3]} -> {c[4]}")

print()
if not canonical or not by:
    print("VERDICT: NOTHING MEASURED — no canonical record carried representations. Check the DB")
    print("         connection and that a build_signals ingest has run; a green zero here would be")
    print("         indistinguishable from a clean corpus (the standing lesson).")
elif now:
    print(f"VERDICT: BLOCKER — {len(now)} record(s) still send chrome. The #862 invariant is broken.")
elif gap_send:
    print(f"VERDICT: REVIEW REQUIRED — {len(gap_send)} SEND-decided record(s) hold clock times only in")
    print("         chrome, which no automated path can now reach. Route via #863 or reconsider.")
else:
    print(f"VERDICT: HOLDS. 0 of {len(canonical):,} canonical records send chrome; the {len(was):,} that")
    print(f"         did pre-#862 are all non-send ({dict(bydec)}), so 0 dispatch decisions changed.")
    print(f"         {len(gap)} record(s) carry chrome-only clock-time evidence — none SEND-decided;")
    print("         that population is #863's to close, and this script is how it stays watched.")
