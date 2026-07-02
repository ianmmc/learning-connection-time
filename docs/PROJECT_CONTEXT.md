# Instructional Minute Metric - Project Context

## Mission

Transform abstract student-to-teacher ratios into tangible metrics that tell the story of student educational equity through "Learning Connection Time" (LCT).

**Core Insight**: A 20:1 student-teacher ratio doesn't communicate that each student receives approximately 18 minutes of potential individual attention per day.

## Background

Traditional education metrics like student-to-teacher ratios are:
- **Abstract**: "20:1" doesn't convey real student experience
- **Teacher-burden focused**: Frames the conversation around teacher workload
- **Equity-masking**: Hides disparities in actual educational resources

### The Reframe

**From**: "This district has a 20:1 student-teacher ratio"
**To**: "Students in this district receive 18 minutes of potential individual teacher attention per day"

This reframing:
1. Makes resource disparities tangible
2. Centers the student experience
3. Enables meaningful equity comparisons across districts

## Learning Connection Time (LCT)

### Basic Formula

```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

### Example Calculation

**District Profile**:
- Enrollment: 5,000 students
- Instructional Staff: 250 teachers
- Daily Instruction: 360 minutes (6 hours)

**Calculation**:
```
LCT = (360 minutes × 250 teachers) / 5,000 students
LCT = 90,000 / 5,000
LCT = 18 minutes per student per day
```

### What This Means

- Each student in this district receives ~18 minutes of potential individual teacher attention daily
- Over a 180-day school year: 3,240 minutes = 54 hours total
- This is a resource metric, not an outcome metric

## Key Questions

### Primary Research Questions

1. **Variability**: How does LCT vary across the largest U.S. school districts?
2. **Equity**: What are the equity implications when comparing districts serving different populations?
3. **Policy**: How do state instructional time requirements affect calculations?
4. **Data Availability**: What data is actually accessible vs. what would be ideal?

### Secondary Considerations

- Within-district variations (school-level analysis where possible)
- Demographic correlations (with careful attention to avoid deficit framing)
- Temporal trends (year-over-year changes)
- Relationship to outcomes (with appropriate caveats)

## Current Status (2026-07-01 — root `CLAUDE.md` *Current Status* is always the live authority)

**Phase**: Phase 1.5 (bell-schedule enrichment) via the **9-stage per-school acquisition pipeline**
(`infrastructure/acquisition/`), console-driven and **built through the Stage 6→7 seam** — the paid
council extraction (Stage 7), per-band aggregation (Stage 8), and LCT-DB write (Stage 9) are next.
**Metric**: **GROSS bell-to-bell minutes** (`end − start`, labeled `gross_bell_to_bell`; net
deferred). Extractors read TIMES; deterministic code computes minutes + the per-band mode
(REQ-054/055/056).
**Extraction finding** (the durable one): on good inputs top cheap cloud models hit ~95–100% —
**input quality, not the model, is the ceiling**; hence the pipeline's per-school targeting,
tiered capture, and Stage-5 filtering. See `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.
**Discovery**: a deterministic SERP cascade (Bright Data SERP + Serper failover → Claude WebSearch
residual) — **the search index predicts recall**; agent-led and own-index providers retired.
**Coverage**: 17,842 U.S. school districts in PostgreSQL · **SEA Integrations**: 9/9 (FL, TX, CA,
NY, IL, MI, PA, VA, MA) ✅ · **Data Sources**: Federal (NCES CCD, CRDC, IDEA 618) + bell schedules
+ state agencies.
**Architecture**: isolated `governance` Postgres = the working store; JSON artifacts = auditable
receipts; cross-stage state = the `state_event` log; human gates are stage-numbered
(`gate@1/5/6/7/8`).

> **History note:** strategy evolved twice — cloud multi-tier (Firecrawl/Gemini) → the Jan-2026
> local-first Crawlee+Ollama pivot → superseded 2026-06-13 when benchmarking showed paid-cloud
> extraction is *cheap* (~$0.05–0.30/1M) and far more accurate. The Crawlee/Ollama stack is
> archived (`data/archive/crawlee-ollama-era-superseded-20260625/`). Canonical learnings:
> `docs/technical-notes/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md`; decisions:
> `docs/PROJECT_HISTORY.md`.

### What We Have ✅
- PostgreSQL database with 17,842 districts; 9/9 SEA crosswalks
- LCT calculation engine with variants (8+2 staff scopes, grade-level breakdowns)
- SPED segmentation (v3 self-contained focus) + data safeguards (7 validation flags)
- QA dashboard and validation framework; interactive enrichment tools
- Acquisition Stages 1–6 built + run live on real batches: gate@1 queue console, SERP discovery,
  Playwright capture (fingerprinting, de-chrome, iframe/embed), local processing (pdftotext /
  pdfplumber / camelot / tesseract), Stage-5 detector/combiner scoring + three-axis human
  labeling (440 labels), Stage-6 routing/pricing/immutable dispatch (gate@6)
- The measurement discipline: config-as-data + fingerprinted scorecards + tuning ledger
  (nothing ships to scoring without harness measurement)

## Evolution Strategy

LCT is designed to evolve through six phases, addressing limitations while maintaining the core rhetorical power of the basic metric:

### Phase 1: Basic LCT ✅ Complete
- Uses available enrollment and staff data
- Applies state statutory instructional minutes
- Provides district-level comparisons
- **Status:** Implemented with grade-level breakdowns

