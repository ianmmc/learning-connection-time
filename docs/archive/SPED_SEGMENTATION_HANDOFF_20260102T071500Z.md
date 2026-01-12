# SPED Segmentation Implementation Handoff

**Created:** 2026-01-02T07:15:00Z  
**Purpose:** Enable Claude Code (Sonnet) to implement GenEd/SPED teacher segmentation for refined LCT calculations  
**Model Target:** Claude Sonnet 4 (optimized for token efficiency)

---

## Executive Summary

This handoff provides step-by-step implementation instructions for segmenting special education (SPED) teachers from general education (GenEd) teachers to improve LCT calculation accuracy. Current LCT metrics show higher-than-expected values (median ~25 minutes vs. anticipated ~18 minutes), likely because SPED teachers are included in denominators despite serving smaller, specialized caseloads.

**Key Discovery:** NCES CCD Staff files do NOT contain SPED teacher categories. Federal SPED staffing data exists only at the state level (IDEA Section 618). The only federal source with district-level SPED teacher counts is **CRDC (Civil Rights Data Collection)**.

**Strategy:** Use CRDC 2017-18 as the foundation for SPED segmentation, validated against IDEA 618 LEA Child Count 2022-23.

---

## Table of Contents

1. [Data Source Overview](#1-data-source-overview)
2. [Phase 1A: CRDC 2017-18 Integration](#2-phase-1a-crdc-2017-18-integration)
3. [Phase 1B: IDEA 618 Validation Layer](#3-phase-1b-idea-618-validation-layer)
4. [Phase 1C: LCT Calculation Updates](#4-phase-1c-lct-calculation-updates)
5. [Phase 2: Equity Context Integration](#5-phase-2-equity-context-integration)
6. [Database Schema Modifications](#6-database-schema-modifications)
7. [Documentation Updates](#7-documentation-updates)
8. [Validation Checklist](#8-validation-checklist)

---

## 1. Data Source Overview

### 1.1 Why CRDC (Not CCD or IDEA 618)?

| Data Source | SPED Teachers | SPED Students | Granularity | Years Available |
|-------------|---------------|---------------|-------------|-----------------|
| **NCES CCD Staff** | ❌ None | ❌ None | LEA | Annual |
| **IDEA Section 618** | ✅ State-level only | ✅ LEA-level (since 2020-21) | Mixed | Annual |
| **CRDC** | ✅ School-level | ✅ School-level | School→LEA | Biennial |

**CRDC is the ONLY federal source with district-level SPED teacher counts.**

### 1.2 Data Year Strategy

| Component | Year | Rationale |
|-----------|------|-----------|
| CRDC (SPED teachers/students) | 2017-18 | Pre-COVID, most recent clean biennial data |
| IDEA 618 LEA Child Count | 2022-23 | Most recent LEA-level data for validation |
| CCD Enrollment/Staffing | 2023-24 | Current primary dataset |
| Bell Schedules | 2025-26/2024-25 | Current enrichment campaign |

**Temporal mismatch is acceptable** because:
- SPED teacher ratios are relatively stable year-over-year
- We're calculating proportions (GenEd:SPED ratio), not absolute counts
- Mixed-year methodology already established in project (enrollment/staffing/bell schedules)

### 1.3 CRDC Collection History

CRDC is collected biennially:
- 2000, 2004, 2006, 2009-10, 2011-12, 2013-14, 2015-16, **2017-18**, 2020-21, 2021-22, 2023-24

**2017-18 is preferred** because:
- Pre-COVID (avoids pandemic staffing anomalies)
- More recent than 2015-16
- 2020-21 and 2021-22 are COVID-affected
- 2023-24 not yet fully released as of handoff date

---

## 2. Phase 1A: CRDC 2017-18 Integration

### 2.1 Data Acquisition

**Download URL:**
```
https://ocrdata.ed.gov/assets/downloads/CRDC-2017-18-School-Characteristics-and-Membership-and-Staffing.zip
```

**Alternative (if above changes):**
1. Go to: https://ocrdata.ed.gov/
2. Navigate: Data Downloads → 2017-18
3. Download: "School Characteristics, Membership, and Staffing" file

**Expected file:** ~118 MB ZIP containing CSV(s)

**Storage location:**
```
data/raw/federal/crdc/2017_18/
├── CRDC_2017-18_School_Data.csv (or similar name)
├── README.txt (if included)
└── metadata/ (create if needed)
    └── download_info.yaml
```

**Create download metadata:**
```yaml
# data/raw/federal/crdc/2017_18/metadata/download_info.yaml
source: "Office for Civil Rights Data Collection"
url: "https://ocrdata.ed.gov/assets/downloads/CRDC-2017-18-School-Characteristics-and-Membership-and-Staffing.zip"
downloaded: "2026-01-XX"  # Fill in actual date
collection_year: "2017-18"
file_size_mb: 118
notes: "Pre-COVID data for SPED segmentation"
```

### 2.2 Key CRDC Fields to Extract

**School Identification:**
- `COMBOKEY` - Unique school identifier (state FIPS + LEA ID + school ID)
- `LEA_STATE` - State abbreviation
- `LEAID` - LEA identifier (matches NCES CCD)
- `LEA_NAME` - LEA name
- `SCHID` - School identifier
- `SCH_NAME` - School name

**SPED Teacher Data:**
- `SCH_FTETEACH_CERT_IDEA` - FTE teachers certified to teach students with disabilities (IDEA)
- `SCH_FTETEACH_NOTCERT_IDEA` - FTE teachers NOT certified but teaching IDEA students

**Total Teacher Data (for ratio calculation):**
- `SCH_FTETEACH_TOT` - Total FTE teachers at school

**SPED Student Data:**
- `TOT_IDEAENR_M` - Male students with disabilities (IDEA)
- `TOT_IDEAENR_F` - Female students with disabilities (IDEA)
- Or combined: `TOT_IDEAENR` if available

**Total Enrollment:**
- `TOT_ENR_M` - Male total enrollment
- `TOT_ENR_F` - Female total enrollment

### 2.3 Processing Script

**Create:** `infrastructure/scripts/extract/extract_crdc_sped.py`

```python
#!/usr/bin/env python3
"""
Extract SPED teacher and student data from CRDC 2017-18.
Aggregates school-level data to LEA-level for LCT integration.

Usage:
    python extract_crdc_sped.py data/raw/federal/crdc/2017_18/CRDC_*.csv
"""

import pandas as pd
import argparse
import logging
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from infrastructure.utilities.common import setup_logging, safe_divide

def extract_crdc_sped(input_path: str, output_dir: str = None) -> pd.DataFrame:
    """
    Extract and aggregate CRDC SPED data to LEA level.
    
    Args:
        input_path: Path to CRDC CSV file
        output_dir: Output directory (default: data/processed/crdc/)
    
    Returns:
        DataFrame with LEA-level SPED metrics
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Loading CRDC data from {input_path}")
    
    # Load CRDC data
    df = pd.read_csv(input_path, low_memory=False)
    logger.info(f"Loaded {len(df):,} school records")
    
    # Standardize column names (CRDC uses uppercase)
    df.columns = df.columns.str.upper()
    
    # Identify relevant columns (CRDC column names may vary slightly)
    # These are the expected patterns - adjust if actual file differs
    teacher_cols = {
        'sped_teachers_cert': 'SCH_FTETEACH_CERT_IDEA',
        'sped_teachers_notcert': 'SCH_FTETEACH_NOTCERT_IDEA', 
        'total_teachers': 'SCH_FTETEACH_TOT'
    }
    
    student_cols = {
        'sped_male': 'TOT_IDEAENR_M',
        'sped_female': 'TOT_IDEAENR_F',
        'total_male': 'TOT_ENR_M',
        'total_female': 'TOT_ENR_F'
    }
    
    # Check which columns exist
    available_teacher_cols = {k: v for k, v in teacher_cols.items() if v in df.columns}
    available_student_cols = {k: v for k, v in student_cols.items() if v in df.columns}
    
    logger.info(f"Found teacher columns: {list(available_teacher_cols.keys())}")
    logger.info(f"Found student columns: {list(available_student_cols.keys())}")
    
    # Calculate school-level SPED metrics
    df['sped_teachers'] = (
        df.get(teacher_cols['sped_teachers_cert'], 0).fillna(0) +
        df.get(teacher_cols['sped_teachers_notcert'], 0).fillna(0)
    )
    
    df['total_teachers'] = df.get(teacher_cols['total_teachers'], 0).fillna(0)
    
    df['sped_students'] = (
        df.get(student_cols['sped_male'], 0).fillna(0) +
        df.get(student_cols['sped_female'], 0).fillna(0)
    )
    
    df['total_students'] = (
        df.get(student_cols['total_male'], 0).fillna(0) +
        df.get(student_cols['total_female'], 0).fillna(0)
    )
    
    # Calculate GenEd teachers (total - SPED)
    df['gened_teachers'] = df['total_teachers'] - df['sped_teachers']
    df['gened_teachers'] = df['gened_teachers'].clip(lower=0)  # Prevent negative
    
    df['gened_students'] = df['total_students'] - df['sped_students']
    df['gened_students'] = df['gened_students'].clip(lower=0)
    
    # Aggregate to LEA level
    logger.info("Aggregating to LEA level...")
    
    lea_agg = df.groupby('LEAID').agg({
        'LEA_NAME': 'first',
        'LEA_STATE': 'first',
        'sped_teachers': 'sum',
        'gened_teachers': 'sum',
        'total_teachers': 'sum',
        'sped_students': 'sum',
        'gened_students': 'sum',
        'total_students': 'sum',
        'COMBOKEY': 'count'  # Number of schools
    }).reset_index()
    
    lea_agg.rename(columns={
        'LEAID': 'nces_id',
        'LEA_NAME': 'district_name',
        'LEA_STATE': 'state',
        'COMBOKEY': 'schools_in_crdc'
    }, inplace=True)
    
    # Calculate ratios
    lea_agg['sped_teacher_ratio'] = safe_divide(
        lea_agg['sped_teachers'], 
        lea_agg['total_teachers']
    )
    
    lea_agg['sped_student_ratio'] = safe_divide(
        lea_agg['sped_students'],
        lea_agg['total_students']
    )
    
    # Add data source metadata
    lea_agg['crdc_year'] = '2017-18'
    lea_agg['data_source'] = 'crdc'
    
    logger.info(f"Aggregated to {len(lea_agg):,} LEAs")
    logger.info(f"Mean SPED teacher ratio: {lea_agg['sped_teacher_ratio'].mean():.1%}")
    logger.info(f"Mean SPED student ratio: {lea_agg['sped_student_ratio'].mean():.1%}")
    
    # Save output
    if output_dir is None:
        output_dir = Path('data/processed/crdc/')
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / 'crdc_sped_by_lea_2017_18.csv'
    lea_agg.to_csv(output_path, index=False)
    logger.info(f"Saved LEA-level SPED data to {output_path}")
    
    # Also save a slim version with just the ratios for merging
    slim_cols = ['nces_id', 'state', 'sped_teacher_ratio', 'sped_student_ratio', 
                 'sped_teachers', 'gened_teachers', 'total_teachers',
                 'sped_students', 'gened_students', 'total_students', 'crdc_year']
    
    slim_path = output_dir / 'crdc_sped_ratios_2017_18.csv'
    lea_agg[slim_cols].to_csv(slim_path, index=False)
    logger.info(f"Saved slim ratio file to {slim_path}")
    
    return lea_agg


def main():
    parser = argparse.ArgumentParser(description='Extract CRDC SPED data')
    parser.add_argument('input_file', help='Path to CRDC CSV file')
    parser.add_argument('--output-dir', '-o', help='Output directory')
    parser.add_argument('--verbose', '-v', action='store_true')
    
    args = parser.parse_args()
    
    setup_logging(verbose=args.verbose)
    
    extract_crdc_sped(args.input_file, args.output_dir)


if __name__ == '__main__':
    main()
```

### 2.4 Expected Output

**Primary output:** `data/processed/crdc/crdc_sped_by_lea_2017_18.csv`

| Column | Type | Description |
|--------|------|-------------|
| nces_id | str | NCES LEA identifier (matches CCD) |
| district_name | str | District name from CRDC |
| state | str | Two-letter state code |
| sped_teachers | float | Total SPED-certified teachers (FTE) |
| gened_teachers | float | Non-SPED teachers (FTE) |
| total_teachers | float | All teachers (FTE) |
| sped_students | int | Students with disabilities (IDEA) |
| gened_students | int | Students without disabilities |
| total_students | int | Total enrollment |
| schools_in_crdc | int | Number of schools in CRDC data |
| sped_teacher_ratio | float | SPED teachers / total teachers |
| sped_student_ratio | float | SPED students / total students |
| crdc_year | str | "2017-18" |
| data_source | str | "crdc" |

**Slim output:** `data/processed/crdc/crdc_sped_ratios_2017_18.csv`
- Contains only merge-relevant columns for joining with LCT data

---

## 3. Phase 1B: IDEA 618 Validation Layer

### 3.1 Data Acquisition

**Download URL:**
```
https://data.ed.gov/dataset/16968dd3-87bd-4e4a-92ed-50f03e6c4941/resource/0e0a1a55-57f5-4e50-b66e-1a68949e38f3/download/bchildcountdisabilitycategorylea2022-23.csv
```

**Alternative navigation:**
1. Go to: https://data.ed.gov/dataset/idea-section-618-lea-part-b-child-count
2. Download: 2022-23 CSV file

**Storage location:**
```
data/raw/federal/idea-618/2022_23/
├── bchildcountdisabilitycategorylea2022-23.csv
└── metadata/
    └── download_info.yaml
```

### 3.2 Key IDEA 618 Fields

**LEA Identification:**
- `State Name` - Full state name
- `LEA State ID` - State-assigned LEA ID
- `LEA Name` - LEA name
- `SEA ID` - State Education Agency ID

**Child Count Data:**
- `Ages 3-5` - Students ages 3-5 with disabilities
- `Ages 6-21` - Students ages 6-21 with disabilities
- `Total` - Total students with disabilities

**Disability Categories (13 types):**
- Autism
- Deaf-blindness
- Developmental delay
- Emotional disturbance
- Hearing impairment
- Intellectual disability
- Multiple disabilities
- Orthopedic impairment
- Other health impairment
- Specific learning disability
- Speech or language impairment
- Traumatic brain injury
- Visual impairment

### 3.3 Processing Script

**Create:** `infrastructure/scripts/extract/extract_idea618_childcount.py`

```python
#!/usr/bin/env python3
"""
Extract IDEA Section 618 LEA-level child count data for SPED validation.

Usage:
    python extract_idea618_childcount.py data/raw/federal/idea-618/2022_23/*.csv
"""

import pandas as pd
import argparse
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from infrastructure.utilities.common import setup_logging, standardize_state

def extract_idea618(input_path: str, output_dir: str = None) -> pd.DataFrame:
    """
    Extract IDEA 618 LEA child count data.
    
    Args:
        input_path: Path to IDEA 618 CSV file
        output_dir: Output directory
    
    Returns:
        DataFrame with LEA-level SPED enrollment from IDEA 618
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Loading IDEA 618 data from {input_path}")
    
    df = pd.read_csv(input_path, low_memory=False)
    logger.info(f"Loaded {len(df):,} LEA records")
    
    # Standardize column names
    df.columns = df.columns.str.strip()
    
    # Map state names to abbreviations
    df['state'] = df['State Name'].apply(standardize_state)
    
    # Extract relevant columns
    result = pd.DataFrame({
        'state': df['state'],
        'lea_state_id': df['LEA State ID'].astype(str),
        'lea_name': df['LEA Name'],
        'idea618_sped_3_5': pd.to_numeric(df.get('Ages 3-5', 0), errors='coerce').fillna(0),
        'idea618_sped_6_21': pd.to_numeric(df.get('Ages 6-21', 0), errors='coerce').fillna(0),
        'idea618_sped_total': pd.to_numeric(df.get('Total', 0), errors='coerce').fillna(0),
        'idea618_year': '2022-23'
    })
    
    # Note: IDEA 618 uses state LEA IDs, not NCES IDs
    # Crosswalk to NCES IDs will be needed for merging
    logger.info(f"Processed {len(result):,} LEAs")
    logger.info(f"Total SPED students: {result['idea618_sped_total'].sum():,.0f}")
    
    # Save output
    if output_dir is None:
        output_dir = Path('data/processed/idea-618/')
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / 'idea618_childcount_lea_2022_23.csv'
    result.to_csv(output_path, index=False)
    logger.info(f"Saved to {output_path}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Extract IDEA 618 child count data')
    parser.add_argument('input_file', help='Path to IDEA 618 CSV')
    parser.add_argument('--output-dir', '-o', help='Output directory')
    parser.add_argument('--verbose', '-v', action='store_true')
    
    args = parser.parse_args()
    setup_logging(verbose=args.verbose)
    extract_idea618(args.input_file, args.output_dir)


if __name__ == '__main__':
    main()
```

### 3.4 Validation Approach

**Purpose:** Cross-check CRDC SPED student counts against IDEA 618 LEA data.

**Challenge:** IDEA 618 uses state LEA IDs; CRDC/CCD use NCES IDs. A crosswalk is needed.

**Crosswalk source:** NCES CCD Directory file contains both:
- `LEAID` - NCES LEA ID (used by CRDC)
- `ST_LEAID` - State LEA ID (used by IDEA 618)

**Create:** `infrastructure/scripts/validate/validate_crdc_vs_idea618.py`

```python
#!/usr/bin/env python3
"""
Validate CRDC SPED enrollment against IDEA 618 LEA child count.
Generates validation report with correlation analysis.
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from datetime import datetime

def validate_sped_counts(
    crdc_path: str,
    idea618_path: str,
    crosswalk_path: str,
    output_dir: str = None
):
    """
    Validate CRDC SPED counts against IDEA 618.
    
    Args:
        crdc_path: Path to CRDC LEA-level SPED data
        idea618_path: Path to IDEA 618 LEA child count
        crosswalk_path: Path to CCD directory with LEAID and ST_LEAID
        output_dir: Output directory for validation report
    """
    logger = logging.getLogger(__name__)
    
    # Load data
    crdc = pd.read_csv(crdc_path)
    idea618 = pd.read_csv(idea618_path)
    crosswalk = pd.read_csv(crosswalk_path, usecols=['LEAID', 'ST_LEAID', 'LEA_NAME', 'ST'])
    
    # Standardize crosswalk
    crosswalk.rename(columns={
        'LEAID': 'nces_id',
        'ST_LEAID': 'lea_state_id',
        'ST': 'state'
    }, inplace=True)
    crosswalk['lea_state_id'] = crosswalk['lea_state_id'].astype(str)
    
    # Merge IDEA 618 with crosswalk to get NCES IDs
    idea618_with_nces = idea618.merge(
        crosswalk[['nces_id', 'lea_state_id', 'state']],
        on=['lea_state_id', 'state'],
        how='left'
    )
    
    matched_pct = idea618_with_nces['nces_id'].notna().mean()
    logger.info(f"IDEA 618 to NCES crosswalk match rate: {matched_pct:.1%}")
    
    # Merge with CRDC
    comparison = crdc.merge(
        idea618_with_nces[['nces_id', 'idea618_sped_total', 'idea618_sped_6_21']],
        on='nces_id',
        how='inner'
    )
    
    logger.info(f"Matched {len(comparison):,} LEAs for comparison")
    
    # Calculate validation metrics
    # Compare CRDC sped_students (all grades) to IDEA 618 total
    comparison['diff_abs'] = comparison['sped_students'] - comparison['idea618_sped_total']
    comparison['diff_pct'] = (comparison['diff_abs'] / comparison['idea618_sped_total']).replace([np.inf, -np.inf], np.nan)
    
    # Correlation
    corr = comparison['sped_students'].corr(comparison['idea618_sped_total'])
    
    # Summary statistics
    validation_summary = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'matched_leas': len(comparison),
        'correlation': round(corr, 4),
        'mean_crdc_sped': round(comparison['sped_students'].mean(), 1),
        'mean_idea618_sped': round(comparison['idea618_sped_total'].mean(), 1),
        'median_diff_pct': round(comparison['diff_pct'].median() * 100, 1),
        'within_10pct': (comparison['diff_pct'].abs() <= 0.10).mean(),
        'within_25pct': (comparison['diff_pct'].abs() <= 0.25).mean(),
        'crdc_year': '2017-18',
        'idea618_year': '2022-23'
    }
    
    logger.info(f"Correlation: {corr:.3f}")
    logger.info(f"Within 10%: {validation_summary['within_10pct']:.1%}")
    logger.info(f"Within 25%: {validation_summary['within_25pct']:.1%}")
    
    # Generate report
    if output_dir is None:
        output_dir = Path('data/processed/validation/')
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save comparison data
    comparison_path = output_dir / 'crdc_vs_idea618_comparison.csv'
    comparison.to_csv(comparison_path, index=False)
    
    # Save summary
    import json
    summary_path = output_dir / 'sped_validation_summary.json'
    with open(summary_path, 'w') as f:
        json.dump(validation_summary, f, indent=2)
    
    logger.info(f"Saved validation report to {output_dir}")
    
    return validation_summary, comparison


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--crdc', required=True)
    parser.add_argument('--idea618', required=True)
    parser.add_argument('--crosswalk', required=True)
    parser.add_argument('--output-dir', '-o')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    validate_sped_counts(args.crdc, args.idea618, args.crosswalk, args.output_dir)
```

### 3.5 Expected Validation Outcomes

**Acceptable variance:** Given 5-year temporal gap (2017-18 CRDC vs 2022-23 IDEA 618):
- Correlation ≥ 0.85 → Strong validation
- Correlation 0.70-0.85 → Acceptable with notes
- Correlation < 0.70 → Investigate data quality

**Reasons for variance:**
- SPED identification rates change over time
- District boundary changes
- CRDC samples schools; IDEA 618 is universe
- Different definitions (CRDC includes Section 504; IDEA 618 is IDEA-only)

---

## 4. Phase 1C: LCT Calculation Updates

### 4.1 New LCT Variants

Add two new LCT scopes:

| Variant | Staff Numerator | Enrollment Denominator |
|---------|-----------------|------------------------|
| **LCT-Teachers-GenEd** | GenEd teachers only | GenEd students (K-12) |
| **LCT-Teachers-SPED** | SPED teachers only | SPED students |

**Formula:**
```
LCT-Teachers-GenEd = (Daily Minutes × GenEd Teachers) / GenEd Students
LCT-Teachers-SPED = (Daily Minutes × SPED Teachers) / SPED Students
```

### 4.2 Applying CRDC Ratios to Current Data

Since CRDC is from 2017-18 but our primary data is 2023-24, we apply CRDC ratios proportionally:

```python
# For each district with both CCD 2023-24 and CRDC 2017-18 data:
gened_teachers_2023 = ccd_total_teachers_2023 * (1 - crdc_sped_teacher_ratio)
sped_teachers_2023 = ccd_total_teachers_2023 * crdc_sped_teacher_ratio

gened_students_2023 = ccd_total_enrollment_2023 * (1 - crdc_sped_student_ratio)
sped_students_2023 = ccd_total_enrollment_2023 * crdc_sped_student_ratio
```

**Rationale:** 
- SPED teacher ratios are relatively stable (state policies don't change dramatically)
- Using ratios (not absolute counts) accounts for district size changes
- Method is transparent and reproducible

### 4.3 Script Modifications

**Update:** `infrastructure/scripts/analyze/calculate_lct_variants.py`

Add import of CRDC data and new calculation functions:

```python
# Add to existing calculate_lct_variants.py

def load_crdc_ratios(crdc_path: str) -> pd.DataFrame:
    """Load CRDC SPED ratios for merging."""
    return pd.read_csv(crdc_path, usecols=[
        'nces_id', 'sped_teacher_ratio', 'sped_student_ratio'
    ])

def calculate_sped_lct_variants(
    df: pd.DataFrame,
    crdc_ratios: pd.DataFrame,
    instructional_minutes: int = 360
) -> pd.DataFrame:
    """
    Calculate GenEd and SPED-specific LCT variants.
    
    Args:
        df: DataFrame with district data (enrollment, teachers)
        crdc_ratios: DataFrame with SPED ratios from CRDC
        instructional_minutes: Daily instructional minutes
    
    Returns:
        DataFrame with new LCT columns added
    """
    # Merge CRDC ratios
    df = df.merge(crdc_ratios, on='nces_id', how='left')
    
    # Fill missing ratios with state or national median
    state_medians = df.groupby('state')['sped_teacher_ratio'].transform('median')
    national_median = df['sped_teacher_ratio'].median()
    
    df['sped_teacher_ratio'] = df['sped_teacher_ratio'].fillna(state_medians)
    df['sped_teacher_ratio'] = df['sped_teacher_ratio'].fillna(national_median)
    
    df['sped_student_ratio'] = df['sped_student_ratio'].fillna(
        df.groupby('state')['sped_student_ratio'].transform('median')
    )
    df['sped_student_ratio'] = df['sped_student_ratio'].fillna(
        df['sped_student_ratio'].median()
    )
    
    # Calculate segmented counts
    df['teachers_gened_est'] = df['teachers_k12'] * (1 - df['sped_teacher_ratio'])
    df['teachers_sped_est'] = df['teachers_k12'] * df['sped_teacher_ratio']
    
    df['enrollment_gened_est'] = df['enrollment_k12'] * (1 - df['sped_student_ratio'])
    df['enrollment_sped_est'] = df['enrollment_k12'] * df['sped_student_ratio']
    
    # Calculate LCT variants
    df['lct_teachers_gened'] = (
        instructional_minutes * df['teachers_gened_est']
    ) / df['enrollment_gened_est']
    
    df['lct_teachers_sped'] = (
        instructional_minutes * df['teachers_sped_est']
    ) / df['enrollment_sped_est']
    
    # Add metadata
    df['sped_source'] = 'crdc_2017-18_ratio'
    df['sped_method'] = 'proportional_application'
    
    return df
```

### 4.4 Database Updates

**Add columns to lct_calculations table:**

```sql
-- Add SPED-segmented LCT columns
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS lct_teachers_gened NUMERIC,
ADD COLUMN IF NOT EXISTS lct_teachers_sped NUMERIC,
ADD COLUMN IF NOT EXISTS teachers_gened_est NUMERIC,
ADD COLUMN IF NOT EXISTS teachers_sped_est NUMERIC,
ADD COLUMN IF NOT EXISTS enrollment_gened_est NUMERIC,
ADD COLUMN IF NOT EXISTS enrollment_sped_est NUMERIC,
ADD COLUMN IF NOT EXISTS sped_teacher_ratio NUMERIC,
ADD COLUMN IF NOT EXISTS sped_student_ratio NUMERIC,
ADD COLUMN IF NOT EXISTS sped_source VARCHAR(50),
ADD COLUMN IF NOT EXISTS sped_method VARCHAR(50);
```

---

## 5. Phase 2: Equity Context Integration

### 5.1 CCD F-33 Finance Data

**What it is:** School district finance survey (identical to Census Annual Survey of School System Finances)

**Why it matters:** Correlate LCT with per-pupil expenditure to test if more spending → more teacher time

**Download URL:**
```
https://nces.ed.gov/ccd/files/f33agency.asp
```
Select year 2022-23 (most recent as of handoff)

**Direct download (typical pattern):**
```
https://nces.ed.gov/ccd/Data/zip/sdf_lea_fy2022_l_2a_101023.zip
```

**Storage location:**
```
data/raw/federal/nces-ccd/finance/2022_23/
├── sdf_lea_fy2022_*.csv
└── metadata/
    └── download_info.yaml
```

**Key fields to extract:**

| Field | Description | Use Case |
|-------|-------------|----------|
| LEAID | NCES LEA ID | Join key |
| TOTALREV | Total revenue | Resource measure |
| TFEDREV | Federal revenue | Funding source analysis |
| TSTREV | State revenue | Funding source analysis |
| TLOCREV | Local revenue | Equity indicator (local wealth) |
| TOTALEXP | Total expenditure | Spending measure |
| TCURSPND | Total current spending | Operating costs |
| TCURINST | Instruction spending | Direct instruction resources |
| TCURSSVC | Student support services | Support investment |
| PPEXPEND | Per-pupil expenditure (if available) | Primary metric |
| MEMBERSCH | Enrollment (from finance survey) | Validation |

**Processing script:** `infrastructure/scripts/extract/extract_f33_finance.py`

```python
#!/usr/bin/env python3
"""
Extract CCD F-33 finance data for equity analysis.
"""

import pandas as pd
import logging
from pathlib import Path

def extract_f33_finance(input_path: str, output_dir: str = None) -> pd.DataFrame:
    """Extract and standardize F-33 finance data."""
    logger = logging.getLogger(__name__)
    
    df = pd.read_csv(input_path, low_memory=False)
    logger.info(f"Loaded {len(df):,} LEA finance records")
    
    # Select relevant columns (adjust based on actual file structure)
    finance_cols = [
        'LEAID', 'STNAME', 'NAME',
        'TOTALREV', 'TFEDREV', 'TSTREV', 'TLOCREV',
        'TOTALEXP', 'TCURSPND', 'TCURINST', 'TCURSSVC',
        'MEMBERSCH'  # Enrollment from finance survey
    ]
    
    # Filter to available columns
    available = [c for c in finance_cols if c in df.columns]
    result = df[available].copy()
    
    # Standardize names
    result.rename(columns={
        'LEAID': 'nces_id',
        'STNAME': 'state_name',
        'NAME': 'district_name',
        'MEMBERSCH': 'enrollment_finance'
    }, inplace=True)
    
    # Calculate per-pupil metrics
    if 'enrollment_finance' in result.columns and 'TOTALEXP' in result.columns:
        result['per_pupil_expenditure'] = (
            result['TOTALEXP'] / result['enrollment_finance']
        ).round(2)
        
        result['per_pupil_instruction'] = (
            result.get('TCURINST', 0) / result['enrollment_finance']
        ).round(2)
    
    # Calculate local revenue share (equity indicator)
    if 'TLOCREV' in result.columns and 'TOTALREV' in result.columns:
        result['local_revenue_share'] = (
            result['TLOCREV'] / result['TOTALREV']
        ).round(4)
    
    # Add metadata
    result['finance_year'] = '2022-23'
    result['data_source'] = 'ccd_f33'
    
    # Save
    if output_dir is None:
        output_dir = Path('data/processed/finance/')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / 'f33_finance_by_lea_2022_23.csv'
    result.to_csv(output_path, index=False)
    logger.info(f"Saved to {output_path}")
    
    return result
```

### 5.2 EDGE Poverty Estimates

**What it is:** School neighborhood poverty estimates using Census ACS data

**Why it matters:** Test if high-poverty schools have lower LCT (equity analysis)

**Download URL:**
```
https://nces.ed.gov/programs/edge/Economic/NeighborhoodPoverty
```

**Key metric:** Income-to-Poverty Ratio (IPR) for school neighborhoods

**Processing approach:**
1. Download school-level poverty estimates
2. Aggregate to LEA level (weighted by enrollment)
3. Categorize districts by poverty quartile
4. Cross-reference with LCT calculations

**Storage location:**
```
data/raw/federal/nces-edge/poverty/
├── edge_poverty_*.csv
└── metadata/
    └── download_info.yaml
```

### 5.3 Integration with LCT Analysis

**Analysis questions for Phase 2:**

1. **Finance-LCT Correlation:**
   - Do districts with higher per-pupil expenditure have higher LCT?
   - Does instruction-specific spending predict LCT better than total spending?

2. **Poverty-LCT Correlation:**
   - Do high-poverty districts have lower LCT?
   - Does this hold when controlling for state and locale?

3. **Funding Source Analysis:**
   - Do districts relying more on local funding have higher LCT?
   - How does federal/state funding relate to LCT?

**Recommended visualizations:**
- Scatter plot: Per-pupil expenditure vs. LCT
- Box plot: LCT by poverty quartile
- Map: LCT geographic distribution with poverty overlay

---

## 6. Database Schema Modifications

### 6.1 New Tables

**Create:** `infrastructure/database/migrations/add_sped_tables.sql`

```sql
-- CRDC SPED data by LEA
CREATE TABLE IF NOT EXISTS crdc_sped (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(7) NOT NULL REFERENCES districts(nces_id),
    crdc_year VARCHAR(7) NOT NULL,
    sped_teachers NUMERIC,
    gened_teachers NUMERIC,
    total_teachers NUMERIC,
    sped_students INTEGER,
    gened_students INTEGER,
    total_students INTEGER,
    sped_teacher_ratio NUMERIC,
    sped_student_ratio NUMERIC,
    schools_in_crdc INTEGER,
    data_source VARCHAR(20) DEFAULT 'crdc',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nces_id, crdc_year)
);

-- IDEA 618 validation data
CREATE TABLE IF NOT EXISTS idea618_childcount (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(7) REFERENCES districts(nces_id),
    lea_state_id VARCHAR(20),
    state VARCHAR(2) NOT NULL,
    lea_name VARCHAR(200),
    idea618_year VARCHAR(7) NOT NULL,
    sped_ages_3_5 INTEGER,
    sped_ages_6_21 INTEGER,
    sped_total INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nces_id, idea618_year)
);

-- Finance data (Phase 2)
CREATE TABLE IF NOT EXISTS district_finance (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(7) NOT NULL REFERENCES districts(nces_id),
    finance_year VARCHAR(7) NOT NULL,
    total_revenue NUMERIC,
    federal_revenue NUMERIC,
    state_revenue NUMERIC,
    local_revenue NUMERIC,
    total_expenditure NUMERIC,
    instruction_expenditure NUMERIC,
    support_expenditure NUMERIC,
    per_pupil_expenditure NUMERIC,
    per_pupil_instruction NUMERIC,
    local_revenue_share NUMERIC,
    data_source VARCHAR(20) DEFAULT 'ccd_f33',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nces_id, finance_year)
);

-- Poverty estimates (Phase 2)
CREATE TABLE IF NOT EXISTS district_poverty (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(7) NOT NULL REFERENCES districts(nces_id),
    poverty_year VARCHAR(7) NOT NULL,
    ipr_mean NUMERIC,  -- Income-to-Poverty Ratio mean
    ipr_median NUMERIC,
    poverty_rate NUMERIC,  -- % below poverty line
    poverty_quartile INTEGER,  -- 1-4 (4 = highest poverty)
    schools_in_estimate INTEGER,
    data_source VARCHAR(20) DEFAULT 'edge_poverty',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nces_id, poverty_year)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_crdc_sped_nces ON crdc_sped(nces_id);
CREATE INDEX IF NOT EXISTS idx_crdc_sped_state ON crdc_sped(nces_id);
CREATE INDEX IF NOT EXISTS idx_idea618_nces ON idea618_childcount(nces_id);
CREATE INDEX IF NOT EXISTS idx_idea618_state ON idea618_childcount(state);
CREATE INDEX IF NOT EXISTS idx_finance_nces ON district_finance(nces_id);
CREATE INDEX IF NOT EXISTS idx_poverty_nces ON district_poverty(nces_id);
```

### 6.2 SQLAlchemy Models

**Update:** `infrastructure/database/models.py`

```python
# Add to existing models.py

class CRDCSped(Base):
    """CRDC SPED teacher and student data by LEA."""
    __tablename__ = 'crdc_sped'
    
    id = Column(Integer, primary_key=True)
    nces_id = Column(String(7), ForeignKey('districts.nces_id'), nullable=False)
    crdc_year = Column(String(7), nullable=False)
    sped_teachers = Column(Numeric)
    gened_teachers = Column(Numeric)
    total_teachers = Column(Numeric)
    sped_students = Column(Integer)
    gened_students = Column(Integer)
    total_students = Column(Integer)
    sped_teacher_ratio = Column(Numeric)
    sped_student_ratio = Column(Numeric)
    schools_in_crdc = Column(Integer)
    data_source = Column(String(20), default='crdc')
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('nces_id', 'crdc_year', name='uq_crdc_sped_district_year'),
    )
    
    district = relationship('District', back_populates='crdc_sped')


class IDEA618ChildCount(Base):
    """IDEA Section 618 LEA-level child count data."""
    __tablename__ = 'idea618_childcount'
    
    id = Column(Integer, primary_key=True)
    nces_id = Column(String(7), ForeignKey('districts.nces_id'))
    lea_state_id = Column(String(20))
    state = Column(String(2), nullable=False)
    lea_name = Column(String(200))
    idea618_year = Column(String(7), nullable=False)
    sped_ages_3_5 = Column(Integer)
    sped_ages_6_21 = Column(Integer)
    sped_total = Column(Integer)
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        UniqueConstraint('nces_id', 'idea618_year', name='uq_idea618_district_year'),
    )


class DistrictFinance(Base):
    """CCD F-33 finance data by LEA."""
    __tablename__ = 'district_finance'
    
    id = Column(Integer, primary_key=True)
    nces_id = Column(String(7), ForeignKey('districts.nces_id'), nullable=False)
    finance_year = Column(String(7), nullable=False)
    total_revenue = Column(Numeric)
    federal_revenue = Column(Numeric)
    state_revenue = Column(Numeric)
    local_revenue = Column(Numeric)
    total_expenditure = Column(Numeric)
    instruction_expenditure = Column(Numeric)
    support_expenditure = Column(Numeric)
    per_pupil_expenditure = Column(Numeric)
    per_pupil_instruction = Column(Numeric)
    local_revenue_share = Column(Numeric)
    data_source = Column(String(20), default='ccd_f33')
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('nces_id', 'finance_year', name='uq_finance_district_year'),
    )


class DistrictPoverty(Base):
    """EDGE poverty estimates by LEA."""
    __tablename__ = 'district_poverty'
    
    id = Column(Integer, primary_key=True)
    nces_id = Column(String(7), ForeignKey('districts.nces_id'), nullable=False)
    poverty_year = Column(String(7), nullable=False)
    ipr_mean = Column(Numeric)
    ipr_median = Column(Numeric)
    poverty_rate = Column(Numeric)
    poverty_quartile = Column(Integer)
    schools_in_estimate = Column(Integer)
    data_source = Column(String(20), default='edge_poverty')
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        UniqueConstraint('nces_id', 'poverty_year', name='uq_poverty_district_year'),
    )
```

---

## 7. Documentation Updates

### 7.1 Claude.md Updates

**Add to "What's Been Completed" section:**

```markdown
### ✅ SPED Segmentation Infrastructure (January 2026) ⭐ NEW
- **CRDC 2017-18 Integration**: School-level SPED data aggregated to LEA
- **IDEA 618 Validation**: LEA-level child count for cross-reference
- **New LCT Variants**: LCT-Teachers-GenEd, LCT-Teachers-SPED
- **Database Tables**: crdc_sped, idea618_childcount, district_finance, district_poverty
- **Scripts**: extract_crdc_sped.py, extract_idea618_childcount.py, validate_crdc_vs_idea618.py
```

**Add to "Current Challenges & Opportunities" section:**

```markdown
### SPED Data Limitations

**Federal Data Gap (GAO-24-106264):** District-level SPED teacher counts do not exist in IDEA Section 618. Personnel data is aggregated to state level only. CRDC is the only federal source with school-level SPED teacher data.

**Temporal Mismatch:** CRDC 2017-18 is used with CCD 2023-24 data. SPED ratios applied proportionally to current teacher counts.

**Validation:** IDEA 618 LEA Child Count 2022-23 used to validate CRDC SPED student ratios.
```

### 7.2 METHODOLOGY.md Updates

**Add new section after "LCT Variants":**

```markdown
### SPED-Segmented LCT Variants (Phase 1.5+)

To address the observation that SPED teachers serve smaller caseloads than general education teachers, we calculate segmented LCT variants:

| Variant | Staff Numerator | Enrollment Denominator | Source |
|---------|-----------------|------------------------|--------|
| LCT-Teachers-GenEd | GenEd teachers (estimated) | GenEd students (estimated) | CRDC ratio × CCD |
| LCT-Teachers-SPED | SPED teachers (estimated) | SPED students (estimated) | CRDC ratio × CCD |

**Methodology:**

1. **CRDC 2017-18** provides school-level SPED teacher and student counts
2. Aggregate school data to LEA level
3. Calculate ratios: `sped_teacher_ratio = sped_teachers / total_teachers`
4. Apply ratios to current CCD data: `teachers_gened_est = teachers_k12 × (1 - sped_teacher_ratio)`
5. Calculate segmented LCT using standard formula

**Validation:**
- CRDC SPED student counts validated against IDEA 618 LEA Child Count 2022-23
- Correlation threshold: ≥ 0.70 for acceptable validation
- Temporal gap (5 years) acceptable because SPED ratios are relatively stable

**Limitations:**
- CRDC is biennial; latest pre-COVID data is 2017-18
- School-to-LEA aggregation may mask within-district variation
- SPED definitions may differ slightly between CRDC (includes 504) and IDEA 618 (IDEA-only)
```

### 7.3 TERMINOLOGY.md Updates

**Add new section:**

```markdown
## SPED Segmentation Terms

### SPED (Special Education)
**Definition:** Educational services for students with disabilities under IDEA (Individuals with Disabilities Education Act)

**In LCT context:** SPED teachers serve smaller caseloads; including them in general LCT calculations inflates apparent connection time.

### CRDC (Civil Rights Data Collection)
**Definition:** Biennial federal survey collecting civil rights-related data from schools

**In LCT context:** Only federal source with school-level SPED teacher counts. Used for GenEd/SPED segmentation.

### IDEA Section 618
**Definition:** Federal data collection on students and personnel in special education

**In LCT context:** Provides LEA-level SPED student counts (since 2020-21) for validation. Personnel data is state-level only.

### GenEd (General Education)
**Definition:** Standard curriculum instruction for students without disabilities

**In LCT context:** GenEd teachers and students are the primary focus of LCT calculations, as they represent mainstream classroom instruction.

### SPED Teacher Ratio
**Definition:** `sped_teachers / total_teachers` from CRDC data

**Use:** Applied proportionally to CCD teacher counts to estimate current GenEd/SPED breakdown.

### SPED Student Ratio  
**Definition:** `sped_students / total_students` from CRDC data

**Use:** Applied proportionally to CCD enrollment to estimate GenEd/SPED student populations.
```

### 7.4 PROJECT_CONTEXT.md Updates

**Update "Evolution Strategy" section:**

```markdown
### Phase 1.5: Bell Schedule + SPED Segmentation (Current)
- Uses actual bell schedules where available
- **NEW:** Segments GenEd vs. SPED teachers using CRDC ratios
- **NEW:** Calculates separate LCT for GenEd and SPED populations
- Applies IDEA 618 validation for SPED student counts
- Addresses higher-than-expected LCT values

### Phase 2: Equity Context (Roadmap)
- Integrate CCD F-33 finance data
- Add EDGE poverty estimates
- Analyze LCT vs. per-pupil expenditure
- Test equity hypothesis: Do high-poverty districts have lower LCT?
```

---

## 8. Validation Checklist

### Phase 1A: CRDC Integration
- [ ] Download CRDC 2017-18 ZIP file
- [ ] Extract and verify CSV structure
- [ ] Run `extract_crdc_sped.py`
- [ ] Verify output has expected columns
- [ ] Check LEA count matches expectations (~15,000+ LEAs)
- [ ] Validate SPED ratios are reasonable (typically 10-20% SPED teachers)

### Phase 1B: IDEA 618 Validation
- [ ] Download IDEA 618 LEA Child Count 2022-23
- [ ] Run `extract_idea618_childcount.py`
- [ ] Create crosswalk using CCD Directory (LEAID ↔ ST_LEAID)
- [ ] Run `validate_crdc_vs_idea618.py`
- [ ] Verify correlation ≥ 0.70
- [ ] Document any systematic discrepancies

### Phase 1C: LCT Calculation Updates
- [ ] Run database migration SQL
- [ ] Update SQLAlchemy models
- [ ] Modify `calculate_lct_variants.py`
- [ ] Run LCT calculations with SPED segmentation
- [ ] Verify LCT-Teachers-GenEd < LCT-Teachers (expected pattern)
- [ ] Generate comparison report

### Documentation
- [ ] Update Claude.md with SPED section
- [ ] Update METHODOLOGY.md with segmentation details
- [ ] Update TERMINOLOGY.md with new terms
- [ ] Update PROJECT_CONTEXT.md evolution strategy

### Phase 2 Preparation
- [ ] Download CCD F-33 Finance 2022-23
- [ ] Download EDGE Poverty Estimates
- [ ] Create processing scripts
- [ ] Run database migrations for finance/poverty tables

---

## Appendix A: File Locations Summary

```
data/
├── raw/
│   └── federal/
│       ├── crdc/
│       │   └── 2017_18/
│       │       ├── CRDC_*.csv
│       │       └── metadata/download_info.yaml
│       ├── idea-618/
│       │   └── 2022_23/
│       │       ├── bchildcount*.csv
│       │       └── metadata/download_info.yaml
│       └── nces-ccd/
│           └── finance/
│               └── 2022_23/
│                   └── sdf_lea_*.csv
│
├── processed/
│   ├── crdc/
│   │   ├── crdc_sped_by_lea_2017_18.csv
│   │   └── crdc_sped_ratios_2017_18.csv
│   ├── idea-618/
│   │   └── idea618_childcount_lea_2022_23.csv
│   ├── finance/
│   │   └── f33_finance_by_lea_2022_23.csv
│   └── validation/
│       ├── crdc_vs_idea618_comparison.csv
│       └── sped_validation_summary.json
│
infrastructure/
├── scripts/
│   ├── extract/
│   │   ├── extract_crdc_sped.py
│   │   ├── extract_idea618_childcount.py
│   │   └── extract_f33_finance.py
│   └── validate/
│       └── validate_crdc_vs_idea618.py
└── database/
    └── migrations/
        └── add_sped_tables.sql
```

---

## Appendix B: Expected Metrics

Based on national averages, expect approximately:

| Metric | Expected Range | Source |
|--------|----------------|--------|
| SPED teacher ratio | 10-18% | CRDC national average |
| SPED student ratio | 13-17% | IDEA 618 national average |
| LCT-Teachers-GenEd | 22-28 min | Estimated (lower than current 25 min median) |
| LCT-Teachers-SPED | 45-90 min | Estimated (smaller caseloads) |
| CRDC-IDEA618 correlation | ≥ 0.70 | Validation threshold |

---

## Appendix C: Troubleshooting

### CRDC Download Issues
- If primary URL fails, try OCR Data Collection portal directly
- Check for 2015-16 as fallback if 2017-18 unavailable
- File may be split into multiple CSVs (check for Part 1, Part 2, etc.)

### IDEA 618 Crosswalk Issues
- State LEA IDs may have leading zeros stripped
- Some states use different ID formats
- ~5-10% of LEAs may not match; this is acceptable

### Validation Correlation Low
- Check for state-level systematic differences
- Verify crosswalk is correctly matching LEAs
- Consider using state-level validation as supplement

### LCT Calculations Unexpected
- If LCT-GenEd > LCT-All, check ratio application logic
- If many districts missing CRDC data, use state medians
- Document all imputation decisions

---

**Document Version:** 1.0  
**Created:** 2026-01-02  
**Author:** Claude Opus 4.5 (strategic analysis session)  
**Target:** Claude Sonnet 4 (implementation)  
**Status:** Ready for implementation
