# Bell Schedule Enrichment Operations Guide

## Purpose

This operational guide provides step-by-step procedures, troubleshooting routines, and tool usage patterns for the bell schedule enrichment campaign. It encodes best practices that should be followed to avoid stalls, maximize token efficiency, and ensure consistent data collection.

**Key Principle:** Prioritize local file processing over API calls whenever possible to maximize token efficiency and user value.

**Quick Access:** See `docs/QUICK_REFERENCE_BELL_SCHEDULES.md` for a one-page cheat sheet of most common commands and decision trees.

---

## Available Tools Inventory

### Web Tools (Remote Processing)
- **WebSearch** - Search for bell schedules online
- **WebFetch** - Fetch HTML content from URLs
- **Read (images)** - API-based image reading (FALLBACK ONLY - prone to errors)

### Local Processing Tools (PREFERRED)
- **tesseract** - OCR for extracting text from images (PNG, JPG, TIFF)
- **pdftotext** - Extract text from PDF files
- **ocrmypdf** - OCR PDFs (if pdftotext fails on image-based PDFs)
- **convert** (ImageMagick) - Image format conversion, manipulation
- **pup** - HTML/CSS selector for parsing HTML files
- **curl** - Download files to local filesystem
- **grep/sed/awk** - Text processing and pattern extraction

### When to Use Local vs. Remote

| Scenario | Tool Choice | Reasoning |
|----------|-------------|-----------|
| Image contains bell schedule | `curl` + `tesseract` | More reliable than Read API, no token overhead |
| PDF contains bell schedule | `curl` + `pdftotext` | Direct extraction, faster than API processing |
| HTML parsing needed | `curl` + `pup` or `grep` | Local processing more efficient |
| Need to analyze webpage | WebFetch | Remote processing acceptable for initial fetch |
| Need to search for URLs | WebSearch | Required for discovery |

---

## Search Strategy Best Practices

### Current School Year Awareness

**CRITICAL: Always search for the CURRENT school year first**

As of December 2024, the current school year is **2025-26** (Fall 2025 - Spring 2026).

**Search Year Priority:**
1. **2025-26** (current year) - Try FIRST
2. **2024-25** (prior year) - Acceptable fallback
3. **2023-24** (two years old) - Last resort, still valid for post-COVID data

**❌ NEVER search for COVID-era years:** 2019-20, 2020-21, 2021-22, 2022-23

### Effective Search Terms

Use a variety of search terms to maximize discovery. Schools use different terminology:

**Primary Terms:**
- "bell schedule" - Most common official term
- "daily schedule" - Alternative phrasing
- "school day" - Broader term that often includes times

**Time-Related Terms:**
- "start time" / "start times"
- "end time" / "dismissal time"
- "arrival time"
- "dismissal"

**Example Search Patterns:**
```
Good: "[District Name] bell schedule 2025-26"
Good: "[District Name] daily schedule 2025-26"
Good: "[District Name] school start end times 2025-26"
Good: "[School Name] bell schedule arrival dismissal"

Avoid: "[District Name] bell schedule 2024-25"  # Unless 2025-26 fails
```

**Multi-Term Strategy:**
If initial search doesn't find results, try combinations:
- "bell schedule" + "school day"
- "daily schedule" + "start" + "dismissal"
- "[School Name]" + "arrival" + "end time"

### Using Gemini for Research Assistance

**Purpose:** Leverage Google Gemini (via MCP) to accelerate discovery of bell schedule resources

**Available Tool:** `mcp__gemini__gemini-query`

**What Gemini is Good For:**
- ✅ Identifying potential web pages, PDFs, and .docx files that might contain schedules
- ✅ Understanding district structure (elementary/middle/high schools)
- ✅ Suggesting search strategies for difficult-to-find districts
- ✅ Recognizing general schedule patterns (e.g., "elementary typically 9am-3pm")

**What Gemini is NOT Authoritative For:**
- ❌ Specific start and end times (MUST verify with actual sources)
- ❌ URLs (often outdated or incorrect - verify with WebSearch/WebFetch)
- ❌ Exact instructional minutes
- ❌ Current year schedules (may provide older data)

**Recommended Workflow:**
```
1. Use Gemini for initial research and discovery
   → "What are the schools in [District Name]?"
   → "Where might I find bell schedules for [District Name]?"

2. Verify URLs with WebSearch
   → Find actual current URLs, not Gemini's suggestions

3. Fetch and extract with WebFetch or local tools
   → Get authoritative data from verified sources

4. Insert verified data into database
   → Only use data extracted from actual district sources
```

**Token Efficiency Note:** Use Gemini when it saves tokens by reducing blind searching. Skip it when direct searches are faster (e.g., obvious district website patterns).

