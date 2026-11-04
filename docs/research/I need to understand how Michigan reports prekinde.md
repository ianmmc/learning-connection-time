<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# I need to understand how Michigan reports prekindergarten (Pre-K) students and Pre-K teachers to the

U.S. Department of Education (EDFacts), which the NCES Common Core of Data (CCD) then publishes, for
school years 2023-24 and 2024-25. Please cite primary sources (NCES/EDFacts documentation, Michigan
CEPI / MDE / MiLEAP manuals) wherever possible.

Observed facts from the CCD files:

1. The CCD LEA (district) membership file (ccd_lea_052) reports ~53,882 Pre-K students for Michigan
in 2024-25 (48,993 in 2023-24) across ~305 districts, with data flag "Reported".
2. The CCD SCHOOL membership file (ccd_sch_052) reports ZERO Pre-K students for every Michigan school.
About 1,110 Pre-K cells per year carry the data flag "Manual adjustment" with a value of 0, and
even Michigan's 11 schools classified as "Prekindergarten" level report 0 Pre-K students.
No other state shows this; the next-lowest state reports ~70% of its district Pre-K count at
the school level.
3. The CCD LEA staff file (ccd_lea_059) reports ~2,980 Pre-K teacher FTE and ~5,137 Kindergarten
teacher FTE for Michigan in 2024-25, both flagged "Reported".
4. Michigan's school-level teacher FTE (ccd_sch_059) sums to roughly the district teacher total
MINUS Pre-K teachers in aggregate, but district by district the match is inconsistent.

Questions:
A. Why does Michigan report Pre-K membership at the district level but not at the school (building)
level? In particular, is Pre-K enrollment for the Great Start Readiness Program (GSRP), Head Start,
Strong Beginnings or special-education preschool collected in the MSDS Early Childhood
Collection rather than the building-level General Collection (Fall count), and is it reported
without an operating building/school code?
B. Are GSRP classrooms commonly operated by intermediate school districts (ISDs) or
community-based organizations rather than in a local district's school buildings, and how
does that affect which LEA and which school the students and teachers are attributed to in EDFacts?
C. What does the CCD/EDFacts data flag "Manual adjustment" (DMS_FLAG) mean, and is there an NCES or
EDFacts data note explaining Michigan's school-level Pre-K values?
D. For EDFacts file FS059 (staff FTE), how does Michigan derive school-level teacher FTE from the
Registry of Educational Personnel (REP)? Are Pre-K teachers (GSRP lead teachers, preschool special
education teachers) included in a school's teacher FTE, assigned to a building, or reported only at
the district or ISD level?
E. Do Michigan's Pre-K teachers primarily teach Pre-K classes only, or are Pre-K and kindergarten
commonly taught by the same teachers (blended Pre-K/K or "young fives" / transitional
kindergarten classrooms)? How is transitional kindergarten counted: as Pre-K or as Kindergarten?
F. Is this a long-standing pattern (earlier years such as 2018-19), or new in recent years?

Please distinguish clearly between what primary documentation states and what is inferred.

**Michigan’s district-versus-school Pre-K discrepancy is explicitly documented by NCES—not merely inferred from the files.** For both 2023–24 and 2024–25, Michigan’s CCD membership metadata states that Pre-K membership is reported at the LEA and SEA levels, but not at the building level; however, the documentation does **not** support the stronger explanation that Michigan collects no building identifiers for preschool children.[^1_1][^1_2]

The staffing discrepancy also has a documented explanation, but **“school teachers = district teachers minus Pre-K teachers” is not an established reporting rule**: Michigan identifies several additional reasons school and LEA teacher FTE do not reconcile.[^1_2]

## The decisive NCES documentation

The most useful primary sources are the workbooks accompanying the CCD releases:

- [2023–24 final data notes](https://nces.ed.gov/ccd/xls/SY_2023-24_Final_1a_Data_Notes.xlsx), particularly **CCD Membership Metadata** and **Data Notes**.
- [2024–25 final data notes](https://nces.ed.gov/ccd/xls/SY_2024-25_CCD_Final_2a_Data_Notes.xlsx), particularly **CCD Membership Metadata** and **Data Notes**.
- [2018–19 data notes](https://nces.ed.gov/ccd/xls/SY1819_Membership_Staff_SpecialPopulations_DataNotes.xlsx), particularly **State Notes**.

These are companion documentation available through the [NCES CCD data-file catalog](https://nces.ed.gov/ccd/ccddata.asp).[^1_2]

In **both recent-year workbooks**, Michigan’s row in *CCD Membership Metadata* says:

> “Membership counts for pre-K are reported for the LEA and SEA levels, they are not reported at the building level.”[^1_2]

The same rows describe Michigan’s Pre-K population as:

> “Michigan includes special education students who are served in a classroom setting, students enrolled in Michigan’s state-funded Great Start Readiness Program, and students in Head Start, Early Head Start and Title I Preschool programs if they are reported to the state.”[^1_2]

Thus, the LEA Pre-K count is **not simply a GSRP enrollment count**, and it should not be interpreted as a complete count of every preschool child or every child receiving early childhood special-education services. The metadata specifically identifies classroom-served special-education students and makes inclusion of several other programs contingent on their being reported to the state.[^1_2]

## A. Student collection and buildings

### Separate collection, but not universally

**Documented:** CEPI says that the Fall Early Childhood Collection is combined with other MSDS data to produce fall preschool headcounts, and that Early Childhood Collection data are reported to the U.S. Department of Education. It identifies GSRP and GSRP/Head Start Blend among the programs required to report through that collection.[^1_3]

But it would be incorrect to conclude that **all preschool-related records—including special education—exist exclusively in the Early Childhood Collection**. Michigan’s General Collection supports the Early Childhood grade/setting code **30**, while its district-user documentation distinguishes the program-oriented Early Childhood Collection from the General Collection.[^1_4][^1_5]


| Population | What the documentation establishes |
| :-- | :-- |
| GSRP | Reported through the MSDS Early Childhood Collection; ISDs are responsible for ensuring reporting. [^1_3] |
| GSRP/Head Start Blend | A required Early Childhood Collection program. [^1_3] |
| Standalone Head Start/Early Head Start | Can be reported in Early Childhood collections; Michigan’s CCD metadata includes them if reported to the state, rather than establishing comprehensive coverage. [^1_4][^1_2] |
| Strong Beginnings | CEPI announced that participating districts would begin reporting the program in the **EOP 2024 Early Childhood Collection**. That does not establish inclusion in the preceding fall 2023 CCD snapshot. [^1_6] |
| Preschool special education | Should not be treated as exclusively an Early Childhood Collection population: MSDS supports early-childhood grade/setting records in its broader student reporting system, and the CCD metadata specifically includes classroom-served special-education children. [^1_5][^1_2] |

**Important limitation:** The sources reviewed do not provide Michigan’s complete year-specific extraction logic showing precisely which General and Early Childhood records, program dates, ages, educational settings, and deduplication rules produced your 48,993 and 53,882 totals.

### Building identifiers can exist

**Documented, but in a later manual:** The **2025–26 MSDS Collection Details Manual**, pages 62–63, contains a `SchoolFacilityNumber` characteristic in the Early Childhood Programs component. It requires the building’s five-digit EEM code when the reported program or service is provided by a public school district in a school building.[^1_1]

That manual also allows the characteristic to be blank when another business rule does not require it. Consequently, the collection accommodates both building-linked and non-building-linked services; it is not inherently a building-code-free collection.[^1_1]

**Inference:** Michigan’s federal school-level omission is better characterized as a **reporting/export limitation or convention** than as proof that Michigan has no information about preschool service locations. The later manual demonstrates the distinction between possessing some building identifiers and publishing a comprehensive school-level CCD Pre-K membership series; it does not establish the exact 2023–24 or 2024–25 implementation.[^1_1][^1_2]

**Unresolved:** The public sources establish *that* Michigan omits school-level Pre-K membership, but not the complete administrative or technical rationale for continuing that practice.

## B. ISDs and community providers

### A mixed-delivery system

**Yes—GSRP is not simply a program operated inside local-district elementary schools.** MiLEAP’s FY25 implementation documentation identifies ISDs as GSRP grantees, and its ISD-administration guidance states that legislation requires each ISD to distribute at least 30% of its allocation to community-based organizations.[^1_7][^1_8]

That is an **allocation requirement**, not evidence that 30% of children or classrooms are community-based. It nevertheless establishes that community provision is a substantial, deliberately built-in feature of the program.[^1_7]

CEPI separately states that ISDs are GSRP fiscal agents and are responsible for ensuring that program data are reported in MSDS. Fiscal responsibility therefore should not be confused with directly operating every classroom.[^1_3]

### Attribution is not automatic

Four distinct relationships must be kept separate:


| Relationship | Why it matters |
| :-- | :-- |
| Fiscal agent/grantee | An ISD can receive and administer GSRP funding without operating the child’s classroom. [^1_8][^1_3] |
| Actual provider/location | Services can be delivered through a community organization rather than a conventional public school. [^1_7][^1_9] |
| Student’s residence | MI School Data’s Early Childhood Participation report explicitly uses district of residence—not location of enrollment—for its district-based reporting. That is a separate product and should not be assumed to reproduce CCD attribution. [^1_10] |
| Staff reporting relationship | Michigan’s CCD notes identify staffing relationships that do not conform to the directory’s one-school/one-LEA structure. [^1_2] |

**What cannot safely be inferred:** A CBO child is not necessarily assigned in CCD to the local district containing the CBO, and an ISD’s fiscal-agent status does not establish that every GSRP child or teacher is counted under that ISD’s CCD LEA ID.

The documentation reviewed does not expose Michigan’s complete crosswalk from **submitting entity, fiscal entity, provider, residence, and EEM entity** to the LEA identifier in FS052. That is a genuine remaining gap—not something the mixed-delivery structure alone resolves.

### Reportable programs matter

Federal FS052 excludes entities classified as **reportable programs** from school-level membership reporting, and FS059 likewise excludes them from school-level teacher reporting.[^1_11][^1_12]

This is directly relevant to Michigan: the **2024–25 Data Notes**, rule **DGO-0033**, contain a Michigan explanation covering 12 entities that identifies them as buildings serving Pre-K students and confirms their classification as reportable programs.[^1_2]

**Inference:** Reportable-program classification explains why **some identifiable preschool buildings** do not produce ordinary school-level membership and teacher records. It does **not**, by itself, explain every zero Pre-K cell in otherwise regular Michigan schools; the statewide membership metadata supplies the broader explanation.[^1_12][^1_11][^1_2]

## C. “Manual adjustment” and zeros

**Treat these zeros as a reporting limitation, not as evidence of no preschool children at the schools.** The controlling evidence is Michigan’s explicit metadata statement that school-level Pre-K membership is not reported.[^1_2]

The defensible interpretation of the label **“Manual adjustment”** is that the published value has been changed during CCD processing rather than retained as an unaltered “Reported” value. However, I did **not** verify a formal flag-definition passage or a Michigan-specific edit instruction establishing the exact original value and transformation applied to those cells.

Three distinctions are important:

- **Documented:** Michigan does not report Pre-K membership at the school/building level in either requested year.[^1_2]
- **Your observed file result:** The affected published cells contain zero and carry “Manual adjustment.”
- **Inference, not verified edit history:** Those adjusted zeros operationalize the school-level reporting gap; the evidence reviewed does not establish whether every cell was originally missing, absent, or otherwise coded.

The workbooks’ **Post-submission data revisions** sheets did not contain a Michigan-specific explanation of this Pre-K conversion. The Michigan-specific explanation is instead in **CCD Membership Metadata**, which is easy to miss if one reads only release notes or error-resolution notes.[^1_2]

**Analytical recommendation:** Preserve the original values and flags, but create a separate analysis variable identifying Michigan school-level Pre-K membership as **not reported at this level**. Do not use the adjusted zeros to conclude that a school lacks a preschool program or to calculate meaningful school-level Pre-K participation rates.

## D. REP and teacher FTE

### What federal reporting expects

FS059 contains **two different data groups**: **DG528**, staff FTE by category at SEA and LEA levels, and **DG644**, total classroom-teacher FTE at the school level. The school file is not a school-by-school reproduction of all the LEA staff categories.[^1_11]

The federal guidance explicitly says that the teacher categories reported at SEA/LEA level—including **Pre-K teachers**—should also be represented in school teacher totals, subject to the applicable entity exclusions. There is therefore **no general EDFacts rule excluding Pre-K teachers from school FTE**.[^1_11]

The accessible specification is for **2025–26**, but its change section states that there were no substantive changes from 2024–25; that supports using these provisions to understand the 2024–25 structure. It is not a substitute for independently verifying the 2023–24 specification.[^1_11]

### What REP establishes

CEPI’s REP documentation says that REP data support federal and state personnel reporting, including district/building staff FTE reporting. REP also collects school-assignment information, so its design is not limited to district-only staff records.[^1_13]

**But the public documentation reviewed did not reveal the complete Michigan REP-to-FS059 transformation**, including the exact assignment-code filters, school eligibility filters, treatment of multiple grade settings, and mappings into `PKTCH` versus other teacher categories.

Consequently, it is not possible to verify from these sources alone that every GSRP lead teacher or preschool special-education teacher is included in `PKTCH`, or that every such teacher’s REP school assignment survives into school-level DG644.

### Michigan explains the mismatch

The strongest evidence is Michigan’s **2023–24 Data Notes**, rule **CCD-0045**, associated with **134 LEAs** whose district teacher total differed from the sum of school totals. Michigan identifies three reasons:[^1_2]

- LEAs may report staff FTE at the LEA level instead of prorating it across several schools.[^1_2]
- Teachers in **reportable programs** are excluded from school-level reporting under federal guidance but retained at LEA and SEA levels.[^1_2]
- Shared-school staffing relationships can fail to fit the directory’s one-school/one-district structure, preventing the corresponding FTE from being submitted at school level while retaining it at LEA level.[^1_2]

A separate Michigan note, **CCD-0089**, addresses **47 schools** with membership but no positive teacher FTE. It reiterates the LEA-level reporting option and says that most of the reviewed mismatches involved virtual curriculum and teachers contracted from providers.[^1_2]

**Interpretation:** Your aggregate “district total minus Pre-K” relationship is consistent with substantial preschool staffing being associated with reportable programs or LEA-only assignments. But the documented additional mechanisms explain why that relationship need not hold district by district, and they prevent treating it as a verified subtraction rule.[^1_2]

### CBO staffing needs separate verification

MiLEAP’s FY25 guidance says that the GSRP **Staff Information Report** is completed through **MiRegistry**, with teaching-team members maintaining information on credentials, compensation, and time worked.[^1_14]

That is distinct from demonstrating inclusion in REP or EDFacts. **A teacher’s presence in the GSRP staffing system should not be assumed to establish that teacher’s inclusion in Michigan’s CCD Pre-K teacher FTE.**

## E. Pre-K, kindergarten, and TK

### Shared teachers are not established

FS059 anticipates teachers who teach both Pre-K and kindergarten and instructs states to divide their FTE proportionally between `PKTCH` and `KGTCH` based on time spent in each assignment. It also provides proportional-allocation guidance when the underlying records do not distinguish those categories.[^1_11]

That guidance does **not** demonstrate that combined Pre-K/K teaching is common in Michigan, nor do separate CCD FTE totals identify unique individuals. One teacher can contribute fractional FTE to more than one category.[^1_11]

**Unresolved:** The sources reviewed do not establish the statewide proportion of Michigan Pre-K teachers who teach only preschool versus those who also teach kindergarten.

### Young Fives is a separate issue

Michigan’s transitional/developmental kindergarten—often called **Young Fives**—should not be equated with GSRP or assumed to mean a classroom mixing preschool and traditional-kindergarten children. Michigan describes developmental kindergarten as an additional year of schooling, and University of Michigan research describes TK as funded through the traditional-kindergarten formula.[^1_15][^1_16]

The university’s research also indicates that TK generally operates separately from traditional kindergarten; curricular use of Pre-K or Pre-K/K materials does not establish a mixed-grade classroom.[^1_17][^1_18]

**Counting interpretation:** The evidence points to Michigan TK/Young Fives being treated as **kindergarten**, rather than GSRP-style Pre-K, in the state’s enrollment/funding structure. However, I did not locate a year-specific CEPI instruction or EDFacts crosswalk explicitly stating how every locally named TK/Young Fives program maps into FS052 and its teachers into FS059, so that last federal mapping remains less firmly documented than the district-versus-school membership omission.[^1_16][^1_15]

## F. The pattern predates these years

**It is long-standing—documented at least as far back as 2018–19.** The NCES 2018–19 workbook’s Michigan **Membership / FS052** note states:

> “Michigan did not report prekindergarten membership for the 1,062 schools that offer that grade,”

and records Michigan’s explanation that it did not collect Pre-K data at school level.[^1_2]

The same workbook’s Michigan **Staff / FS059** note already describes school-versus-district mismatches arising from assignment reporting, students being counted at their primary educational provider, and contracted-out teachers being reported only at district level.[^1_2]

**Qualification:** The 2018–19 statement about not collecting school-level data should be understood as the explanation recorded for that federal reporting cycle. It should not be generalized into a claim that later MSDS systems cannot capture preschool building identifiers—the later collection manual clearly can.[^1_1][^1_2]

## Remaining verification gaps

The principal conclusions are documented, but four narrower questions require an actual Michigan extraction specification or an agency explanation:


| Missing detail | What would resolve it |
| :-- | :-- |
| Exact LEA attribution | The 2023–24 and 2024–25 MSDS-to-FS052 crosswalk, including fiscal entity, submitting entity, provider, and residence |
| Exact teacher inclusion | REP assignment/grade-setting codes used for `PKTCH`, including GSRP and preschool special education, and treatment of CBO personnel |
| Exact school-FTE construction | REP-to-DG644 aggregation rules, including reportable-program exclusions and LEA-only assignments |
| Exact zero conversion | NCES’s Michigan-specific processing instruction or edit history for school Pre-K cells flagged “Manual adjustment” |

For interpreting your existing files, the key distinction is already secure: **Michigan’s school-level Pre-K zeros do not negate its reported LEA Pre-K enrollment, and its school-level teacher totals are not a fully reconcilable allocation of district teacher FTE.** Both limitations are explicitly acknowledged in the CCD’s Michigan documentation.[^1_2]

<span style="display:none">[^1_100][^1_101][^1_102][^1_103][^1_104][^1_105][^1_106][^1_107][^1_108][^1_109][^1_110][^1_111][^1_112][^1_113][^1_114][^1_115][^1_116][^1_117][^1_118][^1_119][^1_120][^1_121][^1_122][^1_123][^1_124][^1_125][^1_126][^1_127][^1_128][^1_129][^1_130][^1_131][^1_132][^1_133][^1_134][^1_135][^1_136][^1_137][^1_138][^1_139][^1_140][^1_141][^1_142][^1_143][^1_144][^1_145][^1_146][^1_147][^1_148][^1_149][^1_150][^1_151][^1_152][^1_153][^1_154][^1_155][^1_156][^1_157][^1_158][^1_159][^1_160][^1_161][^1_162][^1_163][^1_164][^1_165][^1_166][^1_167][^1_168][^1_169][^1_170][^1_171][^1_172][^1_173][^1_174][^1_175][^1_176][^1_177][^1_178][^1_179][^1_180][^1_181][^1_182][^1_183][^1_184][^1_185][^1_186][^1_187][^1_188][^1_189][^1_19][^1_190][^1_191][^1_192][^1_193][^1_194][^1_195][^1_196][^1_197][^1_198][^1_199][^1_20][^1_200][^1_201][^1_202][^1_203][^1_204][^1_205][^1_206][^1_207][^1_208][^1_209][^1_21][^1_210][^1_211][^1_212][^1_213][^1_214][^1_215][^1_216][^1_217][^1_218][^1_219][^1_22][^1_220][^1_221][^1_222][^1_223][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81][^1_82][^1_83][^1_84][^1_85][^1_86][^1_87][^1_88][^1_89][^1_90][^1_91][^1_92][^1_93][^1_94][^1_95][^1_96][^1_97][^1_98][^1_99]</span>

<div align="center">⁂</div>

[^1_1]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MSDS/Collection-Details_SY25-26.pdf?rev

[^1_2]: https://nces.ed.gov/ccd/ccddata.asp

[^1_3]: https://www.michigan.gov/cepi/pk-12/msds/early-childhood

[^1_4]: https://www.michigan.gov/-/media/Project/Websites/cepi/MSDS/District_User_Guide.pdf?rev=49d0f2e8284747a1a1e7a95ef191763b

[^1_5]: https://www.michigan.gov/-/media/Project/Websites/mde/Year/2018/03/05/MSDS_Best_Practices.pdf?rev=34daa3f8395d4bd5bf852b92656bc692

[^1_6]: https://content.govdelivery.com/accounts/MICEPI/bulletins/3893ebc

[^1_7]: https://www.michigan.gov/mileap/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/gsrp/implementation/isd_administration_of_gsrp.pdf?rev=f37720df11334d9bba0997b4b6b5d7c3\&hash=2C4A408F9AC641D9AB5D83F09BA90697

[^1_8]: https://www.michigan.gov/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/gsrp/implementation/overview.pdf?rev=cf75ddf126e94eb7b2af54ed0103b8aa

[^1_9]: https://www.michigan.gov/cepi/ec-program-not-part-of-a-school-or-district

[^1_10]: https://www.mischooldata.org/early-childhood-program-participation/

[^1_11]: https://www.ed.gov/media/document/edfacts-dg528-dg644-staff-fte-v220-fs059-22-0-112797.docx

[^1_12]: https://www.ed.gov/media/document/edpass-fs052-21-1-110090.docx

[^1_13]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/REP/REP-User-Guide.pdf?rev=fd580769199a4e79905c1565818cfb20\&hash=AA706B84919D7809AD4007DB5DFE0E1F

[^1_14]: https://www.michigan.gov/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/gsrp/implementation/implementation_manual.pdf?rev=c1a2c5f2dc6e4cd99e99ff98d1120482

[^1_15]: https://www.michigan.gov/mikidsmatter/parents/pre-k/faq-transition-to-kindergarten

[^1_16]: https://edpolicy.umich.edu/sites/epi/files/2023-01/TK_Brief_Jan_2023.pdf

[^1_17]: https://fordschool.umich.edu/news/2023/michigan-transitional-kindergarten-widely-available-supported-administrators-and-parents

[^1_18]: https://fordschool.umich.edu/news/2023/weiland-expertise-transitional-kindergarten-universal-preschool-news

[^1_19]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MSDS/Collection-Details_SY24-25v4.pdf

[^1_20]: https://www.michigan.gov/-/media/Project/Websites/cepi/MSDS/EC_FAQs.pdf

[^1_21]: https://www.michigan.gov/en/cepi/pk-12/msds/early-childhood

[^1_22]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/REP/REP-Data-Field-Descriptions-EOY-2027.pdf?rev=bf2384a4cf8c4dd29390cd96492c7309\&hash=1660F87CC85D72709349706D67781578

[^1_23]: https://www.michigan.gov/cepi/pk-12/msds/matrix/2025-26-collection-component-matrix

[^1_24]: https://www.michigan.gov/cepi/public-school-district-or-psa

[^1_25]: https://www.michigan.gov/en/cepi/pk-12/msds/early-roster

[^1_26]: https://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=394\&schoolyear=18\&format=xls\&name=ECPrograms_2024-2025BR

[^1_27]: https://nces.ed.gov/ccd/psu_rev.asp

[^1_28]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MSDS/MSDS-2025-EOY-Checklist.pdf

[^1_29]: https://nces.ed.gov/ccd/tables/202425_summary_4.asp

[^1_30]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MSDS/MSDS_reports.xlsx

[^1_31]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MSDS/2025-26-Early-Childhood-Spring-Schema-Summary.pdf

[^1_32]: https://nces.ed.gov/ccd/online_documentation.asp

[^1_33]: https://www.michigan.gov/cepi/pk-12/msds

[^1_34]: https://www.ed.gov/media/document/fs059-21-0-110182.docx

[^1_35]: https://www.ed.gov/sites/ed/files/about/inits/ed/edfacts/eden/non-xml/fs059-15-1.docx

[^1_36]: https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2025-26

[^1_37]: https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2024-25

[^1_38]: https://nces.ed.gov/programs/statereform/tab4_3-2023.asp

[^1_39]: https://nces.ed.gov/pubs2024/2024144.pdf

[^1_40]: https://nces.ed.gov/pubs2023/2023144.pdf

[^1_41]: https://nces.ed.gov/surveys/pss/privateschoolsearch/school_detail.asp?ID=A9103505

[^1_42]: https://nces.ed.gov/learn/press-release/nces-data-show-public-school-enrollment-held-steady-overall-fall-2022-fall-2023

[^1_43]: https://nces.ed.gov/ccd/tables/202324_summary_4.asp

[^1_44]: https://nces.ed.gov/programs/digest/

[^1_45]: https://nces.ed.gov/ccd/tables/xls/202324_summary_4.xlsx

[^1_46]: https://www.ed.gov/edfacts-file-specifications

[^1_47]: http://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications

[^1_48]: http://www.ed.gov/data/edfacts-initiative

[^1_49]: https://nces.ed.gov/ccd/doc/SY_2024-25_Universe_1a_CCD_Nonfiscal_Release_Notes.docx

[^1_50]: https://nces.ed.gov/use-work/dataset/2024-25-common-core-data-ccd-preliminary-directory-files

[^1_51]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/REP/REP_User_Guide.pdf

[^1_52]: https://nces.ed.gov/sites/default/files/data-asset/ccd-common-core-data/2025/08/common-core-data-ccd-nonfiscal-preliminary-version-0a-files-release-notes/SY 2024-25 Preliminary Data Release CCD Nonfiscal Release Notes_0.pdf

[^1_53]: https://ies.ed.gov/learn/news/2024-25-common-core-data-ccd-universe-data-files-now-available

[^1_54]: https://nces.ed.gov/ccd/xls/SY_2024-25_RPGM_Directory_Companion_2026-005d.xlsx

[^1_55]: https://nces.ed.gov/ccd/tables/202425_summary_1.asp

[^1_56]: https://nces.ed.gov/use-work/dataset/2024-25-common-core-data-ccd-universe-files-version-1a

[^1_57]: https://nces.ed.gov/ccd/files.asp

[^1_58]: https://nces.ed.gov/ccd/tables/202425_summary_2.asp

[^1_59]: https://nces.ed.gov/ccd/pau_rev.asp

[^1_60]: https://nces.ed.gov/programs/digest/d20/tables/dt20_203.25.asp

[^1_61]: https://nces.ed.gov/ccd/elsi/expresstables.aspx?bridge=quickFacts\&tableid=13\&level=State\&year=2018-19

[^1_62]: https://nces.ed.gov/ccd/tables/201819_summary_2.asp

[^1_63]: https://files.eric.ed.gov/fulltext/ED675146.pdf

[^1_64]: https://nces.ed.gov/ccd/elsi/tableGenerator.aspx?savedTableID=16591

[^1_65]: https://nces.ed.gov/ccd/doc/SY_2024-25_Universe_2a_CCD_Nonfiscal_Release_Notes.docx

[^1_66]: https://nces.ed.gov/programs/digest/d22/tables/xls/tabn203.40.xlsx

[^1_67]: https://nces.ed.gov/ccd/tables/xls/202425_summary_2.xlsx

[^1_68]: https://nces.ed.gov/programs/digest/d23/tables/dt23_216.70.asp

[^1_69]: https://nces.ed.gov/programs/digest/d22/tables/dt22_216.90c.asp

[^1_70]: https://nces.ed.gov/programs/digest/d23/tables/dt23_203.40.asp

[^1_71]: https://nces.ed.gov/fastfacts/display.asp?id=372\&e9bc163a_page=6\&e9bc163a_page=5

[^1_72]: https://nces.ed.gov/programs/digest-dashboard/state/michigan

[^1_73]: https://nces.ed.gov/ccd/pdf/stnfis061cgen.pdf

[^1_74]: https://nces.ed.gov/ccd/pdf/psu96gen.pdf

[^1_75]: https://educationdata.urban.org/csv/ccd/codebook_schools_ccd_directory.xls

[^1_76]: https://nces.ed.gov/ccd/xls/SY_2021-22_School_Membership_Companion.xlsx

[^1_77]: https://educationdata.urban.org/csv/ccd/codebook_districts_ccd_directory.xls

[^1_78]: https://nces.ed.gov/ccd/pdf/2015146_2013-14_State_documentation_v1a.pdf

[^1_79]: https://nces.ed.gov/ccd/districtsearch/district_detail.asp?Search=1\&Zip=48915\&Miles=5\&details=2\&ID2=2601077

[^1_80]: https://nces.ed.gov/ccd/pdf/pau97gen.pdf

[^1_81]: https://nces.ed.gov/ccd/pdf/stnfis99gen.pdf

[^1_82]: https://nces.ed.gov/ccd/xls/2017-18_SEA_Staff_Layout.xlsx

[^1_83]: https://nces.ed.gov/ccd/pdf/stNfis041egen.pdf

[^1_84]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/REP/REP-Data-Field-Descriptions-EOY-2025.pdf?rev=9ac121defec14cb988acc35c89f44724\&hash=C7D97F51488F097DE044EA08F99DEA44

[^1_85]: https://www.westmonroe.com/press-releases/life-sciences-ma-rebounds-execution-will-separate-winners

[^1_86]: https://nces.ed.gov/ccd/doc/SY_2022-23_Universe_1a_CCD_Nonfiscal_Release_Notes.docx

[^1_87]: https://reason.com/wp-content/uploads/2026/07/SY_2024-25_Universe_1a_CCD_Nonfiscal_Release_Notes.pdf

[^1_88]: https://nces.ed.gov/ccd/stnfis.asp

[^1_89]: https://www.michigan.gov/-/media/Project/Websites/cepi/REP/REP_FAQs.pdf?rev=463085157cca433fa3401930b223610e

[^1_90]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/REP/REP-User-Guide.pdf

[^1_91]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/REP/REP-Data-Field-Descriptions-Fall-2026.pdf

[^1_92]: https://cepi.state.mi.us/rep/

[^1_93]: https://www.michigan.gov/cepi/pk-12/rep

[^1_94]: https://nces.ed.gov/ccd/commonfiles/aboutdata.asp

[^1_95]: https://nces.ed.gov/ccd/edrp.asp

[^1_96]: https://www.eddatacenter.org/edfacts

[^1_97]: https://ies.ed.gov/nces-statistical-products-release-calendar

[^1_98]: https://nces.ed.gov/ccd/xls/SY1819_Directory_DataNotes.xlsx

[^1_99]: https://osse.dc.gov/sites/default/files/dc/sites/osse/service_content/attachments/SY%2023-24%20SHP%20Data_final.xlsx

[^1_100]: https://nces.ed.gov/ccd/tables/xls/202324_summary_2.xlsx

[^1_101]: https://www.mischooldata.org/recently-posted-page/

[^1_102]: https://ocrdata.ed.gov/data

[^1_103]: https://www.ed.gov/media/document/edpass-ccd-staff-fte-and-membership-metadata-user-guide-18773.pdf

[^1_104]: https://www.ed.gov/media/document/business-rules-single-inventory-2023-24-v1-04xlsx-18728.xlsx

[^1_105]: https://www.michigan.gov/mileap/early-childhood-education/early-learners-and-care/special-ed-05/early-childhood-special-education-ages-3-5

[^1_106]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MSDS/Collection-Details_SY26-27.pdf

[^1_107]: https://www.michigan.gov/mileap/early-childhood-education

[^1_108]: https://www.michigan.gov/mileap/Early-Childhood-Education/early-learners-and-care/special-ed-05/early-on-michigan

[^1_109]: https://www.ed.gov/media/document/edpass-ccd-grades-offered-metadata-user-guide-18772.pdf

[^1_110]: http://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2023-24

[^1_111]: http://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2024-25

[^1_112]: https://sfa.senate.michigan.gov/Departments/DecisionDoc/DDedu_initial.pdf

[^1_113]: https://www.michigan.gov/-/media/Project/Websites/cepi/CRDC_Communication_08-13-2019.pdf?rev=5ca69c6639db4de3bb0e48efb8f48847

[^1_114]: https://legislature.michigan.gov/documents/2023-2024/publicact/htm/2023-PA-0320.htm

[^1_115]: https://www.michigan.gov/mde/-/media/Project/Websites/mde/OFM/State-Aid/Pupil-Accounting/Manual/2025---2026-Documents/2025---2026-Pupil-Accounting-Manual.pdf

[^1_116]: https://www.legislature.mi.gov/documents/2023-2024/publicact/pdf/2023-PA-0103.pdf

[^1_117]: https://www.michigan.gov/mde/-/media/Project/Websites/mde/OES/Current-Topics/Comparability/Title_I_Part_A_Comparability_PowerPoint.pdf?rev=97a680ddf1d4463b87fe1972ffc041d3\&hash=FD455B2ADC34777C34BC9B3CC121F037

[^1_118]: https://www.michigan.gov/budget/-/media/Project/Websites/budget/Fiscal/Executive-Budget/FY27-Exec-Rec/Executive-Budget/FY27-Education-Omnibus.pdf

[^1_119]: https://www.msbo.org/wp-content/uploads/2026/02/sfa_sectionbysection_DDk12_web.pdf

[^1_120]: https://www.michigan.gov/-/media/Project/Websites/cepi/REP/REP_FAQs.pdf?rev=32fdbb1d8660404aa4af51b95b372d51

[^1_121]: https://nces.ed.gov/sites/default/files/nces/document/2026/05/2026008_FY24NPEFS_FirstLook.pdf

[^1_122]: https://www.michigan.gov/-/media/Project/Websites/corrections/assets/Folder12/05-15-09\_-\_Section_907.pdf?rev=fb8f92a5be8a4298be025e52479e9758

[^1_123]: https://www.michigan.gov/cepi/pk-12/msds/general

[^1_124]: https://nces.ed.gov/ccd/tables/xls/NPEFS_FinanceTable8_FY22_1a.xlsx

[^1_125]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MiSchoolData/ProfDev/EARLY_CHILDHOOD-QUICKSTART_GUIDE.pdf

[^1_126]: https://www.michigan.gov/CEPI

[^1_127]: https://www.michigan.gov/en/cepi/pk-12

[^1_128]: https://www.michigan.gov/mileap/press-releases/2026/07/23/more-3-year-olds-gain-access-to-free-prek-through-strong-beginnings-expansion

[^1_129]: https://www.michigan.gov/mileap/early-childhood-education/early-learners-and-care

[^1_130]: https://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=394\&schoolyear=19\&format=pdf\&name=ECPrograms_2025-2026BR

[^1_131]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/25Port74vSchool-Level-Expend-Download-Filein.csv

[^1_132]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/24-25-SID-EpiPen-Use.xlsx

[^1_133]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/PublicReporting2025WhyItMatters_Final_3525.pdf

[^1_134]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/25-School-Year-Homeless.xlsx

[^1_135]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2024-25/25-Port-74vSchool-Level-Expend-Download-File.csv

[^1_136]: https://mpaaa.org/images/downloads/Conference_Fall_2024/msds_in_depth_fall_2024.pdf

[^1_137]: https://www.michigan.gov/cepi/pk-12/msds/early-roster

[^1_138]: https://mischooldata.org/k-3-absenteeism-and-early-childhood-participation/

[^1_139]: https://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=309\&schoolyear=18\&format=xls\&name=PersonalCore_2024-2025BR

[^1_140]: https://www.mischooldata.org/early-childhood-program-participation-by-kindergarten-class/

[^1_141]: https://www.mischooldata.org/pathways-to-kindergarten/

[^1_142]: https://sites.google.com/berrienresa.org/resourcehub/home/illuminate

[^1_143]: https://www.gvsu.edu/cms4/asset/64CB422A-ED08-43F0-F795CA9DE364B6BE/final-pam-2024-2025.pdf

[^1_144]: https://www.michigan.gov/mileap/early-childhood-education/early-learners-and-care/gsrp/allocations

[^1_145]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/Reference/Data-File-Table-Layouts\_\_051426.xlsx

[^1_146]: https://www.michigan.gov/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/gsrp/implementation/implementation_manual.pdf?rev=11deb32b4e4d4aa4bb811d7dcac7a771

[^1_147]: https://www.michigan.gov/mileap/early-education-homepage/reports-data-investments

[^1_148]: https://www.michigan.gov/mileap/inside-mileap/legislative-reports

[^1_149]: https://www.michigan.gov/mileap/-/media/Project/Websites/mileap/Archives/Legislative-Reports/FY25/FY-2024_25-Legislative-CBO-Report-Memorandum-and-CBO-Report-Combined.pdf

[^1_150]: https://www.michigan.gov/mileap/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/gsrp/allocations/2024_25-GSRP-Allocations.pdf?rev=efb352b593b74133825be610006e2a9f\&hash=D98D82F41DBF220720F48043DC18345F

[^1_151]: https://www.michigan.gov/mileap/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/gsrp/allocations/2024-2025-GSRP-Final-Allocations.pdf?rev=91032bdab43c43c296da33a07e8cddd7\&hash=4F60C0D78DC7CB224C6346A7AA3DC188

[^1_152]: http://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=404\&schoolyear=20\&format=pdf\&name=ECPrograms_2026-2027BR

[^1_153]: https://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=401\&schoolyear=20\&format=xls\&name=ECPrograms_2026-2027BR

[^1_154]: https://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=338\&schoolyear=12\&format=pdf\&name=ECPrograms_2018-2019BR

[^1_155]: https://www.michigan.gov/cepi/pk-12

[^1_156]: https://www.michigan.gov/en/cepi/about/how-cepi-protects-education-data

[^1_157]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MSDS/District_User_Guide.pdf?rev=1a8e368f18d6411095022d6386b0a12b\&hash=9567D2BCCE51D0618F2FE016A3651B2F

[^1_158]: https://kb-test.infinitecampus.com/help/msds-extracts

[^1_159]: https://www.clintondaleschools.net/enroll-today/early-childhood

[^1_160]: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/EEM/EEM_Glossary.pdf

[^1_161]: https://www.melnapschools.com/schools/baby-birds-early-childhood-center/

[^1_162]: https://anchorbay-cdn.fxbrt.com/schools/macdonald-early-childhood/

[^1_163]: https://www.misd.net/mt/files/MISDmsdsdocumentation.pdf

[^1_164]: https://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=327\&schoolyear=11\&format=pdf\&name=EarlyOn_2017-2018BR

[^1_165]: https://sp-programs.powerschool-docs.com/special-programs-mi/latest/mi-compliance-at-a-glance

[^1_166]: https://anchorbay-cdn.fxbrt.com/schools/ms-north/

[^1_167]: https://youthpolicylab.umich.edu/news/2024/opinion-transitional-kindergarten-offers-lessons-michigan-early-learning-investments

[^1_168]: https://anchorbay-cdn.fxbrt.com/schools/maconce/

[^1_169]: https://anchorbay-cdn.fxbrt.com/schools/lighthouse/

[^1_170]: https://www.michigan.gov/-/media/Project/Websites/cepi/FAQs-SecurityPrivacy.pdf?rev=7efa45e0c1ed42fda8b3768447fc9025

[^1_171]: https://www.michigan.gov/-/media/Project/Websites/cepi/MSDS/District_User_Guide.pdf

[^1_172]: https://www.michigan.gov/en/cepi/pk-12/msds/general

[^1_173]: https://tea.texas.gov/educators/early-childhood-education/early-childhood-education-faqs

[^1_174]: https://mpaaa.org/images/downloads/bootcamp_summer_2024/intro_to_cepi_2024_mpaaa_bootcamp_reorganized.pdf

[^1_175]: https://cepi.state.mi.us/msdsxml/generatebrr.aspx?component=100\&schoolyear=19\&format=xls\&name=CertificationRules_2025-2026BR

[^1_176]: https://doe.louisiana.gov/docs/default-source/early-childhood/faq---early-childhood-ancillary-teaching-certificate---simplified-chinese.pdf?sfvrsn=3

[^1_177]: https://www.hcps.org/webfiles/WebFilesHandler.ashx?id=5826

[^1_178]: https://www.edenpr.org/early-childhood/faq/~board/early-childhood-faqs/post/what-are-the-immunization-requirements-for-ecfe-classes

[^1_179]: https://doe.louisiana.gov/docs/default-source/early-childhood/faq---early-childhood-ancillary-teaching-certificate---spanish.pdf?sfvrsn=3

[^1_180]: https://doe.louisiana.gov/docs/default-source/early-childhood/faq---early-childhood-ancillary-teaching-certificate---french.pdf?sfvrsn=3

[^1_181]: https://exceptionallives.org/category/early-childhood/

[^1_182]: https://auctions.griffinsauctions.co.uk/en/search

[^1_183]: https://www.hbug.k12.il.us/ISBEManuals/Data_Collection_and_Approval_Instructions_SY24_25.FINAL.pdf

[^1_184]: https://www.michigan.gov/mileap/early-childhood-education/early-learners-and-care/cdc/providers/faqs

[^1_185]: https://www.michigan.gov/en/mileap/Early-Childhood-Education/early-learners-and-care/cdc/providers

[^1_186]: https://www.michigan.gov/mileap/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/Child-Development-and-Care/Spring-2022-Grant-App-Materials/Frequently-Asked-Questions-Spring-2022.pdf?rev=0374aaa22e7949309a8824ccbe76405c\&hash=1C75E7E8C5F0FF8FC393796FD4791BEA

[^1_187]: https://www.michigan.gov/mileap/early-childhood-education/early-learners-and-care/cdc/parents

[^1_188]: https://www.michigan.gov/mileap/-/media/Project/Websites/mileap/Documents/Early-Childhood-Education/gsrp/implementation/gsrp_Program_Administration_Staffing.pdf?rev=b3ac810a2b0644a981f7f5ff980a610e\&hash=AD3CEC1CF68DF6209A1252B147102463

[^1_189]: https://www.michigan.gov/mileap/early-childhood-education/prek-for-all/faq

[^1_190]: https://www.michigan.gov/mileap/early-childhood-education/mi-tri-share-child-care/faq

[^1_191]: https://www.michigan.gov/mileap/early-childhood-education/early-learners-and-care/special-ed-05/early-on-michigan

[^1_192]: https://nces.ed.gov/programs/digest/d16/tables/xls/tabn203.40.xls

[^1_193]: https://nces.ed.gov/ccd/pdf/2026003.pdf

[^1_194]: https://nces.ed.gov/programs/digest/d13/tables/xls/tabn203.45.xls

[^1_195]: https://nces.ed.gov/programs/digest/d18/tables/xls/tabn203.40.xls

[^1_196]: https://nces.ed.gov/ccd/tables/2010313_04.asp

[^1_197]: https://nces.ed.gov/programs/digest/d19/tables/xls/tabn219.50.xls

[^1_198]: https://nces.ed.gov/programs/digest/d17/tables/xls/tabn203.40.xls

[^1_199]: https://nces.ed.gov/ccd/tables/xls/202021_summary_2.xlsx

[^1_200]: https://nces.ed.gov/ccd/tables/xls/202425_summary_3.xlsx

[^1_201]: https://nces.ed.gov/programs/digest/d23/tables/xls/tabn203.70.xlsx

[^1_202]: https://nces.ed.gov/programs/digest-dashboard/iframe/digest?code=digest1\&state=Michigan\&figureNumber=1

[^1_203]: https://www.ed.gov/media/document/edfacts-dg39-membership-v220-fs052-22-0-112795.docx

[^1_204]: https://www.ed.gov/media/document/2024-25-edfacts-workbook-faqs-110073.pdf

[^1_205]: https://kb.infinitecampus.com/help/early-childhood-program-michigan

[^1_206]: https://www.mischooldata.org/support-page

[^1_207]: https://academic.oup.com/chidev/article/97/4/1348/8666949

[^1_208]: https://edworkingpapers.com/sites/default/files/ai24-921.pdf

[^1_209]: https://edpolicy.umich.edu/sites/epi/files/2023-12/MI Pre-K for All Report_v8_0.pdf

[^1_210]: https://nieer.org/sites/default/files/2023-10/YB2021_Full_Report.pdf

[^1_211]: https://edpolicy.umich.edu/sites/epi/files/2024-11/epi-tk-policy-brief-nov-2024.pdf

[^1_212]: https://journals.sagepub.com/doi/10.3102/0013189X251318334

[^1_213]: https://www.cde.ca.gov/BE/pn/im/documents/jun24memomsd01a3.pdf

[^1_214]: https://huggingface.co/datasets/mteb/sts22-crosslingual-sts/blob/459f014f865eddf8729b5fe0e2faba716f411548/raw/train/41/1484191441.json

[^1_215]: https://www.michigan.gov/mde/-/media/Project/Websites/mileap/Documents/Education-Partnerships/OST/2023-PA-0103.pdf?rev=1f590089c4d44efbac0a18466f14b4fd\&hash=C960580D80F18F4DB50B18B79546648B

[^1_216]: https://www.michigan.gov/-/media/Project/Websites/mde/Year/2021/08/30/2021-PA-0048_CB_fall_testing_and_benchmark_requirements.pdf?rev=a5f2566477574309953638bac6c14114

[^1_217]: https://www.michigan.gov/mde/-/media/Project/Websites/mde/top10/SBE-Presentation-Goal-1_December-10-2024.pdf?rev=50c05171c5cc4c38ac212c47b03c41e0\&hash=2E8E98383FE8DAF7EF5009D86FFAC06D

[^1_218]: https://www.michigan.gov/budget/-/media/Project/Websites/budget/Fiscal/Final-Signed-Budget-Bills/FY26-Education-Omnibus-SB-166-PA-15-of-2025-Includes-2025-Supplemental-Funding.pdf?rev=8546515fd88b4b469ef4f95154d99f06\&hash=81A45D0FE47F33F4E94B21D680460F70

[^1_219]: https://www.michigan.gov/-/media/Project/Websites/mde/2010/03/01/Non_Public_School_Membership_Report_SM_4325.pdf?rev=3724c8374d4848339e0bf9817cc30fae

[^1_220]: https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-388-1606

[^1_221]: https://nces.ed.gov/pubs2018/2018301/tables/table_04.asp

[^1_222]: https://nces.ed.gov/pubs2018/2018301/tables/table_02.asp

[^1_223]: https://nces.ed.gov/pubs2018/2018301/tables/table_05.asp

