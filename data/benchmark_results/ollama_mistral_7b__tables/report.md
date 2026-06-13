# Benchmark Report: ollama:mistral:7b
Run date: 2026-06-12T22:57:43
Districts tested: 17
Total extraction time: 2051s (avg 120.6s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 7.2% |
| JSON parse success | 88.2% |
| Grade coverage rate | 84.0% |
| False positive rate | 7.35/district |
| Mean time/extraction | 120.6s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 14 | 30 | 46.7% | missing_grade_level |  |
| Sweetwater County School Distr | WY | 9 | 30 | 30.0% |  |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | extraction_error |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+9 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | extraction_error |  |
| Mobile County | AL | 0 | 10 | 0.0% | extraction_error |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+74 more) |  |
| Tucson Unified District (4403) | AZ | 0 | 20 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Christina School District | DE | 0 | 10 | 0.0% | extraction_error |  |
| ORANGE | FL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+34 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+4 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+73 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | extraction_error |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | extraction_error |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | json_parse_failure | JSON failure |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 9 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:45 | start=3/3 (Δ0m) end=0/3 (Δ35m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-14:30 (ARCTIC LIGHT ELEMENTARY))
  false_positive: -3 (elementary 09:00-15:45 (DENALI ELEMENTARY))
  false_positive: -3 (elementary 09:00-15:30 (NORTH POLE ELEMENTARY))
  false_positive: -3 (elementary 09:00-15:45 (SALCHA ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (UNIVERSITY PARK ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (WATERSHED CHARTER))
  false_positive: -3 (elementary 09:15-15:45 (WELLER ELEMENTARY))
  false_positive: -3 (elementary 09:15-15:45 (WOODRIVER ELEMENTARY))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '15:45'))

Total: 5 (entries) + -32 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 48 | Matched: 3

Entry Scores:
  middle 07:30-14:45 → middle 07:30-14:30 | start=3/3 (Δ0m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:10-15:10 → elementary 08:10-14:30 | start=3/3 (Δ0m) end=0/3 (Δ40m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:15-14:45 → high 08:10-14:35 | start=0/3 (Δ55m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:30-14:30 (Baldwin Arts and Academic Magnet))
  false_positive: -3 (elementary 07:45-14:30 (Bellingrath))
  false_positive: -3 (elementary 07:45-14:30 (Booker T. Washington (BTW) Magnet High School))
  false_positive: -3 (elementary 08:30-14:30 (Brew Tech))
  false_positive: -3 (middle 07:45-14:30 (Brewbaker Intermediate School))
  false_positive: -3 (middle 08:10-14:30 (Brewbaker Middle School))
  false_positive: -3 (primary 07:30-14:30 (Brewbaker Primary School))
  false_positive: -3 (elementary 08:10-14:30 (Capitol Heights))
  false_positive: -3 (elementary 07:45-14:30 (Carver Elementary Arts Magnet))
  false_positive: -3 (elementary 08:10-14:30 (Catoma Elementary School))
  false_positive: -3 (elementary 07:30-14:30 (Chisholm Elementary))
  false_positive: -3 (elementary 08:10-14:30 (Dalraida))
  false_positive: -3 (elementary 08:40-14:30 (Dannelly Elementary))
  false_positive: -3 (elementary 08:10-14:30 (Dozier Elementary))
  false_positive: -3 (elementary 07:45-14:30 (Dunbar Ramer))
  false_positive: -3 (elementary 08:30-14:30 (E.D.Nixon Elementary))
  false_positive: -3 (elementary 07:30-14:30 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 08:10-14:30 (Flowers Elementary School))
  false_positive: -3 (middle 08:10-14:30 (Floyd Middle School))
  false_positive: -3 (elementary 07:30-14:30 (Forest Avenue Academic Magnet))
  false_positive: -3 (high 08:10-14:30 (G.W. Carver High School))
  false_positive: -3 (elementary 08:10-14:30 (Halcyon Elementary School))
  false_positive: -3 (elementary 07:30-14:30 (Highland Avenue Elementary))
  false_positive: -3 (elementary 08:10-14:30 (Highland Gardens ES))
  false_positive: -3 (middle 07:30-14:30 (Johnnie R. Carr Middle School))
  false_positive: -3 (elementary 08:10-14:30 (LAMP))
  false_positive: -3 (high 08:10-14:35 (Lanier High School))
  false_positive: -3 (elementary 07:55-14:30 (MacMillan International Academy))
  false_positive: -3 (middle 08:10-14:30 (McKee Middle School))
  false_positive: -3 (pre-k 07:50-14:30 (McKee Pre-K Center))
  false_positive: -3 (elementary 08:10-14:30 (MLK))
  false_positive: -3 (elementary 07:30-14:30 (Morningview Elementary School))
  false_positive: -3 (elementary 08:10-14:30 (Morris Elementary))
  false_positive: -3 (elementary 07:55-14:30 (MPACT))
  false_positive: -3 (high 08:00-14:30 (Park Crossing Highschool))
  false_positive: -3 (elementary 07:25-14:30 (Percy Julian))
  false_positive: -3 (elementary 08:10-14:30 (Peter Crump Elem.))
  false_positive: -3 (elementary 07:50-14:30 (Pintlala Elementary School))
  false_positive: -3 (elementary 08:10-14:30 (Seth Johnson Elementary School))
  false_positive: -3 (elementary 07:30-14:30 (Southlawn Elementary School))
  false_positive: -3 (middle 08:10-14:30 (Southlawn Middle))
  false_positive: -3 (elementary 07:30-14:30 (Vaughn Road Elementary))
  false_positive: -3 (elementary 08:10-14:30 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 07:30-14:30 (William Silas Garrett Elementary))
  false_positive: -3 (elementary 08:10-14:30 (Wilson))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:10', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:55', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '14:30'))

