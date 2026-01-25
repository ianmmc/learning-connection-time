# Strategic Analysis: Optimizing Bell Schedule Collection

**Date:** January 25, 2026
**Status:** Strategic Recommendation

---

## Current State Assessment

### Success Rates by Method
| Method | Districts | % of Successes |
|--------|-----------|----------------|
| **Human-provided** | 40 | 52% |
| Automated enrichment | 28 | 36% |
| Web scraping | 7 | 9% |
| Tier 1 Firecrawl | 4 | 5% |
| **Total** | 77/17,842 | 0.4% overall |

**Key Insight:** Human effort (40 districts) has been MORE effective than all automated methods combined (38 districts).

### What Failed or Underperformed
1. **Gemini API (~28-56% error rate)** - Hallucinated plausible-looking data, removed from pipeline
2. **Full automation for complex sites** - JS-heavy CMS (Finalsite, SchoolBlocks) defeat scrapers
3. **Security blocks** - ~15% of sites have Cloudflare/WAF protection
4. **School-level variation** - Most districts don't publish unified schedules

### What Worked
1. **Human search** - Most reliable, accounts for 52% of successes
2. **Perplexity for verification** - Good citations, catches hallucinations
3. **Tier 1-3 for simple sites** - Free local processing works when it works
4. **Claude Review for context** - Good at understanding pages, needs human validation

---

## Strategic Recommendations

### Priority 1: Optimize Human Search (Highest ROI)

Since humans produce 52% of successes, make human search 10x faster:

**A. AI-Assisted Search Generation (NOT extraction)**
Instead of having AI extract data, have AI generate optimal search queries:
```
Human: "Denver Public Schools"
AI: Here are 5 search strategies:
1. "Denver Public Schools 2025-26 bell schedule"
2. site:dpsk12.org bell schedule
3. "DPS" "school hours" elementary middle high
4. Denver schools start time 2025
5. dpsk12.org/calendar OR dpsk12.org/parents
```

**B. Quick-Entry Interface**
Build a simple web form:
- Pre-populated with district name, state
- Paste URL where found
- Dropdowns for grade levels
- Auto-calculate instructional minutes
- ~30 seconds per district vs current manual database entry

**C. Batch Human Processing**
Instead of one district at a time:
- Group by state (same timezone, similar patterns)
- Open 10 district tabs, scan all, record findings
- Estimated: 5-10 districts per hour vs current 2-3

### Priority 2: State Education Agency Data (Medium effort, high potential)

**Colorado Model:**
Colorado actually collects instructional hours/days at the state level via their [Periodic Data Collection](https://www.cde.state.co.us/datapipeline/per_inst-hours-days).

**Action Items:**
1. Contact Colorado DOE for bulk data export (covers ~180 districts)
2. Identify other states with similar mandatory reporting
3. Submit FOIA requests where needed

**Likely States with Data:**
- States with centralized SIS requirements
- States that already collect calendar data for transportation
- Contact [Education Commission of the States](https://www.ecs.org/) for guidance

### Priority 3: Focus on Impact (200 Largest Districts)

**The 80/20 Rule:**
The 200 largest districts serve 13.6M students. Fully enriching these 200 would provide more impact than partially enriching 17,000+.

**Current State:**
- **52 of top 200** have bell schedules (26% coverage)
- **148 missing** in top 200
- **6.6M students covered** (48.6% of top 200 enrollment)

**Top 30 Missing (Highest Priority):**
| # | District | State | Enrollment |
|---|----------|-------|------------|
| 1 | Puerto Rico DOE | PR | 240,910 |
| 2 | Pasco | FL | 85,855 |
| 3 | Davidson County | TN | 80,468 |
| 4 | Greenville 01 | SC | 78,371 |
| 5 | Osceola | FL | 74,289 |
| 6 | Brevard | FL | 73,810 |
| 7 | Conroe ISD | TX | 72,352 |
| 8 | Fort Worth ISD | TX | 71,060 |
| 9 | Guilford County | NC | 67,832 |
| 10 | Milwaukee | WI | 66,864 |

**Action:** Human-search these 30 districts first (3 hours work) to add 1.1M students to coverage.

### Priority 4: Test External APIs (Low effort, unknown potential)

**SchoolDigger API** - [developer.schooldigger.com](https://developer.schooldigger.com/)
- Has 136,000 school profiles
- Cost: Free tier (2,000 calls), then $0.0028-0.004/call
- **Unknown if they have bell schedules** - worth testing with 5-10 calls

**GreatSchools NearbySchools API** - [greatschools.org/api](https://www.greatschools.org/api)
- 200,000 school profiles
- 14-day free trial
- Focus on ratings/demographics, but **might have hours**

**Action:** Sign up for free tiers, test 10 schools, report back.

### Priority 5: Crowdsourcing (Long-term)

**Concept:** Parents/teachers have this information readily available.

**Implementation Options:**
1. Simple Google Form shared on education forums
2. Partner with PTO networks
3. Incentivize with small donations to school PTOs

**Quality Control:**
- Require photo/screenshot of source
- Cross-validate with official website
- Multiple submissions = higher confidence

---

## NOT Recommended

### Full Automation at Scale
The economics don't work:
- ~0.2% success rate for automated methods
- Token cost for 17,000 districts adds up
- Maintenance burden exceeds benefit

### AI-Based Data Extraction
Every AI we've tested (Gemini, various scraper approaches) produces hallucinations that are costly to verify.

### Security Bypass Techniques
- Cloudflare bypass services exist but are ethically questionable
- Districts that block scrapers likely have reasons
- Better to handle these manually

---

## Recommended Approach: Phased Implementation

### Phase 1: Quick Wins (Week 1)
1. Build quick-entry web form for human data entry
2. Query to identify which top 200 districts need schedules
3. Human-search the top 50 missing from largest 200

### Phase 2: External Data (Week 2)
1. Test SchoolDigger and GreatSchools APIs (free tiers)
2. Contact Colorado DOE for bulk data
3. Research which other states collect this data

### Phase 3: AI-Assisted Human Search (Week 3)
1. Build search query generator
2. Create batch processing workflow
3. Target: 10 districts/hour human search rate

### Phase 4: Crowdsourcing Pilot (Week 4+)
1. Create simple submission form
2. Pilot with one state's parent community
3. Evaluate quality and scale potential

---

## Cost Comparison

| Approach | Monetary | Token/API | Human Time | Success Rate |
|----------|----------|-----------|------------|--------------|
| Current automated pipeline | $0 | High | Low | 0.2% |
| AI-assisted human search | $0 | Medium | Medium | ~80%+ |
| External APIs | $20-100 | Low | Low | Unknown |
| State data requests | $0 | Zero | Medium | ~100% (where exists) |
| Crowdsourcing | $0-50 | Zero | Low (setup) | Unknown |

**Recommendation:** Shift from "automate everything" to "AI-assisted human efficiency"

---

## Key Sources

- [SchoolDigger API](https://developer.schooldigger.com/)
- [GreatSchools API](https://www.greatschools.org/api)
- [ECS 50-State Instructional Time](https://www.ecs.org/50-state-comparison-instructional-time-policies-2023/)
- [Colorado Instructional Hours Collection](https://www.cde.state.co.us/datapipeline/per_inst-hours-days)
- [NCES Common Core of Data](https://nces.ed.gov/ccd/pubagency.asp)
