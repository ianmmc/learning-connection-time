# Guards against the #970 and #972 failure shapes — findings + plan (2026-10-30)

Status: **IMPLEMENTED 2026-10-30** (branch `feat/guards-total-row-and-year-default`; corrections below are marked, the original text is kept). Written before any guard code, per the standing rule that
a plan states acceptance properties and is checked against the real code before it is accepted.

## The two shapes

| shape | instance | what went wrong | why nothing caught it |
|---|---|---|---|
| **S1 — a source's own total row summed in as a component** | #970, `import_sped_baseline.py` | `Total, Age 6-21` summed with the environment rows → 2× denominator; `Separate School` label never matched → 342k students in no bucket | the audit identity (SPED + GenEd = total) holds by construction; the test asserted hand-typed numbers and never called the parser |
| **S2 — a hand-typed data-year default that silently stops matching** | #972, `apply_sped_estimates.py` | `default="2023-24"`; source was the single-vintage `districts` snapshot; 2024-25 found 0 rows and exited 0 with `Updated: 0` | a zero-row sweep was reported as success |

Both have a common root: **an empty or degenerate match is indistinguishable from a healthy run.**
A label set that never matches, a year that selects nothing, a sum that is exactly 2× its reference —
each printed a plausible number and exited 0.

## Inventory (measured 2026-10-30, live code + live DB)

### S1 — every parser that reads a file carrying its own totals

| parser | source total available | handling today | verdict |
|---|---|---|---|
| `import_sped_baseline.import_idea_child_count` | `Total, Age 6-21` / `Total, Age 3-5` rows | fixed in #970 — totals read FROM the total rows | fixed; needs the generic guard to stay fixed |
| `import_sped_baseline.import_idea_personnel` | `Total Special Education Teachers` / `…Paraprofessionals` rows | reads only the two `Ages 6-21` rows; never sums | OK, no reference check |
| `import_sped_baseline.import_crdc_enrollment` | none in file (school rows only); CCD LEA total used as denominator | sums school rows per LEA | OK — but note `TOT_ENR_X` (2023-24 nonbinary column) is NOT summed (`_M + _F` only); `-10` for every school in 2023-24 so no loss *today* |
| `import_sped_baseline.import_ccd_enrollment` | `TOTAL_INDICATOR = 'Derived - Education Unit Total'` | filters TO the total row | OK |
| `import_staff_and_enrollment` (→ `enrollment_by_grade`) | `Education Unit Total` row per LEA | sums `Category Set A` rows, excludes `No Category Codes` subtotals, then `enrollment_total = Σ grades` | **measured: 17,705 / 17,739 LEAs equal the file's own total for 2024-25; 34 differ** (mostly file total 0/1 with real components — suppression in the total row, DC/AR charters), 797 LEAs file-only. Sound, but the cross-check is not asserted anywhere |
| `extract_grade_level_enrollment` / `_staffing` | same CCD files | filter to `Category Set A` | OK by inspection; same missing cross-check |
| `import_ca_sped` | `ReportingCategory == 'TA'` (Total All) | filters TO the total category | OK |
| `import_new_york_data` | `Subgroup Name` (All Students + subgroups) | reads `PreK-12 Total` per subgroup row; stores per subgroup | OK — but hard-codes `'2023-24'` in the INSERT SQL (→ S2) |
| state SEA imports (FL, IL, MI, PA, VA, MA, TX) | explicit total columns (`Total Teachers`, `tot_all`, `TOTAL_CNT`…) | read the total column, do not sum components | OK, no reference check possible without a second number |

**Finding:** only ONE live parser (`import_idea_child_count`) had the S1 defect, and it is fixed. But
the one place a source total AND a component-sum both exist in bulk (`enrollment_by_grade` vs the CCD
Education Unit Total) is **not cross-checked** — the 34 disagreements were unknown until this
measurement. That cross-check is the generic guard worth having.

### S2 — every hand-typed school-year literal on an operational path

