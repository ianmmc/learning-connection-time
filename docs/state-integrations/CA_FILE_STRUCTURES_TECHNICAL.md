# California CDE Data File Structures - Technical Documentation

**Date:** January 9, 2026
**Purpose:** Complete field-level documentation for California state data integration
**Status:** Verified via direct file inspection

---

## Overview

This document provides exact file structure specifications for California Department of Education (CDE) data files, obtained through direct inspection of actual data files rather than documentation pages (many of which return 404 errors).

**Files Analyzed:**
- Special Education Enrollment by Educational Environment (2023-24)
- Public Districts Directory (current)
- Staff Assignment Data (2018-19, most recent available)
- Assignment Codes Reference (2012+)
- Free or Reduced-Price Meal Data (2023-24)

---

## 1. Special Education Enrollment by Educational Environment

**Source:** https://www3.cde.ca.gov/demo-downloads/sped/spedpsYYYY.txt
**File Format:** Tab-delimited text (TXT)
**File Size:** 11-13MB per year
**Years Available:** 2022-23, 2023-24, 2024-25
**Records:** ~115,000 total (59,935 district-level in 2023-24)
**Encoding:** UTF-8

### Field Structure (23 columns)

| # | Field Name | Data Type | Description |
|---|------------|-----------|-------------|
| 1 | Academic Year | String | Format: "YYYY-YY" (e.g., "2023-24") |
| 2 | Aggregate Level | String(1) | T=State, C=County, D=District, A=DSEA, S=School |
| 3 | County Code | String(2) | 2-digit county code (01-58) |
| 4 | District Code | String(5) | 5-digit district code within county |
| 5 | School Code | String(7) | 7-digit school code (full CDS code) |
| 6 | County Name | String | County name |
| 7 | District Name | String | District name |
| 8 | School Name | String | School name (blank for district-level) |
| 9 | Charter School | String | "All", "Y" (charter only), or "N" (non-charter) |
| 10 | ReportingCategory | String | Demographics code (see below) |
| 11 | SPED_ENR_N | Integer | Total SPED enrollment with active IEPs |
| 12 | PS_RCGT80_N | Integer | **Mainstreamed**: Regular class 80%+ of day |
| 13 | PS_RC4079_N | Integer | **Mainstreamed**: Regular class 40-79% of day |
| 14 | PS_RCL40_N | Integer | **Self-Contained**: Regular class <40% of day |
| 15 | PS_SSOS_N | Integer | **Self-Contained**: Separate school & other settings |
| 16 | PS_PSS_N | Integer | **Preschool**: Early childhood settings (Ages 3-5) |
| 17 | PS_MUK_N | Integer | Missing/unreported educational environment |
| 18 | PS_RCGT80_% | Decimal | Percentage for PS_RCGT80_N |
| 19 | PS_RC4079_% | Decimal | Percentage for PS_RC4079_N |
| 20 | PS_RCL40_% | Decimal | Percentage for PS_RCL40_N |
| 21 | PS_SSOS_% | Decimal | Percentage for PS_SSOS_N |
| 22 | PS_PSS_% | Decimal | Percentage for PS_PSS_N |
| 23 | PS_MUK_% | Decimal | Percentage for PS_MUK_N |

### ReportingCategory Values

**Reporting categories represent disaggregation dimensions:**

**Age Ranges:**
- `AR_35` - Ages 3-5 (preschool)
- `AR_612` - Ages 6-12 (elementary/middle)
- `AR_1318` - Ages 13-18 (high school)
- `AR_19P` - Ages 19+ (adult transition)

**Disability Categories (DC_):**
- `DC_AUT` - Autism
- `DC_DB` - Deaf-Blindness
- `DC_DFHI` - Deaf/Hearing Impairment
- `DC_ED` - Emotional Disturbance
- `DC_EMD` - Established Medical Disability
- `DC_HH` - Hard of Hearing
- `DC_ID` - Intellectual Disability
- `DC_MD` - Multiple Disabilities
- `DC_OHI` - Other Health Impairment
- `DC_OI` - Orthopedic Impairment
- `DC_SLD` - Specific Learning Disability
- `DC_SLI` - Speech/Language Impairment
- `DC_TBI` - Traumatic Brain Injury
- `DC_VI` - Visual Impairment

