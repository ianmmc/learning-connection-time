# State Education Data Availability Assessment

**Assessment Date:** January 11, 2026
**Purpose:** Evaluate state education data portals for Learning Connection Time (LCT) metric integration
**States Assessed:** 46 U.S. states (excluding CA, TX, FL, NY which are already planned) + 6 territories

---

## Data Requirements Summary

For LCT metric calculation, we need from each state:
- **Enrollment Data:** District-level total enrollment, grade-level breakdowns, SPED enrollment
- **Staffing Data:** Teachers (general education), SPED teachers, paraprofessionals/instructional aides
- **Special Education Data:** SPED enrollment counts, educational environment/setting
- **Identifiers:** State LEA IDs, NCES IDs (for crosswalk)
- **Socioeconomic Data (Nice-to-Have):** FRPM eligibility, English Language Learners

---

## State Data Availability Matrix

| State | Data Portal URL | Enrollment | Staffing | SPED | Format | Data Year | Priority | Notes |
|-------|----------------|------------|----------|------|--------|-----------|----------|-------|
| **NORTHEAST** |
| Connecticut | https://public-edsight.ct.gov/ | ✅ | ✅ | ✅ | CSV/Excel | 2024-25 | **High** | EdSight portal, excellent data quality, includes staffing FTE |
| Delaware | https://data.delaware.gov/Education/ | ✅ | ✅ | ⚠️ | CSV/Excel | 2024-25 | **High** | Open Data Portal + Report Card, annual releases Feb |
| Maine | https://www.maine.gov/doe/data-reporting/warehouse | ✅ | ✅ | ✅ | CSV/Excel | 2024 | **High** | Data Warehouse with FTE staff, SPED by environment |
| Maryland | https://reportcard.msde.maryland.gov/ | ✅ | ⚠️ | ✅ | Excel/PDF | 2024-25 | **Medium** | Report Card portal, SPED Census available |
| Massachusetts | https://profiles.doe.mass.edu/statereport/ | ✅ | ✅ | ✅ | CSV/Excel | 2024-25 | **High** | Comprehensive School & District Profiles, FTE data |
| New Hampshire | https://www.education.nh.gov/data-reports | ✅ | ✅ | ✅ | Excel | 2024 | **Medium** | District Staff Reports, NHSEIS for SPED |
| New Jersey | https://www.nj.gov/education/doedata/ | ✅ | ✅ | ⚠️ | Excel/CSV | 2024-25 | **High** | Data & Reports Portal, Certified Staff Reports |
| Pennsylvania | https://www.pa.gov/agencies/education/data-and-reporting | ✅ | ✅ | ✅ | Excel/CSV | 2024-25 | **High** | PennData for SPED, Educator Workforce Reports |
| Rhode Island | https://datacenter.ride.ri.gov/ | ✅ | ⚠️ | ✅ | Excel | 2023-24 | **Medium** | RIDE Data Center, 618 data collections |
| Vermont | https://education.vermont.gov/data-and-reporting/vermont-education-dashboard | ✅ | ✅ | ✅ | Excel/Dashboard | 2024 | **High** | Dashboard with enrollment, staffing, SPED reports |
| **SOUTHEAST** |
| Alabama | https://www.alabamaachieves.org/reports-data/ | ✅ | ✅ | ✅ | Excel | 2024-25 | **High** | Reports & Data portal, Financial Reports with staffing |
| Arkansas | https://adedata.arkansas.gov/ | ✅ | ⚠️ | ✅ | Excel | 2024 | **Medium** | ADE Data Center, ARKSPED Portal separate |
| Georgia | https://georgiainsights.gadoe.org/ | ✅ | ⚠️ | ✅ | Excel/CSV | 2024 | **Medium** | Georgia Insights + GOSA downloadable data |
| Kentucky | https://www.education.ky.gov/Open-House/data/ | ✅ | ✅ | ⚠️ | Excel | 2023-24 | **Medium** | School Report Card Dashboard, Personnel Info |
| Louisiana | https://doe.louisiana.gov/data-and-reports | ✅ | ⚠️ | ✅ | Excel | 2024 | **Medium** | Enrollment Data + Special Ed Reporting pages |
| Mississippi | https://newreports.mdek12.org/ | ✅ | ⚠️ | ⚠️ | Excel | 2023-24 | **Medium** | MDEReports with Data Explorer and Downloads |
| North Carolina | https://www.dpi.nc.gov/data-reports | ✅ | ⚠️ | ✅ | Excel | 2024 | **High** | Data & Reports, Exceptional Children data |
| South Carolina | https://ed.sc.gov/data/ | ✅ | ✅ | ⚠️ | Excel | 2024 | **Medium** | Student Counts, Educator Profession Reports |
| Tennessee | https://tdepublicschools.ondemand.sas.com/ | ✅ | ✅ | ⚠️ | Excel/CSV | 2024-25 | **High** | State Report Card, Data Downloads page |
| Virginia | https://www.doe.virginia.gov/data-policy-funding/data-reports | ✅ | ✅ | ✅ | Excel | 2024-25 | **High** | Statistics & Reports, Teacher Staffing Dashboard |
| West Virginia | https://wvde.us/data-school-improvement/education-data | ✅ | ⚠️ | ⚠️ | Excel | 2024-25 | **Medium** | ZoomWV interactive portal, WVEIS system |
| **MIDWEST** |
| Illinois | https://www.illinoisreportcard.com/ | ✅ | ✅ | ✅ | Excel | 2024 | **High** | Illinois Report Card + Data Library, comprehensive |
| Indiana | https://www.in.gov/doe/it/data-center-and-reports/ | ✅ | ⚠️ | ⚠️ | Excel | 2024 | **Medium** | DOE Data Center, GPS dashboard |
| Iowa | https://reports.educateiowa.gov/COE/ | ✅ | ✅ | ✅ | Excel | 2024-25 | **High** | Condition of Education portal, staff by district |
| Kansas | https://datacentral.ksde.org/ | ✅ | ⚠️ | ⚠️ | Excel | 2024-25 | **Medium** | Data Central, EDCS for educators, SPEDPro |
| Michigan | https://mischooldata.org/ | ✅ | ✅ | ✅ | Excel | 2024 | **High** | MI School Data portal, comprehensive staffing |
| Minnesota | https://education.mn.gov/MDE/Data/ | ✅ | ⚠️ | ✅ | Excel | 2023-24 | **Medium** | Data Center interactive tool, Special Ed Division |
| Missouri | https://dese.mo.gov/school-data | ✅ | ⚠️ | ✅ | Excel | 2023-24 | **Medium** | School Data portal, Special Ed Data Collections |
| Nebraska | https://www.education.ne.gov/dataservices/data-reports/ | ✅ | ✅ | ⚠️ | Excel | 2024-25 | **Medium** | NSSRS system, Staff Reporting due Sept 15 |
| North Dakota | https://insights.nd.gov/ | ✅ | ⚠️ | ⚠️ | Excel | 2023-24 | **Medium** | Insights.nd.gov portal, Financial Facts publication |
| Ohio | https://education.ohio.gov/Topics/Data | ✅ | ⚠️ | ✅ | Excel/CSV | 2024-25 | **High** | Enrollment Data, Special Education Profiles |
| South Dakota | https://doe.sd.gov/data/ | ✅ | ✅ | ✅ | Excel | 2023-24 | **Medium** | Data Dashboards, Staffing Data, SPP reports |
| Wisconsin | https://dpi.wi.gov/wisedash | ✅ | ⚠️ | ✅ | CSV/Excel | 2023-24 | **High** | WISEdash Public Portal, WISEdata warehouse |
| **WEST** |
| Alaska | https://education.alaska.gov/data-center | ✅ | ✅ | ✅ | Excel | 2023-24 | **Medium** | Data Center, SPED District Data Profile |
| Arizona | https://www.azed.gov/data/public-data-sets/ | ✅ | ⚠️ | ✅ | Excel | 2024-25 | **High** | Public Data Sets, Accountability & Research Data |
| Colorado | https://ed.cde.state.co.us/cdereval | ✅ | ✅ | ✅ | Excel | 2024-25 | **High** | Colorado Education Statistics, SchoolView portal |
| Hawaii | https://arch.k12.hi.us/reports/hidoe-data-book | ✅ | ⚠️ | ⚠️ | Excel/PDF | 2023-24 | **Low** | ARCH data portal, single district state |
| Idaho | https://boardofed.idaho.gov/k-12-education/isee-idaho-system-for-educational-excellence/ | ✅ | ✅ | ✅ | Excel | 2024-25 | **Medium** | ISEE system, Idaho Ed Trends portal |
| Montana | https://opi.mt.gov/ | ✅ | ⚠️ | ⚠️ | Excel | 2023-24 | **Low** | OPI data services, limited online portal access |
| Nevada | https://doe.nv.gov/DataCenter/Enrollment/ | ✅ | ✅ | ⚠️ | Excel | 2024-25 | **Medium** | Nevada Accountability Portal, new Educator Workforce portal |
| New Mexico | https://webnew.ped.state.nm.us/ | ✅ | ⚠️ | ✅ | Excel | 2023-24 | **Medium** | NM Vistas, STARS system, District SPED data |
| Oklahoma | https://oklahoma.gov/education/school-data | ✅ | ⚠️ | ✅ | Excel | 2024-25 | **Medium** | School Data portal, Special Ed Data page |
| Oregon | https://www.ode.state.or.us/data/reportcard/reports.aspx | ✅ | ⚠️ | ✅ | Excel | 2024 | **High** | At-A-Glance Profiles, Special Ed District Profiles |
| Utah | https://datagateway.schools.utah.gov/ | ✅ | ⚠️ | ⚠️ | Excel | 2024 | **Medium** | USBE Data Gateway, Reports section |
| Washington | https://ospi.k12.wa.us/ | ✅ | ⚠️ | ⚠️ | Excel | 2023-24 | **Medium** | OSPI data (limited direct portal info), JLARC reports |
| Wyoming | https://edu.wyoming.gov/data/ | ✅ | ✅ | ⚠️ | Excel | 2024 | **Medium** | School District Enrollment & Staffing Data |
| **TERRITORIES** |
| District of Columbia | https://osse.dc.gov/page/data-and-reports-0 | ✅ | ⚠️ | ✅ | Excel | 2024 | **High** | OSSE Data & Reports, SLED system |
| Puerto Rico | NCES data only | ⚠️ | ⚠️ | ⚠️ | NCES | 2022-23 | **Low** | No dedicated PRDE data portal found, rely on NCES |
| US Virgin Islands | https://www.vide.vi/ | ⚠️ | ⚠️ | ⚠️ | NCES | 2022-23 | **Low** | VIDE website, data primarily via NCES |
| Guam | https://www.gdoe.net/ | ⚠️ | ⚠️ | ⚠️ | NCES | 2023-24 | **Low** | GOSDV data system, limited public access |
| American Samoa | https://www.amsamoadoe.com/ | ⚠️ | ⚠️ | ⚠️ | NCES | 2023-24 | **Low** | ASDOE website, data primarily via NCES |
| Northern Mariana Islands | https://slds.cnmipss.org/ | ⚠️ | ⚠️ | ⚠️ | SLDS | 2024-25 | **Low** | CNMI SLDS + EnVision PSS, limited public data |

