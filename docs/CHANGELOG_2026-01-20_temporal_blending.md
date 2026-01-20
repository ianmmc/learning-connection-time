# Temporal Blending Refactor - January 20, 2026

## Summary

Major refactor of LCT calculation system to support REQ-026 compliant temporal data blending with two distinct calculation modes.

## Key Changes

### 1. Database Schema Updates

**Migration 009: Update calculation_runs table**

- Added `calculation_mode` enum type: `'blended'` | `'target_year'`
- Renamed `year` column to `target_year` (now nullable)
- Added `data_year_min` and `data_year_max` for tracking actual data range
- Added validation constraint: TARGET_YEAR mode requires `target_year` to be set

**CalculationRun Model Updates:**
```python
class CalculationMode(str, Enum):
    BLENDED = 'blended'         # Most recent data within REQ-026 window
    TARGET_YEAR = 'target_year' # Enrollment anchored to specific year

# Updated model fields
calculation_mode: Mapped[CalculationMode]
target_year: Mapped[Optional[str]]
data_year_min: Mapped[Optional[str]]
data_year_max: Mapped[Optional[str]]
```

### 2. Calculation Script Refactor

**File:** `infrastructure/scripts/analyze/calculate_lct_variants.py`

**Breaking Changes:**
- ❌ Removed required `--year` parameter
- ✅ Added optional `--target-year` parameter
- ✅ Default behavior is now BLENDED mode

**New Usage:**
```bash
# BLENDED mode (default): Uses most recent data within REQ-026 window
python calculate_lct_variants.py

# TARGET_YEAR mode: Enrollment anchored to specific year
python calculate_lct_variants.py --target-year 2023-24
```

**Data Selection Logic:**
- **BLENDED**: Automatically selects most recent data per district per table
- **TARGET_YEAR**: Anchors enrollment to specified year, allows staff/bell blending within window

**New Helper Functions:**
- `get_most_recent_enrollment()` - Selects best enrollment data per mode
- `get_most_recent_sped()` - Selects best SPED estimate per mode
- `get_most_recent_ca_sped()` - Selects best CA actual SPED per mode
- `calculate_year_span()` - Computes span from list of school years

### 3. File Naming Convention

**Previous:**
- All files: `lct_all_variants_2023_24_<timestamp>.csv`

**New:**
- **BLENDED mode:** `lct_all_variants_<timestamp>.csv` (no year)
- **TARGET_YEAR mode:** `lct_all_variants_2023_24_<timestamp>.csv` (year included)

**Rationale:** Filename signals whether data is blended or anchored to specific year.

### 4. REQ-026 Temporal Validation Correction

**Previous (Incorrect):**
- `year_span = |year1_start - year2_start| + 1`
- Adjacent years (2023-24, 2024-25) had span = 2, triggered WARN_YEAR_GAP

**Corrected:**
- `year_span = |year1_start - year2_start|`
- Adjacent years (2023-24, 2024-25) have span = 1, NO flags

**Updated Flag Logic:**
- Span 0-1: No flags (same year or adjacent years)
- Span 2-3: WARN_YEAR_GAP (1-2 year gap, valid but notable)
- Span > 3: ERR_SPAN_EXCEEDED (exceeds 3-year blending window)

**Impact:**
- 85% reduction in false positive warnings (3,567 → 527)
- Only MA and VA correctly flagged for 2-year span
- CA, FL, PA, TX have no flags (adjacent years = valid)

### 5. Report Headers

**Previous:**
```
Year: 2023-24
```

**New:**
```
Mode: BLENDED (most recent data within REQ-026 window)
Data Range: 2023-24 to 2025-26
```

OR

```
Mode: TARGET_YEAR (enrollment anchored to 2023-24)
Target Year: 2023-24
Data Range: 2023-24 to 2024-25
```

### 6. QA Report Enhancements

**New Fields in QA JSON:**
```json
{
  "calculation_mode": "blended",
  "target_year": null,
  "data_year_min": "2023-24",
  "data_year_max": "2025-26",
  ...
}
```

## Files Modified

### Database
- `infrastructure/database/models.py` - Added CalculationMode enum, updated CalculationRun
- `infrastructure/database/migrations/009_update_calculation_runs.sql` - Schema migration
- `infrastructure/database/migrations/apply_009_calculation_runs.py` - Migration script
- `infrastructure/database/migrations/008_add_temporal_validation.sql` - Corrected year_span formula
- `infrastructure/database/migrations/merge_sea_precedence.py` - Fixed temporal logic

### Scripts
- `infrastructure/scripts/analyze/calculate_lct_variants.py` - Major refactor for blended/target modes

### Tests
- `tests/test_temporal_validation.py` - Updated all tests to match corrected logic (34 tests passing)

### Documentation
- `docs/METHODOLOGY.md` - Updated Temporal Data Blending section
- `docs/CHANGELOG_2026-01-20_temporal_blending.md` - This file
- `Claude.md` - Updated command examples

## Migration Path

**For existing workflows:**

1. **If using `--year 2023-24`:** Change to `--target-year 2023-24`
   ```bash
   # Old
   python calculate_lct_variants.py --year 2023-24

   # New
   python calculate_lct_variants.py --target-year 2023-24
   ```

2. **If you want to use most recent data:** Omit the year parameter entirely
   ```bash
   # New default behavior
   python calculate_lct_variants.py
   ```

3. **Database updates:** Run migration 009
   ```bash
   python infrastructure/database/migrations/apply_009_calculation_runs.py
   ```

## Testing

All tests passing:
- ✅ 34/34 temporal validation tests
- ✅ BLENDED mode: Data range 2023-24 to 2025-26 (span: 2 years)
- ✅ TARGET_YEAR 2023-24: Enrollment anchored correctly
- ✅ 164,797 LCT values calculated successfully
- ✅ File naming convention verified

## Benefits

1. **Flexibility:** Choose between most-recent data or year-anchored calculations
2. **Clarity:** File names indicate calculation mode
3. **Auditability:** Data range tracked and reported
4. **Accuracy:** Corrected year_span reduces false warnings by 85%
5. **REQ-026 Compliance:** All data within 3-year temporal window

## Next Steps

1. ✅ Update documentation (METHODOLOGY.md, Claude.md)
2. ✅ Test both calculation modes
3. ⏭️ Commit all changes to GitHub
4. ⏭️ Update any downstream processes that parse filenames
5. ⏭️ Consider adding `--strict-year` mode for exact-year-only matching

## References

- REQ-026: 3-Year Temporal Blending Window
- Migration 008: Temporal Validation Infrastructure
- Migration 009: CalculationRun Schema Updates
