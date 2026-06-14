# Benchmark Report: openrouter:mistralai/mistral-medium-3.1
Run date: 2026-06-14T02:53:23
Districts tested: 17
Total extraction time: 174s (avg 10.2s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 27.3% |
| JSON parse success | 100.0% |
| Grade coverage rate | 100.0% |
| False positive rate | 13.71/district |
| Mean time/extraction | 10.2s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| Albany County School District  | WY | 27 | 30 | 90.0% |  |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 22 | 30 | 73.3% | false_positive, duplicate_extraction |  |
| Sweetwater County School Distr | WY | 12 | 30 | 40.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Lewiston Public Schools | ME | 2 | 30 | 6.7% | false_positive, false_positive, false_positive (+4 more) |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | false_positive, false_positive, duplicate_extraction (+1 more) |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+34 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+60 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+54 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+50 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+48 more) |  |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+89 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+12 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-15:15 | start=3/3 (Δ0m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:45-15:15 (Houston High School))
  false_positive: -3 (high 07:45-15:15 (Palmer High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '15:15'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '15:15'))

Total: 5 (entries) + -10 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 24 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (Anne Wien Elementary))
  false_positive: -3 (elementary 08:00-14:30 (Arctic Light Elementary))
  false_positive: -3 (elementary 08:15-14:45 (Barinette Magnet))
  false_positive: -3 (elementary 08:45-15:15 (Boreal Sun Charter))
  false_positive: -3 (elementary 08:15-14:45 (Chinook Montessori Charter))
  false_positive: -3 (elementary 09:15-15:45 (Denali Elementary))
  false_positive: -3 (elementary 08:00-14:30 (Hunter Elementary))
  false_positive: -3 (high 07:30-14:00 (Hutchison High))
  false_positive: -3 (elementary 09:15-15:45 (Ladd Elementary))
  false_positive: -3 (high 07:30-14:00 (Lathrop High))
  false_positive: -3 (elementary 09:00-15:30 (North Pole Elementary))
  false_positive: -3 (high 07:30-14:00 (North Pole High))
  false_positive: -3 (middle 07:50-14:20 (North Pole Middle))
  false_positive: -3 (middle 07:50-14:20 (Randy Smith Middle))
  false_positive: -3 (middle 07:50-14:20 (Ryan Middle))
  false_positive: -3 (elementary 09:15-15:45 (Salcha Elementary))
  false_positive: -3 (middle 07:55-14:25 (Tanana Middle))
  false_positive: -3 (elementary 09:00-15:30 (Ticasuk Brown Elementary))
  false_positive: -3 (elementary 09:15-15:45 (University Park Elementary))
  false_positive: -3 (elementary 08:30-15:00 (Watershed Charter))
  false_positive: -3 (elementary 09:15-15:45 (Weller Elementary))
  false_positive: -3 (high 07:30-14:00 (West Valley High))
  false_positive: -3 (elementary 09:15-15:45 (Woodriver Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))

Total: 9 (entries) + -97 (penalties) = 0/10 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:45-16:00 → high 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:45-16:00 → middle 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 07:40-14:55 (LRSD K-8 Schools (Elementary Grades)))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:55'))

Total: 27 (entries) + -5 (penalties) = 22/30 (73.3%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 38 | Matched: 1

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
  false_positive: -3 (elementary 08:50-15:10 (Jettie Tisdale))
  false_positive: -3 (elementary 08:50-15:10 (John Winthrop))
  false_positive: -3 (elementary 08:50-15:10 (Marin))
  false_positive: -3 (elementary 08:50-15:10 (Madison))
  false_positive: -3 (elementary 08:35-14:55 (Multicultural))
  false_positive: -3 (elementary 08:35-14:55 (Park City Magnet))
  false_positive: -3 (elementary 08:30-15:00 (Read))
  false_positive: -3 (elementary 08:50-15:10 (Roosevelt))
  false_positive: -3 (elementary 08:50-15:10 (Thomas Hooker))
  false_positive: -3 (elementary 08:50-15:10 (Waltersville))
  false_positive: -3 (elementary 08:50-15:10 (Wilbur Cross))
  false_positive: -3 (elementary 08:15-14:00 (Bridgeport Learning Center))
  false_positive: -3 (middle 07:50-14:20 (Curiale))
  false_positive: -3 (middle 07:50-14:20 (Read))
  false_positive: -3 (high 07:53-14:30 (Bassick))
  false_positive: -3 (high 07:53-14:30 (Central))
  false_positive: -3 (high 07:53-14:30 (Harding))
  false_positive: -3 (high 08:15-14:00 (Bridgeport Learning Center))
  false_positive: -3 (high 07:50-14:05 (Fairchild Wheeler))
  false_positive: -3 (high 07:55-14:10 (Bridgeport Military Academy))
  false_positive: -3 (high 08:00-14:05 (Aquaculture))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:55'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:55'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))

Total: 9 (entries) + -163 (penalties) = 0/10 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 35 | Matched: 3

