# Benchmark Report: gemini:gemini-2.5-flash
Run date: 2026-06-13T21:25:48
Districts tested: 40
Total extraction time: 1219s (avg 30.5s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 14.9% |
| JSON parse success | 100.0% |
| Grade coverage rate | 86.7% |
| False positive rate | 20.27/district |
| Mean time/extraction | 30.5s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| Albany County School District  | WY | 24 | 30 | 80.0% |  |  |
| Bangor Public Schools | ME | 22 | 30 | 73.3% | false_positive |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 19 | 30 | 63.3% | false_positive, false_positive, duplicate_extraction |  |
| Matanuska-Susitna Borough Scho | AK | 3 | 10 | 30.0% | false_positive, false_positive |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 7 | 30 | 23.3% | missing_grade_level |  |
| Christina School District | DE | 2 | 10 | 20.0% |  |  |
| Sweetwater County School Distr | WY | 6 | 30 | 20.0% | false_positive, false_positive, false_positive (+3 more) |  |
| BERKELEY COUNTY SCHOOLS | WV | 5 | 30 | 16.7% | missing_grade_level, missing_grade_level |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+37 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+38 more) |  |
| Mesa Unified District (4235) | AZ | 0 | 20 | 0.0% | false_positive, missing_grade_level |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | extraction_error |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+60 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+81 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+55 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+30 more) |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, missing_grade_level |  |
| BROWARD | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+168 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+323 more) |  |
| Cedar Rapids Comm School Distr | IA | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+50 more) |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+8 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+47 more) |  |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+53 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+180 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+13 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+168 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (Big Lake Elementary School))
  false_positive: -3 (middle 07:45-14:15 (Teeland Middle School))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 26 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (ANNE WIEN ELEMENTARY))
  false_positive: -3 (elementary 08:00-14:30 (ARCTIC LIGHT ELEMENTARY))
  false_positive: -3 (elementary 08:15-14:45 (BARNETTE MAGNET))
  false_positive: -3 (elementary 08:45-15:15 (BOREAL SUN CHARTER))
  false_positive: -3 (elementary 08:15-14:45 (CHINOOK MONTESSORI CHARTER))
  false_positive: -3 (elementary 09:15-15:45 (DENALI ELEMENTARY))
  false_positive: -3 (elementary 08:00-14:30 (DISCOVERY PEAK CHARTER))
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
  false_positive: -3 (elementary 08:30-15:00 (WATERSHED CHARTER))
  false_positive: -3 (elementary 09:15-15:45 (WELLER ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (WEST VALLEY HIGH))
  false_positive: -3 (elementary 09:15-15:45 (WOODRIVER ELEMENTARY))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
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

Total: 9 (entries) + -105 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 0

Entry Scores:
  MISSED: elementary 07:15-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:50-15:10 (Daphne High School))
  false_positive: -3 (middle 07:45-15:03 (Elberta Middle School))
  false_positive: -3 (middle 07:45-15:05 (Spanish Fort Middle School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:15-14:45 | start=0/3 (Δ15m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:15-14:25 (Mary G Montgomery High School))
  false_positive: -3 (elementary 08:05-15:10 (Allentown Elementary School))
  false_positive: -3 (middle 07:20-14:30 (Pillans Middle School))
  false_positive: -3 (elementary 08:10-15:25 (Tanner Williams Elementary School))

Total: 2 (entries) + -12 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 34 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:45 → middle 07:30-14:45 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:15-14:45 → high 07:20-14:45 | start=1/3 (Δ5m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (elementary 08:10-15:30 (Bear))
  false_positive: -3 (elementary 07:40-14:45 (Bellingrath))
  false_positive: -3 (middle 08:10-15:10 (Brewbaker Intermediate School))
  false_positive: -3 (middle 07:45-14:45 (Brewbaker Middle School))
  false_positive: -3 (elementary 07:30-14:30 (Capitol Heights))
  false_positive: -3 (elementary 08:10-15:10 (Chisholm Elementary))
  false_positive: -3 (elementary 08:05-15:05 (Dalraida))
  false_positive: -3 (elementary 08:00-15:00 (Dozier Elementary))
  false_positive: -3 (elementary 07:20-14:45 (Dunbar Ramer))
  false_positive: -3 (elementary 08:00-15:00 (E.D.Nixon Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 07:45-15:10 (Flowers Elementary School))
  false_positive: -3 (middle 08:30-15:30 (Floyd Middle School))
  false_positive: -3 (elementary 08:10-15:10 (Halcyon Elementary School))
  false_positive: -3 (high 07:30-14:45 (Jag High School))
  false_positive: -3 (middle 07:25-14:35 (Johnnie R. Carr Middle School))
  false_positive: -3 (high 07:10-14:30 (LAMP))
  false_positive: -3 (high 07:15-15:15 (Lanier High School))
  false_positive: -3 (elementary 08:40-15:40 (MacMillan International Academy))
  false_positive: -3 (middle 07:30-14:30 (McKee Middle School))
  false_positive: -3 (elementary 08:10-15:00 (Morris Elementary))
  false_positive: -3 (elementary 07:30-15:00 (MPACT))
  false_positive: -3 (high 07:45-14:45 (Park Crossing Highschool))
  false_positive: -3 (elementary 07:50-15:10 (Peter Crump Elem.))
  false_positive: -3 (elementary 08:00-15:00 (Pintlala Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Seth Johnson Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Southlawn Elementary School))
  false_positive: -3 (middle 07:30-14:45 (Southlawn Middle))
  false_positive: -3 (elementary 08:10-15:10 (Vaughn Road Elementary))
  false_positive: -3 (elementary 08:00-15:00 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 08:10-15:25 (William Silas Garrett Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))

Total: 25 (entries) + -113 (penalties) = 0/30 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 3

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:45-16:00 → high 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:45-16:00 → middle 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 07:40-14:55 (K-8 Schools))
  false_positive: -3 (middle 07:40-14:55 (K-8 Schools))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:55'))

Total: 27 (entries) + -8 (penalties) = 19/30 (63.3%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  middle 08:05-15:30 → middle 08:05-15:28 | start=3/3 (Δ0m) end=1/3 (Δ2m) grade=2/2 name=0/1 conf=1/1 = 7/10
  elementary 08:05-15:30 → elementary 07:45-15:20 | start=0/3 (Δ20m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: high)

Total: 9 (entries) + -2 (penalties) = 7/30 (23.3%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 2 | Matched: 1

Entry Scores:
  middle 08:00-14:45 → middle 07:30-14:15 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: elementary 07:50-13:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 08:15-15:15 (RED MTN. HIGH SCHOOL))
  missing_grade_level: -2 (Missing: elementary)

Total: 2 (entries) + -5 (penalties) = 0/20 (0.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 3 | Matched: 0

Entry Scores:
  MISSED: high 08:30-15:15 (unnamed) → 0/10
  MISSED: middle 08:50-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:20-14:45 (Borton Elementary Magnet School))
  false_positive: -3 (elementary 09:05-15:25 (Laura Banks Elementary School))
  false_positive: -3 (elementary 08:20-14:40 (John B. Wright Elementary School))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 0 (entries) + -13 (penalties) = 0/20 (0.0%)

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
  elementary 08:30-14:05 → elementary 08:00-14:05 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 08:00-13:54 (Core & Alternative Learning Academy at Conley-Caraballo High School))
  false_positive: -3 (middle 08:15-14:44 (César Chávez Middle School))
  false_positive: -3 (elementary 08:00-14:05 (Searles Elementary School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))

Total: 5 (entries) + -11 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 60 | Matched: 3

Entry Scores:
  elementary 08:45-15:00 → elementary 08:30-15:00 | start=0/3 (Δ15m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:20-13:50 → high 07:30-14:00 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 07:50-14:20 → middle 08:00-15:00 | start=0/3 (Δ10m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:05 (Cooperative Arts and Humanities Magnet High School))
  false_positive: -3 (high 07:10-14:05 (Cross High School))
  false_positive: -3 (high 07:30-14:17 (Eli Whitney Technical High School))
  false_positive: -3 (high 07:10-14:15 (Hill Regional Career High School))
  false_positive: -3 (high 07:10-14:05 (Hillhouse High School))
  false_positive: -3 (high 07:30-14:00 (Metropolitan Business Academy))
  false_positive: -3 (high 07:55-14:30 (New Haven Academy))
  false_positive: -3 (high 07:00-14:11 (Platt Technical High School))
  false_positive: -3 (high 08:00-14:30 (Sound School))
  false_positive: -3 (high 07:30-14:05 (Riverside Education Academy))
  false_positive: -3 (high 07:30-14:10 (HSC High School))
  false_positive: -3 (high 07:45-15:10 (Common Ground High School))
  false_positive: -3 (elementary 09:15-15:30 (Barnard Environmental Studies Magnet School))
  false_positive: -3 (elementary 09:15-15:30 (Beecher School))
  false_positive: -3 (elementary 07:45-14:15 (Betsy Ross Arts Magnet School))
  false_positive: -3 (elementary 08:35-14:50 (Bishop Woods School))
  false_positive: -3 (elementary 07:55-14:10 (Celentano School))
  false_positive: -3 (elementary 08:35-14:50 (Clinton Avenue School))
  false_positive: -3 (elementary 08:35-14:50 (FAME Academy))
  false_positive: -3 (elementary 09:15-15:30 (Conte West Hills Magnet School))
  false_positive: -3 (elementary 09:15-15:30 (Davis Street Arts and Academics School))
  false_positive: -3 (elementary 07:30-14:00 (ESUMS))
  false_positive: -3 (elementary 08:35-14:50 (Barack H. Obama Magnet University School))
  false_positive: -3 (elementary 07:55-14:10 (East Rock Community Magnet School))
  false_positive: -3 (elementary 08:35-14:50 (Edgewood School))
  false_positive: -3 (elementary 08:35-14:50 (Fair Haven School))
  false_positive: -3 (elementary 08:35-14:50 (John C. Martinez School))
  false_positive: -3 (elementary 09:15-15:30 (Jepson Magnet School))
  false_positive: -3 (elementary 08:35-14:50 (John S. Daniels School))
  false_positive: -3 (elementary 09:15-15:30 (King-Robinson Magnet School))
  false_positive: -3 (elementary 08:35-14:50 (Lincoln-Bassett School))
  false_positive: -3 (elementary 07:45-14:00 (Nathan Hale School))
  false_positive: -3 (elementary 08:35-14:50 (Roberto Clemente Leadership Academy))
  false_positive: -3 (elementary 09:15-15:30 (Ross/Woodward School))
  false_positive: -3 (elementary 09:15-15:30 (Mauro-Sheridan Magnet School))
  false_positive: -3 (elementary 08:35-14:50 (Wexler-Grant Community School))
  false_positive: -3 (elementary 08:35-14:50 (Troup School))
  false_positive: -3 (elementary 08:35-14:50 (Truman School))
  false_positive: -3 (elementary 09:00-15:15 (Hill Central Music Academy))
  false_positive: -3 (elementary 08:35-14:50 (Worthington Hooker School))
  false_positive: -3 (high 08:30-16:00 (Achievement First High School))
  false_positive: -3 (middle 08:30-16:00 (Amistad Middle School))
  false_positive: -3 (elementary 09:00-15:45 (Amistad Elementary School))
  false_positive: -3 (elementary 07:45-15:30 (Elm City Montessori School))
  false_positive: -3 (elementary 07:45-15:30 (Edmonds Cofield Preparatory Academy))
  false_positive: -3 (elementary 08:10-15:00 (Foote School))
  false_positive: -3 (high 07:40-15:30 (Hopkins School))
  false_positive: -3 (elementary 07:45-14:15 (All Saints Catholic Academy))
  false_positive: -3 (elementary 08:15-15:00 (St. Thomas Day School))
  false_positive: -3 (elementary 08:30-16:00 (Elm City Elementary School))
  false_positive: -3 (middle 08:30-16:00 (Elm City Middle School))
  false_positive: -3 (elementary 07:40-15:45 (Highville Charter School))
  false_positive: -3 (high 08:15-14:15 (Highville Charter High School))
  false_positive: -3 (elementary 07:40-15:40 (B. T. Washington Elementary School))
  false_positive: -3 (elementary 08:15-14:45 (Dr. Mayo ECLC SPED))
  false_positive: -3 (elementary 08:00-14:00 (Dr. Mayo ECLC H1))
  false_positive: -3 (elementary 09:00-15:00 (Dr. Mayo ECLC H2))
  duplicate_extraction: -2 (Duplicate: ('high', '07:10', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:55', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:30', '16:00'))

Total: 9 (entries) + -225 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 36 | Matched: 3

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
  false_positive: -3 (elementary 08:35-14:50 (Wendell Cross))
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
  false_positive: -3 (elementary 09:00-15:21 (Bucks Hill Pre-K))
  false_positive: -3 (high 07:30-13:45 (Holy Cross High School))
  false_positive: -3 (high 07:25-14:20 (Kaynor Technical))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Bais Yaakov))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Gedolah))
  false_positive: -3 (elementary 09:00-16:00 (Yeshiva K'Tana))
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

Total: 27 (entries) + -149 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 19 | Matched: 1

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
  false_positive: -3 (elementary 09:10-15:10 (Appoquinimink Preschool))
  false_positive: -3 (elementary 09:10-15:10 (Brick Mill ECC 4’s))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:10', '15:10'))

Total: 2 (entries) + -84 (penalties) = 0/10 (0.0%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 1

Entry Scores:
  elementary 08:00-15:00 → elementary 07:20-14:05 | start=0/3 (Δ40m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 2 (entries) + 0 (penalties) = 2/10 (20.0%)

======================================================================
Red Clay Consolidated School District (DE) - 1001300
======================================================================
Ground truth: 1 entries | Extracted: 1 | Matched: 0

Entry Scores:
  MISSED: elementary 09:05-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (high 07:25-14:10 (McKean High School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
BROWARD (FL) - 1200180
======================================================================
Ground truth: 3 entries | Extracted: 95 | Matched: 3

Entry Scores:
  elementary 08:00-14:00 → elementary 08:00-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:40-14:40 → high 07:40-14:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 09:30-16:10 → middle 07:05-13:50 | start=0/3 (Δ145m) end=0/3 (Δ140m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:50-13:50 (Banyan Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Bayview Elementary))
  false_positive: -3 (elementary 09:15-15:45 (Beachside Montessori Village))
  false_positive: -3 (elementary 08:00-14:00 (Bennett Elementary))
  false_positive: -3 (elementary 08:45-15:15 (Bethune, Mary M. Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Boulevard Heights Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Broadview Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Broward Estates Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Castle Hill Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Central Park Elementary))
  false_positive: -3 (elementary 08:45-14:45 (Challenger Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Chapel Trail Elementary))
  false_positive: -3 (elementary 08:00-14:40 (Coconut Creek K-8 Academy of Excellence))
  false_positive: -3 (elementary 08:00-14:00 (Coconut Palm Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Colbert Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Collins Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Cooper City Elementary))
  false_positive: -3 (elementary 08:00-14:40 (Coral Cove))
  false_positive: -3 (elementary 08:00-14:00 (Coral Park Elementary))
  false_positive: -3 (elementary 08:30-14:30 (Coral Springs Elementary))
  false_positive: -3 (elementary 08:10-14:10 (Country Hills Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Country Isles Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Cresthaven Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Croissant Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Cypress Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Dania Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Davie Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Deerfield Beach Elementary))
  false_positive: -3 (elementary 08:30-15:00 (Deerfield Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Dillard Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Discovery Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Dolphin Bay Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Drew, Charles Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Driftwood Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Eagle Point Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Eagle Ridge Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Embassy Creek Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Endeavor Primary Learning Center))
  false_positive: -3 (elementary 08:00-14:00 (Everglades Elementary))
  false_positive: -3 (elementary 08:10-14:10 (Fairway Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Flamingo Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Floranada Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Forest Hills Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Gulfstream Early Learning Center))
  false_positive: -3 (elementary 08:00-14:00 (Hawkes Bluff Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Heron Heights Elementary))
  false_positive: -3 (elementary 08:00-14:40 (Hollywood Central Preparatory K-8))
  false_positive: -3 (elementary 08:00-14:00 (Hollywood Hills Elementary))
  false_positive: -3 (elementary 08:10-14:10 (Hollywood Park Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Horizon Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Hunt, James S. Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Indian Trace Elementary))
  false_positive: -3 (elementary 08:00-14:00 (King, Martin Luther Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Lake Forest Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Lakeside Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Larkdale Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Lauderhill Paul Turner Elementary))
  false_positive: -3 (elementary 08:30-14:30 (Liberty Elementary))
  false_positive: -3 (elementary 07:55-13:55 (Lloyd Estates Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Manatee Bay Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Maplewood Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Margate Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Markham, Robert C. Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Marshall, Thurgood Elementary))
  false_positive: -3 (elementary 08:00-14:00 (McNab Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Meadowbrook Elementary))
  false_positive: -3 (elementary 07:55-13:55 (Miramar Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Mirror Lake Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Morrow Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Nob Hill Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Norcrest Elementary))
  false_positive: -3 (elementary 08:30-15:00 (North Andrews Gardens Elementary))
  false_positive: -3 (elementary 08:00-14:00 (North Fork Elementary))
  false_positive: -3 (elementary 08:00-14:00 (North Lauderdale Elementary))
  false_positive: -3 (elementary 08:00-14:00 (North Side Elementary))
  false_positive: -3 (elementary 09:30-15:30 (Nova Blanche Forman Elementary))
  false_positive: -3 (elementary 09:30-15:30 (Nova Dwight D. Eisenhower Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Oakland Park Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Oakridge Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Orange Brook Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Oriole Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Palm Cove Elementary))
  false_positive: -3 (elementary 07:50-13:50 (Palmview Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Panther Run Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Park Lakes Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Park Ridge Elementary))
  false_positive: -3 (elementary 07:45-13:45 (Park Springs Elementary))
  false_positive: -3 (elementary 08:15-14:15 (Park Trails Elementary))
  false_positive: -3 (elementary 09:15-15:15 (Wingate Oaks Center (PRE-K/ESE)))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:55', '13:55'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:50', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '13:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:40', '14:40'))

Total: 20 (entries) + -434 (penalties) = 0/30 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 170 | Matched: 3

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-14:20 → high 07:20-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 09:30-16:04 → middle 09:30-16:04 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:45-15:00 (Andover))
  false_positive: -3 (elementary 08:45-15:00 (Apopka))
  false_positive: -3 (elementary 08:45-15:00 (Arbor Ridge K-8))
  false_positive: -3 (middle 08:42-15:04 (Arbor Ridge K-8))
  false_positive: -3 (elementary 08:45-15:00 (Atwater Bay))
  false_positive: -3 (elementary 08:45-15:00 (Audubon Park K-8))
  false_positive: -3 (middle 08:42-15:04 (Audubon Park K-8))
  false_positive: -3 (elementary 08:45-15:00 (Avalon))
  false_positive: -3 (elementary 08:45-15:00 (Azalea Park))
  false_positive: -3 (elementary 08:45-15:00 (Baldwin Park))
  false_positive: -3 (elementary 08:45-15:00 (Bay Lake))
  false_positive: -3 (elementary 08:45-15:00 (Bay Meadows))
  false_positive: -3 (elementary 08:45-15:00 (Blankner K-8))
  false_positive: -3 (middle 08:42-15:04 (Blankner K-8))
  false_positive: -3 (elementary 08:45-15:00 (Bonneville))
  false_positive: -3 (elementary 08:45-15:00 (Brookshire))
  false_positive: -3 (elementary 08:45-15:00 (Camelot))
  false_positive: -3 (elementary 08:45-15:00 (Castleview))
  false_positive: -3 (elementary 08:45-15:00 (Castle Creek))
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:45-15:00 (Cheney))
  false_positive: -3 (elementary 08:45-15:00 (Chickasaw))
  false_positive: -3 (elementary 08:45-15:00 (Citrus))
  false_positive: -3 (elementary 08:45-15:00 (Clay Springs))
  false_positive: -3 (elementary 08:45-15:00 (Columbia))
  false_positive: -3 (elementary 08:45-15:00 (Conway))
  false_positive: -3 (elementary 08:45-15:00 (Cypress Springs))
  false_positive: -3 (elementary 08:45-15:00 (Deerwood))
  false_positive: -3 (elementary 08:30-14:45 (Dillard Street))
  false_positive: -3 (elementary 08:45-15:00 (Dommerich))
  false_positive: -3 (elementary 08:45-15:00 (Dover Shores))
  false_positive: -3 (elementary 08:45-15:00 (Dr. Phillips))
  false_positive: -3 (elementary 08:45-15:00 (Dr. Phillips HS Pre-K))
  false_positive: -3 (elementary 08:45-15:00 (Dream Lake))
  false_positive: -3 (elementary 08:45-15:00 (Eagle Creek))
  false_positive: -3 (elementary 08:45-15:00 (Eagles Nest))
  false_positive: -3 (elementary 08:45-15:00 (East Lake))
  false_positive: -3 (elementary 08:15-15:30 (Eccleston))
  false_positive: -3 (elementary 08:45-15:00 (Endeavor))
  false_positive: -3 (elementary 08:15-15:30 (Engelwood))
  false_positive: -3 (elementary 08:45-15:00 (Forsyth Woods))
  false_positive: -3 (elementary 08:45-15:00 (Frangus))
  false_positive: -3 (elementary 08:45-15:00 (Hamlin))
  false_positive: -3 (elementary 08:15-15:30 (Hiawassee))
  false_positive: -3 (elementary 08:45-15:00 (Hidden Oaks))
  false_positive: -3 (elementary 08:45-15:00 (Hillcrest))
  false_positive: -3 (elementary 08:45-15:00 (Hungerford))
  false_positive: -3 (elementary 08:45-15:00 (Hunter’s Creek))
  false_positive: -3 (elementary 08:45-15:00 (Independence))
  false_positive: -3 (elementary 08:15-15:30 (Ivey Lane))
  false_positive: -3 (elementary 08:45-15:00 (John Young))
  false_positive: -3 (elementary 08:45-15:00 (Keene’s Crossing))
  false_positive: -3 (elementary 08:45-15:00 (Kelly Park K-8))
  false_positive: -3 (middle 08:42-15:04 (Kelly Park K-8))
  false_positive: -3 (elementary 08:45-15:00 (Killarney))
  false_positive: -3 (elementary 08:45-15:00 (Lake Como K-8))
  false_positive: -3 (middle 08:42-15:04 (Lake Como K-8))
  false_positive: -3 (elementary 08:45-15:00 (Lake Gem))
  false_positive: -3 (elementary 08:45-15:00 (Lake George))
  false_positive: -3 (elementary 08:45-15:00 (Lake Silver))
  false_positive: -3 (elementary 08:45-15:00 (Lake Sybelia))
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  false_positive: -3 (elementary 08:45-15:00 (Lake Whitney))
  false_positive: -3 (elementary 08:45-15:00 (Lakemont))
  false_positive: -3 (elementary 08:45-15:00 (Lakeville))
  false_positive: -3 (elementary 08:45-15:00 (Lancaster))
  false_positive: -3 (elementary 08:45-15:00 (Laureate Park))
  false_positive: -3 (elementary 08:45-15:00 (Lawton Chiles))
  false_positive: -3 (elementary 08:45-15:00 (Luminary))
  false_positive: -3 (elementary 08:45-15:00 (Little River))
  false_positive: -3 (elementary 08:45-15:00 (Lockhart))
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  false_positive: -3 (elementary 08:45-15:00 (Maxey))
  false_positive: -3 (elementary 08:45-15:00 (McCoy))
  false_positive: -3 (elementary 08:45-15:00 (Meadow Woods))
  false_positive: -3 (elementary 08:45-15:00 (MetroWest))
  false_positive: -3 (elementary 08:45-15:00 (Millennia))
  false_positive: -3 (elementary 08:45-15:00 (Millennia Gardens))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
  false_positive: -3 (elementary 08:45-15:00 (Moss Park))
  false_positive: -3 (elementary 08:45-15:00 (NorthLake Park))
  false_positive: -3 (elementary 08:45-15:00 (Oak Hill))
  false_positive: -3 (elementary 08:45-15:00 (Oakshire))
  false_positive: -3 (elementary 08:45-15:00 (Ocoee))
  false_positive: -3 (elementary 08:45-16:00 (OCPS Academic Center for Excellence K-8))
  false_positive: -3 (middle 08:45-16:00 (OCPS Academic Center for Excellence K-8))
  false_positive: -3 (elementary 08:15-15:30 (Orange Center))
  false_positive: -3 (elementary 08:45-15:00 (Orlando Gifted K-8))
  false_positive: -3 (middle 08:42-15:04 (Orlando Gifted K-8))
  false_positive: -3 (elementary 08:15-15:30 (Orlo Vista))
  false_positive: -3 (elementary 08:45-15:00 (Palm Lake))
  false_positive: -3 (elementary 08:45-15:00 (Palmetto))
  false_positive: -3 (elementary 08:45-15:00 (Panther Lake))
  false_positive: -3 (elementary 08:45-15:00 (Pinar))
  false_positive: -3 (elementary 08:45-15:00 (Pershing K-8))
  false_positive: -3 (middle 08:42-15:04 (Pershing K-8))
  false_positive: -3 (elementary 08:45-15:00 (Pine Hills))
  false_positive: -3 (elementary 08:15-15:30 (Pineloch))
  false_positive: -3 (elementary 08:15-15:30 (Pinewood))
  false_positive: -3 (elementary 08:45-15:00 (Prairie Lake))
  false_positive: -3 (elementary 08:45-15:00 (Princeton))
  false_positive: -3 (elementary 08:15-15:30 (Ridgewood Park))
  false_positive: -3 (elementary 08:45-15:00 (Riverdale))
  false_positive: -3 (elementary 08:45-15:00 (Riverside))
  false_positive: -3 (elementary 08:15-15:30 (Rock Lake))
  false_positive: -3 (elementary 08:45-15:00 (Rock Springs))
  false_positive: -3 (elementary 08:15-15:30 (Rolling Hills))
  false_positive: -3 (elementary 08:15-15:30 (Rosemont))
  false_positive: -3 (elementary 08:45-15:00 (Sadler))
  false_positive: -3 (elementary 08:45-15:00 (Sally Ride))
  false_positive: -3 (elementary 08:45-15:00 (Sand Lake))
  false_positive: -3 (elementary 08:45-15:00 (Shenandoah))
  false_positive: -3 (elementary 08:15-15:30 (Shingle Creek))
  false_positive: -3 (elementary 08:45-15:00 (Southwood))
  false_positive: -3 (elementary 08:45-15:00 (Spring Lake))
  false_positive: -3 (elementary 08:45-15:00 (Stone Lakes))
  false_positive: -3 (elementary 08:45-15:00 (Vista Pointe))
  false_positive: -3 (elementary 08:15-15:30 (Washington Shores))
  false_positive: -3 (elementary 08:30-14:30 (Washington Shores Early Learning Center))
  false_positive: -3 (elementary 08:45-15:00 (Waterbridge))
  false_positive: -3 (elementary 08:45-15:00 (Waterford))
  false_positive: -3 (elementary 08:45-15:00 (Water Spring))
  false_positive: -3 (elementary 08:45-15:00 (Wedgefield K-8))
  false_positive: -3 (middle 08:42-15:04 (Wedgefield K-8))
  false_positive: -3 (elementary 08:45-15:00 (Wetherbee))
  false_positive: -3 (elementary 08:45-15:00 (Westbrooke))
  false_positive: -3 (elementary 08:45-15:00 (West Creek))
  false_positive: -3 (elementary 08:45-15:00 (West Oaks))
  false_positive: -3 (middle 09:30-16:04 (Meadowbrook))
  false_positive: -3 (middle 09:30-16:04 (Memorial))
  false_positive: -3 (middle 09:30-16:04 (Ocoee))
  false_positive: -3 (middle 09:30-16:04 (Odyssey))
  false_positive: -3 (middle 09:30-16:04 (Piedmont Lakes))
  false_positive: -3 (middle 09:30-16:04 (Robinswood))
  false_positive: -3 (middle 09:30-16:04 (South Creek))
  false_positive: -3 (middle 09:30-16:04 (Southwest))
  false_positive: -3 (middle 09:30-16:04 (SunRidge))
  false_positive: -3 (middle 09:30-16:04 (Timber Springs))
  false_positive: -3 (middle 09:30-16:04 (Union Park))
  false_positive: -3 (middle 09:30-16:04 (Walker))
  false_positive: -3 (middle 09:30-16:04 (Water Spring))
  false_positive: -3 (middle 09:30-16:04 (Westridge))
  false_positive: -3 (middle 09:30-16:04 (Wolf Lake))
  false_positive: -3 (high 07:20-14:20 (Boone))
  false_positive: -3 (high 07:20-14:20 (Colonial))
  false_positive: -3 (high 07:10-14:04 (Colonial 9th Gr. Ctr.))
  false_positive: -3 (high 07:20-14:20 (Cypress Creek))
  false_positive: -3 (high 07:20-14:20 (Dr. Phillips))
  false_positive: -3 (high 07:20-14:20 (East River))
  false_positive: -3 (high 07:20-14:20 (Edgewater))
  false_positive: -3 (high 07:20-14:20 (Evans))
  false_positive: -3 (high 07:20-14:20 (Freedom))
  false_positive: -3 (high 07:20-14:20 (Horizon))
  false_positive: -3 (high 07:20-14:20 (Innovation))
  false_positive: -3 (high 07:20-14:20 (Jones))
  false_positive: -3 (high 07:20-14:20 (Lake Buena Vista))
  false_positive: -3 (high 07:20-14:20 (Lake Nona))
  false_positive: -3 (high 07:20-14:20 (Oak Ridge))
  false_positive: -3 (high 07:20-14:20 (Ocoee))
  false_positive: -3 (high 07:20-14:20 (Olympia))
  false_positive: -3 (high 07:20-14:20 (Timber Creek))
  false_positive: -3 (high 07:20-14:20 (University))
  false_positive: -3 (high 07:20-14:20 (Wekiva))
  false_positive: -3 (high 07:20-14:20 (West Orange))
  false_positive: -3 (high 07:20-14:20 (Windermere))
  false_positive: -3 (high 07:20-14:20 (Winter Park))
  false_positive: -3 (high 07:10-14:10 (Winter Park 9th Gr. Ctr.))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:42', '15:04'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:42', '15:04'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:42', '15:04'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:42', '15:04'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:42', '15:04'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:42', '15:04'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:42', '15:04'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '16:04'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '14:20'))

Total: 27 (entries) + -819 (penalties) = 0/30 (0.0%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 5 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:50 (High School))
  false_positive: -3 (elementary 08:50-15:50 (Wright Elementary School))
  false_positive: -3 (high 07:50-15:00 (Metro High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:50'))

Total: 10 (entries) + -11 (penalties) = 0/20 (0.0%)

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
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  high 08:40-15:48 → high 08:40-15:48 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 08:00-14:45 (Lincoln High School))
  false_positive: -3 (middle 08:40-15:45 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))

Total: 9 (entries) + -9 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 31 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:45-13:45 (DREWICZ))
  false_positive: -3 (elementary 07:45-13:45 (EARLY CHILDHOOD CENTER))
  false_positive: -3 (elementary 07:45-13:45 (FALLON))
  false_positive: -3 (elementary 07:45-13:45 (FORD))
  false_positive: -3 (elementary 07:45-13:45 (HARRINGTON))
  false_positive: -3 (elementary 07:45-13:45 (INGALLS))
  false_positive: -3 (elementary 07:45-13:45 (SISSON))
  false_positive: -3 (elementary 07:45-13:45 (VIRGINIA BARTON CENTER AT BRIARCLIFF (TEAMS)))
  false_positive: -3 (elementary 07:45-13:45 (WASHINGTON))
  false_positive: -3 (elementary 08:15-14:15 (ABORN))
  false_positive: -3 (elementary 08:15-14:15 (BRICKETT))
  false_positive: -3 (elementary 08:15-14:15 (COBBET))
  false_positive: -3 (elementary 08:15-14:15 (CONNERY))
  false_positive: -3 (elementary 08:15-14:15 (HOOD))
  false_positive: -3 (elementary 08:15-14:15 (LINCOLN-THOMSON))
  false_positive: -3 (elementary 08:15-14:15 (LYNN WOODS))
  false_positive: -3 (elementary 08:15-14:15 (SEWELL ANDERSON))
  false_positive: -3 (elementary 08:15-14:15 (SHOEMAKER))
  false_positive: -3 (elementary 08:15-14:15 (TRACY))
  false_positive: -3 (high 07:45-14:05 (HAROLD DURGIN SUCCESS ACADEMY))
  false_positive: -3 (high 07:45-14:30 (DISCOVERY ACADEMY))
  false_positive: -3 (high 07:45-14:30 (FREDERICK DOUGLASS COLLEGIATE ACADEMY))
  false_positive: -3 (high 07:45-14:30 (LYNN CLASSICAL HIGH SCHOOL))
  false_positive: -3 (high 07:45-14:30 (LYNN ENGLISH HIGH SCHOOL))
  false_positive: -3 (high 07:45-14:30 (LYNN VOCATIONAL TECHNICAL INSTITUTE))
  false_positive: -3 (middle 07:45-14:30 (PICKERING MIDDLE SCHOOL))
  false_positive: -3 (high 07:45-14:30 (VIRGINIA BARTON CENTER AT BRIARCLIFF (SECONDARY TEAMS)))
  false_positive: -3 (middle 07:45-14:30 (THURGOOD MARSHALL MIDDLE SCHOOL))
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
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))

