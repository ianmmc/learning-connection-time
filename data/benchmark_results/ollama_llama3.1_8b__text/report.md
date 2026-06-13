# Benchmark Report: ollama:llama3.1:8b
Run date: 2026-06-12T03:49:38
Districts tested: 40
Total extraction time: 7154s (avg 178.9s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 10.5% |
| JSON parse success | 95.0% |
| Grade coverage rate | 66.2% |
| False positive rate | 3.45/district |
| Mean time/extraction | 178.9s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| Albany County School District  | WY | 15 | 30 | 50.0% |  |  |
| Cedar Rapids Comm School Distr | IA | 7 | 20 | 35.0% | false_positive |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 10 | 30 | 33.3% | missing_grade_level |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 10 | 30 | 33.3% | duplicate_extraction, missing_grade_level, missing_grade_level |  |
| Bangor Public Schools | ME | 9 | 30 | 30.0% | false_positive |  |
| Essex Westford Educational Com | VT | 3 | 10 | 30.0% | false_positive, false_positive |  |
| Lewiston Public Schools | ME | 6 | 30 | 20.0% | missing_grade_level |  |
| Sweetwater County School Distr | WY | 3 | 30 | 10.0% | false_positive, false_positive, duplicate_extraction |  |
| ORANGE | FL | 2 | 30 | 6.7% | false_positive, missing_grade_level, missing_grade_level |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| Mesa Unified District (4235) | AZ | 0 | 20 | 0.0% | false_positive, missing_grade_level, missing_grade_level |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | extraction_error |  |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | extraction_error |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+10 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+48 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+25 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, missing_grade_level |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, missing_grade_level |  |
| BROWARD | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive |  |
| Washoe County | NV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+31 more) |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| BERKELEY COUNTY SCHOOLS | WV | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-14:35 | start=3/3 (Δ0m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 10:15-15:45 (Big Lake Elementary School))
  false_positive: -3 (middle 07:45-14:35 (Teeland Middle School))

Total: 5 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 0

Entry Scores:
  MISSED: elementary 07:40-14:10 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:30-14:00 (HUTCHISON HIGH))
  false_positive: -3 (high 07:30-14:00 (LATHROP HIGH))
  false_positive: -3 (high 07:30-14:00 (NORTH POLE HIGH))
  false_positive: -3 (high 07:30-14:00 (W E S T   V A L L E Y   H I G H))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -20 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 0