**Example:**
```
Good: Use Gemini to identify which schools to sample in a large district
Bad:  Trust Gemini's provided start/end times without verification
```

---

## District Accessibility Patterns ⭐ EMPIRICAL INSIGHTS

Based on analysis of 15+ state enrichment campaigns (December 2025), certain patterns predict enrichment success.

### Characteristics of Successfully Enriched Districts

Districts that tend to have accessible bell schedules:

| Pattern | Indicator | Example |
|---------|-----------|---------|
| **Dedicated bell schedule page** | URL contains "bell-schedule" or "school-hours" | `/about-us/bell-schedule` |
| **District-wide policies** | Single authoritative schedule for all schools | "All elementary schools: 8:00-3:00" |
| **Modern website infrastructure** | Recent site updates (2024-2025) | Copyright shows current year |
| **Consistent URL patterns** | Predictable school subdomain structure | `{school}.district.org/schedules` |
| **Multiple data sources** | District + individual school confirmation | Cross-reference available |
| **PDF handbooks available** | Parent handbooks with schedule sections | Direct download links |

### Characteristics of Blocked/Inaccessible Districts

Districts that typically require manual follow-up:

| Pattern | Indicator | Action |
|---------|-----------|--------|
| **Aggressive WAF/Cloudflare** | 403 errors on all pages | Add to manual follow-up immediately |
| **Large page sizes** | Pages >100KB that timeout | Add to manual follow-up |
| **Extensive 404 errors** | 4+ broken schedule links | Add to manual follow-up |
| **Outdated websites** | Last update 2022 or earlier | Try 2-3 pages, then manual follow-up |
| **JavaScript-only content** | Schedule in dynamic widgets | Add to manual follow-up |
| **Login-required sections** | "Parent Portal" for schedules | Add to manual follow-up |

### Success Rate by District Rank

Empirical data from Idaho, Nebraska, Mississippi, Kansas campaigns:

| Rank | Success Rate | Notes |
|------|--------------|-------|
| 1 | ~40% | Largest districts often have complex infrastructure |
| 2 | ~45% | Still large, similar challenges |
| 3 | ~50% | Moderate complexity |
| 4-5 | ~80% | Sweet spot - enough resources for good websites |
| 6-7 | ~85% | Smaller, simpler infrastructure |
| 8-9 | ~80% | May have less web presence |

**Key insight:** Districts ranked 4-9 have an ~83% success rate vs ~44% for ranks 1-3. The expanded candidate pool (Option A) leverages this pattern.

### Pre-Screening Recommendations

Before attempting enrichment, quick indicators of likely success:

**Positive signals (try this district):**
- ✅ Search results show dedicated schedule pages
- ✅ District website is `.org` or `.k12.XX.us`
- ✅ Multiple schools have consistent URL patterns
- ✅ Search results include PDF documents

**Warning signals (may need manual follow-up):**
- ⚠️ No schedule pages in search results
- ⚠️ Cloudflare or "Security Check" in search snippets
- ⚠️ Only results from third-party sites (GreatSchools, Niche)
- ⚠️ All results are 2+ years old

### Notable Schedule Patterns Discovered

During enrichment campaigns, several interesting patterns emerged:

| Pattern | States/Districts | Notes |
|---------|------------------|-------|
| **Four-day school week** | ID (Nampa), rural districts | Mon-Thu, longer days |
| **Three-tier bell schedules** | KS (Olathe) | Bus efficiency, staggered starts |
| **A/B rotating blocks** | MS (Madison County, Rosa Scott HS) | 94-min blocks, alternate days |
| **Wednesday modified** | KS (Wichita), NE (various) | Early release or "Ace Day" |
| **Multi-zone districts** | MS (Rankin County) | 8 different schedule zones |
| **Early high school start** | KS (Olathe, Shawnee Mission) | 7:40 AM high school |

These patterns should be documented in notes fields when encountered.

---

## Quality Metrics Tracking

### Per-District Metrics

Track for each enrichment attempt:

| Metric | Description | Target |
|--------|-------------|--------|
| Tool calls | WebSearch + WebFetch count | ≤4 per success |
| Token usage | Approximate tokens consumed | ≤2,500 per success |
| Time to success | Attempts before success | ≤3 attempts |
| Data completeness | All three grade levels found | 100% |
| Source quality | Verified vs estimated data | "high" confidence |

### Per-State Metrics

Track for each state:

| Metric | Description | Target |
|--------|-------------|--------|
| Completion rate | Districts successfully enriched / 9 attempted | ≥33% (3/9) |
| Manual follow-ups | Districts marked for manual | ≤6 per state |
| Total attempts | Districts tried before reaching 3 | ≤6 average |
| Session efficiency | Tokens per completed state | ≤15K tokens |

