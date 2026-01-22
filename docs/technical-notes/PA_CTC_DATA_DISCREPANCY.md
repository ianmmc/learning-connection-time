# Pennsylvania Career and Technical Center (CTC) Data Discrepancy

**Date**: January 19, 2026
**Investigator**: Claude Code
**Status**: Documented - Mitigation Required

---

## Executive Summary

Pennsylvania shows a 214% discrepancy in mean district-level LCT between federal NCES CCD data (114.70 min) and state PDE data (36.48 min). Investigation reveals this is **not a systematic measurement difference** but rather **extreme outliers** in Career and Technical Centers (CTCs) within NCES data.

**Key Finding**: The median LCT values are nearly identical (28.06 vs 27.53 min), confirming that the vast majority of PA districts have consistent data. The mean discrepancy is driven by 10-15 CTCs with impossible NCES LCT values ranging from 1,620 to 5,428 minutes.

---

## Data Summary

### Aggregate Statistics (768 districts compared)

| Metric | NCES CCD | PDE (State) | Difference |
|--------|----------|-------------|------------|
| **Total Teachers** | 129,477 | 131,311 | -1,834 (-1.4%) |
| **Total Enrollment** | 1,681,947 | 1,741,705 | -59,758 (-3.4%) |
| **Mean District LCT** | 114.70 min | 36.48 min | +78.22 min (+214%) |
| **Median District LCT** | **28.06 min** | **27.53 min** | **+0.53 min (+1.9%)** |
| **Max District LCT** | 5,428.80 min | 2,295.00 min | +3,133.80 min |

### Top 10 Outlier Districts (All CTCs)

| District | NCES LCT | PDE LCT | Difference |
|----------|----------|---------|------------|
| Warren County Area Vocational-Technical | 5,428.80 | 13.19 | 5,415.61 |
| Mifflin County Academy of Science and Tech | 5,400.00 | 12.95 | 5,387.05 |
| Susquehanna County Career and Technology | 5,400.00 | 12.99 | 5,387.01 |
| Central Westmoreland Career and Technology | 2,880.00 | 10.93 | 2,869.07 |
| A W Beattie Career Center | 2,448.00 | 12.38 | 2,435.62 |
| Erie County Technical School | 2,400.00 | 9.75 | 2,390.25 |
| Venango Technology Center | 2,040.00 | 9.44 | 2,030.56 |
| Steel Center for Career and Technical Ed | 1,980.00 | 8.43 | 1,971.57 |
| Mon Valley Career and Technology Center | 1,800.00 | 9.54 | 1,790.46 |
| Western Montgomery Career and Technology | 1,620.00 | 14.55 | 1,605.45 |

---

## Root Cause Analysis

### Hypothesis

Career and Technical Centers serve students from multiple school districts on a **part-time basis** (typically half-day programs). NCES appears to count:
- **Full FTE teachers** assigned to the CTC
- **Only students physically present** at the CTC at time of reporting

While PDE captures:
- **Teachers FTE** (similar to NCES)
- **Actual student FTE** based on instructional hours/days across all sending districts

### Evidence Supporting Hypothesis

1. **All extreme outliers are CTCs**: 100% of districts with LCT > 1,000 minutes are career and technical centers
2. **PDE values are reasonable**: CTC LCT values in PDE data (9-15 minutes) align with typical part-time CTC service models
3. **NCES values are impossible**: 5,428 minutes = 90+ hours per student per day (only 6-7 hours exist in a school day)
4. **Pattern consistency**: All PA CTCs show the same directional error (NCES >> PDE), suggesting systematic reporting difference

### NCES Reporting Known Issues

Per Gemini consultation:
- NCES CCD relies on state-reported data with varying interpretations
- States may report CTC enrollment differently:
  - Some count only students physically at CTC on survey day
  - Some count full FTE enrollment across all sending districts
- Teacher counts are typically more consistent (full FTE assigned to CTC)
- This creates artificially inflated teacher-to-student ratios in NCES data

---

## Impact Assessment

### On LCT Calculations

- **State-level aggregate LCT**: Minimal impact if using enrollment-weighted averages
- **Mean district LCT**: Severely inflated due to CTC outliers
- **Median district LCT**: No material impact (robust to outliers)
- **District comparisons**: CTCs will appear as extreme outliers and should be flagged

### On Analysis Validity

- **Within-PA traditional district comparisons**: Valid (CTCs are distinct entity type)
- **Cross-state comparisons**: Invalid if PA CTCs included but other states exclude similar entities
- **National rankings**: Severely distorted if CTCs included

