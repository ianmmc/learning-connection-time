# CLAUDE_WORKFLOWS.md - Development Procedures and Commands

Load this appendix when doing development work, running tests, or executing commands.

---

## Development Workflow

### 1. Full Database Rebuild (From Raw Sources)

```bash
# Complete rebuild from scratch - runs all phases
python infrastructure/scripts/rebuild_database.py

# With dry-run to preview
python infrastructure/scripts/rebuild_database.py --dry-run

# Start from specific phase (skip reset)
python infrastructure/scripts/rebuild_database.py --phase 3 --skip-reset
```

### 2. Individual Pipeline Steps

```bash
# Reset database (preserves schema)
python infrastructure/scripts/reset_database.py --force

# Load foundation data (districts, state requirements)
python infrastructure/database/migrations/import_all_data.py

# Load staff and enrollment
python infrastructure/database/migrations/import_staff_and_enrollment.py --year 2023-24

# Load SPED baseline
python infrastructure/database/migrations/import_sped_baseline.py

# Start acquisition services
docker-compose up -d

# Calculate LCT (DB-first, then exports)
python infrastructure/scripts/analyze/calculate_lct_variants.py
```

### 3. Development Principles
- **Never modify raw data**: Work with copies in processed/
- **Database is source of truth**: CSVs are exports from database
- **Verify enrichment claims**: Run `verify_enrichment.py` after any enrichment
- **Test incrementally**: Validate at each pipeline stage
- **Log everything**: Use Python's logging module

---

## Testing

### Unit Tests
```bash
cd infrastructure/quality-assurance/tests
pytest test_utilities.py -v
```

### SEA Integration Tests
```bash
# All 9 states
pytest tests/test_*_integration.py -v

# Single state
pytest tests/test_florida_integration.py -v

# By category
pytest tests/test_*_integration.py -v -k "crosswalk"
pytest tests/test_*_integration.py -v -k "enrollment"

# Collect only (quick validation)
pytest tests/test_*_integration.py --collect-only
```

### Test Individual Components
```bash
# State standardization
python infrastructure/utilities/common.py

# Sample data
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24 --sample

# Normalization validation
python infrastructure/scripts/transform/normalize_districts.py input.csv --source nces --year 2023-24 --validate-only
```

---

## Common Commands Reference

### Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Full Pipeline
```bash
python pipelines/full_pipeline.py --year 2023-24 --sample
```

### Database Operations
```bash
# Check status
psql -d learning_connection_time -c "SELECT COUNT(*) FROM districts;"

# Re-import
python infrastructure/database/migrations/import_all_data.py

# Export JSON
python infrastructure/database/export_json.py

# Refresh materialized views
psql -d learning_connection_time -c "SELECT refresh_all_materialized_views();"

# Query views
psql -d learning_connection_time -c "SELECT * FROM mv_state_enrichment_progress ORDER BY enriched DESC LIMIT 10;"
```

### LCT Calculation
```bash
# BLENDED mode (default)
python infrastructure/scripts/analyze/calculate_lct_variants.py

# TARGET_YEAR mode
python infrastructure/scripts/analyze/calculate_lct_variants.py --target-year 2023-24

# With Parquet export
python infrastructure/scripts/analyze/calculate_lct_variants.py --parquet

# Incremental
python infrastructure/scripts/analyze/calculate_lct_variants.py --incremental
```

### Bell Schedule Acquisition
```bash
# Start services (FastAPI + Crawlee)
docker-compose up -d

# Acquire a district
curl -X POST http://localhost:8000/acquire/district/1200390 \
  -H "Content-Type: application/json" \
  -d '{"district_id": "1200390", "district_name": "Pasco County", "state": "FL", "website_url": "https://www.pasco.k12.fl.us"}'

# Check status
curl http://localhost:8000/acquire/status/1200390

# Submit feedback for learning loop
curl -X POST http://localhost:8000/patterns/feedback \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/bell-schedule", "is_bell_schedule": true, "district_id": "1200390"}'
```

### Scraper Service
```bash
# Start locally
cd scraper && npm run dev

# Docker
docker-compose up -d scraper

# Health check
curl http://localhost:3001/health
```

### Utilities
```bash
# Generate data dictionary
python infrastructure/scripts/utilities/generate_data_dictionary.py

# Make scripts executable
python infrastructure/scripts/make_executable.py
```

---

## Troubleshooting

### "Column not found" errors
- Check input data matches expected schema
- Review column mappings in normalization script
- Use `--validate-only` flag to test without saving

### Memory issues
- Use `dask` for large files
- Process in chunks with pandas `chunksize`
- Use PostgreSQL for very large datasets

### Multi-part files not detected
- Ensure naming follows `basename_N.ext` pattern
- Check pattern parameter: `--pattern "_"`
- Verify files are in same directory

### Scraper issues
- Check `http://localhost:3001/status` for queue depth
- Review logs: `docker logs scraper`
- Respect ONE-attempt rule for blocked districts

---

## Getting Help

1. **Script documentation**: All scripts have `--help` flags
2. **Script README**: `infrastructure/scripts/README.md`
3. **Test files**: Tests show expected usage patterns
4. **Chat history**: `docs/chat-history/`
