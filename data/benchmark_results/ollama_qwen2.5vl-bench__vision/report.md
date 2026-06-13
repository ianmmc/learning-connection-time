# Benchmark Report: ollama:qwen2.5vl-bench
Run date: 2026-06-12T20:53:18
Districts tested: 13
Total extraction time: 18690s (avg 1437.7s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 13.6% |
| JSON parse success | 100.0% |
| Grade coverage rate | 82.6% |
| False positive rate | 14.85/district |
| Mean time/extraction | 1437.7s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Lynn | MA | 13 | 30 | 43.3% | false_positive, missing_grade_level |  |
| Tucson Unified District (4403) | AZ | 7 | 20 | 35.0% |  |  |
| Essex Westford Educational Com | VT | 3 | 10 | 30.0% | false_positive, false_positive |  |
| Lewiston Public Schools | ME | 7 | 30 | 23.3% |  |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | false_positive, false_positive |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+28 more) |  |
| Baldwin County | AL | 0 | 10 | 0.0% | false_positive, false_positive, missing_grade_level |  |
| Mobile County | AL | 0 | 10 | 0.0% | false_positive, false_positive, duplicate_extraction |  |
| Montgomery County | AL | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+72 more) |  |
| Washoe County | NV | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+104 more) |  |
| Cleveland Municipal | OH | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+101 more) |  |
| CABELL COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive, false_positive |  |
| KANAWHA COUNTY SCHOOLS | WV | 0 | 10 | 0.0% | false_positive |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 08:10-14:35 | start=0/3 (Δ25m) end=0/3 (Δ20m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 08:45-12:30 (Big Lake Elementary))
  false_positive: -3 (middle 08:45-12:30 (Colony Middle School))

Total: 2 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 23 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:35 | start=3/3 (Δ0m) end=0/3 (Δ25m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 09:15-16:15 (Anne Wien Elementary))
  false_positive: -3 (elementary 08:00-14:30 (Arctic Light Elementary))
  false_positive: -3 (elementary 08:15-16:45 (Barnette Magnet))
  false_positive: -3 (elementary 08:45-15:15 (Boreal Sun Charter))
  false_positive: -3 (elementary 08:15-16:45 (Chinook Montessori Charter))
  false_positive: -3 (elementary 09:15-17:45 (Denali Elementary))
  false_positive: -3 (elementary 08:00-16:30 (Discovery Peak Charter))
  false_positive: -3 (elementary 09:50-17:45 (Effie Kokrine Charter))
  false_positive: -3 (elementary 08:00-16:30 (Hunter Elementary))
  false_positive: -3 (high 07:30-14:30 (Hutchison High))
  false_positive: -3 (elementary 09:15-16:45 (Ladd Elementary))
  false_positive: -3 (high 07:30-14:30 (Lathrop High))
  false_positive: -3 (elementary 09:00-16:30 (North Pole Elementary))
  false_positive: -3 (high 07:30-14:30 (North Pole High))
  false_positive: -3 (middle 07:50-16:20 (Ryan Middle))
  false_positive: -3 (elementary 09:15-16:45 (Salcha Elementary))
  false_positive: -3 (middle 07:55-16:25 (Tanana Middle))
  false_positive: -3 (elementary 09:00-16:30 (Ticasuk Brown Elementary))
  false_positive: -3 (elementary 09:15-16:45 (University Park Elementary))
  false_positive: -3 (middle 08:30-15:00 (Watershed Charter))
  false_positive: -3 (elementary 09:15-16:45 (Weller Elementary))
  false_positive: -3 (high 07:30-14:30 (West Valley High))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:15', '16:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '16:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '16:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '16:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '16:45'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:30', '14:30'))

Total: 5 (entries) + -84 (penalties) = 0/10 (0.0%)

======================================================================
Baldwin County (AL) - 0100270
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 0

Entry Scores:
  MISSED: elementary 07:15-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (middle 07:15-15:05 (Daphne Middle School))
  false_positive: -3 (high 07:40-23:10 (DHS))
  missing_grade_level: -2 (Missing: elementary)

Total: 0 (entries) + -8 (penalties) = 0/10 (0.0%)

