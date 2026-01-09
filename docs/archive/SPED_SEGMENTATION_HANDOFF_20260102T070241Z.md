# SPED/GenEd Segmentation Handoff Document

**Created:** 2026-01-02T07:02:41Z  
**Purpose:** Implementation instructions for Claude Code (Sonnet) to integrate special education data for LCT segmentation  
**Session Context:** Opus analysis of federal data sources for SPED/GenEd teacher and enrollment segmentation

---

## Executive Summary

### Problem Statement
Current LCT calculations use total teacher counts without distinguishing between general education (GenEd) classroom teachers and special education (SPED) teachers. This inflates apparent GenEd LCT because SPED teachers serve a smaller, specialized student population with legally mandated lower ratios.

### Solution Architecture
Integrate two complementary federal data sources:
1. **CRDC 2017-18** (Foundation): Only federal source with district-level SPED teacher counts
2. **IDEA Section 618 LEA Child Count 2022-23** (Validation): LEA-level SPED student counts by disability category

### Key Discovery
**CCD does NOT contain SPED enrollment data.** The NCES CCD Membership file (LEA 052) breaks down enrollment by Grade × Race/Ethnicity × Sex only—there is no disability dimension. SPED data comes exclusively from CRDC and IDEA Section 618.

### Data Availability Summary

| Data Element | Source | Granularity | Latest Year | URL |
|--------------|--------|-------------|-------------|-----|
| SPED Teachers | CRDC | School→LEA | 2017-18 | ed.gov/ocr/data |
| SPED Students | CRDC | School→LEA | 2017-18 | ed.gov/ocr/data |
| SPED Students | IDEA 618 | LEA | 2022-23 | data.ed.gov |
| SPED Teachers | IDEA 618 | **State only** | 2022-23 | data.ed.gov |
| GenEd Teachers | CCD | LEA | 2023-24 | nces.ed.gov/ccd |
| Total Enrollment | CCD | LEA | 2023-24 | nces.ed.gov/ccd |

**Critical Gap (GAO-24-106264):** District-level SPED teacher counts do NOT exist in IDEA 618. Personnel data is aggregated to state level only.

---

## Phase 1A: CRDC 2017-18 Integration (Foundation)

### Overview
The Civil Rights Data Collection (CRDC) is the **only federal source** providing district-level SPED teacher counts. While biennial and somewhat dated (2017-18 is pre-COVID), it provides the essential GenEd:SPED teacher ratio needed for segmentation.

### Step 1: Download CRDC 2017-18 Data

**Download URL:**  
https://ocrdata.ed.gov/assets/downloads/2017-18-crdc-data.zip

**Alternative (if main link fails):**
https://www2.ed.gov/about/offices/list/ocr/docs/crdc-2017-18.html

**File Size:** ~118.7 MB (compressed)

**Commands:**
```bash
# Create directory structure
mkdir -p /Users/ianmmc/Development/learning-connection-time/data/raw/federal/crdc/2017-18

# Download (using curl with redirect following)
cd /Users/ianmmc/Development/learning-connection-time/data/raw/federal/crdc/2017-18
curl -L -o crdc-2017-18-data.zip "https://ocrdata.ed.gov/assets/downloads/2017-18-crdc-data.zip"

# Extract
unzip crdc-2017-18-data.zip

# List contents to identify relevant files
ls -la
```

### Step 2: Identify Relevant CRDC Files

CRDC data is organized by topic. Look for these files after extraction:

| File Pattern | Contains | Needed For |
|--------------|----------|------------|
| `*SCH*STAFF*` or `*staff*` | Teacher counts by certification | SPED teacher counts |
| `*SCH*ENROLL*` or `*enrollment*` | Student counts by program | SPED student counts |
| `*LEA*` | District-level identifiers | Matching to CCD |

**Key Variables to Extract:**

**For SPED Teachers:**
- `SCH_FTETEACH_CERT_SPE` - FTE SPED-certified teachers (school level)
- `SCH_FTETEACH_CERT_TOT` - FTE total certified teachers (for validation)

**For SPED Students:**
- `TOT_ENRL_IDEA` - Students with disabilities (IDEA) enrolled
- `TOT_ENRL_M` / `TOT_ENRL_F` - Total enrollment by sex (for validation)

**School Identifiers:**
- `COMBOKEY` - Unique school identifier (NCES format: SS-LLLLLLL-SSSSS)
- `LEA_STATE` - State abbreviation
- `LEA_NAME` - District name
- `LEAID` - District ID (7-digit NCES format)

### Step 3: Process CRDC Data

**Create processing script:**
```bash
touch /Users/ianmmc/Development/learning-connection-time/infrastructure/scripts/extract/extract_crdc_sped_data.py
```