**Race/Ethnicity (R_):**
- `RB` - African American
- `RI` - American Indian/Alaska Native
- `RA` - Asian
- `RF` - Filipino
- `RH` - Hispanic/Latino
- `RW` - White
- `RP` - Pacific Islander
- `RT` - Two or More Races
- `RD` - Not Reported

**Grade Spans:**
- `PS-3` - PreSchool through Grade 3
- `4-6` - Grades 4-6
- `7-8` - Grades 7-8
- `9-12` - Grades 9-12

**Gender:**
- `GF` - Female
- `GM` - Male
- `GX` - Non-Binary
- `GZ` - Missing

**English Learner:**
- `EL_Y` - English Learner
- `EL_N` - Not English Learner

**Total Category:**
- `Total` - Aggregate across all demographics

### Data Privacy

**Suppression Rules:**
- Cells with ≤10 students are suppressed at school level
- District-level data includes all students (aggregated)
- School-level demographic breakdowns unavailable (totals only)

### Usage for LCT Calculations

**Key Calculation:**
```python
# Self-contained SPED enrollment (exclude preschool)
self_contained = PS_RCL40_N + PS_SSOS_N

# Mainstreamed SPED enrollment
mainstreamed = PS_RCGT80_N + PS_RC4079_N

# Self-contained proportion
proportion = self_contained / SPED_ENR_N
```

**Filter to District-Level Data:**
```python
district_data = df[
    (df['Aggregate Level'] == 'D') &
    (df['ReportingCategory'] == 'Total')
]
```

---

## 2. Public Districts Directory

**Source:** https://www.cde.ca.gov/SchoolDirectory/report?rid=dl2&tp=txt
**File Format:** Tab-delimited text (TXT)
**File Size:** ~258KB
**Records:** 1,070 districts
**Update Frequency:** Real-time (dynamically generated)
**Encoding:** UTF-8

### Field Structure (22 columns)

| # | Field Name | Data Type | Description | Sample Value |
|---|------------|-----------|-------------|--------------|
| 1 | CD Code | String(7) | **CDS District Code** (CCCDDDD format) | 0110017 |
| 2 | County | String | County name | Alameda |
| 3 | District | String | District name | Alameda County Office of Education |
| 4 | Street | String | Physical street address | 313 West Winton Avenue |
| 5 | City | String | City | Hayward |
| 6 | Zip | String(10) | ZIP code with extension | 94544-1136 |
| 7 | State | String(2) | State code (always "CA") | CA |
| 8 | MailStreet | String | Mailing street address | (same or different) |
| 9 | MailCity | String | Mailing city | |
| 10 | MailZip | String(10) | Mailing ZIP code | |
| 11 | MailState | String(2) | Mailing state | |
| 12 | Phone | String(14) | Phone number with area code | (510) 887-0152 |
| 13 | Ext | String(6) | Phone extension | No Data |
| 14 | FaxNumber | String(14) | Fax number | No Data |
| 15 | AdmFName | String(20) | Administrator first name | Alysse |
| 16 | AdmLName | String(40) | Administrator last name | Castro |
| 17 | Latitude | Decimal(10) | GPS latitude | 37.658212 |
| 18 | Longitude | Decimal(10) | GPS longitude | -122.09713 |
| 19 | DOC | String(2) | District Ownership Code | 00 |
| 20 | DOCType | String | District type description | County Office of Education (COE) |
| 21 | StatusType | String | Active, Closed, Merged, or Pending | Active |
| 22 | LastUpDate | Date(10) | Last updated date (MM/DD/YYYY) | 03/08/2023 |

### District Types (DOCType)

| DOCType | Count | Description |
|---------|-------|-------------|
| Elementary School District | 515 | K-8 or K-6 districts |
| Unified School District | 345 | K-12 districts |
| High School District | 76 | 9-12 districts |
| Regional Occupation Center/Program (ROC/P) | 59 | Career technical education |
| County Office of Education (COE) | 58 | County-level agencies |
| State Board of Education | 14 | State-managed programs |
| State Special Schools | 3 | CA School for Blind/Deaf |

### CDS Code Format

**Structure:** `CCCDDDD` (7 digits)
- `CC` - 2-digit county code (01-58)
- `DDDDD` - 5-digit district code within county

**Example:** `0110017`
- County: 01 (Alameda)
- District: 10017 (Alameda County Office of Education)

**Crosswalk to NCES:**
NCES CCD file field `ST_LEAID` = `"CA-" + CDS_Code`
- Example: `ST_LEAID = "CA-0110017"` → `CDS Code = "0110017"`

