# Texas Education Data Integration Plan

**Created:** 2026-01-11
**Status:** Research Phase
**Target Dataset:** 2024-25 school year

---

## Overview

Texas provides comprehensive education data through the **Public Education Information Management System (PEIMS)**, one of the largest education databases in the world, covering ~1,200 districts and charter schools.

---

## Data Sources Summary

### 1. Student Enrollment Data
- **Source:** [PEIMS Standard Reports - Student Enrollment](https://tea.texas.gov/reports-and-data/student-data/standard-reports/peims-standard-reports)
- **Direct Portal:** [Student Enrollment Reports](https://rptsvr1.tea.texas.gov/adhocrpt/adste.html)
- **Available Years:** 2011-12 through 2024-25
- **Latest Publication:** March 14, 2025
- **Granularity:** District-level and campus-level
- **Format:** Web display or comma-delimited (CSV)
- **Data Includes:**
  - Total enrollment by district
  - Grade-level breakdown (K-12)
  - Demographics (ethnicity, gender)
  - Combined categories available

### 2. Staffing Data
- **Source:** [PEIMS Standard Reports - Staff FTE and Salary](https://tea.texas.gov/reports-and-data/student-data/standard-reports/peims-standard-reports)
- **Available Years:** 2011-12 through 2024-25
- **Latest Publication:** April 3, 2025
- **Additional Reports:**
  - Teacher FTE Counts and Student Course Enrollment (published March 25, 2025)
  - Superintendent Salary Reports (published March 27, 2025)
- **Granularity:** District-level
- **Format:** Web display or CSV

### 3. Special Education Data
- **Source:** [Special Education Data and Reports](https://tea.texas.gov/academics/special-student-populations/special-education/data-and-reports)
- **Direct Portal:** [Special Education Reports](https://rptsvr1.tea.texas.gov/adhocrpt/adser.html)
- **Available Years:** 2012-13 through 2024-25
- **Latest Publication:** May 9, 2025
- **Data Includes:**
  - Students receiving SPED services by district
  - Breakdown by primary disability
  - Multiple aggregation levels (state, region, county, district)
- **Format:** Web display or CSV
- **Privacy:** FERPA-compliant masking (N/A on web, -999 in CSV)

### 4. Economically Disadvantaged Data
- **Source:** [PEIMS Standard Reports - Economically Disadvantaged](https://tea.texas.gov/reports-and-data/student-data/standard-reports/peims-standard-reports)
- **Available Years:** 2011-12 through 2024-25
- **Latest Publication:** April 21, 2025
- **Data Includes:**
  - Free meals eligible
  - Reduced-price meals eligible
  - Other economic disadvantage
  - Not economically disadvantaged
- **Format:** Web display or CSV

### 5. District Identifiers & Crosswalk
- **Source:** [Campus and District Type Data Search](https://tea.texas.gov/reports-and-data/school-data/campus-and-district-type-data-search)
- **Available:** 2017-18 forward (includes both TEA and NCES classifications)
- **Format:** Excel (.xlsx)
- **Data Includes:**
  - TEA district codes
  - NCES district IDs
  - District names
  - District type classifications (TEA 9-category, NCES 12-category)
  - Geographic information

---

## Data Quality Assessment

### ✅ Strengths
- **Comprehensive coverage:** All data types we need are available
- **Recent data:** 2024-25 school year published (March-May 2025)
- **Consistent format:** CSV downloads available for all reports
- **Good documentation:** Clear data dictionaries and glossaries
- **Built-in crosswalk:** NCES IDs included in district type data
- **Multiple years:** Historical data back to 2011-12

### ⚠️ Considerations
- **Web-based portal:** Data accessed through report server, not bulk download
- **Privacy masking:** FERPA compliance uses -999 for small cell sizes
- **District-level focus:** Less granular than California's school-level data
- **Limited SPED detail:** Disability categories available, but educational environment/setting data unclear

---

## Integration Strategy

### Phase 1: Data Acquisition ✅ (Current)
- [x] Identify data sources
- [x] Document availability
- [ ] Download sample files for format analysis
- [ ] Verify district identifier matching

### Phase 2: Database Design
- [ ] Design Texas state tables (Layer 2 schema)
- [ ] Create SQL migration scripts
- [ ] Add indexes and constraints
- [ ] Document schema in data dictionary

### Phase 3: Crosswalk Development
- [ ] Download District Type Data (2023-24)
- [ ] Build TEA ↔ NCES ID mapping table
- [ ] Validate crosswalk completeness
- [ ] Handle charter schools and special cases

### Phase 4: Data Import Scripts
- [ ] Enrollment import script
- [ ] Staffing import script
- [ ] Special education import script
- [ ] Economically disadvantaged import script
- [ ] Batch import orchestration

### Phase 5: Validation & QA
- [ ] Data completeness checks
- [ ] Crosswalk validation
- [ ] Audit calculations (compare to federal data)
- [ ] Generate validation report

### Phase 6: Documentation
- [ ] Integration methodology document
- [ ] Data lineage tracking
- [ ] Known limitations and caveats
- [ ] Update PROJECT_CONTEXT.md

---

## Key Differences from California Integration

| Aspect | California | Texas |
|--------|-----------|-------|
| **Data Portal** | Multiple APIs (DataQuest, CalPADS) | Single PEIMS portal |
| **Granularity** | School-level | District-level primarily |
| **SPED Detail** | Educational settings available | Disability categories only |
| **Format** | API + downloadable files | Web reports + CSV export |
| **Crosswalk** | Built custom utility | TEA provides NCES IDs |
| **Socioeconomic** | FRPM + LCFF funding | Economically disadvantaged (NSLP) |

---

## Data Access Findings (2026-01-11)

### ✅ Completed Research
1. **Downloaded District Type Data (2022-23):**
   - 1,217 Texas districts
   - Contains: TEA District Number, District Name, TEA Type, NCES Type (code only), Charter flag
   - **⚠️ Missing:** NCES LEA IDs (only has NCES type classification codes 11-42)
   - File: `data/raw/state/texas/district_identifiers/district_type_2022_23.xlsx`

2. **✅ FOUND: NCES CCD Crosswalk (2018-19):**
   - **Source:** NCES Common Core of Data (CCD) LEA Universe Survey
   - **Field:** `ST_LEAID` contains TEA district numbers in format "TX-XXXXXX"
   - **Coverage:** 1,235 Texas districts with complete NCES ↔ TEA mapping
   - **Format:** CSV with both NCES LEAID and state-assigned IDs
   - **Files:**
     - Raw CCD data: `nces_ccd_lea_2018_19.csv`
     - Texas crosswalk: `texas_nces_tea_crosswalk_2018_19.csv`
   - **Sample mapping:**
     - TEA District #054901 → NCES LEAID 4800001 (CROSBYTON CISD)
     - TEA District #227901 → NCES LEAID 4821990 (Houston ISD)
   - **Note:** 2023-24 CCD preliminary files released July 2024 (more recent crosswalk available if needed)

2. **Downloaded Documentation:**
   - TAPR Guidelines 2023-24 (tapr_guidelines_2023_24.pdf)
   - TAPR Data Dictionary (tapr_data_dictionary.pdf - 26,695 lines, technical variable codes)
   - Enrollment Summary 2024-25 (enrollment_summary_2024_25.pdf)

3. **Data Portal Assessment:**
   - **PEIMS Standard Reports:** Web-based form system, not bulk downloads
   - **TAPR Downloads:** SAS-based dynamic generation system
   - **Format:** Comma-delimited CSVs available, but requires interactive selection
   - **FERPA Masking:** -999 for suppressed cells

### 🎯 Recommended Approach

Given Texas's web-based data access model, we have **three options**:

#### **Option A: Use Existing NCES CCD Data (Recommended)**
- **Pros:**
  - We already have NCES CCD data for all Texas districts
  - Includes enrollment, staffing, grade-level breakdowns
  - Direct NCES IDs for matching
  - Consistent with federal data we use for other states
- **Cons:**
  - Less detailed than state-specific data (no SPED environmental settings)
  - 1-2 year lag in federal data availability
- **Recommendation:** Start here for Phase 1, add Texas-specific data in Phase 2

#### **Option B: Manual PEIMS Report Generation**
- **Pros:**
  - Can get state-specific data (economically disadvantaged, detailed SPED)
  - CSV format available
- **Cons:**
  - Interactive web forms (not scriptable)
  - Would need to generate ~1,200 district reports manually
  - Time-intensive for marginal additional data
- **Recommendation:** Only for high-priority supplemental data

#### **Option C: Contact TEA for Bulk Data Access**
- **Pros:**
  - Potential bulk data files
  - Complete state dataset
- **Cons:**
  - May require formal data request process
  - Approval timeline unknown
  - May incur fees
- **Recommendation:** Pursue if we need Texas-specific details not in NCES

### 📋 Revised Next Steps

#### Phase 1: NCES CCD Integration (2-3 weeks)
1. **Use existing NCES CCD data** for Texas districts
2. **Build crosswalk:** Match NCES CCD ↔ TEA District Numbers using district names
3. **Import to database:** Follow California pattern for Layer 2 tables
4. **Validate:** Compare NCES totals against Texas enrollment summary (5.5M students)

#### Phase 2: Texas-Specific Enrichment (if needed)
1. **Assess gaps:** What critical data is missing from NCES?
2. **Priority areas:**
   - Economically disadvantaged students (if FRPM in NCES is insufficient)
   - SPED environmental settings (if needed for advanced analysis)
3. **Contact TEA:** Request bulk data access for supplemental datasets

---

## Technical Notes

### Download Process (Current Understanding)
- **PEIMS Reports:** Interactive web forms at `rptsvr1.tea.texas.gov`
- **TAPR Downloads:** SAS-generated, requires multi-step selection
- **Output Format:** CSV with metadata headers
- **FERPA Masking:** -999 for suppressed cells
- **Bulk Access:** Not publicly available, may require TEA data request

### Data Volume
- **Districts:** ~1,200 (1,217 in 2022-23 District Type file)
- **Students:** ~5.5 million (2024-25)
- **Data Years:** 2011-12 through 2024-25 available
- **NCES CCD:** Already downloaded, ready to process

### Crosswalk Strategy ✅ COMPLETE
1. **Source:** NCES CCD LEA Universe file (ST_LEAID field)
2. **Format:** "TX-" + 6-digit TEA district number → 7-digit NCES LEAID
3. **Coverage:** 1,235 Texas districts (2018-19 baseline)
4. **File:** `data/raw/state/texas/district_identifiers/texas_nces_tea_crosswalk_2018_19.csv`
5. **Columns:**
   - `TEA_DISTRICT_NO`: 6-digit TEA district number (e.g., "054901")
   - `NCES_LEAID`: 7-digit NCES identifier (e.g., "4800001")
   - `ST_LEAID`: Full state LEA ID (e.g., "TX-054901")
   - `DISTRICT_NAME`: Official district name
   - `LEA_TYPE_TEXT`: District type classification
   - `CHARTER_LEA_TEXT`: Charter status

### Integration Timeline Estimate (Revised)
- **✅ Complete:** Build NCES ↔ TEA crosswalk (found in CCD files)
- **✅ Complete:** Design Texas database schema (Migration 005)
- **✅ Complete:** Import TEA crosswalk to database (1,193 districts)
- **Next:** Create import scripts for NCES enrollment/staffing/SPED data
- **Week 1:** Import NCES data and validation
- **Week 2:** QA, validation report, and documentation
- **Future:** Phase 2 PEIMS enrichment if needed

## Integration Status (2026-01-11) ✅

### Completed Work:

**1. Database Schema (Migration 005):**
   - Added `st_leaid` column to `districts` table (multi-state enhancement)
   - Created `tx_district_identifiers` table (TEA crosswalk storage)
   - Created `tx_sped_district_data` table (placeholder for future PEIMS data)
   - Created `v_texas_districts` view (consolidated queries)

**2. Crosswalk Import:**
   - Imported 1,193 of 1,235 Texas districts (96.6% coverage)
   - Populated `st_leaid` for all districts
   - Identified charter schools and district types
   - Skipped 42 administrative units (Education Service Centers, state schools)

**3. Files Created:**
   - `infrastructure/database/migrations/005_add_texas_integration.sql` (schema)
   - `infrastructure/database/migrations/apply_texas_migration.py` (migration script)
   - `infrastructure/database/migrations/import_tx_crosswalk.py` (crosswalk import)
   - `data/raw/state/texas/district_identifiers/texas_nces_tea_crosswalk_2018_19.csv` (crosswalk data)

### Database Verification:

```sql
-- Count Texas districts in database
SELECT COUNT(*) FROM tx_district_identifiers;
-- Result: 1,193

-- View Texas districts with identifiers
SELECT * FROM v_texas_districts LIMIT 5;
-- Returns: NCES ID, district name, state, st_leaid, TEA district number, type, charter status

-- Example: Find Houston ISD
SELECT * FROM v_texas_districts WHERE tea_district_no = '227901';
```

### Next Phase: NCES Data Import

**Approach:** Import NCES CCD federal data for Texas districts
- Enrollment (total and by grade)
- Staffing (teachers, instructional staff)
- Special education enrollment
- Demographics

**Rationale:** Consistent with federal data approach, avoids manual PEIMS extraction, sufficient for Phase 1 LCT calculations

---

## Resources

### Primary Documentation
- [PEIMS Overview](https://tea.texas.gov/reports-and-data/data-submission/peims/peims-overview)
- [PEIMS Data Standards](https://tea.texas.gov/reports-and-data/data-submission/peims/peims-data-standards)
- [District Type Glossary](https://tea.texas.gov/reports-and-data/school-data/district-type-data-search/district-type-glossary-of-terms-2023-24)

### Support Contacts
- **Technical Support:** TSDSCustomerSupport@tea.texas.gov
- **TIMS Ticket System:** Available for technical issues

---

**Last Updated:** 2026-01-11
**Next Review:** After sample data acquisition
