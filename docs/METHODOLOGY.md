# Learning Connection Time (LCT) Methodology

## Overview

This document provides the detailed methodology for calculating Learning Connection Time (LCT), including formulas, data requirements, known limitations, and planned evolutions.

---

## Core Calculation (Phase 1.5)

### Basic Formula

```
LCT = (Daily Instructional Minutes × Staff Count) / Student Enrollment
```

**Result**: Minutes of potential individual attention per student per day

### LCT Variants (Multiple Staffing Scopes)

As of December 2025, we calculate **seven LCT variants** using different staff definitions to provide rhetorical flexibility and analytical depth. **All scopes exclude Pre-K** from both enrollment and staffing.

#### Base Scopes (5 variants)

| Variant | Staff Scope | Enrollment | Use Case |
|---------|-------------|------------|----------|
| **LCT-Teachers** | K-12 teachers (elem+sec+kinder, NO ungraded) | K-12 | Most conservative measure |
| **LCT-Core** | K-12 teachers + ungraded | K-12 | Includes all K-12 classroom staff |
| **LCT-Instructional** | Core + coordinators + paras | K-12 | **Recommended primary metric** |
| **LCT-Support** | Above + counselors/psychologists | K-12 | Holistic support view |
| **LCT-All** | All staff (excl. Pre-K teachers) | K-12 | Maximum resource investment |

#### Teacher-Level Variants (2 additional)

| Variant | Staff Scope | Enrollment | Use Case |
|---------|-------------|------------|----------|
| **LCT-Teachers-Elementary** | Elem + Kinder teachers | K-5 only | Elementary-specific analysis |
| **LCT-Teachers-Secondary** | Secondary teachers only | 6-12 only | Secondary-specific analysis |

#### Key Methodology Decisions (December 2025)

1. **Pre-K Exclusion**: All scopes exclude Pre-K from both enrollment and staffing due to heterogeneous Pre-K availability and different licensing requirements.

2. **Ungraded Teachers**:
   - **EXCLUDED** from LCT-Teachers, LCT-Teachers-Elementary, LCT-Teachers-Secondary
   - **INCLUDED** in LCT-Core, LCT-Instructional, LCT-Support, LCT-All

3. **Grade Boundaries**:
   - Elementary (K-5): Kindergarten through Grade 5
   - Secondary (6-12): Grades 6 through 12

4. **QA Validation**: Level-based LCT calculations include `level_lct_notes` for transparency about data quality issues.

**Key Findings** (December 2025 calculation):

| Scope | Mean LCT | Median LCT | Districts |
|-------|----------|------------|-----------|
| Teachers-Only | 27.9 min | 25.2 min | 14,286 |
| Teachers-Elementary | 34.3 min | 30.8 min | 13,090 |
| Teachers-Secondary | 22.9 min | 20.1 min | 12,378 |
| Teachers-Core | 29.5 min | 26.2 min | 14,305 |
| Instructional | 38.4 min | 34.2 min | 14,314 |
| Support | 42.2 min | 37.9 min | 14,271 |
| All | 59.8 min | 54.5 min | 14,250 |

**Observed Patterns**:
- Elementary LCT > Overall > Secondary (lower student-teacher ratios in elementary)
- Broadening from teachers-only to all-staff adds ~27 minutes (median)

**Recommended Usage**:
- **Policy discussions**: Use LCT-Instructional (balanced, defensible)
- **Conservative estimates**: Use LCT-Teachers (most restrictive)
- **Level comparisons**: Use LCT-Teachers-Elementary vs LCT-Teachers-Secondary
- **Resource analysis**: Compare across all scopes to understand staffing mix impact

See `docs/STAFFING_DATA_ENHANCEMENT_PLAN.md` for detailed scope definitions and data sources.

### Components

#### 1. Daily Instructional Minutes

**Definition**: The actual or statutory instructional time per day. When sourced from bell schedules, this is **gross / bell-to-bell** minutes (last-bell end − first-bell start), **not** net of lunch/passing/recess — see the Collection approach section and `docs/TERMINOLOGY.md`. Net minutes is a deferred future enhancement.

**Sources**:
1. **Primary (Phase 1.5+)**: Actual bell schedules from district/school websites (gross bell-to-bell)
2. **Fallback (Phase 1)**: State statutory minimum requirements

**Variations**:
- Range: 240-420 minutes across U.S. states (statutory)
- Actual schedules often exceed statutory minimums
- Grade-level differences in many states
- District-specific policies may vary

**Minutes-source priority** (see `docs/ACQUISITION_PIPELINE.md` for the current pipeline):

> The earlier district-ranking tier system (manual top-districts / Firecrawl / Gemini) was retired in Jan 2026 and replaced by a single local-first pipeline plus a statutory fallback. Minutes now come from a priority cascade, not a per-district tier assignment.

**1. Actual bell schedule (preferred)**:
- Acquired automatically by the local-first Crawlee + Ollama pipeline: site mapping → Ollama URL ranking → PDF capture → Ollama triage → local time extraction
- Or human-collected where the pipeline can't reach the schedule
- Confidence levels track source quality (high / medium / low)

**2. State statutory requirement (fallback)**:
- State statutory minimums from `config/state-requirements.yaml`
- Applied based on district state and grade levels
- Grade-weighted averages for districts with multiple levels
- Used whenever an actual schedule is unavailable

**3. Default (360 min)**:
- Last-resort fallback when neither an actual schedule nor a state requirement is available

**Example Values (Statutory)**:
```
California (K-8):     200 minutes (minimum)
Texas (all grades):   420 minutes
New York (9-12):      330 minutes
Florida (4-12):       300 minutes
```

**Example Values (Actual - from bell schedules)**:
```
Los Angeles Unified Elementary:  360 minutes (actual)
NYC DOE Middle School:            375 minutes (actual)
Chicago PS High School:           390 minutes (actual)
```

**Data Quality Tracking**:
- Source: `web_search`, `district_policy`, `school_sample`, or `state_statutory`
- Confidence: `high`, `medium`, `low`, or `assumed`
- Documentation: URLs and sampling methodology recorded

See **Bell Schedule Sampling Policy** (below) for the sampling methodology, and
`docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE1_QUEUE_DESIGN_2026-06.md` for its Stage-1 implementation.

#### 2. Staff Count (Multiple Scopes)

**Definition**: Number of full-time equivalent (FTE) staff, with scope varying by LCT variant

**Source**: NCES CCD Staff file (LEA 059) - provides 24 distinct staff categories

**Staff Categories by Tier**:

**Tier 1 - Classroom Teachers** (used in all scopes):
- Teachers (total)
- Elementary Teachers
- Secondary Teachers
- Kindergarten Teachers
- Pre-kindergarten Teachers
- Ungraded Teachers

**Tier 2 - Instructional Support** (added in LCT-Instructional):
- Instructional Coordinators and Supervisors
- Librarians/Media Specialists
- Library/Media Support Staff
- Paraprofessionals/Instructional Aides

**Tier 3 - Student Support** (added in LCT-Support):
- Guidance Counselors
- School Psychologists
- Student Support Services Staff

**Tier 4 - Administrative** (added in LCT-All):
- LEA Administrators
- School Administrators
- Administrative Support Staff
- Other Staff

**Scope Calculation Formulas** (December 2025):

```python
# Teacher-level aggregates (NO Pre-K, NO ungraded)
teachers_k12 = (teachers_elementary + teachers_secondary + teachers_kindergarten)
teachers_elementary_k5 = (teachers_elementary + teachers_kindergarten)
teachers_secondary_6_12 = teachers_secondary

# LCT-Teachers: Most conservative K-12 teachers only (NO ungraded)
scope_teachers_only = teachers_k12

# LCT-Core: K-12 teachers + ungraded (NO Pre-K)
scope_teachers_core = (teachers_elementary + teachers_secondary +
                       teachers_kindergarten + teachers_ungraded)

# LCT-Instructional: Core + coordinators + paras (NO Pre-K teachers)
scope_instructional = (scope_teachers_core +
                       instructional_coordinators +
                       paraprofessionals)

# LCT-Support: Instructional + counselors + psychologists
scope_instructional_plus_support = (scope_instructional +
                                    counselors_total +
                                    psychologists +
                                    student_support_services)

# LCT-All: All staff except Pre-K teachers
scope_all = sum(all_staff_categories) - teachers_prek
```

