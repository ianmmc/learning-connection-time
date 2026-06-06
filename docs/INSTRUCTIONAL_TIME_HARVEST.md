# Instructional-Time Harvest Map (SEA central data)

> **Strategy (decided 2026-06-06):** Build a **census** of district instructional time. **Harvest centrally-published SEA data first**, then fall back to the Crawlee+Ollama scraping pipeline only for states/districts where central data isn't obtainable.
>
> **Key insight:** Most states already collect *actual* daily instructional minutes/hours per district (or per building/grade) through their **funding/accountability data systems** (Texas PEIMS, California CBEDS/CALPADS, Ohio EMIS, NY State Aid, Colorado data pipeline, PA PIMS, etc.). That data is often **more authoritative than a scraped bell schedule** — it's the LCT numerator (daily instructional minutes) reported by the district itself for funding. So **SEA harvest is the primary acquisition method; web scraping is the fallback.**
>
> **This is a research/tracking doc, not verified ground truth.** Each row's *access* must be confirmed before relying on it. Per project Rule #6, verify before claiming.

---

## ⚠️ VERIFICATION VERDICT (2026-06-06) — harvest-first does NOT deliver daily minutes

After rigorous verification of the strongest candidates, **the harvest-first hypothesis failed.** The leads in the matrix below were mostly **collection specifications** (what districts submit *to* the state), not **published datasets**. FOIA / adhoc-request channels are out of scope (user decision).

Verified findings:
- **Colorado** — brand-new collection (HB24-1063, first standardized 2025-26); page offers only blank **submission templates** (XLSX), no published per-district values. ❌
- **Illinois** — Report Card publishes only **"Total School Days"** (count of days with ≥5 hrs instruction), **not** daily length or minutes. ❌
- **Ohio** — "Hours Per Day" exists only in the **EMIS submission manual**; no public queryable/downloadable dataset of collected values. ❌
- **Texas** — PEIMS Standard Reports / TAPR public downloads carry demographics/finance/staff, **not** instructional minutes; minutes only via adhoc request (excluded). ❌
- **Oregon** (3rd-party Stand for Children) — lookup tool returned 403; no confirmed bulk download. ⚠️

**Root cause:** LCT needs **daily instructional minutes**. States *collect* this for funding compliance but *publish* only **statutory minimums or day-counts** — which we already have as the `statutory_fallback`. Daily minutes is exactly the value districts post as bell schedules and keep internal at the SEA.

**Conclusion:** Central SEA harvest does not beat the statutory fallback for the core input. **Web-scraping district sites (the Crawlee pipeline) remains the necessary primary method** for actual daily minutes. The durable win from this research is on the *extraction* side, not acquisition: cheap cloud LLM extraction (Gemini 2.5 Flash-Lite / GPT-4o-mini batch, ~$30–170 for all ~20K districts) replaces the local-Ollama quality risk — see Research notes. The matrix below is retained as a record of what was checked; treat all "LEAD" rows as **not viable** unless re-verified as a genuine public dataset.

---

## What we need (per district, ideally per grade band)

- **Daily instructional minutes** (the LCT numerator) — elementary / middle / high where available.
- Bonus: lunch/passing-period deductions, start/end times, days/year.
- Grain priority: district → building/grade → calendar-type. Any is usable; finer is better.

## Fallback that's already universal

