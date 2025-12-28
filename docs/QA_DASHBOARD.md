# LCT Calculation QA Dashboard

**Last Updated**: December 28, 2025

This document describes the automated Quality Assurance (QA) dashboard for Learning Connection Time calculations.

---

## Overview

The QA dashboard provides real-time validation of LCT calculations with:

- **Data quality metrics** (pass rates, invalid calculations)
- **Hierarchy validation** (ensures LCT values follow expected patterns)
- **Outlier detection** (flags extreme values for review)
- **State coverage analysis** (tracks data availability)
- **Automated reporting** (JSON exports for transparency)

Generated automatically by `calculate_lct_variants.py` as of December 28, 2025.

---

## Dashboard Output

### Console Display

```
============================================================
QA DASHBOARD
============================================================
Status: PASS
Pass Rate: 99.46%

Hierarchy Checks:
  ✓ Secondary < Overall Teachers
  ✓ Teachers < Elementary
  ✓ Teachers < Core
  ✓ Core < Instructional
  ✓ Instructional < Support
  ✓ Support < All

Outliers Detected: 20
  - 5 very low LCT warnings
  - 15 very high LCT (informational)

State Coverage: 48 states/territories
Districts Processed: 14,314
============================================================
```

### JSON Report

Saved to `data/enriched/lct-calculations/lct_qa_report_<year>_<timestamp>.json`

**Structure**:
```json
{
  "metadata": {
    "timestamp": "20251228T014457Z",
    "generated_at": "2025-12-28T01:45:10Z",
    "year": "2023-24",
    "version": "2.0"
  },
  "data_quality": {
    "total_calculations": 97422,
    "valid_calculations": 96894,
    "invalid_calculations": 528,
    "pass_rate": 99.46,
    "districts_with_qa_notes": 1919
  },
  "scope_summary": {
    "all": {
      "districts": 14250,
      "mean": 59.77,
      "median": 54.47,
      "min": 0.35,
      "max": 360.0
    },
    "teachers_only": {
      "districts": 14286,
      "mean": 27.91,
      "median": 25.18,
      "min": 0.10,
      "max": 350.0
    }
    // ... other scopes
  },
  "hierarchy_validation": {
    "Teachers < Core": {
      "passed": true,
      "lower": {"scope": "teachers_only", "mean": 27.91},
      "higher": {"scope": "teachers_core", "mean": 29.48}
    }
    // ... other checks
  },
  "state_coverage": {
    "states_with_data": 48,
    "states": ["AL", "AK", "AZ", ...]
  },
  "outliers": [
    {
      "district_id": "3900528",
      "district_name": "Findlay Digital Academy",
      "scope": "teachers_only",
      "issue": "Very low LCT: 0.4 min",
      "severity": "warning"
    }
    // ... more outliers
  ],
  "overall_status": "PASS"
}
```

---

## QA Validation Rules

### 1. Data Quality Checks

**Valid Calculation Criteria**:
- Enrollment > 0
- Staff count > 0
- LCT value > 0 and ≤ daily instructional minutes
- No null values in required fields

**Pass Rate Threshold**: ≥95% of calculations must be valid

**Current Performance** (2023-24 data):
- **Pass rate**: 99.46%
- **Invalid**: 528 of 97,422 calculations (0.54%)

**Common Reasons for Invalid Calculations**:
- Administrative districts (no students)
- Special programs (highly atypical ratios)
- Data collection artifacts (zeros, nulls)

### 2. Hierarchy Validation

LCT values should follow expected hierarchy based on staff scope:

```
Secondary Teachers < Overall Teachers < Elementary Teachers
           ↓
    Overall Teachers < Teachers + Ungraded (Core)
           ↓
        Teachers Core < Instructional Staff
           ↓
      Instructional < Instructional + Support
           ↓
   Support Staff < All Staff
```

**Validation Method**: Compare mean LCT across scopes

**Example**:
- Teachers-Only mean: 27.9 min ✓
- Teachers-Core mean: 29.5 min ✓ (should be higher)
- Instructional mean: 38.4 min ✓ (should be higher)

**All checks passing** (December 2025 calculation)

### 3. Outlier Detection

**Very Low LCT** (warnings):
- LCT < 5 minutes per student per day
- Often virtual/online schools or special programs
- Flagged for manual review

**Very High LCT** (informational):
- LCT > 200 minutes per student per day
- Often special education centers, IUs, or small programs
- Not necessarily errors, just atypical

**Severity Levels**:
- `warning`: Needs investigation (very low LCT)
- `info`: Atypical but may be legitimate (very high LCT)

**Current Outliers** (2023-24 data):
- **5 very low**: 0.3-4.6 minutes (virtual schools, charter programs)
- **15 very high**: 200-352 minutes (IUs, special ed centers, small programs)

### 4. State Coverage

**Metrics**:
- Number of states with valid LCT calculations
- Enrollment coverage by state
- Enrichment status by state

**Current Coverage** (2023-24):
- **48 states/territories** with LCT data
- Missing: Outlying territories with limited reporting

---

## Using the QA Dashboard

### Generate Report

```bash
# Standard calculation (auto-generates dashboard)
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24

# View JSON report
cat data/enriched/lct-calculations/lct_qa_report_2023_24_<timestamp>.json | jq
```

### Interpret Results

#### PASS Status

✅ **Good to proceed**:
- Pass rate ≥95%
- All hierarchy checks passing
- Outliers documented and reviewed
- Adequate state coverage

#### Review Needed

⚠️ **Investigate before publishing**:
- Pass rate <95%
- Any hierarchy check failures
- Unexpected outliers
- Missing data from major states

### Investigating Outliers

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, LCTCalculation