### Cumulative Metrics

Track across campaign:

| Metric | Current Value | Notes |
|--------|---------------|-------|
| States completed (≥3) | 25/55 | 45% of states/territories |
| Total enriched districts | 104 | 0.58% of 17,842 |
| Total bell schedules | 296 | ~3 per district average |
| Manual follow-up queue | 6 districts | Ready for human collection |
| Success rate (ranks 1-3) | ~44% | Historical average |
| Success rate (ranks 4-9) | ~83% | Historical average |

---

## Standard Operating Procedures

### SOP 1: Bell Schedule Discovery

**Objective:** Find bell schedule information for a district

**Steps:**
1. **Web Search** for district bell schedule (use current school year 2025-26)
   ```
   WebSearch("[District Name] bell schedule 2025-26")
   WebSearch("[District Name] daily schedule school day 2025-26")
   WebSearch("[District Name] start end times dismissal 2025-26")
   ```

   If no results, try prior year:
   ```
   WebSearch("[District Name] bell schedule 2024-25")
   ```

2. **Evaluate Results** - Look for:
   - District-wide bell schedule pages
   - Individual school schedule pages
   - PDF documents with schedules
   - School handbooks

3. **Check for Security Blocks** (ONE attempt rule)
   - If Cloudflare/WAF detected → Add to `manual_followup_needed.json`
   - **If 4+ 404 errors (1 district + 3 schools)** → Add to manual follow-up
   - Move to next district immediately
   - **CRITICAL:** See `ENRICHMENT_SAFEGUARDS.md` for auto-flagging rules

4. **Select Best Source** - Prioritize in order:
   - District-wide policy page
   - Elementary/Middle/High school representative samples
   - School handbooks
   - State statutory requirements (fallback)

### SOP 1A: School-Level Discovery ⭐ NEW

**Objective:** Find individual school websites within a district when district-wide searches fail

**Context:** Research shows 80%+ of districts do NOT publish district-wide bell schedules. Schedules are decentralized at the school level. This SOP provides procedures for discovering and sampling individual school sites.

**When to use:**
- After district-level search (SOP 1) yields no results
- When district website has no centralized bell schedule page
- When preliminary search suggests school-level organization

**Steps:**

1. **Identify Target Schools**

   **Method A: Query NCES database**
   ```python
   # Get schools in district
   from infrastructure.database.connection import session_scope
   from infrastructure.database.models import School

   with session_scope() as session:
       schools = session.query(School).filter_by(district_id='XXXXXXX').all()
       for school in schools:
           print(f"{school.name} - {school.level}")
   ```

   **Method B: Search for district schools directory**
   ```
   WebSearch("{District Name} schools directory")
   WebFetch("{district-url}/schools")
   ```

2. **Test Common Subdomain Patterns**

   Districts typically use these URL patterns:

   ```bash
   # Pattern 1: School name subdomains
   curl -I https://lincoln-hs.{district.org}  # Returns 200 if exists
   curl -I https://washington-ms.{district.org}

   # Pattern 2: Common prefixes (elementary/middle/high)
   curl -I https://hs.{district.org}
   curl -I https://ms.{district.org}
   curl -I https://elem.{district.org}
   curl -I https://elementary.{district.org}

   # Pattern 3: Abbreviated school names
   curl -I https://lhs.{district.org}  # Lincoln High School
   curl -I https://wms.{district.org}  # Washington Middle School
   ```

   **Success indicators:** HTTP 200 or 301/302 redirect (not 404)

3. **Extract School Links from District Site**

   ```bash
   # Download district site
   curl -o /tmp/district.html "{district-url}"

   # Extract school links with pup
   cat /tmp/district.html | pup 'a[href*="school"]@href'
   cat /tmp/district.html | pup 'nav a@href' | grep -i school

   # Alternative: grep for patterns
   grep -oE 'https?://[^"]+school[^"]+' /tmp/district.html
   ```

4. **Search for Individual School Bell Schedules**

   Once school websites identified, search each:

   ```
   WebSearch("{School Name} bell schedule 2025-26")
   WebSearch("{School Name} {District Name} daily schedule")
   WebSearch("site:{school-url} bell schedule")
   ```

   **Tip:** Use school name + district name to avoid ambiguity

5. **Sample Representative Schools**

   Follow the sampling strategy from BELL_SCHEDULE_SAMPLING_METHODOLOGY.md:

   | Level | Selection Criteria | Rationale |
   |-------|-------------------|-----------|
   | **Elementary** | Largest enrollment elementary | Most representative |
   | **Middle** | Largest enrollment middle | Most representative |
   | **High** | Largest enrollment high | Most representative |

   **Quality check:** If possible, sample 2-3 schools per level to verify consistency

