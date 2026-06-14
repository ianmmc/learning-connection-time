# Benchmark Report: openrouter:meta-llama/llama-3.3-70b-instruct
Run date: 2026-06-14T00:06:27
Districts tested: 40
Total extraction time: 848s (avg 21.2s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 16.8% |
| JSON parse success | 100.0% |
| Grade coverage rate | 90.9% |
| False positive rate | 10.12/district |
| Mean time/extraction | 21.2s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Albany County School District  | WY | 27 | 30 | 90.0% |  |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 20 | 30 | 66.7% |  |  |
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| Cleveland Municipal | OH | 14 | 30 | 46.7% |  |  |
| Bangor Public Schools | ME | 12 | 30 | 40.0% | false_positive |  |
| Cedar Rapids Comm School Distr | IA | 7 | 20 | 35.0% | false_positive |  |
| BERKELEY COUNTY SCHOOLS | WV | 9 | 30 | 30.0% | missing_grade_level |  |
| Sweetwater County School Distr | WY | 9 | 30 | 30.0% |  |  |
| Tucson Unified District (4403) | AZ | 4 | 20 | 20.0% | false_positive, false_positive, duplicate_extraction |  |
| Los Angeles Unified | CA | 6 | 30 | 20.0% |  |  |
| Matanuska-Susitna Borough Scho | AK | 1 | 10 | 10.0% | false_positive, false_positive, duplicate_extraction |  |
| Burlington School District | VT | 1 | 10 | 10.0% | false_positive, false_positive |  |
| Lewiston Public Schools | ME | 2 | 30 | 6.7% | false_positive, false_positive, false_positive (+4 more) |  |
| Mesa Unified District (4235) | AZ | 1 | 20 | 5.0% | false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+34 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+9 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+47 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+27 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| BROWARD | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+122 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+29 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+47 more) |  |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+110 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+112 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+14 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 07:00-15:00 (Houston High School))
  false_positive: -3 (high 07:00-15:00 (Palmer High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:00', '15:00'))

Total: 9 (entries) + -8 (penalties) = 1/10 (10.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 24 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (Anne Wien Elementary))
  false_positive: -3 (elementary 08:00-14:30 (Arctic Light Elementary))
  false_positive: -3 (elementary 08:15-14:45 (Barnette Magnet))
  false_positive: -3 (elementary 08:45-15:15 (Boreal Sun Charter))
  false_positive: -3 (elementary 08:15-14:45 (Chinook Montessori Charter))
  false_positive: -3 (elementary 09:15-15:45 (Denali Elementary))
  false_positive: -3 (elementary 08:00-14:30 (Hunter Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Ladd Elementary))
  false_positive: -3 (elementary 09:00-15:30 (North Pole Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Salcha Elementary))
  false_positive: -3 (elementary 09:00-15:30 (Ticasuk Brown Elementary))
  false_positive: -3 (elementary 09:15-15:45 (University Park Elementary))
  false_positive: -3 (elementary 08:30-15:00 (Watershed Charter))
  false_positive: -3 (elementary 09:15-15:45 (Weller Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Woodriver Elementary))
  false_positive: -3 (middle 07:50-14:20 (North Pole Middle))
  false_positive: -3 (middle 07:50-14:20 (Randy Smith Middle))
  false_positive: -3 (middle 07:50-14:20 (Ryan Middle))
  false_positive: -3 (middle 07:55-14:25 (Tanana Middle))
  false_positive: -3 (high 07:30-14:00 (Hutchison High))
  false_positive: -3 (high 07:30-14:00 (Lathrop High))
  false_positive: -3 (high 07:30-14:00 (North Pole High))
  false_positive: -3 (high 07:30-14:00 (West Valley High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))

Total: 9 (entries) + -97 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 8 | Matched: 1

Entry Scores:
  elementary 07:15-14:45 → elementary 07:40-14:40 | start=0/3 (Δ25m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (middle 07:42-15:05 (Daphne Middle School))
  false_positive: -3 (middle 07:45-15:03 (Elberta Middle School))
  false_positive: -3 (middle 07:42-15:05 (Fairhope Middle School))
  false_positive: -3 (high 07:50-15:15 (Daphne High School))
  false_positive: -3 (high 07:50-15:15 (Fairhope High School))
  false_positive: -3 (high 07:45-15:05 (Robertsdale High School))
  false_positive: -3 (high 07:45-14:35 (Baldwin County High School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:42', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:50', '15:15'))

Total: 3 (entries) + -25 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 9 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:10-15:05 | start=0/3 (Δ10m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:15-14:35 (Mary G Montgomery High School))
  false_positive: -3 (high 07:05-14:25 (Blount High School))
  false_positive: -3 (middle 07:15-14:20 (Causey Middle School))
  false_positive: -3 (middle 07:05-14:20 (Pillans Middle School))
  false_positive: -3 (elementary 07:45-15:15 (Holloway Elementary School))
  false_positive: -3 (elementary 07:45-15:15 (Allentown Elementary School))
  false_positive: -3 (elementary 07:40-15:10 (Dodge Elementary School))
  false_positive: -3 (elementary 08:10-15:15 (Tanner Williams Elementary School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:15'))

Total: 2 (entries) + -26 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 8 | Matched: 3

Entry Scores:
  middle 07:30-14:45 → middle 07:25-14:35 | start=1/3 (Δ5m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 4/10
  high 07:15-14:45 → high 07:15-15:15 | start=3/3 (Δ0m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=1/1 = 6/10
  elementary 08:10-15:10 → elementary 07:30-14:30 | start=0/3 (Δ40m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 07:30-14:30 (Blount Elementary))
  false_positive: -3 (high 07:45-15:15 (Booker T. Washington (BTW) Magnet High School))
  false_positive: -3 (middle 08:10-15:10 (Brewbaker Middle School))
  false_positive: -3 (elementary 07:30-14:30 (Morningview Elementary School))
  false_positive: -3 (high 08:00-15:10 (Park Crossing Highschool))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))

Total: 13 (entries) + -19 (penalties) = 0/30 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:45-16:00 → high 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:45-16:00 → middle 07:40-14:55 | start=0/3 (Δ65m) end=0/3 (Δ65m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 20 (entries) + 0 (penalties) = 20/30 (66.7%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 2

Entry Scores:
  middle 08:05-15:30 → middle 08:05-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:05-15:30 → elementary 07:45-15:15 | start=0/3 (Δ20m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-15:15 (Harp Elementary))
  false_positive: -3 (middle 08:05-15:30 (Helen Tyson Middle School))
  false_positive: -3 (middle 08:05-15:30 (Sonora Middle School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:05', '15:30'))
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
  false_positive: -3 (high 07:15-15:15 (Red Mountain High School))

Total: 4 (entries) + -3 (penalties) = 1/20 (5.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 4 | Matched: 2

Entry Scores:
  middle 08:50-15:50 → middle 08:50-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:30-15:15 → high 07:05-16:45 | start=0/3 (Δ85m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 08:20-14:45 (Borton Elementary))
  false_positive: -3 (high 07:05-16:45 (Tucson High Magnet School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:05', '16:45'))

Total: 12 (entries) + -8 (penalties) = 4/20 (20.0%)

======================================================================
Los Angeles Unified (CA) - 0622710
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary Varies-Varies → elementary 08:00-14:23 | start=0/3 end=0/3 grade=2/2 name=0/1 conf=0/1 = 2/10
  high Varies-Varies → high 08:00-14:53 | start=0/3 end=0/3 grade=2/2 name=0/1 conf=0/1 = 2/10
  middle Varies-Varies → middle 08:00-14:53 | start=0/3 end=0/3 grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 6 (entries) + 0 (penalties) = 6/30 (20.0%)

======================================================================
New Haven Unified (CA) - 0626910
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 08:30-14:05 → elementary 08:00-14:05 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-14:05 (Delaine Eastin Elementary School))
  false_positive: -3 (elementary 08:00-14:05 (Searles Elementary School))
  false_positive: -3 (middle 08:15-14:47 (César Chávez Middle School))
  false_positive: -3 (high 08:00-13:54 (Conley-Caraballo High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))

Total: 5 (entries) + -16 (penalties) = 0/10 (0.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 10 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:30-15:00 | start=0/3 (Δ20m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:25-14:55 (Blackham))
  false_positive: -3 (middle 07:50-14:20 (Curiale))
  false_positive: -3 (middle 07:50-14:20 (Read))
  false_positive: -3 (high 07:50-14:05 (Fairchild Wheeler))
  false_positive: -3 (high 07:53-14:30 (Bassick))
  false_positive: -3 (high 07:53-14:30 (Central))
  false_positive: -3 (high 07:53-14:30 (Harding))
  false_positive: -3 (high 07:55-14:10 (Bpt. Military Academy))
  false_positive: -3 (high 08:00-14:05 (Aquaculture))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))

Total: 2 (entries) + -33 (penalties) = 0/10 (0.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 11 | Matched: 3

Entry Scores:
  middle 07:50-14:20 → middle 07:45-14:10 | start=1/3 (Δ5m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 3/10
  elementary 08:45-15:00 → elementary 08:35-14:50 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  high 07:20-13:50 → high 07:30-14:00 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:17 (Sound School))
  false_positive: -3 (high 07:10-14:05 (New Haven Academy))
  false_positive: -3 (high 07:10-14:05 (HSC HS))
  false_positive: -3 (high 07:30-14:15 (Metro Bus. Academy))
  false_positive: -3 (elementary 07:55-14:10 (King-Robinson))
  false_positive: -3 (elementary 09:15-15:30 (John Martinez))
  false_positive: -3 (elementary 07:30-14:00 (Mauro-Sheridan))
  false_positive: -3 (middle 08:35-14:50 (Bishop Woods))
  duplicate_extraction: -2 (Duplicate: ('high', '07:10', '14:05'))

Total: 7 (entries) + -26 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 29 | Matched: 3

Entry Scores:
  elementary 08:35-14:50 → elementary 08:35-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-13:50 → high 07:20-13:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:50-14:20 → middle 07:50-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 07:20-13:50 (Kennedy))
  false_positive: -3 (high 07:20-13:50 (Wtby Arts Magnet))
  false_positive: -3 (high 07:20-13:50 (Wtby Career Academy))
  false_positive: -3 (high 07:20-13:50 (Wilby))
  false_positive: -3 (middle 07:50-14:20 (Wallace))
  false_positive: -3 (middle 07:50-14:20 (West Side))
  false_positive: -3 (elementary 08:05-14:20 (Driggs))
  false_positive: -3 (elementary 08:05-14:20 (Duggan))
  false_positive: -3 (elementary 08:05-14:20 (Sprague))
  false_positive: -3 (elementary 08:05-14:20 (Tinker))
  false_positive: -3 (elementary 08:05-14:20 (Washington))
  false_positive: -3 (elementary 08:35-14:50 (Bunker Hill))
  false_positive: -3 (elementary 08:35-14:50 (Carrington))
  false_positive: -3 (elementary 08:35-14:50 (Chase))
  false_positive: -3 (elementary 08:35-14:50 (Cross, Wendell))
  false_positive: -3 (elementary 08:35-14:50 (Generali))
  false_positive: -3 (elementary 08:35-14:50 (Gilmartin))
  false_positive: -3 (elementary 08:35-14:50 (Hopeville))
  false_positive: -3 (elementary 08:35-14:50 (Kingsbury))
  false_positive: -3 (elementary 08:35-14:50 (Maloney))
  false_positive: -3 (elementary 08:35-14:50 (Reed))
  false_positive: -3 (elementary 08:35-14:50 (Regan))
  false_positive: -3 (elementary 08:35-14:50 (Walsh))
  false_positive: -3 (elementary 08:35-14:50 (Wilson))
  false_positive: -3 (elementary 09:05-15:20 (Roberto Clemente))
  false_positive: -3 (elementary 09:05-15:20 (Rotella))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:20'))

Total: 27 (entries) + -126 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 17 | Matched: 1

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

Total: 2 (entries) + -76 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 64 | Matched: 1

Entry Scores:
  elementary 08:00-14:00 → elementary 08:00-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 07:40-14:40 (unnamed) → 0/10
  MISSED: middle 09:30-16:10 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-13:45 (Colbert Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Cresthaven Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Dania Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Forest Hills Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Horizon Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Indian Trace Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Marshall, Thurgood Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Morrow Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Palmview Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Pines Lakes Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Silver Lakes Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Welleby Elementary))
  false_positive: -3 (elementary 07:55-13:55 (Lloyd Estates Elementary))
  false_positive: -3 (elementary 07:55-13:55 (Miramar Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Bayview Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Beachside Montessori Village))
  false_positive: -3 (elementary 08:00-14:00 (Bennett Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Boulevard Heights Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Broadview Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Broward Estates Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Castle Hill Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Central Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Chapel Trail Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Coconut Palm Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Collins Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Cooper City Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Coral Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Cypress Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Davie Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Deerfield Beach Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Dillard Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Discovery Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Dolphin Bay Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Drew, Charles Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Driftwood Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Eagle Point Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Eagle Ridge Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Embassy Creek Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Everglades Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Floranada Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Forest Hills Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Foster, Stephen Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Fox Trail Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Gator Run Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Griffin Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Harbordale Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Hawkes Bluff Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Heron Heights Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Hollywood Hills Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Hollywood Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Lake Forest Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Lakeside Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Larkdale Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Manatee Bay Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Maplewood Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Margate Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Markham, Robert C. Elementary))
  false_positive: -3 (elementary 08:00-14:00 (McNab Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Meadowbrook Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Mirror Lake Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Nob Hill Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Norcrest Elementary))
  false_positive: -3 (elementary 08:00-14:00 (North Andrews Gardens Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:55', '13:55'))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 9 (entries) + -313 (penalties) = 0/30 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 19 | Matched: 3

Entry Scores:
  high 07:20-14:20 → high 07:10-14:10 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  elementary 08:45-15:00 → elementary 08:15-15:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 09:30-16:04 → middle 08:45-15:00 | start=0/3 (Δ45m) end=0/3 (Δ64m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
  false_positive: -3 (elementary 08:15-15:30 (Eccleston))
  false_positive: -3 (elementary 08:15-15:30 (Orlo Vista))
  false_positive: -3 (elementary 08:15-15:30 (Engelwood))
  false_positive: -3 (elementary 08:15-15:30 (Hiawassee))
  false_positive: -3 (elementary 08:15-15:30 (Ivey Lane))
  false_positive: -3 (elementary 08:15-15:30 (Ridgewood Park))
  false_positive: -3 (elementary 08:15-15:30 (Washington Shores))
  false_positive: -3 (elementary 08:15-15:30 (Rock Lake))
  false_positive: -3 (elementary 08:15-15:30 (Rolling Hills))
  false_positive: -3 (elementary 08:15-15:30 (Rosemont))
  false_positive: -3 (elementary 08:15-15:30 (Wheatley))
  false_positive: -3 (elementary 08:15-15:30 (Tangelo Park))
  false_positive: -3 (middle 08:45-15:00 (Deerwood))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '08:45', '15:00'))

Total: 6 (entries) + -80 (penalties) = 0/30 (0.0%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:50 (Metro High School))

Total: 10 (entries) + -3 (penalties) = 7/20 (35.0%)

======================================================================
Des Moines Independent Comm School District (IA) - 1908970
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:15-15:15 → elementary 07:40-14:35 | start=0/3 (Δ35m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 08:30-15:25 (Des Moines Public Schools))
  false_positive: -3 (high 08:15-15:15 (Des Moines Public Schools))

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
  false_positive: -3 (middle 08:40-15:50 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))
  false_positive: -3 (high 08:40-15:48 (Thunder Ridge High School))
  duplicate_extraction: -2 (Duplicate: ('high', '08:40', '15:48'))

Total: 9 (entries) + -17 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 9 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-14:15 (Aborn))
  false_positive: -3 (middle 07:45-14:05 (Harold Durgin Success Academy))
  false_positive: -3 (middle 07:45-14:30 (Pickering Middle School))
  false_positive: -3 (middle 07:45-14:30 (Thurgood Marshall Middle School))
  false_positive: -3 (high 07:45-14:30 (Lynn English High School))
  false_positive: -3 (high 07:45-14:30 (Lynn Vocational Technical Institute))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))

Total: 20 (entries) + -24 (penalties) = 0/30 (0.0%)

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
  middle 08:15-14:30 → middle 08:15-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  elementary 08:55-15:00 → elementary 08:55-14:00 | start=3/3 (Δ0m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 08:00-14:00 → high 08:55-15:00 | start=0/3 (Δ55m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:50-14:00 (Grades 4-5))

Total: 15 (entries) + -3 (penalties) = 12/30 (40.0%)

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
  false_positive: -3 (elementary 08:25-15:20 (DeSoto Central Primary))
  false_positive: -3 (elementary 08:30-15:25 (DeSoto Central Elementary))
  false_positive: -3 (middle 08:00-15:40 (DeSoto Central Middle))
  false_positive: -3 (high 08:25-15:45 (DeSoto Central High))
  false_positive: -3 (elementary 07:40-14:35 (Hernando Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Oak Grove Central Elementary))
  false_positive: -3 (elementary 07:45-14:40 (Hernando Hills Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Hernando Intermediate School))
  false_positive: -3 (middle 07:15-14:50 (Hernando Middle))
  false_positive: -3 (high 07:30-14:55 (Hernando High))
  false_positive: -3 (elementary 07:45-14:40 (Horn Lake Elementary))
  false_positive: -3 (elementary 07:45-14:40 (Shadow Oaks Elementary))
  false_positive: -3 (elementary 07:40-14:20 (Horn Lake Intermediate))
  false_positive: -3 (middle 07:10-14:50 (Horn Lake Middle))
  false_positive: -3 (high 07:35-14:55 (Horn Lake High))
  false_positive: -3 (elementary 08:30-15:25 (Lake Cormorant Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Walls Elementary))
  false_positive: -3 (middle 08:00-15:40 (Lake Cormorant Middle))
  false_positive: -3 (high 08:25-15:45 (Lake Cormorant High))
  false_positive: -3 (elementary 07:40-14:40 (Lewisburg Primary))
  false_positive: -3 (elementary 07:40-14:40 (Lewisburg Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Lewisburg Intermediate))
  false_positive: -3 (middle 07:10-14:50 (Lewisburg Middle))
  false_positive: -3 (elementary 08:30-15:25 (Southaven Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Hope Sullivan Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Greenbrook Elementary))
  false_positive: -3 (elementary 08:25-15:20 (Southaven Intermediate))
  false_positive: -3 (middle 08:00-15:40 (Southaven Middle))
  false_positive: -3 (high 08:25-15:45 (Southaven High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:10', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '15:45'))

Total: 27 (entries) + -130 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 60 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:00-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Culler Middle School))
  false_positive: -3 (high 08:00-15:05 (Lincoln High School))
  false_positive: -3 (high 08:00-15:00 (Northwest High School))
  false_positive: -3 (middle 08:00-15:00 (Pound Middle School))
  false_positive: -3 (high 08:00-15:00 (Standing Bear High School))
  false_positive: -3 (middle 08:00-15:00 (Lux Middle School))
  false_positive: -3 (elementary 08:15-14:53 (Adams Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Arnold Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Beattie Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Belmont Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Brownell Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Calvert Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Campbell Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Cavett Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Clinton Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Eastridge Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Elliott Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Everett Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Fredstrom Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Hartley Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Hill Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Holmes Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Humann Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Huntington Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Kahoa Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Kloefkorn Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Kooser Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Lakeview Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Maxey Elementary))
  false_positive: -3 (elementary 09:00-15:38 (McPhee Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Meadow Lane Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Morley Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Norwood Park Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Pershing Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Prescott Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Pyrtle Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Randolph Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Riley Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Robinson Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Roper Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Rousseau Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Saratoga Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Sheridan Elementary))
  false_positive: -3 (elementary 09:00-15:38 (West Lincoln Elementary))
  false_positive: -3 (elementary 09:00-15:38 (Wysong Elementary))
  false_positive: -3 (elementary 08:15-14:53 (Zeman Elementary))
  false_positive: -3 (elementary 09:10-15:30 (Don D. Sherrill Education Center))
  false_positive: -3 (middle 08:00-15:00 (Dawes Middle School))
  false_positive: -3 (middle 08:00-15:00 (Goodrich Middle School))
  false_positive: -3 (middle 08:00-15:00 (Irving Middle School))
  false_positive: -3 (middle 08:00-15:00 (Lefler Middle School))
  false_positive: -3 (middle 08:00-15:00 (Lux Middle School))
  false_positive: -3 (middle 08:00-15:00 (Mickle Middle School))
  false_positive: -3 (middle 08:00-15:00 (Moore Middle School))
  false_positive: -3 (middle 08:00-15:00 (Park Middle School))
  false_positive: -3 (middle 08:00-15:00 (Pound Middle School))
  false_positive: -3 (middle 08:00-15:00 (Schoo Middle School))
  false_positive: -3 (middle 08:00-15:00 (Scott Middle School))
  false_positive: -3 (elementary 09:10-15:30 (Nuernberger Education Center))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:30'))

Total: 9 (entries) + -285 (penalties) = 0/10 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 68 | Matched: 1

Entry Scores:
  elementary 07:26-14:00 → elementary 09:30-15:30 | start=0/3 (Δ124m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:26-14:00 (Academy of Arts, Careers & Technology))
  false_positive: -3 (high 08:00-14:30 (Damonte Ranch))
  false_positive: -3 (high 07:26-14:00 (Debbie Smith CTE))
  false_positive: -3 (high 08:00-14:30 (Galena))
  false_positive: -3 (high 08:00-15:30 (Gerlach K-12))
  false_positive: -3 (high 07:45-14:34 (Hug))
  false_positive: -3 (high 07:45-14:30 (Incline))
  false_positive: -3 (high 08:30-14:57 (Innovations))
  false_positive: -3 (high 08:30-15:00 (Inspire Academy))
  false_positive: -3 (high 08:00-14:35 (McQueen))
  false_positive: -3 (high 08:00-14:35 (North Valleys))
  false_positive: -3 (high 08:00-14:35 (Reed))
  false_positive: -3 (high 07:40-14:30 (Reno))
  false_positive: -3 (high 08:00-14:30 (Spanish Springs))
  false_positive: -3 (high 08:00-14:35 (Sparks))
  false_positive: -3 (high 08:00-14:20 (TMCC))
  false_positive: -3 (high 09:50-16:00 (Transitions Academy))
  false_positive: -3 (high 08:00-14:30 (Turning Point))
  false_positive: -3 (high 08:00-14:30 (Wooster))
  false_positive: -3 (middle 07:30-14:00 (Billinghurst))
  false_positive: -3 (middle 07:30-14:00 (Clayton))
  false_positive: -3 (middle 07:30-14:00 (Cold Springs))
  false_positive: -3 (middle 07:30-14:00 (Depoali))
  false_positive: -3 (middle 07:30-14:00 (Desert Skies))
  false_positive: -3 (middle 07:30-14:00 (Dilworth))
  false_positive: -3 (middle 07:30-14:00 (Herz))
  false_positive: -3 (middle 07:50-14:25 (Incline))
  false_positive: -3 (middle 07:30-14:00 (Mendive))
  false_positive: -3 (middle 07:30-13:54 (O'Brien))
  false_positive: -3 (middle 07:30-14:00 (Pine))
  false_positive: -3 (middle 07:30-14:00 (Shaw))
  false_positive: -3 (middle 07:30-14:00 (Sky Ranch))
  false_positive: -3 (middle 07:30-14:00 (Sparks))
  false_positive: -3 (middle 07:30-14:00 (Swope))
  false_positive: -3 (middle 07:30-14:00 (Traner))
  false_positive: -3 (middle 07:25-14:00 (Vaughn))
  false_positive: -3 (elementary 09:00-15:00 (Anderson))
  false_positive: -3 (elementary 09:15-15:15 (Beasley))
  false_positive: -3 (elementary 09:00-15:00 (Beck))
  false_positive: -3 (elementary 09:00-15:00 (Bennett))
  false_positive: -3 (elementary 09:30-15:30 (Bohach))
  false_positive: -3 (elementary 09:00-15:00 (Booth))
  false_positive: -3 (elementary 09:30-15:30 (Brown))
  false_positive: -3 (elementary 09:30-15:30 (Cannan))
  false_positive: -3 (elementary 09:00-15:00 (Caughlin Ranch))
  false_positive: -3 (elementary 09:30-15:30 (Corbett))
  false_positive: -3 (elementary 09:30-15:30 (Desert Heights))
  false_positive: -3 (elementary 08:45-14:45 (Diedrichsen))
  false_positive: -3 (elementary 09:00-15:00 (Dodson))
  false_positive: -3 (elementary 09:30-15:30 (Donner Springs))
  false_positive: -3 (elementary 09:15-15:15 (Double Diamond))
  false_positive: -3 (elementary 09:00-15:00 (Drake))
  false_positive: -3 (elementary 09:00-15:00 (Duncan))
  false_positive: -3 (elementary 09:00-15:00 (Dunn))
  false_positive: -3 (elementary 09:00-15:00 (Elmcrest))
  false_positive: -3 (elementary 09:00-15:00 (Gomes))
  false_positive: -3 (elementary 09:30-15:30 (Gomm))
  false_positive: -3 (elementary 09:00-15:00 (Greenbrae))
  false_positive: -3 (elementary 09:00-15:00 (Hall))
  false_positive: -3 (elementary 09:00-15:00 (Hidden Valley))
  false_positive: -3 (elementary 09:30-15:30 (Huffaker))
  false_positive: -3 (elementary 09:30-15:30 (Hunsberger))
  false_positive: -3 (elementary 09:00-15:00 (Hunter Lake))
  false_positive: -3 (elementary 09:20-15:20 (Incline))
  false_positive: -3 (elementary 09:30-15:30 (Inskeep))
  false_positive: -3 (elementary 09:00-15:00 (Juniper))
  false_positive: -3 (elementary 09:00-15:00 (JWood Raw))
  duplicate_extraction: -2 (Duplicate: ('high', '07:26', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))

Total: 2 (entries) + -297 (penalties) = 0/10 (0.0%)

======================================================================
Cincinnati Public Schools (OH) - 3904375
======================================================================
Ground truth: 1 entries | Extracted: 11 | Matched: 1

Entry Scores:
  elementary 08:00-14:30 → elementary 07:40-14:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:40-14:10 (CANS))
  false_positive: -3 (elementary 07:40-14:10 (Rockdale Academy))
  false_positive: -3 (elementary 07:40-14:10 (Roll Hill School))
  false_positive: -3 (elementary 09:10-15:40 (James N. Gamble Montessori Elementary))
  false_positive: -3 (elementary 09:10-15:40 (North Avondale Montessori School))
  false_positive: -3 (elementary 09:10-15:40 (Roberts Academy))
  false_positive: -3 (elementary 09:10-15:40 (Roselawn Condon School))
  false_positive: -3 (middle 08:00-15:00 (Pleasant Hill Middle School))
  false_positive: -3 (high 08:00-15:00 (James N. Gamble Montessori High School))
  false_positive: -3 (high 08:00-15:00 (Dr. O'dell Owens Center for Learning))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))

Total: 2 (entries) + -44 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  middle 08:35-15:05 → middle 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:35-15:05 → high 08:00-15:00 | start=0/3 (Δ35m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=0/1 = 3/10
  elementary 08:35-15:05 → elementary 07:35-14:05 | start=0/3 (Δ60m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 14 (entries) + 0 (penalties) = 14/30 (46.7%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 07:30-14:30 (Westford School))
  false_positive: -3 (middle 08:35-15:35 (Essex Middle School))
  false_positive: -3 (high 08:40-15:15 (Essex High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))

Total: 9 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Champlain Valley Unified Union School District #56 (VT) - 5000396
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 07:50-14:35 | start=3/3 (Δ0m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 07:45-14:45 (Charlotte Central School))
  false_positive: -3 (elementary 07:45-14:45 (Shelburne Community School))
  false_positive: -3 (elementary 07:55-14:45 (Williston Central School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:45'))

Total: 5 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:10-14:50 | start=1/3 (Δ2m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (high 08:10-14:35 (Burlington High School))
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle School))

Total: 7 (entries) + -6 (penalties) = 1/10 (10.0%)

======================================================================
BERKELEY COUNTY SCHOOLS (WV) - 5400060
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  high 07:28-14:38 → high 07:28-14:38 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:55-15:30 → elementary 08:20-15:20 | start=0/3 (Δ25m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 07:30-14:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)

Total: 11 (entries) + -2 (penalties) = 9/30 (30.0%)

======================================================================
CABELL COUNTY SCHOOLS (WV) - 5400180
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  middle 07:27-15:06 → middle 07:15-14:55 | start=0/3 (Δ12m) end=0/3 (Δ11m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:20-14:42 (Huntington High School))
  false_positive: -3 (middle 07:27-14:20 (Huntington Middle School))
  false_positive: -3 (high 07:15-14:45 (Cabell Midland High School))

Total: 2 (entries) + -9 (penalties) = 0/10 (0.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 07:15-14:15 → elementary 07:45-14:15 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (middle 08:15-14:38 (Horace Mann Middle))
  false_positive: -3 (middle 08:15-15:10 (Elkview Middle))
  false_positive: -3 (elementary 07:45-14:12 (Anne Bailey Elementary))
  false_positive: -3 (high 08:36-15:36 (Nitro High))

Total: 5 (entries) + -12 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 07:50-15:15 → elementary 07:45-15:00 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 08:00-15:55 → high 07:45-16:05 | start=0/3 (Δ15m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 9 (entries) + 0 (penalties) = 9/30 (30.0%)