Total: 20 (entries) + -134 (penalties) = 0/30 (0.0%)

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
  elementary 08:55-15:00 → elementary 08:55-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:15-14:30 → middle 08:15-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:00-14:00 → high 07:55-14:00 | start=1/3 (Δ5m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (elementary 08:50-15:00 (Bangor Elementary Schools (Grades 4-5)))

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
Ground truth: 3 entries | Extracted: 33 | Matched: 3

Entry Scores:
  elementary 08:30-15:25 → elementary 08:30-15:25 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:25-15:45 → high 08:25-15:45 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:40 → middle 08:00-15:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:30-15:25 (Overpark Elementary))
  false_positive: -3 (elementary 08:25-15:20 (DeSoto Central Primary))
  false_positive: -3 (elementary 08:30-15:25 (DeSoto Central Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Pleasant Hill Elementary))
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
  false_positive: -3 (elementary 08:30-15:25 (Southaven Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Hope Sullivan Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Greenbrook Elementary))
  false_positive: -3 (elementary 08:25-15:20 (Southaven Intermediate))
  false_positive: -3 (middle 08:00-15:40 (Southaven Middle))
  false_positive: -3 (high 08:25-15:45 (Southaven High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:25'))
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
Ground truth: 1 entries | Extracted: 31 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:10-14:48 | start=0/3 (Δ10m) end=0/3 (Δ12m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Culler Middle School))
  false_positive: -3 (elementary 09:00-15:38 (McPhee))
  false_positive: -3 (middle 08:00-15:00 (Dawes))
  false_positive: -3 (elementary 09:00-15:38 (Meadow Lane))
  false_positive: -3 (middle 08:00-15:00 (Goodrich))
  false_positive: -3 (elementary 09:00-15:38 (Morley))
  false_positive: -3 (middle 08:00-15:00 (Irving))
  false_positive: -3 (elementary 09:00-15:38 (Norwood Park))
  false_positive: -3 (middle 08:00-15:00 (Lefler))
  false_positive: -3 (elementary 08:15-14:53 (Pershing))
  false_positive: -3 (middle 08:00-15:00 (Lux))
  false_positive: -3 (elementary 09:00-15:38 (Prescott))
  false_positive: -3 (middle 08:00-15:00 (Mickle))
  false_positive: -3 (elementary 09:00-15:38 (Pyrtle))
  false_positive: -3 (middle 08:00-15:00 (Moore))
  false_positive: -3 (elementary 09:00-15:38 (Randolph))
  false_positive: -3 (middle 08:00-15:00 (Park))
  false_positive: -3 (elementary 09:00-15:38 (Riley))
  false_positive: -3 (middle 08:00-15:00 (Pound))
  false_positive: -3 (elementary 08:15-14:53 (Robinson))
  false_positive: -3 (middle 08:00-15:00 (Schoo))
  false_positive: -3 (elementary 08:15-14:53 (Roper))
  false_positive: -3 (middle 08:00-15:00 (Scott))
  false_positive: -3 (elementary 09:00-15:38 (Rousseau))
  false_positive: -3 (elementary 08:15-14:53 (Saratoga))
  false_positive: -3 (elementary 09:00-15:38 (Sheridan))
  false_positive: -3 (elementary 09:00-15:38 (West Lincoln))
  false_positive: -3 (elementary 09:00-15:38 (Wysong))
  false_positive: -3 (elementary 08:15-14:53 (Zeman))
  false_positive: -3 (elementary 09:10-15:30 (Don D. Sherrill Education Center))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:38'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:53'))