### Phase 1.5: Bell Schedule Enrichment & SPED Segmentation 🔄 In Progress
- Actual instructional time collection (vs statutory fallback)
- SPED segmentation (v3 self-contained focus):
  - Three LCT scopes: core_sped, teachers_gened, instructional_sped
  - Self-contained SPED vs mainstreamed SPED distinction
  - Two-step ratio estimation using IDEA 618 + CRDC baselines
  - See [SPED_SEGMENTATION_IMPLEMENTATION.md](SPED_SEGMENTATION_IMPLEMENTATION.md) for methodology
- Data quality safeguards (6 validation flags)
  - See [METHODOLOGY.md](METHODOLOGY.md#data-safeguards) for details
- PostgreSQL database infrastructure

**Current Limitations**:
- Individualization fallacy (assumes all time could be 1-on-1)
- Time-as-quality assumption (more time ≠ better education)
- Averaging deception (masks within-district disparities)
- SPED estimation uses state-level ratios (not LEA-specific)

### Phase 2: Teacher Quality Weights
- Incorporate teacher experience, certification, education level
- Create weighted instructional staff counts
- More accurately reflect instructional capacity

### Phase 3: Differentiated Student Needs
- Account for special education, ELL, gifted services
- Apply multipliers based on student needs
- Reflect actual attention requirements

### Phase 4: Interaction Quality Dimensions
- Incorporate class size data where available
- Consider instructional model variations
- Account for collaborative vs. individual instruction

### Phase 5: Opportunity-to-Connect Scores
- Develop composite metrics
- Include accessibility factors
- Consider scheduling and structure

### Phase 6: Outcome-Validated Connection Time
- Correlate with achievement data
- Validate against graduation rates, growth metrics
- Establish evidence-based thresholds

## Critical Methodological Notes

### What LCT Is
- A **resource metric** quantifying instructional staff time availability
- A **comparison tool** for equity analysis
- A **communication device** for making ratios tangible

### What LCT Is NOT
- An **outcome measure** (doesn't directly measure learning)
- A **quality indicator** (doesn't assess instruction effectiveness)
- A **comprehensive metric** (one dimension of many in education)

### Appropriate Uses
✅ Comparing resource allocation across districts
✅ Identifying potential equity concerns
✅ Framing policy discussions about staffing
✅ Communicating abstract ratios to stakeholders

### Inappropriate Uses
❌ Ranking districts as "better" or "worse"
❌ Making hiring/firing decisions
❌ Predicting student outcomes
❌ Deficit framing of communities

## Related Work

### Technical Integration
- **OneRoster**: Direct Student Information System access for live calculations
- **React Prototype**: Web-based visualization tool
- **1EdTech Standards**: Analysis of temporal dimension limitations

### Broader Initiative
- **"Reducing the Ratio"**: Educational equity campaign
- **Strategic Reframing**: Moving from teacher burden to student opportunity
- **Policy Language**: Development of equity-focused terminology

## Success Criteria

### Phase 1 (Initial Analysis) ✅ Mostly Complete
- [x] Successfully calculate LCT for all districts in database
- [x] Document data availability and limitations
- [x] Enrich districts with actual bell schedules (campaign complete - 182 districts, 50 U.S. states)
- [x] Implement SPED segmentation (v3)
- [x] Create data quality safeguards
- [ ] Identify 3-5 compelling equity stories (in progress)
- [ ] Create visualization prototypes (pending)

### Long-term
- [ ] Establish LCT as recognized education metric
- [ ] Integration into state/federal reporting
- [ ] Policy changes informed by LCT analysis
- [ ] Reduced educational opportunity gaps

## Ethical Considerations

1. **Avoid Deficit Framing**: Never imply that students or communities are lacking
2. **Contextual Analysis**: Always provide context for numerical disparities
3. **Systemic Focus**: Frame inequities as policy/resource issues, not individual failures
4. **Actionable Insights**: Connect findings to concrete policy recommendations
5. **Stakeholder Engagement**: Involve educators and communities in interpretation

## Technical Architecture

### Data Flow
```
Federal/State Sources
    ↓
[Download Scripts]
    ↓
Raw Data (with metadata)
    ↓
[Extract & Combine]
    ↓
[Normalize Schema]
    ↓
Processed Data
    ↓
[Calculate LCT]
    ↓
Enriched Data
    ↓
[Generate Reports]
    ↓
Outputs & Visualizations
```

### Quality Assurance
- Validation at every stage
- Processing logs with full lineage
- Test suite for calculations
- Manual spot-checks of results

## Next Steps (2026-07; live sequencing in root `CLAUDE.md` → "Next session")

1. **Immediate**
   - Complete the v2.1 re-tagging of the 440 Stage-5 labels (field observations →
     `STAGE5_FILTER_DESIGN` §3a; fold in measured, never by eye)
   - Facet-level per-detector scoring (as re-tagging fills the confounder facets)

2. **Short-term**
   - The council lab (`cost_benchmark`): measured token model + live OpenRouter pricing
   - **Stage 7** (paid council + judge loop + request-more-evidence back-edges, budget-governed)
   - Stage 8 (per-band modal aggregation + gate@8) → Stage 9 (LCT-DB write)

3. **Medium-term**
   - GT alignment into the pipeline (`batch_00000`) → council composition re-benchmark
   - Scale batches toward the enrollment-weighted top districts; funnel/coverage analysis
   - Equity-story analysis and visualization on enriched (gross bell-to-bell) LCT

---

**Document Version**: 2.4
**Last Updated**: July 1, 2026
**Status**: Bell Schedule Acquisition — 9-stage pipeline built through the Stage 6→7 seam; Stage 7 (paid council extraction) next; 9/9 SEA integrations complete
