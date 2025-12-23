# Enrichment Script Safeguards - Critical Rules

**Last Updated:** December 21, 2025
**Purpose:** Prevent silent failures and maintain data quality integrity

---

## Core Principle

**When automation fails, FLAG LOUDLY for manual follow-up.**
**NEVER silently fall back to statutory data and call it "enriched".**

---

## Rule 1: 404 Detection and Auto-Flagging

### Threshold for Manual Follow-up
- **4 or more 404 errors** in a single district enrichment attempt = AUTO-FLAG
- Example: 1 district website 404 + 3 school website 404s = 4 total = FLAG
- **Rationale:** Multiple 404s indicate hardened cybersecurity, not missing pages

### Implementation

```python
class HTTPErrorTracker:
    def __init__(self, threshold=4):
        self.errors_404 = []
        self.threshold = threshold

    def record_404(self, url: str):
        """Record a 404 error"""
        self.errors_404.append(url)

    def should_flag_manual_followup(self) -> bool:
        """Check if we've hit the threshold"""
        return len(self.errors_404) >= self.threshold

    def get_summary(self) -> dict:
        """Get error summary for flagging"""
        return {
            "total_404s": len(self.errors_404),
            "urls_tried": self.errors_404,
            "threshold": self.threshold,
            "flagged": self.should_flag_manual_followup()
        }
```

### Usage Pattern

```python
error_tracker = HTTPErrorTracker(threshold=4)

# Try district site
try:
    response = fetch(district_url)
except HTTP404:
    error_tracker.record_404(district_url)

# Try schools
for school_url in school_urls:
    try:
        response = fetch(school_url)
    except HTTP404:
        error_tracker.record_404(school_url)

    # Check if we should stop
    if error_tracker.should_flag_manual_followup():
        flag_for_manual_followup(district, error_tracker.get_summary())
        return None  # Do NOT create statutory fallback
```

---

## Rule 2: Statutory Fallback ≠ Enriched

### CRITICAL Distinction
**Statutory data must NEVER be counted as "enriched"**

These are different data quality tiers:
- **Enriched:** Actual bell schedules from schools/districts
- **Statutory Fallback:** State minimum requirements (NOT enriched)

### Enforcement Mechanisms

#### 1. Separate Output Directories
```
data/enriched/bell-schedules/              # Actual enriched data ONLY
data/enriched/bell-schedules/tier3_statutory_fallback/  # Statutory data
```

#### 2. Required Metadata Fields
```python
# For actual enriched data
result['data_quality_tier'] = 'enriched'
result['enriched'] = True

# For statutory fallback
result['data_quality_tier'] = 'statutory_fallback'
result['enriched'] = False
```

#### 3. Tracking File Separation
```python
# enrichment_reference.csv
district_id,district_name,enriched
4700148,Memphis-Shelby County,True   # Has actual bell schedules
1234567,Example District,False       # Only has statutory data
```

#### 4. Validation Check
```python
def save_result(result, district_id):
    if result['data_quality_tier'] == 'statutory_fallback':
        # Save to separate directory
        output_dir = 'data/enriched/bell-schedules/tier3_statutory_fallback/'
        result['enriched'] = False
    elif all(level['method'] != 'state_statutory' for level in [result['elementary'], result['middle'], result['high']]):
        # Has actual data - can be enriched
        output_dir = 'data/enriched/bell-schedules/'
        result['enriched'] = True
    else:
        raise ValueError("Mixed data quality - has both actual and statutory")
```

---

## Rule 3: Manual Follow-up Flagging

### Required Fields When Flagging

```json
{
  "district_id": "XXXXX",
  "district_name": "District Name",
  "state": "XX",
  "enrollment": 12345,
  "national_rank": 25,
  "category": "top_25",
  "reason": "Automated collection failed - multiple 404 errors",
  "attempts": [
    {
      "date": "YYYY-MM-DD",
      "method": "WebSearch + WebFetch",
      "total_404s": 4,
      "urls_tried": ["url1", "url2", "url3", "url4"]
    }
  ],
  "known_info": {},
  "next_steps": "Manual collection needed",
  "priority": "high|medium|low",
  "flagged_date": "YYYY-MM-DD"
}
```

### Auto-Flagging Function

