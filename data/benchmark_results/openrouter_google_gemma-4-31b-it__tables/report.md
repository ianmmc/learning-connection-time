# Benchmark Report: openrouter:google/gemma-4-31b-it
Run date: 2026-06-13T22:36:36
Districts tested: 7
Total extraction time: 236s (avg 33.8s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 25.9% |
| JSON parse success | 100.0% |
| Grade coverage rate | 89.5% |
| False positive rate | 23.43/district |
| Mean time/extraction | 33.8s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| Sweetwater County School Distr | WY | 17 | 30 | 56.7% | false_positive, false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+35 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+38 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+60 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+38 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+93 more) |  |

## Detailed Scoring

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 25 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (Anne Wien Elementary))
  false_positive: -3 (elementary 08:00-14:30 (Arctic Light Elementary))
  false_positive: -3 (elementary 08:15-14:45 (Barnette Magnet))
  false_positive: -3 (elementary 08:45-15:15 (Boreal Sun Charter))
  false_positive: -3 (elementary 08:15-14:45 (Chinook Montessori Charter))
  false_positive: -3 (elementary 09:15-15:45 (Denali Elementary))
  false_positive: -3 (elementary 09:50-15:45 (Effie Kokrine Charter))
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

Total: 9 (entries) + -100 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 34 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:45 → middle 07:30-14:45 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:15-14:45 → high 07:20-14:45 | start=1/3 (Δ5m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (high 07:45-14:45 (Booker T. Washington (BTW) Magnet High School))
  false_positive: -3 (middle 07:45-14:45 (Brewbaker Middle School))
  false_positive: -3 (elementary 08:10-14:45 (Brewbaker Primary School))
  false_positive: -3 (elementary 08:40-15:40 (Carver Elementary Arts Magnet))
  false_positive: -3 (elementary 08:10-15:10 (Catoma Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Chisholm Elementary))
  false_positive: -3 (elementary 07:30-15:00 (Dannelly Elementary))
  false_positive: -3 (elementary 08:00-15:00 (Davis Elementary School))
  false_positive: -3 (elementary 07:20-14:45 (Dozier Elementary))
  false_positive: -3 (elementary 08:00-15:00 (E.D.Nixon Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 07:45-15:30 (Flowers Elementary School))
  false_positive: -3 (middle 08:30-15:40 (Floyd Middle School))
  false_positive: -3 (elementary 08:10-15:10 (Halcyon Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Highland Avenue Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Highland Gardens ES))
  false_positive: -3 (high 07:30-14:45 (Jag High School))
  false_positive: -3 (middle 07:25-14:35 (Johnnie R. Carr Middle School))
  false_positive: -3 (high 07:15-15:15 (Lanier High School))
  false_positive: -3 (middle 07:30-14:30 (McKee Middle School))
  false_positive: -3 (elementary 08:10-15:10 (Morningview Elementary School))
  false_positive: -3 (elementary 08:10-15:00 (Morris Elementary))
  false_positive: -3 (high 07:30-15:00 (Park Crossing Highschool))
  false_positive: -3 (elementary 07:30-14:45 (Peter Crump Elem.))
  false_positive: -3 (elementary 07:50-15:00 (Pintlala Elementary School))
  false_positive: -3 (elementary 08:00-15:10 (Seth Johnson Elementary School))
  false_positive: -3 (elementary 08:10-15:00 (Southlawn Elementary School))
  false_positive: -3 (middle 08:00-14:45 (Southlawn Middle))
  false_positive: -3 (elementary 07:30-15:10 (Vaughn Road Elementary))
  false_positive: -3 (elementary 08:10-15:00 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 08:00-15:25 (William Silas Garrett Elementary))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))

Total: 25 (entries) + -113 (penalties) = 0/30 (0.0%)

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
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 08:00-15:30 → elementary 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:15-15:15 → high 08:15-15:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:00-15:30 → middle 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Total: 27 (entries) + 0 (penalties) = 27/30 (90.0%)

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
Ground truth: 3 entries | Extracted: 52 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10
  middle 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (elementary 09:35-16:05 (Adlai E. Stevenson))
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
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
  false_positive: -3 (elementary 09:35-16:05 (Stonebrook-White))
  false_positive: -3 (elementary 09:35-16:05 (Bunerotalerateee))
  false_positive: -3 (elementary 09:35-16:05 (Louisa May Alcott))
  false_positive: -3 (elementary 08:40-15:10 (Campus International KB))
  false_positive: -3 (elementary 07:35-14:05 (Luis Mufioz Marin))
  false_positive: -3 (elementary 08:35-15:05 (Sunbeam))
  false_positive: -3 (elementary 07:35-14:05 (GinieseAneasy))
  false_positive: -3 (elementary 09:35-16:05 (Marion C. Seltzer))
  false_positive: -3 (elementary 09:35-16:05 (Tremont Montessori))
  false_positive: -3 (elementary 09:35-16:05 (Charles Dickens))
  false_positive: -3 (elementary 08:35-15:05 (Marion-Sterling))
  false_positive: -3 (elementary 08:05-14:35 (Valley View Boys’ Leadership Academy))
  false_positive: -3 (elementary 07:35-14:05 (Clara E. Westropp))
  false_positive: -3 (elementary 07:35-14:05 (Mary B. Martin))
  false_positive: -3 (elementary 08:35-15:05 (Wade Park))
  false_positive: -3 (elementary 09:35-16:05 (Clark))
  false_positive: -3 (elementary 09:35-16:05 (Mary Church Terrell))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (elementary 07:35-14:05 (Mary M. Bethune))
  false_positive: -3 (elementary 08:05-14:35 (Warner Girls))
  false_positive: -3 (elementary 07:35-14:05 (Daniel E. Morgan))
  false_positive: -3 (elementary 07:35-14:05 (Memorial))
  false_positive: -3 (elementary 16:05-16:05 (Waverly))
  false_positive: -3 (elementary 08:35-15:05 (Denison))
  false_positive: -3 (elementary 09:35-16:05 (Miles))
  false_positive: -3 (elementary 09:35-16:05 (Dike School of the Arts))
  false_positive: -3 (elementary 08:35-15:05 (Miles Park))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:05', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 23 (entries) + -241 (penalties) = 0/30 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-15:15 (4-6 Elementary Schools))
  false_positive: -3 (elementary 08:00-15:55 (Wamsutter K-8))

Total: 23 (entries) + -6 (penalties) = 17/30 (56.7%)