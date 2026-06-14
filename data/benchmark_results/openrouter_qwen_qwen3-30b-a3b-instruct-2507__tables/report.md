# Benchmark Report: openrouter:qwen/qwen3-30b-a3b-instruct-2507
Run date: 2026-06-13T22:26:39
Districts tested: 7
Total extraction time: 103s (avg 14.7s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 20.6% |
| JSON parse success | 100.0% |
| Grade coverage rate | 76.5% |
| False positive rate | 24.71/district |
| Mean time/extraction | 14.7s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Sweetwater County School Distr | WY | 19 | 30 | 63.3% |  |  |
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+32 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+59 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+60 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+39 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+122 more) |  |

## Detailed Scoring

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 23 | Matched: 1

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
  false_positive: -3 (high 07:30-14:00 (Hutchison High))
  false_positive: -3 (high 07:30-14:00 (Lathrop High))
  false_positive: -3 (elementary 09:15-15:45 (Ladd Elementary))
  false_positive: -3 (elementary 09:00-15:30 (North Pole Elementary))
  false_positive: -3 (high 07:30-14:00 (North Pole High))
  false_positive: -3 (middle 07:50-14:20 (North Pole Middle))
  false_positive: -3 (middle 07:50-14:20 (Randy Smith Middle))
  false_positive: -3 (middle 07:50-14:20 (Ryan Middle))
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
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))

Total: 9 (entries) + -92 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 34 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:15-14:45 → high 08:10-15:10 | start=0/3 (Δ55m) end=0/3 (Δ25m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 07:30-14:45 → middle 08:10-15:10 | start=0/3 (Δ40m) end=0/3 (Δ25m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:10-15:10 (G.W. Carver High School))
  false_positive: -3 (high 08:10-15:10 (Jag High School))
  false_positive: -3 (high 08:10-15:10 (Lanier High School))
  false_positive: -3 (high 08:10-15:10 (Park Crossing Highschool))
  false_positive: -3 (middle 08:10-15:10 (Floyd Middle School))
  false_positive: -3 (middle 08:10-15:10 (Goodwyn Middle School))
  false_positive: -3 (middle 08:10-15:10 (Johnnie R. Carr Middle School))
  false_positive: -3 (middle 08:10-15:10 (McKee Middle School))
  false_positive: -3 (middle 08:10-15:10 (Southlawn Middle))
  false_positive: -3 (elementary 08:10-15:10 (Bellingrath))
  false_positive: -3 (elementary 08:10-15:10 (Carver Elementary Arts Magnet))
  false_positive: -3 (elementary 08:10-15:10 (Catoma Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Chisholm Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Dalraida))
  false_positive: -3 (elementary 08:10-15:10 (Dannelly Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Davis Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Dozier Elementary))
  false_positive: -3 (elementary 08:10-15:10 (E.D.Nixon Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Flowers Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Halcyon Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Highland Avenue Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Highland Gardens ES))
  false_positive: -3 (elementary 08:10-15:10 (Morningview Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Morris Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Pintlala Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Seth Johnson Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Southlawn Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Vaughn Road Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 08:10-15:10 (William Silas Garrett Elementary))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))

Total: 13 (entries) + -155 (penalties) = 0/30 (0.0%)

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
  false_positive: -3 (elementary 08:15-14:00 (Bpt. Learning Ctr.))
  false_positive: -3 (middle 07:50-14:20 (Curiale))
  false_positive: -3 (middle 07:50-14:20 (Read))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:53', '14:30'))

