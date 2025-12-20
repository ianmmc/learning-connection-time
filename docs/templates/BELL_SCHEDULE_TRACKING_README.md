# Bell Schedule Tracking Template

## Purpose

This template is used to track the progress and results of bell schedule data collection across school districts.

## Files

### `bell_schedule_tracking_template.csv`
Main tracking spreadsheet for recording bell schedule enrichment progress.

### Column Definitions

| Column | Type | Description | Example Values |
|--------|------|-------------|----------------|
| **district_id** | Text | NCES district identifier | "0600001" |
| **district_name** | Text | Full district name | "Los Angeles Unified" |
| **state** | Text | Two-letter state code | "CA" |
| **enrollment** | Number | Total student enrollment | 430000 |
| **tier** | Number | Quality tier (1, 2, or 3) | 1 |
| **status** | Text | Current status | "pending", "in_progress", "completed", "blocked" |
| **fetch_date** | Date | When data was collected | "2025-12-19" |
| **year** | Text | School year | "2023-24" |
| **elem_minutes** | Number | Elementary instructional minutes | 360 |
| **elem_confidence** | Text | Confidence level | "high", "medium", "low", "assumed" |
| **elem_method** | Text | How data was obtained | "district_policy", "school_sample", "web_search", "state_statutory" |
| **elem_sources** | Text | Source URLs (semicolon-separated) | "https://...;https://..." |
| **elem_notes** | Text | Additional context | "K-5 only; K uses different schedule" |
| **middle_minutes** | Number | Middle school instructional minutes | 375 |
| **middle_confidence** | Text | Confidence level | "high", "medium", "low", "assumed" |
| **middle_method** | Text | How data was obtained | "district_policy", "school_sample", "web_search", "state_statutory" |
| **middle_sources** | Text | Source URLs (semicolon-separated) | "https://...;https://..." |
| **middle_notes** | Text | Additional context | "6-8 configuration" |
| **high_minutes** | Number | High school instructional minutes | 390 |
| **high_confidence** | Text | Confidence level | "high", "medium", "low", "assumed" |
| **high_method** | Text | How data was obtained | "district_policy", "school_sample", "web_search", "state_statutory" |
| **high_sources** | Text | Source URLs (semicolon-separated) | "https://...;https://..." |
| **high_notes** | Text | Additional context | "Block schedule vs. traditional" |
| **overall_notes** | Text | General notes about district | "District uses rotating schedule" |
| **researcher** | Text | Who collected the data | "Claude", "Ian", etc. |
| **review_status** | Text | Quality review status | "not_reviewed", "reviewed", "needs_revision" |

## Workflow

### 1. Initialization
Start with template containing target districts:
```bash
cp docs/templates/bell_schedule_tracking_template.csv \
   data/enriched/bell-schedules/tracking_2023_24.csv
```

### 2. Data Collection

For each district:

#### Step 1: Mark as in progress
```csv
status: "in_progress"
researcher: "Your Name"
```

#### Step 2: Search for schedules
Follow methodology in `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md`

#### Step 3: Record findings
Fill in all relevant fields:
- Minutes for each level
- Confidence ratings
- Methods used
- Source URLs
- Notes

#### Step 4: Mark as completed
```csv
status: "completed"
fetch_date: "2025-12-19"
```

### 3. Quality Review

Second person reviews:
```csv
review_status: "reviewed"  # or "needs_revision"
```

### 4. Export

Once complete, export to enriched data format:
```bash
python infrastructure/scripts/enrich/fetch_bell_schedules.py \
  --import tracking_2023_24.csv
```

## Status Values

| Status | Meaning |
|--------|---------|
| **pending** | Not started |
| **in_progress** | Currently being researched |
| **completed** | Data collection complete |
| **blocked** | Cannot find data, needs escalation |
| **skipped** | Intentionally skipped (using Tier 3) |

## Confidence Values