**Critical Decision**: Ungraded teachers are **EXCLUDED** from `scope_teachers_only` but **INCLUDED** in `scope_teachers_core` and all broader scopes. This ensures the most conservative teacher scope excludes ambiguous grade assignments while broader scopes capture all classroom staff.

**Data Storage**:
- `staff_counts` table: Historical raw data from all sources (one row per district/year/source)
- `staff_counts_effective` table: Resolved current values with pre-calculated scopes
- All 5 scope values are pre-computed for query performance

**Challenges**:
- FTE vs headcount reporting varies
- Part-time teacher accounting inconsistent
- Charter school reporting differs
- Some staff categories may overlap (e.g., reading specialists counted as teachers)
- District-level data may mask school-level variation

#### 3. Student Enrollment

**Definition**: Student membership count, with scope varying by LCT variant

**Source**: NCES CCD Membership file (LEA 052 - October count)

**Grade-Level Breakdown**:

Individual grade counts aggregated by level:
- **Pre-K**: Pre-Kindergarten enrollment
- **Elementary (K-5)**: Kindergarten + Grades 1-5
- **Middle (6-8)**: Grades 6-8
- **High (9-12)**: Grades 9-12
- **Other**: Ungraded, Adult Ed, Grade 13

**Enrollment by LCT Scope** (December 2025 - All scopes use K-12):

| LCT Variant | Enrollment Used | Rationale |
|-------------|-----------------|-----------|
| **All base scopes** | **K-12 enrollment** | Pre-K excluded for consistency |
| LCT-Teachers-Elementary | K-5 enrollment | Elementary grades only |
| LCT-Teachers-Secondary | 6-12 enrollment | Secondary grades only |

**Enrollment Calculations**:
```python
# All base scopes use K-12 enrollment
enrollment_k12 = sum(grades K through 12)  # excludes Pre-K

# Level-based variants use level-specific enrollment
enrollment_elementary = sum(grades K through 5)
enrollment_secondary = sum(grades 6 through 12)
```

**Data Storage**:
- `enrollment_by_grade` table: Grade-level enrollment for each district
- `enrollment_total`: Sum of all grades (including Pre-K)
- `enrollment_k12`: Sum of K-12 only (excluding Pre-K)
- `enrollment_elementary`: Sum of K-5
- `enrollment_secondary`: Sum of 6-12

