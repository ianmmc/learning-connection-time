# Benchmark Report: openrouter:google/gemini-3.5-flash
Run date: 2026-06-14T00:53:18
Districts tested: 40
Total extraction time: 744s (avg 18.6s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 20.9% |
| JSON parse success | 77.5% |
| Grade coverage rate | 73.3% |
| False positive rate | 1.52/district |
| Mean time/extraction | 18.6s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Matanuska-Susitna Borough Scho | AK | 9 | 10 | 90.0% |  |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 27 | 30 | 90.0% |  |  |
| Bridgeport School District | CT | 9 | 10 | 90.0% |  |  |
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| Albany County School District  | WY | 24 | 30 | 80.0% |  |  |
| Bangor Public Schools | ME | 22 | 30 | 73.3% | false_positive |  |
| New Haven Unified | CA | 5 | 10 | 50.0% |  |  |
| Washoe County | NV | 5 | 10 | 50.0% | missing_grade_level |  |
| LINCOLN PUBLIC SCHOOLS | NE | 4 | 10 | 40.0% | false_positive |  |
| BERKELEY COUNTY SCHOOLS | WV | 9 | 30 | 30.0% | missing_grade_level |  |
| Tucson Unified District (4403) | AZ | 5 | 20 | 25.0% | false_positive, false_positive |  |
| Montgomery County | AL | 5 | 30 | 16.7% | missing_grade_level, missing_grade_level |  |
| Waterbury School District | CT | 5 | 30 | 16.7% | missing_grade_level, missing_grade_level |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 4 | 30 | 13.3% | false_positive, duplicate_extraction, missing_grade_level |  |
| Mesa Unified District (4235) | AZ | 1 | 20 | 5.0% | false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Baldwin County | AL | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Mobile County | AL | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | extraction_error |  |
| New Haven School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, duplicate_extraction (+1 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| BROWARD | FL | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| ORANGE | FL | 0 | 30 | 0.0% | missing_grade_level, missing_grade_level |  |
| Cedar Rapids Comm School Distr | IA | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, duplicate_extraction, missing_grade_level (+1 more) |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+8 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | false_positive, duplicate_extraction, missing_grade_level (+1 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+14 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Sweetwater County School Distr | WY | 0 | 30 | 0.0% | json_parse_failure | JSON failure |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 9 (entries) + 0 (penalties) = 9/10 (90.0%)

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
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

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
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 07:15-14:45 (unnamed) → 0/10
  MISSED: middle 07:30-14:45 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 9 (entries) + -4 (penalties) = 5/30 (16.7%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:45-16:00 → high 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:45-16:00 → middle 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 27 (entries) + 0 (penalties) = 27/30 (90.0%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 2

Entry Scores:
  middle 08:05-15:30 → middle 08:05-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:05-15:30 → elementary 07:45-15:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-15:10 (Harp Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:10'))
  missing_grade_level: -2 (Missing: high)

Total: 11 (entries) + -7 (penalties) = 4/30 (13.3%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 07:50-13:50 → elementary 08:15-14:45 | start=0/3 (Δ25m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 08:00-14:45 → middle 07:30-14:15 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:15-15:15 (Red Mtn. High School))

Total: 4 (entries) + -3 (penalties) = 1/20 (5.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 4 | Matched: 2

Entry Scores:
  middle 08:50-15:50 → middle 08:50-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:30-15:15 → high 08:05-15:21 | start=0/3 (Δ25m) end=0/3 (Δ6m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:20-14:45 (Borton Elementary School))
  false_positive: -3 (high 08:00-15:01 (Pueblo High School))

Total: 11 (entries) + -6 (penalties) = 5/20 (25.0%)

======================================================================
Los Angeles Unified (CA) - 0622710
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
New Haven Unified (CA) - 0626910
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:30-14:05 → elementary 08:00-14:05 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Total: 5 (entries) + 0 (penalties) = 5/10 (50.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:50-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 9 (entries) + 0 (penalties) = 9/10 (90.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 2

Entry Scores:
  high 07:20-13:50 → high 07:30-14:05 | start=0/3 (Δ10m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  elementary 08:45-15:00 → elementary 08:30-16:00 | start=0/3 (Δ15m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 07:50-14:20 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:10-14:05 (Cross High School))
  false_positive: -3 (high 07:10-14:05 (Hillhouse High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:10', '14:05'))
  missing_grade_level: -2 (Missing: middle)

Total: 4 (entries) + -10 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high 07:20-13:50 → high 07:20-13:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: elementary 08:35-14:50 (unnamed) → 0/10
  MISSED: middle 07:50-14:20 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 9 (entries) + -4 (penalties) = 5/30 (16.7%)

======================================================================
KIPP DC PCS (DC) - 1100031
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:00-15:30 → elementary 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:15-15:15 → high 08:15-15:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:30 → middle 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 27 (entries) + 0 (penalties) = 27/30 (90.0%)

======================================================================
Appoquinimink School District (DE) - 1000080
======================================================================
Ground truth: 1 entries | Extracted: 6 | Matched: 1

Entry Scores:
  high 07:30-14:30 → high 08:20-15:00 | start=0/3 (Δ50m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:20-15:00 (Middletown HS))
  false_positive: -3 (high 08:20-15:00 (Odessa HS))
  false_positive: -3 (high 08:20-15:00 (Special Program MS/HS))
  false_positive: -3 (middle 07:30-14:10 (Everett Meredith MS))
  false_positive: -3 (middle 07:30-14:10 (Louis L. Redding MS))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:10'))

Total: 2 (entries) + -23 (penalties) = 0/10 (0.0%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 08:00-15:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (middle 07:05-14:05 (Shue-Medill Middle School))
  false_positive: -3 (high 07:20-14:05 (Newark High School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -8 (penalties) = 0/10 (0.0%)

======================================================================
Red Clay Consolidated School District (DE) - 1001300
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 0

Entry Scores:
  MISSED: elementary 09:05-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:25-14:10 (McKean High School))
  false_positive: -3 (high 07:25-14:10 (Alexis I du Pont High School))
  false_positive: -3 (high 07:25-14:10 (John Dickinson High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:25', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:25', '14:10'))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -15 (penalties) = 0/10 (0.0%)

======================================================================
BROWARD (FL) - 1200180
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
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:45-15:00 → elementary 08:15-15:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 07:20-14:20 (unnamed) → 0/10
  MISSED: middle 09:30-16:04 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 2 (entries) + -4 (penalties) = 0/30 (0.0%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 7 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:50 (Cedar Rapids High Schools))
  false_positive: -3 (middle 07:50-14:50 (Franklin Middle School))
  false_positive: -3 (high 07:50-14:50 (Washington High School))
  false_positive: -3 (elementary 08:50-15:50 (Wright Elementary School))
  false_positive: -3 (high 07:50-15:00 (Metro High School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:50', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:50'))

Total: 10 (entries) + -21 (penalties) = 0/20 (0.0%)

======================================================================
Des Moines Independent Comm School District (IA) - 1908970
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:15-15:15 → elementary 07:40-14:35 | start=0/3 (Δ35m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:15-15:15 (All High Schools))
  false_positive: -3 (middle 08:30-15:25 (All Middle Schools))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
BONNEVILLE JOINT DISTRICT (ID) - 1600930
======================================================================
Ground truth: 1 entries | Extracted: 6 | Matched: 1

Entry Scores:
  high 08:40-15:48 → high 08:40-15:48 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 08:40-15:54 (Hillcrest High School))
  false_positive: -3 (high 08:00-14:45 (Lincoln High School))
  false_positive: -3 (middle 08:40-15:45 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))
  false_positive: -3 (high 08:40-15:48 (Thunder Ridge High School))
  duplicate_extraction: -2 (Duplicate: ('high', '08:40', '15:48'))

Total: 9 (entries) + -17 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 1

Entry Scores:
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 07:45-14:30 (unnamed) → 0/10
  MISSED: middle 07:30-14:15 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-13:45 (Drewicz))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 2 (entries) + -9 (penalties) = 0/30 (0.0%)

======================================================================
Worcester (MA) - 2513230
======================================================================
Ground truth: 1 entries | Extracted: 8 | Matched: 1

Entry Scores:
  middle 08:47-14:17 → middle 08:47-15:10 | start=3/3 (Δ0m) end=0/3 (Δ53m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:20-13:43 (Burncoat High School))
  false_positive: -3 (high 07:20-13:43 (North High School))
  false_positive: -3 (high 07:20-13:43 (Worcester Technical High School))
  false_positive: -3 (elementary 08:15-14:20 (Belmont Street Community School))
  false_positive: -3 (elementary 07:55-14:00 (Elm Park Community School))
  false_positive: -3 (elementary 08:25-14:30 (Grafton Street School))
  false_positive: -3 (elementary 08:25-14:30 (May Street School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '14:30'))

Total: 5 (entries) + -27 (penalties) = 0/10 (0.0%)

======================================================================
Bangor Public Schools (ME) - 2302820
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  elementary 08:55-15:00 → elementary 08:55-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:15-14:30 → middle 08:15-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:00-14:00 → high 07:55-14:00 | start=1/3 (Δ5m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (elementary 08:50-15:00 (Bangor School Department (Grades 4-5)))

Total: 25 (entries) + -3 (penalties) = 22/30 (73.3%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 9 | Matched: 3

Entry Scores:
  high 07:45-14:00 → high 07:45-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:35-14:00 → middle 07:35-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:20-14:50 → elementary 08:40-15:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:00-14:30 (Connors))
  false_positive: -3 (elementary 08:40-15:10 (McMahon))
  false_positive: -3 (elementary 08:00-14:30 (Montello))
  false_positive: -3 (elementary 08:40-15:10 (Geiger))
  false_positive: -3 (high 07:45-14:00 (LRTC))
  false_positive: -3 (high 07:45-14:00 (Next STEP))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:40', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:40', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:00'))

Total: 20 (entries) + -28 (penalties) = 0/30 (0.0%)

======================================================================
DESOTO CO SCHOOL DIST (MS) - 2801320
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 1

Entry Scores:
  elementary 08:30-15:25 → elementary 08:30-15:25 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 08:25-15:45 (unnamed) → 0/10
  MISSED: middle 08:00-15:40 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:30-15:25 (Overpark Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 9 (entries) + -9 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:00-15:05 | start=3/3 (Δ0m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Culler Middle School))

Total: 7 (entries) + -3 (penalties) = 4/10 (40.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 07:26-14:00 → high 07:26-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

Penalties:
  missing_grade_level: -2 (Missing: elementary)

Total: 7 (entries) + -2 (penalties) = 5/10 (50.0%)

======================================================================
Cincinnati Public Schools (OH) - 3904375
======================================================================
Ground truth: 1 entries | Extracted: 11 | Matched: 1

Entry Scores:
  elementary 08:00-14:30 → elementary 07:40-14:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:40-14:10 (Rockdale Academy))
  false_positive: -3 (elementary 09:10-15:40 (Roselawn Condon School))
  false_positive: -3 (elementary 07:40-14:10 (CANS (Clifton Area Neighborhood School)))
  false_positive: -3 (high 08:00-15:00 (Dr. O'dell Owens Center for Learning))
  false_positive: -3 (elementary 09:10-15:40 (James N. Gamble Montessori Elementary School))
  false_positive: -3 (elementary 09:10-15:40 (North Avondale Montessori School))
  false_positive: -3 (elementary 07:40-14:10 (Roll Hill School))
  false_positive: -3 (elementary 09:10-15:40 (Roberts Academy))
  false_positive: -3 (high 08:00-15:00 (James N. Gamble Montessori High School))
  false_positive: -3 (middle 08:00-15:00 (Pleasant Hill Middle School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))

Total: 2 (entries) + -44 (penalties) = 0/10 (0.0%)

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
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 08:40-15:15 (Essex High School))
  false_positive: -3 (middle 08:35-15:35 (Essex Middle School))
  false_positive: -3 (elementary 07:30-14:30 (Westford School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))

Total: 9 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Champlain Valley Unified Union School District #56 (VT) - 5000396
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:08-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:10-14:50 (Edmunds Elementary))
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle School))
  false_positive: -3 (middle 08:00-15:00 (Hunt Middle School))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))

Total: 9 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
BERKELEY COUNTY SCHOOLS (WV) - 5400060
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  high 07:28-14:38 → high 07:28-14:38 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:55-15:30 → elementary 08:45-15:20 | start=0/3 (Δ50m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 07:30-14:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)

Total: 11 (entries) + -2 (penalties) = 9/30 (30.0%)

======================================================================
CABELL COUNTY SCHOOLS (WV) - 5400180
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

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
Albany County School District #1 (WY) - 5600730
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:02-15:00 → elementary 08:02-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:05 → middle 08:00-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:45-15:45 → high 07:45-16:45 | start=3/3 (Δ0m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=1/1 = 6/10

Total: 24 (entries) + 0 (penalties) = 24/30 (80.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)