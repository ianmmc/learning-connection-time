# Benchmark Report: ollama:llama3.1:8b
Run date: 2026-06-13T03:41:15
Districts tested: 17
Total extraction time: 14480s (avg 851.8s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 10.0% |
| JSON parse success | 88.2% |
| Grade coverage rate | 71.4% |
| False positive rate | 7.06/district |
| Mean time/extraction | 851.8s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| Essex Westford Educational Com | VT | 3 | 10 | 30.0% | false_positive, false_positive |  |
| Sweetwater County School Distr | WY | 7 | 30 | 23.3% | false_positive, missing_grade_level |  |
| Lewiston Public Schools | ME | 6 | 30 | 20.0% | missing_grade_level |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | extraction_error |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+27 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | extraction_error |  |
| Mobile County | AL | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+10 more) |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+87 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, false_positive |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+34 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+8 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | extraction_error |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+33 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 20 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 08:00-14:30 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:00 (HUTCHISON HIGH))
  false_positive: -3 (high 07:30-14:00 (LATHROP HIGH))
  false_positive: -3 (high 07:30-14:00 (NORTH POLE HIGH))
  false_positive: -3 (high 07:30-14:00 (W E S T V A L L E Y H I G H))
  false_positive: -3 (middle 07:50-14:20 (RANDY SMITH MIDDLE))
  false_positive: -3 (middle 07:50-14:20 (RYAN MIDDLE))
  false_positive: -3 (middle 07:55-14:25 (TANANA MIDDLE))
  false_positive: -3 (elementary 08:00-14:30 (HUNTER ELEMENTARY))
  false_positive: -3 (elementary 09:00-15:30 (TICASUK BROWN ELEMENTARY))
  false_positive: -3 (elementary 09:00-15:30 (UNIVERSITY PARK ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (ANNE WIEN ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (DENALI ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (LADD ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (SALCHA ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (UNIVERSITY PARK ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (WELLER ELEMENTARY))
  false_positive: -3 (elementary 09:30-15:00 (BARNETTE MAGNET))
  false_positive: -3 (elementary 08:45-15:15 (BOREAL SUN CHARTER))
  false_positive: -3 (elementary 08:30-15:00 (WATERSHED CHARTER))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))

Total: 2 (entries) + -79 (penalties) = 0/10 (0.0%)

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
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 8 | Matched: 2

Entry Scores:
  middle 07:30-14:45 → middle 07:30-15:00 | start=3/3 (Δ0m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:15-14:45 → high 08:10-14:35 | start=0/3 (Δ55m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: elementary 08:10-15:10 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:10-14:35 (G.W. Carver High School))
  false_positive: -3 (middle 07:30-15:00 (Goodwyn Middle School))
  false_positive: -3 (high 08:10-14:35 (Lanier High School))
  false_positive: -3 (middle 07:30-15:00 (McKee Middle School))
  false_positive: -3 (high 08:10-14:35 (Park Crossing Highschool))
  false_positive: -3 (middle 07:30-15:00 (Southlawn Middle))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '15:00'))
  missing_grade_level: -2 (Missing: elementary)

Total: 7 (entries) + -32 (penalties) = 0/30 (0.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 47 | Matched: 0

Entry Scores:
  MISSED: high 08:30-15:15 (unnamed) → 0/10
  MISSED: middle 08:50-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-08:58 (None))
  false_positive: -3 (unknown 09:03-09:56 (None))
  false_positive: -3 (unknown 10:01-10:54 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 09:46-11:20 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 08:05-09:39 (None))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  duplicate_extraction: -2 (Duplicate: ('unknown', '08:05', '09:39'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 0 (entries) + -227 (penalties) = 0/20 (0.0%)

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
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:00-15:00 → elementary 07:05-14:35 | start=0/3 (Δ55m) end=0/3 (Δ25m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 07:05-14:35 (Shue-Medill Middle School))
  false_positive: -3 (high 07:20-14:38 (Newark High School))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 22 | Matched: 3

Entry Scores:
  high 07:20-14:20 → high 07:10-14:10 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  elementary 08:45-15:00 → elementary 08:15-15:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 09:30-16:04 → middle 08:45-13:00 | start=0/3 (Δ45m) end=0/3 (Δ184m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
  false_positive: -3 (middle 08:45-13:00 (Deerwood))
  false_positive: -3 (elementary 08:15-15:30 (Eccleston))
  false_positive: -3 (elementary 08:15-15:30 (Orlo Vista))
  false_positive: -3 (elementary 08:15-15:30 (Engelwood))
  false_positive: -3 (elementary 08:15-15:30 (Hiawassee))
  false_positive: -3 (middle 08:15-15:30 (OCPS Academic Center for Excellence K-8))
  false_positive: -3 (elementary 08:15-15:30 (Orange Center))
  false_positive: -3 (elementary 08:15-15:30 (Ivey Lane))
  false_positive: -3 (elementary 08:15-15:30 (Ridgewood Park))
  false_positive: -3 (elementary 08:15-15:30 (Washington Shores))
  false_positive: -3 (elementary 08:15-15:30 (Rock Lake))
  false_positive: -3 (elementary 08:15-15:30 (Rolling Hills))
  false_positive: -3 (elementary 08:15-15:30 (Rosemont))
  false_positive: -3 (middle 08:15-15:30 (Shingle Creek))
  false_positive: -3 (elementary 08:15-15:30 (Wheatley))
  false_positive: -3 (elementary 08:15-15:30 (Tangelo Park))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:45', '13:00'))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))

Total: 7 (entries) + -93 (penalties) = 0/30 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 10 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-14:15 (Aborn))
  false_positive: -3 (middle 07:45-14:05 (Harold Durgin Success Academy))
  false_positive: -3 (middle 07:45-14:30 (City Arts & Sciences Academy (CASA)))
  false_positive: -3 (middle 07:45-14:30 (Discovery Academy))
  false_positive: -3 (middle 07:45-14:30 (Frederick Douglass Collegiate Academy))
  false_positive: -3 (middle 07:45-14:30 (Thurgood Marshall Middle School))
  false_positive: -3 (high 07:45-14:30 (Lynn English High School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))

Total: 20 (entries) + -29 (penalties) = 0/30 (0.0%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  middle 07:35-14:00 → middle 07:35-17:15 | start=3/3 (Δ0m) end=0/3 (Δ195m) grade=2/2 name=0/1 conf=1/1 = 6/10
  high 07:45-14:00 → high 07:15-14:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: elementary 08:20-14:50 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: elementary)

Total: 8 (entries) + -2 (penalties) = 6/30 (20.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 20 | Matched: 3

Entry Scores:
  high 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  elementary 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=0/1 = 6/10
  middle 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=0/1 = 6/10

Penalties:
  false_positive: -3 (high 08:00-14:30 (Bard High School))
  false_positive: -3 (high 08:25-15:55 (Garrett Morgan School of))
  false_positive: -3 (high 08:35-15:05 (Ginn Academy))
  false_positive: -3 (high 08:35-15:05 (Natividad Pagan International))
  false_positive: -3 (high 08:35-15:05 (Glenville High School))
  false_positive: -3 (high 08:00-14:30 (Cleveland Early CollegeH.S.))
  false_positive: -3 (high 08:00-14:30 (Cleveland H.S. for Digital Arts))
  false_positive: -3 (high 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (high 08:00-14:30 (Newcomers Academy))
  false_positive: -3 (high 08:00-14:30 (John Adams College & Architecture & Design Career Academy))
  false_positive: -3 (high 08:00-14:30 (Cleveland School of Science & Medicine))
  false_positive: -3 (high 08:00-14:30 (John Marshall School of Civic & Business Leadership Environmental Studies))
  false_positive: -3 (high 08:00-14:30 (Collinwood High School))
  false_positive: -3 (high 08:35-15:05 (Davis Aerospace & Maritime Engineering at School Based Sites))
  false_positive: -3 (high 08:00-14:30 (East Technical High School))
  false_positive: -3 (high 08:35-15:05 (Facing History New Tech))
  false_positive: -3 (high 08:35-15:05 (Lincoln-West School of Global Studies))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: elementary)

Total: 20 (entries) + -89 (penalties) = 0/30 (0.0%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 08:40-15:15 (Essex High School))
  false_positive: -3 (middle 08:35-15:15 (Essex Middle School))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

======================================================================
CABELL COUNTY SCHOOLS (WV) - 5400180
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 2

Entry Scores:
  middle 08:30-15:50 → middle 08:30-15:55 | start=3/3 (Δ0m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=1/1 = 7/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10
  MISSED: high 08:00-15:55 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-15:00 (Elementary School))
  missing_grade_level: -2 (Missing: high)

Total: 12 (entries) + -5 (penalties) = 7/30 (23.3%)