# **Methodological Protocols for Integrating Charter Schools in District-Level Education-Equity Metrics: Analytical Practices, Structural Distortions, and Empirical Guidelines**

The rapid growth of the public charter school sector since the early 1990s has fundamentally altered the administrative and spatial architecture of public education in the United States1. Traditional public school systems are geographically bounded entities mandated to enroll every student residing within their borders4. By contrast, charter schools operate as schools of choice under performance contracts governed by private, unelected boards, often drawing students from multiple neighborhoods without regard to traditional attendance boundaries7. This divergence in governance, spatial enrollment, and staffing structures introduces severe challenges for researchers and policy analysts who construct district-level education-equity metrics12.  
Calculations of core resource indicators—such as student-teacher ratios and instructional-time-per-student—become highly sensitive to the methodological choices made when integrating charter systems into local datasets12. Failing to properly align these datasets leads to systematic measurement errors, masking severe resource disparities and biasing state-level funding and accountability evaluations12.

## **Comparative Taxonomy of Methodological Approaches**

When modeling district-level education equity, analysts generally deploy one of three core methodological frameworks to manage charter schools: integrating them as independent "pseudo-districts," excluding them entirely from the analytical sample, or reporting them as separate, segmented entities nested within a parent geographic footprint12. The selection of the framework must align with the specific research objective, as each choice introduces distinct trade-offs for data validity and structural interpretation12.

### **Integration as Pseudo-Districts**

The pseudo-district model treats each independent charter school or charter network as an autonomous, self-contained school district12. This approach aligns directly with federal data structures19. In the National Center for Education Statistics (NCES) Common Core of Data (CCD), these agencies are designated as "Agency Type 7" (Charter Agencies), indicating that all associated schools are charter schools19. Treating these Type 7 agencies as independent pseudo-districts preserves the organizational link between a charter’s internal staff and its enrolled student body, enabling highly accurate assessments of resource deployment within the charter sector itself12.  
The primary limitation of this model is its complete decoupling from physical geography5. Because charter LEAs do not operate within fixed geographic boundaries, the Census Bureau's school district boundary files (EDGE) and the corresponding Census demographic datasets strictly exclude independent charter school districts5. Consequently, the pseudo-district model prevents analysts from conducting spatial equity studies or correlating student resource access with local neighborhood characteristics, such as the poverty estimates provided by the Small Area Income and Poverty Estimates (SAIPE) program5.

### **Systemic Exclusion**

The second methodological approach is the deliberate exclusion of charter schools and charter LEAs from district-level databases16. This practice is standard in geographic public school finance modeling16. For example, the Urban Institute's funding progressivity indices exclude charter-only districts, online networks, and alternative education programs from their calculations, restricting the analytical sample to traditional public school districts with defined geographic footprints17.  
The exclusion of charter schools is methodologically necessary to avoid severe distortions when aligning fiscal data with geographic census tracts17. Because charter schools do not possess a local property tax base and are frequently omitted from the geographic collections of the U.S. Census Bureau’s School District Finance Survey (F-33), integrating them would corrupt the calculation of state funding progressivity metrics16.  
However, this exclusion introduces a profound coverage bias17. In jurisdictions with high charter school penetration, such as the District of Columbia, where over 40% of public school students attend charter schools, excluding the charter sector artificially reduces the reported public school enrollment of the geographic area and presents an incomplete picture of the region's overall public resource allocation17.

### **Segmented and Parallel Reporting**

Segmented reporting represents the current consensus best practice for multi-sector equity analyses, particularly in studies monitoring access for historically marginalized student populations12. In this framework, charter schools are geographically grouped based on the physical boundaries of the "parent" traditional public school district in which they reside12. However, their enrollment, staffing, and fiscal metrics are analyzed and reported separately from the TPS counts12.  
This parallel structure, heavily utilized by the Center for Learner Equity (CLE), prevents the masking of critical differences in student demographics and avoids averaging out sector-specific resource disparities12. By segmenting the data, analysts can evaluate how resources are distributed across traditional and charter sectors within the same geographic community, while preserving the structural nuances of their respective governance models12.

| Methodological Framework | Operational Definition in Data | Key Analytical Strengths | Primary Empirical Limitations |
| :---- | :---- | :---- | :---- |
| **Pseudo-Districts (LEA Type 7\)** | Evaluates every independent charter agency as an autonomous district19. | Captures precise organizational staffing and spending; prevents dilution of sector-specific data12. | Eradicates spatial/geographic analysis; excludes charter data from neighborhood demographic models5. |
| **Systemic Exclusion** | Omits all Type 7 charter agencies and non-operating systems from the dataset16. | Preserves the integrity of geographic property tax and funding progressivity models16. | Fails to capture overall public resource distribution, especially in high-charter urban centers17. |
| **Segmented & Parallel Reporting** | Geocodes charter schools to parent TPS boundaries but reports sectors in isolation12. | Uncovers inter-sector inequities within the same community; highlights demographic sorting12. | Requires complex spatial joins and extensive state-level administrative crosswalks27. |

