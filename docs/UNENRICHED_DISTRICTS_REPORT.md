# Unenriched Districts with Files - Processing Hurdles Report

**Generated:** 2026-01-26
**Updated:** 2026-01-26 (after processing)

## Processing Summary

| Metric | Before | After |
|--------|--------|-------|
| Districts analyzed | 14 | 14 |
| Districts enriched (total) | 52 | 66 |
| With files but not enriched | 14 | 2 |
| Successfully processed | - | 13 |

### Successfully Imported (13 districts)
- Friendship PCS DC (1100008) - PDF extraction
- KIPP DC PCS (1100031) - HTML extraction
- Joint SD #2 ID (1602100) - PDF extraction
- Carson City NV (3200390) - Excel parsing
- Albany County WY (5600730) - PDF extraction
- Sweetwater County WY (5605302) - PDF extraction
- Montgomery County AL (0102430) - OCR from PNG
- Lynn MA (2507110) - OCR from PNG
- Lewiston ME (2307320) - OCR from PNG + Excel
- Great Falls HS MT (3013050) - OCR from WebP (corrected district ID)
- Cleveland OH (3904378) - OCR from WebP
- Springdale AR (0512660) - OCR from images
- Little Rock AR (0509000) - Manual PDF download + extraction
- Bangor ME (2302820) - Manual PDF download + extraction

### Still Unenriched (2 districts)

- **Great Falls Elem MT (3013040)** - File was misplaced (contained HS data for 3013050)
- **Douglas County CO (0803450)** - Automated acquisition captured school homepages, not bell schedules

---

## Original Analysis

---

## Summary by Hurdle Type

| Hurdle Type | Count | Districts |
|-------------|-------|-----------|
| **Images (PNG/JPEG/WebP) - Need OCR** | 6 | Montgomery AL, Springdale AR (partial), Lynn MA, Great Falls MT, Cleveland OH, Lewiston ME (partial) |
| **Navigation-Only HTML** | 4 | Little Rock AR, Bangor ME, Springdale AR (partial), Friendship PCS |
| **Excel Files - Need Parsing** | 2 | Carson City NV, Lewiston ME (partial) |
| **Mixed Formats - Complex** | 2 | Springdale AR, Albany WY |
| **Extractable - Ready to Process** | 5 | Friendship PCS, KIPP DC, Joint SD #2 ID, Albany WY, Sweetwater WY |

---

## Detailed Analysis by District

### 1. Montgomery County, AL (0102430)
**Files:** 2 PNG images
**Hurdle:** Image-only format requiring OCR
**Content:**
- `Montgomery County Public Schools 1.png` (1105×1159)
- `Montgomery County Public Schools 2.png` (1085×806)

**Processing Required:** Run OCR (tesseract) on images to extract schedule data.

---

### 2. Little Rock, AR (0509000)
**Files:** 1 HTML file
**Hurdle:** Navigation page with no actual schedule data
**Content:** The HTML file `Bell Schedules _ LITTLE ROCK.html` only contains site navigation and footer. Actual schedule data was not captured.

**Processing Required:** Re-acquire from source. The Crawlee pipeline needs to follow the "Bell Schedules" link to reach actual schedule pages.

---

### 3. Springdale, AR (0512660)
**Files:** 10 files (3 HTML, 4 JPEG, 1 DOCX, 2 more)
**Hurdle:** Mixed formats with navigation HTML and images
**Content:**
- HTML files (`Attendance & Bell Schedule _ Harp Elementary.html`, etc.) contain only navigation menus
- JPEG images of individual school schedules (`Har-Ber High School.png`, `Helen Tyson Middle School 1.jpeg`, etc.)
- `SMS 2025-2026 Bell Schedule.docx` (empty or minimal content when extracted)

**Processing Required:**
1. OCR on JPEG/PNG images
2. Manual extraction from school-specific pages
3. District uses individual school pages rather than consolidated schedule

---

### 4. Friendship PCS, DC (1100008) ✅ EXTRACTABLE
**Files:** 1 PDF
**Hurdle:** None - data is extractable
**Content:** `FPCS_Parent_Student_Handbook_25-26.pdf` contains clear schedule data:
- All campuses: **7:45 AM - 3:30 PM** (M-F)
- Includes Armstrong, Blow Pierce, Chamberlain, Collegiate, Ideal, Southeast, Technology Prep, Woodridge

**Processing Required:** Ready for import. All schools share same schedule (7:45-3:30 = 345 min minus lunch/transitions ≈ 390 instructional minutes).

---

### 5. KIPP DC PCS (1100031) ✅ EXTRACTABLE
**Files:** 1 HTML file
**Hurdle:** None - data is in HTML
**Content:** `Calendar _ KIPP DC.html` contains:
- **PreK3-8:** 8:00 AM - 3:30 PM
- **High School:** 8:15 AM - 3:15 PM

**Processing Required:** Ready for import. Simple extraction from HTML text.

---

### 6. Joint School District No. 2, ID (1602100) ✅ EXTRACTABLE
**Files:** 1 PDF
**Hurdle:** None - excellent data quality
**Content:** `2025-26_West_Ada_Bell_Schedules.pdf` contains detailed schedules:
- **High School:** 7:40 AM - 2:39 PM (344 min instruction)
- **Middle School:** 8:20 AM - 3:05 PM (various schedules)
- **Elementary:** 9:10 AM - 3:55 PM (345 min instruction)

**Processing Required:** Ready for import. Clear times with total minutes listed.

---

