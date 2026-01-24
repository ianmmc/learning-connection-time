# Multi-Tier Enrichment Queue System - Implementation Status

**Date:** January 22, 2026
**Status:** Foundation Complete ✅

---

## Completed Components

### ✅ Database Infrastructure
**File:** `infrastructure/database/migrations/011_create_enrichment_queue.sql`

**Created:**
- `enrichment_queue` table - Tracks each district through 5-tier process
- `enrichment_batches` table - Tracks API batch processing
- Views:
  - `v_enrichment_queue_status` - Status summary by tier
  - `v_enrichment_tier_success` - Success rates per tier
  - `v_enrichment_batch_summary` - Batch processing stats
  - `v_districts_ready_for_batching` - Districts ready for API tiers
- Functions:
  - `get_queue_dashboard()` - Monitoring dashboard data
  - `queue_districts_for_enrichment()` - Add districts to queue
  - `escalate_to_next_tier()` - Move to next tier with reason
  - `complete_enrichment()` - Mark completion with results

**Migration Status:** ✅ Applied to database

### ✅ Architecture Documentation
**File:** `docs/MULTI_TIER_ENRICHMENT_ARCHITECTURE.md`

Complete specification including:
- Tier definitions and escalation criteria
- Queue processing flow diagrams
- Batch composition strategies
- Cost estimates ($8.80 for 245 districts)
- Monitoring dashboard spec

---

## Next Implementation Steps

### Priority 1: Core Queue Manager (Python)

**File to create:** `infrastructure/database/enrichment_queue_manager.py`

**Key classes:**
```python
class EnrichmentQueueManager:
    """Core orchestration for multi-tier enrichment"""

    def add_districts(district_ids: List[str]) -> int
    def get_status() -> Dict
    def process_tier_1_batch(batch_size: int = 50)
    def process_tier_2_batch(batch_size: int = 50)
    def process_tier_3_batch(batch_size: int = 20)
    def prepare_tier_4_batches() -> List[Batch]
    def process_tier_4_batch(batch: Batch)
    def prepare_tier_5_batches() -> List[Batch]
    def process_tier_5_batch(batch: Batch)
```

### Priority 2: Batch Composer

**File to create:** `infrastructure/database/batch_composer.py`

**Intelligent grouping:**
- Group Tier 4 (Claude) by: CMS platform, content type, district size
- Group Tier 5 (Gemini) by: State, district size, failure patterns

### Priority 3: Tier Processors

**Files to create:**
1. `infrastructure/scripts/enrich/tier_1_processor.py` - Local discovery
2. `infrastructure/scripts/enrich/tier_2_processor.py` - Local extraction
3. `infrastructure/scripts/enrich/tier_3_processor.py` - PDF/OCR
4. `infrastructure/scripts/enrich/tier_4_processor.py` - Claude API
5. `infrastructure/scripts/enrich/tier_5_processor.py` - Gemini MCP

---

## Testing Strategy

### Phase 1: Local Tiers Only (Tier 1-3)
**Goal:** Validate queue mechanics and local processing

**Test cases:**
1. Add 10 districts from swarm results
2. Process through Tier 1 (discovery)
3. Escalate to Tier 2 (extraction)
4. Escalate to Tier 3 (PDF) where applicable
5. Verify database tracking

**Success criteria:**
- All tier transitions logged correctly
- Escalation reasons captured
- Processing times tracked
- No API costs incurred

### Phase 2: API Tiers (Tier 4-5)
**Goal:** Validate batching and API integration

**Test cases:**
1. Create batch of 5 districts for Tier 4 (Claude)
2. Process batch via Claude API
3. Verify results logged
4. Escalate failures to Tier 5 (Gemini)
5. Process Gemini batch
6. Verify cost tracking

**Success criteria:**
- Batches composed correctly by similarity
- API responses parsed and stored
- Cost tracking accurate
- Confidence scores captured

### Phase 3: Full Pipeline
**Goal:** Process complete swarm dataset (245 districts)

**Test execution:**
```bash
# Add all swarm districts to queue
python -c "
from infrastructure.database.enrichment_queue_manager import EnrichmentQueueManager
from infrastructure.database.connection import session_scope

# Get districts from swarm results
swarm_districts = [...]  # 245 districts from SWARM_RESULTS_IMPORTED.md

with session_scope() as session:
    qm = EnrichmentQueueManager(session)
    added = qm.add_districts(swarm_districts)
    print(f'Added {added} districts to queue')

    # Process tiers
    qm.process_tier_1_batch()  # Local discovery
    qm.process_tier_2_batch()  # Local extraction
    qm.process_tier_3_batch()  # PDF/OCR

    # Prepare and process API batches
    tier_4_batches = qm.prepare_tier_4_batches()
    for batch in tier_4_batches:
        qm.process_tier_4_batch(batch)

    tier_5_batches = qm.prepare_tier_5_batches()
    for batch in tier_5_batches:
        qm.process_tier_5_batch(batch)

    # View results
    status = qm.get_status()
    print(status)
"
```

---

## Monitoring

### Real-Time Dashboard