## **Structural Distortions and Partitioning Errors in Resource Metrics**

A failure to correctly partition charter school enrollment and staffing counts relative to their parent geographic districts introduces severe statistical distortions into district-level equity metrics14. These partitioning errors manifest as mathematically invalid ratios and skewed resource distributions14.

### **Numerator-Denominator Mismatch and Staffing Ratio Distortion**

The most pervasive distortion in district-level resource metrics occurs when student enrollment and instructional staff counts are misaligned across distinct database tables14. In several state administrative systems, students residing within a geographic district boundary who choose to attend a charter school are still tracked as district-resident enrollment for funding pass-through purposes30. However, the charter school’s teachers are reported under the administrative payroll of an independent charter LEA30.  
If an analyst calculates the district-level student-teacher ratio by including these charter students in the numerator (district enrollment) but failing to include the charter school's teachers in the denominator (district FTE staff), the resulting student-teacher ratio for the parent district will be artificially inflated14.  
This distortion is exacerbated by real-world data gaps and reporting anomalies in federal datasets31. For example, in the 2014–15 and 2015–16 CCD nonfiscal reporting cycles, Utah was unable to report staff data, forcing NCES to impute state-level staff values, while Wyoming failed to report staff data at the LEA level entirely, leaving all local teacher values as missing (-1)31. Similarly, Illinois has experienced large, sudden shifts in Free and Reduced Price Lunch (FS033) and FTE Staff (FS049) counts21. When researchers construct aggregated district-level averages without sector-specific validation, these state-level reporting gaps generate profound estimation errors in regional staffing ratios21.

### **The Impact of Virtual and Online Charter Systems**

The integration of virtual or online charter schools into geographic district-level metrics introduces a massive downward bias in perceived local staffing resources32. Virtual charter schools represent approximately 33.3% of all virtual schools but command a disproportionate 58.4% of all virtual enrollment33.  
Because online instruction relies on asynchronous modules and centralized grading, virtual schools operate with vastly higher student-teacher ratios, averaging 24.4 students per teacher compared to the national public school average of 14.833. These elevated ratios are strongly associated with lower graduation rates and school performance ratings33.  
If virtual charter students and staff are geographically aggregated into the parent physical district’s database, the local student-teacher ratio will appear significantly worse than the actual classroom reality33. This mis-partitioning obscures the true density of physical classroom teachers available to local, in-person students33.

### **Scraped schedule and Time-Per-Student Metrics**

A similar attribution error occurs when measuring instructional-time-per-student using web-scraped "bell schedule" data34. While online charter schools and large virtual consortium programs maintain centralized, digital databases of their academic calendars and instructional strategies, traditional single-district programs are highly decentralized35.  
Attempts to scrape and attribute bell schedules to geographic districts without isolating virtual charter schools lead to severe measurement errors, as the highly flexible, non-classroom-based schedules of online charters are mistakenly averaged into the highly rigid, physical schedules of local neighborhood schools35.

## **Double-Counting Anomalies and "Holder Record" Inflation**

In addition to partitioning errors, the administrative complexity of charter network reporting structures frequently introduces double-counting anomalies that artificially inflate or deflate student-staff ratios14.

### **Teacher Aggregation Surplus**

Because teacher full-time equivalent (FTE) counts are collected and reported at three distinct levels of the CCD—school, agency, and state—split-site teaching creates significant data anomalies14. In cases where a specialized teacher (e.g., an art or speech-language specialist) provides instruction to pupils across multiple schools, their FTE may be reported fully at each individual school site to reflect their local presence14.  
When these school-level files are aggregated upward to the district or state level, the sum of the school-level teacher counts frequently exceeds the actual unduplicated state-level staff totals14. This aggregation surplus generates an overestimation of teaching staff and artificially deflates the calculated student-teacher ratio for the region14.

### **The NAPCS Modified Count System and "Holder Records"**