---

## 3. Staff Assignment Data

**Source:** https://www3.cde.ca.gov/download/dq/StaffAssignYY.zip
**File Format:** ZIP archive containing TXT (tab-delimited)
**File Size:** ~25MB compressed, ~191MB uncompressed
**Years Available:** 2012-13 through 2018-19 (historical only)
**Records:** ~1.27 million (2018-19)
**Encoding:** Latin-1 (not UTF-8)
**Status:** ⚠️ **Outdated** - Last release 2018-19, no updates since

### Field Structure (13 columns)

| # | Field Name | Data Type | Description | Sample Value |
|---|------------|-----------|-------------|--------------|
| 1 | AcademicYear | String(4) | School year YYZZ format | 1819 |
| 2 | RecID | String | Record identifier | 1321406 |
| 3 | DistrictCode | String(7) | **CDS District Code** | 5673940 |
| 4 | Schoolcode | String(7) | CDS School Code | 6102230 |
| 5 | CountyName | String | County name (padded) | "VENTURA        " |
| 6 | DistrictName | String | District name | Moorpark Unified |
| 7 | SchoolName | String | School name | Chaparral Middle |
| 8 | StaffType | String(1) | T=Teacher, P=Pupil Services, A=Admin | T |
| 9 | AssignmentCode | String(4) | Assignment/subject code (see codes) | 0400 |
| 10 | ClassID | String | Class identifier | 03-01-Gym |
| 11 | CourseCode | String(4) | Course code (curriculum) | 2517 |
| 12 | EstimatedFTE | Decimal | Estimated Full-Time Equivalent | 17.14 |
| 13 | FileCreated | Date | File creation date (MM/DD/YYYY) | 08/22/2019 |

### StaffType Values

| Code | Description | Count (in sample) |
|------|-------------|-------------------|
| T | Teacher (instructional staff) | Majority |
| P | Pupil Services (counselors, psychologists, etc.) | Moderate |
| A | Administration | Lower |

### Assignment Codes

**⚠️ CRITICAL LIMITATION:** Assignment codes do **NOT explicitly identify special education teachers**. SPED teacher designation must be inferred indirectly or is not available in this dataset.

**SPED-Related Codes Found (23 codes):**

**Administrative (Type A):**
- `0124` - Admin special education

**Pupil Services (Type P):**
- `0212` - Special ed audiology
- `0213` - Special ed physical therapy
- `0214` - Special ed vision therapy
- `0216` - Special ed psychologist
- `0217` - Special ed parent counseling/training
- `0219` - Special ed social worker
- `0221` - Special ed diagnostic staff
- `0222` - Special ed work study coordinator
- `0223` - Special ed occupational therapist
- `0224` - Special ed program specialist
- `0225` - Special ed mobility instruction
- `0228` - Special ed other noninstructional staff

**Teaching (Type T):**
- `2516` - Modified or Specially Designed Physical Education
- `6004` - Resource Class (not special education) ⚠️

**Note:** Most SPED-related codes are **Pupil Services (P)** or **Administrative (A)**, not teaching positions (T). Regular teaching assignments (Type T) do not distinguish between GenEd and SPED teachers in most cases.

### Assignment Codes Reference

**Source:** http://www3.cde.ca.gov/download/dq/AssignmentCodes12On.xlsx
**File Format:** Excel (XLSX), 79KB
**Total Codes:** 1,150

**Fields:**
- `AssignmentCode` - 4-digit code
- `AssignmentName` - Descriptive name
- `AssignmentType` - A (Admin), P (Pupil Services), T (Teaching)
- `AssignmentSubject` - Subject area category
- `AP Course` - Y/N indicator
- `IB Course` - Y/N indicator
- `CTE Course` - Y/N indicator
- `MeetsUC/CSU Requirements` - Y/N indicator
- `EffectiveStartDate` - Code effective date
- `EffectiveEndDate` - Code end date (null if current)
- `FileCreated` - File creation timestamp

**Distribution by Type:**
- Teaching (T): 1,062 codes
- Administration (A): 63 codes
- Pupil Services (P): 25 codes

### Usage Recommendation

**For LCT Calculations:** ⚠️ **Defer staffing integration until current data available**

**Reasons:**
1. **Outdated:** Last release 2018-19 (6+ years old)
2. **SPED Teachers Not Identified:** Cannot distinguish SPED teachers from GenEd teachers
3. **School-Level Only:** Would require aggregation to district level
4. **Complexity:** 1.27 million records per year, significant processing overhead

