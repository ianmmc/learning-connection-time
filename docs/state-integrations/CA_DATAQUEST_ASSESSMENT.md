# California DataQuest & CDE Data Assessment

**Date:** January 9, 2026
**Status:** Phase 2 Planning - State-Level Data Integration
**Purpose:** Comprehensive evaluation of California education data for LCT enrichment

---

## Executive Summary

California offers **exceptional data availability** through the California Department of Education (CDE), with district-level special education, staffing, enrollment, and socioeconomic data. Key advantage: **direct NCES-to-CDS crosswalk exists** in federal NCES CCD data, enabling seamless integration.

### Key Strengths
- ✅ **Crosswalk Ready**: NCES `ST_LEAID` field contains CDS codes (format: `CA-CCCDDDD`)
- ✅ **SPED Environment Data**: District-level educational environment breakdowns (2022-23, 2023-24, 2024-25)
- ✅ **Recent Data**: 2023-24 and 2024-25 data available (vs. federal 2017-18 baseline)
- ✅ **Multiple Years**: Can analyze trends and validate against baseline
- ✅ **Large Files**: 12MB SPED files with 59,935 district-level records
- ✅ **Comprehensive Coverage**: 1,010 unique districts in SPED data

### Recommendation
**PROCEED** with California as first state for Phase 2 enrichment. Data quality, recency, and crosswalk availability make it ideal starting point.

---

## 1. Data Sources Catalog

### 1.1 Special Education Enrollment by Educational Environment
**Source:** https://www.cde.ca.gov/ds/ad/filesspedps.asp
**Years Available:** 2022-23, 2023-24, 2024-25
**File Format:** TXT (tab-delimited), 11-13MB
**Download URL Pattern:** `https://www3.cde.ca.gov/demo-downloads/sped/spedpsYYYY.txt`

**Coverage:**
- 115,423 total records (2023-24)
- 59,935 district-level records
- 1,010 unique districts
- 5 aggregate levels: State (T), County (C), District (D), DSEA (A), School (S)

**Educational Environment Categories (5 Settings):**
| Field | Description | Use for LCT |
|-------|-------------|-------------|
| `PS_RCGT80_N` | Regular class 80%+ of day | **Mainstreamed SPED** |
| `PS_RC4079_N` | Regular class 40-79% of day | **Mainstreamed SPED** |
| `PS_RCL40_N` | Regular class <40% of day | **Self-Contained SPED** |
| `PS_SSOS_N` | Separate school & other settings | **Self-Contained SPED** |
| `PS_PSS_N` | Preschool settings | Exclude (Ages 3-5) |
| `PS_MUK_N` | Missing/unreported | Flag for data quality |
| `SPED_ENR_N` | Total SPED enrollment with IEPs | Total SPED count |

**Disaggregation Dimensions:**
- **Demographics:** Race/ethnicity (9 categories), Gender (M/F/X/Missing), English Learner status
- **Disability:** 14 disability categories (Autism, SLD, OHI, SLI, etc.)
- **Age Ranges:** 3-5, 6-12, 13-18, 19+
- **Grade Spans:** PS-3, 4-6, 7-8, 9-12

**Key Fields:**
```
Academic Year, Aggregate Level, County Code, District Code, School Code,
County Name, District Name, School Name, Charter School, ReportingCategory,
SPED_ENR_N, PS_RCGT80_N/%, PS_RC4079_N/%, PS_RCL40_N/%, PS_SSOS_N/%,
PS_PSS_N/%, PS_MUK_N/%
```

**Privacy Protection:** Cells ≤10 students suppressed. School-level demographic data unavailable (totals only).

### 1.2 Public Schools and Districts Directory
**Source:** https://www.cde.ca.gov/ds/si/ds/pubschls.asp
**File Format:** TXT (tab-delimited), 258KB
**Download URL:** `https://www.cde.ca.gov/SchoolDirectory/report?rid=dl2&tp=txt`

**Coverage:**
- 1,070 district records (active and pending)
- Real-time data (dynamically generated)

