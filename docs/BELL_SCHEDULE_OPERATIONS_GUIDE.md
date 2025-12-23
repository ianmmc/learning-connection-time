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

## Standard Operating Procedures

### SOP 1: Bell Schedule Discovery

**Objective:** Find bell schedule information for a district

**Steps:**
1. **Web Search** for district bell schedule
   ```
   WebSearch("[District Name] bell schedule [year]")
   WebSearch("[District Name] [School Name] daily schedule")
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

**Last Updated:** December 21, 2024
**Status:** Active operational guide
**Maintained by:** Project development sessions
**Review Frequency:** After each major enrichment campaign milestone
