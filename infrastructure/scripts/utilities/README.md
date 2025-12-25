# Utility Scripts for Bell Schedule Enrichment

This directory contains utility scripts that streamline the manual bell schedule collection and enrichment process.

## 🎯 Quick Start

**Complete workflow for a new state:**

```bash
# 1. Find top districts
python3 district_lookup.py --top 3 --state ND

# 2. Generate template
python3 template_generator.py --ids 3800014,3819410,3806780 --year 2024-25 -o nd_template.json

# 3. Collect files manually from district websites
# Save to: data/raw/manual_import_files/North Dakota/[District Name]/

# 4. Convert files to text
python3 batch_convert.py "data/raw/manual_import_files/North Dakota/Bismarck/" -v

# 5. Extract data, fill template (manual step)

# 6. Validate before merging
python3 validate_bell_data.py nd_filled.json

# 7. Merge into consolidated file
```

---

## 📚 Tool Reference

### 1. district_lookup.py

**Purpose:** Quick lookup of district metadata (ID, name, enrollment) for bell schedule enrichment.

**Common Usage:**

```bash
# Find top N districts in a state
python3 district_lookup.py --top 3 --state ND

# Look up by name
python3 district_lookup.py "BISMARCK 1" ND

# Look up by ID
python3 district_lookup.py --id 3800014

# Search for districts containing a term
python3 district_lookup.py --search "County" --state AL

# Batch lookup from file
python3 district_lookup.py --file districts.txt
```

**File format for batch lookup** (`districts.txt`):
```
BISMARCK 1, ND
WEST FARGO 6, ND
FARGO 1, ND
```

**Output:**
```
ID: 3800014
Name: BISMARCK 1
State: ND
Enrollment: 13,743
```

---

### 2. template_generator.py

**Purpose:** Generate pre-filled JSON templates for manual bell schedule data entry.

**Common Usage:**

```bash
# Single district by ID
python3 template_generator.py --id 3800014 --year 2024-25

# Multiple districts by ID
python3 template_generator.py --ids 3800014,3819410,3806780 --year 2024-25 -o nd.json

# By name
python3 template_generator.py --name "BISMARCK 1" --state ND --year 2024-25

# From file
python3 template_generator.py --file districts.txt --year 2024-25 -o output.json
```

**Output structure:**

```json
{
  "3800014": {
    "district_id": "3800014",
    "district_name": "BISMARCK 1",
    "state": "ND",
    "year": "2024-25",
    "elementary": {
      "instructional_minutes": null,
      "start_time": "",
      "end_time": "",
      "lunch_duration": null,
      "passing_periods": null,
      "schools_sampled": [],
      "source_urls": [],
      "confidence": "",
      "method": "human_provided",
      "source": ""
    },
    "middle": { ... },
    "high": { ... },
    "enriched": true,
    "_comment_enrollment": "13,743 students"
  }
}
```

---

### 3. batch_convert.py

**Purpose:** Batch convert PDFs and HTML files to text for easier data extraction.

**Common Usage:**

```bash
# Convert all files in a directory
python3 batch_convert.py "data/raw/manual_import_files/Alabama/Baldwin County/" -v

# Specify output directory
python3 batch_convert.py input_dir/ -o output_dir/

# Convert only PDFs
python3 batch_convert.py input_dir/ --pdf-only

# Convert only HTML
python3 batch_convert.py input_dir/ --html-only
```

**What it does:**
- Converts PDFs using `pdftotext -layout`
- Converts HTML using `html2text -nobs -ascii`
- Lists image files (PNGs, JPGs) for manual review
- Saves converted files to `input_dir/converted/` by default

**Output:**
```
Processing 2 PDF files...
✓ Converted PDF: elementary_schedule.pdf
✓ Converted PDF: middle_school_times.pdf

Processing 1 HTML files...
✓ Converted HTML: district_bell_times.html

Found 3 image files (require manual review):
  - high_school_schedule.png
  - block_schedule.jpg
  - bell_times.jpeg

✓ Total files converted: 3
✓ Output saved to: .../converted/
```

---

### 4. validate_bell_data.py

**Purpose:** Validate extracted bell schedule data before merging into consolidated file.

**Common Usage:**

```bash
# Validate a JSON file
python3 validate_bell_data.py new_districts.json

# Strict mode (warnings become errors)
python3 validate_bell_data.py new_districts.json --strict

# Save validation report
python3 validate_bell_data.py new_districts.json --report report.txt
```

**Validation checks:**
- Required fields present
- Instructional minutes in valid range (180-480)
- Start/end time format correct (e.g., "8:00 AM")
- Valid confidence levels (high, medium, low)
- Valid methods (human_provided, web_scraping, etc.)
- Source documentation present
- Valid state codes

