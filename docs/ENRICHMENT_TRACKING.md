# Enrichment Attempt Tracking

**Date:** January 22, 2026
**Status:** Active

## Overview

The `enrichment_attempts` table tracks ALL bell schedule scraping attempts (both successes and failures) to:

1. **Avoid repeated attempts** on districts that block scraping (Cloudflare, WAF, CAPTCHA)
2. **Track failure patterns** (404s, timeouts, errors)
3. **Auto-flag problematic districts** after threshold failures
4. **Provide audit trail** of enrichment operations

This implements the ONE-attempt security block protocol from [BELL_SCHEDULE_OPERATIONS_GUIDE.md](BELL_SCHEDULE_OPERATIONS_GUIDE.md).

---

## Database Setup

### 1. Run Migration

```bash
psql -d learning_connection_time -f infrastructure/database/migrations/010_create_enrichment_attempts.sql
```

This creates:
- `enrichment_attempts` table
- Helper views: `v_districts_to_skip`, `v_recent_blocks`, `v_enrichment_attempt_summary`
- Helper functions: `should_skip_district()`, `mark_district_skip()`

### 2. Verify Setup

```bash
psql -d learning_connection_time -c "SELECT COUNT(*) FROM enrichment_attempts;"
psql -d learning_connection_time -c "SELECT * FROM v_enrichment_attempt_summary;"
```

---

## Usage

### Python API

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_tracking import (
    should_skip_district,
    log_scraper_response,
    get_districts_to_skip,
    auto_flag_repeat_failures
)

# Check before attempting enrichment
with session_scope() as session:
    if should_skip_district(session, district_id='0622710'):
        print("Skipping district - previously blocked")
        continue

    # Make scraper request
    response = requests.post('http://localhost:3000/scrape',
        json={'url': 'https://lausd.org'}).json()

    # Log the attempt
    log_scraper_response(session, district_id='0622710', scraper_response=response)

    # Auto-flag districts with repeated failures
    flagged = auto_flag_repeat_failures(session)
    print(f"Auto-flagged {flagged} districts")
