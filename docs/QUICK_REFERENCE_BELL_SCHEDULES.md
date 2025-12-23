# Bell Schedule Enrichment - Quick Reference Card

**READ FIRST:** `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md` for complete procedures

---

## Tool Priority: Local > Remote

**ALWAYS prioritize local file processing over API calls**

### Image Processing
```bash
# CORRECT (local OCR)
curl -o /tmp/schedule.png "URL"
tesseract /tmp/schedule.png stdout

# WRONG (API call, prone to errors)
Read(/tmp/schedule.png)  # Use this only as last resort
```

### PDF Processing
```bash
# Text-based PDF
curl -o /tmp/schedule.pdf "URL"
pdftotext /tmp/schedule.pdf -

# Image-based PDF
ocrmypdf /tmp/schedule.pdf /tmp/ocr.pdf
pdftotext /tmp/ocr.pdf -
```

### HTML Processing
```bash
# Download once, process locally many times
curl -o /tmp/page.html "URL"
pup 'table.schedule' < /tmp/page.html
grep -E "[0-9]{1,2}:[0-9]{2}" /tmp/page.html
```

---

## Standard Workflow

1. **Search**: WebSearch for bell schedule
2. **Evaluate**: Check for security blocks (ONE attempt rule)
3. **Download**: curl to /tmp/
4. **Process Locally**: tesseract/pdftotext/pup
5. **Validate**: Check times, calculate minutes
6. **Save**: JSON to data/enriched/bell-schedules/

---

## Security Block Protocol

**ONE attempt rule:**
- 1 search + 1 fetch
- If Cloudflare/WAF/404s → Add to manual_followup_needed.json
- Move to next district immediately
- NO workarounds

---

## Common Failure Modes

| Problem | Solution |
|---------|----------|
| Read tool image error | Use tesseract instead |
| Empty pdftotext output | PDF is image-based, use ocrmypdf |
| Session stall on retry | Check decision tree, switch approach |
| Forgot available tools | Review tool inventory in ops guide |

---

## Pre-Enrichment Checklist

- [ ] Read BELL_SCHEDULE_OPERATIONS_GUIDE.md
- [ ] Check if district already enriched
- [ ] Verify grade levels served
- [ ] Prepare /tmp/ for downloads
- [ ] Review decision trees for obstacles

---

## Tools Installed

- `tesseract` - OCR for images
- `pdftotext` - Extract text from PDFs
- `ocrmypdf` - OCR image-based PDFs
- `convert` - ImageMagick image processing
- `pup` - HTML CSS selector parsing
- `curl` - Download files

---

## Decision Tree: Image Found

```
Image URL found
  → curl -o /tmp/img.png URL
  → tesseract /tmp/img.png stdout
    ├─ [Success] → Parse times
    └─ [Fail] → convert -resize 200% → tesseract again
                └─ [Still fail] → Manual follow-up
```

---

## Quick Commands

```bash
# Enhanced image OCR
convert -resize 200% /tmp/schedule.png /tmp/large.png
tesseract /tmp/large.png stdout

# PDF to text with OCR
ocrmypdf /tmp/schedule.pdf /tmp/ocr.pdf && pdftotext /tmp/ocr.pdf -

# Check if district enriched
ls data/enriched/bell-schedules/ | grep {district_id}

# Verify grade levels
python3 << 'EOF'
import pandas as pd
df = pd.read_csv('data/enriched/lct-calculations/districts_2023_24_with_grade_levels_enriched_with_lct_valid.csv')
print(df[df['district_id'] == 'XXXXXXX'][['enrollment_elementary', 'enrollment_middle', 'enrollment_high']])
EOF
```

---

**Full Documentation:** `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md`
**Methodology:** `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md`
**Last Updated:** December 21, 2024