6. **Common School Site URL Patterns by State**

   Based on empirical data (see DISTRICT_WEBSITE_LANDSCAPE_2026.md):

   | State | Common Pattern | Example |
   |-------|---------------|---------|
   | Florida | {school}.{district}.k12.fl.us | lincolnhs.district.k12.fl.us |
   | Wisconsin | {school}.{district}.k12.wi.us | elementary.district.k12.wi.us |
   | Oregon | {school}.{district}.k12.or.us | middle.district.k12.or.us |
   | California | {district}.org/{school} | district.org/lincoln-high |
   | Texas | {school}.{district}.net | lincolnhs.districtxxx.net |
   | New York | {district}.org/schools/{school} | district.org/schools/lincoln-hs |

7. **CMS Platform Detection**

   Identify CMS early to apply platform-specific strategies:

   ```bash
   # Check for Finalsite
   curl -I "{url}" | grep -i finalsite
   cat /tmp/page.html | grep -i "/fs/pages"

   # Check for SchoolBlocks
   curl -I "{url}" | grep -i schoolblocks

   # Check for Blackboard/Edlio
   cat /tmp/page.html | grep -i "schoolinsites\|schoolwires"
   ```

   **Adjust timeout based on CMS:**
   - Finalsite: 60+ seconds (heavy JavaScript)
   - SchoolBlocks: 45+ seconds (Vue.js SPA)
   - Legacy/Static: 30 seconds (standard)

**Success Criteria:**
- Found 1-3 schools per grade level
- Extracted bell schedules from school sites
- Documented source URLs per school
- Confidence level: "medium" (school sample) or "high" (multiple schools)

**Failure Criteria (trigger manual follow-up):**
- 404 errors on 4+ school sites (indicates hardened security)
- Cloudflare/WAF blocks on school sites
- No accessible school websites found
- All school sites timeout (>60 seconds)

**Example Workflow:**

```bash
# 1. District-level search failed, moving to school-level
WebSearch("Springfield Public Schools bell schedule 2025-26")  # No results

# 2. Find schools in district
WebSearch("Springfield Public Schools elementary middle high schools")

# 3. Test subdomain patterns
curl -I https://hs.springfield.org  # 200 OK - found!
curl -I https://ms.springfield.org  # 200 OK - found!
curl -I https://elem.springfield.org  # 404 - not used

# 4. Search for schedules at discovered schools
WebSearch("site:hs.springfield.org bell schedule")
WebFetch("https://hs.springfield.org/about/bell-schedule")

# 5. Extract and validate data
curl -o /tmp/hs_schedule.html "https://hs.springfield.org/about/bell-schedule"
cat /tmp/hs_schedule.html | pup 'div.schedule text{}'
```

### SOP 2: Document Processing - Images

**Objective:** Extract bell schedule data from PNG, JPG, or other image files

**CRITICAL: Always use local processing for images**

**Steps:**
1. **Download Image Locally**
   ```bash
   curl -o /tmp/bell_schedule.png "https://example.com/schedule.png"
   ```

2. **Verify Download**
   ```bash
   ls -lh /tmp/bell_schedule.png
   file /tmp/bell_schedule.png  # Verify it's actually an image
   ```

3. **Extract Text with OCR (PREFERRED METHOD)**
   ```bash
   tesseract /tmp/bell_schedule.png stdout
   ```

4. **Alternative: Convert format first** (if tesseract has issues)
   ```bash
   convert /tmp/bell_schedule.png /tmp/bell_schedule.tiff
   tesseract /tmp/bell_schedule.tiff stdout
   ```

5. **Parse Extracted Text**
   - Look for time patterns (8:00 AM, 3:30 PM)
   - Calculate instructional minutes
   - Note lunch and break times

**DO NOT:** Use Read tool for images as primary method - it's prone to API errors

**Troubleshooting:**
- If OCR output is garbled → Check image quality with `convert schedule.png -resize 200% large.png`
- If still poor → Note in manual follow-up, estimate from school hours if available
- If image is sideways → `convert -rotate 90 schedule.png rotated.png`

### SOP 3: Document Processing - PDFs

**Objective:** Extract bell schedule data from PDF documents

**Steps:**
1. **Download PDF Locally**
   ```bash
   curl -o /tmp/bell_schedule.pdf "https://example.com/schedule.pdf"
   ```

2. **Try Text Extraction First** (for text-based PDFs)
   ```bash
   pdftotext /tmp/bell_schedule.pdf /tmp/schedule.txt
   cat /tmp/schedule.txt
   ```

3. **If Text Extraction Fails** (image-based PDF)
   ```bash
   ocrmypdf /tmp/bell_schedule.pdf /tmp/schedule_ocr.pdf
   pdftotext /tmp/schedule_ocr.pdf /tmp/schedule.txt
   cat /tmp/schedule.txt
   ```

