# Benchmark Report: ollama:qwen2.5:7b
Run date: 2026-06-12T23:23:05
Districts tested: 17
Total extraction time: 1520s (avg 89.4s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 8.8% |
| JSON parse success | 88.2% |
| Grade coverage rate | 58.3% |
| False positive rate | 3.47/district |
| Mean time/extraction | 89.4s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| Montgomery County | AL | 7 | 30 | 23.3% |  |  |
| Sweetwater County School Distr | WY | 4 | 30 | 13.3% | missing_grade_level |  |
| Essex Westford Educational Com | VT | 1 | 10 | 10.0% | false_positive, false_positive |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | extraction_error |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+30 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | extraction_error |  |
| Mobile County | AL | 0 | 10 | 0.0% | extraction_error |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | json_parse_failure | JSON failure |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, missing_grade_level |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+38 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, missing_grade_level, missing_grade_level |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 25 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 09:15-15:45 (ANNE WIEN ELEMENTARY))
  false_positive: -3 (elementary 08:00-14:30 (ARCTIC LIGHT ELEMENTARY))
  false_positive: -3 (middle 08:15-14:45 (BARNETTE MAGNET))
  false_positive: -3 (elementary 08:45-15:15 (BOREAL SUN CHARTER))
  false_positive: -3 (middle 08:15-15:15 (CHINOOK MONTESSORI CHARTER))
  false_positive: -3 (elementary 09:15-16:45 (DENALI ELEMENTARY))
  false_positive: -3 (middle 08:23-13:00 (DISCOVERY PEAK CHARTER))
  false_positive: -3 (middle 09:50-15:45 (EFFIE KOKRINE CHARTER))
  false_positive: -3 (elementary 08:00-14:30 (HUNTER ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (HUTCHISON HIGH))
  false_positive: -3 (elementary 09:15-15:45 (LADD ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (LATHROP HIGH))
  false_positive: -3 (elementary 09:00-16:30 (NORTH POLE ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (NORTH POLE HIGH))
  false_positive: -3 (middle 07:50-14:20 (NORTH POLE MIDDLE))
  false_positive: -3 (middle 07:50-14:20 (RANDY SMITH MIDDLE))
  false_positive: -3 (middle 07:50-14:20 (RYAN MIDDLE))
  false_positive: -3 (elementary 09:15-15:45 (SALCHA ELEMENTARY))
  false_positive: -3 (middle 07:55-14:25 (TANANA MIDDLE))
  false_positive: -3 (elementary 09:00-16:30 (TICASUK BROWN ELEMENTARY))
  false_positive: -3 (middle 09:15-16:45 (UNIVERSITY PARK ELEMENTARY))
  false_positive: -3 (elementary 08:30-15:00 (WATERSHED CHARTER))
  false_positive: -3 (elementary 09:15-16:45 (WELLER ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (WEST VALLEY HIGH))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '16:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))

Total: 9 (entries) + -90 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 07:12-14:15 | start=0/3 (Δ58m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 2/10
  high 07:15-14:45 → high 07:45-21:40 | start=0/3 (Δ30m) end=0/3 (Δ415m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 07:30-14:45 → middle 08:10-15:30 | start=0/3 (Δ40m) end=0/3 (Δ45m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 7 (entries) + 0 (penalties) = 7/30 (23.3%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/20 (0.0%)

======================================================================
KIPP DC PCS (DC) - 1100031
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  elementary 08:00-15:30 → elementary 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:15-15:15 → high 08:15-15:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: middle 08:00-15:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)

Total: 18 (entries) + -2 (penalties) = 16/30 (53.3%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 08:00-15:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:00-14:05 (Newark High School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 21 | Matched: 1

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: high 07:20-14:20 (unnamed) → 0/10
  MISSED: middle 09:30-16:04 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
  false_positive: -3 (elementary 08:15-15:30 (Deerwood))
  false_positive: -3 (elementary 08:45-15:00 (Eccleston))
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
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 8 (entries) + -102 (penalties) = 0/30 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 1

Entry Scores:
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 07:45-14:30 (unnamed) → 0/10
  MISSED: middle 07:30-14:15 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:15-14:15 (ABORN))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 2 (entries) + -7 (penalties) = 0/30 (0.0%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 7 | Matched: 2

Entry Scores:
  elementary 08:20-14:50 → elementary 08:25-15:10 | start=1/3 (Δ5m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 07:45-14:00 → high 07:15-14:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 07:35-14:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-14:30 (Connors))
  false_positive: -3 (elementary 08:25-15:10 (McMahon))
  false_positive: -3 (elementary 07:45-14:30 (Montello))
  false_positive: -3 (elementary 08:25-15:10 (Geiger))
  false_positive: -3 (elementary 07:15-14:00 (LMS))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:10'))
  missing_grade_level: -2 (Missing: middle)

Total: 5 (entries) + -23 (penalties) = 0/30 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 7 | Matched: 1

Entry Scores:
  high 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: elementary 08:35-15:05 (unnamed) → 0/10
  MISSED: middle 08:35-15:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:00-15:00 (Bard High School))
  false_positive: -3 (high 08:25-14:55 (Garrett Morgan School of Engineering and Innovation))
  false_positive: -3 (high 09:00-15:30 (John Adams College & Career Academy))
  false_positive: -3 (high 08:00-14:30 (John Marshall School of Science & Medicine))
  false_positive: -3 (high 09:00-15:30 (John Marshall School of Engineering at School Based Sites))
  false_positive: -3 (high 08:00-14:30 (Rhodes School of Civic & Business Leadership Environmental Studies))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 8 (entries) + -26 (penalties) = 0/30 (0.0%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:35 | start=3/3 (Δ0m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (middle 08:35-15:35 (Essex Middle School))
  false_positive: -3 (high 08:40-14:35 (Essex High School))

Total: 7 (entries) + -6 (penalties) = 1/10 (10.0%)

======================================================================
CABELL COUNTY SCHOOLS (WV) - 5400180
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  elementary 07:50-15:15 → elementary 07:45-15:00 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10
  MISSED: high 08:00-15:55 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: high)

Total: 6 (entries) + -2 (penalties) = 4/30 (13.3%)