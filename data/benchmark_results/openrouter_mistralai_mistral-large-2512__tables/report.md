# Benchmark Report: openrouter:mistralai/mistral-large-2512
Run date: 2026-06-14T00:56:51
Districts tested: 40
Total extraction time: 740s (avg 18.5s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 13.4% |
| JSON parse success | 100.0% |
| Grade coverage rate | 90.7% |
| False positive rate | 14.95/district |
| Mean time/extraction | 18.5s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| LITTLE ROCK SCHOOL DISTRICT | AR | 27 | 30 | 90.0% |  |  |
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| Albany County School District  | WY | 27 | 30 | 90.0% |  |  |
| BERKELEY COUNTY SCHOOLS | WV | 9 | 30 | 30.0% | missing_grade_level |  |
| Tucson Unified District (4403) | AZ | 5 | 20 | 25.0% | false_positive, false_positive |  |
| Sweetwater County School Distr | WY | 5 | 30 | 16.7% | false_positive, false_positive, false_positive (+3 more) |  |
| Lewiston Public Schools | ME | 2 | 30 | 6.7% | false_positive, false_positive, false_positive (+4 more) |  |
| Mesa Unified District (4235) | AZ | 1 | 20 | 5.0% | false_positive |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+64 more) |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+34 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+6 more) |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+54 more) |  |
| SPRINGDALE SCHOOL DISTRICT | AR | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| Los Angeles Unified | CA | 0 | 30 | 0.0% | extraction_error |  |
| New Haven Unified | CA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+60 more) |  |
| New Haven School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+41 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+62 more) |  |
| Appoquinimink School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+25 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Red Clay Consolidated School D | DE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| BROWARD | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+93 more) |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+38 more) |  |
| Cedar Rapids Comm School Distr | IA | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+5 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+47 more) |  |
| Worcester | MA | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+7 more) |  |
| Bangor Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+8 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+47 more) |  |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+96 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+88 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+13 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+95 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Champlain Valley Unified Union | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Burlington School District | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+2 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 35 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:55-15:20 (Alpine Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Avondale Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Ayers Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Basehor Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Belvoir Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Berwick Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Brier Creek Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Buckhorn Creek Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Bugg Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Carpenter Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Cedar Fork Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Combs Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Conn Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Davis Drive Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Davis Drive Year-Round Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Farmington Woods Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Forest Pines Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Fox Road Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Green Hope Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Green Year-Round Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Heritage Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Highcroft Drive Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Hortons Creek Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Lacy Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Lacy Year-Round Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Lake Myra Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Lead Mine Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Lincoln Heights Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Lockhart Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Mills Park Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (North Forest Pines Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (North Ridge Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Northwest Elementary School))
  false_positive: -3 (elementary 08:55-15:20 (Oakview Elementary School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:20'))

Total: 9 (entries) + -168 (penalties) = 0/10 (0.0%)

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
  false_positive: -3 (high 07:50-15:10 (Daphne High))
  false_positive: -3 (middle 07:45-15:03 (Elberta Middle))
  false_positive: -3 (high 08:00-15:15 (Fairhope High))
  false_positive: -3 (middle 07:45-15:05 (Fairhope Middle))
  false_positive: -3 (high 07:59-15:05 (Robertsdale High))
  false_positive: -3 (middle 07:15-15:05 (Daphne Middle))
  false_positive: -3 (high 07:45-14:35 (Baldwin County High))

Total: 3 (entries) + -21 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 9 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 08:15-14:45 | start=0/3 (Δ15m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:15-14:25 (Mary G Montgomery High))
  false_positive: -3 (elementary 08:20-15:05 (Allentown Elementary))
  false_positive: -3 (high 07:15-14:25 (Mattie T. Blount High))
  false_positive: -3 (middle 07:29-14:20 (Causey Middle))
  false_positive: -3 (elementary 08:15-15:15 (Collier Elementary))
  false_positive: -3 (elementary 07:55-15:10 (Dodge Elementary))
  false_positive: -3 (middle 07:20-14:30 (Pillans Middle))
  false_positive: -3 (elementary 08:20-15:15 (Tanner Williams Elementary))
  duplicate_extraction: -2 (Duplicate: ('high', '07:15', '14:25'))

Total: 2 (entries) + -26 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 42 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:15-14:45 → high 07:30-14:45 | start=0/3 (Δ15m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:30-14:45 → middle 07:25-14:35 | start=1/3 (Δ5m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (high 07:10-14:30 (Baldwin Arts and Academic Magnet))
  false_positive: -3 (high 07:45-14:45 (Booker T. Washington (BTW) Magnet High School))
  false_positive: -3 (high 08:30-15:30 (Brew Tech))
  false_positive: -3 (high 07:15-15:15 (Lanier High School))
  false_positive: -3 (high 07:45-14:45 (G.W. Carver High School))
  false_positive: -3 (high 07:45-14:45 (Park Crossing Highschool))
  false_positive: -3 (middle 08:10-15:10 (Brewbaker Middle School))
  false_positive: -3 (middle 07:10-14:30 (LAMP))
  false_positive: -3 (middle 08:40-15:40 (MacMillan International Academy))
  false_positive: -3 (middle 07:30-14:30 (McKee Middle School))
  false_positive: -3 (middle 07:30-15:00 (Southlawn Middle))
  false_positive: -3 (middle 08:30-15:30 (Goodwyn Middle School))
  false_positive: -3 (elementary 07:40-14:45 (Bellingrath))
  false_positive: -3 (elementary 07:45-14:45 (Brewbaker Intermediate School))
  false_positive: -3 (elementary 07:45-14:45 (Brewbaker Primary School))
  false_positive: -3 (elementary 07:30-14:30 (Capitol Heights))
  false_positive: -3 (elementary 08:40-15:40 (Carver Elementary Arts Magnet))
  false_positive: -3 (elementary 08:10-15:10 (Catoma Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Chisholm Elementary))
  false_positive: -3 (elementary 08:05-15:05 (Dalraida))
  false_positive: -3 (elementary 07:30-14:30 (Dannelly Elementary))
  false_positive: -3 (elementary 07:30-15:00 (Davis Elementary School))
  false_positive: -3 (elementary 07:30-14:30 (Dozier Elementary))
  false_positive: -3 (elementary 08:00-15:00 (E.D.Nixon Elementary))
  false_positive: -3 (elementary 07:20-14:45 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 08:00-15:00 (Flowers Elementary School))
  false_positive: -3 (elementary 08:30-15:30 (Forest Avenue Academic Magnet))
  false_positive: -3 (elementary 07:20-14:45 (Halcyon Elementary School))
  false_positive: -3 (elementary 07:30-14:45 (Highland Avenue Elementary))
  false_positive: -3 (elementary 08:10-15:10 (Highland Gardens ES))
  false_positive: -3 (elementary 07:30-14:45 (Morningview Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Morris Elementary))
  false_positive: -3 (elementary 07:30-15:00 (Peter Crump Elem.))
  false_positive: -3 (elementary 08:00-15:00 (Pintlala Elementary School))
  false_positive: -3 (elementary 08:10-15:10 (Seth Johnson Elementary School))
  false_positive: -3 (elementary 07:30-14:45 (Southlawn Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Vaughn Road Elementary))
  false_positive: -3 (elementary 08:10-15:25 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 08:10-15:10 (William Silas Garrett Elementary))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:20', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))

Total: 17 (entries) + -153 (penalties) = 0/30 (0.0%)

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
  false_positive: -3 (middle 08:05-15:30 (Helen Tyson Middle School))
  false_positive: -3 (middle 08:05-15:28 (Sonora Middle School))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:05', '15:30'))
  missing_grade_level: -2 (Missing: high)

Total: 11 (entries) + -13 (penalties) = 0/30 (0.0%)

======================================================================
Mesa Unified District (4235) (AZ) - 0404970
======================================================================
Ground truth: 2 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 07:50-13:50 → elementary 08:15-14:45 | start=0/3 (Δ25m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 08:00-14:45 → middle 07:30-14:15 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:15-15:15 (Red Mountain High))

Total: 4 (entries) + -3 (penalties) = 1/20 (5.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 4 | Matched: 2

Entry Scores:
  middle 08:50-15:50 → middle 08:50-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:30-15:15 → high 08:05-15:21 | start=0/3 (Δ25m) end=0/3 (Δ6m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:20-14:45 (Borton Elementary Magnet School))
  false_positive: -3 (high 08:00-15:01 (Pueblo High School))

Total: 11 (entries) + -6 (penalties) = 5/20 (25.0%)

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
  false_positive: -3 (middle 08:15-14:44 (César Chávez Middle))
  false_positive: -3 (high 09:00-13:54 (Conley-Caraballo High))
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
Ground truth: 3 entries | Extracted: 35 | Matched: 3

Entry Scores:
  elementary 08:45-15:00 → elementary 08:30-15:00 | start=0/3 (Δ15m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-14:20 → middle 07:45-14:10 | start=1/3 (Δ5m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 07:20-13:50 → high 07:30-14:00 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 07:30-14:15 (Cooperative Arts and Humanities Magnet High School))
  false_positive: -3 (high 07:30-14:15 (Metro Business Academy))
  false_positive: -3 (high 07:10-14:05 (New Haven Academy))
  false_positive: -3 (high 13:00-16:00 (Platt Tech))
  false_positive: -3 (high 07:30-14:17 (Sound School))
  false_positive: -3 (high 10:00-14:15 (Riverside))
  false_positive: -3 (high 07:10-14:05 (HSC High School))
  false_positive: -3 (high 07:45-15:30 (Edmonds Cofield Prep))
  false_positive: -3 (elementary 09:15-15:30 (John Martinez))
  false_positive: -3 (elementary 09:15-15:30 (Jepson))
  false_positive: -3 (elementary 07:45-14:15 (John Daniels))
  false_positive: -3 (elementary 07:55-14:10 (King-Robinson))
  false_positive: -3 (elementary 08:35-14:50 (Lincoln Bassett))
  false_positive: -3 (elementary 08:35-14:50 (Nathan Hale))
  false_positive: -3 (elementary 09:15-15:30 (Roberto Clemente))
  false_positive: -3 (elementary 09:15-15:30 (Ross-Woodward))
  false_positive: -3 (elementary 07:30-14:00 (Mauro-Sheridan))
  false_positive: -3 (elementary 08:35-14:50 (Wexler (WG)))
  false_positive: -3 (elementary 07:55-14:10 (Troup))
  false_positive: -3 (elementary 08:35-14:50 (Truman))
  false_positive: -3 (elementary 09:00-15:15 ((Unnamed Elementary)))
  false_positive: -3 (elementary 08:35-14:50 ((Unnamed Elementary)))
  false_positive: -3 (elementary 07:45-15:10 (B. T. Washington Elementary))
  false_positive: -3 (elementary 08:10-15:00 (Foote))
  false_positive: -3 (elementary 07:40-15:30 (Hopkins))
  false_positive: -3 (elementary 07:45-14:15 (All Saints Catholic))
  false_positive: -3 (elementary 07:30-17:15 (St. Martin))
  false_positive: -3 (elementary 08:15-15:00 (St. Thomas))
  false_positive: -3 (elementary 08:35-14:50 (Elm City Elementary))
  false_positive: -3 (middle 08:35-14:50 (Elm City Middle))
  false_positive: -3 (elementary 09:00-15:45 (Highville Charter K-8))
  false_positive: -3 (high 07:30-14:05 (Highville Charter High School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:10', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:55', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '14:50'))

Total: 10 (entries) + -120 (penalties) = 0/30 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 39 | Matched: 3

Entry Scores:
  elementary 08:35-14:50 → elementary 08:35-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-13:50 → high 07:20-13:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:50-14:20 → middle 07:50-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 07:20-13:50 (Kennedy))
  false_positive: -3 (high 07:20-13:50 (Wtby Arts Magnet))
  false_positive: -3 (high 07:20-13:50 (Wtby Career Academy))
  false_positive: -3 (high 07:20-13:50 (Wilby))
  false_positive: -3 (high 07:30-13:45 (Holy Cross High School))
  false_positive: -3 (high 07:25-14:20 (Kaynor Technical))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Bais Yaakov))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Gedolah))
  false_positive: -3 (middle 07:50-14:20 (Wallace))
  false_positive: -3 (middle 07:20-13:50 (Wtby Arts Magnet))
  false_positive: -3 (middle 07:50-14:20 (West Side))
  false_positive: -3 (middle 07:50-14:20 (Academic Academy (at Wallace)))
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
  false_positive: -3 (elementary 09:00-16:00 (Yeshiva K'Tana))
  false_positive: -3 (elementary 09:05-15:20 (Catholic Academy of Waterbury))
  false_positive: -3 (elementary 09:05-15:20 (Children's Community))
  false_positive: -3 (elementary 09:05-15:20 (Our Lady of Mount Carmel))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:20', '13:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '16:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:05', '15:20'))

Total: 27 (entries) + -166 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 16 | Matched: 1

Entry Scores:
  high 07:30-14:30 → high 08:20-15:00 | start=0/3 (Δ50m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:20-15:00 (Middletown HS))
  false_positive: -3 (high 08:20-15:00 (Odessa HS))
  false_positive: -3 (middle 07:30-14:10 (Everett Meredith MS))
  false_positive: -3 (middle 07:30-14:10 (Louis L. Redding MS))
  false_positive: -3 (middle 07:30-14:10 (Alfred G. Waters MS))
  false_positive: -3 (middle 07:30-14:10 (Cantwell’s Bridge MS))
  false_positive: -3 (elementary 09:10-15:50 (Brick Mill ES))
  false_positive: -3 (elementary 09:10-15:50 (Bunker Hill ES))
  false_positive: -3 (elementary 09:10-15:50 (Cedar Lane ES))
  false_positive: -3 (elementary 09:10-15:50 (Lorewood Grove ES))
  false_positive: -3 (elementary 09:10-15:50 (Crystal Run ES))
  false_positive: -3 (elementary 09:10-15:50 (Old State ES))
  false_positive: -3 (elementary 09:10-15:50 (Olive B. Loss ES))
  false_positive: -3 (elementary 09:10-15:50 (Silver Lake ES))
  false_positive: -3 (elementary 09:10-15:50 (Townsend ES))
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

Total: 2 (entries) + -71 (penalties) = 0/10 (0.0%)

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
  false_positive: -3 (high 07:25-14:10 (McKean High))
  false_positive: -3 (high 07:25-14:10 (Alexis I du Pont High))
  false_positive: -3 (high 07:25-14:10 (John Dickinson High))
  duplicate_extraction: -2 (Duplicate: ('high', '07:25', '14:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:25', '14:10'))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -15 (penalties) = 0/10 (0.0%)

======================================================================
BROWARD (FL) - 1200180
======================================================================
Ground truth: 3 entries | Extracted: 53 | Matched: 1

Entry Scores:
  elementary 08:00-14:00 → elementary 08:00-14:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: high 07:40-14:40 (unnamed) → 0/10
  MISSED: middle 09:30-16:10 (unnamed) → 0/10

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
  false_positive: -3 (elementary 08:00-14:00 (Foster, Stephen Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Fox Trail Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Gator Run Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Griffin Elementary))
  false_positive: -3 (elementary 08:00-14:40 (Gulfstream Academy of Hallandale Beach))
  false_positive: -3 (elementary 08:00-14:00 (Hawkes Bluff Elementary))
  false_positive: -3 (elementary 08:00-14:00 (Heron Heights Elementary))
  false_positive: -3 (elementary 08:00-14:40 (Hollywood Central Preparatory K-8))
  false_positive: -3 (elementary 08:00-14:00 (Hollywood Hills Elementary))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:40'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '14:00'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 9 (entries) + -244 (penalties) = 0/30 (0.0%)

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
Cedar Rapids Comm School District (IA) - 1906540
======================================================================
Ground truth: 2 entries | Extracted: 7 | Matched: 2

Entry Scores:
  elementary 08:50-14:20 → elementary 08:50-15:50 | start=3/3 (Δ0m) end=0/3 (Δ90m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:50-13:55 → middle 07:50-14:50 | start=3/3 (Δ0m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:50-14:50 (Cedar Rapids Community School District))
  false_positive: -3 (middle 07:50-14:50 (Franklin Middle School))
  false_positive: -3 (high 07:50-14:50 (Washington High School))
  false_positive: -3 (elementary 08:50-15:50 (Wright Elementary School))
  false_positive: -3 (high 08:20-15:00 (Metro High School))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:50', '14:50'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:50'))

Total: 10 (entries) + -21 (penalties) = 0/20 (0.0%)

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
  false_positive: -3 (high 08:40-15:54 (Hillcrest High))
  false_positive: -3 (high 08:00-14:45 (Lincoln High))
  false_positive: -3 (high 08:40-15:48 (Thunder Ridge High))
  false_positive: -3 (middle 08:40-15:45 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))
  duplicate_extraction: -2 (Duplicate: ('high', '08:40', '15:48'))

Total: 9 (entries) + -17 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 29 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:45-13:45 (Drewicz))
  false_positive: -3 (elementary 07:45-13:45 (Fallon))
  false_positive: -3 (elementary 07:45-13:45 (Ford))
  false_positive: -3 (elementary 07:45-13:45 (Harrington))
  false_positive: -3 (elementary 07:45-13:45 (Ingalls))
  false_positive: -3 (elementary 07:45-13:45 (Sisson))
  false_positive: -3 (elementary 07:45-13:45 (Virginia Barton Center at Briarcliff (Elementary Teams)))
  false_positive: -3 (elementary 07:45-13:45 (Washington))
  false_positive: -3 (elementary 08:15-14:15 (Aborn))
  false_positive: -3 (elementary 08:15-14:15 (Brickett))
  false_positive: -3 (elementary 08:15-14:15 (Cobbet))
  false_positive: -3 (elementary 08:15-14:15 (Connery))
  false_positive: -3 (elementary 08:15-14:15 (Hood))
  false_positive: -3 (elementary 08:15-14:15 (Lincoln-Thomson))
  false_positive: -3 (elementary 08:15-14:15 (Lynn Woods))
  false_positive: -3 (elementary 08:15-14:15 (Sewell Anderson))
  false_positive: -3 (elementary 08:15-14:15 (Shoemaker))
  false_positive: -3 (elementary 08:15-14:15 (Tracy))
  false_positive: -3 (high 07:45-14:30 (Discovery Academy))
  false_positive: -3 (high 07:45-14:30 (Frederick Douglass Collegiate Academy))
  false_positive: -3 (high 07:45-14:30 (Lynn Classical High School))
  false_positive: -3 (high 07:45-14:30 (Lynn English High School))
  false_positive: -3 (high 07:45-14:30 (Lynn Vocational Technical Institute))
  false_positive: -3 (middle 07:45-14:30 (Pickering Middle School))
  false_positive: -3 (middle 07:45-14:30 (Virginia Barton Center at Briarcliff (Secondary Teams)))
  false_positive: -3 (middle 07:45-14:30 (Thurgood Marshall Middle School))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))

