<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# In the U.S. NCES Common Core of Data (CCD), charter schools appear in inconsistent structures: (a) each campus as its own LEA with Agency Type Code 7 (e.g. Ascend, KIPP New York), (b) one LEA operating many schools (multiple ccd_sch rows), and (c) dependent charters reported under a traditional district's LEA. For a data pipeline that must attribute each physical school's bell schedule to the correct LEA: What CCD fields (LEA_TYPE, CHARTER_LEA, CHARTER_TEXT, OPERATIONAL_SCHOOLS, supervisory-union or management-org identifiers) reliably distinguish these three structures? Is there any CCD or federal field identifying the parent Charter Management Organization so sibling LEAs sharing one website can be recognized as distinct entities? How do researchers de-duplicate/attribute across CMO campuses that share a website but are separate LEAs?

I now have all the information needed to write a comprehensive, precise answer. Let me compose it.

The three CCD charter structures you've described map to distinct but overlapping combinations of fields. Here is a precise breakdown, starting with what the actual field values tell you and ending with the CMO attribution problem.

***

## LEA_TYPE and Its Scope

`LEA_TYPE` (field position 31 in the modern LEA directory, sourced from EDFacts FS029 DG453) is the most reliable first filter for your pipeline. The key values are:[^1_1]


| Code | Label | Charter Relevance |
| :-- | :-- | :-- |
| 1 | Regular public school district (not supervisory union component) | May contain dependent charters as member schools |
| 2 | Regular district, component of supervisory union | Same as above |
| 7 | **Independent charter district** | All schools are charters; this is your Structure A |
| 8 | Other education agency | Legacy catch-all; review carefully |
| 9 | Specialized public school district (added SY 2016-17) | Some states classify multi-campus charter operators here |

The critical historical caveat: prior to SY 2007-08, code `7` meant "other education agencies, *including* charter school agencies." Starting with SY 2007-08, NCES reserved `7` exclusively for charter school agencies, adding `8` for all other non-charter agencies. Any pipeline spanning data before 2007-08 must recode accordingly.[^1_2]

***

## Distinguishing the Three Structures

