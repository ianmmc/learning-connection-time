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

## Current Status (2026-06-13 — see root `CLAUDE.md` for the live 2026-06-22 picture)

> **Freshness:** This block is the 2026-06-13 snapshot. The current state (per-school pipeline built, **GROSS bell-to-bell** metric, 6-model council with composition TBD, reader-routing, 3 human checkpoints, code at `infrastructure/acquisition/`, GT 940/943 verified) lives in root `CLAUDE.md` → *Current Status* + *Next session*. Below is retained as the design-validation milestone.

**Phase**: Pipeline design validated end-to-end — extraction *and* discovery proven; building toward a cheap-cloud "council" + per-school targeting
**Extraction finding**: a capable cloud model ~doubles the best local. Full-41 leader **Gemini 2.5 Flash 68.9%** (cheapest *and* best); on *good* inputs (difficulty > 0.70) top models hit **~95–100%**. **Input quality, not the model, is the ceiling** (20% of districts solved by zero models; hard inputs failed on granularity/noise, not OCR). See `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.
**Discovery finding**: search-led discovery works; **domain-scoped search** (Perplexity / OpenRouter `gpt-4o-mini-search` / Claude WebSearch) eliminates the wrong-district problem and reaches school subdomains. Blind Crawlee crawling fails. New bottleneck = capture fidelity on JS pages → tiered capture (text-layer preferred; screenshot+OCR/vision fallback).
**Direction**: per-school targeting → tiered capture → cheap-cloud council consensus (Gemini 2.5 Flash + a cross-family model) → fail-loud statutory fallback. Multi-model conduits wired (`pplx:`, `openrouter:` in `extractors.py`). REQ-043…053.
**Coverage**: 17,842 U.S. school districts in PostgreSQL database
**SEA Integrations**: 9/9 complete (FL, TX, CA, NY, IL, MI, PA, VA, MA) ✅
**Acquisition Stack**: search APIs (Perplexity/OpenRouter/Claude WebSearch) for discovery + Playwright capture; Crawlee re-cast as terrain-mapper/one-hop fetcher; cheap-cloud council for extraction (local Ollama models deleted post-benchmark; Granite 4.1 8B is the self-host candidate)
**Data Sources**: Federal (NCES, CRDC, IDEA 618) + Bell schedules + State agencies

> **Note:** Strategy evolved twice — the Jan-2026 local-first Crawlee+Ollama pivot (to avoid per-token cost) was itself superseded on 2026-06-13 once benchmarking showed paid-cloud extraction is *cheap* (~$0.05–0.30/1M) and far more accurate. Canonical learnings: `docs/technical-notes/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md`. Architecture map: `docs/PROJECT_HISTORY.md` (Part 5; SYNTHESIS archived).

### What We Have ✅
- Comprehensive project structure
- PostgreSQL database with 17,842 districts
- Multi-part file handling capability
- SPED segmentation (v3 self-contained focus)
- Data safeguards (7 validation flags)
- Crawlee scraper service (Playwright browsers) with async crawl jobs, school discovery + grade-band sampling
- Local-first acquisition pipeline: Crawlee mapping → Ollama URL ranking → PDF capture → Ollama triage
- Local LLM time-extraction stage (Ollama) with deterministic minutes calculation
- Ground-truth + benchmark harness for measuring local extraction accuracy
- LCT calculation engine with variants
- QA dashboard and validation framework
- Interactive enrichment tools
- Grade-level analysis (elementary, middle, high)
- Token-optimized infrastructure (88% size reduction)

### Recent Work (Jan 2026)

- **9/9 SEA integrations complete** with crosswalk tables
- Pivot from cloud multi-tier (Firecrawl/Gemini) to local-first Crawlee + Ollama acquisition
- Async crawl jobs, serial acquisition queue, school discovery + grade-band sampling
- Local Ollama time-extraction stage + deterministic minutes calculation
- Ground-truth labeling + benchmark harness (in progress) to validate extraction accuracy

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

## Next Steps

1. **Immediate** (This Month - January 2026)
   - Continue state-by-state bell schedule enrichment
   - Analyze SPED segmentation results for policy insights
   - Document equity findings from SPED data
   - Refine data safeguard thresholds based on review

2. **Short-term** (Next Quarter - Q1 2026)
   - Complete bell schedule enrichment for remaining priority states
   - Generate district-level SPED equity profiles
   - Create visualization dashboard for LCT variants
   - Draft initial SPED disparity analysis report

3. **Medium-term** (H1 2026)
   - Complete Layer 2 integrations for Florida and New York
   - Enhance Texas with PEIMS data (if needed for deeper analysis)
   - Expand SPED analysis with state-specific data where available
   - Develop interactive web tool for LCT exploration
   - Publish methodology paper and findings

---

**Document Version**: 2.3
**Last Updated**: June 13, 2026
**Status**: Bell Schedule Acquisition - local-first Crawlee + Ollama pipeline with 9/9 SEA integrations complete
