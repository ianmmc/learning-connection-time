# Benchmark Report: openrouter:deepseek/deepseek-v4-pro
Run date: 2026-06-14T00:44:30
Districts tested: 40
Total extraction time: 1546s (avg 38.6s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 18.7% |
| JSON parse success | 70.0% |
| Grade coverage rate | 91.7% |
| False positive rate | 5.42/district |
| Mean time/extraction | 38.6s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Matanuska-Susitna Borough Scho | AK | 9 | 10 | 90.0% |  |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 27 | 30 | 90.0% |  |  |
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| Albany County School District  | WY | 27 | 30 | 90.0% |  |  |
| Sweetwater County School Distr | WY | 20 | 30 | 66.7% | false_positive |  |
| Montgomery County | AL | 18 | 30 | 60.0% |  |  |
| Burlington School District | VT | 3 | 10 | 30.0% | false_positive, false_positive |  |
| BERKELEY COUNTY SCHOOLS | WV | 9 | 30 | 30.0% | missing_grade_level |  |
| Cedar Rapids Comm School Distr | IA | 4 | 20 | 20.0% | false_positive, false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+21 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+10 more) |  |
| Mobile County | AL | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| SPRINGDALE SCHOOL DISTRICT | AR | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Mesa Unified District (4235) | AZ | 0 | 20 | 0.0% | json_parse_failure | JSON failure |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | json_parse_failure | JSON failure |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | extraction_error |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+60 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+45 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+18 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+27 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| BROWARD | FL | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| ORANGE | FL | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| Bangor Public Schools | ME | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+8 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Washoe County | NV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+60 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+13 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | json_parse_failure | JSON failure |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |

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
Ground truth: 1 entries | Extracted: 16 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (ANNE WIEN ELEMENTARY))
  false_positive: -3 (elementary 08:00-14:30 (ARCTIC LIGHT ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (DENALI ELEMENTARY))
  false_positive: -3 (elementary 08:00-14:30 (HUNTER ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (HUTCHISON HIGH))
  false_positive: -3 (elementary 09:15-15:45 (LADD ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (LATHROP HIGH))
  false_positive: -3 (elementary 09:00-15:30 (NORTH POLE ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (NORTH POLE HIGH))
  false_positive: -3 (middle 07:50-14:20 (NORTH POLE MIDDLE))
  false_positive: -3 (middle 07:50-14:20 (RANDY SMITH MIDDLE))
  false_positive: -3 (middle 07:50-14:20 (RYAN MIDDLE))
  false_positive: -3 (elementary 09:15-15:45 (SALCHA ELEMENTARY))
  false_positive: -3 (middle 07:55-14:25 (TANANA MIDDLE))
  false_positive: -3 (elementary 09:00-15:30 (TICASUK BROWN ELEMENTARY))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:30'))

Total: 9 (entries) + -63 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 10 | Matched: 1

Entry Scores:
  elementary 07:15-14:45 → elementary 07:40-14:40 | start=0/3 (Δ25m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (high 07:50-15:15 (Baldwin County High))
  false_positive: -3 (middle 07:45-15:05 (Daphne Middle))
  false_positive: -3 (high 07:50-15:10 (Daphne High))
  false_positive: -3 (middle 07:45-15:03 (Elberta Middle))
  false_positive: -3 (high 08:00-15:15 (Fairhope High))
  false_positive: -3 (middle 07:45-15:05 (Fairhope Middle))
  false_positive: -3 (high 07:50-15:10 (Robertsdale High))
  false_positive: -3 (middle 07:45-15:05 (Spanish Fort Middle))
  false_positive: -3 (elementary 07:40-14:40 (Stapleton Elementary))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:40'))

Total: 3 (entries) + -35 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:30-14:45 → middle 07:45-14:45 | start=0/3 (Δ15m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:15-14:45 → high 07:45-14:45 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Total: 18 (entries) + 0 (penalties) = 18/30 (60.0%)

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
Ground truth: 3 entries | Extracted: 5 | Matched: 2

Entry Scores:
  middle 08:05-15:30 → middle 08:05-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:05-15:30 → elementary 07:45-15:20 | start=0/3 (Δ20m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-15:15 (Harp Elementary))
  false_positive: -3 (middle 08:05-15:30 (Sonora Middle School))
  false_positive: -3 (elementary 07:45-15:20 (Bayyari Elementary))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:05', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:20'))
  missing_grade_level: -2 (Missing: high)

Total: 11 (entries) + -15 (penalties) = 0/30 (0.0%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/20 (0.0%)

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
  false_positive: -3 (high 09:00-13:54 (Conley-Caraballo High))
  false_positive: -3 (middle 08:15-14:44 (César Chávez Middle))
  false_positive: -3 (elementary 08:00-14:05 (Delaine Eastin Elementary))
  false_positive: -3 (elementary 08:00-14:05 (Searles Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))

Total: 5 (entries) + -16 (penalties) = 0/10 (0.0%)

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
  false_positive: -3 (middle 07:50-14:20 (Curiale))
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
  false_positive: -3 (middle 07:50-14:20 (Read))
  false_positive: -3 (elementary 08:50-15:10 (Roosevelt))
  false_positive: -3 (elementary 08:50-15:10 (Thomas Hooker))
  false_positive: -3 (elementary 08:50-15:10 (Waltersville))
  false_positive: -3 (elementary 08:50-15:10 (Wilbur Cross))
  false_positive: -3 (elementary 08:15-14:00 (Bpt. Learning Ctr.))
  false_positive: -3 (high 07:53-14:30 (Bassick))
  false_positive: -3 (high 07:53-14:30 (Central))
  false_positive: -3 (high 07:53-14:30 (Harding))
  false_positive: -3 (high 08:15-14:00 (Brpt. Learning Ctr.))
  false_positive: -3 (high 07:50-14:05 (Fairchild Wheeler))
  false_positive: -3 (high 07:55-14:10 (Bpt. Military Academy))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))

Total: 9 (entries) + -163 (penalties) = 0/10 (0.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 38 | Matched: 3

Entry Scores:
  middle 07:50-14:20 → middle 07:55-14:30 | start=1/3 (Δ5m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 3/10
  elementary 08:45-15:00 → elementary 08:35-14:50 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  high 07:20-13:50 → high 07:30-14:00 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:05 (Cooperative Arts and Humanities Magnet High School))
  false_positive: -3 (high 07:30-14:15 (Metro Bus. Academy))
  false_positive: -3 (high 07:10-14:05 (New Haven Academy))
  false_positive: -3 (high 13:00-16:00 (Platt Tech))
  false_positive: -3 (high 07:30-14:17 (Sound School))
  false_positive: -3 (high 07:10-14:15 (Riverside))
  false_positive: -3 (high 07:10-14:05 (HSC HS))
  false_positive: -3 (elementary 09:15-15:30 (John Martinez))
  false_positive: -3 (elementary 09:15-15:30 (Jepson))
  false_positive: -3 (elementary 07:45-14:15 (John Daniels))
  false_positive: -3 (elementary 07:55-14:10 (King-Robinson))
  false_positive: -3 (elementary 08:35-14:50 (Nathan Hale))
  false_positive: -3 (elementary 09:15-15:30 (Roberto Clemente))
  false_positive: -3 (elementary 09:15-15:30 (Ross-Woodward))
  false_positive: -3 (elementary 07:30-14:00 (Mauro-Sheridan))
  false_positive: -3 (elementary 08:35-14:50 (Wexler (WG)))
  false_positive: -3 (elementary 07:55-14:10 (Troup))
  false_positive: -3 (elementary 08:35-14:50 (Truman))
  false_positive: -3 (elementary 09:00-15:15 (Chart))
  false_positive: -3 (elementary 07:00-14:30 (Edmonds Cofield Prep))
  false_positive: -3 (elementary 08:30-16:00 (Cold Spring))
  false_positive: -3 (elementary 08:10-15:00 (Foote))
  false_positive: -3 (elementary 07:40-15:30 (Hopkins))
  false_positive: -3 (elementary 07:45-14:15 (All Saints Catholic))
  false_positive: -3 (elementary 07:30-17:15 (St. Martin))
  false_positive: -3 (elementary 08:15-15:00 (St. Thomas))
  false_positive: -3 (elementary 07:30-14:00 (Elm City Elem))
  false_positive: -3 (middle 07:00-14:11 (Highville Charter K-8))
  false_positive: -3 (high 08:00-14:30 (Highville Charter HS))
  false_positive: -3 (elementary 07:30-14:05 (B. T. Washington Elem))
  false_positive: -3 (middle 07:30-14:10 (B. T. Washington Middle))
  false_positive: -3 (elementary 07:45-15:10 (Adult Education))
  false_positive: -3 (elementary 08:35-14:50 (Dr. Mayo ECLC SPED))
  false_positive: -3 (elementary 09:15-15:30 (Dr. Mayo ECLC H1))
  false_positive: -3 (elementary 08:35-14:50 (Dr. Mayo ECLC H2))
  duplicate_extraction: -2 (Duplicate: ('high', '07:10', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:55', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))

Total: 7 (entries) + -131 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 14 | Matched: 3

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
  false_positive: -3 (middle 07:20-13:50 (Wtby Arts Magnet))
  false_positive: -3 (middle 07:50-14:20 (West Side))
  false_positive: -3 (elementary 08:35-14:50 (Bunker Hill))
  false_positive: -3 (elementary 08:35-14:50 (Carrington))
  false_positive: -3 (elementary 08:35-14:50 (Chase))
  false_positive: -3 (elementary 08:35-14:50 (Cross, Wendell))
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

Total: 27 (entries) + -53 (penalties) = 0/30 (0.0%)

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
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 4 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:50 (Washington High School))
  false_positive: -3 (high 08:20-15:00 (Metro High School))

Total: 10 (entries) + -6 (penalties) = 4/20 (20.0%)

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
  false_positive: -3 (high 08:40-15:48 (Thunder Ridge High School))
  false_positive: -3 (middle 08:40-15:45 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))
  duplicate_extraction: -2 (Duplicate: ('high', '08:40', '15:48'))

Total: 9 (entries) + -17 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
Worcester (MA) - 2513230
======================================================================
Ground truth: 1 entries | Extracted: 8 | Matched: 1

Entry Scores:
  middle 08:47-14:17 → middle 08:47-15:10 | start=3/3 (Δ0m) end=0/3 (Δ53m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:20-13:43 (Burncoat High))
  false_positive: -3 (high 07:20-13:43 (North High))
  false_positive: -3 (high 07:20-13:43 (Worcester Technical High))
  false_positive: -3 (elementary 08:15-14:20 (Belmont Street Community))
  false_positive: -3 (elementary 07:55-14:00 (Elm Park Community))
  false_positive: -3 (elementary 08:25-14:30 (Grafton Street))
  false_positive: -3 (elementary 08:25-14:30 (May Street))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '14:30'))

Total: 5 (entries) + -27 (penalties) = 0/10 (0.0%)

======================================================================
Bangor Public Schools (ME) - 2302820
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (JSONDecodeError: Expecting value: line 175 column 1 (char 957))

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

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
Ground truth: 3 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 41 | Matched: 1

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
  false_positive: -3 (middle 07:30-14:00 (Clayton-Pre AP))
  false_positive: -3 (middle 07:30-14:00 (Cold Springs))
  false_positive: -3 (middle 07:30-14:00 (Depoali))
  false_positive: -3 (middle 07:30-14:00 (Desert Skies))
  false_positive: -3 (middle 07:30-14:00 (Dilworth-STEM))
  false_positive: -3 (middle 07:30-14:00 (Herz))
  false_positive: -3 (middle 07:50-14:25 (Incline))
  false_positive: -3 (middle 07:30-14:00 (Mendive))
  false_positive: -3 (middle 07:30-13:54 (O'Brien-STEM))
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

Total: 2 (entries) + -166 (penalties) = 0/10 (0.0%)

======================================================================
Cincinnati Public Schools (OH) - 3904375
======================================================================
Ground truth: 1 entries | Extracted: 11 | Matched: 1

Entry Scores:
  elementary 08:00-14:30 → elementary 08:00-15:00 | start=3/3 (Δ0m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 07:40-14:10 (AWL))
  false_positive: -3 (elementary 07:40-14:10 (Rockdale Academy))
  false_positive: -3 (elementary 09:10-15:40 (Roselawn Condon School))
  false_positive: -3 (elementary 07:40-14:10 (CANS (Clifton Area Neighborhood School)))
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

Total: 5 (entries) + -42 (penalties) = 0/10 (0.0%)

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
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 07:50-14:35 | start=3/3 (Δ0m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 07:45-14:43 (Charlotte Central School))
  false_positive: -3 (middle 07:45-14:40 (Charlotte Central School))
  false_positive: -3 (elementary,middle 07:45-14:45 (Shelburne Community School))
  false_positive: -3 (middle 07:55-14:45 (Williston Central School))

Total: 5 (entries) + -12 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:08-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:10-14:50 (Edmunds Elementary))
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

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
  high 07:45-15:45 → high 07:45-15:45 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:05 → middle 08:00-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 27 (entries) + 0 (penalties) = 27/30 (90.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-15:15 (4-6 Elementary Schools))

Total: 23 (entries) + -3 (penalties) = 20/30 (66.7%)