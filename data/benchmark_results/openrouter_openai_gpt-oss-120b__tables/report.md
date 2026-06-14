# Benchmark Report: openrouter:openai/gpt-oss-120b
Run date: 2026-06-13T22:20:32
Districts tested: 7
Total extraction time: 113s (avg 16.1s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 20.0% |
| JSON parse success | 71.4% |
| Grade coverage rate | 90.9% |
| False positive rate | 5.29/district |
| Mean time/extraction | 16.1s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Fairbanks North Star Borough S | AK | 9 | 10 | 90.0% |  |  |
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| Sweetwater County School Distr | WY | 9 | 30 | 30.0% |  |  |
| Montgomery County | AL | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+26 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+38 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | json_parse_failure | JSON failure |

## Detailed Scoring

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 9 (entries) + 0 (penalties) = 9/10 (90.0%)

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
Ground truth: 1 entries | Extracted: 17 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:50-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:25-14:55 (Blackham))
  false_positive: -3 (elementary 08:50-15:10 (Batalla))
  false_positive: -3 (elementary 08:50-15:10 (Beardsley))
  false_positive: -3 (elementary 08:50-15:10 (Black Rock))
  false_positive: -3 (elementary 08:50-15:10 (Bryant))
  false_positive: -3 (elementary 08:50-15:10 (Classical Studies))
  false_positive: -3 (elementary 08:50-15:10 (Columbus))
  false_positive: -3 (elementary 08:50-15:10 (Geraldine Claytor))
  false_positive: -3 (elementary 08:45-15:05 (Curiale))
  false_positive: -3 (elementary 08:50-15:10 (Discovery))
  false_positive: -3 (elementary 08:50-15:10 (Dunbar))
  false_positive: -3 (elementary 08:50-15:10 (Edison))
  false_positive: -3 (elementary 08:50-15:10 (Geraldine Johnson))
  false_positive: -3 (elementary 08:50-15:10 (Hall))
  false_positive: -3 (elementary 08:50-15:10 (Hallen))
  false_positive: -3 (elementary 08:35-14:55 (High Horizon))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))

Total: 9 (entries) + -74 (penalties) = 0/10 (0.0%)

======================================================================
KIPP DC PCS (DC) - 1100031
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  high 08:15-15:15 → high 08:15-15:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:30 → middle 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: elementary 08:00-15:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: elementary)

Total: 18 (entries) + -2 (penalties) = 16/30 (53.3%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 24 | Matched: 3

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-14:20 → high 07:10-14:10 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 09:30-16:04 → middle 08:45-16:00 | start=0/3 (Δ45m) end=1/3 (Δ4m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
  false_positive: -3 (elementary 08:45-15:00 (Deerwood))
  false_positive: -3 (elementary 08:15-15:30 (Orange Center))
  false_positive: -3 (elementary 08:15-15:30 (Eccleston))
  false_positive: -3 (elementary 08:15-15:30 (Orlo Vista))
  false_positive: -3 (elementary 08:15-15:30 (Engelwood))
  false_positive: -3 (elementary 08:15-15:30 (Hiawassee))
  false_positive: -3 (elementary 08:15-15:30 (Pineloch))
  false_positive: -3 (elementary 08:15-15:30 (Pinewood))
  false_positive: -3 (elementary 08:15-15:30 (Ivey Lane))
  false_positive: -3 (elementary 08:15-15:30 (Ridgewood Park))
  false_positive: -3 (elementary 08:15-15:30 (Washington Shores))
  false_positive: -3 (elementary 08:15-15:30 (Rock Lake))
  false_positive: -3 (elementary 08:15-15:30 (Rolling Hills))
  false_positive: -3 (elementary 08:15-15:30 (Rosemont))
  false_positive: -3 (elementary 08:15-15:30 (Shingle Creek))
  false_positive: -3 (elementary 08:15-15:30 (Wheatley))
  false_positive: -3 (elementary 08:15-15:30 (Tangelo Park))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))

Total: 14 (entries) + -103 (penalties) = 0/30 (0.0%)

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
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 07:50-15:15 → elementary 07:45-15:00 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 08:00-15:55 → high 07:45-16:05 | start=0/3 (Δ15m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 9 (entries) + 0 (penalties) = 9/30 (30.0%)