# The absolute time-bearing page floor (#821) — Pass B measurement

**Date:** 2026-08-17 · **Script:** `2026-08-17-timebearing-floor-measure.py` (rerunnable, read-only)
**Verdict: PASS.**

## What this replaces

`harvest_schedule_pages` is a peak-RELATIVE selector (`cut = max(6, peak × 0.5)`) gated behind
`is_handbook`. Per-page time counts follow a power law, so a threshold set off the peak discards the
tail: measured, it **loses 26.3% of the corpus's clock times** and selects nothing at all in 887 of
1,640 multi-page docs. #796 proposed widening its trigger; that was rejected on measurement.

The floor keeps page N iff `n_times > 0` **or** `instr` **or** `N == 1` **or** `N±1 is time-bearing`
— lossless on the time signal by construction.

## Results (full corpus, 3,532 records with a per-page signal)

| check | result |
|---|---|
| **B1** sends changed | **155**, and **0** that are not `full text → timebearing_slice` |
| **B2** chars sent | 22,165,144 → 18,665,966 — **15.8% saved through the guard** |
| **B3** handbook sends differing | **0** — byte-identical |
| **B6** records losing a **pairable** school name | **0** |
| B6 records losing any name string | 113 (nav chrome + address directories on time-free pages) |
| B6 records losing a positive keyword | 25 |

### B2: the realized saving is a quarter of the theoretical one — as predicted

Raw page analysis suggested ~64.6% of characters could be dropped. **Realized: 15.8%**, because the
#230 yield guard rejected **446 lossless slices**.

That gap is the counter asymmetry, and it is working as designed. A slice's `n_times` comes from
`build_signals.time_positions` (regex **plus** `to_minutes` validity filtering); a general text rep's
comes from Stage 4's different regex with **no** validity filter. For identical text
`stage4_count ≥ build_signals_count`, so the slice is systematically *disadvantaged* and a provably
lossless slice can still lose and fall back to the full read. Fail-safe, and the reason the raw
figure was only ever an upper bound. **Do not "fix" this into a like-for-like comparison** —
aligning the counters would move the handbook branch too, which byte-identity forbids.

Realized slice/full char ratio: p10 0.18, median 0.54, p90 0.76. `MIN_SLICE_SAVING_FRAC = 0.20`
(i.e. ratio ≤ 0.80) therefore sits just above the p90 of what the guard already admits — it is
trimming genuine churn, not shaping the distribution.

### B6: the raw name diff over-reports, and it nearly read as a blocker

The first version of this check counted any school-name string lost from the slice and flagged 12
records. Inspection of `2302820:e4ae69a65b` showed p22 is a **mailing-address directory** listing
five real schools and **zero** clock times. A fact is a `(school, start, end)` triple, so a name on a
page with no times cannot contribute one — losing it loses nothing extractable.

The check now reports both, and blocks only on the second:

- **names lost at all** — 113, expected non-zero (chrome, footers, directories).
- **pairable names lost** — a name co-occurring with times somewhere in the full document and absent
  from the slice: **0**. This is the end-to-end test of the lossless claim: "every time-bearing page
  is kept" is about *pages*; this checks the *bytes* actually reach the slice.

A second measurement flaw surfaced here too: `SCHOOL_RE`'s `\s+` spans a page join (form feed and
`\n\n` are whitespace), so a name read off the concatenated slice could absorb a trailing word from
the previous page and normalize differently — a phantom "pairable loss" on `3200480:9fc7826938`
(`'Bus\n  School'`). The page was in the slice; only the measurement was wrong. Both sides are now
computed **per page**.

### Accepted, measured trade: 25 records lose a positive keyword

Words like `arrival`, `dismissal`, `school day`, `bell schedule` sitting on a time-free page more
than one page from any time. This does **not** affect scoring — `positive_kw` is computed over the
record's full text reps, not over the slice — only what the council reads, and a heading with no
times beneath it yields no facts. If it ever matters, widening the neighbour window is the lever.

### Safety terms cost about half the pages, and that was the point

Over 828 scoped documents: `times + instr` alone keeps 2,241 pages; adding `first + neighbours`
keeps 5,333 (+3,092). That is the price of the two terms that close the identity and
name/time-straddle risks — paid deliberately, and now measured rather than assumed.

## Scope limit (confirmed)

**B4 found none of the named dense hubs in the changed population**, exactly as predicted. Memphis
`4700148:8d0058ac10`, Orange `1201440:b8f930171d` and Broward `1200180:52b4f372cd` are genuinely
dense — every page carries times, so the floor returns `[]` ("nothing to scope, send it whole").
This change solves *"40 pages of policy text wrapped around 2 pages of times"*. Dense-hub output
overflow is a different problem, tracked in #822 (monitoring) and #823-825 (Council Lab experiments).

## Caveat on these numbers

The sweep replays against the **stored** `pages` signal, which predates the cap fix (#827): it is
truncated at 60 pages and carries no `instr` field. The measurement is therefore **conservative** —
after a re-ingest the floor will see whole documents and the instructional-declaration term will be
live. Re-run this script after the re-ingest to get the true figures.