Every state's **statutory minimum** instructional time is centrally documented and already in our pipeline as the `statutory_fallback`:
- [ECS 50-State Comparison: Instructional Time Policies (2023)](https://www.ecs.org/50-state-comparison-instructional-time-policies-2023/)
- [NCES state-reform tables — min instructional days/hours, hours per day, by state](https://nces.ed.gov/programs/statereform/tab1_1-2020.asp)

Statutory ≠ actual, so these remain the fallback, not the goal.

---

## State harvest matrix

Legend — **Access:** `DOWNLOAD` (public bulk file) · `API` · `FOIA` (public-records request) · `PORTAL` (interactive, may be scrapable) · `NONE/UNK`. **Status:** `LEAD` (data element confirmed to exist, access unverified) · `CONFIRMED` (access verified) · `HARVESTED` · `SCRAPE` (route to Crawlee) · `TODO`.

| State | ~Districts | SEA system | Element found | Grain | Access | Status | Notes / source |
|-------|-----------:|-----------|---------------|-------|--------|--------|----------------|
| OH | ~610 | EMIS — *Grade Schedule (DL)* record | **Hours Per Day** in session + first/last day | building/grade | DOWNLOAD/FOIA? | **LEAD (strong)** | Exactly the LCT numerator. [EMIS Manual §5.2](https://education.ohio.gov/getattachment/Topics/Data/EMIS/EMIS-Documentation/Current-EMIS-Manual/5-2-Grade-Schedule-DL-v6-0.pdf.aspx) |
| TX | ~1,200 | PEIMS / TSDS | **Instructional minutes** + operational minutes per calendar | campus/calendar | FOIA/PORTAL? | **LEAD (strong)** | Reported for funding. [TEDS School Calendar Domain](https://www.texasstudentdatasystem.org/sites/texasstudentdatasystem.org/files/TEDS_Data_Submission_Requirements_School_Calendar_Domain.pdf) |
| CO | ~180 | CDE Data Pipeline — Instructional Days & Hours | Days, **hours, lunch, passing time** | district, elem/sec | DOWNLOAD | **LEAD (strong)** | HB24-1063, 2025-26. [CDE Instr. Days & Hours](https://cde.state.co.us/datapipeline/per_inst-hours-days) |
| CA | ~1,000+ | CBEDS (School Information Form) / CALPADS | Educational calendars; CA instructional-minutes regime | school/district | DOWNLOAD? | **LEAD** | [CDE Downloadable Data](https://www.cde.ca.gov/ds/ad/downloadabledata.asp); verify minutes vs calendar only |
| NY | ~730 | NYSED State Aid — Model Calendars / attendance | Instructional **hours** (building level) | building | FOIA/PORTAL? | **LEAD** | Reported for state aid. [NYSED Model Calendars](https://stateaid.nysed.gov/attendance/htm_docs/Model_Calendars.html) |
| IL | ~850 | ISBE Report Card data files | Instructional setting; school-day length TBD | school/district | DOWNLOAD | **LEAD** | Bulk FTP, semicolon-delimited. [ISBE Report Card Data](https://www.isbe.net/pages/illinois-state-report-card-data.aspx) — verify hours field |
| PA | ~500 | PIMS (end-of-year child accounting) | Instructional **days and hours** | LEA | FOIA? | **LEAD** | Reported annually. [PA Instructional Time BEC](https://www.pa.gov/agencies/education/resources/policies-acts-and-laws/basic-education-circulars-becs/purdons-statutes/instructional-time-and-act-80-exceptions) |
| OR | ~200 | 3rd-party (Stand for Children) + SEA | District bell schedules / contact time | district | DOWNLOAD? | **LEAD** | Someone already built it (2025-26). [Stand OR district lookup](https://stand.org/oregon/district-lookup-tool/) — reuse/partner |
| ID | ~150 | SDE (calendar collection) | School calendars | district | FOIA? | **LEAD** | Collected for min-days rulemaking |
| FL | ~75 | FLDOE (already integrated for enroll/staff) | TBD | — | — | **TODO** | We have an SEA relationship already (SEA_INTEGRATION_GUIDE) |
| MI | ~830 | CEPI (already integrated) | TBD | — | — | **TODO** | Existing integration |
| MA | ~400 | DESE (already integrated) | TBD | — | — | **TODO** | Existing integration |
| VA | ~130 | VDOE (already integrated) | TBD | — | — | **TODO** | Existing integration |
| *(remaining ~37 states)* | — | — | — | — | — | **TODO** | Research in district-count priority order |

District counts are approximate (regular operating districts) and used only to prioritize harvest effort.

---

## Why this changes the plan

1. **SEA harvest is now the primary method, scraping the fallback.** The Crawlee+Ollama pipeline we built is still valuable — but for the *residual* states/districts without obtainable central data, not as the main acquisition path.
2. **Cost is no longer the constraint.** Even where we do use LLM extraction, cheap cloud models (Gemini 2.5 Flash-Lite $0.10/$0.40; GPT-4o-mini batch $0.075/$0.30 per 1M) make extracting *all* ~20K districts cost ~$30–170 total — see research notes below.
3. **The data is often better than a bell schedule.** District-reported instructional minutes (for funding) avoid the bell-schedule-parsing error class entirely (the wrong-grade / implausible-times failures from Jan 2026).

## Open questions per state (the real work)

- **Access:** is it a public bulk download, or does it need a FOIA/public-records request? (Determines effort.)
- **Element fidelity:** is it true *instructional* minutes (lunch/passing excluded) or gross "operational" minutes? (TX reports both — pick the right one.)
- **Grain & mapping:** building/grade vs district; join key to NCES via `state_district_crosswalk`.
- **Currency:** confirm post-COVID year (2023-24+); avoid COVID years.

## Suggested execution order

1. **Proof-of-concept harvest** on the cleanest download: **Colorado** (explicit hours/lunch/passing file) or **Ohio** (EMIS Hours-Per-Day) → validate the join to `districts`/`state_district_crosswalk` and the LCT pipeline ingestion path for SEA-sourced minutes.
2. **Top states by district count:** TX, CA, IL, MI, NY, OH, PA (already part-leads) — these alone cover a large share of the ~13K.
3. **Remaining states** in priority order; mark `SCRAPE` where no central data is obtainable.
4. Only then point Crawlee+Ollama at the residual `SCRAPE` set.

---

## Research notes (2026-06-06)

**Cheap LLM extraction pricing** (for the residual scrape set):
- Gemini 2.5 Flash-Lite: $0.10 in / $0.40 out per 1M ([Google pricing](https://ai.google.dev/gemini-api/docs/pricing))
- GPT-4o-mini batch: $0.075 in / $0.30 out per 1M ([OpenAI pricing](https://openai.com/api/pricing/))
- Claude Haiku 4.5 batch: $0.50 in / $2.50 out per 1M
- ~20K districts × (15K in + 500 out) ≈ **$26–34** on the cheapest tiers.

**Local extraction viability** (Ollama path): peer-reviewed studies show Qwen2.5-7B / Llama-3.1-8B matching GPT-4-class accuracy on structured extraction from messy documents (90%+ exact match when fine-tuned). The Jan-2026 failures were likely prompt/preprocessing, not model ceiling — the benchmark would confirm. ([Pathology extraction study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11958830/), [clinical extraction](https://www.nature.com/articles/s41598-025-28767-z))

**Common Crawl** (alternative to live crawling): queryable by domain via the CDX index (free); WARC files hold raw HTML. Risk: small district sites are thinly covered and stale (schedules change yearly), and PDFs are often absent. Useful as a supplement, not a primary source. ([cdx_toolkit](https://github.com/commoncrawl/cdx_toolkit))