4. **Parse Extracted Text**
   ```bash
   # Extract times
   grep -E "[0-9]{1,2}:[0-9]{2}" /tmp/schedule.txt

   # Or use sed/awk for more complex extraction
   ```

**Troubleshooting:**
- If pdftotext produces empty output → PDF is image-based, use ocrmypdf
- If ocrmypdf fails → Convert to images first: `convert -density 300 schedule.pdf schedule-%03d.png`
- Then OCR each page: `tesseract schedule-001.png stdout`

### SOP 4: HTML Content Processing

**Objective:** Extract bell schedule data from HTML pages

**Steps:**
1. **Fetch and Save HTML Locally**
   ```bash
   curl -o /tmp/schedule.html "https://example.com/bell-schedule"
   ```

2. **Method A: Use pup for CSS selectors**
   ```bash
   cat /tmp/schedule.html | pup 'table.bell-schedule text{}'
   cat /tmp/schedule.html | pup 'div#schedule text{}'
   ```

3. **Method B: Use grep for pattern matching**
   ```bash
   grep -E "[0-9]{1,2}:[0-9]{2}\s*(AM|PM)" /tmp/schedule.html
   ```

4. **Method C: Use WebFetch with prompt** (if above fails)
   ```
   WebFetch("https://example.com/bell-schedule", "Extract the bell schedule times")
   ```

**Best Practice:** Save locally first, then parse. This allows retry without re-fetching.

### SOP 5: Data Validation and Recording

**Objective:** Validate extracted data and save enrichment record

**Validation Checklist:**
- [ ] Times are reasonable (6 AM - 6 PM range)
- [ ] End time is after start time
- [ ] Lunch duration is reasonable (20-60 minutes)
- [ ] Instructional time is reasonable (200-500 minutes)
- [ ] Year matches target year (2023-24)
- [ ] Source URL is documented
- [ ] Confidence level is appropriate

**Confidence Level Assignment:**

| Level | Criteria |
|-------|----------|
| **high** | District-wide policy OR 3+ schools sampled with <15 min variation |
| **medium** | 2 schools sampled OR single school with full schedule details |
| **low** | Single school partial info OR estimated from school hours |
| **assumed** | State statutory requirements used |

**Save Enrichment Record:**
```python
import json
from datetime import datetime

enrichment = {
    "district_id": "XXXXXXX",
    "district_name": "District Name",
    "state": "XX",
    "year": "2023-24",
    "fetch_date": datetime.now().strftime("%Y-%m-%d"),
    "tier": 1,
    "elementary": {
        "instructional_minutes": 345,
        "start_time": "8:00 AM",
        "end_time": "2:45 PM",
        "lunch_duration": 30,
        "schools_sampled": ["School Name"],
        "source_urls": ["https://..."],
        "confidence": "medium",
        "method": "school_website",
        "notes": "Elementary specific schedule found"
    },
    # ... middle and high levels
}

with open(f'data/enriched/bell-schedules/{district_id}_2023-24.json', 'w') as f:
    json.dump(enrichment, f, indent=2)
```

---

## Troubleshooting Decision Trees

### Decision Tree 1: Image Processing

```
Image file found
  ├─→ Download with curl to /tmp/
  ├─→ Verify download: ls -lh /tmp/file.png
  ├─→ Run tesseract: tesseract /tmp/file.png stdout
  │
  ├─→ [SUCCESS] Text extracted
  │   └─→ Parse times and calculate minutes
  │
  └─→ [FAILURE] Poor OCR quality
      ├─→ Try: convert -resize 200% /tmp/file.png /tmp/large.png
      ├─→ Run: tesseract /tmp/large.png stdout
      │
      ├─→ [SUCCESS] Better quality
      │   └─→ Parse and continue
      │
      └─→ [FAILURE] Still poor
          ├─→ Check if rotated: view image or try -rotate 90
          ├─→ If still bad → Note in manual follow-up
          └─→ Estimate from school hours if available
```

### Decision Tree 2: PDF Processing

```
PDF file found
  ├─→ Download with curl to /tmp/
  ├─→ Try: pdftotext /tmp/file.pdf /tmp/output.txt
  ├─→ Check: cat /tmp/output.txt
  │
  ├─→ [SUCCESS] Text extracted
  │   └─→ Parse times and calculate minutes
  │
  └─→ [FAILURE] Empty or garbled output
      ├─→ PDF is image-based
      ├─→ Try: ocrmypdf /tmp/file.pdf /tmp/ocr.pdf
      ├─→ Then: pdftotext /tmp/ocr.pdf /tmp/output.txt
      │
      ├─→ [SUCCESS] Text extracted
      │   └─→ Parse and continue
      │
      └─→ [FAILURE] OCR failed
          ├─→ Convert to images: convert -density 300 file.pdf page-%03d.png
          ├─→ OCR each page: tesseract page-001.png stdout
          └─→ If all fail → Manual follow-up
```

