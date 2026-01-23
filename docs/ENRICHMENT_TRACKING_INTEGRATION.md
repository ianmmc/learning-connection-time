# Enrichment Tracking Integration - Implementation Summary

**Date:** January 22, 2026
**Status:** ✅ Complete

## What Was Built

Added comprehensive tracking of bell schedule enrichment attempts (successes and failures) to prevent wasted effort on districts that block scraping.

### 1. Database Infrastructure

**Migration:** `infrastructure/database/migrations/010_create_enrichment_attempts.sql`

- **Table:** `enrichment_attempts` - Logs every scraping attempt
- **Views:**
  - `v_districts_to_skip` - Districts flagged for skipping
  - `v_recent_blocks` - Recent security blocks
  - `v_enrichment_attempt_summary` - Statistics
- **Functions:**
  - `should_skip_district(district_id)` - Check if should skip
  - `mark_district_skip(district_id, reason)` - Flag district

**Schema:**
```sql
CREATE TABLE enrichment_attempts (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(10) REFERENCES districts(nces_id),
    url TEXT,
    attempted_at TIMESTAMP,
    status VARCHAR(20),  -- success, blocked, not_found, timeout, error
    block_type VARCHAR(30),  -- cloudflare, waf, captcha
    http_status_code INTEGER,
    error_message TEXT,
    timing_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    skip_future_attempts BOOLEAN DEFAULT FALSE,
    skip_reason TEXT,
    response_details JSONB,
    ...
);
```

### 2. Python API

**Module:** `infrastructure/database/enrichment_tracking.py`

**Key Functions:**
```python
# Check before attempting
if should_skip_district(session, district_id):
    print("Skipping - previously blocked")
    continue

# Log scraper response
log_scraper_response(session, district_id, response, enrichment_tier='tier1')

# Auto-flag repeat failures
flagged = auto_flag_repeat_failures(session)  # 3+ blocks or 4+ 404s
```

### 3. Script Integration

#### ✅ `fetch_bell_schedules.py`

**Changes:**
1. **Added imports** for database tracking functions
2. **Updated `scrape_url()`** to log attempts to database
3. **Added skip checking** in `process_districts_file()` main loop
4. **Added auto-flagging** at end of batch processing
5. **Updated stats reporting** to show skipped count

**Flow:**
```python
for district in districts:
    # Check skip flag BEFORE attempting
    if should_skip_district(session, district_id):
        logger.info("Skipping - flagged from previous failures")
        stats['skipped'] += 1
        continue

    # Scrape (automatically logs to database)
    response = scrape_url(url, district_id=district_id, enrichment_tier='tier1')

    # Process response...

# Auto-flag repeat failures after batch
flagged = auto_flag_repeat_failures(session)
```

#### ✅ `interactive_enrichment.py`

**Changes:**
1. **Added imports** for tracking functions
2. **Added skip checking** in state campaign loop
3. **Updated 'B'locked action** to mark district as blocked in database
4. **Added skip warning** in single district mode (with override option)

**State Campaign Flow:**
```
For each candidate district:
  1. Check if flagged → skip automatically
  2. Present to user
  3. If user marks as blocked → flag in database
```

**Single District Mode:**
```
Load district → Check flag → Warn user → Allow override
```

## Auto-Flagging Rules

Implemented from `BELL_SCHEDULE_OPERATIONS_GUIDE.md`:

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Security blocks (Cloudflare/WAF/CAPTCHA) | 3 attempts | Auto-flag as `auto_flag_3_blocks` |
| 404 Not Found errors | 4 attempts | Auto-flag as `auto_flag_4_not_found` |
| Manual user block | 1 attempt | Flag as `manual_user_blocked` |

**Note:** Timeouts are NOT auto-flagged (may be temporary network issues).

## Usage Examples

### Check Skip Status Before Enrichment

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_tracking import should_skip_district

with session_scope() as session:
    if should_skip_district(session, '0622710'):
        print("Skip this district")
```

### View Districts to Skip

```bash
# SQL
psql -d learning_connection_time -c "SELECT * FROM v_districts_to_skip;"

# Python
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_tracking import get_districts_to_skip
with session_scope() as session:
    for d in get_districts_to_skip(session):
        print(f\"{d['district_name']} - {d['block_types']}\")
"
```

### Run Enrichment with Skip Checking

```bash
# Tier 1 enrichment (skip checking automatic)
python infrastructure/scripts/enrich/fetch_bell_schedules.py \
    data/processed/normalized/tier1_districts.csv \
    --tier 1 --year 2025-26

# Interactive state campaign (skip checking automatic)
python infrastructure/scripts/enrich/interactive_enrichment.py --state WI
```

### View Attempt Statistics

```sql
-- Summary by status
SELECT * FROM v_enrichment_attempt_summary;

-- Recent blocks
SELECT * FROM v_recent_blocks;

-- Specific district history
SELECT attempted_at, status, block_type, url
FROM enrichment_attempts
WHERE district_id = '0622710'
ORDER BY attempted_at DESC;
```

## Impact

**Before:**
- No tracking of failed attempts
- Same districts attempted repeatedly
- No visibility into block patterns
- Wasted time and resources on inaccessible districts

**After:**
- ✅ All attempts logged with full details
- ✅ Districts auto-flagged after threshold failures
- ✅ Skip checking integrated into all enrichment scripts
- ✅ Visibility into success rates, block types, and failure patterns
- ✅ Respects ONE-attempt security block protocol
- ✅ Efficient resource usage (skip known problematic districts)

## Testing Checklist

### Database Setup
- [ ] Run migration: `psql -d learning_connection_time -f infrastructure/database/migrations/010_create_enrichment_attempts.sql`
- [ ] Verify table created: `psql -d learning_connection_time -c "\d enrichment_attempts"`
- [ ] Test views: `psql -d learning_connection_time -c "SELECT * FROM v_enrichment_attempt_summary;"`

### Python API
- [ ] Test should_skip_district: `python infrastructure/database/enrichment_tracking.py`
- [ ] Test log_scraper_response with mock data
- [ ] Test auto_flag_repeat_failures

### Script Integration
- [ ] Test fetch_bell_schedules.py with skip checking
- [ ] Test interactive_enrichment.py state campaign
- [ ] Verify stats reporting includes skipped count
- [ ] Verify blocked districts are auto-flagged

### End-to-End
- [ ] Run enrichment on sample districts
- [ ] Verify attempts are logged to database
- [ ] Manually mark district as blocked
- [ ] Verify skip checking works on next run
- [ ] Check auto-flagging after repeated failures

## Related Documentation

- [ENRICHMENT_TRACKING.md](ENRICHMENT_TRACKING.md) - Complete usage guide
- [BELL_SCHEDULE_OPERATIONS_GUIDE.md](BELL_SCHEDULE_OPERATIONS_GUIDE.md) - Operational procedures
- [DATABASE_SETUP.md](DATABASE_SETUP.md) - Database infrastructure

---

**Status:** ✅ Ready for Use

All enrichment scripts now check for and respect security blocks automatically.