---

## Recommended Mitigations

### Short-term (Immediate)

1. **Flag CTCs in database**: Add `is_ctc` boolean flag based on district name pattern matching
2. **Separate reporting**: Report CTC LCT separately from traditional districts
3. **Documentation**: Add methodology note about CTC data limitations

### Medium-term (Next Quarter)

4. **Apply correction factor**: Use PDE enrollment with NCES teacher data for PA CTCs
   - Formula: `LCT_corrected = (360 × NCES_teachers) / PDE_enrollment`
   - This assumes PDE enrollment is more accurate while preserving NCES teacher data
5. **Validate with PA DOE**: Confirm reporting methodology with Pennsylvania Department of Education
6. **Extend to other states**: Identify and flag CTCs/vocational centers in all states

### Long-term (Future Research)

7. **Standardized FTE enrollment**: Advocate for NCES to require FTE enrollment reporting for shared-service entities
8. **Proportional allocation**: Develop methodology to allocate CTC resources across sending districts
9. **Alternative metrics**: Consider CTC-specific metrics based on instructional hours rather than enrollment headcount

---

## Comparison Script Status

### What's Working

- ✅ Script correctly loads and merges NCES and PDE data
- ✅ LCT calculations are mathematically correct
- ✅ District matching via NCES IDs is accurate
- ✅ Aggregation to state level is functioning as designed

### What's Not Working

- ❌ Mean aggregation is distorted by CTC outliers (this is a **data issue**, not a code issue)
- ⚠️ No filtering or flagging of CTCs in current implementation
- ⚠️ No documentation of CTC limitation in output files

### Code Changes Needed

```python
# In compare_sea_vs_federal_lct.py, add CTC detection:

def is_career_technical_center(district_name: str) -> bool:
    """Detect if district is a career/technical center based on name."""
    ctc_keywords = [
        'career', 'technical', 'vocational', 'tech center',
        'technology center', 'ctc', 'avts'
    ]
    name_lower = district_name.lower()
    return any(keyword in name_lower for keyword in ctc_keywords)

# Then add separate reporting:
# - All districts (current behavior)
# - Traditional districts only (exclude CTCs)
# - CTCs only (separate analysis)
```

---

## Database Schema Updates

### Proposed `districts` table additions:

```sql
ALTER TABLE districts ADD COLUMN is_career_technical_center BOOLEAN DEFAULT FALSE;
ALTER TABLE districts ADD COLUMN entity_type VARCHAR(50);
-- Values: 'traditional_district', 'charter_school', 'career_technical_center',
--         'special_education', 'alternative', 'virtual'

-- Update PA CTCs
UPDATE districts
SET is_career_technical_center = TRUE,
    entity_type = 'career_technical_center'
WHERE state = 'PA'
  AND (name ILIKE '%career%'
       OR name ILIKE '%technical%'
       OR name ILIKE '%vocational%');
```

---

## Validation Queries

### Check PA CTC flagging accuracy:

```sql
-- Count CTCs in PA
SELECT COUNT(*) as ctc_count
FROM districts
WHERE state = 'PA'
  AND (name ILIKE '%career%'
       OR name ILIKE '%technical%'
       OR name ILIKE '%vocational%');

-- List all PA CTCs with LCT data
SELECT
    d.name,
    sc.teachers_total,
    eg.enrollment_k12,
    ROUND((360.0 * sc.teachers_total / eg.enrollment_k12)::numeric, 2) as nces_lct
FROM districts d
JOIN staff_counts sc ON d.nces_id = sc.district_id
JOIN enrollment_by_grade eg ON d.nces_id = eg.district_id
WHERE d.state = 'PA'
  AND d.is_career_technical_center = TRUE
  AND sc.source_year = '2023-24'
  AND eg.source_year = '2023-24'
  AND eg.enrollment_k12 > 0
ORDER BY nces_lct DESC;
```

---

## References

- **NCES CCD Documentation**: https://nces.ed.gov/ccd/
- **PA PDE Data Portal**: https://www.education.pa.gov/DataAndReporting/
- **Gemini Consultation**: January 19, 2026 (educational data analysis context)
- **Related Issue**: See `data/enriched/lct-calculations/lct_sea_vs_federal_comparison_2023_24_*.csv`

---

## Status Updates

- **2026-01-19**: Initial investigation completed
- **Next Step**: Implement CTC flagging in database
- **Pending**: Validation with PA Department of Education
