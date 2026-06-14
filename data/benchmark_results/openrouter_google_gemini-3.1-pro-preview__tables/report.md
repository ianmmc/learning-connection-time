# Benchmark Report: openrouter:google/gemini-3.1-pro-preview
Run date: 2026-06-14T01:09:05
Districts tested: 40
Total extraction time: 946s (avg 23.7s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 20.1% |
| JSON parse success | 100.0% |
| Grade coverage rate | 64.0% |
| False positive rate | 2.55/district |
| Mean time/extraction | 23.7s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Matanuska-Susitna Borough Scho | AK | 9 | 10 | 90.0% |  |  |
| Fairbanks North Star Borough S | AK | 9 | 10 | 90.0% |  |  |
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 22 | 30 | 73.3% | false_positive, duplicate_extraction |  |
| Albany County School District  | WY | 22 | 30 | 73.3% |  |  |
| Bridgeport School District | CT | 6 | 10 | 60.0% | false_positive |  |
| LINCOLN PUBLIC SCHOOLS | NE | 6 | 10 | 60.0% | false_positive |  |
| Washoe County | NV | 5 | 10 | 50.0% | missing_grade_level |  |
| CABELL COUNTY SCHOOLS | WV | 5 | 10 | 50.0% |  |  |
| DESOTO CO SCHOOL DIST | MS | 11 | 30 | 36.7% | false_positive, duplicate_extraction, missing_grade_level |  |
| Sweetwater County School Distr | WY | 11 | 30 | 36.7% | false_positive, false_positive, false_positive (+1 more) |  |
| BERKELEY COUNTY SCHOOLS | WV | 9 | 30 | 30.0% | missing_grade_level |  |
| Champlain Valley Unified Union | VT | 2 | 10 | 20.0% |  |  |
| BROWARD | FL | 5 | 30 | 16.7% | missing_grade_level, missing_grade_level |  |
| Bangor Public Schools | ME | 5 | 30 | 16.7% | missing_grade_level, missing_grade_level |  |
| Mesa Unified District (4235) | AZ | 1 | 20 | 5.0% | false_positive |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, missing_grade_level (+2 more) |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | false_positive, missing_grade_level, missing_grade_level |  |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | extraction_error |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | missing_grade_level, missing_grade_level |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, duplicate_extraction (+3 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+36 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, duplicate_extraction (+2 more) |  |
| Cedar Rapids Comm School Distr | IA | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+9 more) |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+8 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, duplicate_extraction (+1 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | missing_grade_level, missing_grade_level |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, missing_grade_level |  |

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
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 9 (entries) + 0 (penalties) = 9/10 (90.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 6 | Matched: 1

Entry Scores:
  elementary 07:15-14:45 → elementary 07:40-14:40 | start=0/3 (Δ25m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (high 07:50-15:10 (Daphne High School))
  false_positive: -3 (middle 07:45-15:03 (Elberta Middle School))
  false_positive: -3 (high 08:00-15:15 (Fairhope High School))
  false_positive: -3 (middle 07:45-15:05 (Fairhope Middle School))
  false_positive: -3 (high 07:45-15:05 (Robertsdale High School))

Total: 3 (entries) + -15 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 9 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:15-14:45 | start=0/3 (Δ15m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:15-14:25 (Mary G Montgomery High School))
  false_positive: -3 (elementary 08:20-15:05 (Allentown Elementary School))
  false_positive: -3 (high 07:15-14:25 (Mattie T. Blount High School))
  false_positive: -3 (middle 07:15-14:20 (Causey Middle School))
  false_positive: -3 (elementary 08:15-15:15 (Collier Elementary School))
  false_positive: -3 (elementary 08:15-15:10 (Dodge Elementary School))
  false_positive: -3 (middle 07:20-14:30 (Pillans Middle School))
  false_positive: -3 (elementary 08:20-15:15 (Tanner Williams Elementary School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:15', '14:25'))

Total: 2 (entries) + -26 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 08:10-15:10 (unnamed) → 0/10
  MISSED: high 07:15-14:45 (unnamed) → 0/10
  MISSED: middle 07:30-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (unknown 07:12-14:15 (Baldwin Arts and Academic Magnet))
  false_positive: -3 (unknown 08:10-15:30 (Bear))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 0 (entries) + -12 (penalties) = 0/30 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:45-16:00 → high 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:45-16:00 → middle 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 07:40-14:55 (K-8 Schools))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:55'))

Total: 27 (entries) + -5 (penalties) = 22/30 (73.3%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 2

Entry Scores:
  middle 08:05-15:30 → middle 08:05-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:05-15:30 → elementary 07:45-15:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-15:10 (Harp Elementary))
  false_positive: -3 (elementary 07:45-15:10 (Bayyari Elementary))
  false_positive: -3 (middle 08:05-15:30 (Sonora Middle School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:05', '15:30'))
  missing_grade_level: -2 (Missing: high)

Total: 11 (entries) + -17 (penalties) = 0/30 (0.0%)

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
Ground truth: 2 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: high 08:30-15:15 (unnamed) → 0/10
  MISSED: middle 08:50-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:20-14:45 (Borton Elementary School))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 0 (entries) + -7 (penalties) = 0/20 (0.0%)

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
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 08:30-14:05 → elementary 08:00-14:05 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 09:00-13:54 (Conley-Caraballo High School))
  false_positive: -3 (middle 08:15-14:44 (César Chávez Middle School))
  false_positive: -3 (elementary 08:00-14:05 (Delaine Eastin Elementary School))
  false_positive: -3 (elementary 08:00-14:05 (Searles Elementary School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))

Total: 5 (entries) + -16 (penalties) = 0/10 (0.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:50-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:25-14:55 (Blackham))

Total: 9 (entries) + -3 (penalties) = 6/10 (60.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high 07:20-13:50 → high 07:30-14:05 | start=0/3 (Δ10m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: elementary 08:45-15:00 (unnamed) → 0/10
  MISSED: middle 07:50-14:20 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 2 (entries) + -4 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 07:20-13:50 → high 07:20-13:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: elementary 08:35-14:50 (unnamed) → 0/10
  MISSED: middle 07:50-14:20 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:20-13:50 (Kennedy))
  false_positive: -3 (high 07:20-13:50 (Wtby Arts Magnet))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 9 (entries) + -14 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 23 | Matched: 1

Entry Scores:
  high 07:30-14:30 → high 08:20-15:00 | start=0/3 (Δ50m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:20-15:00 (Middletown HS))
  false_positive: -3 (high 08:20-15:00 (Odessa HS))
  false_positive: -3 (high 08:20-15:00 (Special Program MS/HS))
  false_positive: -3 (middle 07:30-14:10 (Everett Meredith MS))
  false_positive: -3 (middle 07:30-14:10 (Louis L. Redding MS))
  false_positive: -3 (middle 07:30-14:10 (Alfred G. Waters MS))
  false_positive: -3 (middle 07:30-14:10 (Cantwell’s Bridge MS))
  false_positive: -3 (elementary 09:10-15:50 (Brick Mill ES/ECC))
  false_positive: -3 (elementary 09:10-15:50 (Bunker Hill ES))
  false_positive: -3 (elementary 09:10-15:50 (Cedar Lane ES/ECC))
  false_positive: -3 (elementary 09:10-15:50 (Lorewood Grove ES))
  false_positive: -3 (elementary 09:10-15:50 (Crystal Run ES))
  false_positive: -3 (elementary 09:10-15:50 (Old State ES & Spring Meadow ECC))
  false_positive: -3 (elementary 09:10-15:50 (Olive B. Loss ES))
  false_positive: -3 (elementary 09:10-15:50 (Silver Lake ES))
  false_positive: -3 (elementary 09:10-15:50 (Townsend ES/ECC))
  false_positive: -3 (pre-k 09:10-11:40 (Appoquinimink Preschool AM))
  false_positive: -3 (pre-k 12:55-15:10 (Appoquinimink Preschool PM))
  false_positive: -3 (pre-k 09:10-15:10 (Appoquinimink Preschool Full))
  false_positive: -3 (pre-k 09:10-11:40 (Brick Mill ECC AM))
  false_positive: -3 (pre-k 12:55-15:10 (Brick Mill ECC PM))
  false_positive: -3 (pre-k 09:10-15:10 (Brick Mill ECC 4’s))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('pre-k', '09:10', '11:40'))
  duplicate_extraction: -2 (Duplicate: ('pre-k', '12:55', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('pre-k', '09:10', '15:10'))

Total: 2 (entries) + -100 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:00-14:00 → elementary 08:00-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 07:40-14:40 (unnamed) → 0/10
  MISSED: middle 09:30-16:10 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 9 (entries) + -4 (penalties) = 5/30 (16.7%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 07:20-14:20 (unnamed) → 0/10
  MISSED: middle 09:30-16:04 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 9 (entries) + -12 (penalties) = 0/30 (0.0%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 7 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:50 (High School))
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
Ground truth: 3 entries | Extracted: 6 | Matched: 1

Entry Scores:
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 07:45-14:30 (unnamed) → 0/10
  MISSED: middle 07:30-14:15 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-13:45 (DREWICZ))
  false_positive: -3 (elementary 07:45-13:45 (EARLY CHILDHOOD CENTER))
  false_positive: -3 (elementary 07:45-13:45 (FALLON))
  false_positive: -3 (elementary 07:45-13:45 (FORD))
  false_positive: -3 (elementary 07:45-13:45 (HARRINGTON))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 2 (entries) + -29 (penalties) = 0/30 (0.0%)

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
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:55-15:00 → elementary 08:55-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 08:00-14:00 (unnamed) → 0/10
  MISSED: middle 08:15-14:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 9 (entries) + -4 (penalties) = 5/30 (16.7%)

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
Ground truth: 3 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 08:30-15:25 → elementary 08:30-15:25 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:40 → middle 08:00-15:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 08:25-15:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:30-15:25 (Overpark Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  missing_grade_level: -2 (Missing: high)

Total: 18 (entries) + -7 (penalties) = 11/30 (36.7%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:00-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 08:00-15:05 (Lincoln High))

Total: 9 (entries) + -3 (penalties) = 6/10 (60.0%)

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
Ground truth: 1 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 08:00-14:30 (unnamed) → 0/10

Penalties:
  false_positive: -3 (unknown 07:40-14:10 (AWL))
  false_positive: -3 (unknown 07:40-14:10 (Rockdale Academy))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:40', '14:10'))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -10 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:35-15:05 → elementary 09:35-16:05 | start=0/3 (Δ60m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:35-15:05 (unnamed) → 0/10
  MISSED: middle 08:35-15:05 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 2 (entries) + -4 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 08:00-14:43 | start=0/3 (Δ10m) end=0/3 (Δ58m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 2 (entries) + 0 (penalties) = 2/10 (20.0%)

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
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  middle 07:27-15:06 → middle 07:15-15:06 | start=0/3 (Δ12m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Total: 5 (entries) + 0 (penalties) = 5/10 (50.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 07:15-14:15 (unnamed) → 0/10

Penalties:
  false_positive: -3 (middle 07:30-14:38 (Horace Mann Middle School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Albany County School District #1 (WY) - 5600730
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  middle 08:00-15:05 → middle 08:00-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:02-15:00 → elementary 07:59-15:00 | start=1/3 (Δ3m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10
  high 07:45-15:45 → high 07:45-16:45 | start=3/3 (Δ0m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=1/1 = 6/10

Total: 22 (entries) + 0 (penalties) = 22/30 (73.3%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 7 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 07:45-14:45 (Overland Elementary School))
  false_positive: -3 (elementary 08:00-15:15 (4 - 6 Elementary Schools))
  false_positive: -3 (elementary 07:45-15:00 (Elementary School))
  false_positive: -3 (middle 07:45-16:05 (Middle School))

Total: 23 (entries) + -12 (penalties) = 11/30 (36.7%)