**Key Fields:**
- `CD Code` (7-digit): California CDS code (County-District format: CCCDDDD)
- `County`, `District`: Names
- `DOCType`: District type (Elementary, Unified, High School, COE, ROC/P, State Special)
- `StatusType`: Active, Closed, Merged, Pending
- Geographic: Street, City, Zip, Latitude, Longitude
- Contact: Phone, Website, Administrator names
- Operational: Charter (Y/N), Magnet (Y/N), Virtual (F/V/C/N/P)

**District Types:**
- Elementary School District: 515
- Unified School District: 345
- High School District: 76
- Regional Occupation Center/Program (ROC/P): 59
- County Office of Education (COE): 58
- State Board of Education: 14
- State Special Schools: 3

**File Structure Documentation:** https://www.cde.ca.gov/ds/si/ds/fspubschls.asp

### 1.3 Staff Assignment Data
**Source:** https://www.cde.ca.gov/ds/ad/staff.asp
**Years Available:**
- Historical: 2012-13 through 2017-18
- Current: 2018-19 through 2023-24
- 2024-25 expected Summer 2026

**File Format:** TXT (tab-delimited)
**Granularity:** School-level with class-level detail

**Key Fields:**
```
AcademicYear, RecID, DistrictCode (7-digit), SchoolCode, StaffType,
AssignmentCode, ClassID, CourseCode, EstimatedFTE
```

**Limitation:** File structure documentation (404 error) needed to determine if special education teacher designation is explicitly coded. May require inference from `AssignmentCode` or `CourseCode`.

**Connector Fields:**
- `DistrictCode` (7-digit CDS district code)
- `SchoolCode` (7-digit CDS school code)

### 1.4 LCFF Funding Data
**Source:** https://www.cde.ca.gov/fg/aa/pa/lcffsumdata.asp
**Years Available:** 2019-20 through 2024-25
**File Format:** Excel (XLSX)

**Data Elements:**
- Base grants by grade span (TK-3, 4-6, 7-8, 9-12)
- Supplemental grants (unduplicated pupil count)
- Concentration grants (>55% UPC)
- Funded ADA (Average Daily Attendance)

**Granularity:** LEA level (County Offices, School Districts, Charter Schools)

**Use for LCT:**
- California-specific equity funding metric
- More current than federal F-33 data (2019-20 vs 2021-22)
- Complements FRPM data for socioeconomic analysis

### 1.5 FRPM (Free or Reduced-Price Meal) Data
**Source:** https://www.cde.ca.gov/ds/ad/filessp.asp
**Years Available:** 2011-12 through 2024-25
**File Format:** XLSX (2MB) for 2014-15+, XLS for earlier years

**Granularity:** School-level

**Key Distinction:**
- **FRPM Census Day** (official count): First Wednesday in October, eligibility as of that date
- **CALPADS UPC** (LCFF funding): Eligibility through October 31st, used ONLY for LCFF calculations

**Use for LCT:** Socioeconomic equity analysis, district poverty rates

**File Structure Documentation:** (404 error, need to locate)

### 1.6 English Learner Data
**Source:** https://www.cde.ca.gov/ds/ad/eldf.asp
**Years Available:** Not specified on page
**File Format:** Downloadable data files

**Four Data Categories:**
1. **English Learners by Grade & Language** - EL enrollment by grade, language, school
2. **Fluent English Proficient (FEP)** - FEP students by grade, language, school
3. **Reclassified FEP (RFEP)** - Students reclassified from EL to FEP since last census
4. **Long-Term English Learners (LTEL)** - By ELAS status, LTEL status, at-risk status, by grade

**Granularity:** School and district levels

**Use for LCT:** ELL subgroup analysis, reclassification rates, language diversity

### 1.7 CALPADS UPC (Unduplicated Pupil Count)
**Source:** https://www.cde.ca.gov/ds/ad/calpadsfiles.asp
**Files Available:** TK/K-12 grades, Grades 9-12 separately

**Student Populations Counted:**
- Free or Reduced-Price Meal (FRPM) eligible
- English Learners (EL)
- Foster Youth

**Critical Note:** UPC counts are "ONLY applicable for LCFF purposes and should NOT be used in any other context." Use FRPM Census Day data for general analysis.

**Use for LCT:** California-specific equity metric for supplemental/concentration grants

---

## 2. NCES-to-CDS Crosswalk

