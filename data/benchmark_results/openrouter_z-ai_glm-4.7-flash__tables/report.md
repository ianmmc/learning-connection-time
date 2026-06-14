# Benchmark Report: openrouter:z-ai/glm-4.7-flash
Run date: 2026-06-13T22:32:39
Districts tested: 7
Total extraction time: 243s (avg 34.8s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 0.0% |
| JSON parse success | 14.3% |
| Grade coverage rate | 33.3% |
| False positive rate | 0.29/district |
| Mean time/extraction | 34.8s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Montgomery County | AL | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Bridgeport School District | CT | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| KIPP DC PCS | DC | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, duplicate_extraction (+2 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Sweetwater County School Distr | WY | 0 | 30 | 0.0% | json_parse_failure | JSON failure |

## Detailed Scoring

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
KIPP DC PCS (DC) - 1100031
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: high 07:20-14:20 (unnamed) → 0/10
  MISSED: middle 09:30-16:04 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 8 (entries) + -12 (penalties) = 0/30 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)