======================================================================
Mobile County (AL) - 0102370
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:00-14:25 → elementary 07:45-16:35 | start=0/3 (Δ15m) end=0/3 (Δ130m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (middle 08:05-16:35 (MGM))
  false_positive: -3 (elementary 07:45-16:35 (Allentown Elementary School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:45', '16:35'))

Total: 3 (entries) + -8 (penalties) = 0/10 (0.0%)

======================================================================
Montgomery County (AL) - 0102430
======================================================================
Ground truth: 3 entries | Extracted: 48 | Matched: 2

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:00 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10
  middle 07:30-14:45 → middle 07:40-14:50 | start=0/3 (Δ10m) end=1/3 (Δ5m) grade=2/2 name=0/1 conf=0/1 = 3/10
  MISSED: high 07:15-14:45 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 07:12-15:30 (Baldwin Arts and Academic Magnet))
  false_positive: -3 (middle 08:10-15:00 (Bear))
  false_positive: -3 (middle 07:45-14:30 (Booker T. Washington (BTW) Magnet High School))
  false_positive: -3 (middle 08:30-15:00 (Brew Tech))
  false_positive: -3 (elementary 08:10-15:00 (Brewbaker Intermediate School))
  false_positive: -3 (middle 07:45-14:30 (Brewbaker Middle School))
  false_positive: -3 (elementary 08:10-15:00 (Brewbaker Primary School))
  false_positive: -3 (middle 07:30-14:30 (Capitol Heights))
  false_positive: -3 (elementary 08:40-15:20 (Carver Elementary Arts Magnet))
  false_positive: -3 (elementary 08:10-15:00 (Catoma Elementary School))
  false_positive: -3 (middle 07:30-14:30 (Children's Center))
  false_positive: -3 (elementary 08:10-15:00 (Chisholm Elementary))
  false_positive: -3 (middle 08:05-14:30 (Dalraida))
  false_positive: -3 (elementary 07:30-14:30 (Dannelly Elementary))
  false_positive: -3 (elementary 07:30-15:00 (Davis Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Dozier Elementary))
  false_positive: -3 (middle 07:20-14:30 (Dunbar Ramer))
  false_positive: -3 (elementary 08:00-15:00 (E.D.Nixon Elementary))
  false_positive: -3 (middle 08:10-14:30 (Fitzpatrick Elementary))
  false_positive: -3 (elementary 07:45-15:20 (Flowers Elementary School))
  false_positive: -3 (middle 08:30-15:00 (Floyd Middle School))
  false_positive: -3 (elementary 08:40-15:20 (Forest Avenue Academic Magnet))
  false_positive: -3 (middle 07:20-14:30 (G.W. Carver High School))
  false_positive: -3 (elementary 07:30-15:00 (Goodwyn Middle School))
  false_positive: -3 (elementary 08:10-15:00 (Halcyon Elementary School))
  false_positive: -3 (middle 07:30-14:30 (Johnnie R. Carr Middle School))
  false_positive: -3 (elementary 07:10-15:00 (LAMP))
  false_positive: -3 (middle 07:15-15:00 (Lanier High School))
  false_positive: -3 (elementary 08:40-15:20 (MacMillan International Academy))
  false_positive: -3 (middle 07:30-14:30 (McKee Middle School))
  false_positive: -3 (elementary 08:00-15:00 (McKee Pre-K Center))
  false_positive: -3 (middle 07:55-14:30 (MLK))
  false_positive: -3 (elementary 08:10-15:00 (Morningview Elementary School))
  false_positive: -3 (elementary 08:10-15:00 (Morris Elementary))
  false_positive: -3 (middle 07:30-14:30 (MPACT))
  false_positive: -3 (middle 07:45-14:30 (Park Crossing Highschool))
  false_positive: -3 (elementary 07:30-15:00 (Percy Julian))
  false_positive: -3 (middle 07:50-14:30 (Peter Crump Elem.))
  false_positive: -3 (elementary 08:00-15:00 (Pintlala Elementary School))
  false_positive: -3 (elementary 08:10-15:00 (Seth Johnson Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Southlawn Elementary School))
  false_positive: -3 (middle 07:30-14:30 (Southlawn Middle))
  false_positive: -3 (elementary 08:10-15:00 (Vaughn Road Elementary))
  false_positive: -3 (elementary 08:00-15:00 (Wares Ferry Rd. Elementary))
  false_positive: -3 (elementary 08:10-15:20 (William Silas Garrett Elementary))
  false_positive: -3 (middle 08:10-15:00 (Wilson))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:40', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:20', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:40', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:45', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:10', '15:00'))
  missing_grade_level: -2 (Missing: high)

Total: 8 (entries) + -196 (penalties) = 0/30 (0.0%)

======================================================================
Tucson Unified District (4403) (AZ) - 0408800
======================================================================
Ground truth: 2 entries | Extracted: 2 | Matched: 2

Entry Scores:
  middle 08:50-15:50 → middle 08:50-14:39 | start=3/3 (Δ0m) end=0/3 (Δ71m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 08:30-15:15 → high 07:35-14:20 | start=0/3 (Δ55m) end=0/3 (Δ55m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 7 (entries) + 0 (penalties) = 7/20 (35.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 08:00-14:00 → elementary 07:45-13:45 | start=0/3 (Δ15m) end=0/3 (Δ15m) grade=2/2 name=0/1 conf=0/1 = 2/10
  high 07:45-14:30 → middle 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=0/2 name=0/1 conf=1/1 = 7/10

Penalties:
  false_positive: -3 (middle 07:45-14:05 (Harold Durgin Success Academy))
  missing_grade_level: -2 (Missing: high)

Total: 18 (entries) + -5 (penalties) = 13/30 (43.3%)

======================================================================
Lewiston Public Schools (ME) - 2307320
======================================================================
Ground truth: 3 entries | Extracted: 3 | Matched: 3

Entry Scores:
  middle 07:35-14:00 → middle 07:45-02:00 | start=0/3 (Δ10m) end=0/3 (Δ720m) grade=2/2 name=0/1 conf=1/1 = 3/10
  high 07:45-14:00 → high 08:10-14:35 | start=0/3 (Δ25m) end=0/3 (Δ35m) grade=2/2 name=0/1 conf=0/1 = 2/10
  elementary 08:20-14:50 → elementary 07:15-12:30 | start=0/3 (Δ65m) end=0/3 (Δ140m) grade=2/2 name=0/1 conf=0/1 = 2/10

Total: 7 (entries) + 0 (penalties) = 7/30 (23.3%)

======================================================================
Washoe County (NV) - 3200480
======================================================================
Ground truth: 1 entries | Extracted: 59 | Matched: 1

Entry Scores:
  elementary 07:26-14:00 → elementary 08:30-15:45 | start=0/3 (Δ64m) end=0/3 (Δ105m) grade=2/2 name=0/1 conf=0/1 = 2/10

Penalties:
  false_positive: -3 (elementary 09:00-16:15 (Anderson))
  false_positive: -3 (elementary 08:30-15:45 (Beasley))
  false_positive: -3 (elementary 09:00-16:15 (Booth))
  false_positive: -3 (elementary 08:30-15:45 (Brown))
  false_positive: -3 (elementary 09:00-16:15 (Cannan))
  false_positive: -3 (elementary 08:30-15:45 (Corbett))
  false_positive: -3 (elementary 09:00-16:15 (Diedrichsen))
  false_positive: -3 (elementary 08:30-15:45 (Donner Springs))
  false_positive: -3 (elementary 09:15-16:15 (Double Diamond))
  false_positive: -3 (elementary 09:00-16:15 (Drake))
  false_positive: -3 (elementary 08:30-15:45 (Duncan-STEM))
  false_positive: -3 (elementary 09:00-16:15 (Dunn))
  false_positive: -3 (elementary 08:30-15:45 (Elmcrest))
  false_positive: -3 (elementary 09:00-16:15 (Gomes))
  false_positive: -3 (elementary 08:30-15:45 (Gomm))
  false_positive: -3 (elementary 09:00-16:15 (Greenbrae))
  false_positive: -3 (elementary 08:30-15:45 (Hall))
  false_positive: -3 (elementary 09:00-16:15 (Hidden Valley))
  false_positive: -3 (elementary 08:30-15:45 (Huffaker))
  false_positive: -3 (elementary 09:00-16:15 (Hunsberger))
  false_positive: -3 (elementary 08:30-15:45 (Hunter Lake))
  false_positive: -3 (elementary 09:20-16:15 (Incline))
  false_positive: -3 (elementary 08:30-15:45 (Inskeep))
  false_positive: -3 (elementary 09:00-16:15 (Juniper))
  false_positive: -3 (elementary 08:30-15:45 (JWood Raw))
  false_positive: -3 (elementary 09:00-16:15 (Lemelson-STEM))
  false_positive: -3 (elementary 08:30-15:45 (Lenz))
  false_positive: -3 (elementary 09:00-16:15 (Lincoln Park))
  false_positive: -3 (elementary 08:30-15:45 (Loder))
  false_positive: -3 (elementary 09:00-16:15 (Mathews))
  false_positive: -3 (elementary 08:30-15:45 (Maxwell))
  false_positive: -3 (elementary 09:00-16:15 (Melton))
  false_positive: -3 (elementary 08:30-15:45 (Mitchell))
  false_positive: -3 (elementary 09:15-16:15 (Moss))
  false_positive: -3 (middle 07:30-14:15 (Billinghamurst))
  false_positive: -3 (middle 07:30-14:15 (Clayton-Pre AP))
  false_positive: -3 (middle 07:30-14:15 (Cold Springs 6-8))
  false_positive: -3 (middle 09:30-15:45 (Cold Springs EC))
  false_positive: -3 (middle 07:30-14:15 (Depoali))
  false_positive: -3 (middle 07:30-14:15 (Desert Skies))
  false_positive: -3 (middle 07:30-14:15 (Dilworth-STEM))
  false_positive: -3 (middle 07:30-14:15 (Herz))
  false_positive: -3 (middle 07:50-14:25 (Incline))
  false_positive: -3 (middle 07:30-14:15 (Mendive))
  false_positive: -3 (middle 07:30-14:15 (O'Brien-STEM))
  false_positive: -3 (middle 09:30-15:45 (Picollo (PK-12)))
  false_positive: -3 (middle 07:30-14:15 (Pine))
  false_positive: -3 (middle 07:30-14:15 (Shaw))
  false_positive: -3 (middle 07:30-14:15 (Sky Ranch))
  false_positive: -3 (middle 07:30-14:15 (Sparks))
  false_positive: -3 (middle 07:30-14:15 (Swope))
  false_positive: -3 (middle 07:30-14:15 (Traner))
  false_positive: -3 (middle 07:25-14:15 (Vaughn))
  false_positive: -3 (high 07:26-14:35 (Academy of Arts, Careers & Technology))
  false_positive: -3 (high 08:00-14:35 (Damonte Ranch))
  false_positive: -3 (high 07:26-14:35 (Debbie Smith CTE))
  false_positive: -3 (high 08:00-14:35 (Galena))
  false_positive: -3 (high 08:00-14:35 (Gerlach K-12))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:00', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:15', '16:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:30', '15:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:30', '14:15'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:26', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:35'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '14:35'))

Total: 2 (entries) + -272 (penalties) = 0/10 (0.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 57 | Matched: 2

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-12:30 | start=3/3 (Δ0m) end=0/3 (Δ155m) grade=2/2 name=0/1 conf=1/1 = 6/10
  middle 08:35-15:05 → middle 08:35-12:45 | start=3/3 (Δ0m) end=0/3 (Δ140m) grade=2/2 name=0/1 conf=1/1 = 6/10
  MISSED: high 08:35-15:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:35-12:30 (Albert B. Hart))
  false_positive: -3 (elementary 07:35-11:45 (Alfred A. Benesch))
  false_positive: -3 (elementary 08:35-12:30 (Almira))
  false_positive: -3 (elementary 07:35-11:45 (Andrew J. Rickoff))
  false_positive: -3 (elementary 08:35-12:30 (Anton Grdina))
  false_positive: -3 (elementary 08:35-12:30 (Artemus Ward))
  false_positive: -3 (elementary 08:35-12:30 (Benjamin Franklin))
  false_positive: -3 (elementary 09:35-12:45 (Bolton))
  false_positive: -3 (elementary 08:35-12:30 (Buhrer Dual Language))
  false_positive: -3 (elementary 09:00-12:45 (Campus International K8))
  false_positive: -3 (elementary 07:35-11:45 (Charles A. Mooney))
  false_positive: -3 (elementary 09:35-12:45 (Charles Dickens))
  false_positive: -3 (elementary 07:35-11:45 (Clara E. Westropp))
  false_positive: -3 (elementary 09:35-12:45 (Clark))
  false_positive: -3 (elementary 08:00-12:30 (Cleveland Metro Remote School))
  false_positive: -3 (elementary 07:35-11:45 (Daniel E. Morgan))
  false_positive: -3 (elementary 08:35-12:30 (Denison))
  false_positive: -3 (elementary 09:35-12:45 (Dike School of the Arts))
  false_positive: -3 (elementary 08:00-12:30 (Douglas MacArthur Girls' Leadership Academy))
  false_positive: -3 (elementary 07:35-11:45 (East Clark))
  false_positive: -3 (elementary 08:35-12:30 (Euclid Park))
  false_positive: -3 (middle 08:35-12:45 (Garfield))
  false_positive: -3 (middle 09:35-12:45 (George W. Carver))
  false_positive: -3 (middle 08:35-12:45 (Halle))
  false_positive: -3 (middle 09:35-12:45 (Hannah Gibbons))
  false_positive: -3 (middle 08:35-12:45 (Harvey Rice))
  false_positive: -3 (middle 08:35-12:45 (Joseph M. Gallagher))
  false_positive: -3 (middle 09:35-12:45 (Kenneth Clements Boys' Leadership Academy))
  false_positive: -3 (middle 08:35-12:45 (Louisa May Alcott))
  false_positive: -3 (middle 07:35-11:45 (Luis Muñoz Marin))
  false_positive: -3 (middle 09:35-12:45 (Marion C. Seltzer))
  false_positive: -3 (middle 08:35-12:45 (Marion-Sterling))
  false_positive: -3 (middle 07:35-11:45 (Mary B. Martin))
  false_positive: -3 (middle 09:35-12:45 (Mary Church Terrell))
  false_positive: -3 (middle 07:35-11:45 (Mary M. Bethune))
  false_positive: -3 (middle 09:35-12:45 (Memorial))
  false_positive: -3 (middle 08:35-12:45 (Miles))
  false_positive: -3 (middle 09:35-12:45 (Mound))
  false_positive: -3 (middle 08:35-12:45 (Nathan Hale))
  false_positive: -3 (middle 09:35-12:45 (Natividad Pagan International Newcomers Academy))
  false_positive: -3 (middle 07:35-11:45 (Orchard))
  false_positive: -3 (middle 09:35-12:45 (Paul L. Dunbar))
  false_positive: -3 (middle 08:35-12:45 (Riverside))
  false_positive: -3 (middle 09:35-12:45 (Robert H. Jamison))
  false_positive: -3 (middle 08:35-12:45 (Robinson G. Jones))
  false_positive: -3 (middle 07:35-11:45 (Scranton))
  false_positive: -3 (middle 09:35-12:45 (Stephanie Tubbs Jones School))
  false_positive: -3 (middle 08:35-12:45 (Stonebrook-White Montessori Campus))
  false_positive: -3 (middle 09:35-12:45 (Sunbeam))
  false_positive: -3 (middle 08:35-12:45 (Tremont Montessori))
  false_positive: -3 (middle 09:05-12:45 (Valley View Boys' Leadership Academy))
  false_positive: -3 (middle 08:35-12:45 (Wade Park))
  false_positive: -3 (middle 09:35-12:45 (Warner Girls' Leadership Academy))
  false_positive: -3 (middle 08:35-12:45 (Waverly))
  false_positive: -3 (middle 09:35-12:45 (Whitney M. Young))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:35', '12:30'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '07:35', '11:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:35', '12:45'))
  duplicate_extraction: -2 (Duplicate: ('middle', '09:35', '12:45'))
  missing_grade_level: -2 (Missing: high)

Total: 12 (entries) + -263 (penalties) = 0/30 (0.0%)

======================================================================
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 08:35-16:35 (Essex Middle School))
  false_positive: -3 (high 08:10-14:35 (Fivay High))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

======================================================================
CABELL COUNTY SCHOOLS (WV) - 5400180
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  middle 07:27-15:06 → middle 07:20-15:38 | start=0/3 (Δ7m) end=0/3 (Δ32m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (middle 07:20-14:35 (Huntington Middle School))
  false_positive: -3 (high 06:35-15:38 (HHS))

Total: 3 (entries) + -6 (penalties) = 0/10 (0.0%)

======================================================================
KANAWHA COUNTY SCHOOLS (WV) - 5400600
======================================================================
Ground truth: 1 entries | Extracted: 2 | Matched: 1

Entry Scores:
  elementary 07:15-14:15 → elementary 07:30-15:48 | start=0/3 (Δ15m) end=0/3 (Δ93m) grade=2/2 name=0/1 conf=1/1 = 3/10

Penalties:
  false_positive: -3 (middle 09:26-15:48 (Fivay High))

Total: 3 (entries) + -3 (penalties) = 0/10 (0.0%)