| file | literal | role | live? |
|---|---|---|---|
| `apply_sped_estimates.py` | `default="2023-24"` | target year | **fixed in #972 → `NCES_PRIMARY_YEAR`** |
| `import_staff_and_enrollment.py:479` | `default="2023-24"` | the PRIMARY CCD ingest's target year | **live, same shape as #972** — but here a wrong default would ingest the wrong vintage, not zero rows |
| `merge_sea_precedence.py:391` | `default="2023-24"` | SEA→effective merge target year | live (REQ-023 path) |
| `enhance_sped_with_sea_data.py:144` | `default="2023-24"` | SEA SPED enhancement target | live |
| `import_texas_tapr_data.py:411`, `import_california_staff_data.py:289` | `default="2024-25"` | SEA ingest year | live; happens to be current |
| `import_new_york_data.py` (~L421) | `'2023-24'` **inside SQL** | the stored row's year | live; not even a flag |
| `compare_sea_vs_federal_lct.py:224`, `generate_sea_integration.py:508` | `default='2023-24'` | analysis / scaffolding | non-operational |
| `validate_ca_sped_integration.py`, `ca_validation_report.py` | `== '2023-24'` ×14 | validation reports | read-only, stale |
| `models.py:1170,1259,1324` | `default="2017-18"` | SPED baseline vintage columns | correct — the baseline IS 2017-18 (REQ-018); not a currency default |
| `import_sped_baseline.py` ×4 | `source_year="2017-18"` | same | correct, same reason |

**Finding:** six operational scripts carry a hand-typed currency default; two are stale right now
(`merge_sea_precedence`, `enhance_sped_with_sea_data` → 2023-24 while `NCES_PRIMARY_YEAR` is 2024-25),
and `import_staff_and_enrollment` — the ingest whose job is to *produce* the primary vintage — defaults
to the previous one. The 2017-18 literals are legitimate and must be exempt (they name a fixed
baseline, not "current").

## Proposed guards

### G1 — `reconcile_total(components_sum, reference_total, *, label, tolerance)` (S1, generic)
One function in `infrastructure/utilities/` (DB-free, importable by both the migrations and the
measurement scripts). Given a component sum and the source's own published total, it:
- **fails loud** when `|sum − ref| / ref > tolerance` (default 0.5% — the CCD 34/17,739 are
  individual-row disagreements, the aggregate is far inside);
