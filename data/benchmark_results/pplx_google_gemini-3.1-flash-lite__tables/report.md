# Benchmark Report: pplx:google/gemini-3.1-flash-lite
Run date: 2026-06-13T22:05:28
Districts tested: 7
Total extraction time: 24s (avg 3.4s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 37.1% |
| JSON parse success | 100.0% |
| Grade coverage rate | 88.2% |
| False positive rate | 5.29/district |
| Mean time/extraction | 3.4s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 27 | 30 | 90.0% |  |  |
| Sweetwater County School Distr | WY | 20 | 30 | 66.7% | false_positive |  |
| Bridgeport School District | CT | 3 | 10 | 30.0% | false_positive, false_positive |  |
| ORANGE | FL | 6 | 30 | 20.0% | false_positive, missing_grade_level |  |
| Cleveland Municipal | OH | 4 | 30 | 13.3% | false_positive, false_positive, false_positive (+2 more) |  |
| Montgomery County | AL | 3 | 30 | 10.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+36 more) |  |

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
  false_positive: -3 (high 07:30-14:00 (WEST VALLEY HIGH))
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
Ground truth: 3 entries | Extracted: 7 | Matched: 3

Entry Scores:
  elementary 08:10-15:10 → elementary 08:10-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 07:30-14:45 → middle 07:45-14:45 | start=0/3 (Δ15m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10
  high 07:15-14:45 → high 07:45-14:45 | start=0/3 (Δ30m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:10-15:10 (Brewbaker Primary School))
  false_positive: -3 (high 07:15-15:15 (Lanier High School))
  false_positive: -3 (middle 07:30-14:30 (McKee Middle School))
  false_positive: -3 (high 07:45-14:45 (Park Crossing Highschool))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:10', '15:10'))
  duplicate_extraction: -2 (Duplicate: ('high', '07:45', '14:45'))

Total: 19 (entries) + -16 (penalties) = 3/30 (10.0%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:50-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (middle 07:50-14:20 (Curiale Middle))
  false_positive: -3 (high 07:53-14:30 (Bassick))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

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
Ground truth: 3 entries | Extracted: 3 | Matched: 2

Entry Scores:
  elementary 08:45-15:00 → elementary 08:45-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 07:20-14:20 → high 07:10-14:10 | start=0/3 (Δ10m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 2/10
  MISSED: middle 09:30-16:04 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 08:15-15:30 (Lake Weston))
  missing_grade_level: -2 (Missing: middle)

Total: 11 (entries) + -5 (penalties) = 6/30 (20.0%)

======================================================================
Cleveland Municipal (OH) - 3904378
======================================================================
Ground truth: 3 entries | Extracted: 6 | Matched: 2

Entry Scores:
  elementary 08:35-15:05 → elementary 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  high 08:35-15:05 → high 08:35-15:05 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  MISSED: middle 08:35-15:05 (unnamed) → 0/10

Penalties:
  false_positive: -3 (elementary 09:35-16:05 (Adlai E. Stevenson))
  false_positive: -3 (elementary 07:35-14:05 (Oliver H. Perry))
  false_positive: -3 (high 09:00-15:30 (Bard High School Early College))
  false_positive: -3 (high 08:25-14:55 (Garrett Morgan School of Engineering and Innovation))
  missing_grade_level: -2 (Missing: middle)

Total: 18 (entries) + -14 (penalties) = 4/30 (13.3%)

======================================================================
Sweetwater County School District #1 (WY) - 5605302
======================================================================
Ground truth: 3 entries | Extracted: 4 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-15:15 (4 - 6 Elementary Schools))

Total: 23 (entries) + -3 (penalties) = 20/30 (66.7%)