# Instructional Minute Metric — Project Context

> **Authority:** the project's mission, reframe, research questions, and 6-phase evolution roadmap — the
> "story," not the mechanics or the current build state.
> **Audience:** anyone new to the project (human or agent) who needs to understand *why* this exists before
> diving into *how* it's built.
> **Companions:** `docs/METHODOLOGY.md` (the LCT calculation mechanics), `docs/TERMINOLOGY.md` (vocabulary),
> `docs/GETTING_STARTED.md` (dev setup + orientation to the live codebase), root `CLAUDE.md` (current build
> status + durable operating rules), GitHub Issues/Projects (live task tracking).
> **Update this when:** the mission, the reframe, a research question, or the phase roadmap changes — NOT
> for build progress, which lives in `CLAUDE.md` and GitHub, not here.

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

Full formulas, staffing scopes, SPED segmentation, and validation rules: `docs/METHODOLOGY.md`.

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

## Where the project stands

LCT is currently in **Phase 1.5** of the evolution roadmap below (bell-schedule enrichment — moving from
statutory-minimum fallbacks to actual collected instructional time). For what's built, what's running, and
what's next: root `CLAUDE.md` is the current-status authority; day-to-day task tracking lives in GitHub
Issues/Projects, not in this document.

## Evolution Strategy

LCT is designed to evolve through six phases, addressing limitations while maintaining the core rhetorical power of the basic metric:

### Phase 1: Basic LCT — complete
- Uses available enrollment and staff data
- Applies state statutory instructional minutes
- Provides district-level comparisons
- Implemented with grade-level breakdowns and multiple staffing-scope variants

### Phase 1.5: Bell Schedule Enrichment & SPED Segmentation — current
- Actual instructional time collection (vs statutory fallback), via a 9-stage acquisition pipeline
  (`docs/ACQUISITION_PIPELINE.md`) that finds, captures, and extracts real bell schedules
- SPED segmentation: self-contained vs. mainstreamed SPED distinction, three dedicated LCT scopes
  (`docs/METHODOLOGY.md` §SPED Segmentation)
- Data quality safeguards (error/warning flags on every calculation)

**Known limitations carried into this phase**:
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

## Ethical Considerations

1. **Avoid Deficit Framing**: Never imply that students or communities are lacking
2. **Contextual Analysis**: Always provide context for numerical disparities
3. **Systemic Focus**: Frame inequities as policy/resource issues, not individual failures
4. **Actionable Insights**: Connect findings to concrete policy recommendations
5. **Stakeholder Engagement**: Involve educators and communities in interpretation

## Success Criteria (the durable, long-horizon goals — not a build checklist)

- Establish LCT as a recognized, defensible education equity metric
- Identify compelling, well-evidenced equity stories worth publishing
- Enable district-to-district and state-to-state comparisons that hold up to scrutiny
- Longer-term: integration into state/federal reporting conversations; policy changes informed by LCT
  analysis; measurably reduced educational-opportunity-gap blind spots

For what's actually done vs. in flight toward these goals, see `CLAUDE.md` and GitHub Issues/Projects.