**Script content:**
```python
#!/usr/bin/env python3
"""
Extract SPED teacher and student counts from CRDC 2017-18.
Aggregates school-level data to LEA (district) level for LCT integration.

Output: CSV with columns:
  - leaid: NCES district ID (7-digit)
  - lea_name: District name
  - state: Two-letter state code
  - sped_teachers_fte: SPED-certified teachers (FTE)
  - total_teachers_fte: Total certified teachers (FTE)
  - sped_students: Students with disabilities (IDEA)
  - total_students: Total enrollment
  - sped_teacher_ratio: sped_teachers / total_teachers
  - sped_student_ratio: sped_students / total_students
  - source_year: "2017-18"
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
CRDC_DIR = Path("/Users/ianmmc/Development/learning-connection-time/data/raw/federal/crdc/2017-18")
OUTPUT_DIR = Path("/Users/ianmmc/Development/learning-connection-time/data/processed/crdc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def find_crdc_files(base_dir: Path) -> dict:
    """Locate relevant CRDC files in the extracted directory."""
    files = {}
    
    # Common patterns for CRDC file organization
    patterns = {
        'staff': ['*staff*', '*STAFF*', '*teacher*', '*TEACHER*'],
        'enrollment': ['*enroll*', '*ENROLL*', '*membership*'],
        'school': ['*SCH*', '*school*']
    }
    
    for file in base_dir.rglob('*.csv'):
        name_lower = file.name.lower()
        if 'staff' in name_lower or 'teacher' in name_lower:
            files['staff'] = file
        elif 'enroll' in name_lower and 'sch' in name_lower:
            files['enrollment'] = file
    
    logger.info(f"Found files: {files}")
    return files


def extract_sped_data(files: dict) -> pd.DataFrame:
    """Extract and aggregate SPED data from CRDC files."""
    
    # Read staff file
    logger.info(f"Reading staff file: {files.get('staff')}")
    if not files.get('staff'):
        raise FileNotFoundError("Staff file not found. Check CRDC directory structure.")
    
    staff_df = pd.read_csv(files['staff'], dtype=str, low_memory=False)
    logger.info(f"Staff file columns: {list(staff_df.columns)[:20]}...")
    
    # Identify SPED teacher columns (may vary by CRDC version)
    sped_teacher_cols = [c for c in staff_df.columns if 'SPE' in c.upper() and 'TEACH' in c.upper()]
    total_teacher_cols = [c for c in staff_df.columns if 'TOT' in c.upper() and 'TEACH' in c.upper() and 'CERT' in c.upper()]
    
    logger.info(f"SPED teacher columns: {sped_teacher_cols}")
    logger.info(f"Total teacher columns: {total_teacher_cols}")
    
    # Read enrollment file
    logger.info(f"Reading enrollment file: {files.get('enrollment')}")
    if files.get('enrollment'):
        enroll_df = pd.read_csv(files['enrollment'], dtype=str, low_memory=False)
        logger.info(f"Enrollment file columns: {list(enroll_df.columns)[:20]}...")
        
        # Identify SPED student columns
        sped_student_cols = [c for c in enroll_df.columns if 'IDEA' in c.upper()]
        total_student_cols = [c for c in enroll_df.columns if 'TOT_ENRL' in c.upper()]
        
        logger.info(f"SPED student columns: {sped_student_cols}")
    else:
        enroll_df = None
    
    # Extract LEA ID from school-level data
    # CRDC uses COMBOKEY or separate LEAID field
    if 'LEAID' in staff_df.columns:
        lea_col = 'LEAID'
    elif 'COMBOKEY' in staff_df.columns:
        # Extract LEA ID from COMBOKEY (format: SS-LLLLLLL-SSSSS)
        staff_df['LEAID'] = staff_df['COMBOKEY'].str.split('-').str[1]
        lea_col = 'LEAID'
    else:
        raise ValueError("Cannot identify LEA ID column in CRDC data")
    
    # Convert numeric columns
    for col in sped_teacher_cols + total_teacher_cols:
        staff_df[col] = pd.to_numeric(staff_df[col], errors='coerce')
    
    # Aggregate to LEA level
    agg_dict = {}
    if sped_teacher_cols:
        agg_dict['sped_teachers_fte'] = (sped_teacher_cols[0], 'sum')
    if total_teacher_cols:
        agg_dict['total_teachers_fte'] = (total_teacher_cols[0], 'sum')
    
    # Include state and name from first row
    if 'LEA_STATE' in staff_df.columns:
        agg_dict['state'] = ('LEA_STATE', 'first')
    if 'LEA_NAME' in staff_df.columns:
        agg_dict['lea_name'] = ('LEA_NAME', 'first')
    
    lea_df = staff_df.groupby(lea_col).agg(**{
        k: v for k, v in agg_dict.items()
    }).reset_index()
    
    lea_df.rename(columns={lea_col: 'leaid'}, inplace=True)
    
    # Merge enrollment if available
    if enroll_df is not None and sped_student_cols:
        # Similar aggregation for enrollment
        for col in sped_student_cols + total_student_cols:
            enroll_df[col] = pd.to_numeric(enroll_df[col], errors='coerce')
        
        if lea_col in enroll_df.columns or 'COMBOKEY' in enroll_df.columns:
            if 'COMBOKEY' in enroll_df.columns and lea_col not in enroll_df.columns:
                enroll_df['LEAID'] = enroll_df['COMBOKEY'].str.split('-').str[1]
            
            enroll_agg = enroll_df.groupby('LEAID').agg({
                sped_student_cols[0]: 'sum',
                total_student_cols[0]: 'sum' if total_student_cols else 'count'
            }).reset_index()
            
            enroll_agg.columns = ['leaid', 'sped_students', 'total_students']
            lea_df = lea_df.merge(enroll_agg, on='leaid', how='left')
    
    # Calculate ratios
    if 'sped_teachers_fte' in lea_df.columns and 'total_teachers_fte' in lea_df.columns:
        lea_df['sped_teacher_ratio'] = lea_df['sped_teachers_fte'] / lea_df['total_teachers_fte']
    
    if 'sped_students' in lea_df.columns and 'total_students' in lea_df.columns:
        lea_df['sped_student_ratio'] = lea_df['sped_students'] / lea_df['total_students']
    
    lea_df['source_year'] = '2017-18'
    lea_df['source'] = 'CRDC'
    
    return lea_df


def main():
    """Main extraction workflow."""
    logger.info("Starting CRDC SPED data extraction...")
    
    # Find files
    files = find_crdc_files(CRDC_DIR)
    
    if not files:
        logger.error("No CRDC files found. Please download and extract CRDC 2017-18 data first.")
        logger.info(f"Expected location: {CRDC_DIR}")
        return
    
    # Extract data
    lea_df = extract_sped_data(files)
    
    # Output
    output_file = OUTPUT_DIR / "crdc_sped_by_lea_2017-18.csv"
    lea_df.to_csv(output_file, index=False)
    logger.info(f"Saved {len(lea_df)} LEA records to {output_file}")
    
    # Summary statistics
    logger.info("\n=== Summary Statistics ===")
    logger.info(f"Total LEAs: {len(lea_df)}")
    if 'sped_teacher_ratio' in lea_df.columns:
        logger.info(f"Mean SPED teacher ratio: {lea_df['sped_teacher_ratio'].mean():.1%}")
        logger.info(f"Median SPED teacher ratio: {lea_df['sped_teacher_ratio'].median():.1%}")
    if 'sped_student_ratio' in lea_df.columns:
        logger.info(f"Mean SPED student ratio: {lea_df['sped_student_ratio'].mean():.1%}")
        logger.info(f"Median SPED student ratio: {lea_df['sped_student_ratio'].median():.1%}")


if __name__ == "__main__":
    main()
```