Total: 2 (entries) + -142 (penalties) = 0/10 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 106 | Matched: 1

Entry Scores:
  elementary 07:26-14:00 → elementary 08:00-14:50 | start=0/3 (Δ34m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 2/10

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
  false_positive: -3 (middle 09:30-15:30 (Cold Springs EC))
  false_positive: -3 (middle 07:30-14:00 (Depoali))
  false_positive: -3 (middle 07:30-14:00 (Desert Skies))
  false_positive: -3 (middle 07:30-14:00 (Dilworth-STEM))
  false_positive: -3 (middle 07:30-14:00 (Herz))
  false_positive: -3 (middle 07:50-14:25 (Incline))
  false_positive: -3 (middle 07:30-14:00 (Mendive))
  false_positive: -3 (middle 07:30-13:54 (O'Brien-STEM))
  false_positive: -3 (middle 09:30-15:30 (Picollo))
  false_positive: -3 (middle 07:30-14:00 (Pine))
  false_positive: -3 (middle 07:30-14:00 (Shaw))
  false_positive: -3 (middle 07:30-14:00 (Sky Ranch))
  false_positive: -3 (middle 07:30-14:00 (Sparks))
  false_positive: -3 (middle 07:30-14:00 (Swope))
  false_positive: -3 (middle 07:30-14:00 (Traner))
  false_positive: -3 (middle 07:25-14:00 (Vaughn))
  false_positive: -3 (middle 08:00-14:30 (Mt. Rose))
  false_positive: -3 (elementary 09:30-15:30 (Allen))
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
  false_positive: -3 (elementary 09:00-15:00 (Duncan-STEM))
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
  false_positive: -3 (elementary 09:00-15:00 (Lemelson-STEM))
  false_positive: -3 (elementary 09:30-15:30 (Lemmon Valley))
  false_positive: -3 (elementary 09:00-15:00 (Lenz))
  false_positive: -3 (elementary 09:30-15:30 (Lincoln Park))
  false_positive: -3 (elementary 09:00-15:00 (Loder))
  false_positive: -3 (elementary 09:30-15:30 (Mathews))
  false_positive: -3 (elementary 09:00-15:00 (Maxwell))
  false_positive: -3 (elementary 09:30-15:30 (Melton))
  false_positive: -3 (elementary 09:15-15:15 (Mitchell))
  false_positive: -3 (elementary 09:15-15:15 (Moss))
  false_positive: -3 (elementary 08:30-14:30 (Mt. Rose))
  false_positive: -3 (elementary 08:25-14:30 (Natchez))
  false_positive: -3 (elementary 09:00-15:00 (Palmer))
  false_positive: -3 (elementary 09:30-15:30 (Peavine))
  false_positive: -3 (elementary 09:30-15:30 (Pleasant Valley))
  false_positive: -3 (elementary 09:30-15:30 (Poulakidas))
  false_positive: -3 (elementary 09:00-15:00 (Risley))
  false_positive: -3 (elementary 09:00-15:00 (Sepulveda))
  false_positive: -3 (elementary 09:00-15:00 (Silver Lake))
  false_positive: -3 (elementary 09:30-15:30 (Alice Smith))
  false_positive: -3 (elementary 08:45-15:00 (Kate Smith))
  false_positive: -3 (elementary 08:45-15:00 (Smithridge-STEM))
  false_positive: -3 (elementary 09:10-15:15 (Spanish Springs))
  false_positive: -3 (elementary 09:00-15:00 (Stead))
  false_positive: -3 (elementary 09:30-15:30 (Sun Valley))
  false_positive: -3 (elementary 09:00-15:00 (Taylor))
  false_positive: -3 (elementary 09:00-15:00 (Towles))
  false_positive: -3 (elementary 09:25-15:30 (Van Gorder))
  false_positive: -3 (elementary 09:15-15:15 (Verdi))
  false_positive: -3 (elementary 09:00-15:00 (Veterans-STEM))
  false_positive: -3 (elementary 09:00-15:00 (Warner))
  false_positive: -3 (elementary 09:00-15:00 (Westergard))
  false_positive: -3 (elementary 09:00-15:00 (Whitehead))
  false_positive: -3 (elementary 09:00-15:00 (Winnemucca))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '15:30'))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:30', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:00'))

