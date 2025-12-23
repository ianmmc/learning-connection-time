# Project Terminology Guide

**Last Updated:** December 21, 2024

This document standardizes vocabulary used throughout the Learning Connection Time project to prevent confusion between human and AI collaboration.

---

## Data Collection Methods

### Human-Provided Data
**Definition:** Data manually collected by human team members and placed in `data/raw/manual_import_files/`

**Examples:**
- PDFs downloaded by user when Claude encountered access blocks
- Data compiled by user using external tools (Gemini, ChatGPT)
- Documents obtained through official requests or non-public sources

**Indicators in data:**
- Source URLs contain "manual_import:" prefix
- Files located in `data/raw/manual_import_files/`
- Method field may show `manual_data_collection` or `human_provided`

### Automated Enrichment
**Definition:** Data collected by Claude Code through web scraping, PDF extraction, or API calls

**Examples:**
- Bell schedules scraped from district websites
- PDFs downloaded and extracted with pdftotext/tesseract
- HTML pages fetched and parsed

**Indicators in data:**
- Method field shows: `web_scraping`, `pdf_extraction`, `district_policy`, `school_sample`
- Source URLs are direct web links (no "manual_import" prefix)
- Collected during Claude sessions

### Manual Intervention
**Definition:** Cases where Claude attempted automated collection but required human assistance to proceed

**Examples:**
- Cloudflare/WAF blocks preventing automated access
- CAPTCHAs or authentication requirements
- Files requiring human judgment to locate or interpret

**Process:**
1. Claude attempts automated enrichment
2. Encounters block/error
3. Adds to `manual_followup_needed.json`
4. Human provides data to `manual_import_files/`
5. Claude processes the human-provided data
6. Final JSON marked with human-provided indicators

---

## Data Quality Classifications

### Actual Bell Schedules (Enriched)
**Definition:** Bell schedule data obtained from authoritative district or school sources

**Counts as enriched:** YES ✓

**Sources:**
- District policy documents with specific times
- School websites with published schedules
- Official bell schedule PDFs/tables
- District-provided documentation

**Tier classification:**
- **Tier 1:** Manual-assisted detailed search of top districts
- **Tier 2:** Automated search with validation

**Confidence levels:**
- High: Detailed schedule with specific times from official source
- Medium: School-sampled or estimated from total time
- Low: Single school sample representing diverse district

### Statutory Fallback (NOT Enriched)
**Definition:** State minimum instructional time requirements used as default

**Counts as enriched:** NO ✗

**Characteristics:**
- Method: `state_statutory`
- Confidence: low or assumed
- Source: State education code/statute
- No specific school/district times
- Generic minutes (often 360, 420, etc.)

**Tier classification:**
- **Tier 3:** Statutory requirements only

**Storage:**
- Located in `data/enriched/bell-schedules/tier3_statutory_fallback/`
- NOT counted in enrichment campaign progress

---

## Dataset Years

### 2023-24 Data
**Current campaign focus**

**Storage:**
- Individual JSON files: `data/enriched/bell-schedules/{district_id}_2023-24.json`
- Tracking: `enrichment_reference.csv` (19,637 districts)

**Enrichment status:**
- 4 districts enriched (Wyoming campaign)
- Target: 3 per state × 51 = ~153 districts

### 2024-25 Data
**Earlier preliminary work**

**Storage:**
- Single collection file: `bell_schedules_manual_collection_2024_25.json`
- Contains 29 districts (25 largest + 4 others)

**Note:** Different year, different tracking system. Not included in current campaign counts.

---

## File Naming Conventions

### Bell Schedule Files

**Individual district (current):**
```
{district_id}_2023-24.json
Example: 5604510_2023-24.json (Natrona County SD #1)
```

**Collection file (legacy):**
```
bell_schedules_manual_collection_2024_25.json
```

**Manual follow-up tracking:**
```
manual_followup_needed.json
```

### Manual Import Files

**Structure:**
```
data/raw/manual_import_files/{District Name} ({State})/
  ├── document1.pdf
  ├── document2.pdf
  └── README.md (optional - explains what's in the files)
```