Entry Scores:
  MISSED: elementary 07:15-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:00-15:15 (Baldwin County High School))
  false_positive: -3 (middle 07:45-14:50 (Daphne Middle School))
  false_positive: -3 (high 08:40-15:10 (Fairhope High School))
  false_positive: -3 (middle 07:45-14:50 (Spanish Fort Middle School))
  false_positive: -3 (middle 08:53-15:03 (Elberta Middle School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:50'))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -19 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:10-15:00 | start=0/3 (Δ10m) end=0/3 (Δ35m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:15-14:35 (Mary G Montgomery High School))
  false_positive: -3 (middle 06:50-14:20 (Pillans Middle School))
  false_positive: -3 (elementary 07:45-15:00 (Holloway Elementary School))
  false_positive: -3 (elementary 06:30-14:35 (Allentown Elementary School))

Total: 2 (entries) + -12 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 9 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:00 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:15-14:45 → high 07:25-14:35 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 07:30-14:45 → middle 08:40-15:00 | start=0/3 (Δ70m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:35 (Brew Tech))
  false_positive: -3 (elementary 07:30-14:30 (Morningview Elementary School))
  false_positive: -3 (middle 08:10-15:00 (McKee Middle School))
  false_positive: -3 (high 07:45-14:35 (G.W. Carver High School))
  false_positive: -3 (high 07:30-14:35 (Park Crossing Highschool))
  false_positive: -3 (middle 08:40-15:00 (Southlawn Middle))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:40', '15:00'))

Total: 9 (entries) + -22 (penalties) = 0/30 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  high 08:45-16:00 → high 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 08:45-16:00 → middle 07:40-15:55 | start=0/3 (Δ65m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=1/1 = 4/10
  MISSED: elementary 07:40-14:55 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: elementary)

Total: 12 (entries) + -2 (penalties) = 10/30 (33.3%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  middle 08:05-15:30 → middle 08:05-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:05-15:30 → middle 08:05-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  duplicate_extraction: -2 (Duplicate: ('middle', '08:05', '15:30'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: elementary)

Total: 16 (entries) + -6 (penalties) = 10/30 (33.3%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 07:50-13:50 (unnamed) → 0/10
  MISSED: middle 08:00-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:15-14:35 (Red Mtn. High School))
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 0 (entries) + -7 (penalties) = 0/20 (0.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/20 (0.0%)

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
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 08:30-14:05 → elementary 08:00-12:05 | start=0/3 (Δ30m) end=0/3 (Δ120m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 08:00-12:05 (Searles Elementary School))
  false_positive: -3 (middle 08:15-14:44 (César Chávez Middle School))
  false_positive: -3 (high 08:00-14:35 (Conley-Caraballo High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '12:05'))

Total: 3 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 7 | Matched: 0

Entry Scores:
  MISSED: elementary 08:50-15:10 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:53-14:30 (Bassick))
  false_positive: -3 (high 07:53-14:30 (Central))
  false_positive: -3 (high 07:53-14:30 (Harding))
  false_positive: -3 (high 08:15-14:00 (Brpt. Learning Ctr.))
  false_positive: -3 (high 07:50-12:05 (Fairchild Wheeler))
  false_positive: -3 (high 07:55-14:10 (Bpt. Military Academy))
  false_positive: -3 (high 08:00-12:05 (Aquaculture))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -27 (penalties) = 0/10 (0.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 11 | Matched: 2

Entry Scores:
  high 07:20-13:50 → high 07:30-14:00 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  elementary 08:45-15:00 → elementary 08:35-15:50 | start=0/3 (Δ10m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 07:50-14:20 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:30-14:35 (Cooperative Arts and Humanities Magnet High School))
  false_positive: -3 (high 07:10-14:05 (New Haven Academy))
  false_positive: -3 (high 07:30-14:17 (Sound School))
  false_positive: -3 (high 07:10-14:05 (HSC HS))
  false_positive: -3 (high 07:30-12:00 (Common Ground))
  false_positive: -3 (elementary 09:15-15:30 (John Martinez))
  false_positive: -3 (elementary 09:15-15:30 (Jepson))
  false_positive: -3 (elementary 07:45-14:15 (John Daniels))
  false_positive: -3 (elementary 08:35-15:50 (Nathaniel Hawthorne))
  duplicate_extraction: -2 (Duplicate: ('high', '07:10', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:50'))
  missing_grade_level: -2 (Missing: middle)

Total: 4 (entries) + -35 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 30 | Matched: 3

Entry Scores:
  elementary 08:35-14:50 → elementary 08:35-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-13:50 → high 07:20-13:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:50-14:20 → middle 07:50-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 07:20-13:50 (Kennedy High))
  false_positive: -3 (high 07:20-13:50 (Wtby Arts Magnet High))
  false_positive: -3 (high 07:20-13:50 (Wtby Career Academy High))
  false_positive: -3 (high 07:20-13:50 (Wilby High))
  false_positive: -3 (middle 07:50-14:20 (Wallace Middle))
  false_positive: -3 (middle 07:20-13:50 (Wtby Arts Magnet Middle))
  false_positive: -3 (middle 07:50-14:20 (West Side Middle))
  false_positive: -3 (elementary 08:35-14:50 (Bunker Hill Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Carrington Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Chase Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Cross, Wendell Elementary))
  false_positive: -3 (elementary 08:05-12:20 (Driggs Elementary))
  false_positive: -3 (elementary 08:05-12:20 (Duggan Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Generali Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Gilmartin Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Hopeville Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Kingsbury Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Maloney Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Reed Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Regan Elementary))
  false_positive: -3 (elementary 09:05-15:20 (Roberto Clemente Elementary))
  false_positive: -3 (elementary 09:05-15:20 (Rotella Elementary))
  false_positive: -3 (elementary 08:05-12:20 (Sprague Elementary))
  false_positive: -3 (elementary 08:05-12:20 (Tinker Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Walsh Elementary))
  false_positive: -3 (elementary 08:05-12:20 (Washington Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Wilson Elementary))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '12:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '12:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '12:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '12:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))

Total: 27 (entries) + -129 (penalties) = 0/30 (0.0%)

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
Appoquinimink School District (DE) - 1000080
======================================================================
Ground truth: 1 entries | Extracted: 16 | Matched: 1

Entry Scores:
  high 07:30-14:30 → high 08:20-15:00 | start=0/3 (Δ50m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:20-15:00 (Middletown HS))
  false_positive: -3 (high 08:20-15:00 (Odessa HS))
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

Total: 2 (entries) + -71 (penalties) = 0/10 (0.0%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 08:00-15:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:20-14:48 (Newark High School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Red Clay Consolidated School District (DE) - 1001300
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 09:05-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:25-14:35 (McKean High School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
BROWARD (FL) - 1200180
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 1

Entry Scores:
  high 07:40-14:40 → high 07:40-14:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: elementary 08:00-14:00 (unnamed) → 0/10
  MISSED: middle 09:30-16:10 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:40-14:40 (Taravella, J.P. High))
  false_positive: -3 (high 07:40-14:40 (West Broward High))
  false_positive: -3 (high 07:40-14:40 (Western High))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 8 (entries) + -19 (penalties) = 0/30 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 1

Entry Scores:
  high 07:20-14:20 → high 07:20-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: elementary 08:45-15:00 (unnamed) → 0/10
  MISSED: middle 09:30-16:04 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:10-12:54 (Colonial 9th Gr. Ctr.))
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 9 (entries) + -7 (penalties) = 2/30 (6.7%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:20 (Metro High School))

Total: 10 (entries) + -3 (penalties) = 7/20 (35.0%)

======================================================================
Des Moines Independent Comm School District (IA) - 1908970
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:15-15:15 → elementary 07:40-14:35 | start=0/3 (Δ35m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:15-15:15 (All High Schools))
  false_positive: -3 (middle 08:30-15:25 (All Middle Schools (including Cowles and Ruby Van Meter)))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
BONNEVILLE JOINT DISTRICT (ID) - 1600930
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  high 08:40-15:48 → high 08:35-15:48 | start=1/3 (Δ5m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (middle 08:40-14:10 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-13:50 (Sandcreek Middle School))
  false_positive: -3 (high 07:30-14:35 (Lincoln High School))

Total: 7 (entries) + -9 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 9 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-14:15 (Aborn))
  false_positive: -3 (middle 07:45-14:05 (Harold Durgin Success Academy))
  false_positive: -3 (middle 07:45-14:30 (City Arts & Sciences Academy (CASA)))
  false_positive: -3 (middle 07:45-14:30 (Discovery Academy))
  false_positive: -3 (high 07:45-14:30 (Lynn Classical High School))
  false_positive: -3 (high 07:45-14:30 (Lynn English High School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))

Total: 19 (entries) + -24 (penalties) = 0/30 (0.0%)

======================================================================
Worcester (MA) - 2513230
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 0

Entry Scores:
  MISSED: middle 08:47-14:17 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:20-13:43 (Burncoat High School))
  false_positive: -3 (high 07:20-13:43 (North High School))
  false_positive: -3 (high 07:20-13:43 (Worcester Technical High School))
  false_positive: -3 (elementary 08:15-14:20 (Belmont Street Community School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  missing_grade_level: -2 (Missing: middle)

Total: 0 (entries) + -18 (penalties) = 0/10 (0.0%)

======================================================================
Bangor Public Schools (ME) - 2302820
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  middle 08:15-14:30 → middle 08:10-14:35 | start=1/3 (Δ5m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=1/1 = 5/10
  elementary 08:55-15:00 → elementary 08:40-15:00 | start=0/3 (Δ15m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 08:00-14:00 → high 07:45-14:35 | start=0/3 (Δ15m) end=0/3 (Δ35m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:35-15:00 (Grades 4-5))

Total: 12 (entries) + -3 (penalties) = 9/30 (30.0%)

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
DESOTO CO SCHOOL DIST (MS) - 2801320
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 09:00-15:38 | start=0/3 (Δ60m) end=0/3 (Δ38m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 08:00-14:35 (Culler Middle School))

Total: 2 (entries) + -3 (penalties) = 0/10 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 07:26-14:00 → high 07:26-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (high 08:00-14:30 (Damonte Ranch))
  false_positive: -3 (high 07:26-14:00 (Debbie Smith CTE))
  false_positive: -3 (high 08:00-14:30 (Galena High School))
  false_positive: -3 (high 07:34-14:35 (McQueen High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:26', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  missing_grade_level: -2 (Missing: elementary)

Total: 7 (entries) + -18 (penalties) = 0/10 (0.0%)

======================================================================
Cincinnati Public Schools (OH) - 3904375
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 08:00-14:30 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:00-15:50 (James N. Gamble Montessori High School))
  false_positive: -3 (middle 07:40-14:10 (Pleasant Hill Middle School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -8 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 19 | Matched: 3

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
  false_positive: -3 (high 08:00-14:30 (Cleveland SChoolar))
  false_positive: -3 (high 08:00-14:30 (Architecture & Design Career Academy))
  false_positive: -3 (high 08:00-14:30 (Cleveland School of the Arts))
  false_positive: -3 (high 08:35-15:05 (Collinwood High School))
  false_positive: -3 (high 08:35-15:05 (Davis Aerospace & Maritime))
  false_positive: -3 (high 08:35-15:05 (East Technical High School))
  false_positive: -3 (high 08:35-15:05 (Facing History New Tech))
  false_positive: -3 (high 08:35-15:05 (Lincoln-West School of))
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
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  missing_grade_level: -2 (Missing: elementary)
  missing_grade_level: -2 (Missing: middle)

Total: 20 (entries) + -84 (penalties) = 0/30 (0.0%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 08:40-14:30 (Essex High School))
  false_positive: -3 (middle 08:35-15:35 (Essex Middle School))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

======================================================================
Champlain Valley Unified Union School District #56 (VT) - 5000396
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 07:50-14:35 | start=3/3 (Δ0m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (middle 07:45-14:45 (Charlotte Central School))
  false_positive: -3 (middle 07:45-14:45 (Shelburne Community School))
  false_positive: -3 (middle 07:55-14:45 (Williston Central School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:45'))

Total: 5 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 08:08-14:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:10-14:35 (Burlington High School))
  false_positive: -3 (middle 07:55-15:00 (Edmunds Middle School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -8 (penalties) = 0/10 (0.0%)

======================================================================
BERKELEY COUNTY SCHOOLS (WV) - 5400060
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

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
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Albany County School District #1 (WY) - 5600730
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:02-15:00 → elementary 07:59-15:00 | start=1/3 (Δ3m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10
  middle 08:00-15:05 → middle 08:00-14:35 | start=3/3 (Δ0m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:45-15:45 → high 06:45-16:45 | start=0/3 (Δ60m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 15 (entries) + 0 (penalties) = 15/30 (50.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 3

Entry Scores:
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 08:00-15:55 → high 07:45-16:05 | start=0/3 (Δ15m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 07:45-15:00 (Farson-Eden Elementary School))
  false_positive: -3 (middle 07:45-16:05 (Farson-Eden Middle School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '16:05'))

Total: 11 (entries) + -8 (penalties) = 3/30 (10.0%)