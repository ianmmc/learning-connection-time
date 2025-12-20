# Bell Schedule Sampling Methodology

## Purpose

This document defines the methodology for gathering actual bell schedule data from school districts to determine real instructional time, rather than relying solely on state statutory minimums.

## Overview

Different quality tiers are used based on district size and resources available:

| Tier | Description | Use Case | Sample Size |
|------|-------------|----------|-------------|
| **Tier 1** | Detailed manual-assisted search | Top 25 largest districts | 2-3 schools per level |
| **Tier 2** | Automated search with fallback | Districts 26-100 | 1-2 schools per level or statutory |
| **Tier 3** | State statutory only | Districts 101+ or unavailable | No sampling - use state requirements |

## Tier 1: Detailed Sampling Methodology

### Target Districts
- Top 25 largest U.S. school districts by enrollment
- Highest impact on national LCT metrics
- Worth detailed investigation

### Sampling Strategy

#### 1. District-Wide Policy Check
**First**, search for district-wide bell schedule policies:
- Check district policy manuals
- Look for board-approved schedules
- Search for district-wide instructional time requirements

If found, use this for all schools at each level.

#### 2. Stratified School Sampling
If no district-wide policy, use **stratified random sampling**:

##### Elementary Schools
- **Target sample**: 2-3 schools
- **Stratification criteria**:
  - Geographic diversity (if large district)
  - Socioeconomic diversity (Title I vs. non-Title I)
  - School size (large, medium, small)

##### Middle Schools
- **Target sample**: 2-3 schools
- **Stratification criteria**:
  - Geographic diversity
  - Socioeconomic diversity
  - 6-8 vs. 7-8 configurations

##### High Schools
- **Target sample**: 2-3 schools
- **Stratification criteria**:
  - Geographic diversity
  - Socioeconomic diversity
  - Comprehensive vs. specialized schools

#### 3. Data Extraction

For each sampled school, extract:

1. **Start and end times** (e.g., 8:00 AM - 3:30 PM)
2. **Lunch duration** (e.g., 30 minutes)
3. **Passing periods** (total time between classes)
4. **Homeroom/advisory** (if not instructional)
5. **Actual instructional blocks**

Calculate:
```
Instructional Minutes = Total Day - (Lunch + Non-Instructional Time)
```

#### 4. Aggregation

For each level (elementary, middle, high):
- Calculate mean instructional minutes across sampled schools
- Calculate standard deviation
- Document range (min-max)
- Flag if variation is > 30 minutes (indicates different schedules)

#### 5. Confidence Assignment

| Confidence Level | Criteria |
|-----------------|----------|
| **High** | District-wide policy found OR 3+ schools sampled with < 15 min variation |
| **Medium** | 2 schools sampled with < 30 min variation |
| **Low** | Single school sampled OR high variation across sample |

### Example: Los Angeles Unified School District

**District**: LAUSD (Tier 1)
**Enrollment**: ~430,000 students
**Number of schools**: ~1,000

#### Process:
1. Search for "LAUSD bell schedule policy 2023-24"
2. Check LAUSD Board policies for instructional time requirements
3. If not found, sample:
   - Elementary: 3 schools (one East LA, one Valley, one Westside)
   - Middle: 3 schools (geographic spread)
   - High: 3 schools (geographic spread + one magnet)

#### Data Collection:
```yaml
elementary:
  sample:
    - name: "Example Elementary #1"
      start: "8:00 AM"
      end: "2:30 PM"
      lunch: 30 min
      instructional: 360 min
    - name: "Example Elementary #2"
      start: "8:15 AM"
      end: "2:45 PM"
      lunch: 30 min
      instructional: 360 min
    - name: "Example Elementary #3"
      start: "8:00 AM"
      end: "2:35 PM"
      lunch: 35 min
      instructional: 360 min
  mean: 360 min
  std_dev: 0 min
  confidence: "high"
```

## Tier 2: Automated Sampling Methodology

### Target Districts
- Districts 26-100 by enrollment
- Still significant but less resource-intensive

### Strategy

1. **Automated Search**:
   - Use web search for "[District Name] bell schedule [year]"
   - Parse first 3 results
   - Look for PDF/HTML schedules

2. **Quick Extraction**:
   - Extract times using pattern matching or LLM
   - If ambiguous, flag for manual review

3. **Fallback**:
   - If no schedule found within 2 minutes of searching
   - Fall back to state statutory requirements
   - Mark confidence as "medium" or "low"

### Confidence Assignment

| Confidence Level | Criteria |
|-----------------|----------|
| **Medium** | Bell schedule found and parsed successfully |
| **Low** | Fell back to state statutory requirements |

## Tier 3: Statutory Requirements Only

### Target Districts
- Districts 101+ OR
- No web presence OR
- Data not publicly available

### Strategy
- Use state statutory requirements from `config/state-requirements.yaml`
- No web searching
- Mark confidence as "assumed"