with session_scope() as session:
    # Look up flagged district
    district = session.query(District).filter_by(nces_id="3900528").first()
    print(f"{district.name} ({district.state})")
    print(f"Enrollment: {district.enrollment}")
    print(f"Locale: {district.locale_code}")

    # Check LCT calculations
    lcts = session.query(LCTCalculation).filter_by(
        district_id="3900528",
        year="2023-24"
    ).all()

    for lct in lcts:
        print(f"{lct.scope}: {lct.lct_value} min (staff={lct.staff_count}, enrollment={lct.enrollment})")
```

**Common Outlier Patterns**:

1. **Virtual/Online Schools**: Very low LCT due to minimal staff
   - Example: Findlay Digital Academy (0.4 min)
   - **Action**: Document in notes, may exclude from equity analysis

2. **Intermediate Units (IUs)**: Very high LCT due to specialized staffing
   - Example: Berks County IU 14 (284.6 min)
   - **Action**: Note as special-purpose entity, not typical district

3. **Charter/Alternative Schools**: Highly variable ratios
   - Example: Niner University Elementary (0.3 min)
   - **Action**: Verify data accuracy, may be startup program

---

## QA Dashboard in Workflow

### Development Workflow

```bash
# 1. Run calculation with QA
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24

# 2. Review console output
# Check: PASS status, pass rate, hierarchy checks

# 3. Review JSON report (detailed)
cat data/enriched/lct-calculations/lct_qa_report_2023_24_*.json | jq '.overall_status'

# 4. If PASS, proceed with analysis
# 5. If issues found, investigate outliers
```

### Production Workflow

```bash
# 1. Calculate with tracking
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24

# 2. Automated checks
if [ $(jq -r '.overall_status' lct_qa_report_*.json) == "PASS" ]; then
  echo "✓ QA passed, proceeding..."
else
  echo "✗ QA failed, review required"
  exit 1
fi

# 3. Archive QA report with results
cp lct_qa_report_*.json data/enriched/lct-calculations/archive/
```

---

## Customizing QA Thresholds

### Modify in `calculate_lct_variants.py`

```python
# Low LCT warning threshold (default: 5 minutes)
LOW_LCT_THRESHOLD = 5

# High LCT info threshold (default: 200 minutes)
HIGH_LCT_THRESHOLD = 200

# Pass rate threshold (default: 95%)
MIN_PASS_RATE = 0.95
```

### Add Custom Checks

Example: Flag districts with unusual staff-to-student ratios

```python
def check_ratio_outliers(df: pd.DataFrame) -> List[Dict]:
    """Flag districts with very high or low staff ratios."""
    outliers = []

    # Calculate overall ratio
    df['ratio'] = df['staff_count'] / df['enrollment']

    # Flag extremes (< 1:50 or > 1:5)
    low = df[df['ratio'] < 0.02]  # < 1:50
    high = df[df['ratio'] > 0.20]  # > 1:5

    for _, row in low.iterrows():
        outliers.append({
            'district_id': row['district_id'],
            'district_name': row['district_name'],
            'issue': f'Very low staff ratio: 1:{1/row["ratio"]:.0f}',
            'severity': 'warning'
        })

    return outliers
```

---

## QA Reports Archive

Stored in `data/enriched/lct-calculations/`:

- **Current**: `lct_qa_report_<year>_<timestamp>.json`
- **Archive**: `archive/lct_qa_report_<year>_<timestamp>.json`

### Comparing Runs

```bash
# Compare two QA reports
diff \
  <(jq -S . data/enriched/lct-calculations/archive/lct_qa_report_2023_24_20251227T120000Z.json) \
  <(jq -S . data/enriched/lct-calculations/lct_qa_report_2023_24_20251228T014457Z.json)
```

---

## Troubleshooting

### Dashboard Not Appearing

**Issue**: No console output when running calculation

**Solution**: Check that you're using the updated script:
```bash
grep "generate_qa_report" infrastructure/scripts/analyze/calculate_lct_variants.py
```

### JSON Report Missing

**Issue**: `lct_qa_report_*.json` file not created

**Solution**: Check permissions on output directory:
```bash
ls -la data/enriched/lct-calculations/
chmod 755 data/enriched/lct-calculations/
```

### Hierarchy Check Failures

**Issue**: Hierarchy check shows `"passed": false`

**Potential Causes**:
1. **Data issue**: Check if enrollment/staffing data is correct
2. **Edge cases**: Small sample sizes can violate expected patterns
3. **Methodology change**: Verify staff scope definitions match expectations

**Investigation**:
```python
# Compare mean LCT across scopes
from infrastructure.database.queries import get_lct_summary_by_scope

scopes = ['teachers_only', 'teachers_core', 'instructional']
for scope in scopes:
    summary = get_lct_summary_by_scope(session, scope, "2023-24")
    print(f"{scope}: {summary['mean_lct']:.2f} min")
```

---

## Best Practices

1. **Always review QA before publishing**: Even with PASS status, scan outliers
2. **Archive QA reports**: Keep historical record for reproducibility
3. **Document methodology changes**: Update hierarchy checks if scope definitions change
4. **Investigate warnings promptly**: Very low LCT may indicate data quality issues
5. **Track pass rates over time**: Declining rates may indicate data source problems

---

## See Also

- [Methodology](METHODOLOGY.md) - LCT calculation approach
- [Calculate LCT Variants Script](../infrastructure/scripts/analyze/calculate_lct_variants.py) - Implementation
- [Database Setup](DATABASE_SETUP.md) - Calculation run tracking

---

**Last Updated**: December 28, 2025
**QA Dashboard Version**: 2.0
**Current Pass Rate**: 99.46% (2023-24 data)