**Legend:**
- ✅ = Data readily available in downloadable format
- ⚠️ = Data partially available or format unclear
- ❌ = Data not available or restricted access

---

## Top 10 High-Priority States for Integration

Based on data availability, format quality, and recency, these states are the best candidates for next integration:

### Tier 1: Excellent Data Availability (Immediate Integration Candidates)

1. **Illinois** - Outstanding comprehensive data through Illinois Report Card Data Library
   - **Why:** District staffing, finance, and special education data all in Excel format
   - **Portal:** https://www.illinoisreportcard.com/
   - **Data Year:** 2024
   - **Similar to CA:** Yes, comprehensive API-like data access

2. **Michigan** - MI School Data portal is exemplary for multi-level analysis
   - **Why:** Pre-K through postsecondary data, staffing by role, SPED by disability
   - **Portal:** https://mischooldata.org/
   - **Data Year:** 2024
   - **Similar to CA:** Yes, well-structured downloadable datasets

3. **Pennsylvania** - PennData special education system + comprehensive workforce data
   - **Why:** Detailed SPED statistics, educator workforce annual reports
   - **Portal:** https://www.pa.gov/agencies/education/data-and-reporting
   - **Data Year:** 2024-25
   - **Similar to CA:** Yes, separate SPED reporting system like CA

