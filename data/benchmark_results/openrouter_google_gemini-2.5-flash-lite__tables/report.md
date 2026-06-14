# Benchmark Report: openrouter:google/gemini-2.5-flash-lite
Run date: 2026-06-14T02:50:29
Districts tested: 17
Total extraction time: 110s (avg 6.4s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 20.0% |
| JSON parse success | 100.0% |
| Grade coverage rate | 97.0% |
| False positive rate | 15.76/district |
| Mean time/extraction | 6.4s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| Albany County School District  | WY | 24 | 30 | 80.0% |  |  |
| LITTLE ROCK SCHOOL DISTRICT | AR | 16 | 30 | 53.3% | false_positive, false_positive, duplicate_extraction |  |
| KIPP DC PCS | DC | 14 | 30 | 46.7% | missing_grade_level |  |
| Burlington School District | VT | 3 | 10 | 30.0% | false_positive, false_positive |  |
| Sweetwater County School Distr | WY | 9 | 30 | 30.0% | false_positive, false_positive, false_positive (+1 more) |  |
| Matanuska-Susitna Borough Scho | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+14 more) |  |
| Fairbanks North Star Borough S | AK | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+34 more) |  |
| Bridgeport School District | CT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+64 more) |  |
| Waterbury School District | CT | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+67 more) |  |
| Des Moines Independent Comm Sc | IA | 0 | 10 | 0.0% | false_positive, false_positive |  |
| BONNEVILLE JOINT DISTRICT | ID | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+3 more) |  |
| Lynn | MA | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+50 more) |  |
| Lewiston Public Schools | ME | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+8 more) |  |
| DESOTO CO SCHOOL DIST | MS | 0 | 30 | 0.0% | false_positive, false_positive, false_positive (+48 more) |  |
| LINCOLN PUBLIC SCHOOLS | NE | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+109 more) |  |
| Cincinnati Public Schools | OH | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+13 more) |  |
| Essex Westford Educational Com | VT | 0 | 10 | 0.0% | false_positive, false_positive, false_positive (+1 more) |  |

## Detailed Scoring

======================================================================
Matanuska-Susitna Borough School District (AK) - 0200510
======================================================================
Ground truth: 1 entries | Extracted: 11 | Matched: 1