Total: 9 (entries) + -163 (penalties) = 0/10 (0.0%)

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
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 23 | Matched: 2

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 09:30-16:04 → middle 07:10-14:10 | start=0/3 (Δ140m) end=0/3 (Δ114m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 07:20-14:20 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  false_positive: -3 (elementary 08:15-15:30 (Lovell))
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
  false_positive: -3 (elementary 08:45-15:00 (Deerwood))
  false_positive: -3 (elementary 08:15-15:30 (Orange Center))
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
  false_positive: -3 (elementary 08:15-15:30 (Pineloch))
  false_positive: -3 (elementary 08:15-15:30 (Pinewood))
  false_positive: -3 (elementary 08:15-15:30 (Shingle Creek))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:45', '15:00'))
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

Total: 11 (entries) + -105 (penalties) = 0/30 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 63 | Matched: 1

Entry Scores:
  elementary 08:35-15:05 → elementary 07:35-14:05 | start=0/3 (Δ60m) end=0/3 (Δ60m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: high 08:35-15:05 (unnamed) → 0/10
  MISSED: middle 08:35-15:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:35-14:05 (Andrew J. Rickoff))
  false_positive: -3 (elementary 07:35-14:05 (Artemus Ward))
  false_positive: -3 (elementary 07:35-14:05 (Benjamin Franklin))
  false_positive: -3 (elementary 07:35-14:05 (Bolton))
  false_positive: -3 (elementary 07:35-14:05 (Bunerotalerateee))
  false_positive: -3 (elementary 07:35-14:05 (Campus International KB))
  false_positive: -3 (elementary 07:35-14:05 (Charles Dickens))
  false_positive: -3 (elementary 07:35-14:05 (Clark))
  false_positive: -3 (elementary 07:35-14:05 (Cleveland Metro Remote School))
  false_positive: -3 (elementary 07:35-14:05 (Daniel E. Morgan))
  false_positive: -3 (elementary 07:35-14:05 (Denison))
  false_positive: -3 (elementary 07:35-14:05 (Dike School of the Arts))
  false_positive: -3 (elementary 07:35-14:05 (Douglas MacArthur Girls’))
  false_positive: -3 (elementary 07:35-14:05 (East Clark))
  false_positive: -3 (elementary 07:35-14:05 (Euclid Park))
  false_positive: -3 (elementary 07:35-14:05 (Garfield))
  false_positive: -3 (elementary 07:35-14:05 (Halle))
  false_positive: -3 (elementary 07:35-14:05 (Leadership Academy Nathan Hale))
  false_positive: -3 (elementary 07:35-14:05 (Leadership Academy Stonebrook-White))
  false_positive: -3 (elementary 07:35-14:05 (Luis Mufioz Marin))
  false_positive: -3 (elementary 07:35-14:05 (Marion C. Seltzer))
  false_positive: -3 (elementary 07:35-14:05 (Marion-Sterling))
  false_positive: -3 (elementary 07:35-14:05 (Mary B. Martin))
  false_positive: -3 (elementary 07:35-14:05 (Mary Church Terrell))
  false_positive: -3 (elementary 07:35-14:05 (Mary M. Bethune))
  false_positive: -3 (elementary 07:35-14:05 (Memorial))
  false_positive: -3 (elementary 07:35-14:05 (Miles))
  false_positive: -3 (elementary 07:35-14:05 (Miles Park))
  false_positive: -3 (elementary 07:35-14:05 (Montessori Campus))
  false_positive: -3 (elementary 07:35-14:05 (Natividad Pagan International))
  false_positive: -3 (elementary 07:35-14:05 (Newcomers Academy))
  false_positive: -3 (elementary 07:35-14:05 (Newcomers Academy Willson))
  false_positive: -3 (elementary 07:35-14:05 (Robinson G. Jones))
  false_positive: -3 (elementary 07:35-14:05 (Scranton))
  false_positive: -3 (elementary 07:35-14:05 (Sunbeam))
  false_positive: -3 (elementary 07:35-14:05 (Tremont Montessori))
  false_positive: -3 (elementary 07:35-14:05 (Valley View Boys’))
  false_positive: -3 (elementary 07:35-14:05 (Warner Girls))
  false_positive: -3 (elementary 07:35-14:05 (William C. Bryant))
  false_positive: -3 (elementary 07:35-14:05 (Waverly))
  false_positive: -3 (elementary 07:35-14:05 (Wilbur Wright))
  false_positive: -3 (elementary 07:35-14:05 (Willson))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland School of))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland School of the Arts))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Schoolar))
  false_positive: -3 (elementary 08:00-14:30 (Collinwood High School))
  false_positive: -3 (elementary 08:00-14:30 (Davis Aerospace & Maritime))
  false_positive: -3 (elementary 08:00-14:30 (East Technical High School))
  false_positive: -3 (elementary 08:00-14:30 (Facing History))
  false_positive: -3 (elementary 08:00-14:30 (John Adams College &))
  false_positive: -3 (elementary 08:00-14:30 (John F. Kennedy High School))
  false_positive: -3 (elementary 08:00-14:30 (John Marshall School of))
  false_positive: -3 (elementary 08:00-14:30 (New Tech West High School))
  false_positive: -3 (elementary 08:00-14:30 (Rhodes College &))
  false_positive: -3 (elementary 08:00-14:30 (Rhodes School of))
  false_positive: -3 (elementary 08:00-14:30 (Science & Medicine))
  false_positive: -3 (elementary 08:00-14:30 (The School of One Bosed onsite starvlend times))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Early CollegeH.S.))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland H.S. for Digital Arts))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland School of))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland School of the Arts))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:30'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 2 (entries) + -312 (penalties) = 0/30 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  elementary 07:50-15:15 → elementary 07:45-15:05 | start=1/3 (Δ5m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 3/10

Total: 19 (entries) + 0 (penalties) = 19/30 (63.3%)