### 2.1 Crosswalk Mechanism

**Location:** NCES CCD Directory File (ccd_lea_029_YYYY_w_1a_MMDDYY.csv)
**Key Fields:**
- `LEAID`: Federal NCES district ID (e.g., `0600002`)
- `ST_LEAID`: State-assigned LEA ID (format: `CA-CCCDDDD`)
- `STATE_AGENCY_NO`: State agency number (always `01` for CA)

**CDS Code Extraction:**
```python
# Strip "CA-" prefix from ST_LEAID to get 7-digit CDS code
cds_code = st_leaid.replace('CA-', '')  # e.g., "CA-0131609" → "0131609"
```

**Example Crosswalk:**
| NCES ID | ST_LEAID | CDS Code | LEA Name |
|---------|----------|----------|----------|
| 0600002 | CA-0131609 | 0131609 | California School for the Blind (State Special Schl) |
| 0600001 | CA-1975309 | 1975309 | Acton-Agua Dulce Unified |
| 0600013 | CA-3175085 | 3175085 | Rocklin Unified |

### 2.2 Coverage Comparison

| Source | California Districts | Notes |
|--------|---------------------|-------|
| **NCES CCD 2023-24** | 2,130 | Includes all LEAs (districts, charters, state special schools) |
| **CA CDE Directory** | 1,070 | Active/pending districts only (may exclude some charters) |
| **CA SPED Data 2023-24** | 1,010 unique | Districts with SPED enrollment |
| **Our Database** | 1,985 | NCES CCD data currently loaded |

**Explanation of Differences:**
- NCES counts charter schools as separate LEAs
- NCES includes historical/closed districts
- CDE directory excludes some administrative units or uses different aggregation
- SPED data only includes districts with SPED students

**Crosswalk Quality:** ✅ **Excellent** - 100% of NCES California records have ST_LEAID populated

---

## 3. Integration Strategy

### 3.1 Immediate Integration (2023-24 Data)

**Goal:** Enhance current 2023-24 LCT calculations with California district-level SPED environment data

**Data Sources:**
1. **NCES CCD 2023-24** (already loaded in database)
2. **CA SPED 2023-24** (spedps2324.txt, 12MB, downloaded)
3. **CA Districts Directory** (for validation and metadata)

**Integration Steps:**
1. ✅ **Crosswalk Mapping**
   - Extract CDS codes from NCES `ST_LEAID` field
   - Match against CA SPED `District Code` field
   - Expected match rate: ~950-1,000 districts (95%+ of SPED-reporting districts)

2. **SPED Environment Calculation**
   - Aggregate district-level SPED data by environment (sum across all demographic categories)
   - Calculate self-contained SPED: `PS_RCL40_N + PS_SSOS_N` (excluding preschool)
   - Calculate mainstreamed SPED: `PS_RCGT80_N + PS_RC4079_N`
   - Calculate self-contained proportion: Self-contained / Total SPED

3. **Database Schema Extension**
   ```sql
   -- New table: ca_sped_district_environments
   CREATE TABLE ca_sped_district_environments (
     nces_id VARCHAR NOT NULL,
     cds_code VARCHAR(7) NOT NULL,
     year VARCHAR NOT NULL,
     sped_enrollment_total INTEGER,
     sped_mainstreamed INTEGER,  -- 80%+ and 40-79%
     sped_self_contained INTEGER, -- <40% and separate school
     sped_preschool INTEGER,      -- Ages 3-5 settings
     sped_missing INTEGER,        -- Unreported
     self_contained_proportion NUMERIC,
     data_source VARCHAR DEFAULT 'ca_cde_sped',
     created_at TIMESTAMP DEFAULT NOW(),
     PRIMARY KEY (nces_id, year),
     FOREIGN KEY (nces_id) REFERENCES districts(nces_id)
   );
   ```

4. **Enhanced SPED Estimation**
   - **Current Method:** State-level self-contained proportion (e.g., CA = 9.9%)
   - **Enhanced Method:** District-specific self-contained proportion from CA CDE data
   - **Impact:** Replace state-level estimate with actual district data for ~1,000 CA districts (50% of CA districts)

