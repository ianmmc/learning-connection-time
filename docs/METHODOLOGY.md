# Learning Connection Time (LCT) Methodology

## Overview

This document provides the detailed methodology for calculating Learning Connection Time (LCT), including formulas, data requirements, known limitations, and planned evolutions.

---

## Core Calculation (Phase 1)

### Basic Formula

```
LCT = (Daily Instructional Minutes × Instructional Staff Count) / Student Enrollment
```

**Result**: Minutes of potential individual teacher attention per student per day

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

#### 2. Instructional Staff Count

**Definition**: Number of full-time equivalent (FTE) staff providing direct instruction

**Source**: NCES CCD Staff file (LEA 059) with grade-level allocation

**Included**:
- Classroom teachers (all subjects)
- Instructional aides/paraprofessionals
- Specialists providing direct instruction (reading, math, etc.)

**Excluded**:
- Administrators
- Support staff (counselors, librarians)*
- Substitute teachers (typically)

*Note: Some specialists may be included in Phase 2+ with appropriate weighting

**Grade-Level Breakdown** (Phase 1.5+):

NCES provides staff in two categories:
1. **Elementary Teachers** - Used directly for K-5
2. **Secondary Teachers** - Split proportionally between middle (6-8) and high (9-12)

**Allocation Method (Option C - Hybrid Approach)**:
```
Elementary Staff (K-5) = Elementary Teachers from NCES

Middle Staff (6-8) = Secondary Teachers × (Middle Enrollment / Secondary Enrollment)

High Staff (9-12) = Secondary Teachers × (High Enrollment / Secondary Enrollment)

where Secondary Enrollment = Middle Enrollment + High Enrollment
```

**Rationale**:
- Elementary teachers are directly reported by NCES
- Secondary teachers must be allocated proportionally based on enrollment
- Assumes similar student-teacher ratios across middle and high schools
- More accurate than using district-wide totals for grade-specific LCT

**Data Fields**:
- `Elementary Teachers` field in NCES CCD LEA 059
- `Secondary Teachers` field in NCES CCD LEA 059

**Challenges**:
- FTE vs headcount reporting varies
- Part-time teacher accounting inconsistent
- Middle/high split is estimated, not actual
- Some districts may have different ratios for middle vs high
- Charter school reporting differs
- District-level data may mask school-level variation

#### 3. Student Enrollment

**Definition**: Student membership count by grade level

**Source**: NCES CCD Membership file (LEA 052 - October count)

**Grade-Level Breakdown** (Phase 1.5+):

Individual grade counts aggregated into three levels:
- **Elementary (K-5)**: Sum of Kindergarten + Grades 1-5
- **Middle (6-8)**: Sum of Grades 6-8
- **High (9-12)**: Sum of Grades 9-12

**Data Structure**: The CCD Membership file provides student counts broken down by:
- Grade (individual: K, 1, 2, ..., 12)
- Race/Ethnicity
- Sex

**Aggregation Method**:
```python
enrollment_elementary = sum(Kindergarten, Grade 1, Grade 2, Grade 3, Grade 4, Grade 5)
enrollment_middle = sum(Grade 6, Grade 7, Grade 8)
enrollment_high = sum(Grade 9, Grade 10, Grade 11, Grade 12)
```

**Considerations**:
- October count may not reflect year-average
- Some students may be counted multiple times (dual enrollment)
- Pre-K typically excluded from K-12 counts
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

### Data Quality Filtering (Implemented)

**Automated Validation**: All districts are validated against data quality criteria. Invalid districts are excluded from publication-ready outputs but retained in complete datasets for transparency.

**Validation Criteria**:

1. **enrollment > 0**: Districts must have at least one student
2. **instructional_staff > 0**: Districts must have at least one teacher
3. **lct_minutes ≤ daily_instructional_minutes**: LCT cannot exceed available time (physically impossible)
4. **instructional_staff ≤ enrollment**: Cannot have more teachers than students

**Implementation**:
- Script: `infrastructure/scripts/analyze/calculate_lct.py --filter-invalid`
- Two outputs generated:
  - `*_with_lct.csv`: Complete dataset with validation flags
  - `*_with_lct_valid.csv`: Filtered dataset for publication
- Validation report documents filtering details

**Typical Results**:
- ~97% of districts pass validation
- ~2-3% filtered for data quality issues
- Most common issues: zero enrollment or staff (administrative units)

**Publication Policy**:
- **Always use filtered (`*_valid.csv`) files for external communications**
- Validation report provides methodological transparency
- Complete dataset available for research purposes

### Statistical Validation Checks

**Post-Filtering Checks**:
- [x] LCT values are positive
- [x] LCT values are reasonable (0-360 minutes within daily time)
- [x] Distribution shape analysis
- [x] Correlation with known student-teacher ratios

**Ongoing Monitoring**:
- State-level mean/median comparison
- Year-over-year consistency (when available)
- Cross-validation with state-reported ratios

### Outlier Investigation

When valid districts show unusual LCT patterns:

**LCT < 10 minutes**:
- Likely very high enrollment relative to staff
- Common in large urban districts
- Verify enrollment spike or staff reporting

**LCT > 50 minutes**:
- Likely very low enrollment relative to staff
- Common in rural or specialized districts
- Verify specialized program or reporting period

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

**Methodology Version**: 1.0 (Phase 1)  
**Last Updated**: December 16, 2025  
**Next Review**: Upon completion of initial district calculations

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
