# Benchmark Report: openrouter:ibm-granite/granite-4.1-8b
Run date: 2026-06-14T00:29:58
Districts tested: 40
Total extraction time: 552s (avg 13.8s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 14.8% |
| JSON parse success | 100.0% |
| Grade coverage rate | 87.3% |
| False positive rate | 10.45/district |
| Mean time/extraction | 13.8s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| BROWARD | FL | 20 | 30 | 66.7% |  |  |
| Albany County School District  | WY | 17 | 30 | 56.7% |  |  |
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 13 | 30 | 43.3% | false_positive, missing_grade_level |  |
| Cedar Rapids Comm School Distr | IA | 7 | 20 | 35.0% | false_positive |  |
| BERKELEY COUNTY SCHOOLS | WV | 9 | 30 | 30.0% | missing_grade_level |  |
| Sweetwater County School Distr | WY | 9 | 30 | 30.0% |  |  |
| Lewiston Public Schools | ME | 8 | 30 | 26.7% | missing_grade_level |  |
| Mesa Unified District (4235) | AZ | 4 | 20 | 20.0% | false_positive |  |
| Los Angeles Unified | CA | 6 | 30 | 20.0% |  |  |
| Bangor Public Schools | ME | 5 | 30 | 16.7% | false_positive, missing_grade_level |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+28 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+32 more) |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+56 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+26 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+48 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+27 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+40 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+49 more) |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+35 more) |  |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+14 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+108 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+13 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+111 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-14:35 | start=3/3 (Δ0m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (middle 07:45-14:35 (Colony Middle School))
  false_positive: -3 (elementary 07:45-14:35 (Big Lake Elementary School))

Total: 5 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 21 | Matched: 1

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
  false_positive: -3 (middle 07:50-14:20 (North Pole Middle))
  false_positive: -3 (middle 07:50-14:20 (Randy Smith Middle))
  false_positive: -3 (middle 07:50-14:20 (Ryan Middle))
  false_positive: -3 (middle 07:55-14:25 (Tanana Middle))
  false_positive: -3 (elementary 09:00-15:30 (Ticasuk Brown Elementary))
  false_positive: -3 (elementary 09:15-15:45 (University Park Elementary))
  false_positive: -3 (elementary 08:30-15:00 (Watershed Charter))
  false_positive: -3 (elementary 09:15-15:45 (Weller Elementary))
  false_positive: -3 (elementary 09:00-15:30 (Woodriver Elementary))
  false_positive: -3 (high 07:30-14:00 (Hutchison High))
  false_positive: -3 (high 07:30-14:00 (Lathrop High))
  false_positive: -3 (high 07:30-14:00 (North Pole High))
  false_positive: -3 (high 07:30-14:00 (West Valley High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))

Total: 9 (entries) + -82 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 07:15-14:45 → elementary 07:40-14:40 | start=0/3 (Δ25m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (high 07:45-15:05 (Fairhope High))
  false_positive: -3 (middle 07:45-15:05 (Fairhope Middle))

Total: 3 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 8 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:10-15:25 | start=0/3 (Δ10m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:45-15:15 (Ariel W. Holloway Elementary School))
  false_positive: -3 (elementary 07:40-15:10 (Dodge Elementary))
  false_positive: -3 (elementary 07:45-15:15 (Collier Elementary School))
  false_positive: -3 (middle 06:50-14:20 (Causey Middle School))
  false_positive: -3 (middle 06:50-14:20 (Pillans Middle School))
  false_positive: -3 (high 07:05-14:25 (Mary G. Montgomery High School))
  false_positive: -3 (high 07:05-14:25 (Mattie T. Blount High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '06:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:05', '14:25'))

Total: 2 (entries) + -27 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 26 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:30-14:45 → middle 07:25-14:35 | start=1/3 (Δ5m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 07:15-14:45 → high 07:10-14:30 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (elementary 07:12-14:15 (Baldwin Arts and Academic Magnet))
  false_positive: -3 (elementary 07:40-14:45 (Blount Elementary))
  false_positive: -3 (elementary 07:45-14:45 (Bellingrath))
  false_positive: -3 (elementary 07:45-14:45 (Brewbaker Intermediate School))
  false_positive: -3 (elementary 07:45-14:45 (Brewbaker Primary School))
  false_positive: -3 (elementary 07:30-14:30 (Chisholm Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Floyd Middle School))
  false_positive: -3 (elementary 07:30-14:30 (Halcyon Elementary School))
  false_positive: -3 (elementary 07:30-14:30 (Highland Avenue Elementary))
  false_positive: -3 (elementary 07:30-14:30 (Highland Gardens ES))
  false_positive: -3 (elementary 07:30-14:30 (Morningview Elementary School))
  false_positive: -3 (elementary 07:30-14:30 (Southlawn Elementary School))
  false_positive: -3 (elementary 07:30-14:30 (Vaughn Road Elementary))
  false_positive: -3 (elementary 07:30-14:30 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 07:30-14:30 (Wilson))
  false_positive: -3 (middle 07:10-14:30 (LAMP))
  false_positive: -3 (middle 07:15-15:15 (McKee Middle School))
  false_positive: -3 (middle 07:30-14:30 (Southlawn Middle))
  false_positive: -3 (high 07:15-15:15 (Park Crossing Highschool))
  false_positive: -3 (high 07:55-15:10 (Peter Crump Elem.))
  false_positive: -3 (high 07:50-15:10 (Pintlala Elementary School))
  false_positive: -3 (high 08:00-15:00 (G. W. Carver High School))
  false_positive: -3 (high 07:15-15:15 (Jag High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:15', '15:15'))

Total: 14 (entries) + -93 (penalties) = 0/30 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:45-16:00 → middle 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 08:45-16:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (k-8 07:40-14:55 (K-8 Schools))
  missing_grade_level: -2 (Missing: high)

Total: 18 (entries) + -5 (penalties) = 13/30 (43.3%)

======================================================================
SPRINGDALE SCHOOL DISTRICT (AR) - 0512660
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 2

Entry Scores:
  middle 08:05-15:30 → middle 08:05-15:15 | start=3/3 (Δ0m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:05-15:30 → elementary 07:10-15:15 | start=0/3 (Δ55m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10
  MISSED: high 08:40-16:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (middle 08:05-14:35 (Central Junior High))
  false_positive: -3 (elementary 07:20-15:15 (Harp Elementary))
  false_positive: -3 (middle 08:05-15:15 (Sonora Middle School))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:05', '15:15'))
  missing_grade_level: -2 (Missing: high)

Total: 8 (entries) + -13 (penalties) = 0/30 (0.0%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 07:50-13:50 → elementary 07:50-14:45 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 08:00-14:45 → middle 07:30-14:15 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:15 (Red Mountain High School))

Total: 7 (entries) + -3 (penalties) = 4/20 (20.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 7 | Matched: 2

Entry Scores:
  middle 08:50-15:50 → middle 08:50-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:30-15:15 → high 07:05-16:45 | start=0/3 (Δ85m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (elementary 08:20-14:45 (Borton Elementary Magnet School))
  false_positive: -3 (middle 07:05-16:45 (Doolen Middle School))
  false_positive: -3 (middle 07:05-16:45 (Magee Middle School))
  false_positive: -3 (middle 07:05-16:45 (Pistor Middle School))
  false_positive: -3 (high 07:05-16:45 (Tucson High Magnet School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:05', '16:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:05', '16:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:05', '16:45'))

Total: 12 (entries) + -21 (penalties) = 0/20 (0.0%)

======================================================================
Los Angeles Unified (CA) - 0622710
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary Varies-Varies → elementary 08:10-14:35 | start=0/3 end=0/3 grade=2/2 name=0/1 conf=0/1 = 2/10
  high Varies-Varies → high 08:10-14:35 | start=0/3 end=0/3 grade=2/2 name=0/1 conf=0/1 = 2/10
  middle Varies-Varies → middle 08:10-14:35 | start=0/3 end=0/3 grade=2/2 name=0/1 conf=0/1 = 2/10

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
  false_positive: -3 (middle 08:15-14:44 (César Chávez Middle School))
  false_positive: -3 (high 08:00-13:54 (Conley-Cardillo High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:05'))

Total: 5 (entries) + -16 (penalties) = 0/10 (0.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 37 | Matched: 1

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
  false_positive: -3 (elementary 08:50-12:00 (Hallen))
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
  false_positive: -3 (elementary 08:15-14:00 (Bpt. Learning Ctr.))
  false_positive: -3 (elementary 07:40-10:20 (Skane (AM)))
  false_positive: -3 (elementary 11:20-14:00 (Skane (PM)))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:55'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:55'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))

Total: 9 (entries) + -154 (penalties) = 0/10 (0.0%)

======================================================================
New Haven School District (CT) - 0902790
======================================================================
Ground truth: 3 entries | Extracted: 26 | Matched: 3

Entry Scores:
  elementary 08:45-15:00 → elementary 08:30-15:00 | start=0/3 (Δ15m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:20-13:50 → high 07:30-14:00 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 07:50-14:20 → middle 08:35-14:50 | start=0/3 (Δ45m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:15 (Cooperative Arts and Humanities Magnet High School))
  false_positive: -3 (high 07:10-14:05 (New Haven Academy))
  false_positive: -3 (high 13:00-16:00 (Platt Technical High School))
  false_positive: -3 (high 07:30-14:17 (Sound School))
  false_positive: -3 (high 08:10-14:15 (Hill Regional Career High School))
  false_positive: -3 (high 07:10-14:05 (Hillhouse High School))
  false_positive: -3 (elementary 07:45-14:30 (John Martinez Elementary))
  false_positive: -3 (elementary 07:45-14:30 (Jepson Elementary))
  false_positive: -3 (elementary 07:45-14:15 (John Daniels Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Nathan Hale Elementary))
  false_positive: -3 (elementary 09:15-15:30 (Robert C. May Elementary))
  false_positive: -3 (elementary 09:15-15:30 (Ross-Woodward Elementary))
  false_positive: -3 (elementary 07:30-14:00 (Mauro-Sheridan Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Wexler (WG) Elementary))
  false_positive: -3 (elementary 07:55-14:10 (King-Robinson Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Lincoln-Bassett Elementary))
  false_positive: -3 (elementary 08:35-14:50 (Truman Elementary))
  false_positive: -3 (elementary 09:00-15:15 (All Saints Catholic Elementary))
  false_positive: -3 (elementary 07:30-17:15 (St. Martin Elementary))
  false_positive: -3 (elementary 08:15-15:00 (St. Thomas Elementary))
  false_positive: -3 (elementary 07:30-13:30 (Edmonds Cofield Prep Elementary))
  false_positive: -3 (elementary 08:10-15:00 (Foote Elementary))
  false_positive: -3 (elementary 07:40-15:30 (Hopkins Elementary))
  duplicate_extraction: -2 (Duplicate: ('high', '07:10', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))

Total: 9 (entries) + -81 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 30 | Matched: 3

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
Ground truth: 1 entries | Extracted: 17 | Matched: 1

Entry Scores:
  high 07:30-14:30 → high 08:05-15:00 | start=0/3 (Δ35m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:05-15:00 (Middletown HS))
  false_positive: -3 (high 08:05-15:00 (Odessa HS))
  false_positive: -3 (high 08:05-15:00 (Special Program MS/HS))
  false_positive: -3 (middle 07:15-14:10 (Everett Meredith MS))
  false_positive: -3 (middle 07:15-14:10 (Louis L. Redding MS))
  false_positive: -3 (middle 07:15-14:10 (Alfred G. Waters MS))
  false_positive: -3 (middle 07:15-14:10 (Cantwell’s Bridge MS))
  false_positive: -3 (elementary 09:05-15:50 (Brick Mill ES/ECC))
  false_positive: -3 (elementary 09:05-15:50 (Bunker Hill ES))
  false_positive: -3 (elementary 09:05-15:50 (Cedar Lane ES/ECC))
  false_positive: -3 (elementary 09:05-15:50 (Lorewood Grove ES))
  false_positive: -3 (elementary 09:05-15:50 (Crystal Run ES))
  false_positive: -3 (elementary 09:05-15:50 (Old State ES & Spring Meadow ECC))
  false_positive: -3 (elementary 09:05-15:50 (Olive B. Loss ES))
  false_positive: -3 (elementary 09:05-15:50 (Silver Lake ES))
  false_positive: -3 (elementary 09:05-15:50 (Townsend ES/ECC))
  duplicate_extraction: -2 (Duplicate: ('high', '08:05', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:05', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:05', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:15', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:15', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:15', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:50'))

Total: 2 (entries) + -76 (penalties) = 0/10 (0.0%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 08:00-15:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (middle 07:05-14:05 (Shue-Medill Middle School))
  false_positive: -3 (high 07:00-14:05 (Newark High School))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -8 (penalties) = 0/10 (0.0%)

======================================================================
Red Clay Consolidated School District (DE) - 1001300
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 09:05-15:50 → elementary 07:25-14:35 | start=0/3 (Δ100m) end=0/3 (Δ75m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:25-14:35 (McKean High School))
  false_positive: -3 (high 07:25-14:35 (Alexis I du Pont High School))
  false_positive: -3 (high 07:25-14:35 (John Dickinson High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:25', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:25', '14:35'))

Total: 2 (entries) + -13 (penalties) = 0/10 (0.0%)

======================================================================
BROWARD (FL) - 1200180
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  high 07:40-14:40 → high 07:40-14:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 09:30-16:10 → middle 09:30-16:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:50-13:50 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 20 (entries) + 0 (penalties) = 20/30 (66.7%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 24 | Matched: 2

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 09:30-16:04 → middle 07:10-14:10 | start=0/3 (Δ140m) end=0/3 (Δ114m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 07:20-14:20 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  false_positive: -3 (elementary 08:15-15:30 (Castleview))
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
  false_positive: -3 (elementary 08:45-16:00 (OCPS Academic Center for Excellence K-8))
  false_positive: -3 (elementary 08:15-15:30 (Orange Center))
  false_positive: -3 (elementary 08:15-15:30 (Eccleston))
  false_positive: -3 (elementary 08:15-15:30 (Orlo Vista))
  false_positive: -3 (elementary 08:15-15:30 (Engelwood))
  false_positive: -3 (elementary 08:15-15:30 (Hiawassee))
  false_positive: -3 (elementary 08:15-15:30 (Pineloch))
  false_positive: -3 (elementary 08:15-15:30 (Pinewood))
  false_positive: -3 (elementary 08:15-15:30 (Ivey Lane))
  false_positive: -3 (elementary 08:15-15:30 (Ridgewood Park))
  false_positive: -3 (elementary 08:15-15:30 (Washington Shores))
  false_positive: -3 (elementary 08:15-15:30 (Rock Lake))
  false_positive: -3 (elementary 08:15-15:30 (Rolling Hills))
  false_positive: -3 (elementary 08:15-15:30 (Rosemont))
  false_positive: -3 (elementary 08:15-15:30 (Shingle Creek))
  false_positive: -3 (elementary 08:15-15:30 (Wheatley))
  false_positive: -3 (elementary 08:15-15:30 (Tangelo Park))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  missing_grade_level: -2 (Missing: high)

Total: 11 (entries) + -108 (penalties) = 0/30 (0.0%)

======================================================================
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:50 (High School))

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
Ground truth: 1 entries | Extracted: 6 | Matched: 1

Entry Scores:
  high 08:40-15:48 → high 08:40-15:48 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:40-15:48 (Bonneville Elementary Schools (multiple elementary schools in district)))
  false_positive: -3 (middle 08:40-15:48 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))
  false_positive: -3 (high 08:40-15:48 (Hillcrest High School))
  false_positive: -3 (high 08:00-14:45 (Lincoln High School))
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
  false_positive: -3 (middle 07:45-14:05 (HAROLD DURGIN SUCCESS ACADEMY))
  false_positive: -3 (middle 07:45-14:30 (CITY ARTS & SCIENCES ACADEMY (CASA)))
  false_positive: -3 (middle 07:45-14:30 (DISCOVERY ACADEMY))
  false_positive: -3 (middle 07:45-14:30 (FREDERICK DOUGLASS COLLEGIATE ACADEMY))
  false_positive: -3 (high 07:45-14:30 (LYNN ENGLISH HIGH SCHOOL))
  false_positive: -3 (high 07:45-14:30 (LYNN VOCATIONAL TECHNICAL INSTITUTE))
  false_positive: -3 (middle 07:45-14:15 (PICKERING MIDDLE SCHOOL))
  false_positive: -3 (middle 07:45-14:30 (VIRGINIA BARTON CENTER AT BRIARCLIFF (SECONDARY TEAMS)))
  false_positive: -3 (middle 07:45-14:15 (THURGOOD MARSHALL MIDDLE SCHOOL))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:15'))

Total: 20 (entries) + -132 (penalties) = 0/30 (0.0%)

======================================================================
Worcester (MA) - 2513230
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  middle 08:47-14:17 → middle 08:47-15:10 | start=3/3 (Δ0m) end=0/3 (Δ53m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:20-13:43 (Burncoat High))
  false_positive: -3 (high 07:20-13:43 (North High))
  false_positive: -3 (high 07:20-13:43 (Worcester Technical High))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:43'))

Total: 5 (entries) + -13 (penalties) = 0/10 (0.0%)

======================================================================
Bangor Public Schools (ME) - 2302820
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 2

Entry Scores:
  middle 08:15-14:30 → middle 07:50-14:30 | start=0/3 (Δ25m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:55-15:00 → elementary 07:45-15:00 | start=0/3 (Δ70m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  MISSED: high 08:00-14:00 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:45-14:35 (Bangor Regional Program))
  missing_grade_level: -2 (Missing: high)

Total: 10 (entries) + -5 (penalties) = 5/30 (16.7%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  middle 07:35-14:00 → middle 07:15-14:00 | start=0/3 (Δ20m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:45-14:00 → high 07:15-14:00 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  MISSED: elementary 08:20-14:50 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: elementary)

Total: 10 (entries) + -2 (penalties) = 8/30 (26.7%)

======================================================================
DESOTO CO SCHOOL DIST (MS) - 2801320
======================================================================
Ground truth: 3 entries | Extracted: 26 | Matched: 3

Entry Scores:
  elementary 08:30-15:25 → elementary 08:30-15:25 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:25-15:45 → high 08:25-15:45 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:40 → middle 08:00-15:40 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:25-15:20 (Center Hill Elementary))
  false_positive: -3 (elementary 08:25-15:20 (DeSoto Central Primary))
  false_positive: -3 (elementary 08:30-15:25 (DeSoto Central Elementary))
  false_positive: -3 (middle 08:00-15:40 (DeSoto Central Middle))
  false_positive: -3 (high 08:25-15:45 (DeSoto Central High))
  false_positive: -3 (elementary 07:40-14:35 (Hernando Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Oak Grove Central Elementary))
  false_positive: -3 (elementary 07:45-14:40 (Hernando Hills Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Hernando Intermediate School))
  false_positive: -3 (high 07:30-14:55 (Hernando High))
  false_positive: -3 (elementary 07:45-14:40 (Horn Lake Elementary))
  false_positive: -3 (elementary 07:45-14:40 (Shadow Oaks Elementary))
  false_positive: -3 (elementary 07:40-14:20 (Horn Lake Intermediate))
  false_positive: -3 (high 07:35-14:55 (Horn Lake High))
  false_positive: -3 (elementary 08:30-15:25 (Lake Cormorant Elementary))
  false_positive: -3 (elementary 08:30-15:25 (Walls Elementary))
  false_positive: -3 (middle 08:00-15:40 (Lake Cormorant Middle))
  false_positive: -3 (high 08:25-15:45 (Lake Cormorant High))
  false_positive: -3 (elementary 07:40-14:40 (Lewisburg Primary))
  false_positive: -3 (elementary 07:40-14:40 (Lewisburg Elementary))
  false_positive: -3 (elementary 07:35-14:30 (Lewisburg Intermediate))
  false_positive: -3 (middle 08:00-15:40 (Southaven Middle))
  false_positive: -3 (high 08:25-15:45 (Southaven High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:20'))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:40'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:25', '15:45'))

Total: 27 (entries) + -99 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 10 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:00-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Culler Middle School))
  false_positive: -3 (middle 08:00-15:00 (Lux Middle School))
  false_positive: -3 (middle 08:00-15:00 (Pound Middle School))
  false_positive: -3 (high 08:00-15:00 (North Star High))
  false_positive: -3 (high 08:00-15:00 (Northeast High))
  false_positive: -3 (high 08:00-15:00 (Northwest High))
  false_positive: -3 (high 08:00-15:00 (Southeast High))
  false_positive: -3 (high 08:00-15:00 (Southwest High))
  false_positive: -3 (high 08:00-15:00 (Standing Bear High))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))

Total: 9 (entries) + -43 (penalties) = 0/10 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 67 | Matched: 1

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
  false_positive: -3 (high 08:30-15:00 (Inspire Academy (6-12)))
  false_positive: -3 (high 08:00-14:35 (McQueen))
  false_positive: -3 (high 08:00-16:00 (North Star Online School (K-12)))
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
  false_positive: -3 (middle 07:30-14:00 (Cold Springs 6-8))
  false_positive: -3 (middle 07:30-14:00 (Depoali))
  false_positive: -3 (middle 07:30-14:00 (Desert Skies))
  false_positive: -3 (middle 07:30-14:00 (Dilworth-STEM))
  false_positive: -3 (middle 07:30-14:00 (Herz))
  false_positive: -3 (middle 07:50-14:25 (Incline))
  false_positive: -3 (middle 07:30-14:00 (Mendive))
  false_positive: -3 (middle 07:30-13:54 (O' Brien-STEM))
  false_positive: -3 (middle 09:30-15:30 (Picollo (PK-12)))
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

Total: 2 (entries) + -288 (penalties) = 0/10 (0.0%)

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
  false_positive: -3 (elementary 09:10-15:40 (James N. Gamble Montessori Elementary))
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
Ground truth: 3 entries | Extracted: 62 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10
  middle 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (elementary 07:35-14:05 (Adlai E. Stevenson))
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (elementary 09:35-16:05 (Orchard))
  false_positive: -3 (elementary 07:35-14:05 (Alfred A. Benesch))
  false_positive: -3 (elementary 09:35-16:05 (George W. Carver))
  false_positive: -3 (elementary 09:35-16:05 (Paul L. Dunbar))
  false_positive: -3 (elementary 07:35-14:05 (Almira))
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
  false_positive: -3 (elementary 08:35-15:05 (Kenneth Clement Boys’))
  false_positive: -3 (elementary 07:35-14:05 (Stephanie Tubbs Jones School))
  false_positive: -3 (elementary 09:35-16:05 (Bolton))
  false_positive: -3 (elementary 09:35-16:05 (Leadership Academy Stonebrook-White))
  false_positive: -3 (elementary 09:35-16:05 (Louisa May Alcott))
  false_positive: -3 (elementary 08:40-15:10 (Campus International KB))
  false_positive: -3 (elementary 07:35-14:05 (Luis Mufioz Marin))
  false_positive: -3 (elementary 08:35-15:05 (Sunbeam))
  false_positive: -3 (elementary 07:35-14:05 (GinieseAneasy))
  false_positive: -3 (elementary 09:35-16:05 (Marion C. Seltzer))
  false_positive: -3 (elementary 09:35-16:05 (Tremont Montessori))
  false_positive: -3 (elementary 09:35-16:05 (Charles Dickens))
  false_positive: -3 (elementary 08:35-15:05 (Marion-Sterling))
  false_positive: -3 (elementary 08:05-14:35 (Valley View Boys’))
  false_positive: -3 (elementary 07:35-14:05 (Clara E. Westropp))
  false_positive: -3 (elementary 07:35-14:05 (Mary B. Martin))
  false_positive: -3 (elementary 07:35-14:05 (Mary Church Terrell))
  false_positive: -3 (elementary 08:35-15:05 (Wade Park))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (elementary 07:35-14:05 (Mary M. Bethune))
  false_positive: -3 (elementary 08:05-14:35 (Warner Girls))
  false_positive: -3 (elementary 07:35-14:05 (Daniel E. Morgan))
  false_positive: -3 (elementary 07:35-14:05 (Memorial))
  false_positive: -3 (elementary 08:35-15:05 (Denison))
  false_positive: -3 (elementary 09:35-16:05 (Miles))
  false_positive: -3 (elementary 08:35-15:05 (Robinson G. Jones))
  false_positive: -3 (elementary 08:25-14:55 (Garrett Morgan School of Early College))
  false_positive: -3 (elementary 08:35-15:05 (Lincoln-West School of Science & Health))
  false_positive: -3 (elementary 08:35-15:05 (Campus International H.S.))
  false_positive: -3 (elementary 08:25-14:55 (Garrett Morgan School of Early College))
  false_positive: -3 (elementary 08:35-15:05 (Max S. Hayes High School))
  false_positive: -3 (elementary 08:00-15:00 (Cleveland Early College H.S.))
  false_positive: -3 (elementary 09:00-15:30 (Cleveland H.S. for Digital Arts))
  false_positive: -3 (elementary 08:35-15:05 (Ginn Academy))
  false_positive: -3 (elementary 08:35-15:05 (Natividad Pagan International))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Scholar))
  false_positive: -3 (elementary 08:00-15:00 (John Adams College & Architecture & Design Career Academy))
  false_positive: -3 (elementary 08:00-14:30 (New Tech West High School))
  false_positive: -3 (elementary 08:00-14:30 (Rhodes College & Rhodes School of))
  false_positive: -3 (elementary 08:00-14:30 (John F. Kennedy High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '14:55'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  missing_grade_level: -2 (Missing: middle)
  missing_grade_level: -2 (Missing: high)

Total: 23 (entries) + -287 (penalties) = 0/30 (0.0%)

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
  elementary 08:08-14:50 → elementary 08:08-14:35 | start=3/3 (Δ0m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle School))
  false_positive: -3 (high 08:10-14:35 (Burlington High School))

Total: 5 (entries) + -6 (penalties) = 0/10 (0.0%)

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
  middle 07:27-15:06 → middle 07:27-15:20 | start=3/3 (Δ0m) end=0/3 (Δ14m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 06:35-15:10 (Huntington High School))
  false_positive: -3 (middle 07:00-15:20 (Huntington Middle School))
  false_positive: -3 (high 07:15-15:10 (Cabell Midland High School))

Total: 5 (entries) + -9 (penalties) = 0/10 (0.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:15-14:15 → elementary 07:15-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 08:15-15:10 (Elkview Middle))
  false_positive: -3 (middle 08:15-15:10 (Dunbar Middle))
  false_positive: -3 (high 08:36-15:36 (Nitro High))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:15', '15:10'))

Total: 9 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Albany County School District #1 (WY) - 5600730
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  middle 08:00-15:05 → middle 08:00-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:02-15:00 → elementary 07:45-15:00 | start=0/3 (Δ17m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:45-15:45 → high 06:45-16:45 | start=0/3 (Δ60m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 17 (entries) + 0 (penalties) = 17/30 (56.7%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 07:50-15:15 → elementary 07:45-15:00 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 08:00-15:55 → high 07:45-16:05 | start=0/3 (Δ15m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 9 (entries) + 0 (penalties) = 9/30 (30.0%)