# Fix Plan for MEGATHINK_ANALYSIS_REPORT.md Issues

**Created:** December 21, 2025
**Status:** Ready for Implementation

---

## Executive Summary

This plan addresses the 4 critical issues identified in the megathink analysis:
1. fetch_bell_schedules.py safeguard violations
2. merge_bell_schedules.py enriched flag logic error
3. calculate_lct.py metadata loss
4. full_pipeline.py step ordering error

**Estimated Time:** 2-3 hours
**Risk Level:** Medium (changes core enrichment logic)
**Testing Required:** Yes (sample data run)

---

## Issue 1: fetch_bell_schedules.py Safeguard Violations

### Current Problems
- ❌ No HTTPErrorTracker class
- ❌ No flag_for_manual_followup() function
- ❌ Tier 2 silently falls back to statutory (line 209)
- ❌ Always returns result, never None
- ❌ process_districts_file() doesn't handle None returns

### Fix Strategy

**Step 1.1: Add HTTPErrorTracker class**
```python
class HTTPErrorTracker:
    """Track HTTP errors and trigger auto-flagging at threshold"""
    def __init__(self, threshold=4):
        self.errors_404 = []
        self.threshold = threshold

    def record_404(self, url: str):
        self.errors_404.append(url)

    def should_flag_manual_followup(self) -> bool:
        return len(self.errors_404) >= self.threshold

    def get_summary(self) -> dict:
        return {
            "total_404s": len(self.errors_404),
            "urls_tried": self.errors_404,
            "threshold": self.threshold,
            "flagged": self.should_flag_manual_followup()
        }
```

**Step 1.2: Add flag_for_manual_followup() function**
```python
def flag_for_manual_followup(district_info: dict, error_summary: dict):
    """Add district to manual follow-up list"""
    followup_file = Path('data/enriched/bell-schedules/manual_followup_needed.json')

    # Load existing data
    with open(followup_file, 'r') as f:
        data = json.load(f)

    # Create entry
    entry = {
        "district_id": district_info['district_id'],
        "district_name": district_info['district_name'],
        "state": district_info['state'],
        "enrollment": district_info.get('enrollment'),
        "reason": f"Automated collection failed - {error_summary['total_404s']} 404 errors",
        "attempts": [{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "method": "WebSearch + WebFetch",
            "total_404s": error_summary['total_404s'],
            "urls_tried": error_summary['urls_tried']
        }],
        "next_steps": "Manual collection needed",
        "priority": "high",
        "flagged_date": datetime.now().strftime("%Y-%m-%d")
    }

    data['districts_needing_manual_review'].append(entry)
    data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(followup_file, 'w') as f:
        json.dump(data, f, indent=2)

    logger.warning(f"Flagged {district_info['district_name']} for manual follow-up")
```

**Step 1.3: Change return signature to Optional[Dict]**
- Change line 91: `def fetch_district_bell_schedules(...) -> Optional[Dict]:`
- Update docstring to document None return

**Step 1.4: Remove statutory fallback from Tier 2**
- Replace lines 208-210 with:
```python
# Template for automated search
result['notes'].append(
    "TEMPLATE: Automated web search would be performed here"
)

# If no bell schedules found after automated search, return None
# This will flag the district for manual follow-up
logger.warning(f"No bell schedules found for {district_name} - needs manual follow-up")
return None
```

**Step 1.5: Add enriched flag to result**
- Add to result dict:
```python
result['enriched'] = True  # Only set when actual data collected
result['data_quality_tier'] = 'enriched'  # vs 'statutory_fallback'
```

**Step 1.6: Update process_districts_file() to handle None**
- Change lines 327-352:
```python
result = self.fetch_district_bell_schedules(...)

if result is None:
    # Enrichment failed - was flagged for manual follow-up
    logger.info(f"Flagged {row['district_name']} - continuing to next district")
    stats['flagged_for_manual'] += 1
    continue

# Only process districts with actual enrichment
if result.get('enriched', False):
    # Flatten and add to results
    ...
else:
    logger.warning(f"Result returned but not enriched for {row['district_name']}")
    continue
```

**Step 1.7: Add stats tracking**
```python
stats = {'enriched': 0, 'flagged_for_manual': 0}
# Track in loop
# Report at end
logger.info(f"Enriched: {stats['enriched']}")
logger.info(f"Flagged for manual: {stats['flagged_for_manual']}")
```

**Step 1.8: Mark template code clearly**
- Add to _tier1_detailed_search and _tier2_automated_search:
```python
raise NotImplementedError(
    "Tier 1/2 enrichment not yet implemented. "
    "Use manual collection or Tier 3 (statutory only)."
)
```

### Validation
- [ ] HTTPErrorTracker class added
- [ ] flag_for_manual_followup() function added
- [ ] Return signature is Optional[Dict]
- [ ] Tier 2 returns None instead of statutory fallback
- [ ] process_districts_file() handles None returns
- [ ] Stats track enriched vs flagged
- [ ] Template code raises NotImplementedError

---

## Issue 2: merge_bell_schedules.py Enriched Flag Logic