4. **Virginia** - Strong data infrastructure with teacher staffing dashboard
   - **Why:** Statistics & Reports section, dedicated teacher/staff vacancy dashboard
   - **Portal:** https://www.doe.virginia.gov/data-policy-funding/data-reports
   - **Data Year:** 2024-25
   - **Similar to CA:** Moderate, good organization but less granular

5. **Massachusetts** - School and District Profiles with FTE teacher data
   - **Why:** Comprehensive enrollment by grade, FTE staffing, student/teacher ratios
   - **Portal:** https://profiles.doe.mass.edu/statereport/
   - **Data Year:** 2024-25
   - **Similar to CA:** Yes, excellent data quality and accessibility

### Tier 2: Very Good Data Availability (High Value, Minor Work Needed)

6. **Iowa** - Condition of Education (COE) portal with staff by district
   - **Why:** Interactive filters, staff data by position/salary/benefits, enrollment trends
   - **Portal:** https://reports.educateiowa.gov/COE/
   - **Data Year:** 2024-25
   - **Integration Considerations:** Excel downloads require some parsing

7. **Wisconsin** - WISEdash Public Portal backed by WISEdata warehouse
   - **Why:** Multi-year dashboards, demographic disaggregation, special ed by environment
   - **Portal:** https://dpi.wi.gov/wisedash
   - **Data Year:** 2023-24
   - **Integration Considerations:** Data sourced from WISEdata since 2016-17

