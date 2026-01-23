# CLAUDE_WORKFLOWS.md - Development Procedures and Commands

Load this appendix when doing development work, running tests, or executing commands.

---

## Development Workflow

### 1. Start with Sample Data
```bash
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24 --sample
python pipelines/full_pipeline.py --year 2023-24 --sample
```

### 2. Process Real Data Incrementally
```bash
# Download
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24

# Extract multi-part files if present
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/

# Normalize
python infrastructure/scripts/transform/normalize_districts.py input.csv --source nces --year 2023-24

# Calculate LCT
python infrastructure/scripts/analyze/calculate_lct.py input.csv --summary --filter-invalid
```

### 3. Development Principles
- **Never modify raw data**: Work with copies in processed/
- **Document lineage**: Scripts create `_lineage.yaml` automatically
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
python pipelines/full_pipeline.py --year 2023-24 --enrich-bell-schedules --tier 1
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

### Bell Schedule Enrichment
```bash
# Interactive enrichment
python infrastructure/scripts/enrich/interactive_enrichment.py --state WI
python infrastructure/scripts/enrich/interactive_enrichment.py --district 5560580
python infrastructure/scripts/enrich/interactive_enrichment.py --status

# Automated (with scraper service)
python infrastructure/scripts/enrich/fetch_bell_schedules.py districts.csv --tier 1 --year 2023-24
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
