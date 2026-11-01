# The CCD elementary/secondary teacher split — findings, research, decision (2026-11-01)

**Status: phase 1 (quarantine) BUILT on `fix/1017-quarantine-level-scopes`; phases 2–3 are their own issues.**
Issue #1017 · REQ-190 · REQ-011 amended. Corrections, when they come, are appended as dated "Correction"
bullets, never rewritten in place.

## Why

A naive check (≈415 min ÷ ≈21 students ≈ 19.8) put `teachers_elementary` LCT about 41% high (median 27.9). A
four-agent audit traced the gap mainly to definitions. The import (0 mismatches over 17,754 districts) and the
arithmetic are both correct.

CCD/EDFacts FS059 defines **Elementary Teachers** as those "classified by state and local practice as
elementary and composed of any span of grades not above grade 8". **Secondary** starts at "the next grade
following the elementary grades". The level scopes then divide those counts by fixed grade bands:

- `teachers_elementary` = (elementary + kindergarten teachers) ÷ K-5 enrollment (`models.py:987`)
- `teachers_secondary` = secondary teachers ÷ 6-12 enrollment (`models.py:993`, `calculate_lct_variants.py:736-741`)

Wherever practice puts grades 6-8 in "elementary", the numerator holds teachers whose students the
denominator does not count.

## Findings (2024-25; rerun with `2026-11-01-ccd-level-teacher-split-measure.py [--school-files]`)

**M1: unified K-12 districts (8,478).** These districts enroll students in K/1, 6, 9 and 12, report secondary
teachers, and have ≥500 students. The table compares the share of teachers each state reports as
"elementary" with the share of enrollment in K-5, K-6 and K-8:

| Group | Elementary teacher share | Reading |
|---|---|---|
| 22 jurisdictions: AZ, BIE, CA, CT, IA, IL, KS, KY, LA, MA, ME, MT, NC, ND, NE, NH, NJ, OR, PR, RI, SC, SD | 0.60–0.71 | ≈ K-8 enrollment share (0.62–0.71). In most of these, 69–100% of districts individually fit K-8 best (NJ 65%, NE 61%, BIE 44%) |
| 32 others (VA, WI, MO, MI, TX, OH, PA, NY, …) | 0.45–0.58 | Between the K-5 (≈0.44) and K-6 (≈0.52) shares. This is consistent with a K-5/K-6 cutoff plus elementary's genuinely richer staffing (school-file PTR 14.1 vs 15.9) |

So yes: in the 22, **K-12 districts too** report grade 6-8 teachers as elementary. It is not only K-8
districts.

**M2: K-8-only districts.**
- In the K-8 states, ≈100% report **0** secondary teachers.
- **OK** (100%) and **MO** (95%) do too, although their unified districts split near grade 6. That is
  classification by **school type**: every teacher in a K-8 school counts as elementary.
- In TX, OH, PA, NY, MI, WI, MN and others, K-8 districts report 20–27% of their teachers as secondary,
  roughly their grade 6-8 enrollment share (≈0.31).

"State and local practice" therefore means at least three different rules:

- grade taught, cut at K-8
- grade taught, cut at K-5/K-6
- school type

NJ looks mixed within the state.

**M3: CCD school files (the independent yardstick).** `ccd_sch_059` gives one teacher FTE per school, with
no level split. Covered: 91,667 schools, 3,148,870 FTE, 46.6M K-12 students. School sums reconcile with
the LEA totals at 98.7%.