8. **Colorado** - Colorado Education Statistics portal + SchoolView
   - **Why:** District dashboard, staff statistics by role, SPED child count data
   - **Portal:** https://ed.cde.state.co.us/cdereval
   - **Data Year:** 2024-25
   - **Integration Considerations:** Multiple portals to integrate

9. **Connecticut** - EdSight interactive portal with excellent usability
   - **Why:** Visual multi-year reports, staffing levels FTE, PSIS data collection
   - **Portal:** https://public-edsight.ct.gov/
   - **Data Year:** 2024-25
   - **Integration Considerations:** May need to scrape dashboard vs. direct downloads

10. **Vermont** - Education Dashboard with comprehensive metrics
    - **Why:** Student/teacher ratios, average teacher salary, SPED annual performance reports
    - **Portal:** https://education.vermont.gov/data-and-reporting/vermont-education-dashboard
    - **Data Year:** 2024
    - **Integration Considerations:** Dashboard interface, need to identify download endpoints

---

## Honorable Mentions (Next Tier)

These states have good data but require slightly more work:

- **Ohio** - Special Education Profiles + enrollment data (format variation)
- **Tennessee** - State Report Card + Data Downloads (SAS-based portal)
- **North Carolina** - Data & Reports + Exceptional Children data (good SPED data)
- **Alabama** - Reports & Data portal (well-organized financial reports)
- **Arizona** - Public Data Sets + Accountability data (good SPED dashboard)
- **New Jersey** - Data & Reports Portal (excellent certified staff reports)
- **Oregon** - At-A-Glance Profiles (strong SPED district profiles)
- **Delaware** - Open Data Portal (modern API, data released annually in Feb)

---

## States Requiring Special Approaches

### API/Data Request Required
- **Georgia** - GOSA Downloadable Data Repository exists but may require registration
- **Kansas** - Data Central portal has security warnings, may need direct contact
- **New Mexico** - District View requires login/password for unmasked data

### Limited SPED Data Specificity
- **Indiana** - General enrollment good, SPED less detailed
- **Kentucky** - Enrollment/staffing good, SPED reporting manual-heavy
- **Mississippi** - Data Explorer available but SPED granularity unclear
- **Missouri** - Good enrollment reports, SPED data collections less accessible
- **Rhode Island** - 618 data collections available but format unclear

### Single District States (Different Approach Needed)
- **Hawaii** - Single district state, different organizational structure
- **District of Columbia** - OSSE operates differently than traditional state education agencies

---

## States with Severe Data Limitations

### Territories (Rely Primarily on NCES Federal Data)
- **Puerto Rico** - No dedicated PRDE data portal found
- **US Virgin Islands** - VIDE website exists but data primarily via NCES
- **Guam** - GOSDV data system exists but limited public access
- **American Samoa** - ASDOE website exists but data primarily via NCES
- **Northern Mariana Islands** - CNMI SLDS exists but limited public downloadable data

### States with Portal Access Issues
- **Montana** - OPI data services exist but limited online portal functionality
- **Washington** - OSPI website exists but direct data portal unclear (found JLARC reports instead)

---

## Data Integration Strategy Recommendations

### Phase 1: Quick Wins (Months 1-3)
Integrate the Tier 1 states (Illinois, Michigan, Pennsylvania, Virginia, Massachusetts) as they have:
- Modern data portals with downloadable datasets
- Similar structure to California's data organization
- Current 2024-25 data available
- All required data types (enrollment, staffing, SPED)

