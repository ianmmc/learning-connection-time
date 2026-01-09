# Data Sources

## Overview

This document catalogs all data sources for the Instructional Minute Metric project, including access methods, update frequencies, and known limitations.

## Federal Sources

### NCES Common Core of Data (CCD)

**Organization**: National Center for Education Statistics (NCES)
**URL**: https://nces.ed.gov/ccd/

#### Coverage
- **Scope**: All public schools and districts in the United States
- **Frequency**: Annual
- **Lag Time**: Typically 1-2 years behind current school year
- **Latest Available**: 2022-23 (as of Dec 2025)

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

These ratios are applied to LEA-level estimates in a two-step process. See `docs/SPED_SEGMENTATION_IMPLEMENTATION.md` for full methodology.

---

### Civil Rights Data Collection (CRDC)

**Organization**: U.S. Department of Education Office for Civil Rights
**URL**: https://ocrdata.ed.gov/

#### Coverage
- **Scope**: Biennial survey of all public schools
- **Frequency**: Every 2 years
- **Lag Time**: 2-3 years
- **Latest Available**: 2020-21 (as of Dec 2025)

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

#### Data Portal
- **Name**: DataQuest
- **URL**: https://dq.cde.ca.gov/dataquest/
- **API**: Yes - https://api.cde.ca.gov/

#### Key Datasets
- Enrollment by school/district
- Staff demographics and assignments
- SARC (School Accountability Report Card) data

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

#### Data Portal
- **Name**: PEIMS (Public Education Information Management System)
- **URL**: https://tea.texas.gov/reports-and-data

#### Key Datasets
- Student enrollment
- Personnel data (PEIMS)
- Academic performance
- Financial data

#### Strengths
✅ Comprehensive data
✅ Well-documented system
✅ Large population
✅ Regular updates

#### Instructional Time Requirement
- **All Grades**: 7 hours per day minimum (420 minutes)
- This is significantly higher than most states

#### Notes
- Second-largest state by population
- High instructional time requirement makes interesting comparison
- Growing population

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

#### Data Portal
- **Name**: EdStats
- **URL**: http://www.fldoe.org/accountability/data-sys/

#### Key Datasets
- Student enrollment
- Teacher data
- School grades and performance

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

Detailed field-level documentation for each source:
- `data-dictionaries/nces-ccd/` - CCD field definitions by year
- `data-dictionaries/crdc/` - CRDC data dictionary
- `data-dictionaries/states/[state]/` - State-specific documentation

---

## Known Data Challenges

### Multi-Part Files
- Many NCES datasets split across numbered files (`_1`, `_2`, `_3`)
- Requires concatenation before processing
- See `infrastructure/scripts/extract/split-large-files.py`

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
6. Create processor in `src/python/processors/`
7. Add validation tests
8. Update documentation

---

**Last Updated**: January 3, 2026
**Sources Documented**: 3 federal (NCES CCD, CRDC, IDEA 618), 4 state, bell schedules (128 districts)
**Status**: Active development - Phase 1.5 (Bell Schedule Enrichment & SPED Segmentation)