**Alternative Approach:**
- Use NCES CCD staff counts (district-level, current)
- Use IDEA 618 state-level SPED teacher ratios
- Use CA SPED environment data for refined estimates
- Revisit if CA releases updated staff assignment files (check annually)

---

## 4. Free or Reduced-Price Meal (FRPM) Data

**Source:** https://www.cde.ca.gov/ds/ad/filessp.asp
**Direct URL:** https://www.cde.ca.gov/ds/ad/documents/frpmYYYY.xlsx
**File Format:** Excel (XLSX) with 3 sheets
**File Size:** ~2.1MB
**Years Available:** 2011-12 through 2024-25
**Records:** ~10,580 (2023-24)
**Encoding:** UTF-8

### Excel Sheet Structure

**Sheet 1:** Title Page (readme/documentation)
**Sheet 2:** FRPM School-Level Data (actual data) ⭐
**Sheet 3:** Data Field Descriptions

### Field Structure (27 columns)

**Important:** Use `header=1` when reading Sheet 2 (first row is title, second row is header)

| # | Field Name | Data Type | Description | Sample |
|---|------------|-----------|-------------|--------|
| 1 | Academic Year | String | Format: "YYYY-YYYY" | 2023-2024 |
| 2 | County Code | String(2) | 2-digit county code | 01 |
| 3 | District Code | String(5) | 5-digit district code | 10017 |
| 4 | School Code | String(7) | 7-digit school code (0000000 = district) | 0112607 |
| 5 | County Name | String | County name | Alameda |
| 6 | District Name | String | District name | Alameda County Office of Education |
| 7 | School Name | String | School name | Envision Academy for Arts & Technology |
| 8 | District Type | String | District type description | County Office of Education (COE) |
| 9 | School Type | String | School type description | K-12 Schools (Public) |
| 10 | Educational Option Type | String | Traditional, Alternative, etc. | Traditional |
| 11 | Charter School (Y/N) | String | Charter status | Yes |
| 12 | Charter School Number | String(4) | 4-digit charter number | 0811 |
| 13 | Charter Funding Type | String | Directly/locally funded | Directly funded |
| 14 | IRC | String | Independent Review Committee flag | Y |
| 15 | Low Grade | String | Lowest grade offered | 6 |
| 16 | High Grade | String | Highest grade offered | 12 |
| 17 | Enrollment (K-12) | Integer | Total K-12 enrollment | 223 |
| 18 | Free Meal Count (K-12) | Integer | Free-eligible students | 154 |
| 19 | Percent (%) Eligible Free (K-12) | Decimal | Free-eligible percentage | 0.6905829596 |
| 20 | FRPM Count (K-12) | Integer | Free + Reduced eligible | 162 |
| 21 | Percent (%) Eligible FRPM (K-12) | Decimal | **FRPM percentage** | 0.7264573991 |
| 22 | Enrollment (Ages 5-17) | Integer | Ages 5-17 enrollment | 222 |
| 23 | Free Meal Count (Ages 5-17) | Integer | Ages 5-17 free-eligible | 153 |
| 24 | Percent (%) Eligible Free (Ages 5-17) | Decimal | Ages 5-17 free pct | 0.6891891892 |
| 25 | FRPM Count (Ages 5-17) | Integer | Ages 5-17 FRPM count | 161 |
| 26 | Percent (%) Eligible FRPM (Ages 5-17) | Decimal | Ages 5-17 FRPM pct | 0.7252252252 |
| 27 | CALPADS Fall 1 Certification Status | String | Data certification flag | Y |

### Aggregation Levels

**School-Level Records:** School Code ≠ "0000000"
- Count: 10,436 records (2023-24)
- Contains individual school data

**District-Level Records:** School Code = "0000000"
- Count: 146 records (2023-24)
- District aggregates (all schools combined)
- Unique districts: 1,019

### Key Fields for LCT

**Primary Poverty Metric:**
- `Percent (%) Eligible FRPM (K-12)` - Use for socioeconomic equity analysis

**Enrollment Validation:**
- `Enrollment (K-12)` - Compare against NCES CCD enrollment

**CDS Code Composition:**
- Full CDS: County Code + District Code + School Code (14 digits)
- District CDS: County Code + District Code + "0000000" (7 digits for district, 7 zeros for school)

### Important Distinctions

