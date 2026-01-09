# SPED Segmentation Implementation

**Date:** January 3, 2026
**Status:** Implemented (v3 with self-contained focus)
**Based on:** `docs/SPED_SEGMENTATION_HANDOFF_20260102T071500Z.md`

## Overview

This document describes the implementation of SPED (Special Education) segmentation for LCT (Learning Connection Time) calculations. The segmentation separates self-contained SPED students from the general education population to enable accurate per-segment LCT calculations.

## Key Concept: Self-Contained vs Mainstreamed

**Self-Contained SPED Students** (~6.7% of all SPED):
- Separate Class
- Separate School
- Inside regular class less than 40% of the day

These students receive instruction primarily from SPED teachers and are the appropriate denominator for SPED teacher-to-student ratios.

**Mainstreamed SPED Students** (~93.3% of all SPED):
- Inside regular class 80%+ of the day
- Inside regular class 40-79% of the day

These students receive instruction primarily from GenEd teachers and are included in the GenEd population for LCT calculations.

## Key Findings

The self-contained SPED approach reveals distinct instructional time allocations:

| Metric | Value | Description |
|--------|-------|-------------|
| **LCT Teachers (overall)** | 27.9 min | Combined SPED + GenEd teachers / Total enrollment |
| **LCT Core SPED** | 185.5 min | SPED teachers / Self-contained SPED |
| **LCT Teachers GenEd** | 27.2 min | GenEd teachers / GenEd enrollment |
| **LCT Instructional SPED** | 265.8 min | (SPED teachers + paras) / Self-contained SPED |

Key insights:
- **Core SPED** (185.5 min) shows that SPED teachers have intensive individual attention capacity per self-contained student
- **Teachers GenEd** (27.2 min) is close to the overall LCT, reflecting that most students are in GenEd settings
- **Instructional SPED** (265.8 min) shows even higher attention when including paraprofessionals
- **Audit Passes**: The weighted average of core_sped and teachers_gened equals the overall teachers_only LCT

## Three SPED Scopes (January 2026)

### 1. `core_sped` - SPED Teachers / Self-Contained Students
- **Formula:** `(Minutes × SPED Teachers) / Self-Contained SPED Enrollment`
- **Purpose:** Primary SPED attention metric
- **Usage:** Shows potential individual attention per self-contained student
- **Mean LCT:** 185.5 minutes

### 2. `teachers_gened` - GenEd Teachers / GenEd Students
- **Formula:** `(Minutes × GenEd Teachers) / GenEd Enrollment`
- **Purpose:** Primary comparison metric for general education
- **Usage:** GenEd enrollment includes mainstreamed SPED students
- **Mean LCT:** 27.2 minutes

### 3. `instructional_sped` - SPED Teachers + Paras / Self-Contained Students
- **Formula:** `(Minutes × (SPED Teachers + SPED Paras)) / Self-Contained SPED Enrollment`
- **Purpose:** Fuller picture of SPED instructional support
- **Usage:** Includes paraprofessionals who provide significant support
- **Mean LCT:** 265.8 minutes

## Methodology

### Data Sources (2017-18 Pre-COVID Baseline)

1. **IDEA 618 Personnel** (State-level)
   - File: `bpersonnel2017-18.csv`
   - Provides: SPED teacher FTE by state (Ages 6-21)
   - Provides: SPED paraprofessional FTE by state (Ages 6-21)

2. **IDEA 618 Child Count & Educational Environments** (State-level)
   - File: `bchildcountandedenvironments2017-18.csv`
   - Provides: SPED student count by educational environment (ages 6-21) by state
   - Categorizes students as self-contained or mainstreamed

3. **CRDC 2017-18 Enrollment** (LEA-level)
   - File: `Enrollment.csv`
   - Provides: LEA-level total SPED student counts (SCH_ENR_IDEA_M/F)
   - Note: Does not include educational environment breakdown

4. **CCD 2017-18 LEA Membership** (LEA-level)
   - File: `ccd_lea_052_1718_l_1a_083118.csv`
   - Provides: LEA-level total enrollment

### Calculated Ratios

**Ratio 4a: State SPED Teacher-to-Self-Contained-Student Ratio**
```
Ratio = State SPED Teachers / State Self-Contained SPED Students
```
- Example CA: 20,361 teachers / 135,510 self-contained students = 0.1503
- Example TX: 29,747 teachers / 67,079 self-contained students = 0.4435

**Ratio 4a-Instructional: State SPED Instructional-to-Self-Contained-Student Ratio**
```
Ratio = (State SPED Teachers + State SPED Paras) / State Self-Contained SPED Students
```
- Example CA: 78,647 instructional / 135,510 self-contained = 0.5804

**Ratio 4b: LEA SPED Proportion**
```
Ratio = LEA Total SPED Students (CRDC) / LEA Total Students (CCD)
```
- Average proportion: 15.89%
- Used LEA-specific ratio when available (74% of districts)
- Falls back to state average when LEA-specific unavailable (26% of districts)

**Ratio 4c: State Self-Contained Proportion**
```
Ratio = State Self-Contained SPED / State All SPED
```
- National average: 6.7%
- Range: 6.6% (FL, IL) to 9.9% (CA)

### Two-Step Estimation Method

For each current-year (2023-24) district:

1. **Estimated All SPED Enrollment** = Total Enrollment × LEA SPED Proportion
2. **Estimated Self-Contained SPED** = All SPED × State Self-Contained Proportion
3. **Estimated GenEd Enrollment** = Total - Self-Contained (includes mainstreamed SPED)
4. **Estimated SPED Teachers** = Self-Contained × State Teacher Ratio
5. **Estimated SPED Instructional** = Self-Contained × State Instructional Ratio
6. **Estimated GenEd Teachers** = Total Teachers - SPED Teachers

