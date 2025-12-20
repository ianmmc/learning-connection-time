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

**Source**: NCES CCD Staff file or state equivalent

**Included**:
- Classroom teachers (all subjects)
- Instructional aides/paraprofessionals
- Specialists providing direct instruction (reading, math, etc.)

**Excluded**:
- Administrators
- Support staff (counselors, librarians)*
- Substitute teachers (typically)

*Note: Some specialists may be included in Phase 2+ with appropriate weighting

**Data Field**: Typically `TEACHERS` field in NCES CCD

**Challenges**:
- FTE vs headcount reporting varies
- Part-time teacher accounting inconsistent
- Charter school reporting differs
- District-level data may mask school-level variation

#### 3. Student Enrollment

**Definition**: Total student membership count

**Source**: NCES CCD Membership file (October count)

**Data Field**: `MEMBER` (total membership)

**Considerations**:
- October count may not reflect year-average
- Some students may be counted multiple times (dual enrollment)
- Pre-K typically excluded from K-12 counts

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
