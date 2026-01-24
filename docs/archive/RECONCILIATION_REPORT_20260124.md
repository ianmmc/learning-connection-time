# Data Reconciliation Report: Bell Schedule Discrepancy

**Date:** January 24, 2026
**Investigator:** Claude (Holmes)
**Reviewer:** Gemini (Watson)

---

## Executive Summary

Investigation revealed a data contamination issue where LCT calculation CSV files falsely labeled 101 districts as having bell schedule data when they should have been labeled as `state_requirement`.

**Key Finding:** The database was correct. The CSV files were contaminated.

---

## Discrepancy Details

| Metric | CSV Claim | Database Reality | Difference |
|--------|-----------|------------------|------------|
| Districts with `bell_schedule` source | 183 | 82* | 101 phantom |
| Total unique districts with bell schedules | - | 103** | - |

*At time of CSV generation (Jan 19-20, 2026)
**Current database state (Jan 24, 2026)

---

## Timeline

| Date | Event | Districts |
|------|-------|-----------|
| Dec 25, 2025 | Initial bell schedule import | 82 |
| Jan 19-20, 2026 | Contaminated CSV generated | 183 claimed (101 false) |
| Jan 23, 2026 | Additional enrichment | +1 |
| Jan 24, 2026 | Investigation + cleanup | +20 (total: 103) |

---

## Root Cause Analysis

### Contamination Source
The 101 phantom districts were traced to `data/enriched/bell-schedules/tier3_statutory_fallback/` directory which contains JSON files with:
- `method: "state_statutory"`
- `confidence: "statutory"`
- `source: "State statute"`

These should have been labeled as `instructional_minutes_source: state_requirement` in the CSV, not `bell_schedule`.

### How It Happened
Investigation inconclusive. The CSV generation code (`calculate_lct_variants.py::get_instructional_minutes()`) correctly queries the database. Possible causes:
1. Different code path used during generation
2. Data existed in database then was deleted
3. Bug in an import script not yet identified

### Watson's Gap Analysis
1. **Root cause deep dive** - Further investigation needed
2. **Impact assessment** - Affected LCT calculations used incorrect source labels
3. **Monitoring** - Add pre-generation validation
4. **Data provenance** - Improve source tracking
5. **Cross-validation** - Validate source labels during generation

---

## Corrections Applied

### Files Deleted
All files in `data/enriched/lct-calculations/`:
- 8 CSV files (variants, valid, summary, state)
- 8 JSON files (QA reports)
- 8 TXT files (reports)

### Documentation Updated
- `CLAUDE.md`: Updated to show ~103 districts (verified)
- Added note about prior hallucination claim

### Verification Safeguards
REQ-035 through REQ-039 implemented:
- Count verification against database
- Content plausibility validation
- Override audit trail
- Confidence interval-based discrepancy detection

---

## Database State (Verified)

```
Total unique districts: 103
By year:
  2023-24: 5 districts
  2024-25: 74 districts
  2025-26: 24 districts

Total bell_schedule records: 289
```

---

## Prevention Measures

1. **REQ-035**: Enrichment count verification before documentation
2. **REQ-036**: Handoff documents reference verifiable database state
3. **REQ-037**: DataLineage audit trail completeness
4. **REQ-038**: Content plausibility validation
5. **REQ-039**: Override audit trail

---

## Signatures

**Investigator:** Claude (Opus 4.5)
**Reviewer:** Gemini (via MCP)
**Date:** January 24, 2026