**FRPM Census Day vs CALPADS UPC:**
- **FRPM Census Day** (this file): Official count as of first Wednesday in October
  - Use for: General analysis, equity comparisons, validation
  - Time window: Eligibility as of Census Day only

- **CALPADS UPC** (separate file): Extended eligibility window through October 31st
  - Use for: LCFF funding calculations ONLY
  - Time window: Any eligibility during Fall 1 reporting period
  - DO NOT use for general analysis (per CA CDE guidance)

### Usage for LCT

**District-Level Aggregation:**
```python
# Filter to district-level records
district_frpm = df[df['School Code'] == '0000000'].copy()

# Key metrics
district_frpm['poverty_rate'] = district_frpm['Percent (%) Eligible FRPM (K-12)']
district_frpm['enrollment'] = pd.to_numeric(district_frpm['Enrollment (K-12)'])
district_frpm['frpm_count'] = pd.to_numeric(district_frpm['FRPM Count (K-12)'])
```

**Crosswalk to NCES:**
```python
# Build 7-digit district CDS code
district_frpm['cds_code'] = district_frpm['County Code'] + district_frpm['District Code']

# Match to NCES via ST_LEAID
# NCES ST_LEAID format: "CA-CCCDDDD"
```

---

## 5. Integration Workflows

### Workflow 1: SPED Environment Enhancement

**Goal:** Replace state-level self-contained proportions with district-specific CA data

**Data Sources:**
- NCES CCD 2023-24 (districts table) - Already loaded
- CA SPED 2023-24 (spedps2324.txt) - Downloaded ✅

**Steps:**

1. **Read CA SPED Data**
   ```python
   import pandas as pd

   sped = pd.read_csv('data/raw/state/california/sped_2023_24.txt',
                      sep='\t', dtype=str, encoding='utf-8')

   # Filter to district-level totals
   district_sped = sped[
       (sped['Aggregate Level'] == 'D') &
       (sped['ReportingCategory'] == 'Total')
   ].copy()
   ```

2. **Calculate Self-Contained Metrics**
   ```python
   # Convert to numeric
   numeric_cols = ['SPED_ENR_N', 'PS_RCGT80_N', 'PS_RC4079_N',
                   'PS_RCL40_N', 'PS_SSOS_N', 'PS_PSS_N']
   for col in numeric_cols:
       district_sped[col] = pd.to_numeric(district_sped[col], errors='coerce')

   # Calculate self-contained (exclude preschool)
   district_sped['self_contained'] = (
       district_sped['PS_RCL40_N'] + district_sped['PS_SSOS_N']
   )

   # Calculate mainstreamed
   district_sped['mainstreamed'] = (
       district_sped['PS_RCGT80_N'] + district_sped['PS_RC4079_N']
   )

   # Calculate proportion
   district_sped['self_contained_proportion'] = (
       district_sped['self_contained'] / district_sped['SPED_ENR_N']
   )
   ```

3. **Crosswalk to NCES IDs**
   ```python
   # Build 7-digit CDS code
   district_sped['cds_code'] = (
       district_sped['County Code'].str.zfill(2) +
       district_sped['District Code'].str.zfill(5)
   )

   # Read NCES CCD to get ST_LEAID crosswalk
   from infrastructure.database.connection import session_scope
   from sqlalchemy import text

   with session_scope() as session:
       nces_crosswalk = pd.read_sql(text("""
           SELECT nces_id,
                  REPLACE(st_leaid, 'CA-', '') as cds_code
           FROM nces_raw_directory_2023_24
           WHERE state = 'CA'
       """), session.connection())

   # Merge with CA SPED data
   enriched = district_sped.merge(
       nces_crosswalk,
       on='cds_code',
       how='inner'
   )

   print(f"Matched {len(enriched)} / {len(district_sped)} districts")
   ```

4. **Insert to Database**
   ```python
   from infrastructure.database.models import CASpedEnvironment

   with session_scope() as session:
       for _, row in enriched.iterrows():
           ca_sped = CASpedEnvironment(
               nces_id=row['nces_id'],
               cds_code=row['cds_code'],
               year='2023-24',
               sped_enrollment_total=int(row['SPED_ENR_N']),
               sped_mainstreamed=int(row['mainstreamed']),
               sped_self_contained=int(row['self_contained']),
               sped_preschool=int(row['PS_PSS_N']),
               sped_missing=int(row['PS_MUK_N']),
               self_contained_proportion=float(row['self_contained_proportion']),
               data_source='ca_cde_sped',
           )
           session.add(ca_sped)
       session.commit()
   ```