A major source of enrollment distortion involves the presence of "Holder Records" within federal datasets37. The National Alliance for Public Charter Schools (NAPCS) developed the "Modified Count System" to address the reality that not all records in the federal CCD represents a physical school37.  
In many states, charter school networks or Charter Management Organizations (CMOs) report their consolidated student enrollment under a single administrative "Holder Record"27. In the federal database, this Holder Record appears to be a massive physical school with an unusually large student population, while the actual physical campuses where the students receive instruction are reported with zero or missing enrollment data37.  
If an analyst conducts a spatial join or a school-level equity study without adjusting for these Holder Records, they will mistakenly conclude that several local charter campuses are entirely un-enrolled and un-staffed, while a single administrative office possesses an impossibly low student-teacher ratio37.

### **Audit Evidence of Contractual and Ratio Manipulation**

The potential for administrative reporting structures to distort staffing ratios is illustrated by the Fiscal Crisis & Management Assistance Team (FCMAT) audit of Options for Youth (OFL) charter schools15. The audit revealed that the charter schools double-counted the salaries of certificated administrators on their state SB 740 forms, artificially inflating their reported instructional expenditures15.  
Furthermore, the charter school manipulated the calculation of its student-teacher ratio by utilizing a highly unorthodox FTE definition15. The school’s employment contracts mandated 1,680 hours of annual instructional time, but designated this assignment as 1.92 FTE "for the sole purpose of calculating the student-teacher ratio pursuant to Education Code 51745.6 and the prescribed formula and definitions set forth in Title V regulations"15.  
By nearly doubling the reported teacher FTE for a single physical teacher, the charter school artificially deflated its official student-teacher ratio, demonstrating how administrative reporting loopholes can be used to construct a false appearance of high classroom resource density15.

## **Equity Metric Misalignments: Demographic Sorting and Staffing Sensitivity**

Integrating charter schools into district-level equity metrics without segmentation severely distorts the analysis of resource distribution across vulnerable student subgroups, particularly students with disabilities (SWDs)12.

### **LEA Status and Special Education Inclusion**

The governance structure of a charter school—specifically whether it operates as its own independent LEA or as a dependent school within a traditional public school district—profoundly shapes its special education capacity and enrollment12. Research by the Center for Learner Equity (CLE) reveals that charter schools functioning as part of a traditional district LEA report a slightly higher percentage of students with disabilities educated in highly inclusive general education settings (84.2%) compared to charters operating as independent LEAs (82.6%)13.  
Dependent charters typically leverage the centralized special education infrastructure of their host district, utilizing district-employed psychologists, speech therapists, and self-contained regional classrooms12. This relationship allows dependent charters to enroll students with more intensive needs and place them in general education settings, while referring students requiring self-contained placements to traditional district-run schools12.  
If student placement data from these sectors are blended into a single district-level metric, the high general education integration rates of the charter sector will mask the segregative or restrictive placement patterns of the traditional public schools, or vice versa, leading to distorted federal compliance monitoring13.

### **Quantitative Segregation Cascades**

The demographic sorting driven by charter school expansion has been rigorously documented in peer-reviewed research39. Utilizing a triple-differences design that exploits between-grade-level variations in charter expansion, a major Urban Institute study demonstrated that growth in charter school enrollment causally increases the racial and ethnic segregation of Black, Hispanic, and White students within school districts39.  
The prefered estimates indicate that a 1 percentage point increase in a district’s charter enrollment share causes a 0.10 to 0.11 percentage point increase in the segregation of Black or Hispanic students, as measured by the variance ratio index39. Interestingly, while charter penetration increases within-district school segregation, it simultaneously decreases between-district segregation in highly fragmented metropolitan areas by drawing diverse student bodies across traditional district boundaries39.  
If researchers evaluate regional integration trends using aggregated county or metropolitan-level metrics, these countervailing forces will cancel each other out, completely obscuring the localized, segregative sorting taking place within individual neighborhoods39.

### **The Sensitivity of Staffing Metrics to Personnel Classification**

The volatility of resource equity metrics is highly dependent on which categories of school personnel are included in the calculation42. A state-level audit of the Utah State Office of Education (USOE) illustrates this sensitivity42.  
USOE originally reported a statewide student-teacher ratio of 25.3 students per teacher42. The audit revealed that this calculation omitted special education teachers42. When special education teachers were properly integrated, the statewide ratio dropped to 22.5, demonstrating a substantial shift in perceived classroom resource density42.  
Furthermore, the audit demonstrated that the student-adult ratio—which includes non-instructional support staff—was highly sensitive to the inclusion of instructional aides and library media support42. USOE originally reported a student-adult ratio of 21.042. When the audit team included the state’s 7,359 FTE instructional aides and 379 FTE library support staff, the student-adult ratio dropped to 15.342. This empirical variance proves that resource metrics are highly volatile and easily manipulated based on the administrative partitioning of specialized personnel42.