Total: 12 (entries) + -199 (penalties) = 0/30 (0.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 4 | Matched: 0

Entry Scores:
  MISSED: high 08:30-15:15 (unnamed) → 0/10
  MISSED: middle 08:50-15:50 (unnamed) → 0/10

Penalties:
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 07:05-07:58 (None))
  false_positive: -3 (unknown 07:35-08:12 (None))
  false_positive: -3 (unknown 07:25-08:10 (None))
  duplicate_extraction: -2 (Duplicate: ('unknown', '07:05', '07:58'))
  missing_grade_level: -2 (Missing: high)
  missing_grade_level: -2 (Missing: middle)

Total: 0 (entries) + -18 (penalties) = 0/20 (0.0%)

======================================================================
KIPP DC PCS (DC) - 1100031
======================================================================
Ground truth: 3 entries | Extracted: 2 | Matched: 2

Entry Scores:
  elementary 08:00-15:30 → elementary 08:00-15:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 08:15-15:15 → high 08:15-15:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  MISSED: middle 08:00-15:30 (unnamed) → 0/10

Penalties:
  missing_grade_level: -2 (Missing: middle)

Total: 16 (entries) + -2 (penalties) = 14/30 (46.7%)

======================================================================
Christina School District (DE) - 1000200
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (No valid schedules extracted)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
ORANGE (FL) - 1201440
======================================================================
Ground truth: 3 entries | Extracted: 22 | Matched: 3

Entry Scores:
  high 07:20-14:20 → high 08:10-14:30 | start=0/3 (Δ50m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  elementary 08:45-15:00 → elementary 08:15-15:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10
  middle 09:30-16:04 → middle 08:45-15:00 | start=0/3 (Δ45m) end=0/3 (Δ64m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Catalina))
  false_positive: -3 (elementary 08:15-15:30 (Mollie Ray))
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
  false_positive: -3 (middle 08:45-15:00 (OCPS Academic Center for Excellence K-8 Orange Center))
  false_positive: -3 (high 08:45-16:00 (Deerwood))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '08:45', '15:00'))

Total: 6 (entries) + -93 (penalties) = 0/30 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 7 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:30-14:15 → middle 07:30-14:30 | start=3/3 (Δ0m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:15-14:15 (ABORN))
  false_positive: -3 (high 07:45-14:30 (LYNN CLASSICAL HIGH SCHOOL))
  false_positive: -3 (high 07:45-14:30 (LYNN ENGLISH HIGH SCHOOL))
  false_positive: -3 (high 07:45-14:30 (LYNN VOCATIONAL TECHNICAL INSTITUTE))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:30'))