### Workflow 2: FRPM Socioeconomic Enrichment

**Goal:** Add district-level poverty rates for equity analysis

**Data Sources:**
- NCES CCD 2023-24 (districts table)
- CA FRPM 2023-24 (frpm2324.xlsx) - Downloaded ✅

**Steps:**

1. **Read FRPM Data**
   ```python
   import pandas as pd

   # Read from Sheet 2 with proper header
   frpm = pd.read_excel('data/raw/state/california/frpm_2023_24.xlsx',
                        sheet_name='FRPM School-Level Data',
                        header=1,
                        dtype=str)

   # Filter to district-level
   district_frpm = frpm[frpm['School Code'] == '0000000'].copy()
   ```

2. **Prepare District Data**
   ```python
   # Build CDS code
   district_frpm['cds_code'] = (
       district_frpm['County Code'].str.zfill(2) +
       district_frpm['District Code'].str.zfill(5)
   )

   # Convert to numeric
   district_frpm['enrollment'] = pd.to_numeric(
       district_frpm['Enrollment (K-12)'], errors='coerce'
   )
   district_frpm['frpm_count'] = pd.to_numeric(
       district_frpm['FRPM Count (K-12)'], errors='coerce'
   )
   district_frpm['frpm_percent'] = pd.to_numeric(
       district_frpm['Percent (%) Eligible FRPM (K-12)'], errors='coerce'
   )
   ```

3. **Crosswalk and Merge**
   ```python
   # Use same NCES crosswalk as SPED workflow
   enriched_frpm = district_frpm.merge(
       nces_crosswalk,
       on='cds_code',
       how='inner'
   )
   ```

4. **Insert to Database**
   ```python
   from infrastructure.database.models import DistrictSocioeconomic

   with session_scope() as session:
       for _, row in enriched_frpm.iterrows():
           socio = DistrictSocioeconomic(
               nces_id=row['nces_id'],
               year='2023-24',
               frpm_percent=float(row['frpm_percent']),
               frpm_count=int(row['frpm_count']),
               enrollment=int(row['enrollment']),
               data_source='ca_cde_frpm',
           )
           session.add(socio)
       session.commit()
   ```

---

## 6. File Download Quick Reference

### Special Education (Current)
```bash
# 2023-24
curl -L "https://www3.cde.ca.gov/demo-downloads/sped/spedps2324.txt" -o sped_2023_24.txt

# 2024-25
curl -L "https://www3.cde.ca.gov/demo-downloads/sped/spedps2425.txt" -o sped_2024_25.txt
```

### Public Districts Directory (Current)
```bash
# Districts only (TXT)
curl -L "https://www.cde.ca.gov/SchoolDirectory/report?rid=dl2&tp=txt" -o ca_districts.txt

# All schools and districts (TXT, larger)
curl -L "https://www.cde.ca.gov/SchoolDirectory/report?rid=dl1&tp=txt" -o ca_schools_all.txt
```

### FRPM Data (Current)
```bash
# 2023-24
curl -L "https://www.cde.ca.gov/ds/ad/documents/frpm2324.xlsx" -o frpm_2023_24.xlsx

# 2024-25 (when available)
curl -L "https://www.cde.ca.gov/ds/ad/documents/frpm2425.xlsx" -o frpm_2024_25.xlsx
```

### Staff Assignment (Historical)
```bash
# 2018-19 (most recent)
curl -L "https://www3.cde.ca.gov/download/dq/StaffAssign18.zip" -o staff_assign_18.zip

# Assignment codes reference
curl -L "http://www3.cde.ca.gov/download/dq/AssignmentCodes12On.xlsx" -o assignment_codes.xlsx
```

---

## 7. Data Quality Notes

### Special Education Data

**Strengths:**
- ✅ District-level aggregates available
- ✅ Recent data (2023-24, 2024-25)
- ✅ Comprehensive environment breakdown (5 categories)
- ✅ Large sample (1,010 districts)

**Limitations:**
- ⚠️ School-level demographic breakdowns suppressed (privacy)
- ⚠️ Missing environment data tracked (`PS_MUK_N`) - monitor prevalence
- ⚠️ Preschool ages (3-5) must be excluded from K-12 calculations

