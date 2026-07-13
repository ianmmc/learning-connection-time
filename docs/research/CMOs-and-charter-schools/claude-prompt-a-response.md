# Attributing Charter-School Bell Schedules to the Correct Governing LEA in NCES CCD: A Schema and Data-Pipeline Guide

## TL;DR
- CCD reliably distinguishes charter organizational structures using three fields together: **LEA_TYPE** (code 7 = "all associated schools are charter schools"), the derived LEA charter flag **AGCHRT** (1=all/2=some/3=none), and the school-level **CHARTER_TEXT/CHARTR** flag — combined with a count of an LEA's schools (via **OPERATIONAL_SCHOOLS** or by counting ccd_sch rows per LEAID). Single-school charter LEA = LEA_TYPE 7 with one school; multi-school charter LEA = LEA_TYPE 7 with many schools under one LEAID; dependent charter = CHARTER_TEXT="Yes" at the school while its LEAID belongs to a LEA_TYPE 1 traditional district.
- **CCD contains NO charter management organization (CMO) or education management organization (EMO) identifier.** There is no parent-network, board, or management-company field in either ccd_lea or ccd_sch. Sibling LEAs of the same CMO (e.g., separate Ascend campuses) cannot be linked from CCD alone — you must join to an external source (National Alliance for Public Charter Schools database, IRS Form 990/EIN, or state authorizer files).
- For production pipelines, attribute each physical school to its ccd_sch row, take the governing LEA as the first seven digits of NCESSCH (the LEAID), and treat CMO/network grouping as a *separate* enrichment layer built from non-CCD data. Expect agency-type miscoding, LEAID churn when charters change authorizers, and definitional breaks across file vintages.

## Key Findings

### 1. The three structures ARE separable in CCD — but require combining LEA-level and school-level fields

**Agency type — `LEA_TYPE` / `LEA_TYPE_TEXT` (ccd_lea).** NCES documentation defines the LEA typology by governance, with eight values. The relevant one is **7 = "agencies for which all associated schools are charter schools."** Verbatim from NCES: "In the CCD model, every school is associated with an LEA. Charter schools authorized by entities other than a LEA often serve as their own LEA for CCD reporting purposes." Codes 1–8 are: 1 = regular district not in a supervisory union; 2 = regular district that is a component of a supervisory union; 3 = supervisory union administrative center; 4 = regional education service agency; 5 = state-operated; 6 = federally operated (mostly DoDEA); 7 = independent charter agency; 8 = other.

**Critical vintage note:** Before SY 2007–08, TYPE 7 meant "other education agencies" (which happened to include charters). Starting SY 2007–08, TYPE 7 was redefined to mean charter agencies *only*, and TYPE 8 was created for "other." Any pipeline spanning pre-2008 vintages must handle this redefinition.

**LEA charter flag — `AGCHRT` (ccd_lea, derived).** NCES derives AGCHRT from the counts of charter vs. traditional schools on the school file: **AGCHRT=1** (all constituent schools are charter), **AGCHRT=2** (some are charter), **AGCHRT=3** (none are charter). This is the field that surfaces the "dependent charter" case: an LEA with AGCHRT=2 is a traditional or mixed district that operates at least one charter school alongside non-charter schools.

**School charter flag — `CHARTER_TEXT` / `CHARTR` (ccd_sch).** Each school row carries a charter Yes/No indicator. NCES's own FY23 (SY 2022–23) documentation confirms the operative modern name: "the AGCHRT code is derived from the CHARTER_TEXT charter school indicator variable in the CCD School Universe file." The coded companion is CHARTR; missing/NA use "M"/"N".

**School count per LEA — `OPERATIONAL_SCHOOLS` (ccd_lea, derived); or count ccd_sch rows by LEAID.** The number of operating schools tied to an LEA is available as a derived LEA-level count, and can always be reconstructed by counting ccd_sch rows sharing a LEAID (operational status = open).

**Decision logic to classify a given school:**