### Decision Tree 3: Security Block Encountered

```
Web request returns error
  ├─→ Cloudflare error (1016, 1020)?
  ├─→ WAF 403 Forbidden?
  ├─→ 4+ 404 errors in single district (e.g., 1 district site + 3 school sites)?
  │
  └─→ [YES to any]
      ├─→ Do NOT attempt workarounds
      ├─→ Do NOT create statutory fallback
      ├─→ Add to manual_followup_needed.json:
      │   {
      │     "district_id": "...",
      │     "reason": "Automated collection failed - 4+ 404 errors",
      │     "block_type": "Cloudflare|WAF|404s",
      │     "total_404s": N,
      │     "urls_tried": ["url1", "url2", ...],
      │     "suggested_action": "Manual collection needed"
      │   }
      └─→ Move to next district immediately

CRITICAL RULE: 4+ 404s indicates hardened cybersecurity, NOT missing pages.
Do NOT fall back to statutory requirements - statutory ≠ enriched.
See ENRICHMENT_SAFEGUARDS.md for detailed implementation.
```

### Decision Tree 4: No Bell Schedule Found

```
Search completed, no schedules found
  ├─→ Attempted district-wide search? [Y/N]
  ├─→ Attempted school-level search? [Y/N]
  ├─→ Checked for PDF handbooks? [Y/N]
  │
  └─→ After ONE search attempt per level:
      ├─→ No accessible schedules found
      ├─→ Fall back to state statutory requirements
      ├─→ Save enrichment with:
      │   - confidence: "assumed"
      │   - method: "state_statutory"
      │   - notes: "No public schedules found, using state minimum"
      └─→ Move to next district
```

---

## Common Failure Modes and Solutions

### Failure Mode 1: API Image Processing Error

**Symptom:** `Read` tool returns "Could not process image" error

**Root Cause:** API limitation or image format incompatibility

**Solution:**
1. **DO NOT retry Read tool**
2. **Immediately switch to local processing:**
   ```bash
   curl -o /tmp/schedule.png "URL"
   tesseract /tmp/schedule.png stdout
   ```
3. **Update procedure:** Always use local OCR first

**Prevention:** Never use Read tool for images; always use tesseract

### Failure Mode 2: Empty PDF Extraction

**Symptom:** `pdftotext` produces empty output

**Root Cause:** PDF contains images of text, not actual text

**Solution:**
```bash
# Detect if PDF is image-based
pdffonts file.pdf  # If "no fonts", it's image-based

# Apply OCR
ocrmypdf file.pdf file_ocr.pdf
pdftotext file_ocr.pdf output.txt
```

**Prevention:** Always check `pdftotext` output before assuming success

### Failure Mode 3: Session Stall on Retry Loop

**Symptom:** Same command retried multiple times without changing approach

**Root Cause:** No fallback strategy encoded

**Solution:**
1. **Recognize failure after ONE attempt**
2. **Consult decision tree** for next step
3. **Switch approach** - don't retry same method
4. **Set limit:** Max 2-3 different approaches before manual follow-up

**Prevention:** Follow decision trees strictly; they encode max attempts

### Failure Mode 4: Forgetting Available Tools

**Symptom:** Using suboptimal approach when better tool exists

**Root Cause:** Tools not in active context/memory

**Solution:**
1. **Check "Available Tools Inventory"** section (top of this doc)
2. **Prioritize local processing** over API calls
3. **Use this checklist before any data extraction:**
   - [ ] Is it an image? → Use tesseract
   - [ ] Is it a PDF? → Use pdftotext/ocrmypdf
   - [ ] Is it HTML? → Use curl + pup/grep
   - [ ] Need web search? → Use WebSearch
   - [ ] Need content analysis? → Use WebFetch

**Prevention:** Reference this guide at start of each enrichment session

---

## Token Efficiency Best Practices

### 1. Download Once, Process Locally Multiple Times

**Inefficient:**
```
WebFetch(url) → Process → Fail
WebFetch(url) → Process differently → Fail
WebFetch(url) → Process again → Success
```
**Cost:** 3x API calls, 3x tokens

**Efficient:**
```bash
curl -o /tmp/file.html url
# Try multiple local processing approaches
pup 'selector' < /tmp/file.html
grep 'pattern' /tmp/file.html
sed 's/old/new/' /tmp/file.html
```
**Cost:** 1 download, unlimited local retries, minimal tokens

### 2. Batch Text Extraction