Entry Scores:
  elementary 08:35-14:50 → elementary 08:35-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-13:50 → high 07:20-13:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:50-14:20 → middle 07:50-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 07:20-13:50 (Kennedy High School))
  false_positive: -3 (high 07:20-13:50 (Waterbury Arts Magnet High School))
  false_positive: -3 (high 07:20-13:50 (Waterbury Career Academy High School))
  false_positive: -3 (high 07:20-13:50 (Wilby High School))
  false_positive: -3 (middle 07:50-14:20 (Wallace Middle School))
  false_positive: -3 (middle 07:20-13:50 (Waterbury Arts Magnet Middle School))
  false_positive: -3 (middle 07:50-14:20 (West Side Middle School))
  false_positive: -3 (elementary 08:35-14:50 (Bunker Hill Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Carrington Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Chase Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Wendell L. Cross Elementary School))
  false_positive: -3 (elementary 08:05-14:20 (Driggs Elementary School))
  false_positive: -3 (elementary 08:05-14:20 (Duggan Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Generali Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Gilmartin Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Hopeville Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Kingsbury Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Maloney Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Reed Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Regan Elementary School))
  false_positive: -3 (elementary 09:05-15:20 (Roberto Clemente Leadership Academy))
  false_positive: -3 (elementary 09:05-15:20 (Rotella Interdistrict Magnet School))
  false_positive: -3 (elementary 08:05-14:20 (Sprague Elementary School))
  false_positive: -3 (elementary 08:05-14:20 (Tinker Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Walsh Elementary School))
  false_positive: -3 (elementary 08:05-14:20 (Washington Elementary School))
  false_positive: -3 (elementary 08:35-14:50 (Wilson Elementary School))
  false_positive: -3 (high 07:30-13:45 (Holy Cross High School))
  false_positive: -3 (high 07:25-14:20 (Kaynor Technical High School))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Bais Yaakov Girls High School))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Gedolah Boys High School))
  false_positive: -3 (elementary 09:00-16:00 (Yeshiva K'Tana Elementary School))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '16:00'))

Total: 27 (entries) + -146 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 6 | Matched: 1

Entry Scores:
  high 08:40-15:48 → high 08:40-15:48 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 08:40-15:54 (Hillcrest High School))
  false_positive: -3 (high 08:00-14:45 (Lincoln High School))
  false_positive: -3 (high 08:40-15:48 (Thunder Ridge High School))
  false_positive: -3 (middle 09:14-15:45 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))
  duplicate_extraction: -2 (Duplicate: ('high', '08:40', '15:48'))

Total: 9 (entries) + -17 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 31 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:45-13:45 (Drewicz Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Early Childhood Center))
  false_positive: -3 (elementary 07:45-13:45 (Fallon Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Ford Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Harrington Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Ingalls Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Sisson Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Virginia Barton Center at Briarcliff (TEAMS) Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Washington Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Aborn Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Brickett Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Cobbet Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Connery Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Hood Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Lincoln-Thomson Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Lynn Woods Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Sewell-Anderson Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Shoemaker Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Tracy Elementary))
  false_positive: -3 (middle 07:45-14:05 (Harold Durgin Success Academy))
  false_positive: -3 (middle 07:45-14:30 (Pickering Middle School))
  false_positive: -3 (middle 07:45-14:30 (Thurgood Marshall Middle School))
  false_positive: -3 (middle 07:45-14:30 (Virginia Barton Center at Briarcliff (Secondary TEAMS)))
  false_positive: -3 (high 07:45-14:30 (Discovery Academy))
  false_positive: -3 (high 07:45-14:30 (Frederick Douglass Collegiate Academy))
  false_positive: -3 (high 07:45-14:30 (Lynn Classical High School))
  false_positive: -3 (high 07:45-14:30 (Lynn English High School))
  false_positive: -3 (high 07:45-14:30 (Lynn Vocational Technical Institute))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))

Total: 20 (entries) + -134 (penalties) = 0/30 (0.0%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 7 | Matched: 3

Entry Scores:
  high 07:45-14:00 → high 07:45-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:35-14:00 → middle 07:35-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:20-14:50 → elementary 08:40-15:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:00-14:30 (Connors))
  false_positive: -3 (elementary 08:40-15:10 (McMahon))
  false_positive: -3 (elementary 08:00-14:30 (Montello))
  false_positive: -3 (elementary 08:40-15:10 (Geiger))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:40', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:40', '15:10'))

Total: 20 (entries) + -18 (penalties) = 2/30 (6.7%)

======================================================================
DESOTO CO SCHOOL DIST (MS) - 2801320
======================================================================
Ground truth: 3 entries | Extracted: 33 | Matched: 3

