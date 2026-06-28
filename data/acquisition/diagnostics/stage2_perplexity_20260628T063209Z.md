# Stage 2 — perplexity SERP evaluation

- generated: 2026-06-28T06:32:09Z  ·  provider: **perplexity**
- corpus: `batch_00001` (known-positive) · 53 schools
- reference: subagent Wave-1 25/53 (47.2%) · prior runs: OpenRouter 100%/~75%, Claude-low/none 66%/60%

## Summary

| n | OK% | err | gate-pass recall | schedule-kw | mean dur | est cost |
|---|---|---|---|---|---|---|
| 53 | 100.0 | 0 | **43.4%** (23/53) | 15.1% (8/53) | 0.466s | ~$0.265 |

## Raw calls (precision spot-check — eyeball the gated URLs)

| # | district | school | outcome | found | sched | raw | dur | gated URLs |
|---|---|---|---|---|---|---|---|---|
| 1 | 2600992 | Blue Water Middle College Academy | ok | ✓ | ✓ | 10 | 0.4s | https://www.bluewatermiddlecollege.org/about-bwmc/academic-calendar<br>https://www.bluewatermiddlecollege.org/o/bwmc/live-feed<br>https://www.bluewatermiddlecollege.org/o/bwmc<br>https://www.bluewatermiddlecollege.org/enrollment<br>https://www.bluewatermiddlecollege.org/o/scctec/page/academic-and-college-credit<br>https://www.bluewatermiddlecollege.org/about-bwmc<br>https://www.bluewatermiddlecollege.org/staff<br>https://www.bluewatermiddlecollege.org/beyond-the-bwmc/applying-to-colleges<br>https://www.bluewatermiddlecollege.org/students13/canvas-and-online-learning-at-sc4<br>https://www.bluewatermiddlecollege.org/beyond-the-bwmc/request-transcripts |
| 2 | 2900601 | HOPE LEADERSHIP ACADEMY | ok | ✓ | · | 8 | 0.3s | https://www.hlakc.org<br>https://www.hlakc.org/enrollment<br>https://www.hlakc.org/events/enrollment-fair<br>https://www.hlakc.org/profile/hopeleadershipacademykc94849/events<br>https://www.hlakc.org/meet-the-staff<br>https://www.hlakc.org/post/enrollment<br>https://www.hlakc.org/our-school<br>https://www.hlakc.org/boardofdirectors |
| 3 | 3502280 | ROY ELEMENTARY | ok | ✓ | ✓ | 8 | 0.3s | https://www.royschools.org/calendar<br>https://www.royschools.org/studentandparentinfo<br>https://www.royschools.org<br>https://www.royschools.org/boardmeetingnotesanddocuments<br>https://www.royschools.org/athletics<br>https://www.royschools.org/ourboard<br>https://www.royschools.org/about<br>https://www.royschools.org/administrativeforms |
| 4 | 3502280 | ROY HIGH | ok | ✓ | ✓ | 8 | 0.3s | https://www.royschools.org/studentandparentinfo<br>https://www.royschools.org/calendar<br>https://www.royschools.org<br>https://www.royschools.org/boardmeetingnotesanddocuments<br>https://www.royschools.org/athletics<br>https://www.royschools.org/ourboard<br>https://www.royschools.org/about<br>https://www.royschools.org/administrativeforms |
| 5 | 3400734 | Hoboken Dual Language Charter Scho | ok | ✓ | · | 2 | 0.3s | https://www.holahoboken.org/admissions<br>https://www.holahoboken.org/news |
| 6 | 2700159 | Sojourner Truth Academy | ok | ✓ | · | 10 | 0.4s | https://sojournertruthacademy.org/resources<br>https://sojournertruthacademy.org<br>https://sojournertruthacademy.org/announcements<br>https://sojournertruthacademy.org/about-us<br>https://sojournertruthacademy.org/enroll<br>https://sojournertruthacademy.org/contact-us/requests-for-proposals<br>https://sojournertruthacademy.org/about-us/curriculum<br>https://sojournertruthacademy.org/contact-us/donate<br>https://sojournertruthacademy.org/about-us/staff<br>https://sojournertruthacademy.org/about-us/awards-and-recognition |
| 7 | 3805460 | DUNSEITH ELEMENTARY SCHOOL | ok | ✓ | ✓ | 10 | 0.3s | https://www.dunseith.k12.nd.us/page/home<br>https://www.dunseith.k12.nd.us/live-feed?page_no=8<br>https://www.dunseith.k12.nd.us/live-feed?page_no=13<br>https://www.dunseith.k12.nd.us/live_feeds/11791460<br>https://www.dunseith.k12.nd.us/page/elementary<br>https://www.dunseith.k12.nd.us/page/contact-us<br>https://www.dunseith.k12.nd.us/page/elementary-school-class-links<br>https://www.dunseith.k12.nd.us/live-feed?page_no=17<br>https://www.dunseith.k12.nd.us<br>https://www.dunseith.k12.nd.us/staff |
| 8 | 3805460 | DUNSEITH HIGH SCHOOL | ok | ✓ | · | 10 | 0.5s | https://www.dunseith.k12.nd.us/page/student-handbook<br>https://www.dunseith.k12.nd.us/page/home<br>https://www.dunseith.k12.nd.us/live-feed?page_no=8<br>https://www.dunseith.k12.nd.us/live-feed?page_no=13<br>https://www.dunseith.k12.nd.us/page/contact-us<br>https://www.dunseith.k12.nd.us/live-feed?page_no=2<br>https://www.dunseith.k12.nd.us/page/athletics<br>https://www.dunseith.k12.nd.us<br>https://www.dunseith.k12.nd.us/live-feed?page_no=17<br>https://www.dunseith.k12.nd.us/staff |
| 9 | 1918690 | Francis Marion Intermediate School | ok | ✓ | ✓ | 3 | 0.9s | https://www.marion-isd.org/o/francis-marion<br>https://www.marion-isd.org/o/francis-marion/page/school-hours<br>https://www.marion-isd.org |
| 10 | 1918690 | Parkview Elementary School | ok | ✓ | · | 4 | 1.0s | https://www.marion-isd.org/o/parkview<br>https://www.marion-isd.org<br>https://www.marion-isd.org/o/vms<br>https://www.marion-isd.org/o/francis-marion |
| 11 | 1918690 | Longfellow Elementary | ok | ✓ | · | 3 | 0.9s | https://www.marion-isd.org/o/longfellow<br>https://www.marion-isd.org/o/longfellow/news<br>https://www.marion-isd.org/o/francis-marion |
| 12 | 1918690 | Vernon Middle School | ok | ✓ | · | 2 | 0.7s | https://www.marion-isd.org/o/vms<br>https://www.marion-isd.org |
| 13 | 1918690 | Marion High School | ok | ✓ | · | 4 | 0.7s | https://www.marion-isd.org<br>https://www.marion-isd.org/o/mhs<br>https://www.marion-isd.org/browse/173255<br>https://www.marion-isd.org/o/francis-marion |
| 14 | 5000425 | Monkton Central School | ok | · | · | 0 | 0.7s | — |
| 15 | 5000425 | Beeman Elementary School | ok | · | · | 0 | 0.8s | — |
| 16 | 5000425 | Robinson School | ok | · | · | 0 | 0.6s | — |
| 17 | 5000425 | Bristol Elementary School | ok | · | · | 0 | 0.8s | — |
| 18 | 5000425 | Mt. Abraham Union High School | ok | · | · | 0 | 1.3s | — |
| 19 | 2006180 | Eugene Ware Elem | ok | ✓ | · | 10 | 0.5s | https://www.usd234.org/o/eware/live-feed?page_no=2<br>https://www.usd234.org/o/eware<br>https://www.usd234.org/o/eware/news<br>https://www.usd234.org/o/eware/events?id=45351481<br>https://www.usd234.org/o/eware/article/856217<br>https://www.usd234.org/o/fshs/article/1106322<br>https://www.usd234.org/o/eware/staff?page_no=3<br>https://www.usd234.org/live-feed?page_no=10<br>https://www.usd234.org/o/fshs/article/2357507<br>https://www.usd234.org/o/fshs/article/2603859 |
| 20 | 2006180 | Winfield Scott Elem | ok | ✓ | · | 10 | 0.4s | https://www.usd234.org/o/wscott/live-feed?page_no=5<br>https://www.usd234.org/o/fspc/article/1711424<br>https://www.usd234.org/o/wscott/events<br>https://www.usd234.org/o/eware/news<br>https://www.usd234.org/o/fshs/article/1106322<br>https://www.usd234.org/o/wscott/staff?page_no=4<br>https://www.usd234.org/o/fshs/article/2357507<br>https://www.usd234.org/o/wscott/staff<br>https://www.usd234.org/o/eware/article/796355<br>https://www.usd234.org/news |
| 21 | 2006180 | Fort Scott Middle School | ok | ✓ | · | 10 | 0.4s | https://www.usd234.org/o/fshs/article/2719572<br>https://www.usd234.org/o/fshs/article/2357507<br>https://www.usd234.org/o/fsms/live-feed?page_no=4<br>https://www.usd234.org<br>https://www.usd234.org/o/fshs/news?page_no=29<br>https://www.usd234.org/o/fsms/news<br>https://www.usd234.org/o/fshs/article/2603859<br>https://www.usd234.org/o/fsms/events<br>https://www.usd234.org/o/fshs/article/2577284<br>https://www.usd234.org/o/fshs/article/1106322 |
| 22 | 2006180 | Fort Scott Sr High | ok | ✓ | · | 10 | 0.4s | https://www.usd234.org/o/fshs/article/2357507<br>https://www.usd234.org/o/fshs/news?page_no=4<br>https://www.usd234.org/o/fshs/article/2719572<br>https://www.usd234.org/o/fshs/news?page_no=29<br>https://www.usd234.org/o/fshs/article/2577284<br>https://www.usd234.org/o/fshs/article/2603859<br>https://www.usd234.org<br>https://www.usd234.org/live-feed?page_no=4<br>https://www.usd234.org/o/fshs/live-feed<br>https://www.usd234.org/o/fshs/article/2760213 |
| 23 | 4222860 | B F Morey El Sch | ok | · | · | 0 | 0.3s | — |
| 24 | 4222860 | Chipperfield El Sch | ok | · | · | 0 | 0.3s | — |
| 25 | 4222860 | Arlington Heights El Sch | ok | · | · | 0 | 0.3s | — |
| 26 | 4222860 | Hamilton Twp El Sch | ok | · | · | 0 | 0.4s | — |
| 27 | 4222860 | Stroudsburg MS | ok | · | · | 0 | 0.3s | — |
| 28 | 4222860 | Stroudsburg JHS | ok | · | · | 0 | 0.3s | — |
| 29 | 4222860 | Stroudsburg HS | ok | · | · | 0 | 0.4s | — |
| 30 | 1739960 | Leal Elem School | ok | ✓ | · | 10 | 0.6s | https://usd116.org/schools/<br>https://usd116.org/wp-content/uploads/2025/06/Leal-Student-Handbook-2025-26-.pdf<br>https://leal.usd116.org/wp-content/uploads/2021/06/Leal-Student-Parent-Handbook-21-22-English.pdf<br>https://yridge.usd116.org/wp-content/uploads/2022/08/FINAL-student-parent-handbook-2022-23.pdf<br>https://leal.usd116.org/about/<br>https://usd116.org/wp-content/uploads/2026/05/Spanish-2025-26-Policy-and-Procedure-Manual-.pdf<br>https://usd116.org/wp-content/uploads/2024/06/King-Handbook-2024-25-SY-1.pdf<br>https://usd116.org/beforeafterschool/<br>https://drwilliams.usd116.org<br>https://usd116.org/wp-content/uploads/2022/08/FINAL-UrbanaSchoolDistrict116.Booklet8.31.2022.pdf |
| 31 | 1739960 | M L King Jr Elem School | ok | ✓ | ✓ | 10 | 0.6s | https://usd116.org/schools/<br>https://usd116.org/wp-content/uploads/2024/06/King-Handbook-2024-25-SY-1.pdf<br>http://www.usd116.org/files/ParentHandbooks/2018-19%20Handbooks/2018-19DrKing-ENG.pdf<br>https://drking.usd116.org/about/<br>https://usd116.org/wp-content/uploads/2025/06/YRM-student-parent-handbook-2025-26.pdf<br>https://usd116.org/kindergarten/<br>https://ums.usd116.org/wp-content/uploads/2020/07/20-21-UMS-Handbook.pdf<br>https://usd116.org/wp-content/uploads/2024/06/2024-2025-UMS-Student-Handbook-.pdf<br>https://tmspaine.usd116.org<br>https://usd116.org/calendar/ |
| 32 | 1739960 | Dr Preston L Williams Jr Elem Sch | ok | ✓ | · | 10 | 0.6s | https://drwilliams.usd116.org/about/<br>https://drwilliams.usd116.org/wp-content/uploads/2020/07/Student-Handbook-2020-2021-1.pdf<br>https://usd116.org/schools/<br>https://usd116.org/kindergarten/<br>http://usd116.org/files/2014-15BoardDocs/2015-6-2/2015-6-2-StudySessionAgenda.pdf<br>https://usd116.org/wp-content/uploads/2022/08/FINAL-UrbanaSchoolDistrict116.Booklet8.31.2022.pdf<br>https://drwilliams.usd116.org/wp-content/uploads/2021/06/DPW-Spanish-Handbook-2021-2022.pdf<br>https://usd116.org/page/37/<br>https://usd116.org/wp-content/uploads/2025/10/2025-2026-Non-Union-Employee-Handbook.pdf<br>https://usd116.org/wp-content/uploads/2026/05/Spanish-2025-26-Policy-and-Procedure-Manual-.pdf |
| 33 | 1739960 | Thomas Paine Elem School | ok | ✓ | · | 10 | 0.4s | https://tmspaine.usd116.org<br>https://usd116.org/schools/<br>https://usd116.org/usd-summer-programs-2026/<br>https://tmspaine.usd116.org/wp-content/uploads/2019/11/ThomasPaineCompact19web.pdf<br>https://usd116.org/redistricting2024/<br>https://tmspaine.usd116.org/about/<br>https://usd116.org/kindergarten/<br>https://usd116.org/wp-content/uploads/2024/06/2024-2025-UMS-Student-Handbook-.pdf<br>https://ums.usd116.org/wp-content/uploads/2020/07/20-21-UMS-Handbook.pdf<br>http://usd116.org/files/2013-14-BoardDocs/2013-11-19/11-19-13BusinessMeetingAgenda.pdf |
| 34 | 1739960 | Urbana Middle School | ok | ✓ | ✓ | 10 | 0.6s | https://ums.usd116.org/ums-bell-schedule/<br>https://usd116.org/schools/<br>https://usd116.org/wp-content/uploads/2024/06/2024-2025-UMS-Student-Handbook-.pdf<br>https://www.usd116.org/files/2013-14-StudentGuidebook.pdf<br>https://usd116.org/wp-content/uploads/2025/06/UHS-student-handbook-2025-2026.pdf<br>https://ums.usd116.org/wp-content/uploads/2020/07/20-21-UMS-Handbook.pdf<br>https://usd116.org/boe041525/<br>https://yridge.usd116.org<br>https://usd116.org/calendar/<br>https://usd116.org/page/37/ |
| 35 | 1739960 | Urbana High School | ok | ✓ | ✓ | 10 | 0.5s | https://usd116.org/wp-content/uploads/2024/07/Final-UHS-Student-Handbook-SY24-25-1.pdf<br>http://www.usd116.org/files/StudentHandbook.pdf<br>https://usd116.org/schools/<br>https://usd116.org/wp-content/uploads/2025/09/2025-26-USD-Calendar-Board-approved-March-4-2025.pdf<br>https://usd116.org/wp-content/uploads/2024/06/2024-2025-UMS-Student-Handbook-.pdf<br>https://usd116.org/calendar/<br>https://yridge.usd116.org<br>https://ums.usd116.org/ums-bell-schedule/<br>https://ums.usd116.org/wp-content/uploads/2020/07/20-21-UMS-Handbook.pdf<br>https://usd116.org/boe100725/ |
| 36 | 5102940 | Chatham Elementary | ok | · | · | 0 | 0.3s | — |
| 37 | 5102940 | Gretna Elementary | ok | · | · | 0 | 0.3s | — |
| 38 | 5102940 | John L. Hurt Elementary | ok | · | · | 0 | 0.4s | — |
| 39 | 5102940 | Kentuck Elementary | ok | · | · | 0 | 0.3s | — |
| 40 | 5102940 | Mount Airy Elementary | ok | · | · | 0 | 0.3s | — |
| 41 | 5102940 | Southside Elementary | ok | · | · | 0 | 0.3s | — |
| 42 | 5102940 | Stony Mill Elementary | ok | · | · | 0 | 0.4s | — |
| 43 | 5102940 | Union Hall Elementary | ok | · | · | 0 | 0.3s | — |
| 44 | 5102940 | Twin Springs Elementary | ok | · | · | 0 | 0.3s | — |
| 45 | 5102940 | Brosville Elementary | ok | · | · | 0 | 0.5s | — |
| 46 | 5102940 | Tunstall Middle | ok | · | · | 0 | 0.3s | — |
| 47 | 5102940 | Chatham Middle | ok | · | · | 0 | 0.3s | — |
| 48 | 5102940 | Dan River Middle | ok | · | · | 0 | 0.5s | — |
| 49 | 5102940 | Gretna Middle | ok | · | · | 0 | 0.3s | — |
| 50 | 5102940 | Chatham High | ok | · | · | 0 | 0.4s | — |
| 51 | 5102940 | Dan River High | ok | · | · | 0 | 0.3s | — |
| 52 | 5102940 | Gretna High | ok | · | · | 0 | 0.3s | — |
| 53 | 5102940 | Tunstall High | ok | · | · | 0 | 0.4s | — |