### 7. Bangor, ME (2302820)
**Files:** 1 HTML file
**Hurdle:** Navigation page with no schedule data
**Content:** `School Hours _ Bangor School Department.html` shows navigation to "School Hours" but doesn't contain actual times.

**Processing Required:** Re-acquire. Need to follow link to actual school hours page.

---

### 8. Lewiston, ME (2307320)
**Files:** 2 files (1 PNG, 1 XLSX)
**Hurdle:** Image + Excel requiring different processing
**Content:**
- `2023 Start and end times.png` - Screenshot of all school times (requires OCR)
- `Lewiston High School Bell Schedule 24-25.xlsx` - Contains high school schedule:
  - Regular day: **7:45 AM** (with advisory) to **2:45 PM**
  - Period 1/5: 8:24-9:37, Period 2/6: 9:41-10:54, etc.

**Processing Required:**
1. OCR on PNG for elementary/middle data
2. Parse XLSX for high school (data is extractable)

---

### 9. Lynn, MA (2507110)
**Files:** 2 PNG images
**Hurdle:** Image-only format requiring OCR
**Content:**
- `Elementary Schools (2).png` (1080×1080)
- `Secondary Schools.png` (1080×1080)

**Processing Required:** Run OCR on images to extract schedule data.

---

### 10. Great Falls, MT (3013040)
**Files:** 1 WebP image
**Hurdle:** Image format requiring conversion + OCR
**Content:** `09-26-2024_GFH_BellSchedule25-26.png` is actually WebP format (967×286)

**Processing Required:**
1. Convert WebP to PNG: `convert file.webp file.png`
2. Run OCR to extract schedule data

---

### 11. Carson City, NV (3200390) ✅ EXTRACTABLE
**Files:** 1 Excel workbook
**Hurdle:** None - excellent data quality
**Content:** `Bell Schedules.xlsx` with 12 sheets covering all schools:
- Elementary schools (Bordewich, Empire, Fremont, Fritsch, Mark Twain, Seeliger): Start ~8:20 AM
- Middle schools (Carson MS, Eagle Valley MS): Various schedules
- High school (Carson High): Detailed period schedules

**Processing Required:** Parse Excel sheets. Rich data available.

---

### 12. Cleveland Municipal, OH (3904378)
**Files:** 1 WebP image
**Hurdle:** Image format requiring conversion + OCR
**Content:** `StartEndTimesFlier_7-11-25.webp` (1275×1650)

**Processing Required:**
1. Convert WebP to PNG
2. Run OCR - appears to be a flier with all school times

---

### 13. Albany County, WY (5600730) ✅ EXTRACTABLE
**Files:** 3 PDFs
**Hurdle:** None - excellent data quality
**Content:**
- **Slade Elementary:** First bell 7:59 AM, tardy 8:02 AM, end 3:00 PM (418 min)
- **Laramie Middle School:** 8:00 AM - 3:05 PM (detailed period schedules)
- **Whiting High School:** 7:45 AM - 3:45 PM (with periods 0-8)

**Processing Required:** Ready for import. Clear data in all three PDFs.

---

### 14. Sweetwater County, WY (5605302) ✅ EXTRACTABLE
**Files:** 1 PDF
**Hurdle:** None - excellent data quality
**Content:** `SchoolStartandEndTimes.pdf` with Rock Springs area schedules:
- **K-3 Elementary:** 7:50 AM - 3:05 PM (435 min)
- **4-6 Elementary:** 8:00 AM - 3:15 PM (435 min)
- **7-8 Junior High / Wamsutter K-8:** 8:30 AM - 3:50 PM (440 min)
- **9-12 High School:** 8:00 AM - 3:55 PM (475 min)
- **Farson-Eden:** 7:45 AM start, 3:00-4:05 PM end depending on level

**Processing Required:** Ready for import. 4-day school week noted.

---

## Prioritized Processing Recommendations

### Immediate (Ready to Import - 6 districts)
1. **Friendship PCS, DC** - PDF handbook with clear times
2. **KIPP DC PCS** - HTML with simple PreK-8 and HS times
3. **Joint SD #2, ID** - Excellent PDF with detailed schedules
4. **Carson City, NV** - Excel workbook with all schools
5. **Albany County, WY** - Three PDFs covering all levels
6. **Sweetwater County, WY** - Single PDF with comprehensive data

### Medium Effort (OCR Required - 5 districts)
7. **Montgomery County, AL** - 2 PNG images
8. **Lynn, MA** - 2 PNG images (elementary + secondary)
9. **Lewiston, ME** - 1 PNG + Excel parsing
10. **Great Falls, MT** - 1 WebP conversion + OCR
11. **Cleveland, OH** - 1 WebP conversion + OCR

### Re-Acquisition Required (4 districts)
12. **Little Rock, AR** - HTML is navigation-only
13. **Springdale, AR** - Mixed formats, mostly navigation
14. **Bangor, ME** - HTML is navigation-only

---

## Processing Commands Reference

```bash
# OCR on PNG images
tesseract image.png output -l eng

# Convert WebP to PNG
convert input.webp output.png

# Extract Excel data
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('file.xlsx')
for sheet in wb.sheetnames:
    print(f'=== {sheet} ===')
    for row in wb[sheet].iter_rows(max_row=20, values_only=True):
        print(row)
"

# Extract PDF text
pdftotext -layout input.pdf -
```

---

## Next Steps

1. **Batch import ready districts** (6 districts) - straightforward database inserts
2. **OCR processing** for image-based districts (5 districts)
3. **Re-run Crawlee acquisition** for navigation-only HTML districts (3 districts)
4. **Document Springdale AR** as needing individual school page scraping