| Structure | Rule (using ccd_lea + ccd_sch) |
|---|---|
| (a) Single-school charter LEA | School's LEAID has **LEA_TYPE=7** AND that LEAID has exactly **1** operating school (OPERATIONAL_SCHOOLS=1 / one ccd_sch row). |
| (b) Multi-school charter LEA | School's LEAID has **LEA_TYPE=7** AND that LEAID has **>1** operating schools (OPERATIONAL_SCHOOLS>1 / multiple ccd_sch rows). AGCHRT will be 1. |
| (c) Dependent charter under a traditional district | School row has **CHARTER_TEXT="Yes"** BUT its LEAID has **LEA_TYPE=1** (or 2) and **AGCHRT=2** (district has some charter, some non-charter schools). The charter's LEAID equals the district's LEAID. |

The governing LEA for any physical school is always the first seven digits of its 12-digit NCESSCH (= LEAID). This is the single most reliable attribution key in CCD.

### 2. There is NO CMO/EMO/parent-network identifier anywhere in CCD

This is the hard limit for the sibling-LEA problem. The CCD school and LEA universe files do **not** contain any field naming a charter management organization, education management organization, parent network, board, or management company. The published attributes are limited to IDs, address, type, operational status, grade span, charter status, and (at school level) a charter authorizer concept in the EDFacts source spec (CHARTAUTH). NCES's release notes enumerate the "limited attributes" as "type, operational status, the lowest and highest grades offered, and whether a school is a charter school" — no management-organization field.

Consequently, "Ascend Charter School – Bushwick" LEA and "Ascend Charter School – Brownsville" LEA appear in CCD as two legally separate LEAIDs with **nothing in the federal record tying them to the common Ascend CMO parent.** They can only be matched by name-string heuristics (shared prefix) or by joining to an external CMO registry.