The three structures require a joint read of `LEA_TYPE` on the **LEA file** and `CHARTR` (or `charter` in Urban Institute's API) on the **school file**, along with `CHARTER_LEA` and `OPERATIONAL_SCHOOLS`.

### Structure A — Campus-as-Own-LEA (e.g., each KIPP NYC campus)

On the **LEA file**: `LEA_TYPE = 7` ("Independent charter district"). On the **school file**: `CHARTR = 1` (yes, charter) and `LEAID` points back to a 7-type LEA with `OPERATIONAL_SCHOOLS = 1` (exactly one school under that LEA). The LEA and school have distinct but co-located addresses. This is the most common structure for large urban CMOs that obtained independent charters for each building — each campus is its own governmental unit.[^1_3][^1_2][^1_1]

### Structure B — One LEA Operating Many Schools (e.g., a single charter district running multiple campuses)

`LEA_TYPE = 7` but `OPERATIONAL_SCHOOLS > 1` on the LEA file. Multiple rows in the school universe file share the same `LEAID`. `CHARTER_LEA` (see below) will typically be `CHRTESEA` or `CHRTIDEA`. This is the operationally coherent multi-school charter operator that obtained a single charter to run a network — the legal entity is one district, and individual campuses are "schools" within it.[^1_1]

### Structure C — Dependent Charter Under a Traditional District

The LEA file shows a traditional district with `LEA_TYPE = 1` (or 2), not 7. Charter schools in the school file have `CHARTR = 1` but their `LEAID` links to that conventional district's record. The school-level `CHARTR` flag is the only indicator distinguishing these buildings from the district's conventional schools. The `CHARTER_LEA` value on the *LEA* record for the parent district will be `CHRTNOTLEA` or a variant indicating it is not itself a charter LEA. States where charter law treats charters as instrumentalities of their authorizing district (e.g., Texas district-authorized charters) typically produce this pattern.[^1_4][^1_2][^1_1]

***

## CHARTER_LEA Field Values Decoded

`CHARTER_LEA` on the LEA directory file (from EDFacts FS029 DG653) carries six permitted values as of SY 2017-18 forward:[^1_1]


| Value | Meaning for your pipeline |
| :-- | :-- |
| `CHRTESEA` | LEA is a charter district recognized as the LEA for ESEA/Perkins federal programs — assign bell schedule to this LEA |
| `CHRTIDEA` | Charter district recognized as LEA for IDEA special education programs specifically |
| `CHRTIDEAESEA` | Charter district that is the LEA for *both* IDEA and ESEA programs |
| `CHRTNOTLEA` | Entity has charter schools but is **not** the LEA for federal programs (the resident district is) — do not use this as the attributing LEA for most federal programs |
| `NOTCHR` | Not a charter district |
| `NA` | Not applicable |

The `CHARTER_LEA_TEXT` companion field provides human-readable equivalents. For bell schedule attribution to the correct federal-program LEA, `CHRTNOTLEA` is the dangerous value: these are typically Structure C dependent charters where the reporting LEA for most purposes is the umbrella district, not the charter entity itself.[^1_3][^1_1]

The older `CHARTER_TEXT` variable (pre-2016-17 files) carried similar logic under different labels; the 2016-17 LEA directory layout introduced the current six-value `CHARTER_LEA` scheme alongside the new `LEA_TYPE = 9` (specialized public school district).[^1_1]

***

## OPERATIONAL_SCHOOLS and UNION

`OPERATIONAL_SCHOOLS` (added in SY 2016-17) is a derived count of how many schools in the CCD school universe are currently linked to a given LEA. It is invaluable for distinguishing Structure A from B without manually counting school-file rows:[^1_1]

- `LEA_TYPE = 7` AND `OPERATIONAL_SCHOOLS = 1` → high-probability Structure A (campus-as-LEA)
- `LEA_TYPE = 7` AND `OPERATIONAL_SCHOOLS > 1` → Structure B (one charter district, many buildings)

`UNION` (supervisory union number) is useful for the supervisory-union analog but does **not** have a parallel function for CMO affiliation. It identifies New England-style administrative sharing arrangements between conventional component districts (LEA_TYPE = 2 and 3). It carries no CMO identity information for charter agencies.[^1_5][^1_6]

***

## The CMO Parent-Identification Gap

There is **no CCD field** that directly identifies a parent Charter Management Organization. The CCD LEA and school files treat each LEA as an independent governmental unit. Identifying that "KIPP NYC" and "KIPP Brooklyn" are siblings requires going outside the CCD. The federal mechanism is the EDFacts **FS196/FS197 pair**.

### EDFacts FS196 + FS197 (the official CMO link)

- **FS196** (Management Organization for Charter Schools Roster) collects, at the SEA level, the CMO or EMO's full legal name (DG825), its **IRS Employer Identification Number** (DG826), and its type (DG829): `CHARСMO` (nonprofit CMO), `CHAREMO` (for-profit EMO), `CHARSMNP` (single non-profit), `CHARSMFP` (single for-profit).[^1_7]
- **FS197** (Crosswalk of Charter Schools to Management Organizations) links individual school NCESSCH identifiers to the managing organization's EIN (DG833). These two files *must* be submitted together, and FS029 (school directory) must precede them.[^1_8][^1_9][^1_10]

The EIN in FS197 is the practical CMO identifier for sibling-school grouping: all school NCESSCHs that resolve to the same EIN share a CMO parent. NCES surfaces this data in EDFacts, but it does **not** flow into the downloadable CCD flat files as a standard column — you must obtain it through the EDFacts/EDPass channel or from your state education agency's public data release.

### Practical caveat

FS196/FS197 submission is required only from states where management organizations are active. States where every charter is a standalone entity are exempt. Coverage is therefore inconsistent across states, and a given CMO's EIN may appear in some state submissions but not others for cross-state networks.[^1_7]

***

## De-duplication and Attribution for Shared-Website CMO Campuses

When CCD data alone is insufficient (i.e., FS196/197 data is unavailable or incomplete), researchers use a layered approach:

**1. Name-string matching on `LEA_NAME`**
CMOs typically brand their campuses with the network name embedded: "KIPP Infinity Charter School," "KIPP AMP Charter School," etc. Regex on the LEA_NAME field in the LEA directory is a fast first pass. CREDO, for its CMO network studies, relied on this plus state education agency websites and the CMO's own campus-listing pages.[^1_11]

**2. EIN matching via IRS Form 990 cross-reference**
Nonprofits file 990s with the IRS; ProPublica's Nonprofit Explorer and the IRS Tax Exempt Organization data release are publicly searchable by EIN. The EIN on an LEA's W-9 or state fiscal records (often public) can be matched back to a parent CMO's 990.

**3. WEBSITE field in the LEA directory**
The `WEBSITE` field (field position 25 in the 2017-18 layout) records the URL reported by the LEA to EDFacts. Sibling LEAs in the same CMO often report the same root domain (e.g., `kipp.org` subdomain). Normalizing URLs to their registered domain and grouping by domain is a common heuristic — but it conflates CMO identity with web infrastructure choices. A CMO that gives each campus a unique domain will be missed; a CMO that bought the same domain template for unrelated schools will produce false positives.[^1_1]

**4. Shared physical address or phone**
In Structure A networks, the CMO's back-office address frequently appears as the mailing address for multiple LEAs. Grouping on `MSTREET1` + `MCITY` + `MZIP` (or normalizing and fuzzy-matching addresses) surfaces these.

**5. State charter-authorizer databases**
Many state charter authorizer websites (state education agencies, independent authorizers) publish searchable lists linking schools to their management organizations. Colorado's CDE, for instance, collects CMO/EMO EIN, legal name, and address as a distinct data collection mapped to each charter.[^1_12]

**Key attribution principle for a bell-schedule pipeline**: once you resolve a school's governing LEA, the correct attribution target for operational policy (including schedule) is the LEA that is the charter holder and holds the CCD record — not the CMO, which is a management contractor, not a governmental unit. For Structure A, that is the individual campus's LEA_TYPE=7 entity. For Structure B, it is the multi-school charter district. For Structure C, the physical school operates under a conventional district's LEAID, but its charter holder may be a separate legal entity you can identify only through state-level authorizer data or the FS196/197 CMO chain.[^1_4][^1_7]
<span style="display:none">[^1_13][^1_14][^1_15][^1_16][^1_17][^1_18][^1_19][^1_20][^1_21][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81][^1_82][^1_83][^1_84][^1_85]</span>

<div align="center">⁂</div>

[^1_1]: https://nces.ed.gov/ccd/xls/2017-18_LEA_Directory_Layout.xlsx

[^1_2]: https://nces.ed.gov/ccd/bat/glossary.asp?letter=C

[^1_3]: https://www.nysed.gov/sites/default/files/programs/charter-schools/charter-schools-leas-memo.pdf

[^1_4]: http://www.ecs.org/clearinghouse/CharterSch/1-4-LEA.pdf

[^1_5]: https://nces.ed.gov/ccd/aadd.asp

[^1_6]: https://nces.ed.gov.qipservices.com/ccd/Data/txt/sc14prelimlay.txt

[^1_7]: https://www.ed.gov/sites/ed/files/2025-01/fs196-21-0.pdf

[^1_8]: https://www.ed.gov/media/document/fs197-17-0docx-19982.docx

[^1_9]: https://www.ed.gov/media/document/fs197-20-2docx-19989.docx

[^1_10]: https://downloads.regulations.gov/ED-2021-SCC-0159-0003/attachment_2.pdf

[^1_11]: https://credo.stanford.edu/wp-content/uploads/2021/08/cmo_final.pdf

[^1_12]: https://www.cde.state.co.us/datapipeline/chartercollectiontemplateemo-cmo

[^1_13]: https://nces.ed.gov/ccd/xls/SY_2021-22_LEA_Directory_Companion.xlsx

[^1_14]: https://files.eric.ed.gov/fulltext/ED565676.pdf

[^1_15]: https://nces.ed.gov/use-work/dataset/2024-25-common-core-data-ccd-preliminary-directory-files

[^1_16]: https://nces.ed.gov/ccd/commonfiles/glossary.asp

[^1_17]: https://nces.ed.gov/ccd/data/txt/psu081blay.txt

[^1_18]: https://nces.ed.gov/ccd/pdf/pau01gen.pdf

[^1_19]: https://nces.ed.gov/ccd/bat/glossary.asp?letter=A

[^1_20]: https://educationdata.urban.org/documentation/schools.html

[^1_21]: https://nces.ed.gov/sites/default/files/data-asset/ccd-common-core-data/2025/08/common-core-data-ccd-nonfiscal-preliminary-version-0a-files-release-notes/SY 2024-25 Preliminary Data Release CCD Nonfiscal Release Notes_0.pdf

[^1_22]: https://nces.ed.gov/ccd/reference_library.asp

[^1_23]: https://nces.ed.gov/ccd/

[^1_24]: https://www2.census.gov/govs/ccd/instructionmanual.pdf

[^1_25]: https://nces.ed.gov/statprog/handbook/pdf/ccd.pdf

[^1_26]: https://nces.ed.gov/ccd/files.asp

[^1_27]: https://studentprivacy.ed.gov/sites/default/files/resource_document/file/LEASampleRequirements.pdf

[^1_28]: https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/eden/ess/13-14-charter-workbook.doc

[^1_29]: https://files.eric.ed.gov/fulltext/ED579146.pdf

[^1_30]: https://www.cde.ca.gov/SchoolDirectory/topic/8

[^1_31]: https://nces.ed.gov/ccd/pdf/psu98gen.pdf

[^1_32]: https://ies.ed.gov/sites/default/files/nces/document/2025/08/SY 2024-25 Preliminary Data Release CCD Nonfiscal Release Notes.pdf

[^1_33]: https://nces.ed.gov/learn/blog/nces-releases-updated-2022-23-data-table-school-district-structures

[^1_34]: https://nces.ed.gov/ccd/CCDLocaleCodeDistrict.asp

[^1_35]: https://educationdata.urban.org/csv/ccd/codebook_districts_ccd_directory.xls

[^1_36]: https://nces.ed.gov/ccd/ccddata.asp

[^1_37]: https://files.eric.ed.gov/fulltext/ED565859.pdf

[^1_38]: https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2025-26

[^1_39]: https://downloads.regulations.gov/ED-2018-ICCD-0117-0004/attachment_3.pdf

[^1_40]: https://surveys.nces.ed.gov/CCDDMS/login/go

[^1_41]: https://nces.ed.gov/ccd/doc/CCD_Nonfiscal_Data_and_EDFacts.docx

[^1_42]: https://nces.ed.gov/ccd/address.asp

[^1_43]: https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/eden/19-20-workbook-16-0.pdf

[^1_44]: https://downloads.regulations.gov/ED-2018-ICCD-0117-0154/attachment_3.pdf

[^1_45]: https://nces.ed.gov/ccd/xls/2016-17_LEA_Directory_Layout.xls

[^1_46]: https://nces.ed.gov/use-work/dataset/2022-23-common-core-data-ccd-preliminary-directory-files

[^1_47]: https://nces.ed.gov/ccd/pdf/2015172_Documentation_LEA_201415_prel.pdf

[^1_48]: https://educationdata.urban.org/csv/ccd/codebook_schools_ccd_directory.xls

[^1_49]: https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2023-24

[^1_50]: https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/eden/21-22-workbook-18-0.pdf

[^1_51]: https://nces.ed.gov/use-work/resource-library/data/data-file/2020-21-common-core-data-ccd-preliminary-files

[^1_52]: https://nces.ed.gov/ccd/doc/SY_2020-21_Universe_1a_CCD_Nonfiscal_Release_Notes.docx

[^1_53]: https://www.ed.gov/media/document/19-20-workbook-16-1pdf-18664.pdf

[^1_54]: https://2024.edreform.com/wp-content/uploads/2013/03/CER_LEA_primer.pdf

[^1_55]: https://www.ed.gov/sites/ed/files/2020/07/cguidedec2000.pdf

[^1_56]: https://www.ed.gov/sites/ed/files/2023/10/Title-III-EDFacts-Data-Crosswalk-SY-2022-23.pdf

[^1_57]: https://files.eric.ed.gov/fulltext/ED381859.pdf

[^1_58]: https://nces.ed.gov/statprog/handbook/ccd_dataquality.asp

[^1_59]: https://stacks.stanford.edu/file/druid:gm391gj1253/LISD_geo_crosswalk_documentation_1.0.pdf

[^1_60]: https://files.eric.ed.gov/fulltext/ED625516.pdf

[^1_61]: https://nces.ed.gov.qipservices.com/ccd/pdf/sdf99gen.pdf

[^1_62]: https://nces.ed.gov/ccd/search.asp

[^1_63]: https://nces.ed.gov/statprog/handbook/ccd.asp

[^1_64]: https://credo.stanford.edu/wp-content/uploads/2021/08/cmo_executive_summary.pdf

[^1_65]: https://ncss3.stanford.edu/methods-data/methodology/

[^1_66]: https://www.gsastl.org/apps/news/article/1785779?categoryId=18686

[^1_67]: https://fordhaminstitute.org/ohio/commentary/charter-growth-and-replication

[^1_68]: https://educationdata.urban.org/documentation/

[^1_69]: https://urbaninstitute.github.io/education-data-package-r/

[^1_70]: https://nces.ed.gov/ccd/pub_overview.asp

[^1_71]: https://nces.ed.gov/ccd/pdf/psu01gen.pdf

[^1_72]: https://ies.ed.gov/use-work/resource-library/data/data-file/2024-25-common-core-data-ccd-preliminary-directory-files

[^1_73]: https://cran.r-project.org/web/packages/educationdata/educationdata.pdf

[^1_74]: https://educationdata.urban.org/

[^1_75]: https://nces.ed.gov/ccd/tables/202122_summary_1.asp

[^1_76]: https://ies.ed.gov/use-work/dataset/2023-24-common-core-data-ccd-preliminary-directory-files

[^1_77]: https://crdc.communities.ed.gov/sites/default/files/2024-10/Which Schools Do I Report.pdf

[^1_78]: https://www.cde.ca.gov/ds/sp/cl/charterreporting20250509.asp

[^1_79]: https://dcpcsb.org/sites/default/files/media/file/Q39.pdf

[^1_80]: https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/eden/non-xml/fs197-21-0.docx

[^1_81]: http://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2023-24

[^1_82]: https://www.ed.gov/media/document/fs197-16-0docx-19981.docx

[^1_83]: https://cepa.stanford.edu/sites/default/files/SEDA data construction documentation v01.docx

[^1_84]: https://www.ed.gov/sites/ed/files/2023/01/TitleIII_Crosswalk.pdf

[^1_85]: https://www.ed.gov/media/document/crdc-2015-16-code-book-36758.xls


---

# In district-level education-equity metrics (e.g. student-teacher ratio or instructional-time-per-student), what is current best practice for handling charter schools: include them as pseudo-districts, exclude them, or segment/report them separately? What are the known distortions when charter students and charter staff are mis-partitioned relative to a parent district's enrollment and staffing counts? Cite methodological guidance from NCES, Urban Institute, Center for Learner Equity, or peer-reviewed sources.

I now have sufficient material to write a thorough and precise answer. The key empirical findings are clear across sources:

1. **Urban Institute's "Beyond Education Outcomes" equity tool explicitly excludes charters** from district-level metrics[^2_1]
2. **NCES SY2017-18 FS052 guidance change** directly calls out the charter mis-partitioning problem — the pre-2017-18 "home district" reporting rule created broken pupil/teacher ratios, revenues per pupil, and expenditures per pupil[^2_2]
3. **Center for Learner Equity** (in its CRDC methodology report) treated charter LEA status as a distinct analysis dimension and separated charters that are their own LEA from those that are part of a traditional LEA[^2_3]
4. **SLIDE study** explicitly analyzed charter districts (LEA_TYPE=7) separately and subtracts charter schools from district totals when calculating librarian ratios[^2_4]
5. **ESSA report card guidance** treats charter LEAs as "districts" in their own right for reporting purposes[^2_5]

***

## The Core Methodological Position

There is no single federal mandate dictating inclusion vs. exclusion, but a clear convergence in practice: **segment charter schools out of traditional district calculations and treat independent-LEA charters as their own analytical units**. The rationale is structural, not ideological — because charter schools in CCD can be their own LEAs, their students and staff appear in a separate LEA row and would be double-counted or incorrectly attributed if naively aggregated with the surrounding traditional district.[^2_1][^2_2]

## What NCES Itself Prescribes

The sharpest federal guidance on this comes not from a separate charter-methodology document, but from NCES's own 2017-18 revision to **EDFacts FS052 (Student Membership)**. The pre-2017-18 rule required counting charter students in their *home district's* LEA-level membership, even while their teachers and instructional expenditures were reported under the charter's own LEA. NCES explicitly identified this as yielding "problematic results in ratios that used LEA membership," citing three metrics by name: **pupil/teacher ratios, revenues per pupil, and expenditures per pupil**. The revised rule — "count students in the LEA where served" — took effect with SY 2017-18 data and materially changed LEA-level membership figures in at least six states that had systemic misalignment (Illinois, Iowa, Maine, New Hampshire, New Jersey, and Vermont under the old rule). Any pipeline using pre-2017-18 CCD data must treat this as a structural break in all ratio-based equity metrics.[^2_6][^2_2]

The NCES definition of the district-level pupil/teacher ratio further underscores the point: it is "the ratio of pupils to teachers based on the total number of pupils and the total FTE number of teachers reported in the *schools associated with the school district*". For a LEA_TYPE=7 charter, the schools associated with it are its charter campuses — not the surrounding district's schools. Mixing them produces a denominator mismatch.[^2_7]

## Urban Institute: Explicit Exclusion

The Urban Institute's **"Beyond Education Outcomes" equity tool** (built from CCD and CRDC 2017-18 data) states its methodology rule plainly: *"All district-level results exclude charter schools."* For teacher metrics specifically, the tool further restricts the sample to districts with at least two non-charter elementary schools. The rationale is that including charter campuses in a traditional district's equity score confounds governance structures — a charter's staffing decisions are made independently of the district HR and budget process, so including charter teachers in the district's staffing ratio attributes decisions to district leadership that it did not make.[^2_1]

## Center for Learner Equity: LEA Status as an Analytical Axis

The Center for Learner Equity's CRDC methodology (2021) operationalizes a three-way partition rather than a binary include/exclude:[^2_3]

- **Charter as own LEA** (`LEA_TYPE=7` + `CHARTER_LEA_TEXT` = "LEA for ESEA and Perkins" or "LEA for IDEA" + Agency Charter Code = 1): analyzed as an independent unit. In 2017-18, this was 60.8% of charter schools nationally (4,279 of 7,035).[^2_3]
- **Charter as part of traditional LEA** (`CHARTER_LEA_TEXT` = "Not LEA for federal programs"): rolled into the parent district's LEA for federal program metrics, since the district bears legal and financial responsibility. This was 39.2% of charters (2,756 of 7,035).[^2_3]
- **Specialized charter schools** (defined by disability enrollment share): analyzed as a distinct third stratum because their staffing and enrollment profiles are structurally incomparable to general-population schools.[^2_3]

CLE explicitly notes that Connecticut, New Hampshire, and New York City charter schools were treated as part of a traditional LEA for analysis purposes despite some having their own LEAID, because state law keeps those charters financially and programmatically dependent on the host district.[^2_3]

## Known Distortions from Mis-Partitioning

When charter students and charter staff are incorrectly attributed — either included in a traditional district's totals or excluded from their own charter LEA's totals — the following distortions arise:

**For traditional district metrics (if charter students/staff are pooled in):**

- **Student-teacher ratio artificially deflated (improved):** Many urban charter schools, especially CMO networks, report lower pupil-teacher ratios than surrounding district schools due to intentional staffing model choices. Pooling charter teachers into the surrounding district's FTE count makes the district look more generously staffed than its own schools actually are. The SLIDE study addresses this directly: when calculating district ratios, charter schools are subtracted from the denominator of schools operated by a district, because "9 out of 10 charter districts report no School Librarians" — a concrete case where including charters in an aggregate metric would artificially deflate district-level resource ratios.[^2_4]
- **Per-pupil expenditure distorted:** Charter students generating their own categorical funding streams (Title I, IDEA) at the charter LEA level, but being counted in the parent district's enrollment, inflate the denominator without a corresponding increase in the district's reported expenditure numerator. This was a documented problem under the pre-2017-18 membership guidance.[^2_2]
- **Demographic composition skewed:** Many independent charter LEAs enroll higher shares of Black and Hispanic students than surrounding district schools. Pooling them into the district's enrollment counts changes the district's apparent demographics, distorting any equity metric that is subgroup-specific.[^2_3]

**For charter LEA metrics (if charter students/staff are attributed to the wrong unit):**

- **Structure C dependent-charter inflation:** If a charter operating under a traditional district's LEAID has its students counted in the traditional district's membership but some of its staff reported at the school level under the district's staff totals, the charter's own operational staffing ratio is invisible. The school's actual schedule and staffing intensity cannot be derived from LEA-level fields alone.
- **CMO back-office staff pooling:** For Structure B charters (single LEA, multiple schools), the LEA-level staffing count includes both school-based teachers and CMO administrative staff reported as district staff. This compresses the apparent pupil-teacher ratio compared to what is actually present in classrooms — a known limitation of using LEA FTE counts for intra-network comparisons.[^2_8]
- **Instructional time is unmeasured in CCD entirely:** No CCD field captures bell schedule length, instructional minutes, or school-day duration. Charter schools in CMO networks with extended-day models (e.g., KIPP's longer school day) are structurally invisible as more resource-intensive from CCD alone. Any instructional-time-per-student metric must be built from EDFacts FS033 (days in session) or school calendar data, not from CCD staffing fields.[^2_9]


## ESSA Report Card Framework: Charters as Districts

Under ESSA, the term "district" in report card guidance explicitly encompasses charter LEAs: "When used in this document, the term 'district' refers to both traditional public school districts and charters". This means charter LEAs that are their own legal entity are required to publish their own report cards with teacher qualification data, per-pupil expenditures, and disaggregated performance metrics — parallel to traditional districts, not subordinate to them. Researchers using ESSA report card data as a complement to CCD can therefore treat independent charter LEAs as pseudo-districts for disclosure purposes, but must never aggregate their metrics into the surrounding traditional district's figures.[^2_10][^2_5]

## Practical Decision Tree for a Staffing-to-LEA Pipeline

Given the above, a pipeline that needs to attribute each school's bell schedule (or any staffing metric) to its correct LEA should apply the following logic:


| School's charter status and LEA structure | Correct attribution unit | Key distortion risk |
| :-- | :-- | :-- |
| `CHARTR=1`, linked to `LEA_TYPE=7`, `OPERATIONAL_SCHOOLS=1` | The campus's own charter LEA | CMO back-office staff inflating FTE count |
| `CHARTR=1`, linked to `LEA_TYPE=7`, `OPERATIONAL_SCHOOLS>1` | The multi-school charter district LEA | Back-office pooling across campuses |
| `CHARTR=1`, linked to `LEA_TYPE=1/2`, `CHARTER_LEA_TEXT="Not LEA"` | The traditional host district — but flag separately | District PTR distorted by charter inclusion |
| `CHARTR=0`, any LEA type | The district as normal | N/A |

For any district-level equity comparison, the consensus practice is: **exclude Structure A and B charter schools from the traditional district's denominator**, and **report charter LEAs as a separate peer group** matched to similarly-structured charter LEAs, not to conventional districts. The pre-2017-18 CCD data requires extra caution because the "home district" membership rule means LEA-level enrollment figures for traditional districts in at least six states were systematically inflated by cross-LEA charter student counts.[^2_2][^2_4][^2_1][^2_3]
<span style="display:none">[^2_11][^2_12][^2_13][^2_14][^2_15][^2_16][^2_17][^2_18][^2_19][^2_20][^2_21][^2_22][^2_23][^2_24][^2_25][^2_26][^2_27][^2_28][^2_29][^2_30][^2_31][^2_32][^2_33][^2_34][^2_35][^2_36][^2_37][^2_38][^2_39][^2_40][^2_41][^2_42][^2_43][^2_44][^2_45][^2_46][^2_47][^2_48][^2_49][^2_50][^2_51][^2_52][^2_53][^2_54][^2_55][^2_56][^2_57][^2_58][^2_59][^2_60][^2_61][^2_62][^2_63][^2_64][^2_65][^2_66][^2_67][^2_68][^2_69][^2_70][^2_71][^2_72][^2_73][^2_74][^2_75][^2_76][^2_77][^2_78][^2_79][^2_80][^2_81][^2_82][^2_83][^2_84][^2_85][^2_86]</span>

<div align="center">⁂</div>

[^2_1]: https://apps.urban.org/features/education-equity-tool/

[^2_2]: https://nces.ed.gov/ccd/doc/10_Changes_Membership_Reporting_Guidance_201617_201718.docx

[^2_3]: https://files.eric.ed.gov/fulltext/ED618289.pdf

[^2_4]: https://libslide.org/pubs/Perspectives-Appendix-B-Glossary.pdf

[^2_5]: https://edtrust.org/wp-content/uploads/2014/09/What-is-in-ESSA-Public-Reporting.pdf

[^2_6]: https://nces.ed.gov/ccd/pubagency.asp

[^2_7]: https://nces.ed.gov/pubs2001/100_largest/methodology.asp

[^2_8]: https://edpolicyinca.org/sites/default/files/2022-03/a_bodine-jan2008.pdf

[^2_9]: https://nces.ed.gov/programs/coe/pdf/Indicator_CLR/coe_clr_2017_05.pdf

[^2_10]: https://eric.ed.gov/?id=ED578798

[^2_11]: https://nces.ed.gov/pubs2024/2024144.pdf

[^2_12]: https://www.urban.org/sites/default/files/publication/90586/school_funding_brief_1.pdf

[^2_13]: https://www.urban.org/sites/default/files/publication/101052/the_state_of_equity_measurement_0.pdf

[^2_14]: https://nces.ed.gov/learn/blog/tools-tracking-progress-equity-initiatives-school-districts

[^2_15]: https://apps.urban.org/features/school-funding-trends/files/202204_K12_funding_technical_appendix.pdf

[^2_16]: https://plainschools.com/guides/

[^2_17]: https://charterschoolcenter.ed.gov/sites/default/files/upload/toolkits/NCSRC-Intentionally-Diverse-Charter-School-Toolkit.pdf

[^2_18]: https://tcf.org/content/report/advancing-intentional-equity-charter-schools/

[^2_19]: https://www.centerforlearnerequity.org/top-10-resources/

[^2_20]: https://nces.ed.gov/fastfacts/display.asp?id=30

[^2_21]: https://ed.cde.state.co.us/fedprograms/charterschoolinclusion-edtdataanalyses

[^2_22]: https://www.tandfonline.com/doi/full/10.1080/15582159.2023.2273607

[^2_23]: https://nces.ed.gov/ccd/tables/202223_summary_2.asp

[^2_24]: https://publiccharters.org/news/2023-charter-achievements/

[^2_25]: https://nces.ed.gov/ccd/pdf/psu01gen.pdf

[^2_26]: https://files.eric.ed.gov/fulltext/ED674871.pdf

[^2_27]: https://nces.ed.gov/statprog/handbook/ccd.asp

[^2_28]: https://nces.ed.gov/ccd/

[^2_29]: https://files.eric.ed.gov/fulltext/ED661554.pdf

[^2_30]: https://www.ed.gov/sites/ed/files/about/offices/list/ocr/docs/2013-14-first-look.pdf

[^2_31]: https://nces.ed.gov/ccd/pub_overview.asp

[^2_32]: https://nces.ed.gov/ccd/ccddata.asp

[^2_33]: https://crpe.org/assessing-charter-schools-impact-on-districts-too-important-to-get-wrong/

[^2_34]: https://www.the74million.org/article/analysis-new-research-confirms-that-charter-schools-drive-academic-gains-for-their-own-students-and-for-kids-in-nearby-district-schools/

[^2_35]: https://pmc.ncbi.nlm.nih.gov/articles/PMC5015885/

[^2_36]: https://www.centerforlearnerequity.org/wp-content/uploads/OR6.5.17.pdf

[^2_37]: https://www.urban.org/sites/default/files/2023-03/Small and Sparse-Defining Rural School Districts for K–12 Funding.pdf

[^2_38]: https://mpaaa.org/images/downloads/CRDC_2024/civil_rights_data_collection_2023_24_final.pdf

[^2_39]: https://nces.ed.gov/forum/pdf/CRDCReportingGuide_Presentation.pdf

[^2_40]: https://www.centerforlearnerequity.org/wp-content/uploads/RubricPartofLEA.pdf

[^2_41]: https://www.urban.org/sites/default/files/2020/07/31/equal_k-12_state_funding_cuts_could_disproportionately_harm_low-income_students.pdf

[^2_42]: https://www.centerforlearnerequity.org/wp-content/uploads/IN6.5.17.pdf

[^2_43]: https://www.centerforlearnerequity.org/resource/trends-in-special-education-in-charter-and-traditional-public-schools-by-u-s-state/

[^2_44]: https://www.youtube.com/watch?v=lZf-DLbx4F8

[^2_45]: https://nces.ed.gov/admindata/crdc/

[^2_46]: https://www.centerforlearnerequity.org/wp-content/uploads/FocusedreportLEAStatus.pdf

[^2_47]: https://www.centerforlearnerequity.org/wp-content/uploads/Final_CLE-CO-Report-1.pdf

[^2_48]: https://nces.ed.gov/CCD/xls/SY1718_Membership_Staff_Special_Populations_DataNotes.xlsx

[^2_49]: https://nces.ed.gov/ccd/reference_library.asp

[^2_50]: https://www.centerforlearnerequity.org/wp-content/uploads/CLE_CRDC-Methodology-2024.pdf

[^2_51]: https://nces.ed.gov.qipservices.com/ccd/pdf/sdf99gen.pdf

[^2_52]: https://www.cde.state.co.us/datapipeline/24-25_fs029_guidelines_for_lea_school_changes

[^2_53]: https://www.cato.org/policy-analysis/impact-charter-schools-public-private-school-enrollments

[^2_54]: https://nces.ed.gov/ccd/xls/SY_2021-22_LEA_Directory_Companion.xlsx

[^2_55]: https://www.researchforaction.org/wp-content/uploads/2021/07/RFA-Fiscal-Impact-of-Charter-Expansion-September-2017.pdf

[^2_56]: https://www.csasyracuse.org/about-us/about-charter-schools/separating-fact-fiction

[^2_57]: https://nces.ed.gov/ccd/doc/SY_2020-21_Universe_1a_CCD_Nonfiscal_Release_Notes.docx

[^2_58]: https://journals.sagepub.com/doi/10.1177/0013124512458118

[^2_59]: https://www.ed.gov/sites/ed/files/2020/07/report-card-guidance-final.pdf

[^2_60]: https://www.ed.gov/sites/ed/files/policy/elsec/leg/essa/essastatereportcard.pdf

[^2_61]: https://ideas.repec.org/a/tpr/edfpol/v10y2015i3p423-465.html

[^2_62]: https://scholarship.libraries.rutgers.edu/esploro/outputs/journalArticle/Charter-School-Expansion-and-Within-District-Equity/991031665645704646

[^2_63]: https://www.civilrightsproject.ucla.edu/research/k-12-education/integration-and-diversity/choice-without-equity-2009-report

[^2_64]: https://www.sciencedirect.com/science/article/pii/S0047272723001974

[^2_65]: https://crpe.org/charter-schools-good-or-bad-for-students-in-districts/

[^2_66]: https://www.nber.org/system/files/working_papers/w28477/w28477.pdf

[^2_67]: https://stacks.cdc.gov/view/cdc/168584/cdc_168584_DS7.pdf

[^2_68]: https://edtrust.org/wp-content/uploads/2014/09/ESSA-State-and-Local-Report-Cards-Guidance.pdf

[^2_69]: https://edtrust.org/wp-content/uploads/2014/09/Joint-Letter-from-21-Advocacy-Organizations-to-the-U.S.-Department-of-Education-Regarding-Proposed-Guidance-on-State-and-Local-Report-Cards-Under-ESSA-April-2019.pdf

[^2_70]: https://pmc.ncbi.nlm.nih.gov/articles/PMC12366744/

[^2_71]: https://www.p12.nysed.gov/turnaround/documents/LeveragingTImeforSchoolEquity.pdf

[^2_72]: https://www.researchforaction.org/wp-content/uploads/2021/07/RFA-Equity-Authorizing-Toolkit-Final-Nov.-2019.pdf

[^2_73]: https://journals.sagepub.com/doi/10.1177/00317217211043620

[^2_74]: https://www.advocacyinstitute.org/ESSA/Mtg2-Pre-ThinkingGuide-LisaPugh.pdf

[^2_75]: https://wasa-oly.org/WASA/images/WASA/6.0 Resources/Equity/Re-Envisioning Data Processes for Equity.pdf

[^2_76]: https://www.nysed.gov/sites/default/files/programs/charter-schools/charter-school-guidance-for-essa-slfs-reporting-2024-25.pdf

[^2_77]: https://www.centerforlearnerequity.org/wp-content/uploads/CLE-Authorizers-Final.pdf

[^2_78]: https://scholar.harvard.edu/files/fryer/files/2014_injecting_charter_school_best_practices_into_traditional_public_schools.pdf

[^2_79]: https://nces.ed.gov/ccd/files.asp

[^2_80]: https://educationdata.urban.org/

[^2_81]: https://files.eric.ed.gov/fulltext/ED565676.pdf

[^2_82]: https://nces.ed.gov/ccd/tables/202425_summary_2.asp

[^2_83]: https://eric.ed.gov/?id=ED559991

[^2_84]: https://educationdata.urban.org/data-explorer/about

[^2_85]: https://www.policymap.com/data/sources/national-center-for-education-statistics-common-core-of-data

[^2_86]: https://nces.ed.gov/pubs2009/100_largest/methodology.asp


---

# For U.S. charter schools that are NOT their own LEA but are reported within a traditional school district's LEA in NCES CCD, is there a reliable method to separate the charter's instructional staff (ccd_lea_059 / ccd_sch_059) and enrollment (ccd_sch_052) from the host district's totals? Does school-level staffing data (ccd_sch_059) exist and is it complete enough to compute per-school student-teacher ratios? What are the coverage/quality caveats?

I now have sufficient, authoritative material from the NCES official documentation and related sources to answer this precisely. The key facts are:

1. The CCD school-level FS059 file **exists** but contains **teachers only** (TOTTCH/PKTCH/KGTCH/ELMTCH/SECTCH/UGTCH) — no paraprofessionals, counselors, librarians, or other staff[^3_1]
2. School-level enrollment (FS052) exists and is largely complete, providing per-school membership usable for per-school PTR
3. The aggregation guidance (>95% valid = reliable, 85–95% = caution, <85% = unreliable) is the NCES-prescribed threshold for using school-level aggregates[^3_1]
4. Staff categories not reported at the SEA level are imputed at the SEA level, but **not imputed at the LEA or school level**[^3_1]
5. The National Alliance's "Geographic School District" construct is the best published methodology for re-attributing Structure C dependent charters to their host districts[^3_2]

***

## What the School-Level FS059 File Contains

The CCD school-level staff file (FS059, releasing as `CCD_SCH_059_xxyy`) exists and is publicly available for every survey year from SY 2016-17 forward in long format (earlier years in legacy wide format). The critical constraint is explicitly stated in NCES's own usage notes: **school-level data include FTE for teachers only**. The permitted teacher categories are: prekindergarten teachers (`PKTCH`), kindergarten (`KGTCH`), elementary (`ELMTCH`), secondary (`SECTCH`), and ungraded (`UGTCH`), summed to `TOTTCH` (derived). Everything else — paraprofessionals (`PARA`), instructional coordinators (`CORSUP`), counselors (`ELMGUI`/`SECGUI`), librarians (`LIBSPE`/`LIBSUP`), school administrators (`SCHADM`), student support staff (`STUSUP`), and all LEA-level administrative staff (`LEAADM`, `LEASUP`) — is available only at the LEA and SEA levels via the same FS059 file. This means that for a dependent-charter school operating under a traditional district's LEAID, you can separate that school's teacher headcount from the district total by joining on NCESSCH, but you **cannot** isolate its paraprofessionals, counselors, or administrative staff at the school level.[^3_3][^3_1]

## Separating Dependent-Charter Enrollment (FS052)

School-level membership (FS052, `CCD_SCH_052_xxyy`) is substantially more complete than the staffing file and covers all operational schools with disaggregation by grade, sex, and race/ethnicity. For Structure C charters (those with `CHARTR=1` whose `LEAID` points to a traditional district), each charter school has its own NCESSCH row in the membership file. The separation method is: filter the school membership file for `CHARTR=1` within a given `LEAID`, sum those rows for charter enrollment, and subtract from the LEA-level `MEMBER` total for non-charter enrollment. This is numerically clean as long as the LEA is not using the pre-2017-18 home-district reporting rule (see previous answer). One additional wrinkle noted in NCES documentation: a student is counted only in the school where they spend most of the day, but "LEA membership aggregated from school-level rows does not always equal the LEA's directly reported membership" because LEAs that tuition-out students to other LEAs count those students in their own LEA-level membership but not in any school row. For charter schools within the same district, this discrepancy is typically small but non-zero.[^3_1]

## Computing Per-School PTRs: What Is Feasible

A per-school pupil/teacher ratio for a dependent charter is computable as:

$$
\text{PTR}_{school} = \frac{\text{MEMBER}_{NCESSCH}}{\text{TOTTCH}_{NCESSCH}}
$$

Both numerator and denominator exist at the school level. The question is completeness.

## Coverage and Quality Caveats

**Coverage of school-level teacher FTE is uneven across states and charter school types.** NCES has not published a single national completeness rate for the school-level FS059 file specifically for charter schools, but several indicators bound the problem:

- NCES's own aggregation guidance for school-level data sets the reliability threshold at **95% valid non-null values**; anything below 85% is "unreliable". Staff counts at the school level are known to fall below this threshold in a non-trivial number of states. In NCES's comparison of school-level FTE counts against the Teacher Compensation Survey (an external benchmark), FTE teacher counts in the CCD School Universe were within 1% of each other for only **58% of individual schools**; they were within 10% for 87% of schools across 15 states. This is not a directional bias but reflects genuine within-state variance in how schools report FTEs on an October snapshot.[^3_4][^3_1]
- **Staff at the SEA level is imputed when missing; staff at the LEA and school levels is NOT imputed**. Missing values for school-level `TOTTCH` appear as nulls with `DMS_FLAG = "Missing"` — they are silently absent from any sum. This means that for states where charter schools disproportionately fail to submit school-level staff data (a known issue in some states with large numbers of independently governed charter LEAs that route staffing through a separate HR system), the school-level PTR will be systematically unmeasurable for a subset of schools rather than biased — you will simply have holes.[^3_1]
- The **`IAFTEPUP` flag** in the LEA-level FS059 companion file identifies records where both total teachers and the PTR "fluctuated in the current year as compared to previous years," producing values of `SUPPRESSED`, `UNSUPPRESSED`, or `NOT APPLICABLE`. A suppressed value at the LEA level does not propagate to the school file, but it signals that the LEA's staffing data was anomalous and that school-level rows feeding into it may be unreliable.[^3_3]
- **California-specific structural break:** In SY 2018-19, California restructured its CCD reporting so that direct-funded charter schools were reclassified as separate LEAs (moving from Structure C to Structure A/B). NCES release notes specifically called this out as causing "the addition of more than 1,000 new LEAs" and corresponding changes to California's school-level vs. LEA-level enrollment and staffing counts. Any longitudinal pipeline spanning 2017-18 and 2018-19 for California charters must treat this as a hard structural break: the NCESSCH identifiers for those schools persist, but their LEAID and all LEA-level staffing aggregations change.[^3_5]
- **Charter schools with non-standard grade structures** (many CMO high schools or blended-learning schools) may report `UGTCH` (ungraded teachers) as their primary teacher category. Pipelines that only sum `ELMTCH + SECTCH` will undercount teachers in these schools.


## The Non-Teacher Staff Problem

For equity metrics that require all instructional staff (e.g., counselor-to-student ratios, paraprofessional deployment), there is **no school-level field in CCD** at all. The only path to school-level non-teacher staffing is the Civil Rights Data Collection (CRDC), which collects counselors, psychologists, and security personnel at the school level directly — but CRDC is collected every two years, not annually, and its universe is separate from CCD (all public schools serving students, regardless of LEA structure). Joining CCD school-level membership from FS052 with CRDC school-level counselor counts via NCESSCH is the standard approach used by the Urban Institute's equity work and the Center for Learner Equity's CRDC analysis.[^3_6][^3_7][^3_1]

## The Enrollment Re-Attribution Approach (National Alliance Method)

When the goal is not just separating a charter from its host district but re-attributing it to its geographic district (e.g., for a regional equity analysis where all schools serving a catchment area should be analyzed together regardless of LEA structure), the National Alliance for Public Charter Schools published a methodology in 2022 using a **"Geographic School District" variable**. They geocode each school's physical address from CCD FS029, overlay it on NCES EDGE shapefile district boundaries, and assign the school to the traditional district where it is physically located — regardless of its LEAID. For dependent Structure C charters this makes no difference (they are already inside the host district's LEAID), but for Structure A and B charters it re-attributes enrollment and staffing to the geographic district for comparative purposes. The key methodological caution they note: virtual schools must be excluded from this geocoding approach since they have no physical catchment.[^3_2]

## Summary of What Works and What Doesn't

| Metric | Data source | Feasibility for Structure C charter | Key caveat |
| :-- | :-- | :-- | :-- |
| Per-school enrollment | CCD FS052 (`CCD_SCH_052`) | ✅ Reliable; join on NCESSCH | School-level ≠ LEA-level for tuitioned-out students |
| Per-school teacher FTE | CCD FS059 school file (`CCD_SCH_059`) | ⚠️ Feasible but incomplete | School-level only for teachers; missing data not imputed; ~87% of schools within 10% of benchmark |
| Per-school PTR | FS052 ÷ FS059 TOTTCH | ⚠️ Computable where both are non-null | Null TOTTCH produces silent missing PTR, not zero |
| Paraprofessionals, counselors, librarians | CCD FS059 LEA file only | ❌ Not available at school level | Must use CRDC for school-level non-teacher staff |
| Instructional time / bell schedule | Not in CCD at any level | ❌ Entirely absent | Requires FS033 (days in session) or school calendar data |
| Longitudinal tracking post-2018-19 in California | Any CCD field | ⚠️ Structural break | Pre/post reclassification requires LEAID crosswalk |

<span style="display:none">[^3_10][^3_11][^3_12][^3_13][^3_14][^3_15][^3_16][^3_17][^3_18][^3_19][^3_20][^3_21][^3_22][^3_23][^3_24][^3_25][^3_26][^3_27][^3_28][^3_29][^3_30][^3_31][^3_32][^3_33][^3_34][^3_35][^3_36][^3_37][^3_38][^3_39][^3_40][^3_41][^3_42][^3_43][^3_44][^3_45][^3_46][^3_8][^3_9]</span>

<div align="center">⁂</div>

[^3_1]: https://nces.ed.gov/ccd/doc/CCD_Nonfiscal_DataFile_and_Usage_Notes.docx

[^3_2]: https://files.eric.ed.gov/fulltext/ED625516.pdf

[^3_3]: https://nces.ed.gov/ccd/xls/2014-15 CCD Companion_LEA%20Staff_File_Layout.xlsx

[^3_4]: https://nces.ed.gov/pubs2010/tcs2007/sec5a.asp

[^3_5]: https://nces.ed.gov/ccd/doc/SY_2020-21_Universe_1a_CCD_Nonfiscal_Release_Notes.docx

[^3_6]: https://files.eric.ed.gov/fulltext/ED618289.pdf

[^3_7]: https://www.centerforlearnerequity.org/wp-content/uploads/CLE_CRDC-Methodology-2024.pdf

[^3_8]: https://nces.ed.gov/ccd/files.asp

[^3_9]: https://nces.ed.gov/ccd/pdf/psu01gen.pdf

[^3_10]: https://nces.ed.gov/ccd/

[^3_11]: https://nces.ed.gov/statprog/handbook/pdf/ccd.pdf

[^3_12]: https://www.ed.gov/media/document/c059-8-1doc-18911.doc

[^3_13]: https://nces.ed.gov/ccd/pdf/documentation13yr.pdf

[^3_14]: https://nces.ed.gov/ccd/ccddata.asp

[^3_15]: https://nces.ed.gov/ccd/doc/SY_2024-25_Universe_1a_CCD_Nonfiscal_Release_Notes.docx

[^3_16]: https://files.eric.ed.gov/fulltext/ED591173.pdf

[^3_17]: https://data-nces.opendata.arcgis.com/search

[^3_18]: https://catalog.data.gov/dataset/common-core-of-data-nonfiscal-survey-2015-16

[^3_19]: https://ies.ed.gov/use-work/dataset/2024-25-common-core-data-ccd-universe-files-version-1a

[^3_20]: https://nces.ed.gov/CCD/xls/SY2021-22_RPGM_Directory_Companion.xlsx

[^3_21]: https://nces.ed.gov/ccd/tables/202324_summary_2.asp

[^3_22]: https://www.ed.gov/media/document/edfacts-dg528-dg644-staff-fte-v220-fs059-22-0-112797.docx

[^3_23]: https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2023-24

[^3_24]: https://nces.ed.gov/ccd/pub_snf_report.asp

[^3_25]: https://files.eric.ed.gov/fulltext/ED579146.pdf

[^3_26]: https://nces.ed.gov/ccd/stnfisinfo.asp

[^3_27]: https://nces.ed.gov/learn/blog/common-core-data-ccd-nonfiscal-data-releases-how-national-center-education-statistics-improved

[^3_28]: https://www.zelma.ai/edfacts

[^3_29]: https://ies.ed.gov/use-work/dataset/2023-24-common-core-data-ccd-universe-files-version-1a

[^3_30]: https://nces.ed.gov/pubs2010/tcs2007/tables/table_05.asp

[^3_31]: https://nces.ed.gov/ccd/stnfis.asp

[^3_32]: https://nces.ed.gov/programs/digest/d23/tables/dt23_208.40.asp

[^3_33]: https://educationdata.urban.org/documentation/schools.html

[^3_34]: https://www.ed.gov/media/document/edpass-ccd-staff-fte-and-membership-2025-2026-113867.pdf

[^3_35]: https://www.ed.gov/media/document/fs059-15-1docx-19347.docx

[^3_36]: https://nces.ed.gov/pubs2024/2024144.pdf

[^3_37]: https://nces.ed.gov/ccd/pdf/StNonfis081cgen.pdf

[^3_38]: http://www.asasrms.org/Proceedings/papers/1995_141.pdf

[^3_39]: https://nces.ed.gov/ccd/pub_overview.asp

[^3_40]: https://www.cde.ca.gov/ds/ad/fsenrcum.asp

[^3_41]: https://nces.ed.gov/learn/blog/nces-releases-updated-2022-23-data-table-school-district-structures

[^3_42]: https://nces.ed.gov/ccd/CCD13yr.asp

[^3_43]: https://nces.ed.gov/ccd/pdf/pau96gen.pdf

[^3_44]: https://nces.ed.gov/ccd/pdf/psu93gen.pdf

[^3_45]: https://educationdata.urban.org/csv/ccd/codebook_schools_ccd_directory.xls

[^3_46]: https://www.ed-data.org/article/Frequently-Asked-Questions