**Examples:**
```
data/raw/manual_import_files/Sweetwater School District SD1 (WY)/
  └── SchoolStartandEndTimes.pdf

data/raw/manual_import_files/Albany School District No. 1 (WY)/
  ├── Slade Elementary School.pdf
  ├── Whiting High School Bell Schedule.pdf
  └── Laramie Middle School Handbook.pdf
```

---

## Method Field Values

Used in bell schedule JSON files to indicate collection approach:

### Automated Methods (Claude-collected)
- `web_scraping` - Scraped from district/school website HTML
- `pdf_extraction` - Extracted from publicly accessible PDF
- `district_policy` - From official district policy document
- `school_sample` - Representative school(s) sampled
- `school_specific_schedules` - Individual school schedules compiled
- `district_standardized_schedule` - Uniform schedule across district
- `school_hours_with_estimation` - Total hours with estimated breakdown

### Human-Provided Methods
- `manual_data_collection` - User compiled/collected data
- `human_provided` - User obtained and provided files

### Fallback Methods (NOT enriched)
- `state_statutory` - State minimum requirements only
- `fallback_statutory` - Fallback to statutory when actual unavailable

---

## Confidence Levels

### High
- Detailed bell schedule with specific start/end times
- Official district policy document
- Comprehensive school-by-school data

### Medium
- School-sampled with reasonable representativeness
- Estimated from total time with documented assumptions
- News sources or secondary documentation

### Low
- Single school representing large diverse district
- Significant estimation required
- Outdated schedules used as proxy

### Assumed
- Statutory requirements only
- No actual bell schedule data
- Pure estimation

---

## Enrichment Campaign Terminology

### Target Districts
Districts identified for enrichment in the 2023-24 campaign

**Selection criteria:**
- Population-based state ordering (ascending)
- 3 districts per state
- Minimum enrollment thresholds
- Grade level diversity (K-12 coverage)

### Enrichment Status

**Enriched:** District has actual bell schedule data (NOT statutory fallback)

**Pending:** Not yet attempted or in progress

**Manual follow-up:** Attempted but requires human intervention
- Stored in `manual_followup_needed.json`
- Reasons: access blocks, no public schedules, technical issues

**Completed manual collections:** Previously in manual follow-up, now resolved

---

## Common Phrases - Standardized Usage

### "We enriched this district"
**Means:** Obtained actual bell schedule data (Tier 1 or 2)
**Does NOT mean:** Applied statutory fallback

### "Manual collection"
**Means:** Human-provided data in manual_import_files/
**Context matters:** Check if referring to human-provided vs manual intervention

### "Scraped the data"
**Means:** Automated web scraping by Claude
**Does NOT mean:** Human collected

### "Statutory fallback"
**Means:** Using state minimum requirements (NOT enriched)
**Alternative terms:** Tier 3, state statutory, assumed data

---

## Questions to Ask When Unclear

1. **Who collected this data?**
   - Human → human-provided
   - Claude → automated enrichment

2. **What's the source?**
   - manual_import_files/ → human-provided
   - Web URL → automated enrichment
   - State statute → statutory fallback

3. **Does it count as enriched?**
   - Actual bell schedules → YES
   - Statutory fallback → NO

4. **What year is this for?**
   - 2023-24 → current campaign
   - 2024-25 → earlier work

5. **Where is it stored?**
   - Individual JSON → 2023-24 campaign
   - Collection file → 2024-25 legacy
   - tier3_statutory_fallback/ → NOT enriched

---

## Examples of Correct Usage

✓ "We have 4 Wyoming districts enriched with actual bell schedules in the 2023-24 dataset."

✓ "Broward County required human-provided data because Claude encountered Cloudflare blocks."

✓ "The manual collection file contains 29 districts from 2024-25 preliminary work."

✓ "This district uses statutory fallback, so it doesn't count as enriched."

✗ "We manually collected 135 districts." (These are statutory fallback, NOT enriched)

✗ "Manual enrichment for Los Angeles." (Unclear if human-provided or manual intervention)

---

**Summary:** When in doubt, be specific about WHO collected the data (human vs Claude) and WHAT quality it represents (actual vs statutory).
