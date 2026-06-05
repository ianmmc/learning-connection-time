# Enrichment Pipeline Test Results

**Date:** 2026-01-26
**Purpose:** Validate Phase 8 enrichment pipeline by comparing original database records with new pipeline extractions

## Test Districts - Final Results

| NCES ID | State | District Name | Original DB Record(s) | New Pipeline Result |
|---------|-------|---------------|----------------------|---------------------|
| 4666270 | SD | Sioux Falls School District 49-5 | elem: 8:55 AM - 3:48 PM (413 min) | elem: 12:00 - 19:00 (390 min), high: 07:00 - 16:30 (540 min) |
| 4659820 | SD | Rapid City Area School District 51-4 | middle: 8:10 AM - 3:25 PM (435 min) | **high: 08:10 - 14:35 (355 min), middle: 08:10 - 14:35 (355 min)** |
| 1302280 | GA | Fulton County | elem: 7:50AM - 2:20PM (390 min), middle: 8:30AM - 3:30PM (420 min), high: 9:15AM - 4:15PM (420 min) | elem: 07:40 - 14:20 (370 min), middle: 08:55 - 16:05 (400 min) |
| 0804800 | CO | Jefferson County R-1 | elem: 9:50 AM - 3:05 PM (315 min) | elem: 07:15 - 15:45 (480 min), high: 08:05 - 15:20 (405 min) |
| 0803360 | CO | Denver Public Schools | elem: 7:50AM - 2:50PM (420 min), middle: 8:00AM - 3:30PM (450 min), high: 8:00AM - 3:30PM (450 min) | **NO RECORDS** (extraction returned "unknown" grade levels) |
| 0634320 | CA | San Diego Unified | elem: 7:50 AM - 3:05 PM (435 min) | middle: 07:45 - 15:45 (450 min), elem: 07:15 - 15:00 (435 min) |
| 0626910 | CA | New Haven Unified | elem: 8:30 AM - 2:05 PM (335 min) | elem: 8:30 AM - 2:05 PM (335 min) (original retained) |
| 0614550 | CA | Fresno Unified | high: 8:30 AM - 3:20 PM (410 min) | **elem: 08:00 - 14:05 (335 min)** |
| 0634410 | CA | San Francisco Unified | elem: 7:50 AM - 2:05 PM (375 min), middle: 9:30 AM - 4:00 PM (390 min), high: 8:40 AM - 3:40 PM (420 min) | elem: 7:50 AM - 2:05 PM (375 min), middle: 9:30 AM - 4:00 PM (390 min), high: 8:40 AM - 3:40 PM (420 min) (original retained) |
| 1914700 | IA | Iowa City Comm School District | elem: 9:22 AM - 3:07 PM (345 min) | middle: 07:55 - 14:55 (390 min), elem: 09:00 - 15:05 (335 min) |

## Pipeline Summary

| Metric | Count |
|--------|-------|
| Districts processed | 10 |
| Districts with new data | 7 |
| Districts with original data retained | 2 |
| Districts with no records | 1 |

## Pipeline Improvements Made

1. **Deduplication** - Added grade-level deduplication to import script (highest confidence wins)
2. **Low priority execution** - `os.nice(10)` for resource-friendly processing
3. **Inter-district delays** - 30 second delays between districts for memory cleanup
4. **Longer timeouts** - 180 second timeout for Ollama extraction

## Issues Identified

### Grade Level Detection
- Denver extraction returned all "unknown" grade levels
- The Ollama prompt needs improvement to better identify grade levels from school names
- Consider adding post-extraction grade level inference based on school name patterns

### Data Quality Concerns
- **Sioux Falls**: 12:00-19:00 for elementary is suspicious (7 hours starting at noon)
- **Rapid City**: Same times for high and middle school
- **Jefferson County**: 480 min (8 hours) for elementary seems high

### Extraction Accuracy
- Some districts lost grade levels (Fulton County: lost high school)
- Some districts gained grade levels (San Diego: added middle, Iowa City: added middle)
- Fresno: Changed from high school to elementary

## Recommendations

1. **Human review required** for extracted data before production use
2. **Add validation rules** to flag suspicious times (e.g., >450 min, start after 10am)
3. **Improve grade level detection** in extraction prompt
4. **Consider multi-pass extraction** with Claude verification for critical districts

## Files Generated

For each processed district:
- `extraction_result.json` - Raw Ollama extraction output
- `enrichment_ready.json` - After minutes calculation
- `import_result.json` - Import status and deduplication notes