### Phase 2: High-Value States (Months 4-6)
Integrate Tier 2 states (Iowa, Wisconsin, Colorado, Connecticut, Vermont) which require:
- Dashboard scraping or download endpoint identification
- Format standardization work
- Multiple portal integration in some cases

### Phase 3: Fill Gaps (Months 7-9)
Integrate Honorable Mentions states focusing on:
- States with excellent SPED data (North Carolina, Arizona)
- Large population states (Ohio, Tennessee, New Jersey)
- States filling geographic gaps in coverage

### Phase 4: Complete Coverage (Months 10-12)
Address remaining states with:
- API access or data request processes
- Manual data collection where needed
- Workarounds for limited portal access

### Phase 5: Territories (As Resources Allow)
- Focus on DC (high-quality OSSE data available)
- Supplement with NCES federal data for other territories

---

## Technical Considerations

### Data Format Patterns Observed
- **Excel/CSV:** Most common (40+ states)
- **Interactive Dashboards:** 15-20 states (may need scraping)
- **PDF Reports:** 5-10 states (OCR/extraction needed)
- **API Access:** 3-5 states (Delaware, potentially others)

### Common Data Collection Cycles
- **Fall Enrollment Count:** October 1 (most states)
- **Staff Reporting:** September 15 - October 31 (varies by state)
- **SPED Child Count:** December 1 (federal requirement)
- **Public Release:** Typically February-April of following year

### NCES ID Crosswalk Availability
- Most states include NCES IDs in their data exports
- States without NCES IDs will need crosswalk from federal CCD data
- Our existing `infrastructure/utilities/nces_cds_crosswalk.py` can support this

### Data Quality Flags to Watch For
- **FTE vs. Headcount:** States vary in staff reporting (need standardization)
- **District vs. School Level:** Some states only provide school-level (need aggregation)
- **SPED Setting Definitions:** Educational environment classifications vary by state
- **Charter School Inclusion:** Some states report charters separately

---

## Integration Template Checklist

For each state integration, ensure:

1. **Data Download**
   - [ ] Identify download URLs for enrollment, staffing, SPED
   - [ ] Document data collection cycle and update schedule
   - [ ] Verify data year matches our primary dataset (2023-24)

2. **Field Mapping**
   - [ ] Map state LEA ID to NCES ID
   - [ ] Map enrollment fields (total, by grade, by SPED status)
   - [ ] Map staffing fields (teachers, SPED teachers, paraprofessionals)
   - [ ] Map SPED fields (count, setting/environment)

3. **Script Development**
   - [ ] Create `import_[state]_[datatype].py` scripts
   - [ ] Follow pattern from `import_ca_*.py` existing scripts
   - [ ] Include data lineage and source attribution

4. **Database Integration**
   - [ ] Add state-specific tables if needed (like ca_frpm, ca_lcff)
   - [ ] Update `apply_layer2_migration.py` with state data
   - [ ] Verify NCES ID crosswalk accuracy

5. **Validation**
   - [ ] Run `validate_[state]_integration.py` script
   - [ ] Compare totals against NCES federal data
   - [ ] Generate validation report

6. **Documentation**
   - [ ] Update `docs/DATA_SOURCES.md` with state portal info
   - [ ] Add state-specific notes to methodology
   - [ ] Document any data quality issues or limitations

---

## Conclusion

Of the 46 U.S. states assessed (excluding CA, TX, FL, NY), **10 states** are ready for immediate integration with excellent data availability:

**Tier 1 (Immediate):** Illinois, Michigan, Pennsylvania, Virginia, Massachusetts
**Tier 2 (High Value):** Iowa, Wisconsin, Colorado, Connecticut, Vermont

These 10 states represent diverse geographic regions and provide high-quality, recent (2024-25) data across all required categories. They should serve as the foundation for expanding LCT metric calculation beyond California.

An additional **8 states** (Honorable Mentions) are strong candidates once the first 10 are complete, providing good geographic coverage and data quality with minor additional work required.

The remaining **28 states** range from medium priority (requiring API access or format work) to low priority (territories relying on NCES federal data). These can be integrated in later phases as resources and methodology mature.

---

**Assessment Completed:** January 11, 2026
**Next Step:** Begin Phase 1 integration with Illinois as pilot state (comprehensive data similar to California)