Total: 20 (entries) + -126 (penalties) = 0/30 (0.0%)

======================================================================
Worcester (MA) - 2513230
======================================================================
Ground truth: 1 entries | Extracted: 8 | Matched: 1

Entry Scores:
  middle 08:47-14:17 → middle 08:47-15:07 | start=3/3 (Δ0m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (high 07:20-13:43 (Burncoat High))
  false_positive: -3 (high 07:20-13:43 (North High))
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
Ground truth: 3 entries | Extracted: 9 | Matched: 3

Entry Scores:
  elementary 08:55-15:00 → elementary 08:55-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:15-14:30 → middle 08:15-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:00-14:00 → high 08:00-14:35 | start=3/3 (Δ0m) end=0/3 (Δ35m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:55-15:00 (Downeast School))
  false_positive: -3 (elementary 08:55-15:00 (Fourteenth Street School))
  false_positive: -3 (elementary 08:55-15:00 (Fruit Street School))
  false_positive: -3 (elementary 08:55-15:00 (Fairmount School))
  false_positive: -3 (elementary 08:50-15:00 (Mary Snow School))
  false_positive: -3 (middle 08:15-14:30 (William S. Cohen School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:55', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:15', '14:30'))

Total: 23 (entries) + -28 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 55 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:00-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 08:00-15:00 (Culler Middle School))
  false_positive: -3 (high 08:00-15:05 (Lincoln High School))
  false_positive: -3 (high 08:00-15:00 (Northwest High School))
  false_positive: -3 (middle 08:00-15:00 (Pound Middle School))
  false_positive: -3 (high 08:00-15:01 (Standing Bear High School))
  false_positive: -3 (middle 08:00-15:00 (Lux Middle School))
  false_positive: -3 (high 08:00-15:05 (Lincoln High))
  false_positive: -3 (high 08:00-15:00 (East High))
  false_positive: -3 (high 08:00-15:00 (North Star High))
  false_positive: -3 (high 08:00-14:55 (Northeast High))
  false_positive: -3 (high 08:00-15:00 (Northwest High))
  false_positive: -3 (high 08:00-15:00 (Southeast High))
  false_positive: -3 (high 08:15-15:03 (Southwest High))
  false_positive: -3 (high 08:00-15:00 (Standing Bear High))
  false_positive: -3 (high 08:10-15:00 (Bryan Community (9th & 10th Grade)))
  false_positive: -3 (high 09:00-15:00 (Bryan Community (11th & 12th Grade)))
  false_positive: -3 (elementary 08:15-14:53 (Adams))
  false_positive: -3 (elementary 09:00-15:38 (Arnold))
  false_positive: -3 (elementary 08:15-14:53 (Beattie))
  false_positive: -3 (elementary 08:15-14:53 (Belmont))
  false_positive: -3 (elementary 09:00-15:38 (Brownell))
  false_positive: -3 (elementary 08:15-14:53 (Calvert))
  false_positive: -3 (elementary 09:00-15:38 (Campbell))
  false_positive: -3 (elementary 08:15-14:53 (Cavett))
  false_positive: -3 (elementary 08:15-14:53 (Clinton))
  false_positive: -3 (elementary 09:00-15:38 (Eastridge))
  false_positive: -3 (elementary 08:15-14:53 (Elliott))
  false_positive: -3 (elementary 08:15-14:53 (Everett))
  false_positive: -3 (elementary 08:15-14:53 (Fredstrom))
  false_positive: -3 (elementary 09:00-15:38 (Hartley))
  false_positive: -3 (elementary 08:15-14:53 (Hill))
  false_positive: -3 (elementary 08:15-14:53 (Holmes))
  false_positive: -3 (elementary 09:00-15:38 (Humann))
  false_positive: -3 (elementary 08:15-14:53 (Huntington))
  false_positive: -3 (elementary 09:00-15:38 (Kahoa))
  false_positive: -3 (elementary 08:15-14:53 (Kloefkorn))
  false_positive: -3 (elementary 08:15-14:53 (Kooser))
  false_positive: -3 (elementary 09:00-15:38 (Lakeview))
  false_positive: -3 (elementary 09:00-15:38 (Maxey))
  false_positive: -3 (elementary 09:00-15:38 (McPhee))
  false_positive: -3 (elementary 09:00-15:38 (Meadow Lane))
  false_positive: -3 (elementary 09:00-15:38 (Morley))
  false_positive: -3 (elementary 09:00-15:38 (Norwood Park))
  false_positive: -3 (elementary 08:15-14:53 (Pershing))
  false_positive: -3 (elementary 09:00-15:38 (Prescott))
  false_positive: -3 (elementary 09:00-15:38 (Pyrtle))
  false_positive: -3 (elementary 09:00-15:38 (Randolph))
  false_positive: -3 (elementary 09:00-15:38 (Riley))
  false_positive: -3 (elementary 08:15-14:53 (Robinson))
  false_positive: -3 (elementary 08:15-14:53 (Roper))
  false_positive: -3 (elementary 09:00-15:38 (Rousseau))
  false_positive: -3 (elementary 08:15-14:53 (Saratoga))
  false_positive: -3 (elementary 09:00-15:38 (Sheridan))
  false_positive: -3 (elementary 09:00-15:38 (West Lincoln))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
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

