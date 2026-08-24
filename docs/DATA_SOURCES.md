# Data Sources

> **Authority:** what each federal/state data source provides, how it's accessed, and its integration
> status — verify status claims against the live DB (Rule #6) before trusting them for anything LCT-facing.
> **Audience:** anyone adding a new state integration or tracing where a number in the DB came from.
> **Companions:** `SEA_INTEGRATION_GUIDE.md` (the how-to for building a new state integration),
> `docs/METHODOLOGY.md` §Data Source Precedence (the authoritative Tier 1/Tier 2 completeness breakdown).
> **Update this when:** a new data source or state integration is added, or an integration's actual DB
> coverage changes — verify in the DB before updating a status claim, don't just update the prose.

## Overview

This document catalogs all data sources for the Instructional Minute Metric project, including access methods, update frequencies, and known limitations.

> **Bell schedules / daily instructional minutes** are acquired by the per-school **acquisition pipeline**, not a static feed — see **`docs/ACQUISITION_PIPELINE.md`** (the canonical 9-stage discovery → capture → filter → council-extraction design) and its companion `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md`. The federal NCES sources below remain the foundation for district/school rosters, enrollment, and staffing (the LCT denominator/staff inputs); the acquisition pipeline supplies the instructional-minutes numerator.

## Federal Sources

### NCES Common Core of Data (CCD)

**Organization**: National Center for Education Statistics (NCES)
**URL**: https://nces.ed.gov/ccd/

#### Coverage
- **Scope**: All public schools and districts in the United States
- **Frequency**: Annual
- **Lag Time**: Typically 1-2 years behind current school year
- **Latest Available**: 2024-25 (ingested + LCT-calculated 2026-07; 17,751 districts in `enrollment_by_grade` — see `METHODOLOGY.md` §Data Source Precedence "Available Data Sources")

#### Key Tables

| Table Name | Contains | Use for LCT |
|-----------|----------|-------------|
| Directory | District basic info, location | District identification |
| Membership | Student enrollment by grade | Student count (denominator) |
| Staff | Teacher and staff counts by role | Instructional staff count (numerator) |
| Finance | Revenue and expenditures | Contextual analysis |

#### Access Methods

**Primary Source: NCES Direct**
1. **Bulk Download**: https://nces.ed.gov/ccd/data/
2. **Data Files**: Tab-delimited text (`.txt`), CSV, ZIP archives
3. **Format Notes**:
   - Large files often split into multiple parts (`_1`, `_2`, `_3`, etc.)
   - Fixed-width format in older years
   - Schema changes year-over-year (document carefully!)

**Alternative Source: data.gov** (Recommended for automated access)
1. **Catalog**: https://catalog.data.gov/dataset/?tags=nces
2. **School District Characteristics**: https://catalog.data.gov/dataset/school-district-characteristics-current-4aa03
   - Direct CSV download: `data-nces.opendata.arcgis.com/datasets/nces::school-district-characteristics-current-1.csv`
   - Years: 2017-18 through 2021-22 (updated May 2024)
   - Includes: Enrollment, teacher counts, directory info
   - Advantages: Direct CSV URLs, no manual download needed, stable links
   - Limitation: ~2 years behind NCES direct releases
3. **Historic CCD Files**: Individual year releases (e.g., 2018-19) with separate directory, membership, and staff files
4. **API Access**: data.gov catalog API for programmatic discovery

**When to Use Each**:
- **NCES Direct**: For most recent data (2023-24+)
- **data.gov**: For development/testing, automated pipelines, historic analysis (2017-2022)

#### Data Quality Notes
- Very comprehensive for enrollment
- Staff counts can be imprecise (FTE vs headcount varies)
- Some fields have high non-response rates
- Charter school reporting varies by state

#### Key Fields for LCT

**From Membership Table**:
- `LEAID`: District identifier
- `MEMBER`: Total student membership (October count)
- Grade-level breakdowns available

**From Staff Table**:
- `LEAID`: District identifier  
- `TEACHERS`: Number of teachers (FTE)
- `INSTRUCT_AIDE`: Instructional aides
- Various role-specific counts

---

### IDEA 618 Data Collection

**Organization**: U.S. Department of Education Office of Special Education Programs (OSEP)
**URL**: https://www2.ed.gov/about/reports/annual/osep/index.html

#### Coverage
- **Scope**: All states and territories (state-level data only)
- **Frequency**: Annual
- **Lag Time**: Typically 2-3 years
- **Latest Available**: 2021-22 (as of Jan 2026)
- **Used for SPED Baseline**: 2017-18 (pre-COVID)

#### Key Tables

| Table Name | Contains | Use for LCT |
|-----------|----------|-------------|
| Personnel | SPED teacher and paraprofessional FTE by state | SPED staffing ratios |
| Child Count & Educational Environments | SPED student counts by educational environment | Self-contained vs mainstreamed categorization |

#### Access Methods

**Download Portal**: https://www2.ed.gov/programs/osepidea/618-data/state-level-data-files/index.html

**Data Files**: CSV, Excel
- Files organized by year and data type
- Example files (2017-18):
  - `bpersonnel2017-18.csv` - Teacher and para FTE
  - `bchildcountandedenvironments2017-18.csv` - Student counts by environment

#### Educational Environment Categories

**Self-Contained SPED** (used for LCT SPED calculations):
- Separate Class
- Separate School
- Inside regular class less than 40% of the day

**Mainstreamed SPED** (counted as GenEd for LCT):
- Inside regular class 80% or more of the day
- Inside regular class 40% through 79% of the day

#### Key Fields for LCT

**From Personnel Table**:
- State identifier
- `SPEDTCH` columns: SPED teacher FTE (Ages 6-21)
- `SPEDPARA` columns: SPED paraprofessional FTE (Ages 6-21)

**From Child Count Table**:
- State identifier
- Student counts by educational environment (Ages 6-21)
- Used to calculate self-contained proportion

#### Usage in SPED Segmentation

IDEA 618 provides state-level baseline data (2017-18 pre-COVID) for:
1. State SPED teacher-to-self-contained-student ratios
2. State SPED instructional (teachers + paras) ratios
3. State self-contained proportion (self-contained / all SPED)

These ratios are applied to LEA-level estimates in a two-step process. See `docs/METHODOLOGY.md` §SPED Segmentation for full methodology.

---

### Civil Rights Data Collection (CRDC)

**Organization**: U.S. Department of Education Office for Civil Rights
**URL**: https://ocrdata.ed.gov/

#### Coverage
- **Scope**: Biennial survey of all public schools
- **Frequency**: Every 2 years
- **Lag Time**: 2-3 years
- **Latest Available**: 2021-22 public-use files, released January 2025 (2020-21 exists but is a COVID-excluded year — see `docs/state-integrations/STATE_DATA_AVAILABILITY_ASSESSMENT.md`; matches `METHODOLOGY.md`'s Available Data Sources table)

#### Key Data Elements
- Class sizes by subject
- Teacher assignments and qualifications
- Detailed demographic breakdowns
- Access to programs (AP, IB, etc.)
- Discipline and other civil rights indicators

#### Access Methods
1. **Download Portal**: https://ocrdata.ed.gov/assets/downloads/
2. **Data Files**: CSV, Excel
3. **API**: Limited API access available

#### Advantages Over CCD
- More detailed than CCD
- Class-level data (not just district totals)
- Better teacher assignment information

#### Limitations
- Less frequent (biennial vs annual)
- Not all schools surveyed every cycle
- Complex file structure requiring documentation study

#### Key Fields for LCT
- School-level student enrollment
- Teacher FTE by subject area
- Class size distributions
- **SPED enrollment** (LEA-level totals, no environment breakdown)
- Can enable more sophisticated LCT calculations

#### Usage in SPED Segmentation

CRDC 2017-18 provides LEA-level SPED enrollment totals used to calculate district-specific SPED proportions:
- `SCH_ENR_IDEA_M` + `SCH_ENR_IDEA_F` = Total SPED enrollment
- Used in two-step ratio: `LEA SPED Proportion = CRDC SPED / CCD Total Enrollment`
- Note: CRDC does not break down by educational environment (self-contained vs mainstreamed)

---

## State Sources

### General Approach

Each state maintains its own education data system. Quality, accessibility, and formats vary significantly.

#### State Priority Criteria
1. **Population Size**: Larger impact
2. **Data Quality**: Well-documented, accessible
3. **Diversity**: Variety in instructional time requirements
4. **API Availability**: Programmatic access preferred

### California

**Agency**: California Department of Education (CDE)
**URL**: https://www.cde.ca.gov/ds/
**Integration Status**: ✅ LCFF/SPED/FRPM data integrated and tested (January 2026). **Does NOT supersede
NCES staff/enrollment** — verified against the live DB 2026-07-02, CA `staff_counts`/`enrollment_by_grade`
are still 100% `nces_ccd`-sourced. This is a real, tested Layer-2 integration for the datasets it covers
(funding/attendance/SPED/meals), not the staff+enrollment pair LCT's core formula consumes — see
`METHODOLOGY.md` §Data Source Precedence "Future State Integrations (Tier 2)".

#### Data Portal
- **Name**: DataQuest
- **URL**: https://dq.cde.ca.gov/dataquest/
- **API**: Yes - https://api.cde.ca.gov/

#### Key Datasets (available via DataQuest — not all pulled into the DB, see below)
- Enrollment by school/district *(available at source; not integrated — CA enrollment in our DB is NCES)*
- Staff demographics and assignments *(available at source; not integrated — CA staff in our DB is NCES)*
- SARC (School Accountability Report Card) data
- **LCFF Snapshot** - Local Control Funding Formula data — **integrated**
- **SPED Counts** - Special Education enrollment — **integrated**
- **FRPM Counts** - Free/Reduced Price Meals — **integrated**

#### Local Data Files
Actual filenames have drifted from what this doc used to hand-list (now year-subdirectoried, e.g.
`2023_24/lcff_2023_24.xlsx`) — see `data/raw/state/california/MANIFEST.md` for the current, maintained
inventory (source of truth: `docs/state-integrations/state_data_catalog.yaml`).

#### Crosswalk
- Uses county-district format: `XX-XXXXX` (e.g., `19-64733` for LA Unified)
- NCES LEAID mapped via LCFF snapshot data

#### Integration Tests
- **Test file**: `tests/test_california_integration.py` (58 tests)
- **Validates**: Crosswalk accuracy, enrollment/staff against NCES baseline
- **Key districts**: Los Angeles Unified, San Diego Unified, Fresno Unified, Long Beach Unified, Santa Ana Unified, San Francisco Unified, Oakland Unified

#### Strengths
✅ Excellent API access
✅ Well-documented
✅ Comprehensive coverage
✅ Regular updates

#### Instructional Time Requirement
- **Elementary (K-8)**: 36,000 minutes per year (~200 minutes/day for 180-day year)
- **High School (9-12)**: 64,800 minutes per year (~360 minutes/day)

#### Notes
- Very large state - high impact
- Good demographic diversity in districts
- Charter school data included

---

### Texas

**Agency**: Texas Education Agency (TEA)
**URL**: https://tea.texas.gov/
**Integration Status**: ✅ NCES↔TEA identifier crosswalk complete (Migration 005, January 2026). **No
staff/enrollment PEIMS data integrated** — verified against the live DB 2026-07-02, TX
`staff_counts`/`enrollment_by_grade` are still 100% `nces_ccd`-sourced (`tx_sped_district_data` is a
placeholder table, not populated). See `METHODOLOGY.md` §Data Source Precedence "Future State Integrations
(Tier 2)".

#### Data Portal
- **Name**: PEIMS (Public Education Information Management System)
- **URL**: https://tea.texas.gov/reports-and-data

#### Database Integration (Migration 005)
- **Crosswalk**: NCES ↔ TEA via ST_LEAID field from NCES CCD files
- **Coverage**: 1,207 Texas districts in database (1,193 with TEA identifiers)
- **Tables Created**:
  - `tx_district_identifiers` - TEA district numbers, charter status, district types
  - `tx_sped_district_data` - Placeholder for future PEIMS enhancement
  - `v_texas_districts` - Consolidated view for easy querying
- **Key Discovery**: ST_LEAID field in NCES CCD contains state-assigned IDs for all 50 states
- **Status**: Infrastructure ready for PEIMS data enhancement in future phases

#### Key Datasets
- Student enrollment (NCES CCD)
- Personnel data (NCES CCD + PEIMS for enhancement)
- Academic performance (TEA TAPR reports)
- Financial data

#### Strengths
✅ Comprehensive data
✅ Well-documented system
✅ Large population (5.26M students in 2023-24)
✅ Regular updates
✅ Official NCES ↔ TEA crosswalk available

#### Instructional Time Requirement
- **All Grades**: 7 hours per day minimum (420 minutes)
- This is significantly higher than most states

#### Integration Tests
- **Test file**: `tests/test_texas_integration.py` (54 tests)
- **Validates**: NCES↔TEA crosswalk, enrollment/staff accuracy
- **Key districts**: Houston ISD, Dallas ISD, Cypress-Fairbanks ISD, Northside ISD, Katy ISD, Fort Bend ISD, Fort Worth ISD

#### Notes
- Second-largest state by population
- High instructional time requirement makes interesting comparison
- Growing population
- Integration validated: 5.26M students (2023-24 NCES) vs 5.54M (2024-25 TEA) shows reasonable year-over-year growth
- See `TEXAS_INTEGRATION_COMPLETE.md` for full integration report

---

### New York

**Agency**: New York State Education Department (NYSED)
**URL**: https://data.nysed.gov/

#### Data Portal
- **Name**: Information and Reporting Services
- **URL**: https://data.nysed.gov/
- **Open Data**: Yes

#### Key Datasets
- District enrollment and demographics
- Staff data
- School report cards
- Financial data

#### Strengths
✅ Good open data platform
✅ District-level data readily available
✅ Historical data accessible

#### Instructional Time Requirements
- **Kindergarten**: 2.5 hours/day minimum (150 minutes)
- **Grades 1-6**: 5 hours/day minimum (300 minutes)
- **Grades 7-12**: 5.5 hours/day minimum (330 minutes)

#### Notes
- Third-largest state by education population
- Wide variety of district types (urban, suburban, rural)
- Good for comparative analysis

---

### Florida

**Agency**: Florida Department of Education (FLDOE)
**URL**: http://www.fldoe.org/
**Integration Status**: ✅ Layer 2 Complete (January 2026)

#### Data Portal
- **Name**: EdStats
- **URL**: http://www.fldoe.org/accountability/data-sys/

#### Key Datasets
- Student enrollment
- Teacher data
- School grades and performance

#### Local Data Files
Actual filenames have drifted from what this doc used to hand-list (now e.g. `fl_fulltime_staff_2425.xlsx`,
`2425MembInFLPublicSchools.xlsx`) — see `data/raw/state/florida/MANIFEST.md` for the current, maintained
inventory (source of truth: `docs/state-integrations/state_data_catalog.yaml`).

#### Crosswalk
- Uses 2-digit district codes (e.g., `"13"` for Miami-Dade)
- Some codes require leading zeros (e.g., `"06"` for Broward)
- NCES LEAID: 7-digit federal ID (e.g., `"1200390"` for Miami-Dade)

#### Integration Tests
- **Test file**: `tests/test_florida_integration.py` (71 tests)
- **Validates**: Crosswalk, enrollment/staff, state totals, LCT calculations
- **Key districts**: Miami-Dade, Broward, Hillsborough, Orange, Duval, Palm Beach
- **Includes**: State-level aggregate validation

#### Strengths
✅ Growing state
✅ Diverse districts
✅ Good accountability data

#### Instructional Time Requirements
- **Grades K-3**: 720 hours per year (~240 minutes/day for 180-day year)
- **Grades 4-12**: 900 hours per year (~300 minutes/day)

#### Notes
- Fast-growing state
- Interesting policy environment
- Large number of charter schools

---

## Data Acquisition Schedule

### Recommended Phasing

**Phase 1: Federal Foundation**
1. NCES CCD (all years 2020-present)
2. CRDC (2020-21, 2018-19)

**Phase 2: Large States**
3. California
4. Texas
5. New York

**Phase 3: Regional Diversity**
6. Florida
7. Illinois
8. Pennsylvania
9. Ohio

**Phase 4: Policy Interest**
10. Additional states based on specific policy questions

### Update Frequency

| Source | Release Schedule | Recommended Check |
|--------|-----------------|-------------------|
| NCES CCD | Fall (Sept-Nov) | Quarterly |
| CRDC | Biennial (spring of odd years) | Annually |
| State (CA) | Varies by dataset | Monthly |
| State (TX) | Fall for most data | Quarterly |
| State (NY) | Varies | Quarterly |

---

## Data Dictionary Locations

Stale — the top-level `data-dictionaries/` tree this section used to describe no longer exists (archived
2026-06-27 to `docs/archive/data-dictionaries-superseded-20260627/`, and that archive turned out to hold a
database-schema doc, not per-source field dictionaries). Its would-be successor,
`data/raw/federal/metadata/data-dictionaries/`, exists but is currently empty. For field-level schema
today, use `infrastructure/database/models.py` (the schema authority per root `CLAUDE.md`) or the
originating source's own published data dictionary (NCES CCD, IDEA 618, CRDC — URLs above).

---

## Known Data Challenges

### Multi-Part Files
- Many NCES datasets split across numbered files (`_1`, `_2`, `_3`)
- Requires concatenation before processing
- See `infrastructure/scripts/extract/split_large_files.py`

### Schema Changes
- Field names change year-over-year
- Data types may change
- Requires version-specific handling

### Missing Data
- Not all districts report all fields
- FTE calculations vary
- Some charter schools report differently

### Timing Mismatches
- Federal data uses October counts
- State data may use different reference dates
- Fiscal vs academic year differences

### Staff Counts
- FTE vs headcount inconsistencies
- Definition of "instructional staff" varies
- Contracted vs employed staff

---

## Data Quality Checklist

Before using any new data source:

- [ ] Download data dictionary
- [ ] Identify all multi-part files
- [ ] Check for schema changes from previous year
- [ ] Verify field definitions match expectations
- [ ] Calculate missing data percentages for key fields
- [ ] Test on sample districts
- [ ] Document any anomalies or concerns
- [ ] Establish validation rules

---

## Adding New Sources

When adding a new state or data source:

1. Create directory: `data/raw/state/[state-name]/`
2. Document in this file (use template above)
3. Add to `config/data-sources.yaml`
4. Add instructional time requirements to `config/state-requirements.yaml`
5. Create download script in `infrastructure/scripts/download/`
6. Create import script in `infrastructure/database/migrations/import_[state]_data.py` (the `src/python/processors/`
   path this step used to name no longer exists — see `SEA_INTEGRATION_GUIDE.md` "Adding a New State" for the
   current pattern, incl. shared helpers in `sea_import_utils.py`)
7. **Create SEA integration tests**: `tests/test_[state]_integration.py` (see `CLAUDE.md` for template)
8. Add validation tests
9. Update documentation

---

**Sources Documented**: 3 federal (NCES CCD, CRDC, IDEA 618), 9 state SEA integrations (7 feeding LCT
staff+enrollment: FL, IL, MA, MI, NY, PA, VA; 2 narrower-scope: CA funding/SPED/FRPM, TX ID-crosswalk only
— see `METHODOLOGY.md` §Data Source Precedence for the authoritative, DB-verified breakdown), bell
schedules (acquisition pipeline, see `docs/ACQUISITION_PIPELINE.md`).
**Integration Tests**: see `tests/test_*_integration.py`, one suite per state.
**Status**: not tracked here — see root `CLAUDE.md` and GitHub Issues for current build status.
