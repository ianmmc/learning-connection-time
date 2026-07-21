# SEA Data Acquisition Plan — Phase C

**Generated:** 2026-07-20 from `state_data_catalog.yaml` (Phase B probe results, PR #601/#602).
**Status: AWAITING IAN'S SIGN-OFF.** Nothing in this list has been downloaded. Per the campaign plan, this is the hard human gate before any bulk acquisition (Phase D) begins.

## What's in scope

33 entities have at least 2 of 3 core categories (enrollment/staffing/SPED) confirmed via a direct-download file or API endpoint — genuinely ready to acquire without further manual portal work. This list is everything a Phase D acquisition agent could pull today.

Explicitly OUT of scope for this list (Tier 2/3, need manual/dashboard work first, or blocked): see the assessment doc's Tier 2/3 tables. Nothing there should be bulk-downloaded yet.

**Note on crosswalk_ids rows below:** these are a bonus if a state happens to publish its own state-ID<->NCES-LEAID file — NOT something to wait on. The real crosswalk (REQ-027, 17,842 rows) already exists from NCES CCD's ST_LEAID column, ingested months before this campaign. See the assessment doc's crosswalk correction note.

**Caveat — "confirmed direct-download" is not always one bulk statewide file.** A handful of entries below resolve to a *per-district* file pattern rather than a single statewide download — e.g. **CT**'s URL is one example district's PDF (the state publishes ~200 of these, one per LEA code) and **AL**'s SPED source is ~140 separate per-district PDFs. The blockquoted note under each state below carries this caveat when it applies — a Phase D acquisition agent must read it before assuming a single fetch suffices, since enumerating district codes to build the full URL list is itself work that hasn't been scoped here.

---

## AK — Alaska
> Previously-undocumented ArcGIS REST API — strong new lead, not in the Jan-2026 assessment.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | API (ArcGIS REST) | api | https://maps.commerce.alaska.gov/server/rest/services/Education_Related/Education_District_Data/MapServer/2/query?where=1=1&outFields=*&returnGeometry=false&f=json |
| staffing | 2025-26 | API (ArcGIS REST) | api | https://maps.commerce.alaska.gov/server/rest/services/Education_Related/Education_District_Data/MapServer/0/query?where=1=1&outFields=*&returnGeometry=false&f=json |
| frpm_ell | 2025-26 | API (ArcGIS REST) | api | https://maps.commerce.alaska.gov/server/rest/services/Education_Related/Education_District_Data/MapServer/1/query?where=1=1&outFields=*&returnGeometry=false&f=json |

## AL — Alabama
> Enrollment/staffing/FRPM ready to acquire; SPED needs ~140 per-district PDF pulls.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://www.alabamaachieves.org/wp-content/uploads/2025/12/RD_FR_2025124_SY2025-2026ADMReport_v1.xlsx |
| staffing | 2026-27 (FY2027 enacted) | Excel | direct-download | https://www.alabamaachieves.org/wp-content/uploads/2026/05/RD_FIN_FR_2026518_FY2027SummaryofTeacherType_v1.xlsx |
| sped | 2025-26 (Oct-1-2025 count) | PDF (by system, by age/exceptionality) | direct-download | https://www.alabamaachieves.org/wp-content/uploads/2026/06/RD_SPECED_20260602_2025ChildCountbySystem_v1.pdf<br>https://www.alabamaachieves.org/wp-content/uploads/2026/06/RD_SPECED_20260610_2025ChildCountbyExcept_v1.pdf |
| frpm_ell | 2025-26 | Excel | direct-download | https://www.alabamaachieves.org/wp-content/uploads/2025/12/RD_FR_2025124_SY2025-2026FreeLunchBySystemandSchool_v1.xlsx |

## AS — American Samoa
> Correction to Jan-2026 "NCES-only" — real SPED/LRE data exists and is current (FFY24); enrollment/staffing/FRPM stuck at 2020-21.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2020-21 | PDF | direct-download | https://www.amsamoadoe.com/_files/ugd/bcdca0_49f0ddf237e5483cbf29a32ab2d69ea2.pdf |
| staffing | 2020-21 | PDF | direct-download | https://www.amsamoadoe.com/_files/ugd/bcdca0_49f0ddf237e5483cbf29a32ab2d69ea2.pdf |
| sped | 2024-25 | PDF (IDEA Part B SPP/APR) | direct-download | https://www.amsamoadoe.com/_files/ugd/b063e1_397eb282fee6457a84e7e7f612cba147.pdf |
| crosswalk_ids | 2022-23 | NCES CCD School Search (single statewide LEA, ID 6000030) | dashboard-export | https://nces.ed.gov/ccd/schoolsearch/school_list.asp |
| frpm_ell | 2020-21 | PDF | direct-download | https://www.amsamoadoe.com/_files/ugd/bcdca0_49f0ddf237e5483cbf29a32ab2d69ea2.pdf |

## CT — Connecticut
> Rich per-district PDFs (all 5 categories in one doc) but need per-district URL construction, not a bulk file.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | PDF (per-district profile) | direct-download | https://edsight.ct.gov/Output/District/HighSchool/2040012_202425.pdf |
| staffing | 2024-25 | PDF (per-district profile) | direct-download | https://edsight.ct.gov/Output/District/HighSchool/2040012_202425.pdf |
| sped | 2024-25 | PDF (per-district profile) | direct-download | https://edsight.ct.gov/Output/District/HighSchool/2040012_202425.pdf |
| frpm_ell | 2024-25 | PDF (per-district profile) | direct-download | https://edsight.ct.gov/Output/District/HighSchool/2040012_202425.pdf |

## DC — District of Columbia
> One file covers enrollment+SWD+EL+econ-disadvantaged together; staffing is headcount not FTE, no crosswalk found.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://osse.dc.gov/sites/default/files/dc/sites/osse/page_content/attachments/DC%20School%20Report%20Card%20Aggregate%20Enrollment%20Data%20%282025%29.xlsx |
| staffing | 2022-23 | Excel | direct-download | https://osse.dc.gov/sites/default/files/dc/sites/osse/page_content/attachments/2022-23%20DC%20Educator%20Workforce%20Data%20File%20%28Counts%20and%20Demographics%29.xlsx |
| frpm_ell | 2024-25 | Excel | direct-download | https://osse.dc.gov/sites/default/files/dc/sites/osse/page_content/attachments/DC%20School%20Report%20Card%20Aggregate%20Enrollment%20Data%20%282025%29.xlsx |

## DE — Delaware
> Best-in-batch: real Socrata API with a clean SPED-teacher-FTE split, ready to acquire programmatically.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | CSV/API (Socrata) | api | https://data.delaware.gov/resource/6i7v-xnmf.json |
| staffing | 2024-25 | CSV/API (Socrata) | api | https://data.delaware.gov/resource/rv4m-vy79.json |
| sped | 2024-25 | CSV/API (Socrata) | api | https://data.delaware.gov/resource/6i7v-xnmf.json |
| frpm_ell | 2024-25 | CSV/API (Socrata) | api | https://data.delaware.gov/resource/6i7v-xnmf.json |

## GA — Georgia
> Portal moved (georgiainsights -> GOEWS) — update the seed URL in any future re-probe.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | CSV | direct-download | https://download.gosa.ga.gov/2025/Enrollment_by_Grade_2024-25_2026-02-19_00_31_56.csv |
| staffing | 2024-25 | CSV | direct-download | https://download.gosa.ga.gov/2025/CERTIFIED_PERSONNEL_2024-25_2026-02-19_00_32_04.csv |
| sped | 2024-25 | CSV | direct-download | https://download.gosa.ga.gov/2025/Enrollment_by_Subgroup_Metrics_2024-25_2026-02-19_00_31_56.csv |
| frpm_ell | 2024-25 | Excel | direct-download | https://download.gosa.ga.gov/2025/2025_directly_certified_district.xls |

## GU — Guam
> Correction to Jan-2026 "limited public access" — SPED data reports page is genuinely current (Dec 2024 child count), but needs the specific Google Sheet links resolved before it's acquirable.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2023-24 | PDF | direct-download | http://files.eric.ed.gov/fulltext/ED671519.pdf |
| staffing | 2023-24 | PDF (headcount, no true FTE) | direct-download | http://files.eric.ed.gov/fulltext/ED671519.pdf |
| crosswalk_ids | 2024-25 | NCES CCD web lookup (single statewide LEA, ID 6600002) | dashboard-export | https://nces.ed.gov/ccd/districtsearch/district_detail.asp |

## IA — Iowa
> Strong enrollment/SPED/FRPM source once past the Tableau dashboard; staffing FTE unresolved.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://educate.iowa.gov/media/12227/download?inline |
| sped | 2025-26 | Excel | direct-download | https://educate.iowa.gov/media/12231/download?inline |
| frpm_ell | 2025-26 | Excel | direct-download | https://educate.iowa.gov/media/12310/download?inline<br>https://educate.iowa.gov/media/12223/download?inline |

## ID — Idaho
> Strong enrollment/SPED source; staffing lacks a SPED split, no crosswalk or FRPM/ELL found.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://www.sde.idaho.gov/wp-content/uploads/2025/12/Historical-Enrollment-by-District-or-Charter.xlsx |
| staffing | 2023-24 | PDF | direct-download | https://www.sde.idaho.gov/wp-content/uploads/2025/04/All-Staff-Salary-by-District-Charter.pdf |
| sped | 2024-25 | Excel | direct-download | https://www.sde.idaho.gov/wp-content/uploads/2026/02/2024-2025-Child-Count-Ages-3-21.xlsx |

## IL — Illinois
*Refresh of existing integration: il_staff_data + il_enrollment_data (864 districts, 2023-24). REFRESH CANDIDATE: seek 2024-25+.*
> Manual open of the 2024-25 Report Card Public Data Set needed to confirm SPED-teacher-split field before re-import — every recorded URL is a landing page, not a direct file link.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel (linked from a landing page, not a direct file) | dashboard-export | https://www.isbe.net/pages/illinois-state-report-card-data.aspx |
| crosswalk_ids | 2025-26 | Excel (linked from a landing page, not a direct file) | dashboard-export | https://www.isbe.net/pages/data-analysis-directories.aspx |

## IN — Indiana
> Strong enrollment/SPED/FRPM source; staffing needs a different/newer source.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://www.in.gov/doe/files/corporation-enrollment-grade-2006-26.xlsx<br>https://www.in.gov/doe/files/corporation-enrollment-grade-gender-2006-26.xlsx |
| sped | 2025-26 | Excel | direct-download | https://www.in.gov/doe/files/corporation-enrollment-ell-special-education-2006-26-3.xlsx |
| frpm_ell | 2025-26 | Excel | direct-download | https://www.in.gov/doe/files/corporation-enrollment-ethnicity-free-reduced-price-meal-status-2006-26.xlsx<br>https://www.in.gov/doe/files/corporation-enrollment-ell-special-education-2006-26-3.xlsx |

## KY — Kentucky
> Best-in-class source: NCES ID column at district+school level makes this the reference model for a future importer.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | CSV | direct-download | https://www.education.ky.gov/Open-House/data/HistoricalDatasets/KYRC25_OVW_Student_Membership.csv |
| staffing | 2024-25 | CSV | direct-download | https://www.education.ky.gov/Open-House/data/HistoricalDatasets/KYRC25_OVW_Teachers_Full_Time_Equivalent_FTE.csv |
| sped | 2024-25 | CSV | direct-download | https://www.education.ky.gov/Open-House/data/HistoricalDatasets/KYRC25_OVW_Students_with_Disabilities_IEP.csv |
| crosswalk_ids | 2024-25 | CSV | direct-download | https://www.education.ky.gov/Open-House/data/HistoricalDatasets/KYRC25_OVW_District_School_List.csv |
| frpm_ell | 2024-25 | CSV | direct-download | https://www.education.ky.gov/Open-House/data/HistoricalDatasets/KYRC25_OVW_Economically_Disadvantaged.csv<br>https://www.education.ky.gov/Open-House/data/HistoricalDatasets/KYRC25_OVW_English_Learners.csv |

## LA — Louisiana
> Strong enrollment/SPED/FRPM source; staffing FTE-by-district is the gap.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://doe.louisiana.gov/docs/default-source/fiscal-data/oct-2025-multi-stats-(total-by-site-and-school-system)-web.xlsx |
| sped | 2024-25 | Excel (LEA rates) + PDF (district detail) | direct-download | https://doe.louisiana.gov/docs/default-source/academics/oct-2025-idea-student-with-disabilities_public.xlsx<br>https://doe.louisiana.gov/docs/default-source/academics/2024-2025-spedbook-profile.pdf |
| frpm_ell | 2025-26 | Excel (%) + PDF (EL profile) | direct-download | https://doe.louisiana.gov/docs/default-source/fiscal-data/oct-2025-multi-stats-(total-by-site-and-school-system)-web.xlsx<br>https://doe.louisiana.gov/docs/default-source/english-learners/el-data-profile-2024-2025.pdf |

## MD — Maryland
> SPED census is newer than our NCES baseline (SY2025-26) — a real precedence win once acquired.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2023-24 | CSV | direct-download | https://opendata.maryland.gov/api/views/9ju3-j8k6/rows.csv?accessType=DOWNLOAD |
| staffing | 2023-24 | PDF | direct-download | https://www.marylandpublicschools.org/about/Documents/DCAA/SSP/20232024Staff/2024-Staff-Employed-at-School-and-Central-Office-A.pdf |
| sped | 2025-26 (Oct 2025 count, published Apr 2026) | PDF | direct-download | https://marylandpublicschools.org/about/Documents/DCAA/SSP/20252026Student/2025-Census-Publication-A.pdf |

## MI — Michigan
*Refresh of existing integration: mi_staff_data + mi_enrollment_data (836 districts, 2023-24) + mi_special_ed_data. REFRESH CANDIDATE: seek 2024-25+.*
> Best-confirmed refresh of the three (IL/MI/NY): direct-download links in hand for enrollment/staffing/SPED at 2024-25, crosswalk confirmed current.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/District-FTE-Count---Spring-2025.xlsx<br>https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/Spring_2025_FullAuditFile.xlsx |
| staffing | 2024-25 | Excel | direct-download | https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/2024-25-Dec2024-REP.xlsx |
| sped | 2024-25 | Excel | direct-download | https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/2024_25-Special-Ed-Count-data.xlsx |
| crosswalk_ids | current-rolling | CSV/Excel/XML | dashboard-export | https://cepi.state.mi.us/eem/publicdatasets.aspx |

## MO — Missouri
> Basic enrollment/staff totals confirmed via a real PDF directory; finer detail needs the MCDS login or a formal data request.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 (no explicit label; refreshed weekly) | PDF | direct-download | https://apps.dese.mo.gov/MCDS/FileDownloadWebHandler.ashx?filename=16262384-5e2cMissouri%20School%20Directory%20by%20District.pdf |
| staffing | 2025-26 (no explicit label; refreshed weekly) | PDF | direct-download | https://apps.dese.mo.gov/MCDS/FileDownloadWebHandler.ashx?filename=16262384-5e2cMissouri%20School%20Directory%20by%20District.pdf |

## MS — Mississippi
> Portal moved (newreports -> Superintendent Annual Report packet); no crosswalk or FRPM/ELL found.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://mdek12.org/wp-content/uploads/sites/29/2025/12/2024-2025-MTH1-NET-MEMBERSHIP.xlsx |
| staffing | 2024-25 | Excel | direct-download | https://mdek12.org/wp-content/uploads/sites/29/2025/12/2024-2025-CLASSROOM-TEACHERS-COUNTS-AVERAGE-SALARIES.xlsx<br>https://mdek12.org/wp-content/uploads/sites/29/2025/12/2024-2025-INSTRUCTIONAL-PERSONNEL-REPORT.xlsx |
| sped | 2022-23 | PDF | direct-download | https://www.mdek12.org/sites/default/files/Offices/MDE/OAE/OSE/SPP-APR/Districts-2022/v1/4100_lee_county_school_district.pdf |

## ND — North Dakota
> Enrollment + aggregate staffing ready to acquire; SPED is state-level only, no crosswalk found.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://www.nd.gov/dpi/sites/www/files/documents/Data/EnrollmentHistoryPublicSchoolDistrict.xlsx |
| staffing | 2024-25 | PDF | direct-download | https://www.nd.gov/dpi/sites/www/files/documents/SFO/2025FinFacts.pdf |

## NE — Nebraska
> Enrollment/staffing/FRPM ready to acquire now via real files; SPED needs the NEP dashboard.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | CSV | direct-download | https://www.education.ne.gov/wp-content/uploads/2025/12/MembershipByGradeRaceAndGender_20252026.csv |
| staffing | 2024-25 | PDF | direct-download | https://www.education.ne.gov/wp-content/uploads/2025/02/Statsfacts_20242025.pdf |
| frpm_ell | 2025-26 | Excel | direct-download | https://www.education.ne.gov/wp-content/uploads/2025/12/2025-2026_Free_and_Reduced_Lunch_Counts_by_School.xlsx |

## NJ — New Jersey
> Strong open portal; correction to seed note — staffing file does NOT split SPED vs general-ed teachers.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel (in ZIP) | direct-download | https://www.nj.gov/education/doedata/enr/enr26/Enrollment_2526.zip |
| staffing | 2025-26 | Excel (in ZIP) | direct-download | https://www.nj.gov/education/doedata/cs/cs26/Certificated%20Staff%202026.zip |
| sped | 2024-25 (Oct 15 2024 count) | Excel | direct-download | https://www.nj.gov/education/specialed/monitor/ideapublicdata/docs/2025_618data/2025IDEA618PublicReporting_StudentCountandEducationalEnvironment.xlsx |
| frpm_ell | 2025-26 | Excel (in ZIP) | direct-download | https://www.nj.gov/education/doedata/enr/enr26/Enrollment_2526.zip |

## NM — New Mexico
> Portal moved off the Jan-2026 seed URL; richer data confirmed behind a login wall.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://web.ped.nm.gov/wp-content/uploads/_legacy/2025/02/SY2024_2025_40D_Enrollment_By_School_By_Grade.xlsx |
| sped | 2024-25 | PDF | direct-download | https://web.ped.nm.gov/wp-content/uploads/2025/08/Published-24-25-School-Age-Child-Counts.pdf |

## NV — Nevada
> Best small-state find: genuine SPED-teacher split in staffing, all 4 core categories confirmed.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://webapp-strapi-paas-prod-nde-001.azurewebsites.net/uploads/2024_2025_school_year_validation_day_student_counts_16036836ca.xlsx |
| staffing | 2024-25 | PDF | direct-download | https://www.leg.state.nv.us/Division/Research/Documents/RTTL_NRS387.303_2024_Statewide_Revised.pdf |
| sped | 2024-25 | PDF | direct-download | https://webapp-strapi-paas-prod-nde-001.azurewebsites.net/uploads/october_2024_nevada_idea_child_count_1426a218a7.pdf |
| frpm_ell | 2024-25 | PDF | direct-download | https://nevadareportcard.nv.gov/PDF/2025/00.E.pdf |

## NY — New York
*Refresh of existing integration: ny_staff_data (9,298 rows by category) + ny_enrollment_data (2023-24); NYC as 33 sub-districts. REFRESH CANDIDATE: seek 2024-25+.*
> Enrollment/staffing refresh is clean; SPED bulk-file and crosswalk re-verification need manual follow-up (SEDREF login wall).

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | CSV (zip) | direct-download | https://data.nysed.gov/files/enrollment/24-25/ENROLLMENT_2025.zip |
| staffing | 2024-25 | CSV (zip) | direct-download | https://data.nysed.gov/files/studed/24-25/STUDED2025.zip |

## OH — Ohio
> Enrollment + SPED ready to acquire now; staffing needs a login, data.ohio.gov open-data catalog appears dead.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel (.xls) | direct-download | https://education.ohio.gov/getattachment/Topics/Data/Frequently-Requested-Data/Enrollment-Data/oct_hdcnt_fy26.xls.aspx?lang=en-US |
| sped | 2024-25 | Excel | direct-download | https://education.ohio.gov/getattachment/Topics/Special-Education/Special-Education-Data-and-Funding/Special-Education-Accountability-Resources/Ohio-s-Special-Education-Profiles/Public-Indicator-Report-2024-2025.xlsx.aspx?lang=en-US |
| crosswalk_ids | current | CSV/Excel (custom extract) | dashboard-export | https://oeds.education.ohio.gov/dataextract |

## OR — Oregon
> Enrollment + SPED-by-environment confirmed strong; staffing needs a dropdown click-through.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://www.oregon.gov/ode/reports-and-data/students/Documents/fallmembershipreport_20242025.xlsx |
| sped | 2024-25 | Excel | direct-download | https://www.oregon.gov/ode/reports-and-data/SpEdReports/Documents/SECCMediaFiles/2024samediafile.xlsx |

## SC — South Carolina
> SPED-teacher split derivable from position codes even without a pre-built column — worth building that aggregation in the importer.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://ed.sc.gov/data/other/student-counts/active-student-headcounts/2024-25-active-student-headcounts/45-day-district-headcount-by-grade/ |
| staffing | 2024-25 | Excel | direct-download | https://ed.sc.gov/data/other/teacher-data/2024-25-sc-staff-by-school-position-codes-01-105/ |
| sped | 2022-23 | PDF | direct-download | https://ed.sc.gov/districts-schools/special-education-services/data-and-technology-d-t/data-collection-and-reporting/sc-data-collection-history/idea-child-count-data/2022-2023-child-count-data/ages-3-to-21-state-child-count-summary-22-23-pdf/ |

## SD — South Dakota
> Genuinely strong flat-file source once the /ofm sub-pages are known — enrollment/staffing/SPED/FRPM all ready to acquire.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://doe.sd.gov/ofm/documents/Pubdisgr-2025.xlsx |
| staffing | 2024-25 | Excel | direct-download | https://doe.sd.gov/ofm/documents/25-Profile.xlsx |
| sped | 2025 | Excel | direct-download | https://doe.sd.gov/ofm/documents/25-PublicCC-Dst.xlsx |
| frpm_ell | 2025 | Excel | direct-download | https://doe.sd.gov/ofm/documents/PubdisFRL-25.xlsx<br>https://doe.sd.gov/ofm/documents/PubdisEL-2025.xlsx |

## TN — Tennessee
> Confirmed crosswalk file with explicit NCES.District.Number column; portal moved off the SAS seed URL.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2024-25 | Excel | direct-download | https://www.tn.gov/content/dam/tn/education/data/district-profile-2024-2025.xlsx |
| staffing | 2024-25 | Excel | direct-download | https://www.tn.gov/content/dam/tn/education/data/staff-2024-25.xlsx |
| crosswalk_ids | current (undated static reference) | Excel | direct-download | https://www.tn.gov/content/dam/tn/education/data/data_interdepartmental_crosswalk.xlsx |
| frpm_ell | 2024-25 | Excel | direct-download | https://www.tn.gov/content/dam/tn/education/data/district-profile-2024-2025.xlsx |

## UT — Utah
> Genuine SPED-teacher-FTE column confirmed in staffing — a clean source once the real file location (schools.utah.gov, not the dashboard) is known.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | Excel | direct-download | https://schools.utah.gov/datastatistics/_datastatisticsfiles_/_reports_/_enrollmentmembership_/2026EnrollmentLEA.xlsx |
| staffing | 2024-25 | Excel | direct-download | https://schools.utah.gov/datastatistics/_datastatisticsfiles_/_reports_/_educators_/2025LicensedStaffFTESchoolYear.xlsx |

## WA — Washington
> One Socrata API call covers enrollment+FRPM+ELL+SPED-count together — an excellent acquisition target.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | API (Socrata; CSV export also available) | api | https://data.wa.gov/resource/wvqy-yp3m.json |
| staffing | 2024-25 | PDF | direct-download | https://ospi.k12.wa.us/sites/default/files/2025-02/allpersonnelsummaryreport2024-25.pdf |
| sped | FFY2024 (submitted 2026) | Excel | direct-download | https://ospi.k12.wa.us/sites/default/files/2026-05/perf_data_profiles_ffy2024_subm2026-public.xlsx |
| frpm_ell | 2025-26 | API (Socrata; CSV export also available) | api | https://data.wa.gov/resource/wvqy-yp3m.json |

## WI — Wisconsin
> Best crosswalk found in this batch (real NCES-code column + dedicated crosswalk file); enrollment/SPED/FRPM/ELL all one bulk source, only staffing is per-district manual.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | CSV (zipped) | direct-download | https://dpi.wi.gov/sites/default/files/wise/downloads/enrollment_certified_2025-26.zip |
| sped | 2025-26 | CSV (zipped) | direct-download | https://dpi.wi.gov/sites/default/files/wise/downloads/oct1_child_count_certified_2025-26.zip |
| crosswalk_ids | 2025-26 | CSV (zipped) | direct-download | https://dpi.wi.gov/sites/default/files/wise/downloads/agency_ICS_crosswalk.zip<br>https://dpi.wi.gov/sites/default/files/wise/downloads/agency_certified_2025-26.zip |
| frpm_ell | 2025-26 | CSV (zipped) | direct-download | https://dpi.wi.gov/sites/default/files/wise/downloads/enrollment_certified_2025-26.zip |

## WV — West Virginia
> Confirmed SPED-teacher split by county in the FTE file — a clean source for the SPED-teacher-split rubric goal. Enrollment's Excel-via-ZoomWV alternative is JS-dashboard-only, not scriptable; PDF remains the actual acquisition source.

| Category | Year | Format | Access | URL(s) |
|---|---|---|---|---|
| enrollment | 2025-26 | PDF (district table); Excel via dashboard | direct-download | https://wvde.us/sites/default/files/2025-11/Education%20Snapshot%20Booklet%202024-2025.pdf |
| staffing | 2025-26 | Excel | direct-download | https://wvde.us/media/9183/fte-teachers-26accxlsx |
| sped | 2023-24 | Excel | direct-download | https://wvde.us/media/7663/wv-local-annual-performance-reports-2023-24 |

---

## Acquisition mechanics (Phase D, once approved)

- Download to `data/raw/state/{state}/{year}/`, never modify existing raw files.
- Every file gets an acquisition receipt in the catalog: source URL, retrieval date, sha256, size — plus a `MANIFEST.md` per new state directory.
- Spot-verify each file opens/parses (pandas read of first rows) before marking it acquired.
- Failures/blocks on retry -> flag `follow-up-manual`, one-attempt rule applies, do not retry-loop.

## Not in this list — flagged for manual follow-up

17 entities need a human browser session (WAF blocks, JS-only dashboards, login walls) or more manual investigation before any file can be reliably acquired. Full detail in the assessment doc's Tier 2/Tier 3 tables — notably: **AZ, MN, NH, VT** are genuine WAF blocks (not tool artifacts); **HI, WY, KS** are JS-rendered dashboards a probe without Playwright could not read; **MO, NM, GA** (crosswalk/deeper data) need a login or formal data request.