**Pre-K Exclusion Rationale**:
- Heterogeneous Pre-K availability across districts (some offer Pre-K, some don't)
- Different state licensing requirements for Pre-K staffing
- Excludes Pre-K from both enrollment AND staffing for mathematical consistency

**Considerations**:
- October count may not reflect year-average
- Some students may be counted multiple times (dual enrollment)
- Pre-K exclusion ensures mathematical consistency with teachers_core scope
- Districts serving only some grade levels will have zero enrollment for others

---

## Detailed Example

### Sample District

**District Name**: Example Unified School District  
**State**: California  
**Grade Span**: K-12

#### Data Inputs

```
Student Enrollment (MEMBER):           8,500 students
Instructional Staff (TEACHERS):        425 FTE
Daily Instructional Minutes:
  - K-8:    200 minutes (6,000 students, 71%)
  - 9-12:   360 minutes (2,500 students, 29%)
```

#### Step 1: Calculate Weighted Daily Minutes

```
Weighted Minutes = (6,000 × 200 + 2,500 × 360) / 8,500
                 = (1,200,000 + 900,000) / 8,500
                 = 2,100,000 / 8,500
                 = 247 minutes (weighted average)
```

#### Step 2: Calculate Total Available Instructional Minutes

```
Total Minutes = 247 minutes × 425 teachers
              = 104,975 minutes
```

#### Step 3: Calculate LCT

```
LCT = 104,975 minutes / 8,500 students
    = 12.35 minutes per student per day
```

#### Interpretation

**Daily**: Each student receives approximately 12.4 minutes of potential individual teacher attention per day

**Weekly**: 12.4 × 5 = 62 minutes per week

**Yearly**: 12.4 × 180 = 2,232 minutes = 37.2 hours per year

**Comparison**: A district with 15 minutes LCT provides 21% more potential individual attention

---

## Critical Limitations

### The "Individualization Fallacy"

**Issue**: The basic LCT formula assumes all instructional time could theoretically be one-on-one.

**Reality**: 
- Most instruction is whole-class or small-group
- Individual attention is a fraction of total time
- Actual 1-on-1 time varies by grade, subject, and teaching approach

**Mitigation**: 
- LCT is a *relative* measure for comparison, not an *absolute* measure
- Always present as "potential" or "available" time
- Use for district-to-district comparisons, not as standalone metric

### The "Time-as-Quality Assumption"

**Issue**: More time does not automatically equal better education.

**Reality**:
- Quality of instruction matters more than quantity
- Effective use of time varies widely
- 10 minutes of high-quality instruction > 20 minutes of poor instruction

**Mitigation**:
- LCT is a *resource* metric, not an *outcome* metric
- Never use LCT alone to judge educational quality
- Combine with quality indicators in analysis

### The "Averaging Deception"

**Issue**: District-level LCT masks within-district variations.

**Reality**:
- Some schools in a district may have much higher/lower ratios
- Magnet schools, specialized programs create variance
- Tracking and ability grouping affect actual time distribution

**Mitigation**:
- Calculate school-level LCT where data available
- Report variance alongside mean
- Highlight within-district equity concerns

### Other Limitations

**Statutory vs Actual Time**
- Using minimum required time, not actual schedules
- Some districts exceed minimums
- Actual bell schedules not in federal data

**Staff Count Issues**
- FTE reporting inconsistencies
- Contracted vs employed staff
- Teacher quality not considered in basic formula

**Enrollment Timing**
- October count may not represent year average
- Enrollment fluctuates during year
- Some students may be double-counted

---

## Data Requirements

### Minimum Data (Phase 1)

| Data Element | Source | Required |
|--------------|--------|----------|
| District ID | NCES CCD | Yes |
| Student Enrollment | NCES CCD Membership | Yes |
| Teacher FTE | NCES CCD Staff | Yes |
| State Location | NCES CCD Directory | Yes |
| Instructional Minutes | State education code | Yes |

### Enhanced Data (Phase 2+)

| Data Element | Source | Purpose |
|--------------|--------|---------|
| Teacher Experience | State/CRDC | Quality weighting |
| Teacher Education | State/CRDC | Quality weighting |
| Class Size Distribution | CRDC | Within-school analysis |
| Student Needs (SPED, ELL) | NCES CCD/State | Differentiated needs |
| Bell Schedule | District/State | Actual vs statutory time |

---

## Quality Assurance

### Data Quality Filtering (Scope-Aware)

**Automated Validation**: All LCT calculations are validated against data quality criteria. Invalid calculations are excluded from publication-ready outputs but retained in complete datasets for transparency.

**Universal Validation Criteria** (applied to all scopes):

1. **0 < LCT ≤ 360**: LCT must be positive and cannot exceed maximum daily instructional time
2. **enrollment > 0**: Districts must have at least one student
3. **staff_count > 0**: Staff count for the scope must be positive
4. **staff_count ≤ enrollment**: Cannot have more staff than students (for the scope)

**Scope-Specific Validation** (December 2025):

| LCT Variant | Enrollment Check | Staff Check | Special Rules |
|-------------|------------------|-------------|---------------|
| LCT-Teachers | enrollment_k12 > 0 | teachers_k12 > 0 | K-12 only, NO ungraded |
| LCT-Core | enrollment_k12 > 0 | teachers_core > 0 | K-12 only, includes ungraded |
| LCT-Instructional | enrollment_k12 > 0 | scope_instructional > 0 | K-12 only |
| LCT-Support | enrollment_k12 > 0 | scope_support > 0 | K-12 only |
| LCT-All | enrollment_k12 > 0 | scope_all > 0 | K-12 only |
| LCT-Teachers-Elementary | enrollment_elementary > 0 | teachers_elementary_k5 > 0 | K-5 only |
| LCT-Teachers-Secondary | enrollment_secondary > 0 | teachers_secondary_6_12 > 0 | 6-12 only |

**Level-Based QA Validation**:

For teacher-level variants (Elementary, Secondary), additional validation checks:
- `Elementary teachers but no elementary enrollment`: Flag districts with K-5 teachers but zero K-5 students
- `Secondary enrollment but no secondary teachers`: Flag districts with 6-12 students but zero secondary teachers
- `Elementary enrollment but no elementary teachers`: Flag districts with K-5 students but zero K-5 teachers
- All issues captured in `level_lct_notes` column for transparency

### Data Safeguards (January 2026)

Additional safeguards identify potential data quality issues that don't warrant automatic exclusion but should be flagged for transparency. These flags are appended to the `level_lct_notes` column.

**Error Flags (ERR_)** - Indicate likely data quality issues:

| Flag | Condition | Description |
|------|-----------|-------------|
| `ERR_FLAT_STAFF` | All 5 base scopes have identical staff counts | District likely only reported teachers, filling other NCES categories with zeros |
| `ERR_IMPOSSIBLE_SSR` | Staff-to-student ratio > 0.5 | More than 1 staff per 2 students is physically implausible for standard K-12 |
| `ERR_VOLATILE` | K-12 enrollment < 50 | Small enrollment creates high statistical volatility (±30-40 min LCT per staff change) |
| `ERR_RATIO_CEILING` | teachers_only = all staff (100%) | Indicates incomplete reporting (no support staff recorded) |

**Warning Flags (WARN_)** - Indicate unusual but potentially valid data:

| Flag | Condition | Description |
|------|-----------|-------------|
| `WARN_LCT_LOW` | LCT < 5 minutes | Very high enrollment relative to staff; may indicate large urban district |
| `WARN_LCT_HIGH` | LCT > 120 minutes (teachers_only scope) | Very low enrollment relative to staff; may indicate small/specialized district |
| `WARN_SPED_RATIO_CAP` | SPED LCT would exceed 360 | High SPED teacher-to-self-contained-student ratio; LCT capped at 360 for consistency |

**Note on SPED Ratio Cap**: Some states have high ratios of SPED teachers to self-contained SPED students (e.g., CT: 2.8 teachers per student). This produces theoretical LCT values exceeding the school day. These are capped at 360 minutes and flagged for transparency. The high ratio reflects that SPED teachers serve both self-contained and mainstreamed students, but we can only measure their ratio against self-contained enrollment.

**Safeguard Counts** (2023-24 data, January 2026):

| Flag | Records Flagged | Estimated Districts |
|------|-----------------|---------------------|
| ERR_FLAT_STAFF | 190 | ~38 |
| ERR_IMPOSSIBLE_SSR | 1,065 | ~213 |
| ERR_VOLATILE | 2,945 | ~589 |
| ERR_RATIO_CEILING | 190 | ~38 |
| WARN_LCT_LOW | 416 | ~83 |
| WARN_LCT_HIGH | 127 | ~127 |
| WARN_SPED_RATIO_CAP | 8,800 | ~4,400 |

**Usage Recommendations**:
- For **policy analysis**: Consider excluding `ERR_FLAT_STAFF` and `ERR_RATIO_CEILING` districts from LCT-All/Support scopes
- For **state comparisons**: Exclude `ERR_VOLATILE` districts to reduce noise
- For **publication**: Document which safeguards were applied and why

**Implementation**:
- Script: `infrastructure/scripts/analyze/calculate_lct_variants.py`
- Outputs (with ISO 8601 UTC timestamp):
  - `lct_all_variants_YYYY_YY_<timestamp>.csv`: Complete dataset with `level_lct_notes` column
  - `lct_all_variants_YYYY_YY_valid_<timestamp>.csv`: Filtered (0 < LCT ≤ 360)
  - `lct_variants_summary_YYYY_YY_<timestamp>.csv`: Summary statistics by scope
  - `lct_variants_by_state_YYYY_YY_<timestamp>.csv`: State-level summary
  - `lct_variants_report_YYYY_YY_<timestamp>.txt`: Detailed methodology and findings

**Timestamp Convention**:
- Format: `YYYYMMDDTHHMMSSZ` (ISO 8601, UTC, filesystem-safe)
- Example: `lct_all_variants_2023_24_valid_20251228T012536Z.csv`
- Benefits: Sortable, unambiguous timezone, enables version tracking

**Results** (December 2025):

| Scope | Valid Districts | Mean LCT | Median LCT |
|-------|-----------------|----------|------------|
| teachers_only | 14,286 | 27.9 min | 25.2 min |
| teachers_elementary | 13,090 | 34.3 min | 30.8 min |
| teachers_secondary | 12,378 | 22.9 min | 20.1 min |
| teachers_core | 14,305 | 29.5 min | 26.2 min |
| instructional | 14,314 | 38.4 min | 34.2 min |
| instructional_plus_support | 14,271 | 42.2 min | 37.9 min |
| all | 14,250 | 59.8 min | 54.5 min |

**Districts with QA Notes**: 2,109 (14.3% of districts have level-based validation notes)

**Publication Policy**:
- **Always use `*_valid.csv` files for external communications**
- Report which scope(s) were used and why
- Document any scope-specific filtering applied

### Statistical Validation Checks

**Post-Filtering Checks** (per scope):
- [x] LCT values are positive
- [x] LCT values are ≤ 360 minutes (maximum daily time)
- [x] Broader scopes produce higher LCT (expected pattern)
- [x] Distribution shape analysis by scope
- [x] State-level consistency across scopes

**Expected Relationships** (validate these hold):
```
LCT-Teachers-Secondary < LCT-Teachers < LCT-Teachers-Elementary
LCT-Teachers < LCT-Core < LCT-Instructional < LCT-Support < LCT-All
```

Note: Elementary > Overall > Secondary because elementary schools typically have lower student-teacher ratios.

**Ongoing Monitoring**:
- State-level mean/median comparison by scope
- Year-over-year consistency (when available)
- Cross-validation with state-reported ratios
- Scope ratio consistency (e.g., LCT-All / LCT-Teachers should be stable)

### Outlier Investigation

When valid districts show unusual LCT patterns:

**LCT < 10 minutes** (any scope):
- Very high enrollment relative to staff
- Common in large urban districts
- Verify enrollment data accuracy

**LCT > 100 minutes** (LCT-All scope):
- Very low enrollment relative to total staff
- Common in rural or specialized districts
- May indicate administrative-heavy staffing

**Scope Ratio Anomalies**:
- If LCT-All < LCT-Teachers: Data quality issue (scope_all calculation error)
- If LCT-Core > LCT-Teachers: Pre-K data inconsistency
- Investigate and flag for review

### QA Dashboard: generating & interpreting reports

`calculate_lct_variants.py` auto-generates a QA dashboard alongside every calculation run — this is the
operational reference for reading it (validation *rules* are above; this is *how to run and act on* them).
Consolidated 2026-07-02 from the former standalone `QA_DASHBOARD.md` (archived, `docs/archive/`).

**Generate + view:**
```bash
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24
cat data/enriched/lct-calculations/lct_qa_report_2023_24_<timestamp>.json | jq
```

**Console output** (abbreviated):
```
QA DASHBOARD
Status: PASS · Pass Rate: 99.46%
Hierarchy Checks: ✓ Secondary < Overall Teachers  ✓ Teachers < Core  ✓ Core < Instructional
                  ✓ Instructional < Support  ✓ Support < All
Outliers Detected: 20 (5 very low, 15 very high)
State Coverage: 48 states/territories · Districts Processed: 14,314
```

**JSON report** (`data/enriched/lct-calculations/lct_qa_report_<year>_<timestamp>.json`) carries
`metadata`, `data_quality` (total/valid/invalid/pass_rate), `scope_summary` (per-scope mean/median/min/max),
`hierarchy_validation` (per-check pass/fail with the compared means), `state_coverage`, `outliers[]`
(district_id/name/scope/issue/severity), and `overall_status`.

**Interpreting status:** PASS = pass rate ≥95%, all hierarchy checks passing, outliers documented, adequate
state coverage → proceed. Otherwise (pass rate <95%, any hierarchy failure, unexpected outliers, missing
major-state data) → investigate before publishing.

**Investigating a flagged outlier:**
```python
from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, LCTCalculation

with session_scope() as session:
    district = session.query(District).filter_by(nces_id="3900528").first()
    lcts = session.query(LCTCalculation).filter_by(district_id="3900528", year="2023-24").all()
    for lct in lcts:
        print(f"{lct.scope}: {lct.lct_value} min (staff={lct.staff_count}, enrollment={lct.enrollment})")
```

**Common outlier patterns:** virtual/online schools (very low LCT, minimal staff — e.g. Findlay Digital
Academy 0.4 min, document and consider excluding from equity analysis); Intermediate Units / IUs (very high
LCT from specialized staffing — e.g. Berks County IU 14, 284.6 min — note as special-purpose, not a typical
district); charter/alternative schools (highly variable ratios, verify data accuracy).

**Thresholds** are constants in `calculate_lct_variants.py` (`LOW_LCT_THRESHOLD = 5`,
`HIGH_LCT_THRESHOLD = 200`, `MIN_PASS_RATE = 0.95`) — adjust there, not in this doc.

**Troubleshooting:**
- No console output → confirm the script version has `generate_qa_report` (`grep generate_qa_report
  infrastructure/scripts/analyze/calculate_lct_variants.py`).
- JSON report missing → check output-directory permissions (`data/enriched/lct-calculations/`).
- Hierarchy check failure → check the underlying enrollment/staffing data first, then whether a small
  sample size is violating the expected pattern, then whether a scope definition changed.

### Data Source Transparency

For mixed-year data (enrollment, staffing, and bell schedules from different years), document component years:

```json
{
  "component_years": {
    "enrollment": "2023-24",
    "staffing": "2024-25",
    "bell_schedule": "2025-26"
  },
  "data_sources": {
    "enrollment": "nces_ccd",
    "staffing": "nces_ccd",
    "bell_schedule": "automated_enrichment"
  }
}
```

**Transparency Requirements**:
- All published LCT values must include component year metadata
- Data source must be documented for each component
- Mixed-year calculations are acceptable with disclosure

---

## SPED Segmentation (self-contained vs. mainstreamed)

Consolidated 2026-07-02 from the former standalone `SPED_SEGMENTATION_IMPLEMENTATION.md` (archived,
`docs/archive/`). Implemented as of the v3 (2026-01-03) self-contained-focus design.

**Key concept.** SPED students split into two groups with very different instructional relationships:
**self-contained** (~6.7% of all SPED nationally — separate class, separate school, or inside regular class
<40% of the day) are taught primarily by SPED teachers and are the correct denominator for SPED
teacher-to-student ratios; **mainstreamed** (~93.3% — inside regular class 40%+ of the day) are taught
primarily by GenEd teachers and belong in the GenEd population for LCT purposes.

**Three SPED scopes:**

| Scope | Formula | Purpose | Mean LCT (2023-24) |
|---|---|---|---|
| `core_sped` | SPED teachers / self-contained SPED enrollment | Primary SPED attention metric | 185.5 min |
| `teachers_gened` | GenEd teachers / GenEd enrollment (incl. mainstreamed SPED) | Primary GenEd comparison | 27.2 min |
| `instructional_sped` | (SPED teachers + SPED paras) / self-contained SPED enrollment | Fuller SPED support picture | 265.8 min |

**Data sources (2017-18 pre-COVID baseline — exempt from the 3-year window rule, see Temporal Data
Blending below):** IDEA 618 Personnel (`bpersonnel2017-18.csv` — SPED teacher/para FTE by state, ages 6-21),
IDEA 618 Child Count & Educational Environments (`bchildcountandedenvironments2017-18.csv` — self-contained
vs. mainstreamed split by state), CRDC 2017-18 Enrollment (`Enrollment.csv` — LEA-level total SPED count,
no environment breakdown), CCD 2017-18 LEA Membership (LEA-level total enrollment).

**Two-step estimation** (per current-year district): estimated all-SPED = total enrollment × LEA SPED
proportion (CRDC/CCD, LEA-specific for 74% of districts, state-average fallback otherwise) → estimated
self-contained SPED = all-SPED × state self-contained proportion (IDEA 618, national avg 6.7%, range
6.6–9.9%) → GenEd enrollment = total − self-contained → SPED teachers = self-contained × state teacher
ratio → SPED instructional = self-contained × state instructional ratio → GenEd teachers = total teachers
− SPED teachers.

**Audit validation (passes):** self-contained + GenEd = total enrollment; SPED teachers + GenEd teachers ≈
total teachers; and critically, the **weighted average** of `core_sped` and `teachers_gened` LCT equals the
overall `teachers_only` LCT (difference ≈ 0.00 — confirms the segmentation correctly partitions both
enrollment and teachers, not just one side).

**Database tables:** `sped_state_baseline` (56 states/territories, IDEA 618 ratios), `sped_lea_baseline`
(18,606 LEAs, CRDC/CCD SPED proportion), `sped_estimates` (16,459 districts for 2023-24, the applied
two-step estimate + `confidence` high/medium/low). Scripts: `infrastructure/database/migrations/
import_sped_baseline.py`, `apply_sped_estimates.py`; consumed by `calculate_lct_variants.py`.

**Known limitations:** the self-contained proportion is a state-level ratio applied to an LEA-level
estimate (not directly measured per-LEA); it varies by state (6.6–9.9%); para allocation may not reflect
LEA-level variation; ~6 districts show negative GenEd-teacher estimates (flagged low-confidence); ~940
districts are skipped for missing state ratios (territories, etc.). See `WARN_SPED_RATIO_CAP` above for
the related LCT-ceiling cap on high-ratio states (e.g. CT).

---

## Evolution Roadmap

The LCT methodology will evolve through six phases, each addressing specific limitations while maintaining the core metric's simplicity and rhetorical power.

### Phase 2: Teacher Quality Weights

**Target**: Account for teacher experience and qualifications

**Formula Enhancement**:
```
Weighted Staff = Σ (Teachers × Experience Weight × Education Weight)
LCT = (Daily Minutes × Weighted Staff) / Enrollment
```

**Weights** (Provisional):
- Experience: 1.0 (0-3 years) → 1.2 (10+ years)
- Education: 1.0 (BA) → 1.1 (MA) → 1.15 (PhD)

**Data Required**: Teacher credential and experience data from state sources

**Challenge**: Avoiding implications that novice teachers are "lesser"

### Phase 3: Differentiated Student Needs

**Target**: Account for students requiring more attention (SPED, ELL, etc.)

**Formula Enhancement**:
```
Weighted Enrollment = Σ (Students × Needs Multiplier)
LCT = (Daily Minutes × Staff) / Weighted Enrollment
```

**Multipliers** (Provisional):
- General education: 1.0
- ELL: 1.3
- SPED (mild): 1.5
- SPED (moderate): 2.0
- SPED (severe): 3.0
- Gifted: 1.2

**Data Required**: Student program enrollment from NCES CCD or state

**Challenge**: Avoiding deficit framing of student populations

### Phase 4: Interaction Quality Dimensions

**Target**: Incorporate class size and instructional model variations

**Approach**: 
- Calculate LCT at school level where possible
- Adjust for known class size distributions
- Consider instructional models (co-teaching, etc.)

**Data Required**: CRDC class size data, school-level staff assignments

### Phase 5: Opportunity-to-Connect Scores

**Target**: Create composite metric incorporating multiple dimensions

**Components**:
- Base LCT
- Teacher quality
- Student needs
- Accessibility factors (scheduling, structure)
- Resource availability

**Output**: 0-100 score representing overall opportunity

### Phase 6: Outcome-Validated Connection Time

**Target**: Correlate with student outcomes and establish thresholds

**Approach**:
- Statistical analysis: LCT vs achievement, growth, graduation
- Identify potential threshold effects
- Validate assumptions about "enough" connection time

**Cautions**: 
- Correlation ≠ causation
- Many confounding variables
- Avoid deterministic interpretations

---

## Reporting Guidelines

### Appropriate Framing

✅ **Good**: "District A provides students with an average of 15 minutes of potential individual teacher attention per day, compared to 18 minutes in District B."

❌ **Bad**: "District A is worse than District B."

✅ **Good**: "The 20% difference in LCT between these districts serving similar populations raises equity concerns."

❌ **Bad**: "Students in District A are receiving inadequate education."

### Contextual Requirements

Always provide:
1. **Comparison context**: Never report single district in isolation
2. **Demographic context**: Note population served, not as excuse but as context
3. **Resource context**: Funding levels, community characteristics
4. **Limitations**: Remind readers what LCT does and doesn't measure

### Visualization Best Practices

- Use bar charts for comparisons (not pie charts)
- Sort by LCT value for easy comparison
- Include confidence intervals if calculating
- Annotate outliers with explanations
- Use color thoughtfully (avoid red/green good/bad framing)

---

## References

### State Education Codes
- California Education Code Section 46200-46206
- Texas Education Code Chapter 25, Section 25.081
- New York Education Law Section 3204
- [Additional codes documented per state]

### Research Literature
- [Citations to student-teacher ratio research]
- [Citations to instructional time research]
- [Citations to education equity frameworks]

### Technical Standards
- NCES CCD Documentation
- CRDC Data Dictionary
- Common Education Data Standards (CEDS)

---

**Methodology Version**: 2.1 (Temporal Blending Rules)
**Last Updated**: January 17, 2026
**Key Changes in v2.1**:
- Added 3-Year Window Rule for multi-source data blending
- Added temporal validation flags (WARN_YEAR_GAP, ERR_SPAN_EXCEEDED)
- Documented SPED baseline exception (2017-18 data exempt)
- Added database infrastructure for temporal validation
- Added master crosswalk table (state_district_crosswalk)
**Key Changes in v2.0**:
- All scopes now use K-12 enrollment (Pre-K excluded)
- All scopes exclude Pre-K teachers
- Added teacher-level variants (Elementary, Secondary)
- Ungraded teachers excluded from LCT-Teachers, included in broader scopes
- Added `level_lct_notes` for QA transparency
**Next Review**: Upon integration of additional state-level data

---

## Data Source Precedence

### Multi-Source Integration

LCT calculations use a **layered architecture** with State Education Agency (SEA) data superseding federal NCES data when available:

```
┌─────────────────────────────────────────────────────┐
│                Layer 2: SEA Data                    │
│   (State-reported data - supersedes when available) │
├─────────────────────────────────────────────────────┤
│          Layer 1: NCES CCD Foundation               │
│     (17,842 districts - national baseline)          │
└─────────────────────────────────────────────────────┘
```

**Precedence Rules (January 2026)**:

**Rule 1 - State Over Federal**: SEA data supersedes NCES CCD data when available **and within 3-year temporal window**.
- Example: PA SEA 2024-25 supersedes NCES 2023-24 (2-year span = valid)
- Example: FL SEA 2024-25 supersedes NCES 2023-24 (2-year span = valid)
- Example: Hypothetical 2026-27 SEA would NOT supersede 2023-24 NCES (4-year span = rejected)

**Rule 2 - Temporal Validation Required**: All multi-source blending must satisfy the 3-year window rule.
- See "Temporal Data Blending (3-Year Window Rule)" section below
- Flags: `WARN_YEAR_GAP` (2-3 years), `ERR_SPAN_EXCEEDED` (>3 years)

**Rule 3 - Single Source per District**: All staff data for a given district must come from a single source.
- Do not mix SEA teachers with NCES paraprofessionals for same district
- If SEA data is incomplete or outside temporal window, use NCES entirely for that district
- Metadata tracking: `primary_source` and `sources_used` fields document which source was used

**Rule 4 - Granular Enhancement (Selective)**: For states with granular teacher breakdowns:
- **Florida**: Use `ese_teachers` (SPED) and `classroom_teachers` (GenEd) for SPED scopes
- **Other states**: Use aggregate teacher counts only
- NCES granular data (elementary/secondary) used where SEA doesn't provide breakdown

**Rule 5 - NCES LEA Structure Precedence**: When state and federal sources disagree on LEA definitions (e.g., charter school treatment), **always use NCES CCD structure**.
- **Rationale**: Maintains national cohesion and consistency across analyses
- **Example**: California treats some charter schools as separate LEAs; if NCES treats them differently, use NCES structure
- **Implementation**: Use NCES `LEAID` as primary key; crosswalk state identifiers to NCES IDs
- **Documentation**: Note structural differences in state-specific documentation

**Rule 6 - Career and Technical Center (CTC) Exclusion**: Multi-district CTCs — and, as of the 2026-06-22 expansion below, the broader NCES LEA-type buckets they mostly live in — are excluded from national LCT calculations and the acquisition queue.
- **Rationale**: CTCs serve students part-time from multiple districts, causing artificially inflated teacher-to-student ratios in NCES data.
- **Impact**: 600 districts excluded nationally (expanded 2026-06-22 from an initial 152; see below). 39 charter LEAs with career/tech branding (e.g. "California Innovative Career Academy District") correctly NOT excluded — tagged per REQ-060 instead, since they're normal full-time schools, not part-time shared-service entities.
- **Identification (initial pass, 152):** name pattern (career, technical, vocational) **AND** NCES `LEA_TYPE_TEXT` does not contain "charter."
- **Identification (expanded 2026-06-22 to 600):** a real district — Pima County JTED (Joint Technical Education District), AZ — slipped through the name-only pattern into a live acquisition-queue batch, because "JTED" doesn't literally spell out "technical." Investigating turned up a cluster of similarly-named AZ JTEDs/CTEDs, which led to checking `LEA_TYPE_TEXT` more broadly. Expanded identification is the union of: (a) name pattern, now also including `jted`/`cted`; (b) `LEA_TYPE_TEXT` in `{"Specialized public school district", "Service agency", "State operated agency"}`. Either condition flags a candidate unless `LEA_TYPE_TEXT` contains "charter" (a disjoint bucket — `"Independent charter district"` — so this only ever matters for name-pattern matches, never the blanket type match).
- **Known, accepted trade-off (not a silent side effect):** the three blanket-excluded `LEA_TYPE_TEXT` buckets are NOT CTC-only. `"Specialized public school district"` (444 total) splits roughly into 152 with a narrow 9-12 span (real CTC/vocational-technical pattern) vs. 91 with a full PK-12 span (full-time state schools — deaf/blind institutes, fine-arts academies, cyber/STEM schools — that do NOT share Rule 6's part-time ratio-inflation rationale and arguably should stay in scope) vs. 116 with no grade levels at all (`GSLO`/`GSHI` = "N"/"N" — pure administrative service cooperatives, e.g. Arkansas's "Education Service Cooperative" network, which don't enroll students directly). Grade-span narrowness alone doesn't cleanly separate these either — e.g. "Arkansas Correctional Schools" has the same narrow 9-12 span as a real CTC but for an unrelated reason (serving incarcerated students, not part-time multi-district vocational programs). **Decision: blanket-exclude all three buckets anyway, accepting the cost of incorrectly excluding the full-span special-purpose schools.** Rationale: these buckets are small relative to the ~19K-LEA corpus, most genuine members ARE CTC-pattern, and building a surgical classifier to rescue the legitimate special-purpose minority is deferred, separate work, not worth blocking the acquisition pipeline build on. Revisit if/when these specific schools' exclusion turns out to matter (e.g. an equity-analysis use case that specifically wants deaf/blind or similar specialized-population schools in scope).
- **Status**: the schema columns (`is_career_technical_center`, `is_shared_service_entity`) existed since this rule was designed but were never actually populated until 2026-06-22 — the exclusion was a no-op in every LCT calculation prior to that date. Backfilled via `infrastructure/database/migrations/apply_ctc_classification.py` (idempotent — re-running after expanding the criteria only adds flags, never reverts one). Sets both columns (the LCT filter checks `is_shared_service_entity`; the originally documented fix only proposed `is_career_technical_center`).
- **See**: `docs/technical-notes/PA_CTC_DATA_DISCREPANCY.md` for the original detailed analysis.

**Rule 7 - Grade-Span Data Integrity Exclusion (Acquisition Queue)**: A district is excluded from the bell-schedule **acquisition queue** if its school-level roster doesn't actually cover the grade range its LEA-level record claims.
- **Rationale**: Decided 2026-06-22 during the acquisition-pipeline Stage 1 design. The LEA-level `GSLO`/`GSHI` declares the district's overall grade span; the school-level union (each open school's own `GSLO`/`GSHI`, classified into elementary/middle/high via `school_sampling.bands_for()`) shows which bands are *actually* covered by a real school. When a band the LEA claims to serve has **zero** schools covering it (e.g. LEA-level says K-12, but the school roster is K-5 + 9-12 with nothing spanning grades 6-8), that's a discontinuity — a true gap in the served range, not merely a band the district doesn't serve at all. Treated as a data-integrity red flag rather than a benign quirk: in a project where queue targeting depends on trusting NCES's school roster, an internally-inconsistent roster isn't safe to sample from.
- **Not a flag for "this district doesn't serve this band"**: a K-8 district legitimately has zero high schools (LEA-level span ends at grade 8, not claimed) — that's normal, not a gap. The rule only fires when the LEA-level span *claims* a band and the school-level union shows no coverage for it, at either an edge or in the middle of the range.
- **Impact**: TBD — not yet run against the full corpus; will be measured when Stage 1 queue-building is implemented.
- **Implementation**: Acquisition pipeline only (`infrastructure/acquisition/discovery/`), not the core LCT enrollment/staff calculation — `calculate_lct_variants.py` doesn't consume per-school grade-span data, so this rule doesn't change LCT calculation eligibility, only acquisition-queue eligibility. Recorded as `ERR_GRADE_SPAN_GAP` (naming to be finalized) when Stage 1 is built; see `docs/ACQUISITION_PIPELINE.md`.

### States with SEA Data Integration (Tier 1 Complete - January 2026)

| State | Year | Staff Data | Enrollment Data | Districts | Status |
|-------|------|------------|-----------------|-----------|--------|
| FL | 2024-25 | ✅ Classroom + ESE teachers | ✅ Total K-12 | 76 | Complete |
| IL | 2023-24 | ✅ Total teacher FTE | ✅ Total enrollment | 864 | Complete |
| MA | 2024-25 | ✅ Teachers FTE | ✅ Total enrollment | 396 | **Complete (Jan 19, 2026)** |
| MI | 2023-24 | ✅ Total teacher FTE | ✅ Total K-12 | 836 | Complete |
| NY | 2023-24 | ✅ Staff by category | ✅ By subgroup | 625 | Complete |
| PA | 2024-25 | ✅ Classroom teachers FTE | ✅ Total K-12 | 777 | Complete |
| VA | 2025-26 | ✅ Teachers FTE | ✅ Total enrollment | 131 | Complete |

**Total Tier 1: 7 states, 3,971 districts with SEA data superseding federal NCES**

### Future State Integrations (Tier 2)

| State | Districts | Data Availability | Priority |
|-------|-----------|-------------------|----------|
| TX | 1,234 | Identifiers only (need staff/enrollment) | High |
| CA | 1,037 | Funding/SPED only (need staff/enrollment) | High |
| OH | ~600 | Not yet sourced | Medium |
| GA | ~200 | Not yet sourced | Medium |

### Available Data Sources

| Source | Type | Latest Year | Coverage | Access |
|--------|------|-------------|----------|--------|
| NCES CCD | Federal | 2023-24 | National (17,842 districts) | CSV download |
| CRDC | Federal | 2021-22 | National (biennial) | Data portal |
| Census School Finance | Federal | 2022-23 | National | CSV download |
| State Portals | State | 2022-23 typical | State-specific | Varies |

### Year-Over-Year Stability Assumption

When using staffing data from a different year than enrollment:
- Teacher turnover is ~8% annually (typical)
- Staff-to-enrollment ratios are generally stable year-over-year
- Acceptable to use 2022-23 or 2024-25 staffing with 2023-24 enrollment
- Document the mixed years in output metadata

See `docs/STAFFING_DATA_ENHANCEMENT_PLAN.md` for complete data source strategy

---

## Temporal Data Blending (3-Year Window Rule - REQ-026)

### Overview

LCT calculations often combine data from multiple sources with different release years. This section documents the rules for acceptable temporal blending (REQ-026).

### The 3-Year Window Rule

**Rule**: When blending data from multiple sources, the **year span** from oldest to newest source must not exceed 3 years.

**Definition**: Year Span = |newest_start_year - oldest_start_year|

**Clarification** (Corrected January 2026):
- Same year (e.g., 2023-24 and 2023-24): span = 0
- Adjacent years (e.g., 2023-24 and 2024-25): span = 1
- 1-year gap (e.g., 2023-24 and 2025-26): span = 2
- 2-year gap (e.g., 2023-24 and 2026-27): span = 3

**Examples**:

| Datasets Used | Year Span | Flags | Valid? |
|---------------|-----------|-------|--------|
| 2023-24, 2023-24 | 0 | None | ✅ Valid |
| 2023-24, 2024-25 | 1 | None | ✅ Valid (adjacent years) |
| 2023-24, 2025-26 | 2 | WARN_YEAR_GAP | ✅ Valid (1-year gap) |
| 2023-24, 2026-27 | 3 | WARN_YEAR_GAP | ✅ Valid (2-year gap, at limit) |
| 2023-24, 2027-28 | 4 | ERR_SPAN_EXCEEDED | ❌ Invalid (exceeds window) |

### Resolution When Span Exceeds 3 Years

When a calculation would require data spanning more than 3 years:

1. **Upgrade older dataset**: Find a newer release of the older dataset (e.g., upgrade 2023-24 NCES to 2024-25)
2. **Downgrade newer dataset**: Use an older release of the newer dataset (e.g., use 2025-26 schedule instead of 2026-27)
3. **Don't blend**: Use single-year data from a consistent source
4. **Seek user direction**: Flag for manual review and decision

### Calculation Modes (January 2026)

The system supports two calculation modes:

**BLENDED Mode (Default)**:
- Uses most recent available data for each component (enrollment, staffing, instructional time)
- Automatically selects best available data within 3-year window
- File naming: `lct_all_variants_<timestamp>.csv` (no year)

**TARGET_YEAR Mode**:
- Enrollment anchored to specific target year
- Staff and instructional time can come from within 3-year window
- File naming: `lct_all_variants_<year>_<timestamp>.csv` (year included)

Usage:
```bash
# BLENDED mode (default)
python calculate_lct_variants.py

# TARGET_YEAR mode
python calculate_lct_variants.py --target-year 2023-24
```

### Temporal Validation Flags

Calculations include temporal quality flags:

| Flag | Condition | Description |
|------|-----------|-------------|
| None | Year span 0-1 | Same year or adjacent years (e.g., 2024-25 and 2023-24) |
| `WARN_YEAR_GAP` | Year span 2-3 | Valid but sources have 1-2 year gap |
| `ERR_SPAN_EXCEEDED` | Year span > 3 | Exceeds 3-year window, requires resolution |
| `INFO_CROSS_YEAR` | Different years used | Documents cross-year blending |
| `INFO_RATIO_BASELINE` | Uses 2017-18 SPED ratios | Exempt from 3-year rule (stable ratios) |

### SPED Baseline Exception

The 2017-18 IDEA 618 and CRDC data used for SPED ratio baselines is **exempt** from the 3-year rule because:

1. **Pragmatic necessity**: Most recent pre-COVID data with complete SPED environment breakdowns
2. **Ratio stability**: SPED teacher-to-student ratios are relatively stable over time
3. **Methodological approach**: Used as proportional multipliers, not absolute values
4. **Documentation**: Clearly documented as historical baseline proxy

When newer state-level SPED data becomes available that meets quality requirements, it supersedes the 2017-18 baseline according to data precedence rules.

### Database Implementation

The database includes validation infrastructure (corrected January 2026):

```sql
-- Functions for temporal validation
school_year_to_numeric('2023-24')  -- Returns: 2023
year_span('2023-24', '2024-25')    -- Returns: 1 (adjacent years)
year_span('2023-24', '2025-26')    -- Returns: 2 (1-year gap)
is_within_3year_window('2023-24', '2024-25', '2025-26')  -- Returns: TRUE

-- Columns in lct_calculations table
year_span                 INTEGER   -- Year span (absolute difference in start years)
within_3year_window       BOOLEAN   -- TRUE if span ≤ 3
temporal_flags            TEXT[]    -- Array of validation flags

-- Automatic validation trigger
trg_lct_temporal_validation  -- Validates on INSERT/UPDATE

-- CalculationRun tracking table
calculation_mode          ENUM      -- 'blended' or 'target_year'
target_year              VARCHAR   -- Target year (nullable, required for target_year mode)
data_year_min            VARCHAR   -- Earliest source year actually used
data_year_max            VARCHAR   -- Latest source year actually used
```

### Recalculation Policy

When new data becomes available:

1. **Automatic recalculation** with newest available data
2. **3-year rule enforcement** ensures data coherence
3. **Previous calculations preserved** in calculation history
4. **Provenance tracking** documents what changed

### Output Documentation

Every LCT calculation output includes:

```json
{
  "enrollment_source_year": "2023-24",
  "staff_source_year": "2024-25",
  "bell_schedule_source_year": "2025-26",
  "year_span": 3,
  "within_3year_window": true,
  "temporal_flags": ["WARN_YEAR_GAP"]
}
```

---

## Data Processing Optimization

### Token-Efficient Data Processing (December 2024)

To enable efficient processing of 133+ districts for bell schedule enrichment while minimizing computational costs, we implemented a data optimization strategy that reduces file sizes by 88% without data loss.

#### Slim File Creation

**Problem**: NCES CCD files contain 58-15 columns but we only use 3-4 columns per file, leading to inefficient data reads and high token usage.

**Solution**: Created "slim" versions containing only essential columns:

| Original File | Size | Columns | Slim File | Size | Columns | Reduction |
|--------------|------|---------|-----------|------|---------|-----------|
| Directory (029) | 7.7 MB | 58 | `districts_directory_slim.csv` | 0.7 MB | 3 | 91% |
| Membership (052) | 618 MB | 15 | `enrollment_by_grade_slim.csv` | 81 MB | 3 | 87% |
| Staff (059) | 57 MB | 13 | `staff_by_level_slim.csv` | 1.1 MB | 3 | 98% |
| **Total** | **683 MB** | - | **Total** | **83 MB** | - | **88%** |

**Slim File Contents**:
- **Directory slim**: `LEAID`, `LEA_NAME`, `ST` (state code)
- **Enrollment slim**: `LEAID`, `GRADE`, `STUDENT_COUNT` (filtered data)
- **Staff slim**: `LEAID`, `STAFF` (category), `STAFF_COUNT` (filtered data)

**Storage Location**: `data/processed/slim/`

**Impact**:
- 88% reduction in file I/O overhead
- 88% reduction in token usage for file reads
- Faster processing times for bulk operations
- Original raw files preserved in `data/raw/` for future needs

**Usage**:
```bash
# Extraction scripts automatically detect and prefer slim files:
python infrastructure/scripts/extract/extract_grade_level_enrollment.py \\
    data/processed/slim/enrollment_by_grade_slim.csv

python infrastructure/scripts/extract/extract_grade_level_staffing.py \\
    data/processed/slim/staff_by_level_slim.csv \\
    data/processed/normalized/grade_level_enrollment_2324.csv
```

#### Processing Workflow (Optimized)

1. **One-time setup** (already completed):
   - Download raw NCES CCD files (683 MB)
   - Create slim versions (83 MB) - preserves raw files

2. **Regular processing** (uses slim files):
   - Extract grade-level enrollment from slim file (87% faster)
   - Extract grade-level staffing from slim file (98% faster)
   - Normalize and merge data
   - Calculate LCT with quality filtering

3. **Bell schedule enrichment** (manual):
   - Web search for actual bell schedules
   - Extract instructional time by grade level
   - Merge with district data
   - Document sources and confidence levels

---

## Bell Schedule Enrichment Campaign (December 2024)

### Objective

Collect actual instructional time data from the top 3 largest districts in each U.S. state to:
1. Validate state statutory requirements
2. Identify districts exceeding minimums
3. Improve LCT calculation accuracy for policy discussions
4. Establish baseline coverage across all 50 states

### Methodology

**Target**: 3 districts per state × 51 jurisdictions = ~153 districts
- Prioritize largest districts by enrollment
- Skip districts with inaccessible data, move to next-largest
- Process states in ascending population order (smallest states first)

**Collection approach**:

The current approach is **search-led discovery + tiered capture + cheap-cloud council extraction** (see `docs/ACQUISITION_PIPELINE.md`), with human collection only for districts the pipeline can't reach. The earlier local-first Crawlee+Ollama design and the manual-vs-automated district-count tiering were both retired (Jan 2026 / June 2026 respectively).

- **Automated:** domain-scoped search finds per-school (or hub) schedule pages, Playwright captures them (text layer → screenshot/OCR fallback), and a council of cheap cloud models extracts **first-bell start and last-bell end** times per band. **The metric is GROSS daily instructional minutes (end − start), bell-to-bell — lunch/passing/recess are NOT subtracted.** Models extract per-school rows; the modal band value is computed deterministically. Confidence tracks source quality (`high` / `medium` / `low`).
  - **Why gross, not net (decided June 2026):** gross needs only two numbers nearly every schedule states plainly, which sharply improves extraction accuracy; the existing ground truth is itself gross; and assumed deductions add fake precision. Gross **overstates** instructional time by ~30–60 min/day (and inconsistently, since some districts publish lunch and some don't), so it is reported and labeled as **gross / bell-to-bell** — a transparent, defensible step up from statutory minimums. **Net minutes (with real lunch/passing/recess deductions) is a deferred future enhancement.**
- **Manual follow-up:** districts blocked (Cloudflare/WAF) or not covered by the pipeline are queued for offline research.

**Security & Ethics Protocol**:
- ONE search attempt + ONE fetch attempt per district
- If blocked by Cloudflare/WAF, add to manual follow-up list
- Respect district cybersecurity measures
- Do not attempt multiple workarounds
- See `manual_followup_needed.json` for districts requiring offline research

**Data Quality Tracking**:

Each enrichment record includes:
```json
{
  "district_id": "5604510",
  "district_name": "Natrona County School District #1",
  "state": "WY",
  "elementary": {
    "instructional_minutes": 405,
    "minutes_basis": "gross_bell_to_bell",
    "start_time": "8:45 AM",
    "end_time": "3:30 PM",
    "schools_sampled": ["Lincoln Elementary", "Oregon Trail Elementary"],
    "source_urls": ["https://www.natronaschools.org/..."],
    "confidence": "high",
    "method": "district_standardized_schedule",
    "source": "District policy with standardized times"
  }
}
```

**Confidence Levels**:
- `high`: Direct bell schedule with period-by-period breakdown
- `medium`: School hours documented, instructional time estimated using state norms
- `low`: Incomplete data, significant estimation required
- `statutory`: No actual data found, using state minimum requirements

**Progress Tracking**: `data/enriched/bell-schedules/`
- Individual JSON files per district: `{district_id}_2023-24.json`
- Summary file: `enrichment_summary.txt`
- Manual follow-up tracking: `manual_followup_needed.json`

### Example: Wyoming (State #1, Pop: 0.58M)

**District 1: Natrona County SD #1** (12,446 students - K-12)
- Elementary: 345 min (8:45 AM - 3:30 PM, district standardized)
- Middle: 360 min (8:00 AM - 2:45 PM, averaged across 3 schools)
- High: 365 min (8:20 AM - 3:24 PM, verified at 3 high schools)
- Confidence: high (elementary), high (middle), medium (high - estimated instructional time)
- Sources: District website, school-specific pages, Casper Star-Tribune article
- Wyoming requirement: 900/1050/1100 hrs/year = 309/360/377 min/day (175 days)
- **Finding**: District exceeds state minimums, especially elementary

---

## Bell Schedule Sampling Policy (acquisition — 2026-06)

When acquiring bell schedules per district, we sample **schools** to estimate the **modal daily
instructional minutes per band** (elementary/middle/high) — **not a population proportion**. That
distinction determines how many schools to sample, and it kills the textbook survey-formula approach.

**Why the 95% / ±5% finite-population survey formula is the wrong tool.** Computed per-district per-band
school counts and the textbook 95/±5 finite-population sample size from NCES `ccd_sch_029`:
- Across **18,158 districts**, 95/±5 sampling = **127,513 band-extractions = 96% of a full census
  (132,803)** — the finite-population correction saves only ~4%.
- The corpus is mostly small districts (**median 4 calls/district across 3 bands; p95 = 22**), censused
  regardless. The formula only inflates a few mega-districts (LA Unified n=496, Broward 286, Orange 254) —
  maximum effort exactly where the marginal school adds least.
- The formula is statistically correct for the **wrong question**: it estimates a worst-case *proportion*
  (p=0.5), but we want the **mode**, and bell times **cluster by district policy** → the modal band-minutes
  stabilizes far below the proportion-formula n.

**The methodological stance:** **census small districts; cap large ones; sample the mode, not the
proportion.** The mode is robust to subsampling precisely because bell schedules are set by district
policy (low within-band variance), so a handful of schools usually pins a band's minutes.

**Where this is implemented — two separate decisions:**
- **Queue-time cap (Stage 1, settled):** ≤ 12 schools/band → full census; larger → cap at 12/band (seeded
  random sample, most-constrained-first overlap minimization). Implementation + rationale:
  `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE1_QUEUE_DESIGN_2026-06.md` §3.
- **Extraction-time mode-stability early-exit (Stage 7, open):** within the queued candidates, stop once
  the modal gross-minutes is stable (e.g. unchanged over the last ~5 schools) — LA elementary might resolve
  in ~8 of 12. Blocked on Stage 7's per-school extract→aggregate; the 95/±5 number stands only as the
  conservative upper bound this policy replaced.

### Grade-band classification — recognized partition shapes (fallback reference)

When a school's NCES `ccd_sch_029` `LEVEL` is clean (Elementary/Middle/High), that drives the band directly.
For the cases `LEVEL` leaves unresolved (ambiguous `Other`/`Secondary`/`Not reported`/blank, or
inconsistencies between the LEA-level grade span and the school-level levels), Stage 1's
`recursive_band_groups()` partitions a district's distinct grade spans into bands. This table is the set of
**recognized clean partition shapes** it was profiled/validated against (hand-built, then checked against the
full 2024-25 NCES corpus — see `STAGE1_QUEUE_DESIGN_2026-06.md` §2c for the algorithm). `PK`/`K` lead
elementary; grade `13` (an extra-year HS code) rides with high.

Three-band (elementary · middle · high):

| elementary | middle | high |
| ---------- | ------ | ------------- |
| PK\|K\|1-5 | 6-8 | 9-11\|12\|13 |
| PK\|K\|1-4 | 5-8 | 9-11\|12\|13 |
| PK\|K\|1-4 | 5-7 | 8-11\|12\|13 |
| PK\|K\|1-6 | 7-9 | 10-11\|12\|13 |
| PK\|K\|1-6 | 7-8 | 9-11\|12\|13 |

Elementary+middle merged · high:

| elementary + middle | high |
| ------------------- | ------------- |
| PK\|K\|1-8 | 9-11\|12\|13 |
| PK\|K\|1-7 | 8-11\|12\|13 |
| PK\|K\|1-9 | 10-11\|12\|13 |

Elementary · middle+high merged:

| elementary | middle + high |
| ---------- | ------------- |
| PK\|K\|1-5 | 6-12\|13 |
| PK\|K\|1-6 | 7-12\|13 |

Single combined (all three in one school):

| elementary + middle + high |
| -------------------------- |
| PK\|K\|1-10\|11\|12\|13 |

Four-band (lower elementary · upper elementary/intermediate · middle · high) — both elementary
segments map to the **elementary** band (the Southern Lehigh shape, #498):

| lower elementary | upper elementary / intermediate | middle | high |
| ---------------- | ------------------------------- | ------ | ------------- |
| PK\|K\|1-3 | 4-6 | 7-8 | 9-11\|12\|13 |
| PK\|K\|1-3 | 4-5 | 6-8 | 9-11\|12\|13 |
| PK\|K\|1-2 | 3-6 | 7-8 | 9-11\|12\|13 |

A 5-6 tier is NOT upper elementary — it maps to **middle** (RULED 2026-07-15, below), so a
K-4 · 5-6 · 7-8 · 9-12 district is four schools over three bands with TWO middle segments:

| elementary | middle (two segments) | high |
| ---------- | --------------------- | ------------- |
| PK\|K\|1-4 | 5-6 · 7-8 | 9-11\|12\|13 |

Five-band (… · lower high · upper high) — both high segments map to the **high** band:

| lower elementary | upper elem / intermediate | middle | lower high | upper high |
| ---------------- | ------------------------- | ------ | ---------- | ---------- |
| PK\|K\|1-3 | 4-6 | 7-8 | 9-10 | 11-12\|13 |
| PK\|K\|1-4 | 5-6 | 7-8 | 9 *(freshman campus)* | 10-12\|13 |

**The #498 LEVEL carve-out (DECIDED 2026-07-15):** NCES `LEVEL` stays the primary band signal (the
2026-06-22 anti-dilution decision), with exactly ONE corpus-profiled override: `LEVEL="Middle"` on an
**intermediate span (starts ≤ grade 4 AND tops ≤ grade 6)** classifies as **elementary** ("upper
elementary" — the Liberati class, ~330 schools / 0.4% of the 2024-25 corpus). Measured against the
full corpus this is the *only* hard LEVEL-vs-span disagreement class that exists (the reverse edge —
`Elementary` starting ≥5 — is zero), and NCES's `Middle` tag on 5-6 schools *agrees* with this
standard, so 05-06 is deliberately NOT overridden. Every override application is surfaced as a
gate@8 note, never silent (`effective_level_band`, `common/school_sampling.py`). **Boundary orphans
RULED (Ian, 2026-07-15): 5-5, 6-6, and 5-6 are all MIDDLE schools**, unconditionally (Hammarskjold
Upper Elementary NJ — LEVEL=Middle 05-06 — is the pinned specimen). Consequence for the span rules:
**a span starting at grade 5+ is middle-family and never counts elementary** (`bands_for_rescue`
elementary now requires starting ≤ grade 4; `recursive_band_groups`' elementary prefix likewise) —
corpus-measured effect: 129 schools across 123 districts lose a spurious elementary membership
(05-08 Middles, 05-12 secondaries leaked in by the old start-at-5 rule); nothing else moves.

*(Migrated 2026-06-27 from `docs/scratch-paper/Recognized Grade Bands for Fallback Scenarios.md`;
four/five-band shapes + the #498 carve-out added 2026-07-15.)*

---

## Data Quality & Filtering

### Validation Rules

To ensure LCT calculations are meaningful and defensible for policy discussions, we apply strict quality filters:

**Invalid District Criteria** (excluded from analysis):
1. **Zero enrollment**: Administrative units, closed schools
2. **Zero instructional staff**: Reporting errors, specialized facilities
3. **Impossible LCT**: Exceeds available daily time (>600 minutes)
4. **Extreme ratios**: Student-teacher ratios >100:1 or <1:1 (likely data errors)

**Implementation**:
```python
def is_valid_district(enrollment, staff, lct_minutes, instructional_minutes):
    return (
        enrollment > 0 and
        staff > 0 and
        0 < lct_minutes <= (instructional_minutes * 1.5) and  # Allow some buffer
        1 <= (enrollment / staff) <= 100  # Reasonable ratio bounds
    )
```

**Typical Results**:
- Input districts: ~19,600
- Valid after filtering: ~17,300 (88%)
- Filtered out: ~2,300 (12%)
  - Zero enrollment: ~800 (administrative units)
  - Zero staff: ~600 (reporting errors)
  - Invalid LCT: ~500 (calculation errors)
  - Extreme ratios: ~400 (data quality issues)

**Transparency**:
- Validation reports document all filtering decisions
- Filtered districts saved separately for audit
- Summary statistics show before/after counts
- Rationale documented in code and outputs

**File Outputs**:
- `..._with_lct_valid.csv`: Clean, publication-ready data
- `..._with_lct_invalid.csv`: Filtered records for review
- `..._validation_report.txt`: Detailed filtering statistics

This filtering ensures that policy discussions rest on solid, defensible data rather than including obvious errors that could undermine credibility.

---

## Appendix A: Calculation Code

Reference implementation: `src/python/calculators/lct_calculator.py`

```python
def calculate_lct(enrollment: int, 
                  instructional_staff: float,
                  daily_minutes: int) -> float:
    """
    Calculate Learning Connection Time
    
    Args:
        enrollment: Total student count
        instructional_staff: FTE instructional staff
        daily_minutes: Statutory instructional minutes per day
        
    Returns:
        LCT in minutes per student per day
    """
    if enrollment == 0:
        raise ValueError("Enrollment cannot be zero")
    
    total_minutes = daily_minutes * instructional_staff
    lct = total_minutes / enrollment
    
    return round(lct, 2)
```

---

## Appendix B: State Instructional Time Requirements

See `config/state-requirements.yaml` for complete list.

Quick reference:
- **Highest**: Texas (420 min/day)
- **Lowest**: Utah K-6 (240 min/day)
- **Most common**: 300-330 min/day
- **Grade variations**: 28 states have different requirements by grade level

---

**Document Purpose**: Living methodology guide  
**Audience**: Analysts, researchers, policy makers, educators  
**Maintenance**: Update with each phase evolution and data source addition