Entry Scores:
  elementary 08:30-15:25 → elementary 08:30-15:25 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:25-15:45 → high 08:25-15:45 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:40 → middle 08:00-15:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:30-15:25 (Overpark Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Pleasant Hill Elementary))
  false_positive: -3 (elementary 08:25-15:20 (DeSoto Central Primary))
  false_positive: -3 (elementary 08:30-15:25 (DeSoto Central Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Lake Cormorant Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Walls Elementary))
  false_positive: -3 (elementary 07:40-14:40 (Hernando Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Oak Grove Central Elementary))
  false_positive: -3 (elementary 07:45-14:40 (Hernando Hills Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Hernando Intermediate School))
  false_positive: -3 (elementary 07:45-14:40 (Horn Lake Elementary))
  false_positive: -3 (elementary 07:45-14:40 (Shadow Oaks Elementary))
  false_positive: -3 (elementary 07:40-14:20 (Horn Lake Intermediate))
  false_positive: -3 (elementary 07:40-14:40 (Lewisburg Primary))
  false_positive: -3 (elementary 07:40-14:40 (Lewisburg Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Lewisburg Intermediate))
  false_positive: -3 (elementary 08:30-15:25 (Snowden Grove Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Hope Sullivan Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Greenbrook Elementary))
  false_positive: -3 (elementary 08:25-15:20 (Southaven Intermediate))
  false_positive: -3 (middle 08:00-15:40 (DeSoto Central Middle))
  false_positive: -3 (middle 07:15-14:50 (Hernando Middle))
  false_positive: -3 (middle 07:10-14:50 (Horn Lake Middle))
  false_positive: -3 (middle 08:00-15:40 (Lake Cormorant Middle))
  false_positive: -3 (middle 08:00-15:40 (Southaven Middle))
  false_positive: -3 (high 08:25-15:45 (DeSoto Central High))
  false_positive: -3 (high 07:30-14:55 (Hernando High))
  false_positive: -3 (high 07:35-14:55 (Horn Lake High))
  false_positive: -3 (high 08:25-15:45 (Lake Cormorant High))
  false_positive: -3 (high 08:25-15:45 (Southaven High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '15:45'))

Total: 27 (entries) + -132 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 51 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:00-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Culler Middle School))
  false_positive: -3 (middle 08:00-15:00 (Lux Middle School))
  false_positive: -3 (middle 08:00-15:00 (Pound Middle School))
  false_positive: -3 (high 08:00-15:05 (Lincoln High School))
  false_positive: -3 (high 08:00-15:00 (North Star High School))
  false_positive: -3 (high 08:00-14:55 (Northeast High School))
  false_positive: -3 (high 08:00-15:00 (Northwest High School))
  false_positive: -3 (high 08:00-15:00 (Southeast High School))
  false_positive: -3 (high 08:15-15:03 (Southwest High School))
  false_positive: -3 (high 08:00-15:00 (Standing Bear High School))
  false_positive: -3 (high 08:10-15:00 (Bryan Community High School (9th & 10th)))
  false_positive: -3 (high 09:00-15:00 (Bryan Community High School (11th & 12th)))
  false_positive: -3 (elementary 08:15-14:53 (Adams Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Arnold Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Beattie Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Belmont Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Brownell Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Calvert Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Campbell Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Cavett Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Clinton Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Eastridge Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Elliott Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Everett Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Fredstrom Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Hartley Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Hill Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Holmes Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Humann Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Huntington Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Kahoa Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Kloefkorn Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Kooser Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Lakeview Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Maxey Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (McPhee Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Meadow Lane Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Morley Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Norwood Park Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Pershing Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Prescott Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Pyrtle Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Randolph Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Riley Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Robinson Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Roper Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Rousseau Elementary School))
  false_positive: -3 (elementary 08:15-14:53 (Saratoga Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (Sheridan Elementary School))
  false_positive: -3 (elementary 09:00-15:38 (West Lincoln Elementary School))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))

Total: 9 (entries) + -234 (penalties) = 0/10 (0.0%)

======================================================================
Cincinnati Public Schools (OH) - 3904375
======================================================================
Ground truth: 1 entries | Extracted: 10 | Matched: 1

Entry Scores:
  elementary 08:00-14:30 → elementary 07:40-14:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:40-14:10 (Rockdale Academy))
  false_positive: -3 (elementary 09:10-15:40 (Roselawn Condon School))
  false_positive: -3 (elementary 07:40-14:10 (Clifton Area Neighborhood School (CANS)))
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

Total: 2 (entries) + -39 (penalties) = 0/10 (0.0%)

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
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:08-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 07:55-14:35 (Burlington High School))
  false_positive: -3 (elementary 08:10-14:50 (Edmunds Elementary School))
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle School))
  false_positive: -3 (middle 08:00-15:00 (Hunt Middle School))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))

Total: 9 (entries) + -14 (penalties) = 0/10 (0.0%)

======================================================================
Albany County School District #1 (WY) - 5600730
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:02-15:00 → elementary 08:02-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:45-15:45 → high 07:45-15:45 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:05 → middle 08:00-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 27 (entries) + 0 (penalties) = 27/30 (90.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 6 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-15:15 (4-6 Elementary Schools))
  false_positive: -3 (elementary 08:30-15:50 (Wamsutter K-8 (Grades 4-6)))
  false_positive: -3 (middle 08:30-15:50 (Wamsutter K-8 (Grades 7-8)))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:30', '15:50'))

Total: 23 (entries) + -11 (penalties) = 12/30 (40.0%)