```python
def flag_for_manual_followup(district_info, error_summary):
    """Add district to manual follow-up list"""

    followup_file = 'data/enriched/bell-schedules/manual_followup_needed.json'

    with open(followup_file, 'r') as f:
        data = json.load(f)

    entry = {
        "district_id": district_info['district_id'],
        "district_name": district_info['district_name'],
        "state": district_info['state'],
        "enrollment": district_info['enrollment'],
        "category": district_info.get('category', 'unknown'),
        "reason": f"Automated collection failed - {error_summary['total_404s']} 404 errors",
        "attempts": [{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "method": "WebSearch + WebFetch",
            "total_404s": error_summary['total_404s'],
            "urls_tried": error_summary['urls_tried']
        }],
        "next_steps": "Manual collection needed",
        "priority": "high" if district_info.get('category') == 'top_25' else "medium",
        "flagged_date": datetime.now().strftime("%Y-%m-%d")
    }

    data['districts_needing_manual_review'].append(entry)
    data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(followup_file, 'w') as f:
        json.dump(data, f, indent=2)

    logger.warning(f"Flagged {district_info['district_name']} for manual follow-up")
```

---

## Rule 4: Return Values Must Distinguish Outcomes

### Function Signature

```python
def enrich_district(district_info) -> Optional[Dict]:
    """
    Attempt to enrich district with actual bell schedule data.

    Returns:
        Dict with actual data if successful
        None if flagged for manual follow-up

    NEVER returns statutory fallback data.
    """
    error_tracker = HTTPErrorTracker()

    # Attempt enrichment
    result = attempt_web_scraping(district_info, error_tracker)

    # Check if we should flag
    if error_tracker.should_flag_manual_followup():
        flag_for_manual_followup(district_info, error_tracker.get_summary())
        return None  # STOP - do not create statutory entry

    # Check if we got actual data
    if has_actual_data(result):
        result['enriched'] = True
        result['data_quality_tier'] = 'enriched'
        return result
    else:
        # No actual data found - still flag for manual follow-up
        flag_for_manual_followup(district_info, {
            "total_404s": len(error_tracker.errors_404),
            "urls_tried": error_tracker.errors_404,
            "reason": "No bell schedule data found"
        })
        return None
```

---

## Rule 5: Pipeline Integration

### Batch Processing Must Handle None Returns

```python
stats = {'enriched': 0, 'flagged_for_manual': 0}

for district in districts:
    result = enrich_district(district)

    if result is None:
        logger.info(f"Flagged {district['name']} - continuing to next district")
        stats['flagged_for_manual'] += 1
        continue

    if result['enriched']:
        save_enriched_result(result)
        stats['enriched'] += 1
    else:
        raise ValueError(f"Unexpected: result returned but not enriched for {district['name']}")

# Report
logger.info(f"Enriched: {stats['enriched']}")
logger.info(f"Flagged for manual: {stats['flagged_for_manual']}")
logger.info(f"NOT created statutory fallback for any district")
```

---

## Summary of Required Changes

### Scripts to Update
1. `infrastructure/scripts/enrich/fetch_bell_schedules.py`
2. `infrastructure/scripts/enrich/batch_enrich_bell_schedules.py`
3. Any custom enrichment scripts

### Changes Required
1. ✅ Add HTTPErrorTracker class
2. ✅ Update enrichment functions to use error tracker
3. ✅ Enforce enriched flag separation (True = actual, False = statutory)
4. ✅ Remove automatic statutory fallback from enrichment scripts
5. ✅ Add auto-flagging to manual_followup_needed.json
6. ✅ Update return signatures to return None for failures
7. ✅ Update documentation to reflect these rules

---

## Testing Checklist

Before deploying enrichment scripts, verify:

- [ ] 404 detection triggers auto-flagging at threshold (4 errors)
- [ ] Flagged districts go to manual_followup_needed.json
- [ ] No statutory fallback files created in main enriched/ directory
- [ ] All enriched files have enriched=True in metadata
- [ ] All statutory files have enriched=False in metadata
- [ ] Batch processing handles None returns correctly
- [ ] Final reports distinguish enriched vs flagged counts

---

## Example: Memphis-Shelby County Schools

**What happened:** Automated enrichment hit 4+ 404 errors
**Correct action:** ✅ Flagged for manual follow-up
**Incorrect action:** ❌ Create statutory fallback and call it enriched

**Outcome:** User provided actual bell schedule PDF → High-quality enriched data

**Key lesson:** The user caught the automation attempting to fall back to statutory data. These safeguards prevent this from happening automatically.

---

**Last Updated:** December 21, 2025
**Status:** Active enforcement required in all enrichment scripts