### Step 4: Validate CRDC Extraction

After running the extraction script, verify:

```bash
# Check output
head -20 /Users/ianmmc/Development/learning-connection-time/data/processed/crdc/crdc_sped_by_lea_2017-18.csv

# Check record count (should be ~17,000+ LEAs)
wc -l /Users/ianmmc/Development/learning-connection-time/data/processed/crdc/crdc_sped_by_lea_2017-18.csv

# Check for matching LEA IDs with existing database
psql -d learning_connection_time -c "
SELECT COUNT(*) as crdc_leas,
       (SELECT COUNT(*) FROM districts) as ccd_leas
FROM (SELECT DISTINCT leaid FROM crdc_sped_temp) t;
"
```

**Expected Results:**
- ~16,000-17,000 LEA records
- SPED teacher ratio: typically 10-20% of total teachers
- SPED student ratio: typically 10-15% of total students

---

## Phase 1B: IDEA Section 618 Integration (Validation)

### Overview
IDEA Section 618 LEA-level Child Count provides authoritative SPED student counts by disability category. Use this to:
1. Validate CRDC SPED student counts
2. Enrich with disability category detail (13+ categories vs CRDC binary)
3. Provide more recent data point (2022-23 vs 2017-18)

### Step 1: Download IDEA 618 LEA Child Count Data

**Download URL (2022-23 - Most Recent):**
https://data.ed.gov/dataset/16968dd3-87bd-4e4a-92ed-50f03e6c4941/resource/0e0a1a55-57f5-4e50-b66e-1a68949e38f3/download/bchildcountdisabilitycategorylea2022-23.csv

**Data Documentation:**
https://data.ed.gov/dataset/d9624533-ca1e-43dd-bc67-ffe511ec8530/resource/3fbe9470-2858-4d6d-b801-1acfdc0ca6f7/download/b-childcount_disabilitycategory_educationalenvironmentlea_datanotes_2022-23.docx

**Commands:**
```bash
# Create directory
mkdir -p /Users/ianmmc/Development/learning-connection-time/data/raw/federal/idea-618/2022-23

# Download CSV
cd /Users/ianmmc/Development/learning-connection-time/data/raw/federal/idea-618/2022-23
curl -L -o idea_618_lea_child_count_2022-23.csv \
  "https://data.ed.gov/dataset/16968dd3-87bd-4e4a-92ed-50f03e6c4941/resource/0e0a1a55-57f5-4e50-b66e-1a68949e38f3/download/bchildcountdisabilitycategorylea2022-23.csv"

# Download documentation
curl -L -o idea_618_data_notes_2022-23.docx \
  "https://data.ed.gov/dataset/d9624533-ca1e-43dd-bc67-ffe511ec8530/resource/3fbe9470-2858-4d6d-b801-1acfdc0ca6f7/download/b-childcount_disabilitycategory_educationalenvironmentlea_datanotes_2022-23.docx"

# Check file
head -5 idea_618_lea_child_count_2022-23.csv
wc -l idea_618_lea_child_count_2022-23.csv
```

### Step 2: Understand IDEA 618 Data Structure

**Expected Columns:**
- `State Name` / `State Abbreviation`
- `LEA State ID` / `LEA NCES ID` - District identifier
- `LEA Name`
- `Disability` - Category (e.g., "Autism", "Specific Learning Disability")
- `Child Count 3-5` / `Child Count 6-21` / `Child Count Total` - Student counts by age group

**Disability Categories (13+):**
1. Autism
2. Deaf-Blindness
3. Developmental Delay
4. Emotional Disturbance
5. Hearing Impairment
6. Intellectual Disability
7. Multiple Disabilities
8. Orthopedic Impairment
9. Other Health Impairment
10. Specific Learning Disability
11. Speech or Language Impairment
12. Traumatic Brain Injury
13. Visual Impairment

### Step 3: Process IDEA 618 Data

**Create processing script:**
```bash
touch /Users/ianmmc/Development/learning-connection-time/infrastructure/scripts/extract/extract_idea_618_sped_counts.py
```