## **Technical Protocols for District-Level Mapping and System Identification**

To execute rigorous segmented or pseudo-district analyses, researchers must utilize federal database structures to identify, isolate, and map charter school systems27.

NCES School ID Hierarchical Structure:  
\[State FIPS: 2 Chars\] \+ \[District LEAID: 5 Chars\] \+ \[School SCHNO: 5 Chars\]  
Example: 06 12345 67890  
           |     |     |  
           |     |     \+---\> Unique School Number (SCHNO)  
           |     \+---------\> NCES Local Education Agency ID (LEAID)  
           \+---------------\> State FIPS Code (e.g., 06 for California)

### **Longitudinal Matching and the NCES ID System**

The structural foundation for tracking public schools and districts longitudinally is the unique identification numbering system established by the National Center for Education Statistics27. The standard NCES school identifier is a hierarchical twelve-character string27.  
The first two digits correspond to the Federal Information Processing Standards (FIPS) state code27. The next five digits represent the unique Local Education Agency ID (LEAID), which is assigned to the operating administrative unit27. The final five digits represent the unique school number (SCHNO) within that LEA27.  
Because charter schools frequently undergo administrative changes—such as shifting from a dependent district structure to an independent LEA or merging with another network—their LEAID and their twelve-digit NCES ID can change over time27. To conduct longitudinal analyses without artificial school-closure bias, researchers must track schools using their seven-character NCES School ID (FIPST \+ SCHID), which remains constant across administrative migrations27.

### **Administrative Identification and Management Organization Crosswalks**

In the NCES CCD files, several key variables allow for the precise filtering and classification of charter schools and agencies21:

* **CHARTER\_TEXT**: Located in the CCD Public Elementary/Secondary School Universe file, this variable acts as the primary indicator to identify whether an individual school is a public charter school45.  
* **LEA\_TYPE / agency\_type**: Located in the CCD Local Education Agency Universe file, this variable categorizes the administrative structure of the agency20. A value of 7 designates an "Independent Charter Agency," indicating that all schools operated under this agency are charter schools19.

To monitor the growing concentration of charter schools managed by external organizations, the U.S. Department of Education’s EDFacts system collects detailed rosters linking schools to their parent management entities28. Analysts utilize specific file specifications to construct these networks48:

* **EDFacts File Specification 196 (FS196)**: This specification dictates the submission of the "Management Organization for Charter Schools Roster"28. It compiles comprehensive directory data on the management organizations themselves, including the organization's legal name, its physical address, its Employer Identification Number (EIN), and its organizational classification (e.g., nonprofit Charter Management Organization \[CMO\] or for-profit Education Management Organization \[EMO\])28.  
* **EDFacts File Specification 197 (FS197)**: This file serves as the administrative crosswalk linking individual schools to their management organizations28. It pairs the state and federal identifiers of the school—specifically the NCES Local Education Agency ID (LEAID / DG1) and the NCES School ID (DG529)—directly with the Management Organization's Employer Identification Number (DG833)28.

By merging these two databases, researchers can evaluate equity metrics across different management sectors, controlling for the distinct operational profiles of nonprofit CMOs and for-profit EMOs28.

## **Synthesized Methodological Guidelines and Strategic Matrix**

To assist educational researchers, policy analysts, and state administrative offices in selecting the correct analytical protocol, the following matrix pairs specific research objectives with their appropriate charter handling model, identifies the relevant federal database variables, and outlines the corresponding risks of empirical bias.