```

### Command-Line Utilities

```bash
# View districts to skip
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_tracking import get_districts_to_skip
with session_scope() as session:
    for d in get_districts_to_skip(session):
        print(f\"{d['district_name']} ({d['state']}) - {d['block_types']}\")
"

# View recent blocks
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_tracking import get_recent_blocks
with session_scope() as session:
    for b in get_recent_blocks(session, days=7):
        print(f\"{b['attempted_at']}: {b['district_name']} - {b['block_type']}\")
"

# Run auto-flagging
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_tracking import auto_flag_repeat_failures
with session_scope() as session:
    count = auto_flag_repeat_failures(session)
    print(f'Flagged {count} districts')
"
```

### SQL Queries

```sql
-- Districts to skip
SELECT * FROM v_districts_to_skip;

-- Recent blocks (last 30 days)
SELECT * FROM v_recent_blocks;

-- Summary statistics
SELECT * FROM v_enrichment_attempt_summary;

-- Specific district history
SELECT attempted_at, status, block_type, url
FROM enrichment_attempts
WHERE district_id = '0622710'
ORDER BY attempted_at DESC;

-- Manually mark district to skip
SELECT mark_district_skip('0622710', 'manual_review_cloudflare');
```

---

## Integration with Enrichment Scripts

### Example: Updated `fetch_bell_schedules.py`

```python
from infrastructure.database.enrichment_tracking import (
    should_skip_district,
    log_scraper_response,
    mark_district_skip
)

def enrich_district(district_id: str, district_url: str):
    """Enrich single district with security block checking"""

    with session_scope() as session:
        # Check if we should skip this district
        if should_skip_district(session, district_id):
            logger.info(f"Skipping {district_id} - flagged from previous failures")
            return None

        # Attempt scraping
        response = requests.post(
            'http://localhost:3000/scrape',
            json={'url': district_url, 'timeout': 30000}
        ).json()

        # Log the attempt
        log_scraper_response(
            session,
            district_id=district_id,
            scraper_response=response,
            enrichment_tier='tier1'
        )

        # Handle response
        if response.get('blocked'):
            logger.warning(f"Security block detected for {district_id}")
            # Mark to skip after first block (ONE-attempt protocol)
            mark_district_skip(session, district_id, 'security_block_one_attempt')
            return None

        if response.get('success'):
            # Extract bell schedule data
            return extract_bell_schedule(response)

        return None
```

### Example: Batch Processing with Skip Logic

```python
def enrich_batch(districts: List[Dict], tier: str = 'tier1'):
    """Enrich multiple districts, respecting skip flags"""

    with session_scope() as session:
        # Filter out districts to skip
        to_process = []
        for district in districts:
            if not should_skip_district(session, district['nces_id']):
                to_process.append(district)
            else:
                logger.info(f"Skipping {district['name']} - flagged")

        logger.info(f"Processing {len(to_process)} of {len(districts)} districts")

        # Process each district
        for district in to_process:
            try:
                result = enrich_district(district['nces_id'], district['url'])
                if result:
                    save_bell_schedule(result)
            except Exception as e:
                logger.error(f"Failed to enrich {district['nces_id']}: {e}")

        # Auto-flag repeat failures
        flagged = auto_flag_repeat_failures(session)
        if flagged > 0:
            logger.info(f"Auto-flagged {flagged} districts with repeated failures")
```

---

## Auto-Flagging Rules

The `auto_flag_repeat_failures()` function implements these rules:

| Failure Type | Threshold | Action |
|--------------|-----------|--------|
| **Security Blocks** | 3 attempts | Mark skip with reason `auto_flag_3_blocks` |
| **404 Not Found** | 4 attempts | Mark skip with reason `auto_flag_4_not_found` |
| **Timeouts** | Manual review | Not auto-flagged (may be temporary) |

### Manual Override

To manually flag/unflag a district:

```sql
-- Flag district to skip
UPDATE enrichment_attempts
SET skip_future_attempts = TRUE, skip_reason = 'manual_review'
WHERE district_id = '0622710';

-- Unflag district (allow retrying)
UPDATE enrichment_attempts
SET skip_future_attempts = FALSE, skip_reason = NULL
WHERE district_id = '0622710';
```

---

## Monitoring & Reports

### Daily Report: New Blocks

```sql
-- Blocks detected today
SELECT
    d.name,
    d.state,
    ea.block_type,
    ea.url,
    ea.attempted_at
FROM enrichment_attempts ea
JOIN districts d ON ea.district_id = d.nces_id
WHERE
    ea.status = 'blocked'
    AND ea.attempted_at::DATE = CURRENT_DATE
ORDER BY ea.attempted_at DESC;
```

### Weekly Report: Flagged Districts

```sql
-- Districts flagged in last 7 days
SELECT
    d.name,
    d.state,
    MAX(ea.skip_reason) AS reason,
    MAX(ea.attempted_at) AS last_attempt
FROM enrichment_attempts ea
JOIN districts d ON ea.district_id = d.nces_id
WHERE
    ea.skip_future_attempts = TRUE
    AND ea.attempted_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY d.name, d.state
ORDER BY d.state, d.name;
```

### Success Rate Report

```sql
-- Overall enrichment success rate
SELECT
    COUNT(*) FILTER (WHERE status = 'success') AS successful,
    COUNT(*) FILTER (WHERE status = 'blocked') AS blocked,
    COUNT(*) FILTER (WHERE status = 'not_found') AS not_found,
    COUNT(*) FILTER (WHERE status = 'timeout') AS timeout,
    COUNT(*) AS total,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'success') / COUNT(*), 2) AS success_rate_pct
