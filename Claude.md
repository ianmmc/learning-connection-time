# Claude Code Project Briefing: Learning Connection Time

## Project Mission

Transform student-to-teacher ratios into "Learning Connection Time" (LCT) metrics that tell the story of students getting shortchanged.

**Core Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:** 5,000 students, 250 teachers, 360 min/day → LCT = 18 min/student/day

**Goal:** Analyze data from the largest U.S. school districts to identify educational equity disparities.

---

## Project Context

Part of "Reducing the Ratio" educational equity initiative. Currently implementing **Phase 1.5**: enriching basic LCT with actual bell schedules from district websites.

**Known Limitations:** Individualization fallacy, time-as-quality assumption, averaging deception. See `docs/METHODOLOGY.md`.

---

## Current Date and Data Years

**Current Date:** January 24, 2026
**Current School Year:** 2025-26

### Data Year Strategy

| Data Type | Year | Notes |
|-----------|------|-------|
| Primary dataset | 2023-24 | NCES CCD enrollment/staffing |
| Bell schedules | 2025-26, 2024-25, 2023-24 | Any acceptable, search current first |
| COVID exclusion | 2019-20 through 2022-23 | Never use - abnormal schedules |

**Search Order:** 2025-26 → 2024-25 → 2023-24 (all post-COVID, interchangeable)

---

## Project Status (January 24, 2026)

- **Phase**: Bell Schedule Automation
- **Bell Schedules**: ~103 districts enriched (verified from database)
- **Scraper Service**: `infrastructure/scraper/` - Playwright-based, operational
- **SEA Integrations**: 9/9 complete (FL, TX, CA, NY, IL, MI, PA, VA, MA)
- **Database**: PostgreSQL 16, 17,842 districts
- **Test Suite**: 375 passed

> **Note**: Prior documentation claimed 192 districts. Investigation on Jan 24, 2026 revealed Dec 26-27 enrichment was hallucinated by AI. See `~/Development/221B-baker-street/CASE_FILE.md` for forensic analysis.

---

## Database Quick Reference

```bash
# Check database
psql -d learning_connection_time -c "SELECT COUNT(*) FROM districts;"

# Query enrichment status
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report
with session_scope() as session:
    print_enrichment_report(session)
"
```

**Key Tables:** `districts`, `bell_schedules`, `state_requirements`, `lct_calculations`, `state_district_crosswalk`

---

## Essential Commands

```bash
# Calculate LCT (recommended)
python infrastructure/scripts/analyze/calculate_lct_variants.py

# Interactive enrichment
python infrastructure/scripts/enrich/interactive_enrichment.py --state WI

# Run SEA integration tests
pytest tests/test_*_integration.py -v

# VERIFICATION (REQ-035/036/037) - Run after enrichment!
python infrastructure/scripts/verify_enrichment.py --quick
python infrastructure/scripts/verify_enrichment.py --validate-claim 103
python infrastructure/scripts/verify_enrichment.py --date-range 2025-12-25 2025-12-27
```

---

## Key Files

| Task | File |
|------|------|
| Bell schedule operations | `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md` |
| Data methodology | `docs/METHODOLOGY.md` |
| Database setup | `docs/DATABASE_SETUP.md` |
| SEA integration guide | `docs/SEA_INTEGRATION_GUIDE.md` |
| LCT calculation | `infrastructure/scripts/analyze/calculate_lct_variants.py` |
| Database queries | `infrastructure/database/queries.py` |

---

## Load Additional Context When Needed

This is the core briefing (~115 lines). For detailed information, load these appendices:

| Context Needed | Load File |
|----------------|-----------|
| Historical progress, directory structure, technical stack | `docs/claude-instructions/CLAUDE_REFERENCE.md` |
| Development workflow, testing, common commands | `docs/claude-instructions/CLAUDE_WORKFLOWS.md` |
| Data architecture, SEA integrations, crosswalks | `docs/claude-instructions/CLAUDE_DATA.md` |

**Token Efficiency:** Only load appendices relevant to the current task. This modular structure reduces context consumption by ~80% compared to the previous monolithic file.

---

## Critical Rules

1. **COVID Data Exclusion**: Never use 2019-20 through 2022-23 data
2. **Security Blocks**: ONE-attempt rule for Cloudflare/WAF-protected districts
3. **Temporal Validation**: Data from multiple sources must span ≤3 years
4. **Raw Data**: Never modify files in `data/raw/`
5. **Data Verification**: ALWAYS verify data exists in database before claiming enrichment counts. Never trust handoff documentation without database verification.

---

## Technical Reference

- **Crosswalk table**: `state_district_crosswalk` - single source of truth for all state mappings
- **SPED baseline**: 2017-18 IDEA 618/CRDC exempt from temporal rule
- **Scraper API**: `POST /scrape`, `GET /health`, `GET /status`
- **Multi-tier enrichment**: Playwright → HTML → PDF/OCR → Claude → Gemini

For detailed reference, load the appropriate appendix above.