### 3.2 Multi-Year Analysis (2022-23, 2023-24, 2024-25)

**Goal:** Validate SPED environment stability and establish trend data

**Data Sources:**
- CA SPED 2022-23 (spedps2223.txt)
- CA SPED 2023-24 (spedps2324.txt) ✅ Downloaded
- CA SPED 2024-25 (spedps2425.txt)

**Analysis Questions:**
1. How stable are self-contained proportions across years?
2. Do districts show consistent SPED environment patterns?
3. Can we use 2024-25 data as proxy for 2023-24 where gaps exist?

**Validation:**
- Compare CA CDE district totals against CRDC 2017-18 LEA-level SPED enrollment
- Check for systematic differences in counting methodologies

### 3.3 Staff Assignment Integration (Future)

**Goal:** Enhance teacher-level staffing estimates with California school-level assignment data

**Challenges:**
- Need file structure documentation (currently 404)
- Unclear if SPED teacher designation is explicitly coded
- May require inference from assignment codes or course codes

**Potential Enhancement:**
- School-level teacher FTE by subject area
- Class size distributions
- Special education vs general education teacher counts (if coded)

**Decision Point:** Investigate file structure first before committing to integration

### 3.4 Socioeconomic Integration

**Data Sources:**
- FRPM Census Day 2023-24 (school-level)
- LCFF Funding 2023-24 (district-level)
- CALPADS UPC 2023-24 (district-level, LCFF-specific)

**Use Cases:**
1. **Poverty Rate:** Aggregate school-level FRPM to district level
2. **LCFF Funding Analysis:** Supplemental/concentration grant eligibility
3. **Equity Analysis:** LCT by poverty quartile, UPC threshold crosswalks

**Integration Priority:** Medium (Phase 2.5 or Phase 3)

---

## 4. Data Quality Considerations

### 4.1 Strengths
✅ **Recent Data:** 2023-24 and 2024-25 available (vs. federal 2017-18 baseline)
✅ **Large Sample:** 1,010 districts with SPED environment data
✅ **Multiple Years:** Can validate trends and stability
✅ **Direct Crosswalk:** NCES ST_LEAID contains CDS codes
✅ **Comprehensive Breakdowns:** 5 educational environments, 14 disability categories, 9 race/ethnicity groups
✅ **Official Source:** California Department of Education primary data system (CALPADS)

### 4.2 Limitations
⚠️ **Privacy Suppression:** Cells ≤10 students suppressed (affects demographic breakdowns at school level)
⚠️ **Missing Data:** `PS_MUK_N` field tracks unreported educational environment (monitor prevalence)
⚠️ **Preschool Ages:** Must exclude Ages 3-5 from K-12 calculations
⚠️ **Charter School Variability:** Different counting/reporting across NCES vs CA CDE
⚠️ **Staff Assignment Gap:** Need file structure documentation to assess utility

### 4.3 Validation Checks

**Before Integration:**
1. ✅ Verify CDS code format matches (7-digit CCCDDDD)
2. ✅ Confirm district counts align across sources (within expected variance)
3. ⏳ Compare CA CDE 2023-24 SPED totals against NCES CCD 2023-24 SPED enrollment (if available)
4. ⏳ Spot-check 10-20 districts against public-facing data (DataQuest reports)
5. ⏳ Validate self-contained proportions against 2017-18 IDEA 618 state average (CA = 9.9%)

**After Integration:**
1. Check for systematic differences in SPED counts between CA CDE and CRDC/IDEA 618
2. Monitor districts with high `PS_MUK_N` (missing educational environment data)
3. Validate that self-contained + mainstreamed ≈ total SPED enrollment (allowing for preschool)
4. Compare enhanced LCT calculations (CA-specific) against baseline (state-level ratios)

---

## 5. Technical Implementation

### 5.1 Data Download Scripts

**New Script:** `infrastructure/scripts/download/fetch_ca_cde_data.py`