FROM enrichment_attempts;
```

---

## Schema Reference

### `enrichment_attempts` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `district_id` | VARCHAR(10) | NCES district ID (FK to districts) |
| `url` | TEXT | URL attempted |
| `attempted_at` | TIMESTAMPTZ | Timestamp of attempt |
| `status` | VARCHAR(20) | Outcome: success, blocked, not_found, timeout, error, queue_full |
| `block_type` | VARCHAR(30) | Type of block: cloudflare, waf, captcha (if status='blocked') |
| `http_status_code` | INTEGER | HTTP status code |
| `error_message` | TEXT | Error message (if failed) |
| `timing_ms` | INTEGER | Response time in milliseconds |
| `retry_count` | INTEGER | Number of retries for this URL |
| `skip_future_attempts` | BOOLEAN | If TRUE, don't attempt this district again |
| `skip_reason` | TEXT | Reason for skipping |
| `scraper_version` | VARCHAR(20) | Version of scraper service |
| `enrichment_tier` | VARCHAR(10) | Tier: tier1, tier2, tier3 |
| `notes` | TEXT | Additional notes |
| `response_details` | JSONB | Full scraper response for debugging |

### Helper Views

- **`v_districts_to_skip`**: Districts flagged to skip (blocked or repeated failures)
- **`v_recent_blocks`**: Security blocks detected in last 30 days
- **`v_enrichment_attempt_summary`**: Summary statistics by status and block_type

### Helper Functions

- **`should_skip_district(district_id)`**: Returns TRUE if district is flagged to skip
- **`mark_district_skip(district_id, reason)`**: Mark district as skip with reason

---

## Related Documentation

- [BELL_SCHEDULE_OPERATIONS_GUIDE.md](BELL_SCHEDULE_OPERATIONS_GUIDE.md) - Operational procedures
- [BELL_SCHEDULE_SAMPLING_METHODOLOGY.md](BELL_SCHEDULE_SAMPLING_METHODOLOGY.md) - Methodology
- [SCHOOL_LEVEL_DISCOVERY_ENHANCEMENT.md](SCHOOL_LEVEL_DISCOVERY_ENHANCEMENT.md) - Multi-phase discovery

---

## Example Workflows

### Workflow 1: First-Time Enrichment Campaign

```bash
# 1. Start scraper service
cd scraper && docker-compose up -d

# 2. Run enrichment script with skip checking
python infrastructure/scripts/enrich/fetch_bell_schedules.py \
    data/processed/normalized/tier1_districts.csv \
    --tier 1 --year 2025-26 --check-skip-flags

# 3. Review blocks
psql -d learning_connection_time -c "SELECT * FROM v_recent_blocks;"

# 4. Auto-flag repeat failures
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_tracking import auto_flag_repeat_failures
with session_scope() as session:
    print(f'Flagged {auto_flag_repeat_failures(session)} districts')
"
```

### Workflow 2: Retry Failed Districts (Excluding Blocks)

```sql
-- Get districts that failed but weren't blocked
-- (timeouts, network errors - may be temporary)
SELECT DISTINCT
    ea.district_id,
    d.name,
    d.state,
    MAX(ea.attempted_at) AS last_attempt
FROM enrichment_attempts ea
JOIN districts d ON ea.district_id = d.nces_id
WHERE
    ea.status IN ('timeout', 'error')
    AND ea.district_id NOT IN (
        SELECT district_id FROM enrichment_attempts WHERE skip_future_attempts = TRUE
    )
GROUP BY ea.district_id, d.name, d.state
ORDER BY MAX(ea.attempted_at) DESC;
```

Export to CSV and retry:

```bash
psql -d learning_connection_time -c "COPY (...query...) TO '/tmp/retry_districts.csv' CSV HEADER;"
python infrastructure/scripts/enrich/fetch_bell_schedules.py /tmp/retry_districts.csv --tier 2
```

---

**Status:** ✅ Ready for Use

Apply migration and integrate with enrichment scripts to start tracking attempts.
