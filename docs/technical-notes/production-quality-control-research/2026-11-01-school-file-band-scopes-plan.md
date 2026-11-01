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
  to 509,135 FTE against the IDEA personnel baseline's 412,993 SPED teachers (2024-25). It counts teachers
  *certified* in special education, not teachers *assigned* to it. SPED teachers per school would still be
  estimated with the baseline ratio, the same proportionality assumption `teachers_gened` makes today,
  applied at school grain.
  *This reading is inferred from the totals, not from a definition.* No CRDC codebook is on disk
  (`crdc/2023_24/metadata/` holds data only); Ian can obtain the codebooks, and T11 confirms the field
  definition against the 2023-24 CRDC codebook before relying on it either way.

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

## Roadmap (each a sub-issue of #1022)

| Task | What | Depends on | Gated on Ian |
|---|---|---|---|
| T1 | One canonical grade→band map in `utilities/grade_bands.py`; the four spellings import it; call-site identity tests | — | no |
| T2 | Deflate64 zip-member reader in `utilities/` (`inflate64`, size + CRC-32), dependency added | — | no |
| T3 | `fetch_nces_ccd.py` catalog for 2023-24 + 2024-25 school 029/052/059; download 2023-24; `SOURCE.md` with sha256s; a tracked source manifest | — | D6 |
| T4 | Migration 033 + model: `ccd_school_staffing`, `lea_grade_teacher_fte` | — | no |
| T5 | Importer `import_ccd_school_staffing.py` (verbatim, guards), wired into the CCD import, rebuild phase list and `verify_table_counts` | T2, T4 (T3 for 2023-24) | no |
| T6 | Derivation into `lea_grade_teacher_fte` (one function, `method_version`) | T1, T5 | D3, D4, D5 |
| T7 | The three scopes: migration 034 (`chk_staff_scope`), calc, scope registry, reports/QA, REQ-008 amended | T6 | D1, D2 |
| T8 | Drift checks: DB-free sha-vs-manifest test; integration test (stored sha + SQL recompute + full re-derivation); pre-commit wiring | T5, T6 | D7 |
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