Where CMO/EMO concepts DO live:
- **CEDS (Common Education Data Standards)** defines "Charter School Management Organization Type" (Element 001650, National Center for Education Statistics, ceds.ed.gov/element/001650), which defines a CMO as "A separate legal entity that 1) contracts with one or more charter schools to manage, operate, and oversee the charter schools; or 2) holds a charter, or charters, to operate multiple charter schools." (Note: the CEDS element detail page currently returns a server-side processing error, so cite the CEDS ontology entry directly.) CEDS is a *standard*, not a populated dataset — it is not carried into CCD.
- **National Alliance for Public Charter Schools (NAPCS) National Charter School Database / data dashboard** explicitly captures "management type" and identifies "charter school networks... and management organizations." Per NAPCS's *National Charter School Management Overview, 2016–17* (Rebecca David), as reported by ED's National Charter School Resource Center: "in 2016-17, 65 percent of charter schools were independently managed, 23 percent were part of a Charter Management Organization (CMO), and 12 percent were part of an Education Management Organization (EMO)... 180 CMOs and 54 EMOs served 43 percent of all charter school students in 2016-17." (A more recent independent estimate, from the Center for American Progress's 2023 analysis "Understanding the Opportunities and Challenges of Charter Management Contracts," puts it at "CMOs manage 29 percent of all charter schools nationwide... For-profit education management organizations (EMOs) manage 10.5 percent"; NAPCS defines a CMO as a nonprofit network serving at least 3 charter schools and at least 300 students.) NAPCS is the most direct federal-adjacent source for CMO/EMO parent linkage.
- **IRS Form 990 / EIN data** (e.g., via ProPublica Nonprofit Explorer) can group sibling nonprofit charter entities under a common parent 501(c)(3).
- State charter authorizer databases and state education agency crosswalks.

### 3. How practitioners de-duplicate and link CMO/EMO campuses across LEAIDs

There is no single federal crosswalk. The established practice is a multi-source join:

- **Urban Institute Education Data Portal** harmonizes CCD (and CRDC, EDFacts, etc.) and exposes a `charter` filter, but it inherits CCD's structure and does **not** add a CMO/network key. It is excellent for pulling standardized ccd_sch/ccd_lea records but does not solve sibling linkage.
- **NAPCS methodology** is the reference approach: NAPCS merges CCD with state education agency data and its own tracking to "accurately identify and track charter schools," including network/management affiliation. NAPCS's Jamison White authored a widely cited 2019 white paper (*2019 NCES ID Report*) documenting exactly the pathologies in question: "New campuses associated with a charter holder or charter management organization may or may not receive new IDs when they first open. Sometimes NCES generates only one ID for many schools and campuses across an entire city." The report states verbatim: "For years, NCES listed all of the more than one dozen Noble Network schools in Chicago under the same NCES ID. Recently, NCES created separate IDs for these schools, making them appear to be new entities."
- **State crosswalks.** NAPCS explicitly recommends: "For researchers interested in such an analysis, the National Alliance encourages them to seek out existing state crosswalks published by state education agencies." Many SEAs publish authorizer-and-operator tables that map each charter LEAID/state ID to its authorizer and management organization.
- **Name/domain heuristics + manual verification.** Because siblings often share a name prefix and a single public website domain, practitioners cluster by normalized name/domain, then verify against authorizer or 990 records. NAPCS's conclusion applies: "A thorough school-by-school analysis yields a more accurate picture."

### 4. Data-quality caveats a pipeline builder must handle

- **Charter status is self-reported and NOT verified by NCES.** NCES states plainly: "whether a school's charter status was reported correctly has not been reviewed." The categorical value is edited only for validity (must be 1/2/M/N), not accuracy.
- **Agency-type placement is inconsistent across states.** Whether a charter is its own LEA (LEA_TYPE=7) or a dependent school under a traditional district (structure c) is a function of *state statute and SEA reporting practice*, not a uniform national rule. EDFacts guidance: "In some states, charter schools are established as their own LEA... reported in the LEA file as an independent charter district. In other states, all charter schools are under regular public school districts."
- **LEAID churn breaks longitudinal tracking.** Because the LEAID is embedded in the 12-digit NCESSCH, any change of authorizer/LEA regenerates the school's NCES ID. Per the *2019 NCES ID Report* (White, NAPCS): "over the last fifteen years, the National Alliance for Public Charter Schools has recorded more than 500 instances of NCES IDs changing." New Orleans charters' IDs changed when oversight moved from the Recovery School District to Orleans Parish; the same report cites that "one study found that 34 Ohio schools changed authorizers over a seven-year period" (Bellwether/Fordham, *The Road to Redemption*). A school "may appear one year, and be new the next" despite no operational change.
- **One school can appear as multiple records** (grade-span splits) or multiple schools under one ID, so a one-to-one match on NCES IDs "often fails to capture all schools."
- **Definitional/vintage breaks:** the SY 2007–08 TYPE-7 redefinition; the SY 2014–15 restructuring into EDFacts-aligned modules with new short-text variables (e.g., LEA_TYPE_TEXT, CHARTER_TEXT) and geography moved to EDGE; and starting SY 2022–23, Magnet and Title I status were dropped from CCD (get them from CRDC / ED Data Express instead). Field names differ between legacy files (CHARTR, SCH, AGCHRT) and modern files (CHARTER_TEXT, OPERATIONAL_SCHOOLS, LEA_TYPE_TEXT).
- **Independent charter LEAs are excluded from some geographic/Census products.** EDGE school-district boundary files and the Census F-33 universe exclude independent charter districts, so do not expect charter LEAs to appear in boundary/geography joins.

## Details

**Exact field inventory (recent ccd_lea / ccd_sch, EDFacts-era):**
- ccd_lea: `LEAID` (7-digit), `LEA_TYPE` + `LEA_TYPE_TEXT` (codes 1–8; 7=charter), `AGCHRT` (1/2/3 charter flag, derived from school file), `OPERATIONAL_SCHOOLS` (count of operating schools), `ST_LEAID` (state LEA ID), `UNION` (supervisory union ID), `GSLO`/`GSHI` (grade span).
- ccd_sch: `NCESSCH` (12-digit = LEAID+SCHID), `LEAID`, `SCHID`, `SCH_TYPE`/`SCH_TYPE_TEXT` (1=regular…5=reportable program), `CHARTR`/`CHARTER_TEXT` (charter flag), `CHARTAUTH` (charter authorizer, from EDFacts source spec), `LEA_NAME`, `SCH_NAME`, `SY_STATUS` (operational status).

**Why the LEAID-from-NCESSCH rule is safe for bell-schedule attribution.** Every ccd_sch record is by construction tied to exactly one LEA (its LEAID prefix). Whether that LEA is a single-school charter (a), a multi-school charter (b), or a traditional district hosting a dependent charter (c), the *governing* LEA is unambiguous at a point in time. The structural ambiguity your system faces is not "which LEA governs this school" (that is deterministic) but "which schools are siblings under a common operator" (that is NOT in CCD).

## Recommendations

**Stage 1 — Deterministic LEA attribution (build now).** For each physical school, resolve to its ccd_sch row (match on state school ID or NCESSCH), then set governing LEA = first 7 digits of NCESSCH. Join ccd_lea on LEAID to pull LEA_TYPE and AGCHRT. Classify structure with the decision table in Key Finding 1. This fully answers "attribute each bell schedule to the correct governing LEA."

**Stage 2 — Structure tagging.** Add a derived column per school: `charter_structure ∈ {single_school_charter_lea, multi_school_charter_lea, dependent_charter, non_charter}` using LEA_TYPE, AGCHRT, CHARTER_TEXT, and the count of ccd_sch rows per LEAID. Recompute the per-LEA school count from ccd_sch rather than trusting a single vintage's OPERATIONAL_SCHOOLS.

**Stage 3 — CMO/network enrichment (separate layer, do NOT expect from CCD).** Build a `cmo_id` crosswalk from external sources, in priority order: (1) NAPCS National Charter School Database (management type + network); (2) state authorizer/operator tables; (3) IRS 990/EIN clustering via ProPublica; (4) name-prefix + website-domain heuristics with manual verification. Key this crosswalk on LEAID (and state ID for robustness) so it survives independently of CCD.

**Stage 4 — Longitudinal hardening.** Store the CCD file-year vintage with every record. Maintain a LEAID/NCESSCH history table to absorb ID churn; do not treat an ID disappearance as a closure without cross-checking name/address continuity (per NAPCS guidance). Pin field-name mappings per vintage (CHARTR↔CHARTER_TEXT, SCH↔OPERATIONAL_SCHOOLS).

**Thresholds that change the approach:** If your coverage is a single state, prefer that SEA's authorizer file over NAPCS for CMO linkage (higher fidelity). If you must operate purely on federal open data with no license, accept that CMO sibling-linkage will be heuristic (name/domain) and flag those clusters as "unverified." If longitudinal trend analysis is required, invest in the ID-history table before anything else — it is the single biggest source of silent error.

## Caveats
- Exact text-label strings for CHARTER_TEXT, LEA_TYPE_TEXT, and the precise definition/name of OPERATIONAL_SCHOOLS should be confirmed against the specific per-year Excel "companion files" published with each release at nces.ed.gov/ccd/ccddata.asp, since NCES holds per-year value labels and frequencies there. AGCHRT and LEA_TYPE codes are confirmed in primary NCES documentation (NCES 2016-077, *Documentation to the 2014–15 CCD Universe Files*).
- Whether the current published LEA file uses a literal `CHARTER_LEA` variable versus the historical `AGCHRT` was not fully confirmable from published PDFs; AGCHRT is documented and LEA_TYPE=7 is the reliable charter-agency identifier. A charter-authorizer *name* field and any CMO/EMO field are confirmed absent from published CCD.
- Charter status and agency-type coding are state-reported and vary by state law; treat cross-state comparisons of "structure" as approximate, not exact.
- Management-share figures differ by source and definition: NAPCS's 2016–17 overview (23% CMO / 12% EMO) versus the Center for American Progress's 2023 figure (29% CMO / 10.5% EMO). These reflect different years and definitions of CMO/EMO; verify the vintage and definition for any published use.