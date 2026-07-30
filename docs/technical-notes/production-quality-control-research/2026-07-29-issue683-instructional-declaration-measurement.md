# #683 — `instructional_time`: a declaration OF the day, not an interval IN it (measured)

**Date:** 2026-07-29 · **Issue:** #683 (epic #695) · **Branch:** `fix/683-instructional-declaration`
**Protocol:** edit → full `build_signals` re-ingest → `harness.py` A/B scorecards → `tuning_ledger record`
(the standing protocol for signal-level changes — the frontier can't see them).
**Rerunnable:** `2026-07-29-issue683-instructional-declaration-measure.py` alongside this report
(the old regex frozen as a literal; `--guard-audit` splits regex-vs-guard) — committed in the #704
review round, which found the first version's claims verifiable-but-unreproducible.

> **#704 review-round CORRECTION:** the guard as first shipped included threshold hedges
> (`at least` / `more than` / `no more than` / `approximately` / `up to` / `just a few`), which the
> review proved REJECTS the canonical statutory phrasing — *"at least 330 minutes of instruction
> per day"* is a minimum-day **declaration**, semantically identical to Aspire's kept *"a minimum
> of 240 instructional minutes per school day"* — and was internally asymmetric (*"no fewer
> than"* passed). Measured with `--guard-audit`: on the full corpus the hedges changed the outcome
> of **zero** records — every real FP already fails the number+instruction+day-scope regex itself
> — so they only cost the false-negative class. The guard is now **interval antecedents only**
> (`first|last|final|within|during|after|every|each`, across an `or` conjunction). Corpus-neutral:
> still exactly 2 records fire, 0 gained; scorecards and the ledger episode below are unaffected.

## What the issue reported, and what the corpus said

The issue found ONE false positive: Bentonville's employee handbook (`0503060:a5f32ff869`) set
`instructional_time` — a strong 0.95 target vote, the highest-weighted in the bank — on the
sentence *"Attendance must be submitted during the first 30 minutes of class."*

Scanning all 3,714 text-bearing capture records and joining to the human labels showed the problem
was **not one district**. The signal fired on **15 records and was wrong on 13 of them**:

| record | label | the matching string | why it's wrong |
|---|---|---|---|
| `0503060:a5f32ff869` | `target_absent` | "during the **first 30 minutes of class**" | attendance deadline (#683's case) |
| `4000766:97161c6a76` | `school_bell_table` | "during the **first or last 10 minutes of class**" | hall-pass rule |
| `4000766:2f764d7fa2` | `school_start_end_prose` | same | hall-pass rule |
| `3800038:f962d4236d` | `school_bell_table` | "miss **more than 15 minutes of class**" | absence threshold |
| `4824000:af06722adb` | `school_start_end_prose` | "physical activity for **at least 30 minutes per day**" | PE rate |
| `5510620:acfb82a4f6` | `target_absent` | "students **practice 10 minutes per day**" | practice rate |
| `1730540:bcd9c539fb` | `target_absent` | "a reading opportunity of **60 minutes per day**" | reading rate |
| `1725260:f11472e1d7` | `target_absent` | "just a few **minutes per day**" | marketing copy |
| `0503060:55586405a4` | `target_absent` | "**no more than, 360 minutes of instruction** (4 periods) per day" | course-load ceiling |
| `0513530:86f7c6680a` | `target_absent` | "based on **Instructional Minutes**" | no number at all |
| `0634320:8f22974954` | unlabeled | "15. Physical education **instructional minutes**;" | no number |
| `0634320:e6341a6c89` | unlabeled | "compliance with the **instructional minutes** required by the state" | no number |
| `4700148:aac2f7a36e` | unlabeled | "**90 minutes of instruction** in each subject" | per-subject block |
| **`0602095:6e8db3e114`** | `school_start_end_list` | "**240 instructional minutes per school day**" | ✅ genuine |
| **`4700148:00f553bcfc`** | unlabeled | "181 instructional days with **495 minutes of instruction per day**" | ✅ genuine |

Two failure shapes, not one: a number bounding a **part** of the day (interval/threshold/rate), and
the bare phrase `instructional minutes` / `minutes per day`, which states that minutes are *tracked*
but never how many.

## The rule, and why nothing weaker discriminates

A DECLARATION requires all three — each one is load-bearing against a real corpus FP:

1. **a NUMBER** — else number-less compliance prose fires (3 records);
2. **an INSTRUCTION referent** — `minutes per class` / `in each subject` is a portion (2 records);
3. **DAY scope** (`per day` / `per school day`) — the bare `N minutes per day` shape is what the
   PE-rate, practice-rate, reading-rate and marketing FPs all matched (4 records).

Plus a **preceding-token guard** for INTERVAL antecedents only:
`first|last|final|within|during|after|every|each`, optionally across a conjunction (`first **or
last** 10 minutes` — the live KIPP OKC shape). *(Threshold hedges were in the guard as first
shipped and removed in the #704 review round — see the correction note at the top: they rejected
genuine statutory declarations while changing zero corpus outcomes.)*

`INSTRUCTIONAL_RE` alone is deliberately **not** the predicate: the guard is half the rule, so the
one home is `build_signals.instructional_declaration()` and a source pin forbids a caller from
re-spelling `INSTRUCTIONAL_RE.search(all_text)`.

**Widening stayed off the table**, per the file's own REQ-093 reversion (hours phrasings
false-positived on marketing copy; hours-in-calendar is a vision problem). Verified **strictly
narrowing** over the corpus: 15 records fired before, 2 after, **0 gained**.

## Measured delta (harness A/B, full re-ingest between)

Baseline `scorecard_20260729T160502Z` (`data=5aae82e337f0`) → after `scorecard_20260729T200738Z`
(`data=ff50b9ae932a`); labels fingerprint unchanged.

| metric | before | after |
|---|---|---|
| `lf_explicit_minutes` accuracy | **0.4545** (11 firings: 5 target / 6 non-target) | **1.0** (1 firing: 1 / 0) |
| tier A | 447 target / **62** non-target | 447 target / **58** non-target |
| tier-A precision | 0.8782 | **0.8851** (+0.0069) |
| tier-A **recall** | 0.7926 | **0.7926 (+0.0000)** |
| tier-A f1 | 0.8332 | **0.8363** |
| category-guess accuracy | 0.4800 | **0.4823** |
| topology agreement | — | **+0.0151** |

`lf_explicit_minutes` was the **worst target detector in the bank** (45% accurate); it is now the
most accurate. Ledger verdict `[OK]`, every delta non-negative, **recall flat** — the four false
tier-A sends removed cost **zero** target coverage: all five target-labeled records that lost the
signal stay tier A on other detectors (verified individually).

**The trade to name honestly:** coverage drops to `cov=0.0006` (1 labeled firing). The detector is
now narrow-but-trustworthy rather than frequent-and-noisy. If a future measurement shows genuine
declarations being *missed*, the remedy is a better reader (vision/Tier-3), not a looser regex —
the same conclusion REQ-093 reached.

## What this does NOT fix (and where it goes)

**Bentonville `0503060:a5f32ff869` is still a tier-A send.** The signal is now `false` and its
category hypothesis corrected (`explicit_instructional_time` → `school_start_end_list`), which meets
#683's acceptance — but three *other* strong detectors carry it: `lf_time_table` (12 times),
`lf_prose_pair`, `lf_heading_hours`. Those times are **staff/office hours in an employee handbook**,
which is exactly **#684**'s subject (the staff-day confusable). #683 was never going to close that
money leak alone, and the issue's sequencing (#683 then #684) is why. Re-measure the same record
after #684.