### Current Problem
- Lines 209-214 check `confidence == 'high' or 'medium'` to determine "actual"
- Should check `method != 'state_statutory'` instead
- Statutory data with medium confidence incorrectly counted as actual

### Fix Strategy

**Step 2.1: Return method from get_instructional_minutes**
- Change return type: `-> tuple[Optional[int], str, str, str]:`
- Return: `(minutes, source, confidence, method)`
- Update line 134:
```python
method = level_data.get('method', 'unknown')
return minutes, source, confidence, method
```
- Update line 151:
```python
return minutes, source, 'statutory', 'state_statutory'
```
- Update line 160:
```python
return 300, 'Default assumption (5-hour day)', 'assumed', 'default'
```

**Step 2.2: Update merge_data to use method**
- Change line 199:
```python
minutes, source, confidence, method = self.get_instructional_minutes(
    district_id, state, grade_level
)
```
- Add method column:
```python
districts_df.at[idx, f'minutes_method_{grade_level}'] = method
```
- Fix lines 209-214:
```python
# Track statistics
if method != 'state_statutory' and method != 'default':
    stats[grade_level]['actual'] += 1
elif method == 'state_statutory':
    stats[grade_level]['statutory'] += 1
else:
    stats[grade_level]['assumed'] += 1
```

**Step 2.3: Initialize method column**
- Add to line 183:
```python
districts_df[f'minutes_method_{grade_level}'] = None
```

### Validation
- [ ] get_instructional_minutes returns method
- [ ] merge_data checks method field
- [ ] method column added to output
- [ ] Stats correctly distinguish actual vs statutory

---

## Issue 3: calculate_lct.py Metadata Preservation

### Current Problem
- Source/confidence/method columns not included in final output
- Can't audit data quality or verify enriched ≠ statutory
- Can't filter by enrichment quality

### Fix Strategy

**Step 3.1: Preserve metadata columns in output**
- Add to output columns around line 400:
```python
output_columns = [
    # Existing columns...
    'lct_elementary', 'lct_middle', 'lct_high', 'lct_overall',

    # ADD: Enrichment metadata
    'minutes_source_elementary', 'minutes_confidence_elementary', 'minutes_method_elementary',
    'minutes_source_middle', 'minutes_confidence_middle', 'minutes_method_middle',
    'minutes_source_high', 'minutes_confidence_high', 'minutes_method_high',
]
```

**Step 3.2: Add enrichment quality to validation report**
- Add section to _generate_validation_report:
```python
f.write("\nENRICHMENT QUALITY SUMMARY:\n")
for level in ['elementary', 'middle', 'high']:
    method_col = f'minutes_method_{level}'
    if method_col in df_complete.columns:
        counts = df_complete[method_col].value_counts()
        f.write(f"\n{level.capitalize()}:\n")
        for method, count in counts.items():
            pct = (count / len(df_complete)) * 100
            f.write(f"  {method}: {count} ({pct:.1f}%)\n")
```

**Step 3.3: Add enrichment filtering option**
- Add argument to main():
```python
parser.add_argument(
    '--enriched-only',
    action='store_true',
    help='Filter to only include districts with actual bell schedules (not statutory)'
)
```
- Apply filter if requested:
```python
if args.enriched_only:
    # Keep only districts where at least one level has actual data
    df = df[
        (df['minutes_method_elementary'] != 'state_statutory') |
        (df['minutes_method_middle'] != 'state_statutory') |
        (df['minutes_method_high'] != 'state_statutory')
    ]
    logger.info(f"Filtered to {len(df)} districts with actual bell schedules")
```

### Validation
- [ ] Metadata columns preserved in output
- [ ] Validation report includes enrichment quality
- [ ] --enriched-only flag works
- [ ] Can verify enriched ≠ statutory in final output

---

## Issue 4: full_pipeline.py Step Ordering

### Current Problem
- Bell schedule enrichment runs at step 2 (line 127)
- Normalization runs at step 4 (line 196)
- Enrichment needs normalized file but runs before it exists
- Enrichment silently skipped (line 150)

### Fix Strategy

**Step 4.1: Reorder pipeline steps**
Current order:
1. Download (step 1)
2. **Bell schedule enrichment (step 2)** ← WRONG
3. Extract (step 3)
4. **Normalization (step 4)** ← NEEDS TO BE BEFORE ENRICHMENT
5. Calculate (step 5)
6. Export (step 6)

Correct order:
1. Download
2. Extract
3. Normalize
4. Bell schedule enrichment ← MOVED AFTER NORMALIZE
5. Calculate
6. Export

**Step 4.2: Update step numbers and logic**
- Move enrichment block from line 127 to after normalization
- Renumber steps accordingly
- Update comments and logging

**Step 4.3: Add dependency validation**
```python
# Before enrichment step
normalized_file = Path(f"data/processed/normalized/districts_{year_suffix}_nces.csv")
if args.enrich_bell_schedules and not normalized_file.exists():
    logger.error(
        f"Cannot enrich bell schedules: normalized file not found: {normalized_file}"
    )
    logger.error("Run normalization step first or use --skip-enrichment")
    sys.exit(1)
```