- **fails loud on the exact-multiple signature** — `sum/ref` within 0.1% of an integer ≥ 2 is the
  "summed the total row in" fingerprint (#970 was 2.000×) and is reported as such, not as a generic
  mismatch;
- returns a `TotalReconciliation(sum, ref, ratio, n_compared, n_disagree)` receipt so callers can log it.

Wired into (a) `read_child_count_file` — the environment rows summed vs the `Total, Age 6-21` row, per
state (this is the #970 regression guard, DB-free); (b) `import_staff_and_enrollment` — `enrollment_total`
vs the file's Education Unit Total per LEA, aggregate + per-LEA disagreement count logged.

### G2 — `require_labels_seen(expected: set, seen: set, *, label)` (S1, the other half)
A label vocabulary that matches NOTHING in the file is a parse error, not an empty category. Fails loud
when any member of `SELF_CONTAINED_ENVIRONMENTS` / `MAINSTREAMED_ENVIRONMENTS` (and the personnel
`TEACHER_TYPE`/`PARA_TYPE`) is never seen. This is what would have caught `'Separate School'` on day one,
and it is what will fire the moment the 2024-25 file's `School Age` relabels arrive (the refresh is
queued behind this).

### G3 — `tests/test_no_hand_typed_currency_years.py` (S2, fitness function)
Scans `infrastructure/**/*.py` for `default=["']20\d\d-\d\d["']` on an `add_argument`, and for
`== '20\d\d-\d\d'` / `'20\d\d-\d\d'` inside `text(...)` SQL, in operational modules. Exempt list is
**declared in `arch-manifest.json`** (the existing review surface for cross-boundary edges), with a
reason per entry — the 2017-18 baseline literals go there. New literal → test fails → the author either
switches to `NCES_PRIMARY_YEAR` or declares the exemption with its reason.

### G4 — `require_nonempty_selection(rows, *, what, available)` (S2, runtime)
The pattern just added to `apply_sped_estimates` as a one-off, promoted to the same utilities module:
a year-scoped selection that returns zero rows raises with the years the source actually carries.
Wired into the six operational scripts above wherever they select by year. (The `Updated: 0`-exits-0
behaviour is the S2 symptom; this is its generic cure.)

### G5 — one integration test: `NCES_PRIMARY_YEAR` is present in every year-keyed table
`enrollment_by_grade.source_year`, `staff_counts_effective.effective_year`, `sped_estimates.estimate_year`,
`lct_calculations.enrollment_source_year`. Marker `integration` (live LCT DB). This is the check CLAUDE.md
describes in words ("verified against `lct_calculations` rows") made executable; it catches the
"bumped the constant, forgot the ingest" case and the "ingested, forgot to bump" case.

## Corrections found while implementing (2026-10-30)

- **P2 was mis-specified.** The 34 per-LEA disagreements measured above compared our component sum to
  the CCD row `Derived - Education Unit Total minus Adult Education Count`. The ingest's own total is
  the plain `Education Unit Total`; against THAT, G1 reports **18,499 LEAs compared, 0 differ,
  aggregate ratio 1.00000** for 2024-25. So the 34 are adult-education counts, not reconciliation
  noise — and they raise a methodology question (should `enrollment_total` exclude adult ed?) that is
  Ian's call, filed separately, not a guard's. P2's acceptance property is amended: G1 reconciles
  exactly (0 row-wise) against `Education Unit Total`; a non-zero count there IS a finding.
- **The S2 inventory was short by four.** G3's scanner found what the hand grep missed:
  `import_massachusetts_data.py` (`TEACHER_DATA_YEAR = '2024-25'`, `ENROLLMENT_DATA_YEAR = '2025-26'`
  — SEA vintages, declared), `import_manual_bell_schedules.py:439` (`year = "2025-26"` — a currency
  default for manual collection, converted to `current_school_year()`), and `school_year.py`'s own
  `SPED_BASELINE_YEAR` / `PRE_COVID_FALLBACK_YEAR` (declared — they ARE the single homes). A test module
  living under `infrastructure/` (`database/test_infrastructure.py`) is excluded by name.
- **Correction (2026-10-31, review of PR #971/#973 — #975–#989).** The "342k students" / "24,522,548 vs
  12,261,274" figures quoted for the #970 shape include the file's own US aggregate row; for the
  importer's 56 states they are Σ(environments + Total) **12,244,430** vs Total **6,122,215** (exactly
  2.000×). P2 as amended is now ENFORCED (`max_disagree=0`, #976), not printed. G2 is closed-world on
  the environment vocabulary and the header row is sought by content (#975/#982). G3 is AST-based with
  per-(file, literal, COUNT) exemptions (#980). P4/P5 now have DB-free tests
  (`tests/test_data_guard_wiring.py`, `tests/test_primary_year_presence.py::TestTheVerdictCanFail`) and
  every wired guard site is exercised by a production entry point (#981).
- **Three exemptions became one.** `SPED_BASELINE_YEAR` already existed in `school_year.py`; the
  `2017-18` literals in `models.py`, `import_sped_baseline.py` and `apply_sped_estimates.py` now
  import it instead of re-spelling it (the implemented-twice rule), so only `school_year.py` is
  declared for 2017-18.
- **The analysis scaffolds were converted, not exempted** (`compare_sea_vs_federal_lct.py`,
  `generate_sea_integration.py`): their year means "current", so carrying a stale exemption would
  have documented wrong behaviour.
- **NY was parameterized, not re-pointed**: the NYSED workbook on disk IS 2023-24, so its year became
  `--year` (default `SOURCE_YEAR = "2023-24"`, declared as a source vintage) driving both the sheet
  name and every stored row; the four SQL literals are gone.

## Acceptance properties (how this plan can fail)

- **P1.** With G1/G2 in place, reverting the #970 fix (re-summing the Total row; restoring the
  `'Separate School'` label) makes `tests/test_sped_segmentation.py` fail on the fixture **and** makes
  `import_sped_baseline.py` refuse to run on the real file. Verified by actually reverting on a branch.
- **P2.** G1 on `import_staff_and_enrollment` reports exactly the 34 disagreeing LEAs measured above for
  2024-25 and passes the aggregate — if it reports 0 it is not measuring; if it fails the aggregate the
  tolerance is wrong, not the data.
- **P3.** G3 fails on the current tree (6 operational literals) until each is either converted or
  declared; the manifest's exemption list is non-empty (2017-18 baseline) and every entry carries a reason.
- **P4.** G4: running `merge_sea_precedence`/`enhance_sped_with_sea_data` against a year the source does
  not carry exits non-zero with the available years in the message — tested by invoking the selection
  function with a bogus year against the live DB (integration).
- **P5.** G5 is red if `NCES_PRIMARY_YEAR` is bumped without an ingest (checked by monkeypatching the
  constant in the test, not by bumping it).
- **P6.** No guard changes any number: the full LCT recalculation after wiring G1–G4 produces identical
  `lct_calculations` aggregates to the post-#972 snapshot (`sped_after_972.json`).

## Out of scope here (filed or to file separately)

- `teachers_gened` derives from `teachers_total` while the `teachers` scope uses `scope_teachers_only`
  (equal for only 5,643 / 17,842 districts) — a staffing-definition inconsistency, not a guard.
- `TOT_ENR_X` / `SCH_ENR_IDEA_X` (CRDC 2023-24 nonbinary columns) are not summed by
  `import_crdc_enrollment`; harmless today (`-10` everywhere) — fold into the CRDC refresh.
- The CRDC 2023-24 / IDEA 2024-25 refresh itself — queued behind this; G2 is what makes it safe.
