# School-file band teacher scopes — plan and roadmap (2026-11-01)

**Status: PLAN — proposals below await Ian's calls (D1–D8); no code yet.** Phase 2 of #1017 (REQ-190),
tracked as #1022 under epic #724. Findings that motivate it: `2026-11-01-ccd-level-teacher-split.md`.
Corrections, when they come, are appended as dated "Correction" bullets, never rewritten in place.

## Goal

Three band teacher LCT scopes — K-5, 6-8 and 9-12 — whose numerator is the teacher FTE attributed to
**exactly the grades** the denominator counts and the minutes cover (REQ-190). They replace the
quarantined `teachers_elementary` / `teachers_secondary` (retired in #1023), and the per-district math
that produces them is stored in `lct_db`, visible and checkable line by line.

## What the code says today (verified 2026-11-01)

| Finding | Evidence | Consequence for the plan |
|---|---|---|
| **No production code reads `ccd_sch_052` or `ccd_sch_059`.** Only `ccd_sch_029`/`129` are read, by `acquisition/common/school_sampling.py` (`_sch_file`, `_district_schools`). | grep; `school_sampling.py:445-552` | A new reader and a new table are needed. |
| **`ccd_sch_052` is Deflate64.** Python's `zipfile` refuses it; `inflate64` is not a dependency. | `unzip -v`: Def64N; requirements.txt | New dependency (T2). The size+CRC reader in `public-ed-data-navigator/src/ednav/rawread.py` is verified on the 2.35 GB member. |
| **The LCT layer cannot import any band rule.** All of them live in `acquisition/`; import-linter forbids `database`/`scripts` → `acquisition` (pyproject.toml:55-59). `utilities/` is importable by both (precedent: `school_year.py`, `lct_scopes.py`). | agent map, `lint-imports` | The canonical grade→band map moves to `utilities/` (T1). |
| **The canonical K-5/6-8/9-12 map is spelled at least four times:** `school_sampling.BANDS` (:71), `stage9_incorporate/per_grade._canon_band` (:71, reads BANDS), `scripts/analyze/per_grade_lct.ELEM_GRADES/SEC_GRADES/_CANON_BAND` (:25-31), `scripts/extract/extract_grade_level_enrollment.MIDDLE/HIGH_GRADES` (:60-61). | grep | Implemented-twice drift to remove in T1, before a fifth copy appears. |
| **Placement and per-grade attribution diverge for 37% of schools.** 35,889 of the 98,197 schools `school_index()` places span more than one canonical band; one-band-per-school would misattribute them. | measured, `school_index(2024-25)` | Attribute **per grade** (relation 3 of #696), not per school. The #498 carve-out and `recursive_band_groups` stay in acquisition; this design does not need them. |
| **356 districts' live LCT rows use 2023-24 staffing** (269 with 2024-25 enrollment, 87 with 2023-24); 16,652 use 2024-25. **No 2023-24 school files are on disk**, and `fetch_nces_ccd.py`'s catalog has no 2024-25 entry and no school 052/059 entry at all. | `lct_calculations`; `fetch_nces_ccd.py:36-69` | D6; T3. |
| **The pre-push hook and the DB-free test job forbid DB access by design** (`.githooks/pre-push:12-14`; `tests/conftest.py` fails any unmarked test that opens Postgres). The pre-commit hook's only DB check warns and exits 0 when Docker is down. | read | The "full re-derivation at pre-push" in #1022's first sketch is **wrong as written**; D7 and T8 replace it. |
| **`chk_staff_scope` lives only in migrations** (002, redefined 014) and `schema.sql`; `models.py` does not declare it. `schema.sql` is a generated snapshot. Next migration number: **033**. | `014_add_staff_scope_to_lct.sql:48-65`; `models.py:504-510` | A scope addition is a drop-and-re-add migration (T7). |
| **REQ-008 contradicts itself** ("exactly 8", lists 10, "all 10") and no test counts scopes. | `REQUIREMENTS.yaml:236-247` | Fix with T7 (amend REQ-008 to a scope REGISTRY, pinned by a test). |
| **School teacher sums reconcile with the LEA files:** 3,177,662 vs 3,220,261 FTE (98.7%); 95.3% of LEAs within ±5%. 4,063 schools have missing/suppressed counts. | M3 of the measure script | D4/D5. |

## Design (proposed)

> **Revised 2026-11-01: D1/D2 and D3 decided (Ian). This block supersedes items 2–3 below where they conflict.**
> - **Bands are the pipeline's school bands**, not fixed K-5/6-8/9-12. A school goes to its band by
>   `school_sampling.primary_bands_for` (`LEVEL` with the #498 carve-out). This is the same rule that bands
>   the bell minutes, so minutes, teachers and students come from the same schools. Single-band schools
>   (96.1% of teacher FTE, M1) are attributed whole.
> - **Combined schools** (`primary_bands_for` returns more than one band: K-12-style 3.7%, 6-12 0.1% of
>   FTE) are split by grade over the fixed-band overlap (`bands_for`), the pipeline's own fallback for
>   them. `lea_grade_teacher_fte` keeps its per-grade grain, but for single-band schools it is
>   attribution, not a split.
> - **Scope names:** `teachers_band_elementary`, `teachers_band_middle`, `teachers_band_high`. They never
>   reuse `teachers_elementary`, the quarantined LEA pair, whose rows stay readable after #1023.
> - **Each band row records its grade span** (lowest–highest grade served by the band's schools in
>   that district, e.g. K-5 or K-8), so a cross-district comparison can see and filter the variation.
> - **Pre-K (D3):**
>   - Subtract the district's LEA-reported `Pre-kindergarten Teachers` FTE from its school teachers.
>     The FTE is allocated across the district's schools in proportion to Pre-K membership.
>   - Drop the Pre-K students.
>   - A district with Pre-K students and a reported Pre-K FTE of 0 has nothing subtracted and is flagged
>     (1,207 LEAs in 2023-24).
>   - Pro-rata is rejected: it overstates Pre-K teachers by 40% (M2).
>   - **A district whose school rows carry no Pre-K membership (Michigan, and 354 districts elsewhere)
>     has no allocation key.** It takes the fallback in "Pre-K without a school key" below.
> - **Formula:** for band B, over the district's reporting schools in B (plus the B-grades of its
>   combined schools):
>   `LCT_B = minutes_B × Σ(teachers − allocated Pre-K FTE) / Σ(membership − Pre-K membership)`.
>   `minutes_B` is the band's own Stage-9 gross minutes (the mode over the same band's schools), or the
>   statutory value where no schedule was acquired. Its exact binding to `bell_schedules` /
>   `district_grade_minutes` is settled in T7.
> - **METHODOLOGY.md stays present-state.** It gains these scopes (and the GenEd band variants) only in
>   T10, when they are computed. Until then it carries only the quarantine caveats a reader of current
>   results needs.
> - **Acceptance properties A4 and A6 below were written for fixed bands.** T6 adds an independent
>   school-band PTR computation to the decisions measure script, and A4 is restated against it then.
>   A6 (the K-5 regime gap) no longer applies as written. T9 reports the regime gap per band *and* per
>   grade span.

1. **`ccd_school_staffing`** (school × year), loaded **verbatim**: `ncessch`, `leaid`, `source_year`, `level`,
   `gslo`/`gshi` (029); `teachers_fte` + `teachers_dms_flag` (059); membership PK, KG, 1–12, 13, UG
   (052, "Subtotal 4 - By Grade"); one sha256 per source file; `loaded_at`. Missing/suppressed stays NULL
   with its flag — never 0 (REQ-165: no inference from absence).
2. **`lea_grade_teacher_fte`** (district × year × grade) — the stored, auditable derivation: for each grade,
   the teacher FTE attributed to it (Σ over the district's reported schools of `teachers_fte × membership_g /
   membership_school`), that grade's membership in the same schools, the school count, plus per-district
   coverage (reported-school share of membership), the LEA-only FTE left unattributed, and `method_version`.
   An auditor recomputes any row with one SQL query over (1).
3. **Scopes** `teachers_k5`, `teachers_6_8`, `teachers_9_12` (D1): for band B,
   `LCT_B = minutes_B × Σ_{g∈B} teacher_fte_g / Σ_{g∈B} membership_g`, where `minutes_B` comes from the
   existing `weighted_scope_minutes` over B's grades (per-grade bell minutes where Stage 9 wrote them,
   statutory band otherwise). Numerator and denominator come from the **same schools**, so coverage gaps
   shrink both sides rather than biasing the ratio.
4. **One grade→band map** in `infrastructure/utilities/grade_bands.py`; every current spelling imports it.

## Decisions for Ian (recommendations are proposals, not settled)

| # | Question | Recommendation | Why |
|---|---|---|---|
| D1 | Scope names | `teachers_k5`, `teachers_6_8`, `teachers_9_12` | Grade-explicit; "elementary" is the word whose state-practice meaning caused #1017. |
| D2 | Band boundaries: fixed K-5/6-8/9-12, or each district's own grade ownership | **Fixed** | Cross-district comparability is the point of the fix; per-grade minutes already honour each district's real bell schedule inside the fixed band. |
| D3 | Pre-K teachers inside school totals | Spread over PK too (PK membership in the pro-rata), then drop the PK share | Matches "all scopes exclude Pre-K teachers"; assumes PK's PTR equals the school's. |
| D4 | 4,063 schools with missing/suppressed teacher counts | Exclude the school from BOTH numerator and denominator; record coverage; publish the band row only above a declared coverage floor (propose 90% of the district's K-12 membership) | No imputation; the ratio stays paired. |
| D5 | ~1.3% of teacher FTE reported only at LEA level | Leave unattributed; store it per district | Not attributable to grades without inference. `teachers_only` keeps counting it. |
| D6 | 2023-24 school files | Fetch 029/052/059 for 2023-24 | 356 districts' rows use 2023-24 staffing; without them those districts get no band row. |
| D7 | Drift-check gating | Pre-commit runs the DB drift test when Docker is up and **blocks** on drift; warns (does not block) when Docker is down; pre-push stays DB-free | Matches both hooks' current policy; Ian asked for a local pre-commit check. |

**Status (Ian, 2026-11-01):** D4, D5, D7 **approved** as recommended. D6 **done**: Ian placed the 2023-24
`ccd_sch_029/052/059` zips in `data/raw/federal/nces-ccd/2023_24/` (T3 still owes the catalog entries,
`SOURCE.md` sha256s and manifest). **D1/D2 and D3 decided** (later the same day): the Design section's revised block records them.
**D8 decided (Ian, later the same day): the hybrid.** Each school's share of the state's CRDC SPEDCERT
spreads the state's IDEA assigned SPED-teacher total across schools. This replaces today's student-based
key (self-contained students × state ratio) for the band GenEd variants. The student side stays as it is
today (self-contained students removed). A SPEDCERT of 0 means zero *certified*, not zero assigned.

T11 still reports today's key alongside the hybrid on the same rows, as a comparison before adoption; it
is not a re-opening of the decision. Method of record: "GenEd band variants" below.

**All of D1–D8 are now decided.**

## Decision measurements (2026-11-01, 2023-24 vintage)

Rerun: `2026-11-01-band-scope-decisions-measure.py` (imports the live `school_sampling.primary_bands_for`).

**M1 — D1/D2, the pipeline's own school bands.** Ian's position: band a school as the acquisition pipeline
already does (METHODOLOGY "Grade-band classification": `LEVEL` with the #498 carve-out, and grade-span
overlap only for combined `LEVEL`s). The bell minutes are already measured per school band that way, so
minutes, teachers and students would all come from the same schools. Under that rule:

- **96.1% of teacher FTE sits in single-band schools**: elementary 47.8%, high 30.0%, middle 18.2%.
  Whole-school attribution covers them with no per-grade split.
- 3.7% sits in K-12-style combined schools and 0.1% in 6-12 combined schools. These need a split, and the
  pipeline's own fallback for them is the fixed-band overlap (`bands_for`).
- Compare the fixed-band design: 37% of schools span more than one fixed band.
- The elementary band is not K-5 everywhere. By the school's top grade, its teachers sit 57.1% in schools
  ending at grade 5, 14.8% ending at 6, 13.3% ending at 8, and 7.1% ending at 4.
- **Name collision:** `teachers_elementary` is the quarantined LEA-pair scope. Its rows stay readable after
  #1023, so reusing the name for a different definition would mix two meanings in `lct_calculations`
  under one key.

**M2 — D3, Pre-K.** The school file reports one `TEACHERS` total per school, Pre-K included (the LEA file's
national `Teachers` of 3,283,457 matches the 3,239,020 school sum less the ~1.3% LEA-only FTE). It has no
Pre-K breakout. The LEA file does have one, `Pre-kindergarten Teachers`:

- Of 9,838 LEAs with Pre-K students, 9,731 report a Pre-K teacher count. 1,207 of those report 0.
- **The pro-rata assumption overstates Pre-K teachers by 40%**: 95,864 estimated against 68,269 reported in
  the same LEAs (a Pre-K PTR of 14.2 assumed, 20.0 reported).
- Per LEA, reported ÷ pro-rata has a median of 0.70 (p25 0.45, p75 0.93).

**M3/M4 — D8, CRDC `SCH_FTETEACH_SPEDCERT`.**

- **It is school-level.** It is a school-form item, STAF-2. The 2023-24 form (School Form Table Layout)
  reads: "enter the number of FTE teachers in **preschool and grades K-12** … who were employed at this
  school and are **certified/licensed/endorsed** in the specified areas". Teachers on alternative-route,
  emergency, temporary or provisional credentials are excluded.
- **It is a certification count, not an assignment count.**
  - Nationally it runs 1.11× IDEA 618's assigned SPED teachers for the same year: 505,196 against 454,492.
    (The 412,993 quoted earlier in this note is IDEA's *certified* subset; the assigned total is 454,925.)
  - By state it runs from 0.76× (AR) to 2.64× (DE): 1.89 IN, 1.86 MA, 1.77 OK, 1.55 VA, 0.85 CA.
- **The school-grain holes are large:**
  - 5,621 schools with ≥ 20 IDEA students report 0 SPEDCERT, covering 399,319 students.
  - 948 schools report more SPEDCERT than CCD teachers.
  - CRDC's own teacher total differs from CCD's by a median of 6.7%, and by more than 25% in 14.9% of
    schools.
- **Special Education Schools.** SPEDCERT is 77.6% of their teachers, and IDEA students are 90.2% of their
  enrollment.
- **Regular single-band schools.** SPEDCERT's share of teachers tracks the IDEA share of students in every
  band:

  | Band | SPEDCERT share of teachers | IDEA share of students |
  |---|---|---|
  | Elementary | 15.6% | 15.5% |
  | Middle | 15.5% | 15.0% |
  | High | 13.4% | 13.0% |

  So the PTRs move as follows:

  | PTR | Elementary | Middle | High |
  |---|---|---|---|
  | All teachers | 14.3 | 15.0 | 16.1 |
  | Subtract both SPEDCERT and IDEA students | 14.3 | 15.1 | 16.2 |
  | Subtract SPEDCERT only | 17.0 | 17.8 | 18.6 |

## Special education (added 2026-11-01, on Ian's question)

The band scopes inherit the SPED skew `teachers_only` has. CCD school teacher FTE counts special
education teachers, and membership counts students with disabilities. At school grain two effects show:

- **Special Education Schools** (CCD `SCH_TYPE_TEXT`): 962 serve K-12 students. They hold 95,828 students
  and 22,957 teachers, a PTR of **4.2** against 14.9 in regular schools. That is 0.9% of teachers
  nationally, but concentrated in some districts. Per-grade attribution would pull those districts' band
  PTRs down. Alternative and CTE schools hold another 1.1% and 0.8% of teachers.
- **Self-contained SPED inside regular schools** has the same skew as `teachers_only`. Its share by band is
  not measured yet, and if it differs by band it moves the band comparison.

**What exists to correct it, at school grain** (CRDC 2023-24, on disk):

- The school-level IDEA enrollment (`Enrollment.csv` `SCH_ENR_IDEA_M/F/X`) MEASURES SPED students per
  school, rather than estimating them.
- **There is no usable school-level SPED teacher count.** `School Support.csv` `SCH_FTETEACH_SPEDCERT` sums
  to 509,135 FTE against the IDEA personnel baseline's 412,993 SPED teachers (2024-25). *(Corrected
  2026-11-01, see "Decision measurements" M4: 412,993 is IDEA's certified subset; IDEA's assigned total is
  454,925, personnel year 2023-24.)* It counts teachers
  *certified* in special education, not teachers *assigned* to it. SPED teachers per school would still be
  estimated with the baseline ratio, the same proportionality assumption `teachers_gened` makes today,
  applied at school grain.
  **Partly confirmed from the codebook (2026-11-01):** the CRDC 2023-24 Appendix Workbook's Data Dictionary
  (in `~/Development/public-ed-data-navigator/data/raw/crdc/2023-24/`) files it as item STAF-2 under
  "Teacher Certification in Specialized Areas" ("Number of FTE teachers—special education"), alongside the
  math / science / ESL certification counts, so it is a certification count. T11 reads the STAF-2 question
  wording before ruling it out entirely.

**Proposal:**

1. Phase 2 ships the three scopes as the all-teacher analogue of `teachers_only`, SPED included and
   documented. That adds no new assumption and keeps A3's reconciliation to the LEA total.
2. T4 stores `sch_type` so the effect can be measured.
3. T9 reports band PTRs with and without Special Education Schools, plus the IDEA share by band from CRDC.
4. GenEd band variants are a follow-up task (T11), gated on **D8**: whether to build them, and whether
   Special Education Schools are excluded or estimated.

| # | Question | Recommendation |
|---|---|---|
| D8 | SPED in the band scopes | Ship all-teacher band scopes first (the `teachers_only` analogue). Measure in T9. Decide GenEd band variants (CRDC school IDEA enrollment + the baseline teacher ratio) on T9's numbers. |

## GenEd band variants — the teacher-side hybrid (D8, decided 2026-11-01; T11 / #1046)

The design of record for T11. METHODOLOGY describes it only once it is computed. The district-level SPED
scopes (METHODOLOGY → SPED Segmentation) are unchanged.

**The change.** Today each district's SPED teachers are estimated *from students*: self-contained students
× the state's SPED teachers per self-contained student. At school grain the band variants instead spread
each state's **IDEA 618 assigned SPED-teacher total** across its schools *by a teacher count each school
reports*:

```
SPED teachers_s  = IDEA assigned SPED teachers_state × SPEDCERT_s / Σ_{schools in state} SPEDCERT
GenEd teachers_s = school teachers_s (Pre-K removed) − SPED teachers_s
GenEd students_s = school K-12 membership_s − self-contained SPED_s
self-contained_s = CRDC school IDEA enrollment_s × self-contained share (LEA at ≥ 200 school-age SPED, else state)
```

`SPEDCERT_s` is CRDC `SCH_FTETEACH_SPEDCERT`. The band variant sums the GenEd terms over the band's schools,
as the band scopes do.

**Why the hybrid, not CRDC's count directly.** `SCH_FTETEACH_SPEDCERT` is reported per school (CRDC
2023-24 school form, item STAF-2). But it counts teachers "in preschool and grades K-12 … employed at this
school and **certified/licensed/endorsed**" in special education, regardless of assignment. It also leaves
out teachers on emergency, provisional or alternative-route credentials. Measured against IDEA's assigned
SPED teachers for the same year (2023-24), it is 1.11× nationally (505,196 vs 454,492), and **0.76× (AR)
to 2.64× (DE)** by state: a state-practice count, the #1017 problem again. Scaling to each state's IDEA
assigned total removes that state-level bias and keeps the school-level pattern. On the teacher side,
the result rests on two reported teacher counts, not on a student proportion.

**What still rests on an estimate.**
- **The student side.** Self-contained students per school are still CRDC IDEA enrollment × an
  environment share (IDEA's environments are published per LEA and state, not per school).
- **The distribution key.** It assumes that within a state, certified SPED teachers are spread across
  schools the way assigned ones are.

**Known limitations.**
- **CRDC zeros.** A school reporting `SPEDCERT = 0` gets 0 SPED teachers, and a CRDC zero means zero
  *certified*, not zero assigned (5,621 schools with ≥ 20 IDEA students report 0; 399,319 students).
- **More certified SPED teachers than teachers.** 948 schools report a SPEDCERT above CCD's teacher count,
  so a GenEd estimate can go negative. It is flagged, never clipped silently.
- **Pre-K in the key.** The key includes preschool teachers; the IDEA total is school-age (5-21).
- **CRDC is biennial** (2023-24, then 2025-26). A 2024-25 band row pairs with 2023-24 CRDC within the
  REQ-026 window. School matching covers 96.7% of CCD teacher FTE.
- **Special Education Schools** carry SPEDCERT on 77.6% of their teachers and IDEA students on 90.2% of
  their enrollment, so the key places most of their staff on the SPED side without a separate rule.

**Measured context.** In regular single-band schools, SPEDCERT's share of teachers tracks the IDEA share of
students in every band:

| Band | SPEDCERT share of teachers | IDEA share of students |
|---|---|---|
| Elementary | 15.6% | 15.5% |
| Middle | 15.5% | 15.0% |
| High | 13.4% | 13.0% |

Pupil/teacher ratios under the three treatments:

| Treatment | Elementary | Middle | High |
|---|---|---|---|
| All teachers, all students | 14.3 | 15.0 | 16.1 |
| SPEDCERT teachers and all IDEA students removed | 14.3 | 15.1 | 16.2 |
| SPEDCERT teachers removed, all students kept | 17.0 | 17.8 | 18.6 |

The GenEd result is therefore driven mostly by which students leave the denominator, not by which teacher
source is used. T11 computes the hybrid alongside today's student-based key on the same rows and reports
both before adoption.

## Pre-K without a school key — the D3 fallback (Michigan and elsewhere; #1040, #1070, review #1097-#1111)

**The gap.** D3 allocates a district's LEA-reported Pre-K FTE across its schools by Pre-K membership. A
district is **key-less** when it has real Pre-K FTE but its school rows carry no Pre-K membership (Σ
`memb_pk` NULL or 0), so that allocation is 0/0. Michigan is the large case: NCES documents that it never
reports Pre-K at the school level. But the trigger is not Michigan-specific (#1102): 2024-25 has 767
key-less LCT-eligible districts, 413 in Michigan (2,270.5 Pre-K FTE) and 354 elsewhere (1,270.1; PA 51,
OR 43, MO 40, SD 28, NJ 25, MN 20, WA 20, CT 17).

**Measured by** `2026-11-04-keyless-prek-measure.py` (this folder; read-only, LCT DB). Every number in this
section comes from it. **Universe** (the first sizing drifted on each of these): LEA Pre-K FTE is a real number,
not the `'NaN'` placeholder, which `teachers_prek > 0` selects (#1098). The district is LCT-eligible, not
`is_shared_service_entity`, since ISDs, RESAs and CTCs never publish (#1097). The district has school
rows.

**What the sources say** (checked against the primary files).
- NCES CCD Membership Metadata for Michigan, identical in 2023-24 and 2024-25: *"Membership counts for
  pre-K are reported for the LEA and SEA levels, they are not reported at the building level."* The
  2018-19 state notes say the same, so this is long-standing. Sources: `nces.ed.gov/ccd/xls/SY_2023-24_Final_1a_Data_Notes.xlsx`,
  `SY_2024-25_CCD_Final_2a_Data_Notes.xlsx`, `SY1819_Membership_Staff_SpecialPopulations_DataNotes.xlsx`.
- EDFacts FS059 (identical in SY 2023-24, 2024-25 and 2025-26; excerpts and sha256s in
  `docs/research/edfacts-fs059-excerpts.md`): Pre-K teachers reported at the SEA/LEA level *"should also be
  reported at the school level"* (DG644), so by rule school FTE includes them. Reportable programs are
  excluded from the school level.
- Michigan's own explanation of school sums below the LEA total (2023-24, CCD-0045, 134 LEAs): LEAs may
  report FTE at the LEA level instead of prorating it; reportable-program teachers stay at the LEA level;
  shared-school staff cannot be placed at a school.
- Michigan's school files: 12 Pre-K-only buildings that are new in 2024-25 are reportable programs and are
  absent from the 029 directory (DGO-0033). A further 11 Pre-K-level schools (Special Education Schools)
  ARE in the directory, with 62.65 teacher FTE in 2024-25 and 93.22 in 2023-24, and report Pre-K
  membership as a *'Reported'* 0. Michigan carries 33 such 'Reported' Pre-K zeros in 2024-25 and 31 in
  2023-24, stored as 0, beside the 1,110 'Manual adjustment' zeros stored NULL (#1070).
- **Not established:** whether Michigan's Pre-K teachers also teach kindergarten. FS059 splits a blended
  teacher's FTE between PKTCH and KGTCH, so separate totals cannot show it. The research export lists it
  as unresolved (#1105). The decision below does not depend on it.

**Measurements (2024-25 unless noted).**
- **Calibration where Pre-K is inside by rule** (districts WITH a school Pre-K key, LCT-eligible, ≥5
  teachers, n = 8,433): |Σ school / LEA total − 1| has a p50 of 0.00%, a p90 of 2.39% and a p95 of 4.73%;
  70.2% fall within 0.1%. Chance "outside" matches: 1.25% of all, but **4.4% (105 of 2,392) of districts
  with a school shortfall**. A shortfall district is exactly where an "outside" match can occur (#1101).
- **Placement classes, key-less districts, 0.1%, inside tested first (#1100):**

  | vintage | districts | inside (FTE) | outside (FTE) | neither (FTE) |
  |---|---|---|---|---|
  | 2023-24 | 791 | 395 (834.2) | 59 (149.7) | 337 (2,238.0) |
  | 2024-25 | 767 | 363 (871.7) | 63 (234.4) | 341 (2,434.4) |

  One 2024-25 district's LEA total is all Pre-K (Bois Blanc Pines, 2606300). For it "outside" is
  undefined, so it is inside or neither, never a division by zero.
- **Single-year "outside" is about one-third coincidence.** A permutation null (Pre-K FTE shuffled across
  the key-less districts, 2,000 draws; each keeps its own total and school sum) gives a mean of 23.0
  outside matches in 2024-25 (p95 30) against 63 observed, and 21.6 in 2023-24 (p95 29) against 59.
- **Two-year agreement is not.** Of 588 key-less districts present in both vintages, **27 are outside in
  both**. The null for agreement in both years has a mean of 1.86, a p95 of 4 and a max of 7. Transitions:
  inside→inside 219, neither→neither 261, outside→outside 27, and 101 districts change class.
- **Feasibility (#1097).** Subtracting from host schools before the grade split (rule 4 below), the Pre-K
  FTE exceeds the hosts' whole teacher FTE in 6 districts (49.9 Pre-K FTE): CT 0901260 23.00 vs 21.20, MI
  2628740 21.00 vs 8.60, SD 4600052 3.00 vs 1.00, MI 2623910 1.40 vs 1.00, and two NJ districts with
  hosts reporting no FTE. Hosts are PK-offering schools in 524 districts, elementary-band schools in 241,
  and none in 2.
- **Bounds for the neither districts:** 341 districts and 2,434.4 Pre-K FTE. The bound width
  Σ min(pk, gap) is 1,667.6. In 187 of them (1,156.8 FTE) the shortfall is at least the Pre-K FTE.
- **The D3 flag's students (#1103):** 29 Michigan districts report 12,167 Pre-K students in the LEA file
  and Pre-K FTE exactly 0.

**Decision.** Option 1 (Ian, 2026-11-03) is to subtract unless the district's numbers show Pre-K outside the
school counts, with a 0.1% tolerance and the default subtraction plus stored bounds for the neither
districts. Rejected: subtracting everywhere, and ignoring Pre-K teachers. **Revised 2026-11-04 after the
#1095/#1096 review: R1, R3, R4 and R5 confirmed by Ian (2026-11-04); R2 and R6 are corrections; R7 is the
schema proposal T6 implements, still PROPOSED.**
- **R1 — trigger (#1102).** The fallback applies to every key-less district, in any state. There is no
  state gate.
- **R2 — universe (#1097, #1098).** Real Pre-K FTE (not `'NaN'`), LCT-eligible districts.
- **R3 — placement test (#1100, #1101).** Inside first at 0.1%. A district is **outside** only when it is
  outside (0.1%, LEA total − Pre-K > 0) in BOTH the vintage being derived and the previous on-disk vintage.
  Every other district takes the default subtraction. At 2024-25 that is 27 districts, against 63 on one
  year alone.
- **R4 — where the subtraction lands (#1097).** At the school level, BEFORE the grade split: across the
  district's schools whose span starts at PK (`gslo = 'PK'`), else across its elementary-band schools,
  in proportion to their teacher FTE. A combined PK-12 school therefore loses its Pre-K FTE from the
  school total rather than from its elementary slice (the Engadine case).
- **R5 — feasibility (#1097).** If the district's Pre-K FTE exceeds the hosts' total teacher FTE, nothing is
  clipped. The district's elementary band is unpublished and flagged `pk_exceeds_hosts` (6 districts in
  2024-25). Proportional allocation then cannot exceed any single host.
- **R6 — bounds are derived, not stored (#1103).** The lower bound is
  `GREATEST(0, pk_teachers_reported − unattributed_fte)` on existing `lea_school_staffing` columns. T9's
  before/after reports the neither districts' elementary bands at both bounds. Whether they publish is
  decided at T9, with D4's coverage floor.
- **R7 — T6's schema change, migration 035 (#1103). PROPOSED (T6).** `lea_school_staffing.pk_membership` becomes
  nullable (NULL for a key-less district, never a fabricated 0; #1070). A new `lea_pk_membership` holds
  the LEA-file Pre-K count, which `pk_zero_with_students` reads, so the 29 Michigan districts are
  flagged. Both are declared in migration and model (the PR #641 invariant). T7's `chk_staff_scope`
  migration becomes 036.

## Roadmap (each a sub-issue of #1022)

| Task | What | Depends on | Gated on Ian |
|---|---|---|---|
| T1 | One canonical grade→band map in `utilities/grade_bands.py`; the four spellings import it; call-site identity tests | — | no |
| T2 | Deflate64 zip-member reader in `utilities/` (`inflate64`, size + CRC-32), dependency added | — | no |
| T3 | `fetch_nces_ccd.py` catalog for 2023-24 + 2024-25 school 029/052/059; download 2023-24; `SOURCE.md` with sha256s; a tracked source manifest | — | D6 — files in place |
| T4 | Migration 033 + model: `ccd_school_staffing`, `lea_grade_teacher_fte` | — | no |
| T5 | Importer `import_ccd_school_staffing.py` (verbatim, guards), wired into the CCD import, rebuild phase list and `verify_table_counts` | T2, T4 (T3 for 2023-24) | no |
| T6 | Derivation into `lea_grade_teacher_fte` (one function, `method_version`) | T1, T5 | D3, D4, D5 — decided |
| T7 | The three scopes (`teachers_band_*`): migration 036 (`chk_staff_scope`; 034 is #1088, 035 is T6's Pre-K columns), calc, scope registry, reports/QA, REQ-008 amended | T6 | D1, D2 — decided |
| T8 | Drift checks: DB-free sha-vs-manifest test; integration test (stored sha + SQL recompute + full re-derivation); pre-commit wiring | T5, T6 | D7 — decided |
| T9 | Read-only before/after measurement → **stop for Ian's adoption call** | T7, T8 | — |
| T10 | Adopt: restore-verified `pg_dump`, scratch rehearsal, live migrations + import + recompute, row diff; METHODOLOGY / DATA_SOURCES / DATABASE_SETUP; REQ-190 | T9 + Ian | adoption |
| T11 | GenEd band variants: CRDC 2023-24 school IDEA enrollment (measured) + the baseline SPED teacher ratio (estimated), at school grain; Special Education Schools per D8 | T10 | D8 |

Then #1023 retires the LEA pair.

## Acceptance properties (falsifiable)

- **A1** T1 changes no number: a full dry run is byte-identical to main's, and the govdb suite passes.
- **A2** The importer refuses, loudly, a file whose vocabulary (TOTAL_INDICATOR, GRADE, DMS_FLAG) it does
  not know, a member whose CRC fails, and a load that writes 0 rows.
- **A3** Σ `lea_grade_teacher_fte` over grades + unattributed LEA-only FTE + excluded-school FTE
  reconciles to each district's LEA teacher total within the measured school-vs-LEA tolerance, and every
  row recomputes from `ccd_school_staffing` by SQL.
- **A4** National band PTRs reproduce M3 of the measure script (pro-rata ≈ 14.1 / 14.8 / 15.9).
- **A5** `teachers_only` and every existing scope are md5-identical before/after T7; only new rows appear.
- **A6** The regime gap in the K-5 median (31.6 vs 26.2 on the quarantined scope) mostly closes. A miss
  means the method is wrong; it is not a threshold to tune.
- **A7** Each drift test fails on a deliberately altered stored input, an altered source hash, and an empty
  table (one test each).