**LCT Calculations:**
- **LCT Core SPED** = (Minutes × SPED Teachers) / Self-Contained SPED
- **LCT Teachers GenEd** = (Minutes × GenEd Teachers) / GenEd Enrollment
- **LCT Instructional SPED** = (Minutes × SPED Instructional) / Self-Contained SPED

## Database Tables

### sped_state_baseline
State-level SPED baseline data from IDEA 618 (56 states/territories)

Key columns:
- `sped_teachers_total`: SPED teacher FTE (Ages 6-21)
- `sped_paras_total`: SPED paraprofessional FTE (Ages 6-21)
- `sped_instructional_total`: Teachers + Paras
- `sped_students_ages_6_21`: All school-age SPED students
- `sped_students_self_contained`: Self-contained students only
- `sped_students_mainstreamed`: Mainstreamed students (80%+ and 40-79%)
- `ratio_self_contained_proportion`: Self-Contained / All SPED
- `ratio_sped_teachers_per_student`: Teachers / Self-Contained (for core_sped)
- `ratio_sped_instructional_per_student`: Instructional / Self-Contained (for instructional_sped)

### sped_lea_baseline
LEA-level SPED baseline data from CRDC/CCD (18,606 LEAs)

Key columns:
- `crdc_sped_enrollment_total`: Total SPED students (from CRDC, no environment breakdown)
- `ccd_total_enrollment`: Total students (from CCD)
- `ratio_sped_proportion`: LEA SPED proportion (used for first step of estimation)

### sped_estimates
Current-year SPED estimates (16,459 districts for 2023-24)

Key columns:
- `estimated_sped_enrollment`: All estimated SPED students
- `estimated_self_contained_sped`: Self-contained SPED only (used for LCT calculations)
- `estimated_gened_enrollment`: GenEd students (includes mainstreamed SPED)
- `estimated_sped_teachers`: Estimated SPED teachers
- `estimated_sped_instructional`: Estimated SPED teachers + paras
- `estimated_gened_teachers`: Estimated GenEd teachers
- `ratio_state_self_contained_proportion`: State self-contained proportion used
- `ratio_state_sped_teachers_per_student`: Teacher ratio used
- `ratio_state_sped_instructional_per_student`: Instructional ratio used
- `confidence`: high/medium/low
- `estimation_method`: "self_contained_ratio"

## Audit Validation

The self-contained approach passes the weighted average audit:

**Check 1:** Self-Contained + GenEd = Total Enrollment ✓
- Example: Los Angeles: 4,419 + 415,510 = 419,929 ✓

**Check 2:** SPED Teachers + GenEd Teachers ≈ Total Teachers ✓
- Example: Los Angeles: 664.0 + 21,066.3 = 21,730.3 (total: 21,730.2) ✓

**Check 3:** Weighted Average LCT ≈ Overall LCT ✓
```
Weighted Avg = (LCT_core_sped × Self-Contained + LCT_gened × GenEd) / Total
```
- Example: Los Angeles: (54.09 × 4,419 + 18.25 × 415,510) / 419,929 = 18.63 ✓
- Overall LCT Teachers: 18.63 ✓
- **Difference: 0.00** ✓

This validates that the segmentation correctly partitions both enrollment and teachers.

## Output Files

LCT variants now include three SPED scopes:
- `core_sped`: LCT for SPED teachers / self-contained students
- `teachers_gened`: LCT for GenEd teachers / GenEd students (includes mainstreamed SPED)
- `instructional_sped`: LCT for SPED (teachers+paras) / self-contained students

Files location: `data/enriched/lct-calculations/`

## Quality Considerations

### Strengths
- Uses pre-COVID (2017-18) baseline to avoid pandemic distortions
- LEA-specific SPED proportions used when available (74%)
- Self-contained focus provides accurate teacher-to-student relationship
- **Audit passes perfectly** (weighted average = overall LCT)
- Includes paraprofessionals for fuller SPED picture

### Limitations
1. **Two-step ratio**: Uses state-level self-contained proportion applied to LEA SPED estimate
2. **State-level variation**: Self-contained proportion varies by state (6.6% to 9.9%)
3. **Estimation uncertainty**: LEA self-contained count is estimated, not directly measured
4. **Para allocation**: State-level para ratios may not reflect LEA-level variation

### Flagged Issues
- 6 districts with negative GenEd teacher estimates (low confidence)
- ~940 districts skipped due to missing state ratios (territories, etc.)

## Scripts

- `infrastructure/database/migrations/import_sped_baseline.py` - Import 2017-18 baseline data with educational environments
- `infrastructure/database/migrations/apply_sped_estimates.py` - Apply two-step ratio to current year
- `infrastructure/scripts/analyze/calculate_lct_variants.py` - Calculate LCT using self-contained enrollment

## Changelog

- **January 3, 2026 (v3)**: Self-contained SPED focus
  - Changed SPED denominator from "all SPED" to "self-contained SPED only"
  - GenEd enrollment now includes mainstreamed SPED students
  - Added educational environment parsing from IDEA 618
  - Added `sped_students_self_contained` and `sped_students_mainstreamed` columns
  - Added `ratio_self_contained_proportion` for two-step estimation
  - Added `estimated_self_contained_sped` column to sped_estimates
  - **Audit now passes with difference ≈ 0**

- **January 3, 2026 (v2)**: Added paraprofessionals to SPED segmentation
  - Renamed `teachers_sped` → `core_sped`
  - Added `instructional_sped` (teachers + paras)
  - Updated import script to capture para data from IDEA 618

- **January 2, 2026 (v1)**: Initial SPED segmentation
  - Basic SPED/GenEd split using all SPED students