Total: 15 (entries) + -18 (penalties) = 0/30 (0.0%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 7 | Matched: 3

Entry Scores:
  middle 07:35-14:00 → middle 07:15-14:00 | start=0/3 (Δ20m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  elementary 08:20-14:50 → elementary 08:25-15:10 | start=1/3 (Δ5m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 07:45-14:00 → high 07:15-14:30 | start=0/3 (Δ30m) end=0/3 (Δ30m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 07:45-15:00 (Connors))
  false_positive: -3 (elementary 08:25-15:10 (McMahon))
  false_positive: -3 (elementary 07:45-15:00 (Montello))
  false_positive: -3 (elementary 08:25-15:10 (Geiger))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:25', '15:10'))

Total: 10 (entries) + -18 (penalties) = 0/30 (0.0%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 44 | Matched: 3

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 08:35-15:05 → middle 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=0/1 = 6/10

Penalties:
  false_positive: -3 (elementary 07:35-14:05 (Adlai E. Stevenson))
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (elementary 09:35-14:05 (Garfield))
  false_positive: -3 (elementary 08:35-15:05 (Orchard))
  false_positive: -3 (elementary 07:35-14:05 (Alfred A. Benesch))
  false_positive: -3 (elementary 09:35-14:05 (George W. Carver))
  false_positive: -3 (elementary 09:35-14:05 (Paul L. Dunbar))
  false_positive: -3 (elementary 08:35-15:05 (Almira))
  false_positive: -3 (elementary 09:35-14:05 (Halle))
  false_positive: -3 (elementary 09:35-14:05 (Riverside))
  false_positive: -3 (elementary 07:35-14:05 (Andrew J. Rickoff))
  false_positive: -3 (elementary 09:35-14:05 (Hannah Gibbons))
  false_positive: -3 (elementary 09:35-14:05 (Robert H. Jamison))
  false_positive: -3 (elementary 07:35-14:05 (Anton Grdina))
  false_positive: -3 (elementary 07:35-14:05 (Harvey Rice))
  false_positive: -3 (elementary 08:35-15:05 (Robinson G. Jones))
  false_positive: -3 (elementary 09:35-14:05 (Artemus Ward))
  false_positive: -3 (elementary 08:35-15:05 (Joseph M. Gallagher))
  false_positive: -3 (elementary 07:35-14:05 (Scranton))
  false_positive: -3 (elementary 09:35-14:05 (Leadership Academy Stonebrook-White))
  false_positive: -3 (elementary 09:35-16:05 (Campus International KB))
  false_positive: -3 (elementary 08:40-15:10 (Luis Mufioz Marin))
  false_positive: -3 (elementary 07:35-14:05 (Sunbeam))
  false_positive: -3 (elementary 08:35-15:05 (Marion C. Seltzer))
  false_positive: -3 (elementary 09:35-16:05 (Tremont Montessori))
  false_positive: -3 (elementary 09:35-16:05 (Charles Dickens))
  false_positive: -3 (elementary 08:35-15:05 (Marion-Sterling))
  false_positive: -3 (elementary 09:35-16:05 (Valley View Boys’))
  false_positive: -3 (elementary 07:35-14:05 (Clara E. Westropp))
  false_positive: -3 (elementary 07:35-14:05 (Mary B. Martin))
  false_positive: -3 (elementary 08:35-15:05 (Leadership Academy))
  false_positive: -3 (elementary 09:35-16:05 (Clark))
  false_positive: -3 (elementary 07:35-14:05 (Mary Church Terrell))
  false_positive: -3 (elementary 09:35-16:05 (Wade Park))
  false_positive: -3 (elementary 08:00-14:30 (Cleveland Metro Remote School))
  false_positive: -3 (elementary 07:35-14:05 (Mary M. Bethune))
  false_positive: -3 (elementary 08:05-14:35 (Warner Girls))
  false_positive: -3 (middle 09:35-16:05 (Daniel E. Morgan))
  false_positive: -3 (middle 07:35-14:05 (Memorial))
  false_positive: -3 (middle 09:35-16:05 (Carl B. Stokes))
  false_positive: -3 (middle 08:35-15:05 (John Adams))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '14:05'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '16:05'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '15:05'))
  missing_grade_level: -2 (Missing: high)

Total: 22 (entries) + -193 (penalties) = 0/30 (0.0%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (AttributeError: 'list' object has no attribute 'get')

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

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
⚠ JSON PARSE FAILURE

Entry Scores:

Penalties:
  json_parse_failure: -5 (Could not parse JSON response)

Total: 0 (entries) + -5 (penalties) = 0/10 (0.0%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  elementary 07:50-15:15 → elementary 07:45-15:00 | start=1/3 (Δ5m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 3/10
  high 08:00-15:55 → high 07:45-16:05 | start=0/3 (Δ15m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=1/1 = 3/10
  middle 08:30-15:50 → middle 07:45-16:05 | start=0/3 (Δ45m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=1/1 = 3/10

Total: 9 (entries) + 0 (penalties) = 9/30 (30.0%)