Total: 9 (entries) + -252 (penalties) = 0/10 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 56 | Matched: 1

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
  false_positive: -3 (middle 07:30-14:00 (Cold Springs 6-8))
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
  false_positive: -3 (middle 08:00-14:30 (Mt. Rose (6-8)))
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

Total: 2 (entries) + -237 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 53 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:35-15:05 → middle 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

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
  false_positive: -3 (elementary 07:35-14:05 (Stephanie Tubbs Jones School))
  false_positive: -3 (elementary 09:35-16:05 (Bolton))
  false_positive: -3 (elementary 09:35-16:05 (Stonebrook-White))
  false_positive: -3 (elementary 09:35-16:05 (Louisa May Alcott))
  false_positive: -3 (elementary 07:35-14:05 (Luis Munoz Marin))
  false_positive: -3 (elementary 08:35-15:05 (Sunbeam))
  false_positive: -3 (elementary 07:35-14:05 (Ginn (Elementary)))
  false_positive: -3 (elementary 09:35-16:05 (Marion C. Seltzer))
  false_positive: -3 (elementary 09:35-16:05 (Tremont Montessori))
  false_positive: -3 (elementary 09:35-16:05 (Charles Dickens))
  false_positive: -3 (elementary 08:35-15:05 (Marion-Sterling))
  false_positive: -3 (elementary 07:35-14:05 (Clara E. Westropp))
  false_positive: -3 (elementary 07:35-14:05 (Mary B. Martin))
  false_positive: -3 (elementary 09:35-16:05 (Mary Church Terrell))
  false_positive: -3 (elementary 07:35-14:05 (Mary M. Bethune))
  false_positive: -3 (elementary 08:35-15:05 (Wade Park))
  false_positive: -3 (elementary 07:35-14:05 (Daniel E. Morgan))
  false_positive: -3 (elementary 08:35-15:05 (Denison))
  false_positive: -3 (elementary 09:35-16:05 (Dike School of the Arts))
  false_positive: -3 (elementary 08:35-15:05 (Mound))
  false_positive: -3 (elementary 09:35-16:05 (William C. Bryant))
  false_positive: -3 (elementary 08:35-15:05 (Nathan Hale))
  false_positive: -3 (elementary 08:35-15:05 (Natividad Pagan International (K-8)))
  false_positive: -3 (elementary 07:35-14:05 (William Rainey Harper))
  false_positive: -3 (elementary 07:35-14:05 (East Clark))
  false_positive: -3 (elementary 07:35-14:05 (Euclid Park))
  false_positive: -3 (middle 09:35-16:05 (Adlai E. Stevenson))
  false_positive: -3 (middle 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (middle 08:35-15:05 (Albert B. Hart))
  false_positive: -3 (middle 08:35-15:05 (Garfield))
  false_positive: -3 (middle 09:35-16:05 (Orchard))
  false_positive: -3 (middle 07:35-14:05 (Alfred A. Benesch))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:35', '14:05'))
  missing_grade_level: -2 (Missing: high)

Total: 25 (entries) + -246 (penalties) = 0/30 (0.0%)

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
Ground truth: 1 entries | Extracted: 7 | Matched: 1

Entry Scores:
  elementary 07:50-13:45 → elementary 07:50-14:35 | start=3/3 (Δ0m) end=0/3 (Δ50m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (middle 07:45-14:40 (Charlotte Central School))
  false_positive: -3 (elementary 07:45-14:43 (Charlotte Central School))
  false_positive: -3 (elementary 07:45-14:45 (Shelburne Community School))
  false_positive: -3 (middle 07:45-14:45 (Shelburne Community School))
  false_positive: -3 (elementary 07:55-14:45 (Williston Central School))
  false_positive: -3 (middle 07:55-14:45 (Williston Central School))

Total: 5 (entries) + -18 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 5 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:08-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

Penalties:
  false_positive: -3 (elementary 08:10-14:50 (Edmunds Elementary))
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle School))
  false_positive: -3 (middle 08:00-15:00 (Hunt Middle School))
  false_positive: -3 (high 08:10-14:35 (Burlington High School))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))