```python
"""
Download California CDE data files for LCT enrichment.

Supports:
- Special Education enrollment by educational environment (2022-25)
- Public districts directory
- FRPM data
- English Learner data
- Staff assignment data (when structure documented)
"""

import requests
import pandas as pd
from pathlib import Path

BASE_URL = "https://www3.cde.ca.gov/demo-downloads"
OUTPUT_DIR = Path("data/raw/state/california")

def download_sped_data(year: str):
    """Download CA SPED data for given year (e.g., '2324' for 2023-24)."""
    url = f"{BASE_URL}/sped/spedps{year}.txt"
    output_file = OUTPUT_DIR / f"sped_enrollment_by_environment_{year}.txt"
    # ... implementation

def download_districts_directory():
    """Download CA public districts directory with CDS codes."""
    url = "https://www.cde.ca.gov/SchoolDirectory/report?rid=dl2&tp=txt"
    output_file = OUTPUT_DIR / "ca_public_districts_directory.txt"
    # ... implementation
```

### 5.2 Database Migration Script

**New Script:** `infrastructure/database/migrations/import_ca_sped_environments.py`

```python
"""
Import California SPED educational environment data to database.

Creates table: ca_sped_district_environments
Populates from: data/raw/state/california/sped_enrollment_by_environment_*.txt
Crosswalks via: districts.nces_id → ST_LEAID (strip 'CA-' prefix) → CDS Code
"""

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, CASpedEnvironment
from sqlalchemy import text
import pandas as pd

def import_sped_data(year: str, file_path: str):
    """Import CA SPED environment data for specified year."""
    # 1. Read SPED data file
    # 2. Filter to district-level records (Aggregate Level = 'D')
    # 3. Aggregate by district (sum across demographic categories)
    # 4. Calculate self-contained and mainstreamed totals
    # 5. Crosswalk CDS codes to NCES IDs via ST_LEAID
    # 6. Insert into ca_sped_district_environments table
    # ... implementation
```

### 5.3 Enhanced SPED Calculation Script

**Modified Script:** `infrastructure/scripts/analyze/calculate_lct_variants.py`

```python
# Add California-specific SPED environment logic
def get_sped_environment_data(session, nces_id: str, year: str):
    """
    Get SPED environment data for district.

    Returns:
    - CA-specific self-contained count (if available)
    - State-level self-contained proportion (fallback)
    - Confidence level: 'high' (CA data), 'medium' (state ratio)
    """
    ca_data = session.query(CASpedEnvironment).filter(
        CASpedEnvironment.nces_id == nces_id,
        CASpedEnvironment.year == year
    ).first()

    if ca_data and ca_data.sped_self_contained is not None:
        return {
            'self_contained_count': ca_data.sped_self_contained,
            'total_sped': ca_data.sped_enrollment_total,
            'source': 'ca_cde_actual',
            'confidence': 'high'
        }
    else:
        # Fallback to state-level ratio estimation
        # ... existing logic
```

### 5.4 Query Utilities Extension

**Modified:** `infrastructure/database/queries.py`

```python
def get_ca_enriched_districts(session) -> pd.DataFrame:
    """
    Get California districts with enhanced SPED environment data.

    Returns DataFrame with:
    - NCES ID, CDS Code, District Name
    - Total SPED enrollment (CA CDE vs NCES CCD comparison)
    - Self-contained count, mainstreamed count, preschool count
    - Self-contained proportion (actual vs state average)
    - Data quality flags
    """
    query = text("""
        SELECT
            d.nces_id,
            d.name,
            d.state,
            d.enrollment as total_enrollment,
            d.instructional_staff,
            ca.cds_code,
            ca.sped_enrollment_total,
            ca.sped_self_contained,
            ca.sped_mainstreamed,
            ca.self_contained_proportion,
            sr.ratio_self_contained_proportion as state_proportion
        FROM districts d
        LEFT JOIN ca_sped_district_environments ca
            ON d.nces_id = ca.nces_id AND ca.year = '2023-24'
        LEFT JOIN sped_state_baseline sr
            ON d.state = sr.state AND sr.year = '2017-18'
        WHERE d.state = 'CA' AND d.year = '2023-24'
        ORDER BY d.enrollment DESC
    """)
    # ... implementation
```

---

## 6. Success Metrics

### 6.1 Data Integration Metrics

**Coverage Goals:**
- ✅ Crosswalk match rate: **>95%** (950+ of 1,000 SPED-reporting districts)
- ✅ Data completeness: **<5%** missing educational environment data per district
- ✅ California district coverage: **50%** of all CA districts in database (1,000 of 2,000)