Total: 2 (entries) + -471 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 92 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (elementary 09:35-16:05 (Adlai E. Stevenson))
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (elementary 08:35-15:05 (Garfield))
  false_positive: -3 (elementary 09:35-16:05 (Orchard))
  false_positive: -3 (elementary 07:35-14:05 (Alfred A. Benesch))
  false_positive: -3 (elementary 09:35-16:05 (George W. Carver))
  false_positive: -3 (elementary 09:35-16:05 (Paul L. Dunbar))
  false_positive: -3 (elementary 08:35-15:05 (Almira))
  false_positive: -3 (elementary 09:35-16:05 (Halle))
  false_positive: -3 (elementary 09:35-16:05 (Riverside))
  false_positive: -3 (elementary 07:35-14:05 (Andrew J. Rickoff))
  false_positive: -3 (elementary 09:35-16:05 (Hannah Gibbons))
  false_positive: -3 (elementary 09:35-16:05 (Robert H. Jamison))
  false_positive: -3 (elementary 07:35-14:05 (Anton Grdina))
  false_positive: -3 (elementary 07:35-14:05 (Harvey Rice))
  false_positive: -3 (elementary 08:35-15:05 (Robinson G. Jones))
  false_positive: -3 (elementary 09:35-16:05 (Artemus Ward))
  false_positive: -3 (elementary 08:35-15:05 (Joseph M. Gallagher))
  false_positive: -3 (elementary 07:35-14:05 (Scranton))
  false_positive: -3 (elementary 08:35-15:05 (Benjamin Franklin))
  false_positive: -3 (elementary 08:35-15:05 (Kenneth Clement Boys’ Leadership Academy))
  false_positive: -3 (elementary 07:35-14:05 (Stephanie Tubbs Jones School))
  false_positive: -3 (elementary 09:35-16:05 (Bolton))
  false_positive: -3 (elementary 09:35-16:05 (Stonebrook-White Montessori Campus))
  false_positive: -3 (elementary 09:35-16:05 (Buhrer))
  false_positive: -3 (elementary 09:35-16:05 (Louisa May Alcott))
  false_positive: -3 (elementary 08:40-15:10 (Campus International K8))
  false_positive: -3 (elementary 07:35-14:05 (Luis Muñoz Marin))
  false_positive: -3 (elementary 07:35-14:05 (Charles A. Mooney))
  false_positive: -3 (elementary 09:35-16:05 (Marion C. Seltzer))
  false_positive: -3 (elementary 08:35-15:05 (Sunbeam))
  false_positive: -3 (elementary 09:35-16:05 (Charles Dickens))
  false_positive: -3 (elementary 08:35-15:05 (Marion-Sterling))
  false_positive: -3 (elementary 09:35-16:05 (Tremont Montessori))
  false_positive: -3 (elementary 07:35-14:05 (Clara E. Westropp))
  false_positive: -3 (elementary 07:35-14:05 (Mary B. Martin))
  false_positive: -3 (elementary 08:05-14:35 (Valley View Boys’ Leadership Academy))
  false_positive: -3 (elementary 09:35-16:05 (Clark))
  false_positive: -3 (elementary 09:35-16:05 (Mary Church Terrell))
  false_positive: -3 (elementary 08:35-15:05 (Wade Park))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (elementary 07:35-14:05 (Mary M. Bethune))
  false_positive: -3 (elementary 08:05-14:35 (Warner Girls’ Leadership Academy))
  false_positive: -3 (elementary 07:35-14:05 (Daniel E. Morgan))
  false_positive: -3 (elementary 07:35-14:05 (Memorial))
  false_positive: -3 (elementary 09:35-16:05 (Waverly))
  false_positive: -3 (elementary 08:35-15:05 (Denison))
  false_positive: -3 (elementary 09:35-16:05 (Miles))
  false_positive: -3 (elementary 08:35-15:05 (Whitney M. Young))
  false_positive: -3 (elementary 09:35-16:05 (Dike School of the Arts))
  false_positive: -3 (elementary 08:35-15:05 (Miles Park))
  false_positive: -3 (elementary 07:35-14:05 (Wilbur Wright))
  false_positive: -3 (elementary 08:00-14:30 (Douglas MacArthur Girls’ Leadership Academy))
  false_positive: -3 (elementary 08:35-15:05 (Mound))
  false_positive: -3 (elementary 09:35-16:05 (William C. Bryant))
  false_positive: -3 (elementary 07:35-14:05 (East Clark))
  false_positive: -3 (elementary 08:35-15:05 (Nathan Hale))
  false_positive: -3 (elementary 07:35-14:05 (William Rainey Harper))
  false_positive: -3 (elementary 07:35-14:05 (Euclid Park))
  false_positive: -3 (elementary 08:35-15:05 (Natividad Pagan International Newcomers Academy))
  false_positive: -3 (elementary 07:35-14:05 (Willson))
  false_positive: -3 (high 09:00-15:30 (Bard High School Early College Cleveland))
  false_positive: -3 (high 08:25-14:55 (Garrett Morgan School of Engineering and Innovation))
  false_positive: -3 (high 08:35-15:05 (Campus International H.S.))
  false_positive: -3 (high 08:25-14:55 (Garrett Morgan School of Leadership and Innovation))
  false_positive: -3 (high 08:35-15:05 (Max S. Hayes High School))
  false_positive: -3 (high 08:00-15:00 (Cleveland Early College H.S.))
  false_positive: -3 (high 08:35-15:05 (Ginn Academy))
  false_positive: -3 (high 09:00-15:30 (MC²STEM High School))
  false_positive: -3 (high 09:00-15:30 (Cleveland H.S. for Digital Arts))
  false_positive: -3 (high 08:35-15:05 (Glenville High School))
  false_positive: -3 (high 08:35-15:05 (Natividad Pagan International Newcomers Academy))
  false_positive: -3 (high 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (high 08:00-15:00 (John Adams College & Career Academy))
  false_positive: -3 (high 08:00-14:30 (New Tech West High School))
  false_positive: -3 (high 08:00-14:30 (Cleveland School of Architecture & Design))
  false_positive: -3 (high 08:35-15:05 (John F. Kennedy High School))
  false_positive: -3 (high 08:00-14:30 (Rhodes College & Career Academy))
  false_positive: -3 (high 08:00-14:30 (Cleveland School of Science & Medicine))
  false_positive: -3 (high 08:00-14:30 (John Marshall School of Civic & Business Leadership))
  false_positive: -3 (high 08:00-14:30 (Rhodes School of Environmental Studies))
  false_positive: -3 (high 08:35-15:05 (Cleveland School of the Arts))
  false_positive: -3 (high 08:00-14:30 (John Marshall School of Engineering))
  false_positive: -3 (high 08:00-14:30 (Collinwood High School))
  false_positive: -3 (high 08:00-14:30 (John Marshall School of Information Technology))
  false_positive: -3 (high 08:35-15:05 (Davis Aerospace & Maritime High School))
  false_positive: -3 (high 08:35-15:05 (Lincoln-West School of Global Studies))
  false_positive: -3 (high 08:35-15:05 (East Technical High School))
  false_positive: -3 (high 08:35-15:05 (Facing History New Tech High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '14:55'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  missing_grade_level: -2 (Missing: middle)

Total: 25 (entries) + -431 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 6 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 07:50-14:35 | start=3/3 (Δ0m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 07:45-14:45 (Charlotte Central School))
  false_positive: -3 (middle 07:45-14:45 (Charlotte Central School))
  false_positive: -3 (elementary 07:45-14:45 (Shelburne Community School))
  false_positive: -3 (middle 07:45-14:45 (Shelburne Community School))
  false_positive: -3 (middle 07:55-14:45 (Williston Central School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:45'))

Total: 5 (entries) + -19 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 1 | Matched: 1

Entry Scores:
  high 07:28-14:38 → high 07:28-14:38 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: elementary 07:55-15:30 (unnamed) → 0/10
  MISSED: middle 07:30-14:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: elementary)

Total: 9 (entries) + -4 (penalties) = 5/30 (16.7%)

======================================================================
CABELL COUNTY SCHOOLS (WV) - 5400180
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  middle 07:27-15:06 → middle 07:48-15:00 | start=0/3 (Δ21m) end=0/3 (Δ6m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:45-15:17 (Huntington High School))

Total: 2 (entries) + -3 (penalties) = 0/10 (0.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 07:15-14:15 → elementary 07:45-14:17 | start=0/3 (Δ30m) end=1/3 (Δ2m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (middle 08:25-15:10 (Elkview Middle School))
  false_positive: -3 (middle 08:15-15:10 (Elkview Middle School))
  false_positive: -3 (middle 08:15-15:10 (Elkview Middle School))
  false_positive: -3 (high 08:36-15:36 (Nitro High))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:15', '15:10'))

Total: 3 (entries) + -14 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 8 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-15:15 (Rock Springs Elementary Schools (4-6)))
  false_positive: -3 (middle 08:30-15:50 (Wamsutter K-8))
  false_positive: -3 (elementary 07:45-15:00 (Farson-Eden Elementary School))
  false_positive: -3 (middle 07:45-16:05 (Farson-Eden Middle School))
  false_positive: -3 (high 07:45-16:05 (Farson-Eden High School))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:30', '15:50'))

Total: 23 (entries) + -17 (penalties) = 6/30 (20.0%)