**Script content:**
```python
#!/usr/bin/env python3
"""
Extract and aggregate IDEA Section 618 LEA-level SPED child counts.
Provides validation data and disability category enrichment for CRDC.

Output: CSV with columns:
  - leaid: NCES district ID (7-digit)
  - lea_name: District name  
  - state: Two-letter state code
  - sped_students_total: Total students with disabilities
  - sped_students_3_5: Ages 3-5
  - sped_students_6_21: Ages 6-21 (school-age)
  - disability_breakdown: JSON with counts by category
  - top_disability: Most common disability category
  - source_year: "2022-23"
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
IDEA_DIR = Path("/Users/ianmmc/Development/learning-connection-time/data/raw/federal/idea-618/2022-23")
OUTPUT_DIR = Path("/Users/ianmmc/Development/learning-connection-time/data/processed/idea-618")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def process_idea_618_data(input_file: Path) -> pd.DataFrame:
    """Process IDEA 618 LEA child count data."""
    
    logger.info(f"Reading IDEA 618 data from {input_file}")
    df = pd.read_csv(input_file, dtype=str, low_memory=False)
    
    logger.info(f"Columns: {list(df.columns)}")
    logger.info(f"Total rows: {len(df)}")
    
    # Standardize column names (IDEA 618 may vary)
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower().replace(' ', '_')
        if 'nces' in col_lower and 'lea' in col_lower:
            col_mapping[col] = 'leaid'
        elif 'lea_name' in col_lower or col_lower == 'lea_name':
            col_mapping[col] = 'lea_name'
        elif 'state_abb' in col_lower or col_lower == 'state_abbreviation':
            col_mapping[col] = 'state'
        elif 'disability' in col_lower and 'category' not in col_lower:
            col_mapping[col] = 'disability'
        elif 'child_count' in col_lower and 'total' in col_lower:
            col_mapping[col] = 'count_total'
        elif 'child_count' in col_lower and '3-5' in col_lower:
            col_mapping[col] = 'count_3_5'
        elif 'child_count' in col_lower and '6-21' in col_lower:
            col_mapping[col] = 'count_6_21'
    
    df.rename(columns=col_mapping, inplace=True)
    logger.info(f"Mapped columns: {col_mapping}")
    
    # Convert counts to numeric
    for col in ['count_total', 'count_3_5', 'count_6_21']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Aggregate by LEA (data is one row per LEA × disability)
    agg_results = []
    
    for leaid, group in df.groupby('leaid'):
        record = {
            'leaid': leaid,
            'lea_name': group['lea_name'].iloc[0] if 'lea_name' in group.columns else '',
            'state': group['state'].iloc[0] if 'state' in group.columns else '',
            'sped_students_total': group['count_total'].sum() if 'count_total' in group.columns else 0,
            'sped_students_3_5': group['count_3_5'].sum() if 'count_3_5' in group.columns else 0,
            'sped_students_6_21': group['count_6_21'].sum() if 'count_6_21' in group.columns else 0,
        }
        
        # Build disability breakdown
        if 'disability' in group.columns and 'count_total' in group.columns:
            breakdown = group.groupby('disability')['count_total'].sum().to_dict()
            record['disability_breakdown'] = json.dumps(breakdown)
            
            # Identify top disability
            if breakdown:
                record['top_disability'] = max(breakdown, key=breakdown.get)
                record['top_disability_count'] = max(breakdown.values())
            else:
                record['top_disability'] = None
                record['top_disability_count'] = 0
        
        agg_results.append(record)
    
    result_df = pd.DataFrame(agg_results)
    result_df['source_year'] = '2022-23'
    result_df['source'] = 'IDEA_618'
    
    return result_df


def main():
    """Main extraction workflow."""
    logger.info("Starting IDEA 618 SPED data extraction...")
    
    input_file = IDEA_DIR / "idea_618_lea_child_count_2022-23.csv"
    
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        logger.info("Please download IDEA 618 data first. See handoff document for URL.")
        return
    
    result_df = process_idea_618_data(input_file)
    
    # Output
    output_file = OUTPUT_DIR / "idea_618_sped_by_lea_2022-23.csv"
    result_df.to_csv(output_file, index=False)
    logger.info(f"Saved {len(result_df)} LEA records to {output_file}")
    
    # Summary
    logger.info("\n=== Summary Statistics ===")
    logger.info(f"Total LEAs: {len(result_df)}")
    logger.info(f"Total SPED students: {result_df['sped_students_total'].sum():,.0f}")
    logger.info(f"Mean SPED per LEA: {result_df['sped_students_total'].mean():,.1f}")
    logger.info(f"Median SPED per LEA: {result_df['sped_students_total'].median():,.1f}")
    
    if 'top_disability' in result_df.columns:
        top_disabilities = result_df['top_disability'].value_counts().head(5)
        logger.info(f"\nTop disability categories (by LEA count):\n{top_disabilities}")


if __name__ == "__main__":
    main()
```

### Step 4: Cross-Validate CRDC vs IDEA 618

**Create validation script:**
```bash
touch /Users/ianmmc/Development/learning-connection-time/infrastructure/scripts/analyze/validate_sped_sources.py
```