**Data Quality Goals:**
- ✅ Validation against IDEA 618: CA self-contained proportion within 1-2% of state average (9.9%)
- ✅ Consistency check: Multi-year stability (2022-24 self-contained proportions vary <3%)
- ✅ Spot-check accuracy: 95%+ match against DataQuest public reports

### 6.2 LCT Calculation Impact

**Enhancement Goals:**
- **California-specific SPED LCT:** Replace state-level estimates for ~1,000 districts
- **Confidence upgrade:** Move from 'medium' (state ratio) to 'high' (district-specific)
- **Equity analysis:** Enable within-California comparisons using actual SPED environments

**Expected Results:**
- ~50% of California districts move from estimated to actual self-contained proportions
- Improved precision for California SPED equity analysis
- Baseline established for multi-state comparison (CA as reference)

### 6.3 Documentation Deliverables

1. **Data Dictionary:** `docs/data-dictionaries/ca_cde_sped_environments.md`
2. **Integration Summary:** `docs/CA_SPED_INTEGRATION_SUMMARY.md`
3. **Validation Report:** `outputs/validation/ca_sped_validation_report_2023_24.txt`
4. **Comparison Analysis:** `outputs/analysis/ca_vs_national_sped_comparison.csv`

---

## 7. Risks and Mitigation

### 7.1 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Crosswalk Mismatch** | Low | High | Validate against CA CDE directory before proceeding |
| **Privacy Suppression** | Medium | Low | Affects school-level only, district-level aggregates sufficient |
| **Counting Methodology Differences** | Medium | Medium | Document differences, use CA CDE as primary for CA districts |
| **Staff Assignment Utility** | High | Low | Defer until file structure documented |
| **Multi-Year Instability** | Low | Medium | Validate 2022-24 trends before using as proxy |

### 7.2 Mitigation Strategies

**Crosswalk Validation:**
- Run pilot import on 50 districts before full integration
- Manually verify 10-20 high-enrollment districts against DataQuest
- Check for systematic mismatches (e.g., charter school treatment)

**Counting Methodology:**
- Document CA CDE vs NCES CCD vs CRDC SPED enrollment differences
- Add metadata field: `sped_data_source` ('ca_cde', 'crdc_lea', 'idea_618_state')
- Flag districts with >10% discrepancy between sources

**Staff Assignment:**
- Download sample file to inspect structure
- If documentation unavailable, defer to future phase
- Consider requesting technical assistance from CA CDE

---

## 8. Next Steps

### 8.1 Immediate (This Session)
1. ✅ Complete California DataQuest assessment
2. ⏳ Create database migration script for CA SPED environments
3. ⏳ Run pilot import on 50 districts
4. ⏳ Validate crosswalk match rate

### 8.2 Short-Term (Next Session)
1. Full CA SPED 2023-24 data import
2. Enhanced LCT calculation for California districts
3. Validation report generation
4. Multi-year trend analysis (2022-24)

### 8.3 Medium-Term (Phase 2)
1. Download and integrate FRPM data
2. Add LCFF funding data for equity analysis
3. Investigate staff assignment file structure
4. Expand to other large states (Texas, Florida, New York)

---

## 9. Conclusion

California offers **exceptional data quality and availability** for Phase 2 state-level enrichment. Key advantages:

✅ **Ready for Integration:** Direct NCES-to-CDS crosswalk exists
✅ **Recent Data:** 2023-24 and 2024-25 data available (vs 2017-18 federal baseline)
✅ **Large Sample:** ~1,000 districts with detailed SPED environment data
✅ **High Impact:** 50% of California districts can move from estimated to actual SPED calculations
✅ **Scalable:** Methodology can be replicated for other states with similar data

**Recommendation:** **PROCEED** with California as first state for Phase 2 integration. Establish this as reference model for subsequent state integrations (TX, FL, NY, PA).

---

**Document Version:** 1.0
**Last Updated:** January 9, 2026
**Next Review:** After pilot import completion
**Contact:** dro@cde.ca.gov (CA CDE Data Reporting Office)