**Validation:**
- Compare totals against NCES CCD SPED enrollment
- Check self-contained proportion against IDEA 618 state average (9.9% for CA)
- Monitor districts with high missing rates (`PS_MUK_N > 5%`)

### FRPM Data

**Strengths:**
- ✅ School and district levels available
- ✅ Current data (2023-24, 2024-25)
- ✅ Official Census Day counts
- ✅ Both Free-only and FRPM metrics

**Limitations:**
- ⚠️ Different counting methodology than federal NSLP
- ⚠️ Only 146 district-level records (vs 1,019 districts in directory)
- ⚠️ CALPADS UPC differs from FRPM Census Day (don't mix)

**Validation:**
- Enrollment should align with NCES CCD enrollment (within ±5%)
- FRPM percent should be between 0 and 1
- Districts with Certification Status = 'N' may have data quality issues

### Staff Assignment Data

**Critical Issues:**
- ❌ **Outdated:** Last release 2018-19 (6+ years old)
- ❌ **No SPED Teacher Designation:** Cannot identify SPED teachers
- ❌ **School-Level Only:** Requires aggregation
- ❌ **No Update Schedule:** Unknown when/if CA will release current data

**Recommendation:** **DEFER** integration until current data available or SPED teacher coding added

---

## 8. Glossary

**CDS Code:** County-District-School code, California's 14-digit school identifier
- **Format:** CCDDDDDSSSSSSS
- **County Code:** 2 digits (01-58)
- **District Code:** 5 digits within county
- **School Code:** 7 digits within district (0000000 = district-level)

**CALPADS:** California Longitudinal Pupil Achievement Data System, CA's K-12 student data system

**Census Day:** First Wednesday in October, official enrollment count date

**FRPM:** Free or Reduced-Price Meal, federal school lunch program eligibility

**UPC:** Unduplicated Pupil Count, used for California LCFF funding calculations

**LCFF:** Local Control Funding Formula, California's school funding mechanism

**IRC:** Independent Review Committee, oversight for alternative schools

**DSEA:** Direct-funded charter school equivalent of an LEA

**Self-Contained SPED:** Students receiving instruction in separate settings (<40% general education time)

**Mainstreamed SPED:** Students receiving instruction primarily in general education classrooms (40%+ time)

---

## 9. Next Steps

### Immediate Implementation (Phase 2.1)

1. ✅ **CA SPED 2023-24 Integration**
   - Downloaded and analyzed
   - Structure documented
   - Ready for database import

2. ⏳ **NCES Crosswalk Setup**
   - Extract ST_LEAID from NCES CCD
   - Build CDS-to-NCES mapping table
   - Validate match rate (target: >95%)

3. ⏳ **Database Schema Creation**
   - Create `ca_sped_district_environments` table
   - Create `district_socioeconomic` table (for FRPM)
   - Add indexes on nces_id and cds_code

4. ⏳ **Data Import Scripts**
   - `infrastructure/scripts/download/fetch_ca_cde_data.py`
   - `infrastructure/database/migrations/import_ca_sped_environments.py`
   - `infrastructure/database/migrations/import_ca_frpm_data.py`

5. ⏳ **Enhanced LCT Calculation**
   - Modify `calculate_lct_variants.py` to use CA-specific SPED data
   - Upgrade confidence from 'medium' to 'high' for CA districts
   - Generate validation report

### Short-Term (Phase 2.2)

6. **FRPM Socioeconomic Integration**
   - Import 2023-24 FRPM data
   - Add poverty quartile classifications
   - Enable equity analysis by socioeconomic status

7. **Multi-Year Validation**
   - Download CA SPED 2022-23 and 2024-25
   - Validate trend stability
   - Check for systematic shifts

8. **Documentation Updates**
   - Create CA-specific integration guide
   - Update METHODOLOGY.md with CA enhancements
   - Generate CA district profiles

### Future Consideration

9. **Staff Assignment Monitoring**
   - Check annually for data releases
   - Advocate for current data publication
   - Explore alternative CA staffing data sources

10. **Expand to Other States**
    - Texas (TEA PEIMS data)
    - Florida (FLDOE EdStats)
    - New York (NYSED data portal)

---

**Document Version:** 1.0
**Last Updated:** January 9, 2026
**Status:** Technical documentation complete, ready for implementation
**Files Downloaded:** ✅ CA SPED 2023-24, ✅ CA Districts Directory, ✅ CA FRPM 2023-24, ✅ CA Staff 2018-19, ✅ Assignment Codes