| Band | Single-band schools | Pro-rata (each school's teachers spread over its grades by enrollment) | By CCD `LEVEL` |
|---|---|---|---|
| K-5 / Elementary | 13.8 (35,897 schools) | 14.1 | 14.1 |
| 6-8 / Middle | 15.1 (12,642) | 14.8 | 14.9 |
| 9-12 / High | 16.2 (16,355) | 15.9 | 15.8 |

The current LEA-level pairing gives **12.6** students per teacher for elementary and **20.9** for
secondary. NCES Digest 208.10 gives 15.1 elementary and 16.1 secondary. The school files agree with NCES;
the LEA pairing does not.

Effect on medians, from the #1017 audit:

- Elementary median LCT: **31.6** in the K-8-practice states vs **26.2** elsewhere.
- Applying each district's K-12 pupil/teacher ratio to its own band minutes gives elementary 22.6 and
  secondary 24.8 (stored secondary: 19.3).
- The secondary scope's agreement with the naive check was two errors cancelling.

## Research: is there an authority that catalogs each state's rule? No.

- **EDFacts FS5018** (the metadata states file with FS059). Its only teacher question is *"Are any teachers
  identified as teachers for ungraded classes?"* (Yes/No), plus an unpublished comment. Source:
  [EDPass CCD Staff FTE and Membership Metadata User Guide](https://www.ed.gov/media/document/edpass-ccd-staff-fte-and-membership-metadata-user-guide-18773.pdf).
- **NCES State Nonfiscal documentation, Appendix D "State Notes"**: logs edits only, e.g. kindergarten
  teachers folded into elementary in HI, MT and NE
  ([2013-14](https://nces.ed.gov/ccd/pdf/2015146_2013-14_State_documentation_v1a.pdf)). It has nothing on
  grade spans. NCES's own counselor imputation in the same document uses a **fixed** elementary = PK-6 /
  secondary = 7-12 split. That is NCES's convention, not a description of what states do.
- **ESEA §8101** defines elementary and secondary schools "as determined under State law". (Wording quoted
  from memory; confirm before citing.)
- **CCSSO, NASBE, NCSL and ECS** publish no 50-state table of reporting practice.
- **Licensure** is a proxy only:
  - NCTQ: elementary licences are usually K-5, but some states extend to grade 8
    ([State of the States 2021](https://www.nctq.org/wp-content/uploads/2025/03/NCTQ_State_of_the_States_Teacher_Preparation_Policy_Print_878803.pdf)).
  - AMLE lists middle-grades licence spans
    ([AMLE](https://www.amle.org/certification-licensure-by-state/)).
  - A licence span is not a reporting rule, and licensing cannot explain the school-type pattern in OK/MO.
- **Possible human confirmation** (not a pipeline input): the EDFacts Partner Support Center or the states'
  EDFacts coordinators.

## Rejected: correcting the LEA pair

We considered a per-district inference table:

- For each candidate rule (K-5 / K-6 / K-8 / school type), the school files would predict the secondary FTE
  the district *should* have reported.
- The best fit would win by a declared margin; otherwise the district is ambiguous.
- Teachers would then move to the right band, preserving the district total.
- Drift checks would run at pre-commit and pre-push.

It was rejected (Ian, 2026-11-01) for four reasons:

1. **It uses the school files to correct LEA numbers.** The corrected pair would be a roundabout school-file
   calculation, duplicating the planned school-file band scopes: two band answers on one input that would
   disagree.
2. **The inference layer carries most of the REQ-165 risk.** That means a margin, ambiguous and low-coverage
   outcomes, and a zero-secondary rule that infers from absence.
3. **The LEA split records a reporting convention, not staffing by band.** Any rule turning it into K-5 vs
   6-12 is a guess.
4. **Cost.** Two tables, an inference module and drift hooks, all to fix scopes that would then be superseded.

## Decision (Ian, 2026-11-01)

This supersedes the same-day "add school-file scopes alongside, don't replace" call, because the only
defensible correction of the LEA split runs through the school files.

1. **Phase 1, quarantine (this change).**
   - `teachers_elementary` / `teachers_secondary` are still computed.
   - `LEVEL_SPLIT_CAVEAT` labels them in the run report, the console summary, the QA JSON
     (`quarantined_scopes`) and the gate@8 sign-off preview.
   - They are removed from the QA hierarchy. Those two pairs were not containment relations, and the
     direction they expected was the artifact itself.
   - METHODOLOGY.md and DATABASE_SETUP.md carry the caveat. REQ-011 is amended and REQ-190 added.
   - No data writes.
2. **Phase 2, school-file band scopes as THE band scopes.** The design gets its own note first. Sketch:
   - `ccd_school_staffing`, loaded verbatim from sch_029 / sch_052 / sch_059 with source sha256s on every
     CCD import.
   - Each school's teachers spread over its own grades; grades roll up through the one grade→band function
     (METHODOLOGY.md band definitions, #696).
   - Drift checks: pre-commit runs the fast sha256 + SQL recompute; pre-push runs the full re-derivation from
     the raw files. Either prints `NOTHING MEASURED` rather than a green pass when inputs are absent.
   - **Reader:** `ccd_sch_052` is Deflate64-compressed, which Python's `zipfile` cannot read. Use
     `inflate64` with a size + CRC-32 check, as `public-ed-data-navigator/src/ednav/rawread.py` does. It was
     verified 2026-11-01 on the 2.35 GB member (CRC ok). This avoids a `subprocess` edge; the measurement
     script uses `unzip -p` only to keep this change dependency-free.
   - Open decisions for that note:
     - scope names
     - grade-ownership vs a fixed K-5 / 6-8 / 9-12 band
     - Pre-K teachers inside school totals
     - 4,063 schools with missing or suppressed teacher counts
     - ≈1.3% of teacher FTE that is LEA-only
     - fetching the 2023-24 school files for blended mode
3. **Phase 3, retire the LEA pair** once phase 2 validates. Stop computing it, keep the stored rows
   readable, and move `per_grade_lct_sample.py` to the school-file secondary scope.

## Review follow-ups (2026-11-01, `/code-review high` on PR #1024 → #1025–#1032, all addressed in the PR)

- **#1025 (major):** the quarantine was a presenter label only. Now the caveat, the scope list and a
  per-row `QUARANTINED_1017` token have ONE home, `infrastructure/utilities/lct_scopes.py`; the token is
  calculated into `level_lct_notes` on every level-scope row, so `lct_calculations.notes`, the CSV/parquet
  exports and any SQL reader carry it. The postgres MCP server stops advertising the two scopes as ordinary
  and returns the caveat instead of statistics (its `get_lct_summary_by_scope` never served them anyway —
  `scope_map` holds only the five base scopes, a pre-existing mismatch). **Stored rows carry the token from
  the next recompute onward**: stamping the ~30k existing rows is a live write, left to Ian (no data writes
  in this PR; the dry run differs from the pre-change dry run ONLY in that column, on those rows).
- **#1026:** measured on the 2026-11-01 dry run: 10 of the 20 outliers were `teachers_elementary`, and
  because `outliers[:20]` is cut AFTER walking `scope_order`, scopes 3–10 never appeared at all. The
  quarantined scopes are now skipped. The truncation bias itself is pre-existing and logged separately.
- **#1027:** each quarantined `scope_summary` entry now carries `caveat`; the console QA DASHBOARD prints
  a `[Q]` line per quarantined scope.
- **#1028:** `test_teachers_secondary_less_than_teachers_only` renamed to what it checks (a teacher-COUNT
  subset), REQ-011 citation updated; the `elementary >= secondary` row-count assertion kept as the
  REQ-008 availability guard it is, with its reason spelled out.
- **#1029:** `tests/test_level_scope_quarantine.py` (DB-free) pins the one-home rule, the token, the QA
  report shape, the sign-off preview's stdout and the MCP server by source; REQ-190 cites them.
- **#1030:** the sign-off preview prints the caveat ABOVE the table and marks `legacy_lct[Q]` / `pg_lct[Q]`.
  It names only `teachers_secondary` because that is the only LCT the preview shows.
- **#1031:** `models.py` docstrings and the `_k5` / `_6_12` field comments say the suffix names the
  enrollment band, not the grades taught.
- **#1032:** "largely" replaced by the measured regime medians (31.6 vs 26.2) and the PTR counterfactual
  (22.6 / 24.8); the two table rows are marked; the Level-Based QA Validation section carries the caveat.

## Acceptance properties

- **Phase 1**
  - Every numeric value in an LCT dry run is unchanged; only labels and the two QA hierarchy pairs differ.
  - The quarantine is pinned by `tests/test_qa_overall_status.py`: level scopes never gate the hierarchy,
    and the QA JSON names them.
- **Phase 2**
  - National band PTRs reproduce M3 (≈14.1 / 14.8 / 15.9 pro-rata).
  - `teachers_only` is md5-identical.
  - The regime gap in elementary median LCT (31.6 vs 26.2) mostly closes. A miss means the method is wrong;
    it is not a threshold to tune.
- **Phase 3**
  - No consumer reads the retired pair (grep + `arch-manifest`).
  - Stored rows stay readable.
