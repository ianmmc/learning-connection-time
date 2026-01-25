# Archived Bell Schedule Documentation

**Archived:** January 24, 2026
**Reason:** Superseded by multi-tier automated pipeline

These documents describe the manual/semi-automated bell schedule enrichment workflow that was replaced by the automated 5-tier enrichment pipeline in January 2026.

## Archived Files

| File | Original Purpose | Superseded By |
|------|------------------|---------------|
| BELL_SCHEDULE_OPERATIONS_GUIDE.md | Manual enrichment procedures | Automated tier processors |
| BELL_SCHEDULE_SAMPLING_METHODOLOGY.md | Sampling strategy and tier definitions | MULTI_TIER_ENRICHMENT_ARCHITECTURE.md |
| QUICK_REFERENCE_BELL_SCHEDULES.md | Quick commands for manual workflow | Automated pipeline |
| SCHOOL_LEVEL_DISCOVERY_ENHANCEMENT.md | School-level discovery | Integrated into Tier 1-2 processors |

## Current Documentation

The canonical documentation for bell schedule enrichment is now:

- **[MULTI_TIER_ENRICHMENT_ARCHITECTURE.md](../../MULTI_TIER_ENRICHMENT_ARCHITECTURE.md)** - Architecture and implementation details
- **[DATABASE_SETUP.md](../../DATABASE_SETUP.md)** - Database schema including `enrichment_queue` table

## Key Differences

### Old Approach (Manual)
- Web search → manual fetch → local processing → JSON output
- Single-phase discovery (district-only)
- Manual tier selection
- Statutory fallback on any failure

### New Approach (Automated)
- 5-tier automatic escalation: Firecrawl → Playwright → PDF/OCR → Claude → Gemini
- Security blocking for Cloudflare/WAF/403 sites
- Continuous processing until queue complete
- Auto-testing on completion