**Inefficient:**
```python
# Multiple small reads
Read(file, offset=0, limit=100)
Read(file, offset=100, limit=100)
Read(file, offset=200, limit=100)
```

**Efficient:**
```bash
# Single local operation
cat /tmp/file.txt | grep -A 20 "Bell Schedule"
```

### 3. Use Slim Files When Available

For NCES data processing:
- **Use:** `data/processed/slim/` versions (88% smaller)
- **Avoid:** `data/raw/federal/` versions unless specifically needed

### 4. Cache Intermediate Results

```bash
# Save search results
curl "https://district.org/schedules" > /tmp/schedules.html

# Now can grep, pup, sed multiple times without re-fetching
grep "Elementary" /tmp/schedules.html
pup 'table' < /tmp/schedules.html
```

---

## Workflow Checklists

### Checklist: Starting New District Enrichment

- [ ] Check if district already enriched: `ls data/enriched/bell-schedules/{district_id}_*.json`
- [ ] Verify grade levels served: Check enrollment data
- [ ] Review this operations guide: Refresh on tools and procedures
- [ ] Prepare temp directory: `/tmp/` for downloads
- [ ] Begin with WebSearch for district-wide bell schedule
- [ ] Follow SOP 1 (Bell Schedule Discovery)

### Checklist: Processing Image-Based Schedule

- [ ] URL identified for image
- [ ] Downloaded with curl to /tmp/
- [ ] Verified file with `ls -lh` and `file`
- [ ] Extracted text with tesseract
- [ ] Validated extracted text quality
- [ ] Parsed times and calculated minutes
- [ ] If failed: Tried resize/rotate/convert approaches
- [ ] If still failed: Added to manual follow-up
- [ ] Saved enrichment record

### Checklist: Processing PDF Schedule

- [ ] URL identified for PDF
- [ ] Downloaded with curl to /tmp/
- [ ] Attempted pdftotext first
- [ ] If empty: Applied ocrmypdf
- [ ] Validated extracted text
- [ ] Parsed times and calculated minutes
- [ ] If failed: Tried convert to images approach
- [ ] If still failed: Added to manual follow-up
- [ ] Saved enrichment record

### Checklist: Encountering Security Block

- [ ] Identified block type (Cloudflare/WAF/4+ 404s)
- [ ] Counted total 404 errors (threshold: 4+)
- [ ] Did NOT attempt multiple workarounds
- [ ] Did NOT create statutory fallback entry
- [ ] Created manual follow-up entry with:
  - [ ] District ID and name
  - [ ] Total 404 count
  - [ ] All URLs attempted
  - [ ] Block type
- [ ] Moved to next district immediately
- [ ] No more than 1 search + 1 fetch attempt per URL
- [ ] VERIFIED: No enrichment file created for this district

### Checklist: Before Marking District Complete

- [ ] Enrichment JSON saved to `data/enriched/bell-schedules/`
- [ ] All grade levels covered (elementary/middle/high as applicable)
- [ ] Confidence levels assigned appropriately
- [ ] Source URLs documented
- [ ] Method documented (district_policy/school_sample/state_statutory)
- [ ] Notes added for any unusual circumstances
- [ ] Validation checks passed
- [ ] Ready to move to next district

---

## Reference Quick Commands

### Image Processing
```bash
# Download and OCR
curl -o /tmp/schedule.png "URL" && tesseract /tmp/schedule.png stdout

# Enhance and OCR
convert -resize 200% /tmp/schedule.png /tmp/large.png
tesseract /tmp/large.png stdout

# Rotate and OCR
convert -rotate 90 /tmp/schedule.png /tmp/rotated.png
tesseract /tmp/rotated.png stdout
```

### PDF Processing
```bash
# Text-based PDF
curl -o /tmp/schedule.pdf "URL" && pdftotext /tmp/schedule.pdf - | head -50

# Image-based PDF
curl -o /tmp/schedule.pdf "URL"
ocrmypdf /tmp/schedule.pdf /tmp/schedule_ocr.pdf
pdftotext /tmp/schedule_ocr.pdf -

# PDF to images to OCR
convert -density 300 /tmp/schedule.pdf /tmp/page-%03d.png
tesseract /tmp/page-001.png stdout
```

### HTML Processing
```bash
# Download and parse with pup
curl -s "URL" | pup 'table.schedule text{}'

# Download and grep for times
curl -s "URL" | grep -E "[0-9]{1,2}:[0-9]{2}\s*(AM|PM)"

# Save then process
curl -o /tmp/page.html "URL"
pup 'div#schedule' < /tmp/page.html
grep "Elementary" /tmp/page.html
```