**Step 4.4: Change skip behavior**
- Current: Skip silently if file missing
- New: Fail loudly if requested but prerequisites missing

### Validation
- [ ] Steps reordered correctly
- [ ] Enrichment runs after normalization
- [ ] Dependency validation added
- [ ] Fails loudly if prerequisites missing

---

## Plan Validation Results

### ✅ Validated Items

1. **get_instructional_minutes only has one caller** - Safe to change return signature
2. **Pipeline order confirmed wrong** - Line 150 comment even acknowledges it
3. **Method column addition** - No conflicts with existing columns
4. **NotImplementedError** - Intentional breaking change for safety

### ⚠️ Adjustments Needed

**Adjustment 1: Handle missing method column gracefully**
- calculate_lct.py should check if method columns exist before preserving
- Add to Step 3.1:
```python
# Check which metadata columns exist
metadata_cols = []
for level in ['elementary', 'middle', 'high']:
    for field in ['source', 'confidence', 'method']:
        col = f'minutes_{field}_{level}'
        if col in df.columns:
            metadata_cols.append(col)

# Only preserve columns that exist
output_columns.extend(metadata_cols)
```

**Adjustment 2: Clearer NotImplementedError message**
- Update Step 1.8:
```python
raise NotImplementedError(
    f"Tier {self.tier} enrichment not yet implemented. "
    "Tier 1/2 require web scraping implementation. "
    "Options: (1) Use Tier 3 (--tier 3) for statutory-only, "
    "(2) Manually collect bell schedules, or "
    "(3) Implement web scraping in this method. "
    "See docs/ENRICHMENT_SAFEGUARDS.md for requirements."
)
```

**Adjustment 3: Fail loudly in pipeline if prerequisites missing**
- Change Step 4.3 to fail instead of skip:
```python
# After normalization completes
if args.enrich_bell_schedules:
    normalized_file = Path(f"data/processed/normalized/districts_{year_suffix}_nces.csv")
    if not normalized_file.exists():
        logger.error(
            f"ERROR: Cannot enrich bell schedules - normalized file not found"
        )
        logger.error(f"Expected: {normalized_file}")
        logger.error("Normalization must complete before enrichment")
        sys.exit(1)
```

---

## Testing Plan

### Test 1: Safeguards with Sample Data
```bash
# Create sample with 5 districts
cd infrastructure/scripts/download
python fetch_nces_ccd.py --year 2023-24 --sample

# Try enrichment (should raise NotImplementedError for Tier 1/2)
cd ../enrich
python fetch_bell_schedules.py \
  ../../../data/processed/normalized/districts_2023_24_nces.csv \
  --tier 2 --sample

# Expected: NotImplementedError raised, no statutory fallback created
```

### Test 2: Merge with Method Field
```bash
# Create test bell schedule with method field
# Run merge
cd ../enrich
python merge_bell_schedules.py \
  ../../../data/processed/normalized/districts_2023_24_nces.csv \
  --output test_merge.csv

# Verify: method columns present, stats use method not confidence
```

### Test 3: LCT with Metadata
```bash
# Run LCT calculation
cd ../analyze
python calculate_lct.py \
  ../../../data/processed/normalized/districts_2023_24_merged.csv \
  --summary --filter-invalid

# Verify: metadata columns in output, enrichment quality in report
```

### Test 4: Pipeline Ordering
```bash
# Run full pipeline
cd ../../../../pipelines
python full_pipeline.py --year 2023-24 --sample

# Expected: Steps run in correct order, enrichment after normalization
```

---

## Implementation Order

1. **Issue 2 (merge_bell_schedules.py)** - Simplest, no dependencies
2. **Issue 3 (calculate_lct.py)** - Depends on Issue 2 for method column
3. **Issue 1 (fetch_bell_schedules.py)** - Standalone, template fixes
4. **Issue 4 (full_pipeline.py)** - Last, integrates all changes

---

## Rollback Plan

If issues arise:
1. All changes are in infrastructure/scripts - no data modified
2. Git revert to commit before changes
3. Original scripts preserved in git history
4. No database or external system changes

---

## Documentation Updates

After implementation:
- [ ] Update CLAUDE.md with safeguard implementation status
- [ ] Update SESSION_HANDOFF.md with fix completion
- [ ] Mark safeguard rules as implemented in ENRICHMENT_SAFEGUARDS.md
- [ ] Update megathink report with "FIXED" annotations

---

## Success Criteria

### Must Have
- ✅ All 4 critical issues addressed
- ✅ No silent failures in enrichment
- ✅ Enriched ≠ statutory enforced
- ✅ Metadata preserved through pipeline
- ✅ Pipeline steps in correct order

### Nice to Have
- ✅ Template code clearly marked
- ✅ Enrichment quality reporting
- ✅ Filtering by enrichment quality
- ✅ Comprehensive testing

---

**Status:** Plan validated and ready for implementation
**Next Step:** Begin implementation with Issue 2 (merge_bell_schedules.py)