**Script content:**
```python
#!/usr/bin/env python3
"""
Cross-validate SPED student counts between CRDC (2017-18) and IDEA 618 (2022-23).
Identifies discrepancies and generates confidence scores for data quality.

Output:
  - Validation report with match statistics
  - Merged dataset with both sources and confidence flags
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROCESSED_DIR = Path("/Users/ianmmc/Development/learning-connection-time/data/processed")

def validate_sped_sources():
    """Compare CRDC and IDEA 618 SPED counts."""
    
    crdc_file = PROCESSED_DIR / "crdc" / "crdc_sped_by_lea_2017-18.csv"
    idea_file = PROCESSED_DIR / "idea-618" / "idea_618_sped_by_lea_2022-23.csv"
    
    if not crdc_file.exists():
        logger.error(f"CRDC file not found: {crdc_file}")
        return
    if not idea_file.exists():
        logger.error(f"IDEA 618 file not found: {idea_file}")
        return
    
    crdc_df = pd.read_csv(crdc_file, dtype={'leaid': str})
    idea_df = pd.read_csv(idea_file, dtype={'leaid': str})
    
    logger.info(f"CRDC LEAs: {len(crdc_df)}")
    logger.info(f"IDEA 618 LEAs: {len(idea_df)}")
    
    # Standardize LEA IDs (ensure 7-digit format)
    crdc_df['leaid'] = crdc_df['leaid'].str.zfill(7)
    idea_df['leaid'] = idea_df['leaid'].str.zfill(7)
    
    # Merge
    merged = crdc_df.merge(
        idea_df[['leaid', 'sped_students_total', 'sped_students_6_21']],
        on='leaid',
        how='outer',
        suffixes=('_crdc', '_idea')
    )
    
    logger.info(f"Merged LEAs: {len(merged)}")
    
    # Calculate match statistics
    both_sources = merged.dropna(subset=['sped_students', 'sped_students_total'])
    logger.info(f"LEAs with both sources: {len(both_sources)}")
    
    if len(both_sources) > 0:
        # Compare counts (note: 5-year gap, so expect some drift)
        both_sources['diff_pct'] = (
            (both_sources['sped_students_total'] - both_sources['sped_students']) / 
            both_sources['sped_students']
        ) * 100
        
        logger.info("\n=== Validation Results ===")
        logger.info(f"Mean difference: {both_sources['diff_pct'].mean():.1f}%")
        logger.info(f"Median difference: {both_sources['diff_pct'].median():.1f}%")
        logger.info(f"Within ±10%: {(both_sources['diff_pct'].abs() <= 10).mean():.1%}")
        logger.info(f"Within ±25%: {(both_sources['diff_pct'].abs() <= 25).mean():.1%}")
        logger.info(f"Within ±50%: {(both_sources['diff_pct'].abs() <= 50).mean():.1%}")
        
        # Flag outliers
        merged['validation_flag'] = 'ok'
        merged.loc[merged['diff_pct'].abs() > 50, 'validation_flag'] = 'review_needed'
        merged.loc[merged['sped_students'].isna(), 'validation_flag'] = 'crdc_only'
        merged.loc[merged['sped_students_total'].isna(), 'validation_flag'] = 'idea_only'
    
    # Output
    output_file = PROCESSED_DIR / "sped_validation_merged.csv"
    merged.to_csv(output_file, index=False)
    logger.info(f"\nSaved merged data to {output_file}")
    
    # Generate report
    report_file = PROCESSED_DIR / "sped_validation_report.txt"
    with open(report_file, 'w') as f:
        f.write("SPED Data Source Validation Report\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"CRDC 2017-18 LEAs: {len(crdc_df)}\n")
        f.write(f"IDEA 618 2022-23 LEAs: {len(idea_df)}\n")
        f.write(f"Matched LEAs: {len(both_sources)}\n\n")
        f.write("Validation Flags:\n")
        f.write(merged['validation_flag'].value_counts().to_string())
    
    logger.info(f"Saved report to {report_file}")


if __name__ == "__main__":
    validate_sped_sources()
```

---

## Phase 1C: LCT SPED Segmentation Calculations

### Overview
With CRDC SPED teacher ratios and validated SPED student counts, calculate segmented LCT:
- `lct_teachers_gened`: LCT using only GenEd teachers for GenEd students
- `lct_teachers_sped`: LCT using only SPED teachers for SPED students

### Step 1: Database Schema Modifications

**Add new table for SPED data:**
```sql
-- Run in psql -d learning_connection_time

-- SPED staffing and enrollment from CRDC/IDEA 618
CREATE TABLE IF NOT EXISTS sped_data (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(7) NOT NULL REFERENCES districts(nces_id),
    
    -- From CRDC
    crdc_year VARCHAR(10),
    sped_teachers_fte DECIMAL(10,2),
    total_teachers_fte DECIMAL(10,2),
    sped_teacher_ratio DECIMAL(5,4),
    sped_students_crdc INTEGER,
    total_students_crdc INTEGER,
    sped_student_ratio_crdc DECIMAL(5,4),
    
    -- From IDEA 618
    idea_year VARCHAR(10),
    sped_students_idea INTEGER,
    sped_students_6_21 INTEGER,
    top_disability VARCHAR(100),
    disability_breakdown JSONB,
    
    -- Validation
    validation_flag VARCHAR(50),
    diff_pct DECIMAL(8,2),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(district_id)
);

-- Index for queries
CREATE INDEX IF NOT EXISTS idx_sped_data_district ON sped_data(district_id);
CREATE INDEX IF NOT EXISTS idx_sped_data_validation ON sped_data(validation_flag);

-- Add SPED LCT columns to lct_calculations table
ALTER TABLE lct_calculations 
ADD COLUMN IF NOT EXISTS lct_teachers_gened DECIMAL(10,2),
ADD COLUMN IF NOT EXISTS lct_teachers_sped DECIMAL(10,2),
ADD COLUMN IF NOT EXISTS sped_data_source VARCHAR(50),
ADD COLUMN IF NOT EXISTS sped_data_year VARCHAR(10);
```

### Step 2: Import SPED Data to Database

**Create import script:**
```bash
touch /Users/ianmmc/Development/learning-connection-time/infrastructure/database/migrations/import_sped_data.py
```

