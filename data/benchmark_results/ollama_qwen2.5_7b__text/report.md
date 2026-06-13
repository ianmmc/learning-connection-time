# Benchmark Report: ollama:qwen2.5:7b
Run date: 2026-06-12T04:31:56
Districts tested: 40
Total extraction time: 2502s (avg 62.5s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 8.8% |
| JSON parse success | 100.0% |
| Grade coverage rate | 69.0% |
| False positive rate | 3.58/district |
| Mean time/extraction | 62.5s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| LINCOLN PUBLIC SCHOOLS | NE | 5 | 10 | 50.0% | missing_grade_level |  |
| Bangor Public Schools | ME | 10 | 30 | 33.3% |  |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 9 | 30 | 30.0% | missing_grade_level |  |
| Essex Westford Educational Com | VT | 3 | 10 | 30.0% | false_positive, false_positive |  |
| Montgomery County | AL | 6 | 30 | 20.0% |  |  |
| Christina School District | DE | 2 | 10 | 20.0% |  |  |
| Cleveland Municipal | OH | 6 | 30 | 20.0% | false_positive, false_positive |  |
| Sweetwater County School Distr | WY | 6 | 30 | 20.0% | false_positive |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 5 | 30 | 16.7% | missing_grade_level, missing_grade_level |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+35 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Mesa Unified District (4235) | AZ | 0 | 20 | 0.0% | false_positive, missing_grade_level, missing_grade_level |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | extraction_error |  |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | extraction_error |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+33 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | missing_grade_level, missing_grade_level |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+47 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, missing_grade_level |  |
| BROWARD | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+53 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | extraction_error |  |
| Cedar Rapids Comm School Distr | IA | 0 | 20 | 0.0% | false_positive, false_positive, missing_grade_level (+1 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, missing_grade_level, missing_grade_level |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | extraction_error |  |
| Washoe County | NV | 0 | 10 | 0.0% | extraction_error |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive |  |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BERKELEY COUNTY SCHOOLS | WV | 0 | 30 | 0.0% | extraction_error |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| Albany County School District  | WY | 0 | 30 | 0.0% | extraction_error |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 08:15-14:25 | start=0/3 (Δ30m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (Big Lake Elementary School))

Total: 2 (entries) + -3 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 26 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (ANNE WIEN ELEMENTARY))
  false_positive: -3 (elementary 08:00-14:30 (ARCTIC LIGHT ELEMENTARY))
  false_positive: -3 (middle 08:15-14:45 (BARNETTE MAGNET))
  false_positive: -3 (elementary 08:45-13:15 (BOREAL SUN CHARTER))
  false_positive: -3 (elementary 08:15-12:45 (CHINOOK MONTESSORI CHARTER))
  false_positive: -3 (elementary 09:15-15:45 (DENALI ELEMENTARY))
  false_positive: -3 (elementary 08:00-13:30 (DISCOVERY PEAK CHARTER))
  false_positive: -3 (elementary 09:50-15:45 (EFFIE KOKRINE CHARTER))
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
  false_positive: -3 (elementary 09:15-15:45 (UNIVERSITY PARK ELEMENTARY))
  false_positive: -3 (elementary 08:30-12:30 (WATERSHED CHARTER))
  false_positive: -3 (elementary 09:15-15:45 (WELLER ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (WEST VALLEY HIGH))
  false_positive: -3 (elementary 09:15-15:45 (WOODRIVER ELEMENTARY))
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

Total: 9 (entries) + -101 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 0

Entry Scores:
  MISSED: elementary 07:15-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:00-15:05 (Baldwin County High School))
  false_positive: -3 (middle 07:45-15:03 (Daphne Middle School))
  false_positive: -3 (high 08:00-15:05 (Fairhope High School))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:05'))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -13 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:10-15:35 | start=0/3 (Δ10m) end=0/3 (Δ70m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 07:05-14:30 (Pillans Middle School))
  false_positive: -3 (high 07:05-14:35 (Mary G Montgomery High School))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  high 07:15-14:45 → high 07:25-14:35 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  elementary 08:10-15:10 → elementary 07:25-14:35 | start=0/3 (Δ45m) end=0/3 (Δ35m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 07:30-14:45 → middle 08:10-15:15 | start=0/3 (Δ40m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 6 (entries) + 0 (penalties) = 6/30 (20.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 08:45-16:00 (unnamed) → 0/10
  MISSED: middle 08:45-16:00 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 9 (entries) + -4 (penalties) = 5/30 (16.7%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  elementary 08:05-15:30 → elementary 07:10-15:30 | start=0/3 (Δ55m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 6/10
  middle 08:05-15:30 → middle 08:05-14:30 | start=3/3 (Δ0m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 5/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: high)

Total: 11 (entries) + -2 (penalties) = 9/30 (30.0%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 07:50-13:50 (unnamed) → 0/10
  MISSED: middle 08:00-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:15-14:37 (Red Mountain High))
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
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
New Haven Unified (CA) - 0626910
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:30-14:05 → elementary 08:00-14:05 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 08:00-14:35 (Core & Alternative Learning Academy at Conley-Caraballo High School))
  false_positive: -3 (middle 08:15-14:27 (César Chávez Middle School))

Total: 5 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 23 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:50-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

Penalties:
  false_positive: -3 (elementary 08:50-12:50 (Blackham))
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
  false_positive: -3 (high 07:53-14:30 (Bassick))
  false_positive: -3 (high 07:53-11:53 (Central))
  false_positive: -3 (high 07:53-14:30 (Harding))
  false_positive: -3 (high 08:15-11:53 (Bpt. Learning Ctr.))
  false_positive: -3 (high 07:50-12:05 (Fairchild Wheeler))
  false_positive: -3 (high 07:55-12:10 (Bpt. Military Academy))
  false_positive: -3 (high 08:00-12:05 (Aquaculture))
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
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))

Total: 8 (entries) + -94 (penalties) = 0/10 (0.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high 07:20-13:50 → high 07:30-14:15 | start=0/3 (Δ10m) end=0/3 (Δ25m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: elementary 08:45-15:00 (unnamed) → 0/10
  MISSED: middle 07:50-14:20 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: elementary)

Total: 2 (entries) + -4 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 29 | Matched: 3

Entry Scores:
  elementary 08:35-14:50 → elementary 08:35-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:50-14:20 → middle 07:50-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-13:50 → high 08:10-14:35 | start=0/3 (Δ50m) end=0/3 (Δ45m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:10-14:35 (Kennedy))
  false_positive: -3 (high 08:10-14:35 (Wtby Arts Magnet))
  false_positive: -3 (high 08:10-14:35 (Wtby Career Academy))
  false_positive: -3 (high 08:10-14:35 (Wilby))
  false_positive: -3 (middle 07:50-14:20 (Wallace))
  false_positive: -3 (middle 07:50-14:20 (West Side))
  false_positive: -3 (elementary 08:35-14:50 (Bunker Hill))
  false_positive: -3 (elementary 08:35-14:50 (Carrington))
  false_positive: -3 (elementary 08:35-14:50 (Chase))
  false_positive: -3 (elementary 08:35-14:50 (Cross, Wendell))
  false_positive: -3 (elementary 08:05-14:20 (Driggs))
  false_positive: -3 (elementary 08:05-14:20 (Duggan))
  false_positive: -3 (elementary 08:35-14:50 (Generali))
  false_positive: -3 (elementary 08:35-14:50 (Gilmartin))
  false_positive: -3 (elementary 08:35-14:50 (Hopeville))
  false_positive: -3 (elementary 08:35-14:50 (Kingsbury))
  false_positive: -3 (elementary 08:35-14:50 (Maloney))
  false_positive: -3 (elementary 08:35-14:50 (Reed))
  false_positive: -3 (elementary 08:35-14:50 (Regan))
  false_positive: -3 (elementary 09:05-15:20 (Roberto Clemente))
  false_positive: -3 (elementary 09:05-15:20 (Rotella))
  false_positive: -3 (elementary 08:05-14:20 (Sprague))
  false_positive: -3 (elementary 08:05-14:20 (Tinker))
  false_positive: -3 (elementary 08:35-14:50 (Walsh))
  false_positive: -3 (elementary 08:05-14:20 (Washington))
  false_positive: -3 (elementary 08:35-14:50 (Wilson))
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

Total: 20 (entries) + -126 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 6 | Matched: 1

Entry Scores:
  high 07:30-14:30 → high 08:20-15:00 | start=0/3 (Δ50m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 07:30-14:10 (Everett Meredith MS))
  false_positive: -3 (middle 07:30-14:10 (Louis L. Redding MS))
  false_positive: -3 (middle 07:30-14:10 (Alfred G. Waters MS))
  false_positive: -3 (middle 07:30-14:10 (Cantwell’s Bridge MS))
  false_positive: -3 (elementary 09:10-15:50 (Brick Mill ES/ECC))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:10'))

Total: 2 (entries) + -21 (penalties) = 0/10 (0.0%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:00-15:00 → elementary 07:00-14:41 | start=0/3 (Δ60m) end=0/3 (Δ19m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 2 (entries) + 0 (penalties) = 2/10 (20.0%)

======================================================================
Red Clay Consolidated School District (DE) - 1001300
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 09:05-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:25-14:35 (McKean High))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
BROWARD (FL) - 1200180
======================================================================
Ground truth: 3 entries | Extracted: 32 | Matched: 2

Entry Scores:
  elementary 08:00-14:00 → elementary 08:00-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 07:40-14:40 → high 07:40-14:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: middle 09:30-16:10 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:50-13:50 (Banyan Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Beachside Montessori Village))
  false_positive: -3 (elementary 08:00-14:00 (Bennett Elementary))
  false_positive: -3 (elementary 08:45-15:15 (Bethune, Mary M. Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Boulevard Heights Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Broadview Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Challenger Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Coconut Creek K-8 Academy of Excellence))
  false_positive: -3 (elementary 08:00-14:00 (Coconut Palm Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Colbert Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Collins Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Cooper City Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Cypress Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Dania Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Davie Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Deerfield Beach Elementary))
  false_positive: -3 (elementary 08:30-15:00 (Deerfield Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Dillard Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Discovery Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Driftwood Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Eagle Point Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Eagle Ridge Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Endeavor Primary Learning Center))
  false_positive: -3 (elementary 08:00-14:00 (Everglades Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Fairway Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Floranada Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Forest Hills Elementary))
  false_positive: -3 (high 07:40-14:40 (Taravella, J.P. High))
  false_positive: -3 (high 07:40-14:40 (West Broward High))
  false_positive: -3 (high 07:40-14:40 (Western High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  missing_grade_level: -2 (Missing: middle)

Total: 16 (entries) + -142 (penalties) = 0/30 (0.0%)

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
Ground truth: 2 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 08:50-14:20 (unnamed) → 0/10
  MISSED: middle 07:50-13:55 (unnamed) → 0/10

Penalties:
  false_positive: -3 (unknown 08:50-03:50 (None))
  false_positive: -3 (unknown 07:50-02:20 (None))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -10 (penalties) = 0/20 (0.0%)

======================================================================
Des Moines Independent Comm School District (IA) - 1908970
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:15-15:15 → elementary 07:40-14:35 | start=0/3 (Δ35m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 08:30-15:25 (None))
  false_positive: -3 (high 08:15-15:15 (None))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
BONNEVILLE JOINT DISTRICT (ID) - 1600930
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 08:40-15:48 → high 08:35-13:48 | start=1/3 (Δ5m) end=0/3 (Δ120m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (middle 08:40-13:50 (Rocky Mountain Middle))
  false_positive: -3 (elementary 08:00-12:46 (Ammon Elementary))

Total: 3 (entries) + -6 (penalties) = 0/10 (0.0%)

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
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 2 (entries) + -7 (penalties) = 0/30 (0.0%)

======================================================================
Worcester (MA) - 2513230
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 0

Entry Scores:
  MISSED: middle 08:47-14:17 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:20-13:43 (Burncoat High School))
  false_positive: -3 (high 07:20-13:43 (North High School))
  false_positive: -3 (high 07:20-13:43 (Worcester Technical High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  missing_grade_level: -2 (Missing: middle)

Total: 0 (entries) + -15 (penalties) = 0/10 (0.0%)

======================================================================
Bangor Public Schools (ME) - 2302820
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:55-15:00 → elementary 08:35-15:00 | start=0/3 (Δ20m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 08:00-14:00 → high 07:45-14:35 | start=0/3 (Δ15m) end=0/3 (Δ35m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 08:15-14:30 → middle 07:30-16:30 | start=0/3 (Δ45m) end=0/3 (Δ120m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 10 (entries) + 0 (penalties) = 10/30 (33.3%)

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
DESOTO CO SCHOOL DIST (MS) - 2801320
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high 08:00-15:00 → middle 08:00-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

Penalties:
  missing_grade_level: -2 (Missing: high)

Total: 7 (entries) + -2 (penalties) = 5/10 (50.0%)

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
  elementary 08:00-14:30 → elementary 07:40-14:10 | start=0/3 (Δ20m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Pleasant Hill Middle School))
  false_positive: -3 (high 08:00-15:00 (James N. Gamble Montessori High School))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 08:35-15:05 → high 08:25-14:55 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 08:35-15:05 → middle 07:35-14:05 | start=0/3 (Δ60m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (elementary 09:35-16:05 (Adlai E. Stevenson, Franklin D. Roosevelt, Albert B. Hart, Almira, Anton Grdina, Andrew J. Rickoff, Artemus Ward, Benjamin Franklin, Bolototalerateee, Bunerotalerateee, Charles Dickens, Clara E. Westropp, Clark, Cleveland Metro Remote School, Daniel E. Morgan, Denison, Dike School of the Arts, Douglas MacArthur Girls’, East Clark, Euclid Park))

Total: 12 (entries) + -6 (penalties) = 6/30 (20.0%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 08:35-15:35 (Essex Middle School))
  false_positive: -3 (high 08:40-14:35 (Essex High School))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

======================================================================
Champlain Valley Unified Union School District #56 (VT) - 5000396
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 07:45-14:35 | start=1/3 (Δ5m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (elementary 07:35-14:35 (Allen Brook School))

Total: 3 (entries) + -3 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:10-14:30 | start=1/3 (Δ2m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle School))
  false_positive: -3 (high 08:10-14:35 (Burlington High School))

Total: 3 (entries) + -6 (penalties) = 0/10 (0.0%)

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
  high 08:00-15:55 → high 07:45-16:05 | start=0/3 (Δ15m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 09:00-13:00 (Overland Elementary School - Part-day Preschool))

Total: 9 (entries) + -3 (penalties) = 6/30 (20.0%)