**Access via SQL:**
```sql
SELECT * FROM get_queue_dashboard();
```

**Python API:**
```python
from infrastructure.database.enrichment_queue_manager import EnrichmentQueueManager
from infrastructure.database.connection import session_scope

with session_scope() as session:
    qm = EnrichmentQueueManager(session)
    status = qm.get_status()
    print(json.dumps(status, indent=2))
```

### Key Metrics to Track
1. **Queue depth** - How many districts at each tier
2. **Success rates** - Per-tier success percentages
3. **Processing time** - Average seconds per district per tier
4. **Cost tracking** - Running total of API costs
5. **Escalation reasons** - Why districts moved to next tier
6. **Batch efficiency** - Avg cost per district in batches

---

## Integration with Existing Systems

### Enrichment Attempts Table
- Queue results feed into `enrichment_attempts` for historical tracking
- Each tier attempt logged separately
- Final successful result becomes canonical bell schedule entry

### Bell Schedules Table
- Successful extractions create/update `bell_schedules` records
- Source tier tracked (tier_1, tier_2, tier_3, tier_4, tier_5)
- Confidence scores preserved

### Interactive Enrichment Script
- Can be extended to use queue system for automated fallback
- Manual enrichment bypasses queue for immediate processing

---

## Google Drive PDF Handling

Integrated into Tier 3 processor with special handling:

```python
def download_google_drive_pdf(drive_url: str) -> str:
    """Convert Google Drive view link to direct download"""

    # Extract file ID from various URL formats
    patterns = [
        r'drive\.google\.com/file/d/([^/]+)',
        r'drive\.google\.com/open\?id=([^&]+)',
    ]

    file_id = None
    for pattern in patterns:
        match = re.search(pattern, drive_url)
        if match:
            file_id = match.group(1)
            break

    if not file_id:
        raise ValueError(f"Could not extract file ID from: {drive_url}")

    # Convert to direct download URL
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    # Download
    response = requests.get(download_url, timeout=60)
    response.raise_for_status()

    # Save and process
    pdf_path = f"/tmp/schedule_{file_id}.pdf"
    with open(pdf_path, 'wb') as f:
        f.write(response.content)

    return pdf_path
```

---

## Cost Controls

### Budget Limits
Set maximum spend per run:

```python
qm = EnrichmentQueueManager(session, max_cost_dollars=10.00)
```

### Dry Run Mode
Test batches without API calls:

```python
qm.process_tier_4_batch(batch, dry_run=True)  # Logs but doesn't call API
```

### Per-District Cost Tracking
Monitor which districts are expensive:

```sql
SELECT district_id, estimated_cost_cents / 100.0 as cost_dollars
FROM enrichment_queue
WHERE estimated_cost_cents > 50  -- More than $0.50
ORDER BY estimated_cost_cents DESC;
```

---

## Performance Optimization

### Parallel Processing (Tier 1-3)
Local tiers can process many districts in parallel:

```python
# Process 50 districts in parallel using ThreadPoolExecutor
qm.process_tier_1_batch(batch_size=50, workers=10)
```

### Batch Size Tuning
Start conservative, optimize based on results:

| Tier | Initial Size | Adjust Based On |
|------|--------------|-----------------|
| 1-3  | 50 districts | CPU utilization |
| 4    | 10 districts | API token limits, timeout risk |
| 5    | 15 districts | Gemini rate limits |

### Caching
Cache common patterns to avoid redundant processing:
- CMS detection results
- Common URL patterns per district
- Previously discovered school subsites

---

## Failure Handling

### Retry Logic
- **Local tiers (1-3):** Automatic retry up to 3x
- **API tiers (4-5):** Manual review if batch fails

### Manual Review Queue
Districts that exhaust all tiers:

```sql
SELECT * FROM enrichment_queue
WHERE status = 'manual_review'
ORDER BY d.enrollment DESC;  -- Prioritize large districts
```

### Resume Processing
After fixing issues, resume from last tier:

```python
qm.resume_processing(district_id='1234567', from_tier=3)
```

---

## Future Enhancements

### Tier 6: Direct Contact (Optional)
For manual review queue, automate email requests to districts:
- Template email requesting bell schedule
- Track responses
- Human verification before import

### Machine Learning
Train classifier to predict optimal tier based on district characteristics:
- CMS platform → likely tier
- District size → likely complexity
- State → regional patterns

### Continuous Improvement
Log which escalation reasons correlate with tier success:
- "complex_table" → Tier 4 success rate 80%
- "heavy_js" → Tier 4 success rate 65%
- Use to refine escalation criteria

---

## Summary

**Foundation Complete:**
- ✅ Database schema
- ✅ Architecture design
- ✅ Documentation
- ✅ Testing strategy
- ✅ Cost estimates

**Ready to Build:**
- Queue manager (Python)
- Batch composer
- Tier processors (1-5)

**Expected Results:**
- 95% success rate (233/245 districts)
- ~$8.80 total cost
- ~4.5 hours processing time
- Complete audit trail of all attempts

---

**Next Action:** Implement `EnrichmentQueueManager` class in Python to orchestrate the complete workflow.
