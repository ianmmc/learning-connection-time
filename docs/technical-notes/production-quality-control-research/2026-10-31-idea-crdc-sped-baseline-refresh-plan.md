# IDEA 618 / CRDC SPED baseline refresh — findings and plan (2026-10-31)

**Status: PLANNED.** Tasks are sub-issues of epic #724: T1 #999 · T2 #1000 · #960 · T3 #1001 · T4 #1002 ·
T5 #1003 · T6 #1004. Nothing here is implemented. Corrections, when they come, are appended as dated
"Correction" bullets, never rewritten in place.

## Why

The SPED segmentation (REQ-018: `core_sped`, `teachers_gened`, `instructional_sped`) estimates each
district's SPED/GenEd split from **2017-18** ratios: IDEA 618 personnel (state SPED teacher/para FTE),
IDEA 618 child count + educational environments (state self-contained share), CRDC (LEA SPED
proportion) and CCD 2017-18 membership. Every other LCT input is 2024-25. REQ-026 tolerates this only
through an explicit exemption ("SPED baseline … exempt from the window as a ratio proxy").

Newer releases, all outside COVID_EXCLUDED_YEARS, are on disk (downloaded 2026-10-30; provenance and
sha256 in each folder's `SOURCE.md`; `data/raw` is gitignored):

| Component | In use | On disk | Folder |
|---|---|---|---|
| IDEA personnel (state) | 2017-18 | **2023-24** (no 2024-25 published yet) | `data/raw/federal/idea-618/2023_24/` |
| IDEA child count + environments (state) | 2017-18 | **2024-25** | `data/raw/federal/idea-618/2024_25/` |
| IDEA environments + child count (LEA) | — | **2024-25** | same |
| CRDC enrollment (school → LEA) | 2017-18 | **2023-24** (released 2026-08) | `data/raw/federal/crdc/2023_24/` |
| CCD LEA membership (CRDC denominator) | 2017-18 | 2023-24, 2024-25 | `data/raw/federal/nces-ccd/` |

Refreshed, the inputs span 2023-24 → 2024-25 (REQ-026 span 1, no flag), so the exemption can be
**retired** rather than defended. Benefits/risks were assessed 2026-10-30 (session record); the
operative risks are restated per task below.

## Prerequisite — already built, not yet merged

The parser hardening that makes this refresh safe is PR #1005 (`fix/975-989-review-findings`,
opened 2026-10-31, **not yet merged**): header row sought by content, every
column by name (#975), closed-world environment vocabulary + missing-Total guard (#982), CCD row cap
(#976), year-keyed SEA selects (#983/#984), AST year scanner (#980), wiring tests (#981). **Merge it
first**; every task below assumes it. Issues #975–#989 close with it.

## Findings measured 2026-10-31 (what the code must handle)

1. **IDEA relabel — "Ages 6-21" → "School Age".** State child count 2024-25: environments are
   `Total, School Age`, `Separate School, School Age`, `Residential Facility, School Age`,
   `Total, Early Childhood`, `Separate School, Early Childhood`, `Residential Facility, Early Childhood`
   (the four `Inside regular class …`, `Home`, `Homebound/Hospital`, `Correctional Facilities`,
   `Parentally Placed …`, `Separate Class`, `Service Provider Location` and the four `Services in …`
   labels are unchanged). Year cell is `2024` (2017-18: `2017`). The 6-21 count column is gone; the
   school-age total sits in a column that normalizes to `Age 5 (School Age)-21`, with a separate
   `Age 5 (School Age)` column. Personnel 2023-24: types are `Special Education Teachers for School Age`
   / `… Paraprofessionals for School Age` (and `… for Early Childhood`); year cell is `2023-2024`;
   one header wraps (`…Certified/ Paraprofessionals…` — handled by #975's `normalize_header`).
   The hardened parsers already **refuse** both files (G2 fires) — verified 2026-10-31.
2. **Definition shift, not just a relabel.** Since the 2020-21 collection, kindergarten 5-year-olds are
   reported in the school-age file (FS002/FS5003) and excluded from early childhood (FS089) — so
   "School Age" = 6-21 **plus** kindergarten 5-year-olds. Personnel "School Age" follows the same
   population. Mixing a 2017-18 component (6-21) with a 2024-25 one (5K-21) is a definition mismatch;
   refreshing ALL components together keeps one definition. The 5K share must be measured.
3. **CRDC 2023-24 reserve codes.** `Enrollment.csv` (97,094 schools, 146 columns) adds nonbinary
   `_X` columns (`TOT_ENR_X`, `SCH_ENR_IDEA_X`, …) — **every** school carries `-10` (ED removed
   nonbinary data). **1,835 schools carry `-9`** in `TOT_ENR_M/F` and `SCH_ENR_IDEA_M/F`. The live
   importer's `safe_int` parses negatives as numbers and `if x:` is true for them (#960) — at 2023-24
   scale this would subtract thousands of students from LEA totals. -9 is historically "not applicable";
   -10 is undocumented in what was searched (the zip ships no manual) — pin both from the 2023-24 data
   dictionary before import.
4. **Nonbinary undercount.** LEA totals built as M+F miss any student reported only as nonbinary. Size
   it against CCD 2023-24 membership (on disk) before relying on CRDC totals.
5. **LEA-level IDEA environments are usable but suppressed.** `beducationalenvironmentslea2024-25.csv`:
   `School Age Inside regular class less than 40%` is `-8` (small-cell suppression) on 5,186 LEA rows,
   blank on 1,060, `-9` on 7. Measured 2026-10-30: suppressed LEAs are 28% of districts but hold 6.6% of
   SPED students. A per-LEA self-contained share is therefore feasible with a state fallback.
6. **Schema is single-vintage.** `sped_state_baseline` is keyed by `state` alone and `sped_lea_baseline`
   by `lea_id` alone — a refresh as written would OVERWRITE 2017-18, leaving no side-by-side comparison
   and no rollback path except a dump.
7. **The ratio vintage never enters temporal validation.** `calculate_lct_variants` tracks
   `sped_estimates.estimate_year` (2024-25 after #972) as the SPED source year; the baseline vintage
   lives only in `sped_estimates.baseline_year` and is checked by nothing. The REQ-026 "exemption" is
   implicit — retiring it means making the ratio vintages visible to the window, or deciding (and
   recording) that they stay outside it.

## Tasks (sub-issues of #724), in dependency order

| # | Task | Depends on | Decision for Ian? |
|---|---|---|---|
| T1 #999 | Multi-vintage SPED baseline schema + explicit `--baseline-year` in `apply_sped_estimates` | prereq | — |
| T2 #1000 | IDEA vintage profiles: parse 2024-25 child count + 2023-24 personnel | prereq | — |
| #960 | CRDC reserve codes → missing (shared sentinel helper) | — | NULL vs partial-sum-plus-flag |
| T3 #1001 | CRDC 2023-24 LEA import paired with CCD 2023-24 membership | #960, T1 | — |
| T4 #1002 | Read-only before/after measurement script (rerunnable, committed) | T1–T3 | — |
| T5 #1003 | Adopt the refreshed baseline: re-apply estimates, recalc LCT, retire the REQ-026 exemption | T4 + Ian sign-off | **adopt? School Age vs 6-21? ratio vintage in window?** |
| T6 #1004 | Follow-up: LEA-level self-contained share (IDEA LEA environments) + LEA SPED count source | T5 | **methodology change** |

### Acceptance properties (how the plan can fail)

- **A1 (T1).** After the migration the 2017-18 baseline rows are unchanged value-for-value, and
  `apply_sped_estimates --baseline-year 2017-18 --year 2024-25` reproduces today's 2024-25
  `sped_estimates` exactly (0 rows differ). A fresh `create_all()` DB and a migrated DB agree (the
  `_PRECIOUS_ALTERS`-style twice-declared DDL rule, if the column is precious; these are LCT tables).
- **A2 (T2).** The 2017-18 parse output is identical before/after (56 states, 6,122,215 / 985,809).
  The 2024-25 child count reconciles per state against `Total, School Age` (G1) and the 2023-24
  personnel loads all states that report; an unknown label in either still fails (G2). Each vintage's
  file is refused if its sha256 differs from `SOURCE.md` (ED revisions must be a deliberate re-pin).
- **A3 (#960/T3).** No negative value reaches `sped_lea_baseline`; a fixture row with -9 / -10 is
  excluded; the CRDC M+F total vs CCD 2023-24 membership per-LEA comparison is reported with its
  distribution, and the tolerance the importer enforces is the measured one, not a guess.
- **A4 (T4).** The script imports the production parse/estimate functions (never re-implements them),
  carries an explicit `NOTHING MEASURED` verdict, and reports: per-state ratios old vs new; the 5K share
  of school-age counts; Σ estimates and each SPED scope's mean/median/capped-at-360 old vs new with the
  `instructional` scope as an unchanged control; CRDC-vs-CCD totals; the ESSER check (SPED teacher +
  para FTE growth 2017-18 → 2023-24 vs SPED child-count growth — 2023-24 personnel is the last
  pre-cliff year and may overstate staffing paired with 2024-25 enrollment).
- **A5 (T5).** A `pg_dump` of the four SPED/LCT tables precedes the write (restore-verified row counts);
  re-import goes through the SPED migration scripts only, **never `rebuild_database.py`** (#941 — its
  phase 6 destroys Stage-9 bell schedules). The before/after receipt is posted to the issue; the
  control scope does not move. REQ-018, REQ-026, METHODOLOGY (SPED section), DATA_SOURCES and the
  CLAUDE.md "SPED baseline" line are amended in the same PR; the ledger hygiene suite passes.
- **A6 (T6).** Not started until T5 lands (so the before/after attributes movement to one change at a
  time — the #970 lesson).

## Order of operations

1. Merge `fix/975-989-review-findings`.
2. T1 and T2 in parallel; #960 then T3.
3. T4 — run it, post the numbers, **stop for Ian's call** on the three T5 decisions.
4. T5 on Ian's go-ahead (LCT recalculation is a data write).
5. T6 as a separate PR and before/after.