Total: 8 (entries) + -14 (penalties) = 0/10 (0.0%)

======================================================================
BERKELEY COUNTY SCHOOLS (WV) - 5400060
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  high 07:28-14:38 → high 07:28-14:38 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:55-15:30 → elementary 08:45-15:20 | start=0/3 (Δ50m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 07:30-14:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)

Total: 11 (entries) + -2 (penalties) = 9/30 (30.0%)

======================================================================
CABELL COUNTY SCHOOLS (WV) - 5400180
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  middle 07:27-15:06 → middle 07:48-15:00 | start=0/3 (Δ21m) end=0/3 (Δ6m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (high 08:42-15:17 (Huntington High))
  false_positive: -3 (middle 07:49-14:55 (Huntington Middle))
  false_positive: -3 (high 08:15-14:35 (Cabell Midland High))

Total: 2 (entries) + -9 (penalties) = 0/10 (0.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:15-14:15 → elementary 07:45-14:12 | start=0/3 (Δ30m) end=1/3 (Δ3m) grade=2/2 name=0/1 conf=0/1 = 3/10

Penalties:
  false_positive: -3 (middle 07:30-14:38 (Horace Mann Middle))
  false_positive: -3 (middle 08:15-15:10 (Elkview Middle))
  false_positive: -3 (high 08:36-15:36 (Nitro High))

Total: 3 (entries) + -9 (penalties) = 0/10 (0.0%)

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
Ground truth: 3 entries | Extracted: 9 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-15:15 (Elementary Schools (4-6)))
  false_positive: -3 (elementary 08:00-15:55 (Wamsutter K-8))
  false_positive: -3 (middle 08:00-15:55 (Wamsutter K-8))
  false_positive: -3 (elementary 07:45-15:00 (Elementary School))
  false_positive: -3 (middle 07:45-16:05 (Middle School))
  false_positive: -3 (high 07:45-16:05 (High School))

Total: 23 (entries) + -18 (penalties) = 5/30 (16.7%)