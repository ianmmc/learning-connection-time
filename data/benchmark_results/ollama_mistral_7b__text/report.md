# Benchmark Report: ollama:mistral:7b
Run date: 2026-06-12T05:30:42
Districts tested: 40
Total extraction time: 3525s (avg 88.1s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 5.8% |
| JSON parse success | 95.0% |
| Grade coverage rate | 69.8% |
| False positive rate | 4.05/district |
| Mean time/extraction | 88.1s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 14 | 30 | 46.7% | missing_grade_level |  |
| Lynn | MA | 12 | 30 | 40.0% | false_positive |  |
| New Haven Unified | CA | 3 | 10 | 30.0% |  |  |
| Burlington School District | VT | 3 | 10 | 30.0% |  |  |
| Matanuska-Susitna Borough Scho | AK | 2 | 10 | 20.0% |  |  |
| Mobile County | AL | 2 | 10 | 20.0% |  |  |
| Christina School District | DE | 2 | 10 | 20.0% |  |  |
| Sweetwater County School Distr | WY | 6 | 30 | 20.0% | false_positive, duplicate_extraction |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 1 | 30 | 3.3% | missing_grade_level, missing_grade_level |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+19 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+31 more) |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 0 | 30 | 0.0% | extraction_error |  |
| Mesa Unified District (4235) | AZ | 0 | 20 | 0.0% | false_positive, missing_grade_level, missing_grade_level |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | extraction_error |  |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | missing_grade_level, missing_grade_level |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+52 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | extraction_error |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+48 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | extraction_error |  |
| BROWARD | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+44 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | extraction_error |  |
| Cedar Rapids Comm School Distr | IA | 0 | 20 | 0.0% | missing_grade_level |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Bangor Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive, missing_grade_level |  |
| Washoe County | NV | 0 | 10 | 0.0% | extraction_error |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+45 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | extraction_error |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| BERKELEY COUNTY SCHOOLS | WV | 0 | 30 | 0.0% | extraction_error |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| Albany County School District  | WY | 0 | 30 | 0.0% | extraction_error |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 08:10-14:35 | start=0/3 (Δ25m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 2 (entries) + 0 (penalties) = 2/10 (20.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 15 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 08:00-14:30 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 09:00-15:30 (North Pole Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Denali Elementary))
  false_positive: -3 (elementary 09:15-15:45 (University Park Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Salcha Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Watershed Charter))
  false_positive: -3 (elementary 09:15-15:45 (Weller Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Woodriver Elementary))
  false_positive: -3 (middle 07:50-14:20 (North Pole Middle))
  false_positive: -3 (middle 07:50-14:20 (Randy Smith Middle))
  false_positive: -3 (middle 07:50-14:20 (Ryan Middle))
  false_positive: -3 (middle 07:55-14:25 (Tanana Middle))
  false_positive: -3 (high 07:30-12:30 (Hutchison High))
  false_positive: -3 (high 07:30-12:30 (Lathrop High))
  false_positive: -3 (high 07:30-14:00 (West Valley High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '12:30'))

Total: 2 (entries) + -58 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 0

Entry Scores:
  MISSED: elementary 07:15-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (middle 07:45-15:05 (Spanish Fort Middle School))
  false_positive: -3 (middle 07:45-15:35 (Elberta Middle School))
  false_positive: -3 (high 07:50-15:05 (Fairhope High School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:15-15:15 | start=0/3 (Δ15m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 2 (entries) + 0 (penalties) = 2/10 (20.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 22 | Matched: 2

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:00 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:30-14:45 → middle 08:10-15:00 | start=0/3 (Δ40m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 07:15-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:30-14:30 (Baldwin Arts and Academic Magnet))
  false_positive: -3 (elementary 07:45-15:00 (Blount Elementary))
  false_positive: -3 (elementary 08:00-15:00 (Booker T. Washington (BTW) Magnet High School))
  false_positive: -3 (elementary 07:45-15:00 (Brewbaker Intermediate School))
  false_positive: -3 (elementary 08:30-15:00 (Brewbaker Middle School))
  false_positive: -3 (elementary 07:45-15:00 (Brewbaker Primary School))
  false_positive: -3 (elementary 07:45-15:00 (Carver Elementary Arts Magnet))
  false_positive: -3 (elementary 08:30-15:00 (Catoma Elementary School))
  false_positive: -3 (elementary 07:45-15:00 (Children's Center))
  false_positive: -3 (elementary 08:10-15:00 (Chisholm Elementary))
  false_positive: -3 (elementary 07:30-14:30 (Dalraida))
  false_positive: -3 (elementary 08:40-15:00 (Dannelly Elementary))
  false_positive: -3 (elementary 08:10-15:00 (Davis Elementary School))
  false_positive: -3 (elementary 08:10-15:00 (Dozier Elementary))
  false_positive: -3 (elementary 07:45-15:00 (E.D.Nixon Elementary))
  false_positive: -3 (elementary 08:30-15:00 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 07:30-14:30 (Forest Avenue Academic Magnet))
  false_positive: -3 (elementary 07:25-14:30 (Morningview Elementary School))
  false_positive: -3 (elementary 07:10-14:30 (Peter Crump Elem.))
  false_positive: -3 (elementary 08:10-15:00 (Southlawn Elementary School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  missing_grade_level: -2 (Missing: high)

Total: 7 (entries) + -88 (penalties) = 0/30 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  middle 08:05-15:30 → middle 08:05-14:30 | start=3/3 (Δ0m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 5/10
  MISSED: elementary 08:05-15:30 (unnamed) → 0/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: elementary)

Total: 5 (entries) + -4 (penalties) = 1/30 (3.3%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 07:50-13:50 (unnamed) → 0/10
  MISSED: middle 08:00-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (junior 07:30-14:15 (Benjamin Franklin Junior High School))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: elementary)

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
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high Varies-Varies → high 08:10-14:35 | start=0/3 end=0/3 grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: elementary Varies-Varies (unnamed) → 0/10
  MISSED: middle Varies-Varies (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: elementary)

Total: 2 (entries) + -4 (penalties) = 0/30 (0.0%)

======================================================================
New Haven Unified (CA) - 0626910
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:30-14:05 → elementary 08:00-12:05 | start=0/3 (Δ30m) end=0/3 (Δ120m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 3 (entries) + 0 (penalties) = 3/10 (30.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 31 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:50-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

Penalties:
  false_positive: -3 (elementary 08:25-14:35 (Blackham))
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
  false_positive: -3 (elementary 08:35-14:35 (High Horizon))
  false_positive: -3 (elementary 08:50-15:10 (Jettie Tisdale))
  false_positive: -3 (elementary 08:50-15:10 (John Winthrop))
  false_positive: -3 (elementary 08:50-15:10 (Marin))
  false_positive: -3 (elementary 08:50-15:10 (Madison))
  false_positive: -3 (elementary 08:35-14:35 (Multicultural))
  false_positive: -3 (elementary 08:30-15:00 (Park City Magnet))
  false_positive: -3 (elementary 08:50-15:10 (Read))
  false_positive: -3 (elementary 08:50-15:10 (Roosevelt))
  false_positive: -3 (elementary 08:50-15:10 (Thomas Hooker))
  false_positive: -3 (elementary 08:50-15:10 (Waltersville))
  false_positive: -3 (elementary 08:50-15:10 (Wilbur Cross))
  false_positive: -3 (high 07:53-14:30 (Bassick))
  false_positive: -3 (high 07:53-14:30 (Central))
  false_positive: -3 (high 07:53-14:30 (Harding))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))

Total: 8 (entries) + -140 (penalties) = 0/10 (0.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 30 | Matched: 3

Entry Scores:
  elementary 08:35-14:50 → elementary 08:35-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:50-14:20 → middle 07:50-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 07:20-13:50 → high 08:10-14:35 | start=0/3 (Δ50m) end=0/3 (Δ45m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:10-14:35 (Kennedy))
  false_positive: -3 (high 08:10-14:35 (Wtby Arts Magnet))
  false_positive: -3 (high 08:10-14:35 (Wtby Career Academy))
  false_positive: -3 (high 08:10-14:35 (Wilby))
  false_positive: -3 (middle 07:50-14:20 (Wallace))
  false_positive: -3 (middle 07:20-13:50 (Wtby Arts Magnet))
  false_positive: -3 (middle 07:50-14:20 (West Side))
  false_positive: -3 (elementary 08:35-14:50 (Bunker Hill))
  false_positive: -3 (elementary 08:35-14:50 (Carrington))
  false_positive: -3 (elementary 08:35-14:50 (Chase))
  false_positive: -3 (elementary 08:35-14:50 (Cross, Wendell))
  false_positive: -3 (elementary 08:05-14:30 (Driggs))
  false_positive: -3 (elementary 08:05-14:30 (Duggan))
  false_positive: -3 (elementary 08:35-14:50 (Generali))
  false_positive: -3 (elementary 08:35-14:50 (Gilmartin))
  false_positive: -3 (elementary 08:35-14:50 (Hopeville))
  false_positive: -3 (elementary 08:35-14:50 (Kingsbury))
  false_positive: -3 (elementary 08:35-14:50 (Maloney))
  false_positive: -3 (elementary 08:35-14:50 (Reed))
  false_positive: -3 (elementary 08:35-14:50 (Regan))
  false_positive: -3 (elementary 09:05-15:20 (Roberto Clemente))
  false_positive: -3 (elementary 09:05-15:20 (Rotella))
  false_positive: -3 (elementary 08:05-14:30 (Sprague))
  false_positive: -3 (elementary 08:05-14:30 (Tinker))
  false_positive: -3 (elementary 08:35-14:50 (Walsh))
  false_positive: -3 (elementary 08:05-14:30 (Washington))
  false_positive: -3 (elementary 08:05-14:30 (Wilson))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:30'))

Total: 18 (entries) + -129 (penalties) = 0/30 (0.0%)

======================================================================
KIPP DC PCS (DC) - 1100031
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  elementary 08:00-15:30 → elementary 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 08:15-15:15 → high 08:15-15:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: middle 08:00-15:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)

Total: 16 (entries) + -2 (penalties) = 14/30 (46.7%)

======================================================================
Appoquinimink School District (DE) - 1000080
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  high 07:30-14:30 → high 08:20-14:35 | start=0/3 (Δ50m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (high 08:20-14:35 (Middletown HS))
  false_positive: -3 (high 08:20-14:35 (Odessa HS))
  false_positive: -3 (middle/high 08:20-14:35 (Special Program MS/HS))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:20', '14:35'))

Total: 3 (entries) + -13 (penalties) = 0/10 (0.0%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:00-15:00 → elementary 07:00-14:05 | start=0/3 (Δ60m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 2 (entries) + 0 (penalties) = 2/10 (20.0%)

======================================================================
Red Clay Consolidated School District (DE) - 1001300
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
BROWARD (FL) - 1200180
======================================================================
Ground truth: 3 entries | Extracted: 25 | Matched: 1

Entry Scores:
  elementary 08:00-14:00 → elementary 08:00-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: high 07:40-14:40 (unnamed) → 0/10
  MISSED: middle 09:30-16:10 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:50-13:50 (Park Lakes Elementary))
  false_positive: -3 (elementary 08:10-14:10 (Fairway Elementary))
  false_positive: -3 (elementary 08:30-14:30 (Deerfield Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Dillard Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Discovery Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Flamingo Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Forest Hills Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Floranada Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Glen Falls Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Hollywood Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Inverrary Elementary))
  false_positive: -3 (elementary 08:00-14:00 (J.W. Marriott Jr. Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Lake Forest Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Lakeside Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Meadow Glen Elementary))
  false_positive: -3 (elementary 08:00-14:00 (North Lauderdale Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Oakland Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Park Springs Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Pembroke Lakes Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Pineshore Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Riverglades Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Sheridan Hills Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Twin Lakes Elementary))
  false_positive: -3 (elementary 08:00-14:00 (West Lake Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 8 (entries) + -118 (penalties) = 0/30 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:50-14:20 → elementary 08:30-15:50 | start=0/3 (Δ20m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 07:50-13:55 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)

Total: 2 (entries) + -2 (penalties) = 0/20 (0.0%)

======================================================================
Des Moines Independent Comm School District (IA) - 1908970
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:15-15:15 → elementary 07:40-14:35 | start=0/3 (Δ35m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:10-14:35 (Des Moines Public Schools - High Schools))
  false_positive: -3 (middle 08:30-15:25 (Des Moines Public Schools - Middle Schools))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
BONNEVILLE JOINT DISTRICT (ID) - 1600930
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:30-14:15 → middle 07:30-14:30 | start=3/3 (Δ0m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-14:15 (ABORN))

Total: 15 (entries) + -3 (penalties) = 12/30 (40.0%)

======================================================================
Worcester (MA) - 2513230
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  middle 08:47-14:17 → middle 07:20-13:43 | start=0/3 (Δ87m) end=0/3 (Δ34m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-14:20 (None))
  false_positive: -3 (high 08:10-14:35 (Fivay High))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Bangor Public Schools (ME) - 2302820
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 2

Entry Scores:
  middle 08:15-14:30 → middle 07:50-14:30 | start=0/3 (Δ25m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:55-15:00 → elementary 08:40-15:30 | start=0/3 (Δ15m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:00-14:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:35-03:00 (Abraham Lincoln School))
  false_positive: -3 (elementary 07:30-04:00 (Fairmount School))
  missing_grade_level: -2 (Missing: high)

Total: 7 (entries) + -8 (penalties) = 0/30 (0.0%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 6 | Matched: 3

Entry Scores:
  middle 07:35-14:00 → middle 07:15-14:00 | start=0/3 (Δ20m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:20-14:50 → elementary 08:25-15:10 | start=1/3 (Δ5m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 07:45-14:00 → high 07:15-14:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:45-15:00 (McMahon))
  false_positive: -3 (elementary 07:45-15:30 (Montello))
  false_positive: -3 (elementary 08:25-15:10 (Geiger))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:10'))

Total: 10 (entries) + -11 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: high 08:00-15:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (middle 08:00-15:38 (Culler Middle School))
  missing_grade_level: -2 (Missing: high)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Cincinnati Public Schools (OH) - 3904375
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:00-14:30 → elementary 09:10-15:40 | start=0/3 (Δ70m) end=0/3 (Δ70m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 08:00-14:00 (Pleasant Hill Middle School))
  false_positive: -3 (high 08:00-15:00 (James N. Gamble Montessori High School))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 26 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=0/1 = 6/10
  middle 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=0/1 = 6/10

Penalties:
  false_positive: -3 (elementary 07:35-14:05 (Adlai E. Stevenson))
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (elementary 09:35-14:05 (Garfield))
  false_positive: -3 (elementary 07:35-14:05 (Alfred A. Benesch))
  false_positive: -3 (elementary 09:35-14:05 (George W. Carver))
  false_positive: -3 (elementary 09:35-14:05 (Paul L. Dunbar))
  false_positive: -3 (elementary 08:35-15:05 (Almira))
  false_positive: -3 (elementary 09:35-14:05 (Halle))
  false_positive: -3 (elementary 09:35-14:05 (Riverside))
  false_positive: -3 (elementary 07:35-14:05 (Andrew J. Rickoff))
  false_positive: -3 (elementary 09:35-14:05 (Hannah Gibbons))
  false_positive: -3 (elementary 09:35-14:05 (Robert H. Jamison))
  false_positive: -3 (elementary 07:35-14:05 (Anton Grdina))
  false_positive: -3 (elementary 07:35-14:05 (Harvey Rice))
  false_positive: -3 (elementary 08:35-15:05 (Robinson G. Jones))
  false_positive: -3 (elementary 09:35-14:05 (Artemus Ward))
  false_positive: -3 (elementary 09:35-14:05 (Joseph M. Gallagher))
  false_positive: -3 (elementary 07:35-14:05 (Scranton))
  false_positive: -3 (elementary 08:35-15:05 (Benjamin Franklin))
  false_positive: -3 (elementary 09:35-14:05 (Kenneth Clement Boys’))
  false_positive: -3 (elementary 08:35-15:05 (Stephanie Tubbs Jones School))
  false_positive: -3 (elementary 07:35-14:05 (Bolton))
  false_positive: -3 (elementary 09:35-14:05 (Leadership Academy Stonebrook-White))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 20 (entries) + -119 (penalties) = 0/30 (0.0%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Champlain Valley Unified Union School District #56 (VT) - 5000396
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 07:50-14:35 | start=3/3 (Δ0m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 07:45-14:35 (Charlotte Central School))
  false_positive: -3 (elementary 07:45-14:35 (Shelburne Community School))
  false_positive: -3 (elementary 07:55-14:35 (Williston Central School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:35'))

Total: 5 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:10-15:30 | start=1/3 (Δ2m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 3/10

Total: 3 (entries) + 0 (penalties) = 3/10 (30.0%)

======================================================================
BERKELEY COUNTY SCHOOLS (WV) - 5400060
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

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
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  elementary 07:50-15:15 → elementary 07:45-15:00 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 08:00-15:55 → high 08:00-14:35 | start=3/3 (Δ0m) end=0/3 (Δ80m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 07:45-15:00 (Wamsutter K-8 School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:00'))

Total: 11 (entries) + -5 (penalties) = 6/30 (20.0%)