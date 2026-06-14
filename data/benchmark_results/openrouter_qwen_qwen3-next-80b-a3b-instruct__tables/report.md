# Benchmark Report: openrouter:qwen/qwen3-next-80b-a3b-instruct
Run date: 2026-06-13T22:18:39
Districts tested: 7
Total extraction time: 44s (avg 6.3s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 14.7% |
| JSON parse success | 100.0% |
| Grade coverage rate | 88.9% |
| False positive rate | 20.43/district |
| Mean time/extraction | 6.3s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 16 | 30 | 53.3% | missing_grade_level |  |
| Sweetwater County School Distr | WY | 9 | 30 | 30.0% |  |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+36 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+54 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+62 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+38 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+44 more) |  |

## Detailed Scoring

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
  false_positive: -3 (elementary 08:30-15:00 (WATERSHED CHARTER))
  false_positive: -3 (elementary 09:15-15:45 (WELLER ELEMENTARY))
  false_positive: -3 (high 07:30-14:00 (W E S T V A L L E Y H I G H))
  false_positive: -3 (elementary 09:15-15:45 (WOODRIVER ELEMENTARY))
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

Total: 9 (entries) + -103 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 34 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:30-14:45 → middle 07:30-14:30 | start=3/3 (Δ0m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:15-14:45 → high 07:45-14:45 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:15-15:15 (Lanier High School))
  false_positive: -3 (high 07:45-14:45 (Park Crossing Highschool))
  false_positive: -3 (middle 07:30-14:30 (Brewbaker Middle School))
  false_positive: -3 (middle 07:30-14:30 (Goodwyn Middle School))
  false_positive: -3 (middle 07:25-14:35 (Johnnie R. Carr Middle School))
  false_positive: -3 (middle 07:30-14:30 (McKee Middle School))
  false_positive: -3 (middle 08:00-15:00 (Southlawn Middle))
  false_positive: -3 (elementary 08:10-15:10 (Brewbaker Primary School))
  false_positive: -3 (elementary 08:40-15:40 (Carver Elementary Arts Magnet))
  false_positive: -3 (elementary 08:10-15:10 (Catoma Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Chisholm Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Dannelly Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Davis Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Dozier Elementary))
  false_positive: -3 (elementary 08:10-15:10 (E.D.Nixon Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Flowers Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Forest Avenue Academic Magnet))
  false_positive: -3 (elementary 08:10-15:10 (Halcyon Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Highland Avenue Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Highland Gardens ES))
  false_positive: -3 (elementary 08:10-15:10 (Morningview Elementary School))
  false_positive: -3 (elementary 08:10-15:00 (Morris Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Percy Julian))
  false_positive: -3 (elementary 08:10-15:10 (Peter Crump Elem.))
  false_positive: -3 (elementary 08:10-15:10 (Pintlala Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Seth Johnson Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Southlawn Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Vaughn Road Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 08:10-15:10 (William Silas Garrett Elementary))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
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

Total: 18 (entries) + -145 (penalties) = 0/30 (0.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 40 | Matched: 1

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
  false_positive: -3 (elementary 07:40-10:20 (Skane (AM)))
  false_positive: -3 (elementary 11:20-14:00 (Skane (PM)))
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

Total: 9 (entries) + -169 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 24 | Matched: 3

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-14:20 → high 07:10-14:10 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 09:30-16:04 → middle 08:45-16:00 | start=0/3 (Δ45m) end=1/3 (Δ4m) grade=2/2 name=0/1 conf=0/1 = 3/10

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

Total: 14 (entries) + -103 (penalties) = 0/30 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 30 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=0/1 = 6/10

Penalties:
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (elementary 09:35-16:05 (Adlai E. Stevenson))
  false_positive: -3 (elementary 08:40-15:10 (Campus International K-8))
  false_positive: -3 (elementary 08:05-14:35 (Valley View Boys'))
  false_positive: -3 (elementary 08:05-14:35 (Warner Girls'))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (high 09:00-15:30 (Bard High School))
  false_positive: -3 (high 08:25-14:55 (Garrett Morgan School of Engineering and Innovation))
  false_positive: -3 (high 08:00-15:00 (Cleveland Early College H.S.))
  false_positive: -3 (high 09:00-15:30 (Cleveland H.S. for Digital Arts))
  false_positive: -3 (high 09:00-15:30 (MC?STEM High School))
  false_positive: -3 (high 08:35-15:05 (Ginn Academy))
  false_positive: -3 (high 08:35-15:05 (Natividad Pagan International))
  false_positive: -3 (high 08:35-15:05 (Glenville High School))
  false_positive: -3 (high 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (high 08:00-14:30 (Cleveland Schoolar))
  false_positive: -3 (high 08:00-15:00 (John Adams College & Architecture & Design Career Academy))
  false_positive: -3 (high 08:00-14:30 (Cleveland School of Science & Medicine))
  false_positive: -3 (high 08:35-15:05 (Cleveland School of the Arts))
  false_positive: -3 (high 08:00-14:30 (Collinwood High School))
  false_positive: -3 (high 08:35-15:05 (Davis Aerospace & Maritime))
  false_positive: -3 (high 08:35-15:05 (Facing History New Tech High School))
  false_positive: -3 (high 08:35-15:05 (John F. Kennedy High School))
  false_positive: -3 (high 08:00-14:30 (John Marshall School of Information Technology))
  false_positive: -3 (high 08:00-14:30 (Rhodes School of Environmental Studies))
  false_positive: -3 (high 08:00-14:30 (New Tech West High School))
  false_positive: -3 (high 08:35-15:05 (East Technical High School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:35', '15:05'))
  missing_grade_level: -2 (Missing: middle)

Total: 22 (entries) + -121 (penalties) = 0/30 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 07:50-15:15 → elementary 07:45-15:00 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 08:00-15:55 → high 07:45-16:05 | start=0/3 (Δ15m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 9 (entries) + 0 (penalties) = 9/30 (30.0%)