| Core Research Objective | Recommended Handling Model | Primary NCES / EDFacts Variables | Critical Risks of Empirical Bias | Methodological Mitigation |
| :---- | :---- | :---- | :---- | :---- |
| **State School Finance Progressivity & Local Cost-Wages** \[cite: 17, 50\] | Systemic Exclusion of Charter Sector16 | LEA\_TYPE \= 7 (CCD Agency Universe)20; SCHLEV \= 05, 06, 07 (Census Finance)16. | Understates geographic public enrollment; distorts aggregate spending in high-charter urban areas17. | Conduct parallel local checks; exclude jurisdictions where charter enrollment share exceeds a 10% threshold17. |
| **Comparative Multi-Sector Equity & Subgroup Tracking** \[cite: 12, 13, 26\] | Segmented & Parallel Geographic Reporting12 | CHARTER\_TEXT \= "Yes" (CCD School Universe)45; geocoded ST\_LEAID / parent spatial boundary27. | Spatial mismatch and attribution errors; failure to align independent charter LEAs with neighborhood boundaries5. | Deploy geographic geographic information systems (GIS) spatial joins to assign charter coordinates to host TPS boundaries51. |
| **Organizational Resource Allocation & Administrative Efficiency** \[cite: 53, 54\] | Pseudo-District Model (LEA Type 7\)12 | LEA\_TYPE \= 720; FS196 / FS197 (CMO/EMO classification)28. | Scale-economy bias; overstates administrative overhead in small-enrollment charter LEAs53. | Include continuous variables for school/agency enrollment size and average school size in multivariate regressions30. |
| **Special Education Placement Trends & Inclusive LRE Compliance** \[cite: 13, 26\] | Segmented Parallel reporting by LEA Governance Type12 | FS002 (Children with Disabilities)55; LEA\_TYPE (Dependent vs. Type 7 Independent)12. | Demographic selection bias; inclusive LRE metrics mask the systemic cream-skimming of milder disabilities into charters13. | Disaggregate the analysis by primary disability category (FS002) and student race/ethnicity subgroups26. |
| **Physical Classroom Staffing Densities & Class-Size Trends** \[cite: 42, 57\] | Exclusion of Virtual and Non-Classroom-Based Charters32 | VIRTUAL (CCD School Directory)31; FS059 (Staff FTE)55. | Severe downward bias in staffing density; virtual school staffing patterns (24:1) corrupt physical classroom models (14:1)33. | Restrict the analytical sample to brick-and-mortar schools, filtering out schools designated as virtual or non-classroom-based32. |

## **Conclusion**

The structural and administrative diversity of the public charter school sector means that no single, unified method for handling charter data is appropriate for all educational research12. When constructing district-level education equity metrics, the default inclusion of charter schools without sector-specific validation introduces severe partitioning errors, double-counting anomalies, and demographic selection biases that can easily invalidate analytical findings14.  
For investigations focused on geographic school funding progressivity, the systemic exclusion of charter schools remains necessary to align fiscal data with geographic census boundaries16. Conversely, for analyses of special student populations, inclusive placements, and classroom staffing densities, researchers must utilize segmented, parallel geographic reporting12.  
By exploiting the unique hierarchical identifiers of the NCES ID system, geocoding schools to parent TPS boundaries, and leveraging EDFacts management organization crosswalks (FS196/FS197), analysts can construct highly accurate, multi-sector models that avoid empirical distortions and deliver reliable assessments of education equity across all public schools27.

#### **Works cited**