### Confidence Assignment
- **Assumed**: Using state minimums, actual may be higher

## Data Quality Tracking

### Required Metadata

For each district, record:

| Field | Description | Example |
|-------|-------------|---------|
| `district_id` | NCES district ID | "0600001" |
| `district_name` | District name | "Los Angeles Unified" |
| `state` | State code | "CA" |
| `tier` | Quality tier used | 1, 2, or 3 |
| `fetch_date` | When data was collected | "2025-12-19" |
| `year` | School year | "2023-24" |

For each level (elementary, middle, high):

| Field | Description | Example |
|-------|-------------|---------|
| `instructional_minutes` | Average instructional time | 360 |
| `start_time` | Typical start time | "8:00 AM" |
| `end_time` | Typical end time | "2:30 PM" |
| `lunch_duration` | Lunch period | 30 |
| `schools_sampled` | List of schools sampled | ["School A", "School B"] |
| `source_urls` | Documentation URLs | ["https://..."] |
| `confidence` | Confidence level | "high", "medium", "low", "assumed" |
| `method` | How data was obtained | "district_policy", "school_sample", "state_statutory" |
| `notes` | Any additional context | "K-5 only; K uses different schedule" |

## Search Strategies

### Where to Look

#### District Websites
- `/parents` or `/families` sections
- `/academics` sections
- `/calendar` or `/schedules` pages
- Policy manuals (often PDF)

#### School Websites
- Homepage (often has bell schedule link)
- `/parents` sections
- Student handbooks (PDF)

#### Other Sources
- State department of education data portals
- Local news articles about schedule changes
- School board meeting minutes/agendas

### Search Queries

Effective search patterns:
```
"[District Name] bell schedule [year]"
"[District Name] daily schedule [year]"
"[District Name] instructional time policy"
"[School Name] bell schedule [year]"
site:[district-domain] "bell schedule"
site:[district-domain] filetype:pdf schedule
```

## Validation Rules

### Red Flags (require manual review)

1. **Extreme values**: < 200 minutes or > 500 minutes
2. **High variation**: > 60 minutes difference within same level
3. **Inconsistent data**: Start time after end time
4. **Missing lunch**: No lunch period documented
5. **Ambiguous sources**: Unclear if current year or old schedule

### Quality Checks

Before accepting data:
- ✓ Confirm year matches target year
- ✓ Times are reasonable (6 AM - 6 PM range)
- ✓ Lunch and breaks accounted for
- ✓ Source URL is accessible
- ✓ Multiple sources agree (if available)

## Assumptions and Limitations

### Explicit Assumptions

1. **Within-level homogeneity**: Schools at the same level (elementary/middle/high) within a district have similar schedules
2. **Schedule stability**: School year schedules remain constant (not early dismissal days, etc.)
3. **Instructional time definition**: All non-lunch, non-passing period time is "instructional"
4. **Sample representativeness**: Sampled schools represent district-wide patterns

### Known Limitations

1. **No accounting for**:
   - Shortened days (early dismissal schedules)
   - Teacher professional development days
   - Testing schedule changes
   - Weather-related schedule changes

2. **Variation not captured**:
   - Within-school variations (different grade schedules)
   - Special programs (gifted, special ed, ESL)
   - Block vs. traditional scheduling differences

3. **Data staleness**:
   - Schedules change year to year
   - Data may be outdated if not refreshed

### Mitigation Strategies

- Document all assumptions
- Note confidence levels
- Provide ranges when variation exists
- Regular data refresh (annually)
- Cross-validate with multiple sources where possible

## Reporting

### Individual District Reports

For each district, generate:
```
District: Los Angeles Unified (CA)
Enrollment: 430,000
Tier: 1 (Detailed)
Fetch Date: 2025-12-19

Elementary (K-5):
  Instructional Minutes: 360 (±0)
  Schools Sampled: 3
  Confidence: High
  Method: School website sample
  Sources: [URLs]

Middle (6-8):
  Instructional Minutes: 375 (±5)
  Schools Sampled: 3
  Confidence: High
  Method: School website sample
  Sources: [URLs]

High (9-12):
  Instructional Minutes: 390 (±10)
  Schools Sampled: 3
  Confidence: High
  Method: School website sample
  Sources: [URLs]
```

### Aggregate Summary

Across all districts:
- % using Tier 1, 2, 3 methodology
- Distribution of confidence levels
- Average instructional time by state
- Comparison: actual vs. statutory requirements

## References

### Related Documents
- `config/state-requirements.yaml` - State statutory minimums
- `docs/METHODOLOGY.md` - Overall LCT methodology
- `infrastructure/scripts/enrich/fetch_bell_schedules.py` - Implementation

### External Resources
- NCES Common Core of Data
- State education agency websites
- District policy databases

---

**Version**: 1.0
**Last Updated**: 2025-12-19
**Status**: Active methodology for bell schedule enrichment