### Validation
```bash
# Check if district already enriched
ls -lh data/enriched/bell-schedules/ | grep {district_id}

# Verify grade level enrollment
python3 << 'EOF'
import pandas as pd
df = pd.read_csv('data/enriched/lct-calculations/districts_2023_24_with_grade_levels_enriched_with_lct_valid.csv')
print(df[df['district_id'] == 'XXXXXXX'][['district_name', 'enrollment_elementary', 'enrollment_middle', 'enrollment_high']])
EOF
```

---

## Integration with Existing Documentation

This operations guide complements:

1. **`QUICK_REFERENCE_BELL_SCHEDULES.md`** - One-page cheat sheet
   - Quick commands and decision trees
   - Use this for fast reference during enrichment
   - This guide provides the full details

2. **`ENRICHMENT_SAFEGUARDS.md`** - ⭐ CRITICAL safeguards
   - 404 detection and auto-flagging rules
   - Statutory vs enriched data separation
   - Manual follow-up workflow
   - **READ THIS FIRST** to prevent silent failures

3. **`BELL_SCHEDULE_SAMPLING_METHODOLOGY.md`** - Defines WHAT to collect and WHY
   - This guide defines HOW to collect it operationally

4. **`METHODOLOGY.md`** - Overall LCT calculation methodology
   - This guide focuses on data acquisition procedures

5. **`fetch_bell_schedules.py`** - Automation script
   - This guide provides manual procedures and troubleshooting

6. **`CLAUDE.md`** - Project overview
   - This guide provides detailed operational procedures

**When to use each:**
- Quick command lookup → QUICK_REFERENCE_BELL_SCHEDULES.md
- **Critical safeguards** → **ENRICHMENT_SAFEGUARDS.md** ⭐
- Planning approach → BELL_SCHEDULE_SAMPLING_METHODOLOGY.md
- Understanding LCT → METHODOLOGY.md
- Automated processing → fetch_bell_schedules.py
- Manual enrichment → **This guide**
- Project overview → CLAUDE.md

---

## Continuous Improvement

### Logging Lessons Learned

When encountering new failure modes or finding better approaches:

1. **Document immediately** in this guide
2. **Add to decision trees** if it's a branch point
3. **Update checklists** if it's a common step
4. **Share in session handoff** for continuity

### Updating This Guide

This is a living document. Update it when:
- New tools are installed
- New failure modes discovered
- Better approaches identified
- Token efficiency improvements found
- Process optimizations realized

**Format for updates:**
```markdown
## Update Log

### [Date] - [Brief Description]
**Updated Section:** [Section name]
**Change:** [What changed]
**Reason:** [Why it changed]
**Impact:** [How it improves operations]
```

---

## Version History

### Version 1.2 - December 26, 2025
**Status:** Empirical insights and metrics update

**Changes:**
- Added "District Accessibility Patterns" section with empirical insights from 15+ state campaigns
- Documented success rate by district rank (ranks 1-3: ~44%, ranks 4-9: ~83%)
- Added pre-screening recommendations for predicting enrichment success
- Documented notable schedule patterns (four-day weeks, A/B blocks, three-tier systems)
- Added "Quality Metrics Tracking" section for per-district, per-state, and cumulative metrics
- Updated cumulative metrics (25 states completed, 104 districts, 296 schedules)

**Reason:** Analysis of Idaho, Nebraska, Mississippi, Kansas second-pass campaigns revealed clear patterns in district accessibility. These insights inform the expanded candidate pool strategy (Option A) and help predict which districts will succeed.

### Version 1.1 - December 21, 2024
**Status:** Safeguards update

**Changes:**
- Added 404 detection threshold rule (4+ errors = flag for manual follow-up)
- Updated Decision Tree 3 with explicit "Do NOT create statutory fallback" rule
- Enhanced Security Block checklist with 404 counting and verification steps
- Added reference to ENRICHMENT_SAFEGUARDS.md in integration section
- Emphasized statutory ≠ enriched data separation

**Reason:** Memphis-Shelby County near-failure where automation nearly created statutory fallback after hitting 4+ 404 errors. User intervention prevented silent failure. These updates ensure automation flags failures loudly instead of falling back silently.

### Version 1.0 - December 21, 2024
**Status:** Initial release

**Sections:**
- Available Tools Inventory
- Standard Operating Procedures (SOPs 1-5)
- Troubleshooting Decision Trees (4 trees)
- Common Failure Modes (4 modes documented)
- Token Efficiency Best Practices
- Workflow Checklists
- Reference Quick Commands
- Integration with existing docs
- Continuous improvement process

**Created in response to:** Session stall due to API image processing error. Established formal procedures to prevent future stalls by encoding tool knowledge and fallback strategies.

---

**Last Updated:** December 26, 2025
**Status:** Active operational guide
**Maintained by:** Project development sessions
**Review Frequency:** After each major enrichment campaign milestone
