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

## Results (post-re-ingest, the corrected uncapped signal)

| check | result |
|---|---|
| **B1** sends changed | **166**, and **0** that are not `full text → timebearing_slice` |
| **B2** chars sent, swept population | 22,627,274 → 13,494,882 — **40.4% saved through the guard** |
| **B3** handbook sends differing | **0** — byte-identical |
| **B6** records losing a **pairable** school name | **0** |
| B6 records losing any name string | 124 (nav chrome + address directories on time-free pages) |
| B6 records losing a positive keyword | 33 |

Three denominators, all consistent — quote the one that matches the question:

| scope | saving |
|---|---|
| the 166 records the floor actually re-routes | **88.0%** (10,378,692 → 1,246,300) |
| the swept population (records carrying a per-page signal, i.e. PDFs) | **40.4%** |
| **corpus-wide, every dispatched record** | **16.0%** (57,229,220 → 48,096,828) |

The pre-re-ingest estimate was 15.8% corpus-wide; the realized figure is 16.0%. The estimate held.

### B2: the guard rejects most of the theoretical saving — as predicted

Raw page analysis suggested ~64.6% of characters could be dropped from PDF-bearing records;
realized is 40.4% there, because the #230 yield guard rejected **435 lossless slices**.

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

## A false PASS, and the fix (worth reading before trusting any re-run)

The first re-run **after** the re-ingest reported `VERDICT: PASS` with **0 sends changed and 0.0%
saved** — and it was meaningless. The script's baseline was `best_send(reps, …)` read from the live
DB, which by then already carried the `timebearing_slice` reps the re-ingest had written, so it
compared the post-state with itself. Worse, B6 lives inside the `if after != before` block, so with
zero changes it never ran at all: **every safety number printed 0 because nothing was measured, and
the verdict said PASS over an empty sweep.**

Two fixes, both in the script:

- the baseline now strips the floor's own reps (`reps = [r for r in reps if r["source"] !=
  TIMEBEARING_SLICE_SOURCE]`), so the same effect is measured identically before and after landing;
- zero changed sends now prints **`NOTHING MEASURED`**, never `PASS`. A verdict that cannot fail is
  not a verdict.

This is the §10.11 pattern (a measurement that could not fail) reappearing inside the verification
of a fix for a different instance of it. Worth stating plainly rather than quietly patching.

## Scope limit (confirmed, with a correction)

Dense hubs are still not solved here: `4700148:8d0058ac10` is re-scoped by the floor but the yield
guard rejects the slice, so it sends whole. This change solves *"40 pages of policy text wrapped
around 2 pages of times"*. Dense-hub output overflow is #822 (monitoring) and #823-825 (Council Lab).

**Correction to the pre-re-ingest reading.** It was recorded that Memphis "keeps 60/60 pages, so the
floor returns `[]`". That was an artifact of the truncated signal. At true 154-page resolution the
floor keeps **101/154** and trims 170,591 → 135,534 chars — the document is not uniformly dense, it
just looked that way through a 60-page window. The conclusion (dense hubs need #822/#823-825, not
this) is unchanged; the stated reason was wrong.