| Confidence | Meaning |
|-----------|---------|
| **high** | District policy or 3+ schools sampled, low variation |
| **medium** | 2 schools sampled or automated search successful |
| **low** | Single school or high variation |
| **assumed** | Using state statutory requirements |

## Method Values

| Method | Description |
|--------|-------------|
| **district_policy** | Found district-wide bell schedule policy |
| **school_sample** | Sampled individual school schedules |
| **web_search** | Automated web search found schedule |
| **state_statutory** | Fell back to state requirements |
| **manual_entry** | Manually entered from offline source |

## Example Entry

### Complete District Entry
```csv
0600001,Los Angeles Unified,CA,430000,1,completed,2025-12-19,2023-24,360,high,school_sample,https://school1.com/schedule;https://school2.com/schedule,Sampled 3 elementary schools in different regions,375,high,school_sample,https://middle1.com;https://middle2.com,6-8 configuration across all middle schools,390,medium,school_sample,https://high1.com;https://high2.com,Some variation due to block vs traditional,District has consistent approach across levels,Claude,reviewed
```

### In-Progress Entry
```csv
3600001,New York City DOE,NY,900000,1,in_progress,,,,,,,,,,,,,,,,,Researching district-wide policy,Ian,not_reviewed
```

### Blocked Entry
```csv
4800001,Example District,TX,50000,2,blocked,,,,,,,,,,,,,,,,,Website down; no cached schedules found,Claude,needs_revision
```

## Tips for Data Entry

### 1. Source URLs
- Use full URLs, not shortened links
- Separate multiple sources with semicolons
- Include page-specific URLs, not just homepage
- Archive URLs if possible (web.archive.org)

### 2. Notes
- Be specific and concise
- Note any anomalies or special cases
- Document assumptions made
- Flag anything needing follow-up

### 3. Confidence Assignment
- Be conservative - when in doubt, use lower confidence
- Document reasoning in notes
- High variation = lower confidence
- Single source = lower confidence

### 4. Quality Checks
Before marking "completed":
- ✓ All required fields filled
- ✓ Minutes are reasonable (200-500 range)
- ✓ Source URLs are accessible
- ✓ Confidence matches method used
- ✓ Notes explain any anomalies

## Reporting

### Progress Summary

Use spreadsheet to track:
- Total districts: Count all rows
- Completed: Count where `status="completed"`
- In progress: Count where `status="in_progress"`
- Blocked: Count where `status="blocked"`

### Quality Summary

- High confidence: Count where any level has `confidence="high"`
- Medium confidence: Count where any level has `confidence="medium"`
- Low confidence: Count where any level has `confidence="low"`
- Assumed: Count where all levels have `confidence="assumed"`

### Coverage by Tier

- Tier 1 completed: Count where `tier=1 AND status="completed"`
- Tier 2 completed: Count where `tier=2 AND status="completed"`
- Tier 3 completed: Count where `tier=3 AND status="completed"`

## Integration with Pipeline

The tracking spreadsheet can be used in two ways:

### 1. Manual Mode
Manually research and fill in the spreadsheet, then import:
```bash
python infrastructure/scripts/enrich/import_tracking_spreadsheet.py \
  tracking_2023_24.csv
```

### 2. Automated Mode
Pipeline updates the spreadsheet as it runs:
```bash
python infrastructure/scripts/enrich/fetch_bell_schedules.py \
  districts.csv \
  --tracking tracking_2023_24.csv
```

## Version Control

- Keep tracking spreadsheet in version control
- Commit after each batch of districts completed
- Use meaningful commit messages:
  - "Add bell schedules for top 10 CA districts"
  - "Complete Tier 1 districts for TX"

## Backup

- Regular backups to Google Sheets or similar
- Export to CSV daily during active collection
- Keep offline copies of source documents

---

**Template Version**: 1.0
**Last Updated**: 2025-12-19
**Related**: `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md`