**Output (with issues):**
```
============================================================
BELL SCHEDULE DATA VALIDATION REPORT
============================================================

ERRORS: 1
------------------------------------------------------------
✗ District 3800014 (BISMARCK 1) - high: instructional_minutes (520) is too high (> 480 min)

WARNINGS: 2
------------------------------------------------------------
⚠ District 3819410 (WEST FARGO 6) - elementary: Missing source documentation
⚠ District 3806780 (FARGO 1) - middle: instructional_minutes (220) seems low

============================================================
SUMMARY
============================================================
Errors: 1
Warnings: 2

❌ VALIDATION FAILED - Fix errors before proceeding
```

**Output (no issues):**
```
============================================================
BELL SCHEDULE DATA VALIDATION REPORT
============================================================

✓ ALL CHECKS PASSED

✓ VALIDATION PASSED
```

---

## 🔧 Dependencies

**Required:**
- `pandas` - Data manipulation
- `pdftotext` - PDF extraction (install: `brew install poppler-utils`)
- `html2text` - HTML conversion (install: `brew install html2text`)

**Optional:**
- `tesseract` - OCR for images (install: `brew install tesseract`)

**Check installation:**
```bash
# Check if tools are available
which pdftotext
which html2text

# If missing, install
brew install poppler-utils html2text
```

---

## 📊 Efficiency Gains

| Activity | Manual (Old) | Automated (New) | Savings |
|----------|--------------|-----------------|---------|
| District lookup | 5 min | 30 sec | 4.5 min |
| Template creation | 15 min | 30 sec | 14.5 min |
| File conversion | 15 min | 2 min | 13 min |
| Data validation | 10 min | 1 min | 9 min |
| **Per state (3 districts)** | **45 min** | **~15 min** | **~30 min (67%)** |

**Additional benefits:**
- **Token efficiency:** 10-15K tokens saved per state
- **Error reduction:** Validation catches issues early
- **Consistency:** Templates ensure standard structure
- **Documentation:** Source tracking automated

---

## 🎓 Complete Example: North Dakota

See `/tmp/workflow_demo.md` for a complete step-by-step example of using all tools together for North Dakota enrichment.

---

## 🎯 Design Philosophy: Human-in-the-Loop

**These tools are assistive, not autonomous.**

The template generator doesn't auto-check `manual_followup_needed.json` or skip blocked districts. This is intentional:

**Why?**
- **Flexibility:** Sometimes you want templates for manual-followup districts (you're collecting them manually)
- **Context:** You know whether to try automated first or go straight to manual
- **Decisions:** Security blocks, collection strategy, district priority - these need human judgment

**Workflow:**
1. You identify target districts (using `district_lookup.py`)
2. You decide: automated enrichment or manual collection?
3. If automated hits security blocks → you decide next steps
4. If manual collection → you use these tools
5. You validate and merge when ready

**This prevents:**
- Over-automation that makes wrong assumptions
- Complex logic that becomes brittle
- Token waste on "smart" workflows that need override anyway

**The tools save time on mechanical tasks, not strategic decisions.**

---

## 📝 Tips & Best Practices

### District Lookup
- Use `--top N --state XX` to quickly identify target districts
- Add `-v` (verbose) for additional metadata like instructional staff
- Create a `districts.txt` file for batch lookups across multiple states
- **Check `manual_followup_needed.json` manually** before deciding which districts to target

### Template Generation
- Always specify the correct `--year` (2024-25, 2025-26, etc.)
- Output to a temporary file first: `-o /tmp/state_template.json`
- Review template before filling to ensure metadata is correct

### Batch Conversion
- Use `-v` (verbose) to see which files are processed
- Check the `converted/` directory for output files
- Images listed for "manual review" require visual inspection
- PDFs with complex layouts may need manual extraction

### Data Validation
- **Always validate before merging** into consolidated file
- Use `--report report.txt` to save validation results
- Fix errors immediately - don't skip validation
- Review warnings even if they don't block validation

---

## 🐛 Troubleshooting

### "pdftotext not found"
```bash
brew install poppler-utils
```

### "html2text not found"
```bash
brew install html2text
```

### "enrichment_reference.csv not found"
Run the normalization script first:
```bash
python3 infrastructure/scripts/transform/normalize_districts.py \
  data/raw/federal/nces-ccd/2023_24/districts.csv \
  --source nces --year 2023-24
```

### Validation fails with "Invalid confidence"
Valid values: `high`, `medium`, `low` (lowercase)

### Validation fails with "Invalid method"
Valid values:
- `human_provided` (manual collection)
- `web_scraping` (automated web)
- `pdf_extraction` (automated PDF)
- `school_sample` (sampled schools)
- `district_policy` (official policy docs)
- `automated_enrichment` (general automated)
- `manual_data_collection` (manual collection)
- `state_statutory` (state requirements only)

---

## 📚 Related Documentation

- **Main scripts README:** `infrastructure/scripts/README.md`
- **Methodology:** `docs/METHODOLOGY.md`
- **Bell schedule guide:** `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md`
- **Terminology:** `docs/TERMINOLOGY.md`

---

**Last Updated:** December 24, 2025
**Tools Version:** 1.0
**Contributors:** Claude Code + User