Entry Scores:
  high 07:45-14:15 → high 07:45-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (high 07:00-15:00 (Palmer High School))
  false_positive: -3 (high 07:00-15:00 (Houston High School))
  false_positive: -3 (elementary 08:00-15:00 (Big Lake Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Cottonwood Creek Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Goose Bay Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Machetanz Elementary School))
  false_positive: -3 (elementary 08:00-15:00 (Shaw Elementary School))
  false_positive: -3 (middle 08:00-15:00 (Colony Middle School))
  false_positive: -3 (middle 08:00-15:00 (Palmer Jr Middle School))
  false_positive: -3 (middle 08:00-15:00 (Teeland Middle School))
  duplicate_extraction: -2 (Duplicate: ('high', '07:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))

Total: 9 (entries) + -44 (penalties) = 0/10 (0.0%)

======================================================================
Fairbanks North Star Borough School District (AK) - 0200600
======================================================================
Ground truth: 1 entries | Extracted: 24 | Matched: 1

Entry Scores:
  elementary 07:40-14:10 → elementary 07:40-14:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

Penalties:
  false_positive: -3 (elementary 09:15-15:45 (ANNE WIEN ELEMENTARY))
  false_positive: -3 (elementary 08:00-14:30 (ARCTIC LIGHT ELEMENTARY))
  false_positive: -3 (elementary 08:15-14:45 (BARNETTE MAGNET))
  false_positive: -3 (elementary 08:45-15:15 (BOREAL SUN CHARTER))
  false_positive: -3 (elementary 08:15-14:45 (CHINOOK MONTESSORI CHARTER))
  false_positive: -3 (elementary 09:15-15:45 (DENALI ELEMENTARY))
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

Total: 8 (entries) + -97 (penalties) = 0/10 (0.0%)

======================================================================
LITTLE ROCK SCHOOL DISTRICT (AR) - 0509000
======================================================================
Ground truth: 3 entries | Extracted: 5 | Matched: 3

Entry Scores:
  elementary 07:40-14:55 → elementary 07:40-14:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 08:45-16:00 → high 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 08:45-16:00 → middle 08:45-16:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

Penalties:
  false_positive: -3 (middle 07:40-14:55 (K-8 Schools))
  false_positive: -3 (elementary 07:40-14:55 (K-8 Schools))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:40', '14:55'))

Total: 24 (entries) + -8 (penalties) = 16/30 (53.3%)

======================================================================
Bridgeport School District (CT) - 0900450
======================================================================
Ground truth: 1 entries | Extracted: 41 | Matched: 1

Entry Scores:
  elementary 08:50-15:10 → elementary 08:50-15:10 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

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
  false_positive: -3 (elementary 07:40-10:20 (Skane (AM)))
  false_positive: -3 (elementary 11:20-14:00 (Skane (PM)))
  false_positive: -3 (high 07:53-14:30 (Bassick))
  false_positive: -3 (high 07:53-14:30 (Central))
  false_positive: -3 (high 07:53-14:30 (Harding))
  false_positive: -3 (high 08:15-14:00 (Brpt. Learning Ctr.))
  false_positive: -3 (high 07:50-14:05 (Fairchild Wheeler))
  false_positive: -3 (high 07:55-14:10 (Bpt. Military Academy))
  false_positive: -3 (high 08:00-14:05 (Aquaculture))
  false_positive: -3 (elementary 08:50-15:10 (Classical Studies (K-6)))
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
  duplicate_extraction: -2 (Duplicate: ('elementary', '08:50', '15:10'))

Total: 8 (entries) + -174 (penalties) = 0/10 (0.0%)

======================================================================
Waterbury School District (CT) - 0904830
======================================================================
Ground truth: 3 entries | Extracted: 45 | Matched: 3

Entry Scores:
  elementary 08:35-14:50 → elementary 08:35-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  high 07:20-13:50 → high 07:20-13:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:50-14:20 → middle 07:50-14:20 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

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
  false_positive: -3 (middle 07:50-14:20 (Academic Academy (at Wallace)))
  false_positive: -3 (elementary 09:00-15:21 (Bucks Hill Pre-K))
  false_positive: -3 (high 07:20-13:00 (Enlightenment))
  false_positive: -3 (high 07:30-13:35 (State Street))
  false_positive: -3 (high 07:45-14:50 (ACES at Chase))
  false_positive: -3 (high 08:00-15:00 (Alpha & Omega Academy))
  false_positive: -3 (high 09:05-15:20 (Catholic Academy of Waterbury))
  false_positive: -3 (high 07:30-15:45 (Brass City Charter))
  false_positive: -3 (high 09:05-15:20 (Children's Community))
  false_positive: -3 (high 07:30-13:45 (Holy Cross High School))
  false_positive: -3 (high 07:25-14:20 (Kaynor Technical))
  false_positive: -3 (high 09:05-15:20 (Our Lady of Mount Carmel))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Bais Yaakov (Girls HS)))
  false_positive: -3 (high 09:00-16:00 (Yeshiva Gedolah (Boys HS)))
  false_positive: -3 (elementary 09:00-16:00 (Yeshiva K'Tana (Elementary)))
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
  duplicate_extraction: -2 (Duplicate: ('middle', '07:50', '14:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:05', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:05', '15:20'))
  duplicate_extraction: -2 (Duplicate: ('high', '09:00', '16:00'))

Total: 24 (entries) + -182 (penalties) = 0/30 (0.0%)

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
  high 08:40-15:48 → high 08:40-15:48 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

Penalties:
  false_positive: -3 (high 08:40-15:54 (Hillcrest High School))
  false_positive: -3 (high 08:00-14:45 (Lincoln High School))
  false_positive: -3 (middle 08:40-15:45 (Rocky Mountain Middle School))
  false_positive: -3 (middle 08:45-15:50 (Sandcreek Middle School))
  false_positive: -3 (high 08:40-15:48 (Thunder Ridge High School))
  duplicate_extraction: -2 (Duplicate: ('high', '08:40', '15:48'))

Total: 8 (entries) + -17 (penalties) = 0/10 (0.0%)

======================================================================
Lynn (MA) - 2507110
======================================================================
Ground truth: 3 entries | Extracted: 31 | Matched: 3

Entry Scores:
  high 07:45-14:30 → high 07:45-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 07:30-14:15 → middle 07:30-14:15 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
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

Total: 18 (entries) + -134 (penalties) = 0/30 (0.0%)

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
Ground truth: 3 entries | Extracted: 34 | Matched: 3

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
  false_positive: -3 (middle 08:30-15:25 (Lewisburg Middle))
  false_positive: -3 (elementary 08:30-15:25 (Sherwood Elementary))
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

Total: 27 (entries) + -133 (penalties) = 0/30 (0.0%)

======================================================================
LINCOLN PUBLIC SCHOOLS (NE) - 3172840
======================================================================
Ground truth: 1 entries | Extracted: 61 | Matched: 1

Entry Scores:
  high 08:00-15:00 → high 08:00-15:00 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

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
  false_positive: -3 (elementary 09:10-15:30 (Don D. Sherrill Education Center (K-5)))
  false_positive: -3 (middle 08:00-15:00 (Culler))
  false_positive: -3 (middle 08:00-15:00 (Dawes))
  false_positive: -3 (middle 08:00-15:00 (Goodrich))
  false_positive: -3 (middle 08:00-15:00 (Irving))
  false_positive: -3 (middle 08:00-15:00 (Lefler))
  false_positive: -3 (middle 08:00-15:00 (Lux))
  false_positive: -3 (middle 08:00-15:00 (Mickle))
  false_positive: -3 (middle 08:00-15:00 (Moore))
  false_positive: -3 (middle 08:00-15:00 (Park))
  false_positive: -3 (middle 08:00-15:00 (Pound))
  false_positive: -3 (middle 08:00-15:00 (Schoo))
  false_positive: -3 (middle 08:00-15:00 (Scott))
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
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:05'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('high', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
  duplicate_extraction: -2 (Duplicate: ('middle', '08:00', '15:00'))
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

Total: 8 (entries) + -284 (penalties) = 0/10 (0.0%)

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
Essex Westford Educational Community Unified Union SD #51 (VT) - 5000395
======================================================================
Ground truth: 1 entries | Extracted: 4 | Matched: 1

Entry Scores:
  elementary 07:30-14:30 → elementary 07:30-14:30 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10

Penalties:
  false_positive: -3 (high 08:40-15:15 (Essex High School))
  false_positive: -3 (middle 08:35-15:35 (Essex Middle School))
  false_positive: -3 (elementary 07:30-14:30 (Westford School))
  duplicate_extraction: -2 (Duplicate: ('elementary', '07:30', '14:30'))

Total: 8 (entries) + -11 (penalties) = 0/10 (0.0%)

======================================================================
Burlington School District (VT) - 5002820
======================================================================
Ground truth: 1 entries | Extracted: 3 | Matched: 1

Entry Scores:
  elementary 08:08-14:50 → elementary 08:08-14:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=1/1 = 9/10

Penalties:
  false_positive: -3 (elementary 08:10-14:50 (Edmunds Elementary))
  false_positive: -3 (middle 08:00-15:00 (Edmunds Middle School))

Total: 9 (entries) + -6 (penalties) = 3/10 (30.0%)

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
Ground truth: 3 entries | Extracted: 7 | Matched: 3

Entry Scores:
  high 08:00-15:55 → high 08:00-15:55 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  middle 08:30-15:50 → middle 08:30-15:50 | start=3/3 (Δ0m) end=3/3 (Δ0m) grade=2/2 name=0/1 conf=0/1 = 8/10
  elementary 07:50-15:15 → elementary 07:50-15:05 | start=3/3 (Δ0m) end=0/3 (Δ10m) grade=2/2 name=0/1 conf=0/1 = 5/10

Penalties:
  false_positive: -3 (elementary 08:00-15:15 (4 - 6 Elementary Schools))
  false_positive: -3 (elementary 07:45-15:00 (Elementary School))
  false_positive: -3 (middle 07:45-16:05 (Middle School))
  false_positive: -3 (high 07:45-16:05 (High School))

Total: 21 (entries) + -12 (penalties) = 9/30 (30.0%)