1. Thirty Years of Charter Schools: What Does Lottery-Based Research Tell Us?, [https://blueprintcdn.com/wp-content/uploads/2025/04/cohodes-roy-2024-thirty-years-of-charter-schools-what-does-lottery-based-research-tell-us.pdf](https://blueprintcdn.com/wp-content/uploads/2025/04/cohodes-roy-2024-thirty-years-of-charter-schools-what-does-lottery-based-research-tell-us.pdf)  
2. The Condition of Education 2020, [https://nces.ed.gov/pubs2020/2020144.pdf](https://nces.ed.gov/pubs2020/2020144.pdf)  
3. Charter schools are changing the landscape of public education in California. TABLE OF CONTENTS, [https://www.aclusocal.org/app/uploads/2016/12/report-unequal-access-080116.pdf](https://www.aclusocal.org/app/uploads/2016/12/report-unequal-access-080116.pdf)  
4. The Nation's Achievement Inequality Report Card: An Assessment of Test Score and Equality Trends in Traditional Public, Charter, Catholic, and Department of Defense Schools \- EdWorkingPapers.com, [https://edworkingpapers.com/sites/default/files/ai26-1378.pdf](https://edworkingpapers.com/sites/default/files/ai26-1378.pdf)  
5. Composite School District Boundaries File Documentation, 2017 \- National Center for Education Statistics (NCES), [https://nces.ed.gov/programs/edge/docs/EDGE\_SDBOUNDARIES\_COMPOSITE\_2017.pdf](https://nces.ed.gov/programs/edge/docs/EDGE_SDBOUNDARIES_COMPOSITE_2017.pdf)  
6. Education Demographic and Geographic Estimates (EDGE) Program Composite School District Boundaries File Documentation, [https://nces.ed.gov/programs/edge/docs/EDGE\_SDBOUNDARIES\_COMPOSITE\_FILEDOC.pdf](https://nces.ed.gov/programs/edge/docs/EDGE_SDBOUNDARIES_COMPOSITE_FILEDOC.pdf)  
7. 2026 NPE Report Card \- Network For Public Education, [https://networkforpubliceducation.org/wp-content/uploads/2026/06/2026-NPE-Report-Card.pdf](https://networkforpubliceducation.org/wp-content/uploads/2026/06/2026-NPE-Report-Card.pdf)  
8. The Road to School | Urban Institute, [https://www.urban.org/sites/default/files/publication/97151/the\_road\_to\_school\_6.pdf](https://www.urban.org/sites/default/files/publication/97151/the_road_to_school_6.pdf)  
9. Changes in the Performance of Students in Charter and District Sectors of U.S. Education: An Analysis of Nationwide Trends \- Harvard Kennedy School, [https://www.hks.harvard.edu/sites/default/files/Taubman/PEPG/research/PEPG20\_04.pdf](https://www.hks.harvard.edu/sites/default/files/Taubman/PEPG/research/PEPG20_04.pdf)  
10. Scoring States on Charter School Integration \- The Century Foundation, [https://tcf.org/content/report/scoring-states-charter-school-integration/](https://tcf.org/content/report/scoring-states-charter-school-integration/)  
11. Show HN: Lookup the school district associated with a street address in the US | Hacker News, [https://news.ycombinator.com/item?id=39302436](https://news.ycombinator.com/item?id=39302436)  
12. Meeting the Individual Needs of All Students: The Role of Charter Schools, [https://www.help.senate.gov/download/coco-testimonypdf](https://www.help.senate.gov/download/coco-testimonypdf)  
13. Educational Settings of Students with Disabilities in Charter and Traditional Public Schools \- ERIC, [https://files.eric.ed.gov/fulltext/ED664039.pdf](https://files.eric.ed.gov/fulltext/ED664039.pdf)  
14. Documentation to the NCES Common Core of Data Public Elementary/ Secondary School Universe Survey, [https://nces.ed.gov/ccd/pdf/INsc09101a.pdf](https://nces.ed.gov/ccd/pdf/INsc09101a.pdf)  
15. Extraordinary Audit \- FCMAT, [https://www.fcmat.org/PublicationsReports/OFYOFLcompletefinalreport890.pdf](https://www.fcmat.org/PublicationsReports/OFYOFLcompletefinalreport890.pdf)  
16. FUNDING GAPS 2018 \- The Education Trust, [https://edtrust.org/wp-content/uploads/2014/09/FundingGap\_TechnicalAppendix\_2018\_FINAL.pdf](https://edtrust.org/wp-content/uploads/2014/09/FundingGap_TechnicalAppendix_2018_FINAL.pdf)  
17. How has education funding changed over time? \- Urban Institute, [https://apps.urban.org/features/education-funding-trends/Appendix.pdf](https://apps.urban.org/features/education-funding-trends/Appendix.pdf)  
18. ncd-charter-schools-2018.docx \- National Council on Disability, [https://www.ncd.gov/assets/uploads/reports/2018/ncd-charter-schools-2018.docx](https://www.ncd.gov/assets/uploads/reports/2018/ncd-charter-schools-2018.docx)  
19. NCES Handbook of Survey Methods \- Common Core of Data (CCD), [https://nces.ed.gov/statprog/handbook/ccd.asp](https://nces.ed.gov/statprog/handbook/ccd.asp)  
20. School Districts \- Education Data Explorer, [https://educationdata.urban.org/documentation/school-districts.html](https://educationdata.urban.org/documentation/school-districts.html)  
21. SY\_2020-21\_Universe\_1a\_CCD\_Nonfiscal\_Release\_Notes.docx \- National Center for Education Statistics (NCES), [https://nces.ed.gov/ccd/doc/SY\_2020-21\_Universe\_1a\_CCD\_Nonfiscal\_Release\_Notes.docx](https://nces.ed.gov/ccd/doc/SY_2020-21_Universe_1a_CCD_Nonfiscal_Release_Notes.docx)  
22. Directory Records for the EDFacts Data Set for School Years 2019-20, 2020-21, and 2021-22 \- Regulations.gov, [https://downloads.regulations.gov/ED-2018-ICCD-0117-0004/attachment\_3.pdf](https://downloads.regulations.gov/ED-2018-ICCD-0117-0004/attachment_3.pdf)  
23. CCD School and District Glossary \- National Center for Education Statistics (NCES), [https://nces.ed.gov/ccd/commonfiles/glossary.asp](https://nces.ed.gov/ccd/commonfiles/glossary.asp)  
24. API documentation \- Education Data Explorer \- Urban Institute, [https://educationdata.urban.org/documentation/](https://educationdata.urban.org/documentation/)  
25. Every Kid Counts in the District of Columbia: 14th Annual Fact Book 2007 \- Urban Institute, [https://www.urban.org/sites/default/files/publication/31116/1001144-every-kid-counts-in-the-district-of-columbia-th-annual-fact-book-\_0.pdf](https://www.urban.org/sites/default/files/publication/31116/1001144-every-kid-counts-in-the-district-of-columbia-th-annual-fact-book-_0.pdf)  
26. How Students With Disabilities Fare in Both Charter and Regular Public Schools, [https://www.edweek.org/teaching-learning/how-students-with-disabilities-fare-in-both-charter-and-regular-public-schools/2024/10](https://www.edweek.org/teaching-learning/how-students-with-disabilities-fare-in-both-charter-and-regular-public-schools/2024/10)  
27. 2019 NCES ID REPORT \- National Alliance for Public Charter Schools, [https://publiccharters.org/wp-content/uploads/2023/01/NCES-white-paper-final-PUBLISH.pdf](https://publiccharters.org/wp-content/uploads/2023/01/NCES-white-paper-final-PUBLISH.pdf)  
28. fs197-16-0docx-19981.docx \- Department of Education, [https://www.ed.gov/media/document/fs197-16-0docx-19981.docx](https://www.ed.gov/media/document/fs197-16-0docx-19981.docx)  
29. Glossary \- Section J of Basic Facts \- Wisconsin Department of Public Instruction, [https://dpi.wi.gov/sfs/statistical/basic-facts/section-j](https://dpi.wi.gov/sfs/statistical/basic-facts/section-j)  
30. Do charter schools receive their fair share of funding? School finance equity for charter and traditional public schools, [https://epaa.asu.edu/index.php/epaa/article/download/4438/2415/21856](https://epaa.asu.edu/index.php/epaa/article/download/4438/2415/21856)  
31. Documentation to the 2015–16 Common Core of Data (CCD) Universe Files \- ERIC, [https://files.eric.ed.gov/fulltext/ED579146.pdf](https://files.eric.ed.gov/fulltext/ED579146.pdf)  
32. SCHOOL MEAL PROGRAMS Additional Data and Outreach Could Help Charter School Participation \- GAO, [https://www.gao.gov/assets/880/874853.pdf](https://www.gao.gov/assets/880/874853.pdf)  
33. Section I Full-Time Virtual Schools: Enrollment, Student characteristics, and Performance, [https://nepc.colorado.edu/sites/default/files/publications/RB%20Section%20I%20with%20blurb\_2.pdf](https://nepc.colorado.edu/sites/default/files/publications/RB%20Section%20I%20with%20blurb_2.pdf)  
34. The Educators' AI Guide 2026 Ebook | PDF | Artificial Intelligence \- Scribd, [https://www.scribd.com/document/990992661/The-Educators-AI-Guide-2026-eBook](https://www.scribd.com/document/990992661/The-Educators-AI-Guide-2026-eBook)  
35. 2012, [http://www.aurora-institute.org/wp-content/uploads/KeepingPace2012.pdf](http://www.aurora-institute.org/wp-content/uploads/KeepingPace2012.pdf)  
36. Structuring Charter School Accountability: How State Policy Shapes Authorizer Practice in California | Getting Down to Facts, [https://gettingdowntofacts.com/reports/structuring-charter-school-accountability-how-state-policy-shapes-authorizer-practice](https://gettingdowntofacts.com/reports/structuring-charter-school-accountability-how-state-policy-shapes-authorizer-practice)  
37. 2019 MODIFIED COUNT REPORT \- National Alliance for Public Charter Schools, [https://publiccharters.org/wp-content/uploads/2023/01/Modified-Count-2.pdf](https://publiccharters.org/wp-content/uploads/2023/01/Modified-Count-2.pdf)  
38. NBER WORKING PAPER SERIES THE EFFECT OF CHARTER SCHOOLS ON IDENTIFICATION, SERVICE PROVISION, AND ACHIEVEMENT OF STUDENTS WITH D, [https://www.nber.org/system/files/working\_papers/w34778/w34778.pdf](https://www.nber.org/system/files/working_papers/w34778/w34778.pdf)  
39. Charter School Effects on School Segregation | Urban Institute, [https://www.urban.org/sites/default/files/publication/100689/charter\_school\_effects\_on\_school\_segregation\_0.pdf](https://www.urban.org/sites/default/files/publication/100689/charter_school_effects_on_school_segregation_0.pdf)  
40. The Effect of Charter Schools on School Segregation \- EdWorkingPapers.com, [https://edworkingpapers.com/sites/default/files/ai20-308.pdf](https://edworkingpapers.com/sites/default/files/ai20-308.pdf)  
41. Charter School Effects on School Segregation | Urban Institute, [https://www.urban.org/research/publication/charter-school-effects-school-segregation](https://www.urban.org/research/publication/charter-school-effects-school-segregation)  
42. Digest of A Performance Audit of Elementary School Class Size \- Utah Legislature, [https://le.utah.gov/audit/09\_04rpt.pdf](https://le.utah.gov/audit/09_04rpt.pdf)  
43. Accessing the Common Core of Data (CCD) | IES \- Institute of Education Sciences, [https://ies.ed.gov/learn/blog/accessing-common-core-data-ccd](https://ies.ed.gov/learn/blog/accessing-common-core-data-ccd)  
44. Common Core of Data (CCD) \- About School District (Agency) Name and Address File, [https://nces.ed.gov/ccd/aadd.asp](https://nces.ed.gov/ccd/aadd.asp)  
45. Common Core of Data (CCD) Nonfiscal – Preliminary Version 0a Files Release Notes \- National Center for Education Statistics (NCES), [https://nces.ed.gov/sites/default/files/data-asset/ccd-common-core-data/2025/08/common-core-data-ccd-nonfiscal-preliminary-version-0a-files-release-notes/SY%202024-25%20Preliminary%20Data%20Release%20CCD%20Nonfiscal%20Release%20Notes\_0.pdf](https://nces.ed.gov/sites/default/files/data-asset/ccd-common-core-data/2025/08/common-core-data-ccd-nonfiscal-preliminary-version-0a-files-release-notes/SY%202024-25%20Preliminary%20Data%20Release%20CCD%20Nonfiscal%20Release%20Notes_0.pdf)  
46. NCES Public School Characteristics: Enrollment, Racial/Ethnic Data, Locale & Socioeconomic Status \- Placekey, [https://www.placekey.io/datasets/nces-public-school-characteristics](https://www.placekey.io/datasets/nces-public-school-characteristics)  
47. FS196 – Management Organization for Charter Schools Roster File Specifications (PDF) \- Department of Education, [https://www.ed.gov/sites/ed/files/2025-01/fs196-21-0.pdf](https://www.ed.gov/sites/ed/files/2025-01/fs196-21-0.pdf)  
48. EDFacts File Specifications SY 2025-26 | U.S. Department of Education, [https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2025-26](https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2025-26)  
49. Understanding the Opportunities and Challenges of Charter Management Contracts for Public Schools \- Center for American Progress, [https://www.americanprogress.org/article/understanding-the-opportunities-and-challenges-of-charter-management-contracts-for-public-schools/](https://www.americanprogress.org/article/understanding-the-opportunities-and-challenges-of-charter-management-contracts-for-public-schools/)  
50. Do Poor Kids Get Their Fair Share of School Funding? | Urban Institute, [https://www.urban.org/sites/default/files/publication/90586/school\_funding\_brief\_1.pdf](https://www.urban.org/sites/default/files/publication/90586/school_funding_brief_1.pdf)  
51. Building the School Attendance Boundary Information System (SABINS): Collecting, Processing, and Modeling K to 12 Educational Geography \- PMC, [https://pmc.ncbi.nlm.nih.gov/articles/PMC5693243/](https://pmc.ncbi.nlm.nih.gov/articles/PMC5693243/)  
52. Mapping the Profit Motive: A Comparative Analysis of For-Profit and Non-Profit Charter Schools, [https://epaa.asu.edu/index.php/epaa/article/view/1864](https://epaa.asu.edu/index.php/epaa/article/view/1864)  
53. The Condition of Urban School Finance: Efficient Resource Allocation in Urban Schools \- National Center for Education Statistics (NCES), [https://nces.ed.gov/pubs98/finance/98217-4.asp](https://nces.ed.gov/pubs98/finance/98217-4.asp)  
54. Resource Allocation in Charter and Traditional Public Schools \- ERIC, [https://files.eric.ed.gov/fulltext/ED537126.pdf](https://files.eric.ed.gov/fulltext/ED537126.pdf)  
55. EDFacts File Specifications SY 2024-25 | U.S. Department of Education, [https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2024-25](https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2024-25)  
56. EDFacts File Specifications SY 2022-23 | U.S. Department of Education, [https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2022-23](https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2022-23)  
57. Class Size Reduction Research | Class Size Matters Class Size Reduction Research | A clearinghouse for information on class size & the proven benefits of smaller classes, [https://classsizematters.org/research-and-links/](https://classsizematters.org/research-and-links/)