**Script content:**
```python
#!/usr/bin/env python3
"""
Import SPED data from CRDC and IDEA 618 into PostgreSQL database.
"""

import pandas as pd
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from infrastructure.database.connection import session_scope, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROCESSED_DIR = Path("/Users/ianmmc/Development/learning-connection-time/data/processed")


def import_sped_data():
    """Import merged SPED validation data to database."""
    
    merged_file = PROCESSED_DIR / "sped_validation_merged.csv"
    
    if not merged_file.exists():
        logger.error(f"Merged SPED file not found: {merged_file}")
        logger.info("Run validate_sped_sources.py first.")
        return
    
    df = pd.read_csv(merged_file, dtype={'leaid': str})
    df['leaid'] = df['leaid'].str.zfill(7)
    
    logger.info(f"Importing {len(df)} SPED records...")
    
    with session_scope() as session:
        # Clear existing data
        session.execute(text("TRUNCATE TABLE sped_data CASCADE"))
        
        imported = 0
        skipped = 0
        
        for _, row in df.iterrows():
            # Check if district exists
            result = session.execute(
                text("SELECT nces_id FROM districts WHERE nces_id = :id"),
                {'id': row['leaid']}
            ).fetchone()
            
            if not result:
                skipped += 1
                continue
            
            session.execute(text("""
                INSERT INTO sped_data (
                    district_id,
                    crdc_year, sped_teachers_fte, total_teachers_fte, sped_teacher_ratio,
                    sped_students_crdc, total_students_crdc, sped_student_ratio_crdc,
                    idea_year, sped_students_idea, sped_students_6_21,
                    top_disability, validation_flag, diff_pct
                ) VALUES (
                    :district_id,
                    :crdc_year, :sped_teachers_fte, :total_teachers_fte, :sped_teacher_ratio,
                    :sped_students_crdc, :total_students_crdc, :sped_student_ratio_crdc,
                    :idea_year, :sped_students_idea, :sped_students_6_21,
                    :top_disability, :validation_flag, :diff_pct
                )
                ON CONFLICT (district_id) DO UPDATE SET
                    sped_teachers_fte = EXCLUDED.sped_teachers_fte,
                    sped_teacher_ratio = EXCLUDED.sped_teacher_ratio,
                    sped_students_idea = EXCLUDED.sped_students_idea,
                    validation_flag = EXCLUDED.validation_flag,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                'district_id': row['leaid'],
                'crdc_year': '2017-18',
                'sped_teachers_fte': row.get('sped_teachers_fte'),
                'total_teachers_fte': row.get('total_teachers_fte'),
                'sped_teacher_ratio': row.get('sped_teacher_ratio'),
                'sped_students_crdc': row.get('sped_students'),
                'total_students_crdc': row.get('total_students'),
                'sped_student_ratio_crdc': row.get('sped_student_ratio'),
                'idea_year': '2022-23',
                'sped_students_idea': row.get('sped_students_total'),
                'sped_students_6_21': row.get('sped_students_6_21'),
                'top_disability': row.get('top_disability'),
                'validation_flag': row.get('validation_flag'),
                'diff_pct': row.get('diff_pct')
            })
            imported += 1
        
        session.commit()
        logger.info(f"Imported: {imported}, Skipped (no matching district): {skipped}")


if __name__ == "__main__":
    import_sped_data()
```

### Step 3: Calculate Segmented LCT

**Update LCT calculation script to include SPED variants:**

Add to `infrastructure/scripts/analyze/calculate_lct_variants.py`:

```python
def calculate_sped_segmented_lct(session, district_id: str, instructional_minutes: int) -> dict:
    """
    Calculate GenEd and SPED segmented LCT using CRDC teacher ratios.
    
    Methodology:
    1. Get SPED teacher ratio from CRDC (sped_teachers / total_teachers)
    2. Apply ratio to current CCD teacher count to estimate current SPED teachers
    3. Get SPED student ratio from CRDC or IDEA 618
    4. Calculate separate LCT for GenEd and SPED populations
    
    Returns dict with:
        - lct_teachers_gened: LCT for GenEd (teachers - SPED teachers) / (enrollment - SPED students)
        - lct_teachers_sped: LCT for SPED teachers / SPED students
        - sped_data_source: 'crdc' or 'idea_618' or 'mixed'
    """
    from sqlalchemy import text
    
    # Get current CCD data
    ccd_data = session.execute(text("""
        SELECT d.enrollment, d.teachers_k12, d.enrollment_k12
        FROM districts d
        WHERE d.nces_id = :id
    """), {'id': district_id}).fetchone()
    
    if not ccd_data:
        return None
    
    enrollment = ccd_data.enrollment_k12 or ccd_data.enrollment
    total_teachers = ccd_data.teachers_k12
    
    if not enrollment or not total_teachers:
        return None
    
    # Get SPED data
    sped_data = session.execute(text("""
        SELECT sped_teacher_ratio, sped_student_ratio_crdc,
               sped_students_idea, sped_students_6_21,
               validation_flag
        FROM sped_data
        WHERE district_id = :id
    """), {'id': district_id}).fetchone()
    
    if not sped_data or not sped_data.sped_teacher_ratio:
        return None
    
    # Calculate SPED teachers using CRDC ratio applied to current CCD teachers
    sped_teachers = total_teachers * float(sped_data.sped_teacher_ratio)
    gened_teachers = total_teachers - sped_teachers
    
    # Determine SPED students (prefer IDEA 618 school-age if available)
    if sped_data.sped_students_6_21:
        sped_students = sped_data.sped_students_6_21
        sped_source = 'idea_618'
    elif sped_data.sped_student_ratio_crdc:
        sped_students = enrollment * float(sped_data.sped_student_ratio_crdc)
        sped_source = 'crdc'
    else:
        return None
    
    gened_students = enrollment - sped_students
    
    # Validate
    if gened_students <= 0 or sped_students <= 0:
        return None
    if gened_teachers <= 0 or sped_teachers <= 0:
        return None
    
    # Calculate segmented LCT
    lct_gened = (instructional_minutes * gened_teachers) / gened_students
    lct_sped = (instructional_minutes * sped_teachers) / sped_students
    
    return {
        'lct_teachers_gened': round(lct_gened, 2),
        'lct_teachers_sped': round(lct_sped, 2),
        'sped_data_source': sped_source,
        'sped_data_year': '2017-18/2022-23',
        'gened_teachers': round(gened_teachers, 2),
        'sped_teachers': round(sped_teachers, 2),
        'gened_students': int(gened_students),
        'sped_students': int(sped_students),
        'validation_flag': sped_data.validation_flag
    }
```

---

## Phase 2: Equity Context Integration (Roadmap)

### 2A: CCD F-33 Finance Data

**Purpose:** Correlate LCT with per-pupil expenditure to test if higher spending → more teacher time.

**Download URL:**
https://nces.ed.gov/ccd/files.asp#Fiscal:1,LevelId:5,Page:1

