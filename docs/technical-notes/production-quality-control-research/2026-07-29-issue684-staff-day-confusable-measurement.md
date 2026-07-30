# #684 — the staff day is not the student day: a CLAUSE, not a keyword (measured)

**Date:** 2026-07-29 · **Issue:** #684 (epic #128, sibling of #683) · **Branch:** `fix/684-staff-day-confusable`
**Protocol:** measure → edit → full `build_signals` re-ingest → `harness.py` A/B scorecards → `tuning_ledger record`
(the standing protocol for signal-level changes — the frontier can't see them).
**Rerunnable:** `2026-07-29-issue684-staff-day-measure.py` alongside this report. It runs all four arms
(`--presence --doc --clause --sensitivity`), **including the two the measurement rejected** — the
rejections are the load-bearing result here, so they are reproducible too. Arm 3 additionally re-checks
every record's verdict against the live `detectors.staff_day_owned`, so the report cannot drift from the
code.

> **Reading a re-run:** the `tgt`/`non`/`acc` columns are label-derived and stable, but the `tier-A`
> columns read **live** tiers — so post-fix they show Bentonville in tier B. The tier-A figures quoted
> below are the **pre-fix** state (the decision context); a re-run today shows arm 1's "tier-A non-target"
> at 9 rather than 10, and arm 3's at 0 rather than 1, for exactly that reason.

## The record, and what it proves about shape detectors

Bentonville's **employee handbook** (`0503060:a5f32ff869`, human label `target_absent`) was a **tier-A
auto-send** on four independent strong target votes. After #683 removed the `lf_explicit_minutes` false
positive, three remained — and none of them was wrong by its own rule:

| detector | conf | reading |
|---|---|---|
| `lf_time_table` | 0.85 | a real table, 12 in-window times |
| `lf_prose_pair` | 0.80 | in-window start/end pair + positive keyword |
| `lf_heading_hours` | 0.70 | a time under the heading **`bell schedule`** |

Because the page carries a genuine, well-formed table of times — of the **staff day**:

> "Elementary staff with a school start time of 7:30 a.m. are to **report to work** by 7:15 a.m. and
> **remain until** 3:00 p.m." · "Junior High **staff are to report** at 8:05 - 3:50." · "Zero Hour
> **staff members** are to report from 7:00 am - 2:45 pm."

`positive_kw` on this record includes `bell schedule`, `school hours`, `school day`, `start time`,
`arrival`, `homeroom`. **Every shape signal the bank looks for is authentically present. The shape is
right; the referent is wrong.** The document mentions real student start times only as the *anchor* for
an employment obligation, and never states student dismissal — so every extractable pair on the page is a
staff-day pair, and a council sent here returns staff hours with no way to know it.

## What the corpus rejected — twice

#684's own shape-of-fix proposed (1) widening `OFFICE_HOURS_KW` to the observed phrasings and (2) voting
on a staff referent *near the times*. Measured over all **3,559** text-bearing records joined to **1,754**
human labels (564 target / 1,190 non-target; 505 labeled tier-A, 447 target / 58 non-target):

### Arm 1 — a staff word NEAR a time (`--presence`)

| vocabulary | window | fires on targets | on non-targets | acc | tier-A targets it would demote |
|---|---|---|---|---|---|
| today's `OFFICE_HOURS_KW` | 100 | 78 | 81 | 0.509 | **55** |
| today's `OFFICE_HOURS_KW` | **140** | **84** | **88** | **0.512** | **59** |
| today's `OFFICE_HOURS_KW` | 220 | 91 | 97 | 0.516 | 63 |
| + the observed obligation phrasings | 140 | 87 | 99 | 0.532 | 61 |
| + bare `staff`/`faculty`/`employee` | 140 | 144 | 163 | 0.531 | 106 |

`acc` = the share of firings landing on labeled **non**-targets, which is what a negative detector is
supposed to do. **~0.51 is a coin flip.** At the best point the rule would have demoted **59 tier-A
targets to remove 10 false sends** — a 6:1 loss. Widening the vocabulary made it *worse*, not better.
The confusable was anticipated in-code ("the research's #1 confusable, §5.2") and the vocabulary was
already right; **presence was never the discriminator**, because staff language is everywhere on real
school pages.

### Arm 2 — a document-level `/employee handbook/` match (`--doc`)

Fires on 17 labeled records — **11 of them real targets** (2905790, 3800038, 5507770 carry genuine
`school_bell_table` / `district_hub_by_school` / `school_start_end_prose` labels). Districts publish bell
tables *inside and beside* their staff handbooks. Net-negative; rejected.

*(This is the third occurrence of the REQ-093 lesson — the intuitive keyword widening measures out
net-negative. It is why the protocol measures before editing, not after a review finding.)*

## What discriminates: the obligation CLAUSE, scored relationally

A staff **SUBJECT** governing a duty **VERB** governing the **TIME** — the grammar of an employment
obligation, which a student handbook does not use ("students should arrive by", never "are to report to
work by" / "remain until" / "clock in"). Then, instead of a dominance threshold, a **comparison**:

> do the duty clauses govern **more** of this text basis's in-window times than student-referent language
> does?

| candidate | targets | non-targets | acc | tier-A tgt | tier-A non |
|---|---|---|---|---|---|
| duty clause present (`>= 1`) | 0 | 3 | 1.000 | 0 | 1 |
| **duty > student, per basis, ANY basis** | **0** | **1** | **1.000** | **0** | **1** |

**Zero labeled targets at any variant.** Seven records corpus-wide carry a duty clause at all; exactly
**one** reads staff-owned — Bentonville. The other six are the shape a bare `duty >= 1` rule would have
wrongly demoted (Alliance `3805460:84db5b8100`: 1 duty clause vs **23** student-referent times).

**Why a comparison and not a threshold.** A dominance level (`duty_share >= 0.5`) tuned on a single
record is the "measurement that could not fail" — CLAUDE.md's standing lesson, which has now bitten this
project four times. The relational form introduces no tunable number at all.

### Sensitivity — the check that lets this measurement fail (`--sensitivity`)

Bentonville's `student_ref_times = 0` sits near a boundary: "the student contact day" appears ~180 chars
before its first duty time. So the verdict was re-run across student windows and both combinators:

| student window | ANY fires | ALL fires |
|---|---|---|
| 100 | 4 | 3 |
| **140 (shipped)** | **1** | **1** |
| 220 | 1 | 1 |
| 300 | 1 | 1 |
| 500 | **1** | **0** ← loses Bentonville |

The shipped point (**ANY @ 140**, reusing the existing `NONSTANDARD_NEAR_CHARS` grain) sits on a
**140–300 plateau**: a 2× change in the window does not move the verdict. `ALL` is the fragile
combinator, which settles a choice the corpus alone could not — see below.

## The two halves of the fix (a negative vote alone could not have worked)

1. **`lf_staff_day`** — a new negative detector, registered **`hard`** in `UNDERMINE_CLASS`. Hard, not
   soft, because the wrong-**referent** case is not the wrong-**day** case: a soft wrong-day *mention*
   deliberately leaves a real schedule TABLE sending (#60/#528) since the table is still the student day,
   whereas here the table **is** the staff day. This demotes `lf_time_table` and `lf_prose_pair`.
2. **`lf_heading_hours` consults the same predicate.** `lf_heading_hours` is `STRONG_STRUCTURAL`, and by
   deliberate design **nothing undermines `STRONG_STRUCTURAL`** (`combiner.py`'s first branch is
   unconditional). So step 1 alone would have left this record a tier-A auto-send. The verdict has to be
   read at the *source* of the structural target, where it emits the shared `lf_office_hours` negative —
   the same confusable the pre-existing heading-**label** test already caught, just reached a second way.
   `staff_day_owned()` is the ONE home for the comparison, source-pinned by test.

**ANY, not ALL** (the corpus rated them identically at 140): a page carrying *both* a real student table
and a staff table is precisely the record a human should adjudicate, and the risk is asymmetric — a false
positive costs review time at gate@5, a false negative spends money on facts nobody can interpret. ANY is
also the robust combinator per the sensitivity table.

**HOLD, never veto** (#241's posture, and the issue's own read): the outcome is **tier B / review**, not
a drop to D. An employee handbook can contain the student bell table too.

## Measured delta (harness A/B, full re-ingest between)

Baseline `scorecard_20260730T031042Z` (`data=ff50b9ae932a`) → after `scorecard_20260730T032506Z`
(`data=95f8c605220c`); config + labels fingerprints unchanged. Recall floor enforced in-transaction:
`tier-A+B recall=0.9947 >= 0.98` **OK**.

| metric | before | after |
|---|---|---|
| tier A | 447 target / **58** non-target | 447 target / **57** non-target |
| tier-A precision | 0.8851 | **0.8869** (+0.0018) |
| tier-A **recall** | 0.7926 | **0.7926 (+0.0000)** |
| tier-A f1 | 0.8363 | **0.8371** |
| A+B precision / recall | 0.5431 / 0.9947 | **unchanged** |
| `lf_staff_day` | — | cov 0.0006, **acc 1.0** (1 firing: 0 target / 1 non-target) |
| `lf_heading_hours` | cov 0.2013, acc 0.9122 (353: 322/**31**) | cov 0.2007, **acc 0.9148** (352: 322/**30**) |
| `lf_office_hours` | cov 0.0410, acc 0.3750 (72) | cov 0.0416, **acc 0.3836** (73) |
| `lf_staff_day` facet precision (#108) | — | **1.0** (1/1 facet-tagged) |
| category-guess accuracy | 0.4823 | 0.4823 |

`tuning_ledger` verdict **`[OK]`**, every delta non-negative. **Exactly one record moved** —
`0503060:a5f32ff869`, `send`/A → `review`/B — and no target-labeled record changed tier.

**The trade to name honestly:** coverage is `0.0006`, one labeled firing. This detector is
narrow-but-trustworthy rather than frequent-and-noisy — the same shape #683 landed on, and the same
conclusion: if a future measurement shows staff handbooks *slipping through*, the remedy is more clause
vocabulary measured the same way, **never** the presence rule this report rejected.

## Cost + console

- **Ingest cost.** The student-referent scan runs only when a duty clause exists to weigh it against
  (the `#537` S3-guard shape), so 99.8% of records skip a whole-text regex pass; the per-basis in-window
  offsets are now hoisted and shared with the wrong-day signal instead of recomputed. Full re-ingest:
  552 s wall for 116 districts / 3,559 records.
- **Console — verified end-to-end, 11/11**, against the live `0503060:a5f32ff869` record via
  `infrastructure/scraper/verify_684_console.mjs` (committed and rerunnable, deliberately not a
  `*.test.mjs` since it needs a live server + DB). It checks the Signals-panel row renders with its real
  counts ("9 governed by report/remain clauses, vs 0 near student language"), the confounder checkbox is
  pre-checked *by `lf_staff_day`*, the glossary + row tooltip define the shape, the server-supplied
  `staff_duty` weight reaches the client, and the strip paints 2 events when the server voted and **0**
  when it did not. The same DOM/source invariants are pinned DB-free in
  `tests/test_684_staff_day_confusable.py`, so they can't silently disappear from CI.
- **Console.** The heat-strip paints a `staff_duty` event (−0.70, mirroring the vote) at each duty
  clause, but **only when the server actually voted `lf_staff_day`** — the client never re-derives the
  comparison (#521's guardrail). The `office_building_hours` Axis-2 checkbox is now hinted by **both**
  detectors and its tooltip names the employee-handbook shape, so a labeler can record the
  agree/disagree the tuning loop consumes. Both regexes are pinned verbatim against the Python; the JS
  lookback is **codepoint-exact** (`Array.from(...).slice(-90)`), because unlike #683's `$`-anchored
  guard this subject regex is unanchored, so a merely-wider window would change what it matches.

## What this does NOT fix

`lf_time_table` and `lf_prose_pair` still **fire** on this record — correctly, by their own rules; they
are demoted, not silenced, and the record now reaches a human instead of a council. The three votes are
still visible at gate@5, which is the point: the human sees the same evidence the scorer did, plus the
staff-day reason that demoted it.

Nothing here helps a staff handbook whose obligation prose the text extractors mangle beyond regex reach.
That is the standing REQ-093 conclusion for this whole family — a **vision/reader** problem, not a
keyword one.
