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

**Definition**: The actual or statutory instructional time per day

**Sources**:
1. **Primary (Phase 1.5+)**: Actual bell schedules from district/school websites
2. **Fallback (Phase 1)**: State statutory minimum requirements

**Variations**:
- Range: 240-420 minutes across U.S. states (statutory)
- Actual schedules often exceed statutory minimums
- Grade-level differences in many states
- District-specific policies may vary

**Implementation Tiers**:

**Tier 1 - Actual Bell Schedules (Preferred)**:
- Web search for district-wide bell schedule policies
- Sample 2-3 schools per level (elementary, middle, high)
- Extract actual instructional minutes from schedules
- Document sources and confidence levels
- Used for top 25-100 largest districts

**Tier 2 - Automated Search with Fallback**:
- Automated web search for bell schedules
- Quick extraction if found
- Fall back to state requirements if not found
- Used for districts 26-100

**Tier 3 - State Statutory Requirements Only**:
- Use state statutory minimums from `config/state-requirements.yaml`
- Applied based on district state and grade levels
- Grade-weighted averages for districts with multiple levels
- Used for districts 101+ or when schedules unavailable

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

See `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md` for complete methodology.

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

**Methodology Version**: 2.0 (Pre-K Exclusion + Level Variants)
**Last Updated**: December 27, 2025
**Key Changes in v2.0**:
- All scopes now use K-12 enrollment (Pre-K excluded)
- All scopes exclude Pre-K teachers
- Added teacher-level variants (Elementary, Secondary)
- Ungraded teachers excluded from LCT-Teachers, included in broader scopes
- Added `level_lct_notes` for QA transparency
**Next Review**: Upon integration of state-level staffing data

---

## Data Source Precedence

### Multi-Source Integration

LCT calculations may draw from multiple data sources. When sources conflict, apply these precedence rules:

**Rule 1 - Recency Wins**: For the same data type (e.g., staffing), prefer more recent data regardless of source.
- Example: State 2024-25 data > NCES 2023-24 data

**Rule 2 - NCES as Foundation**: When sources have the same year, prefer NCES CCD as the foundational source.
- Example: NCES 2023-24 > State 2023-24 (same year)

**Rule 3 - No Hybrids per District**: All staff data for a given district must come from a single source.
- Do not mix NCES teachers with state paraprofessionals
- If state data is incomplete, use NCES entirely for that district

**Rule 4 - Complete Scope Coverage**: A state source must provide all categories needed for all 5 LCT scopes to be used.
- Required: teachers (total, elem, sec, kinder), coordinators, paraprofessionals, counselors, psychologists, student support, administrators

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

**Data Collection Tiers**:

**Tier 1 - Detailed Manual Enrichment** (Target: Top 25-50 districts nationally):
- Comprehensive web search for district policies
- Sample 2-3 representative schools per grade level
- Extract specific start/end times, lunch duration, passing periods
- Calculate net instructional minutes
- Document all sources with URLs
- Confidence: `high` or `medium`

**Tier 2 - Automated Search with Estimation** (Target: Districts 51-153):
- Automated web search for bell schedules
- Use district-wide policies when available
- Apply reasonable estimates for lunch/passing periods based on state norms
- Fall back to state statutory requirements if unavailable
- Confidence: `medium` or `low`

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
    "instructional_minutes": 345,
    "start_time": "8:45 AM",
    "end_time": "3:30 PM",
    "lunch_duration": 40,
    "recess_duration": 20,
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