Or via Census Bureau:
https://www.census.gov/programs-surveys/school-finances/data/tables.html

**Key Variables:**
- `TOTALREV` - Total revenue
- `TOTALEXP` - Total expenditure
- `TCURINST` - Current instructional expenditure
- `TCURSSVC` - Current student support expenditure
- `PPITOTAL` - Per-pupil instructional expenditure
- `V33` - Total membership (for validation)

**Processing Steps:**
```bash
# 1. Download F-33 data (typically named f33_[year].zip)
mkdir -p /Users/ianmmc/Development/learning-connection-time/data/raw/federal/nces-f33/2022-23
cd /Users/ianmmc/Development/learning-connection-time/data/raw/federal/nces-f33/2022-23
curl -L -o f33_2022-23.zip "https://nces.ed.gov/ccd/data/zip/f33_2022_23.zip"
unzip f33_2022-23.zip

# 2. Create extraction script
touch /Users/ianmmc/Development/learning-connection-time/infrastructure/scripts/extract/extract_f33_finance.py

# 3. Database table
psql -d learning_connection_time -c "
CREATE TABLE IF NOT EXISTS finance_data (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(7) NOT NULL REFERENCES districts(nces_id),
    year VARCHAR(10) NOT NULL,
    total_revenue DECIMAL(15,2),
    total_expenditure DECIMAL(15,2),
    instructional_expenditure DECIMAL(15,2),
    support_expenditure DECIMAL(15,2),
    per_pupil_instructional DECIMAL(10,2),
    per_pupil_total DECIMAL(10,2),
    source VARCHAR(50) DEFAULT 'nces_f33',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(district_id, year)
);
"
```

### 2B: EDGE Poverty Estimates

**Purpose:** Analyze if high-poverty schools have systematically lower LCT (equity analysis).

**Download URL:**
https://nces.ed.gov/programs/edge/Economic/NeighborhoodPoverty

**Key Variables:**
- School-level income-to-poverty ratio (IPR)
- Aggregated to LEA level

**Processing Steps:**
```bash
# 1. Download EDGE Poverty data
mkdir -p /Users/ianmmc/Development/learning-connection-time/data/raw/federal/edge/poverty
# Download from NCES EDGE portal (requires manual navigation or API)

# 2. Database table
psql -d learning_connection_time -c "
CREATE TABLE IF NOT EXISTS poverty_data (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(7) NOT NULL REFERENCES districts(nces_id),
    year VARCHAR(10) NOT NULL,
    mean_ipr DECIMAL(5,2),  -- Income-to-poverty ratio
    pct_below_poverty DECIMAL(5,2),
    pct_low_income DECIMAL(5,2),  -- Below 200% poverty
    school_count INTEGER,
    source VARCHAR(50) DEFAULT 'edge_poverty',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(district_id, year)
);
"
```

### 2C: EDGE ACS-ED Demographic Tables

**Purpose:** Socioeconomic context for LCT variations (parent education, employment, household composition).

**Download URL:**
https://nces.ed.gov/programs/edge/Demographic/ACS

**Key Variables:**
- Parent educational attainment
- Household employment status
- Single-parent households
- Language spoken at home

---

## Documentation Updates for Claude Code

### Update 1: Claude.md

Add the following section after "### Known Limitations":

```markdown
### SPED Segmentation (Phase 2 Enhancement)

**Status:** Implementation in progress (January 2026)

**Goal:** Segment LCT calculations into GenEd vs SPED populations for more accurate equity analysis.

**Data Sources:**
- **CRDC 2017-18**: SPED teacher counts at school level (aggregated to LEA)
- **IDEA Section 618 2022-23**: SPED student counts at LEA level

**New LCT Variants:**
- `lct_teachers_gened`: (Minutes × GenEd Teachers) / GenEd Students
- `lct_teachers_sped`: (Minutes × SPED Teachers) / SPED Students

**Key Scripts:**
- `infrastructure/scripts/extract/extract_crdc_sped_data.py`
- `infrastructure/scripts/extract/extract_idea_618_sped_counts.py`
- `infrastructure/scripts/analyze/validate_sped_sources.py`
- `infrastructure/database/migrations/import_sped_data.py`

**Database Tables:**
- `sped_data`: CRDC/IDEA 618 SPED teacher and student data

**Critical Note:** CCD does NOT contain SPED enrollment data. The NCES CCD Membership file only breaks down by Grade × Race/Ethnicity × Sex—no disability dimension exists.
```

### Update 2: METHODOLOGY.md

Add new section after "### LCT Variants (Multiple Staffing Scopes)":

```markdown
### SPED/GenEd Segmented LCT

**Rationale:** Standard LCT calculations include all teachers in the numerator, but SPED teachers serve a specialized population with legally mandated lower ratios. This inflates apparent GenEd LCT.

**Segmentation Formula:**

```
LCT_GenEd = (Minutes × GenEd_Teachers) / GenEd_Students
LCT_SPED = (Minutes × SPED_Teachers) / SPED_Students

Where:
  GenEd_Teachers = Total_Teachers × (1 - SPED_Teacher_Ratio)
  SPED_Teachers = Total_Teachers × SPED_Teacher_Ratio
  SPED_Teacher_Ratio = from CRDC 2017-18 (only federal source with district-level data)
  
  GenEd_Students = Total_Enrollment - SPED_Students
  SPED_Students = from IDEA 618 2022-23 (most recent LEA-level data)
```

**Data Source Limitations:**

| Data Element | Source | Year | Limitation |
|--------------|--------|------|------------|
| SPED Teacher Count | CRDC | 2017-18 | 7-year temporal gap; biennial collection |
| SPED Student Count | IDEA 618 | 2022-23 | 2-year gap with CCD 2023-24 |
| Total Teachers | CCD | 2023-24 | Current; no SPED breakdown |
| Total Enrollment | CCD | 2023-24 | Current; no SPED breakdown |

**Methodology Decision:** Apply CRDC 2017-18 SPED teacher *ratio* to current CCD teacher counts, rather than using raw CRDC counts. This assumes the proportion of SPED teachers is more stable than absolute counts.

**Validation:** Cross-check CRDC SPED student counts against IDEA 618 counts. Flag districts with >50% discrepancy for manual review.

**GAO Finding (GAO-24-106264):** Federal data gaps prevent comprehensive counting of special education personnel at district level. IDEA 618 personnel data is state-level only.
```

### Update 3: TERMINOLOGY.md

Add new section:

```markdown
## SPED Segmentation Terms

### SPED (Special Education)
**Definition:** Educational services for students with disabilities as defined under IDEA (Individuals with Disabilities Education Act).

### GenEd (General Education)  
**Definition:** Standard classroom instruction for students without IEPs (Individualized Education Programs).

### SPED Teacher Ratio
**Definition:** Proportion of total teachers who are SPED-certified, from CRDC data.
**Formula:** SPED_Teachers_FTE / Total_Teachers_FTE
**Typical Range:** 10-20%

### SPED Student Ratio
**Definition:** Proportion of total enrollment receiving SPED services.
**Formula:** SPED_Students / Total_Enrollment
**Typical Range:** 10-15%

### CRDC (Civil Rights Data Collection)
**Definition:** Biennial federal survey collecting school-level data on civil rights indicators, including SPED staffing and enrollment.
**Publisher:** U.S. Department of Education, Office for Civil Rights

### IDEA Section 618
**Definition:** Federal reporting requirement for states to submit data on children with disabilities.
**Includes:** Child counts by disability category, educational environments, personnel (state-level only)
**Publisher:** U.S. Department of Education, Office of Special Education Programs (OSEP)
```

### Update 4: PROJECT_CONTEXT.md

Add to "Evolution Strategy" section:

```markdown
### Phase 1.6: SPED/GenEd Segmentation (Current - January 2026)
- Integrate CRDC 2017-18 for SPED teacher ratios
- Integrate IDEA 618 2022-23 for validated SPED student counts
- Calculate segmented LCT: GenEd vs SPED populations
- Validate proportional approach against absolute counts
- Document data source temporal gaps and limitations
```

---

## Execution Checklist for Claude Code

### Phase 1A: CRDC Integration
- [ ] Create directory: `data/raw/federal/crdc/2017-18/`
- [ ] Download CRDC 2017-18 data (~118 MB)
- [ ] Extract and identify relevant files (staff, enrollment)
- [ ] Create script: `extract_crdc_sped_data.py`
- [ ] Run extraction, validate output
- [ ] Create directory: `data/processed/crdc/`
- [ ] Output: `crdc_sped_by_lea_2017-18.csv`

### Phase 1B: IDEA 618 Integration  
- [ ] Create directory: `data/raw/federal/idea-618/2022-23/`
- [ ] Download IDEA 618 LEA Child Count 2022-23
- [ ] Create script: `extract_idea_618_sped_counts.py`
- [ ] Run extraction, validate output
- [ ] Create directory: `data/processed/idea-618/`
- [ ] Output: `idea_618_sped_by_lea_2022-23.csv`

### Validation
- [ ] Create script: `validate_sped_sources.py`
- [ ] Run cross-validation
- [ ] Review discrepancy report
- [ ] Output: `sped_validation_merged.csv`, `sped_validation_report.txt`

### Database Integration
- [ ] Run schema SQL to create `sped_data` table
- [ ] Create script: `import_sped_data.py`
- [ ] Run import
- [ ] Verify: `SELECT COUNT(*) FROM sped_data;`

### LCT Calculation Updates
- [ ] Add `calculate_sped_segmented_lct()` function
- [ ] Update `calculate_lct_variants.py` to include SPED variants
- [ ] Run full calculation
- [ ] Verify new columns in output

### Documentation
- [ ] Update Claude.md with SPED section
- [ ] Update METHODOLOGY.md with segmentation methodology
- [ ] Update TERMINOLOGY.md with SPED terms
- [ ] Update PROJECT_CONTEXT.md with Phase 1.6

---

## Success Criteria

1. **CRDC Data Loaded:** >15,000 LEAs with SPED teacher ratios
2. **IDEA 618 Data Loaded:** >15,000 LEAs with SPED student counts
3. **Validation Complete:** <10% of districts flagged for review
4. **Database Populated:** `sped_data` table with matched records
5. **LCT Calculations:** New `lct_teachers_gened` and `lct_teachers_sped` columns populated
6. **Documentation Updated:** All four docs reflect SPED segmentation status

---

## Known Issues and Workarounds

### Issue 1: CRDC File Structure Variations
CRDC data organization may differ from expected patterns. If files are not found:
1. List all files in extracted directory
2. Look for patterns: `*2017*`, `*school*`, `*staff*`
3. Check for nested directories
4. Review CRDC data documentation on ed.gov/ocr

### Issue 2: LEA ID Format Mismatches
CRDC and CCD may use different ID formats:
- CCD: 7-digit NCES ID (e.g., "0100005")
- CRDC: May include state prefix or different padding
- Solution: Normalize all IDs to 7-digit zero-padded format

### Issue 3: Missing SPED Data for Some Districts
Not all districts appear in both CRDC and IDEA 618:
- Small districts may be exempt from CRDC
- New districts may not have historical data
- Solution: Flag as `crdc_only`, `idea_only`, or `no_sped_data`

---

**Document Version:** 1.0  
**Created By:** Opus session analyzing federal SPED data sources  
**For:** Claude Code (Sonnet) implementation  
**Next Session:** Execute Phase 1A (CRDC download and processing)
