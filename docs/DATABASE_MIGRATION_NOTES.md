# Database Migration Working Notes

**Project**: Learning Connection Time - PostgreSQL Migration
**Started**: December 25, 2025
**Status**: In Progress

---

## Objectives

1. Migrate from flat JSON files to PostgreSQL database
2. Improve token efficiency (query specific data vs. loading entire files)
3. Add data integrity guardrails (constraints, foreign keys)
4. Prepare for future web deployment
5. Maintain backward compatibility (JSON export for sharing)

---

## Key Decisions Log

### Decision 1: PostgreSQL over SQLite (Dec 25, 2025)
**Choice**: Skip SQLite, go directly to PostgreSQL
**Rationale**:
- Avoid migration pain later
- JSONB support for flexible nested data
- Same engine locally and in production
- Better constraint support
- Docker makes local setup trivial

### Decision 2: Schema Design Approach
**Choice**: Normalized schema with JSONB for flexibility
**Rationale**:
- Core entities (districts, schedules) as proper tables
- JSONB column for raw import data (preserve original structure)
- Constraints for data integrity
- Indexes for query performance

### Decision 3: Directory Structure
**Choice**: `infrastructure/database/` for all DB code
**Rationale**:
- Consistent with existing infrastructure/ pattern
- Separates DB concerns from analysis code
- Clear location for models, migrations, utilities

---

## Current Data Inventory

### Source Files to Migrate

1. **NCES Districts** (19,637 districts)
   - Location: `data/processed/normalized/districts_2023_24_nces.csv`
   - Columns: district_id, district_name, state, enrollment, instructional_staff, year, data_source
   - Size: ~0.7 MB (slim version)

2. **Enriched Bell Schedules** (77 districts)
   - Location: `data/enriched/bell-schedules/bell_schedules_manual_collection_2024_25.json`
   - Structure: Nested JSON with elementary/middle/high objects
   - Size: 41,624+ tokens

3. **State Requirements** (50 states + territories)
   - Location: `config/state-requirements.yaml`
   - Structure: YAML with per-state instructional time minimums

4. **Individual Bell Schedule Files** (77 files)
   - Location: `data/enriched/bell-schedules/{district_id}_2024-25.json`
   - Same structure as consolidated, one district each

---

## Schema Design Notes

### Core Tables

```
districts
├── nces_id (PK, VARCHAR) - 7-digit NCES district ID
├── name (VARCHAR, NOT NULL)
├── state (CHAR(2), NOT NULL)
├── enrollment (INTEGER)
├── instructional_staff (NUMERIC)
├── total_staff (NUMERIC, nullable)
├── schools_count (INTEGER, nullable)
├── year (VARCHAR) - "2023-24" format
├── data_source (VARCHAR) - "nces_ccd", etc.
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

state_requirements
├── state (PK, CHAR(2))
├── elementary_minutes (INTEGER)
├── middle_minutes (INTEGER)
├── high_minutes (INTEGER)
├── notes (TEXT)
├── source (VARCHAR)
└── updated_at (TIMESTAMP)

bell_schedules
├── id (PK, SERIAL)
├── district_id (FK → districts.nces_id)
├── year (VARCHAR) - "2024-25" format
├── grade_level (VARCHAR) - 'elementary', 'middle', 'high'
├── instructional_minutes (INTEGER, NOT NULL)
├── start_time (VARCHAR) - "8:00 AM" format
├── end_time (VARCHAR) - "3:00 PM" format
├── lunch_duration (INTEGER, nullable)
├── passing_periods (INTEGER, nullable)
├── recess_duration (INTEGER, nullable)
├── schools_sampled (JSONB) - array of school names
├── source_urls (JSONB) - array of URLs
├── confidence (VARCHAR) - 'high', 'medium', 'low'
├── method (VARCHAR) - 'automated_enrichment', 'human_provided'
├── source_description (TEXT)
├── notes (TEXT)
├── raw_import (JSONB) - original JSON for reference
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

lct_calculations
├── id (PK, SERIAL)
├── district_id (FK → districts.nces_id)
├── year (VARCHAR)
├── grade_level (VARCHAR, nullable) - null for district-wide
├── instructional_minutes (INTEGER)
├── enrollment (INTEGER)
├── instructional_staff (NUMERIC)
├── lct_value (NUMERIC) - calculated LCT
├── data_tier (INTEGER) - 1=actual, 2=automated, 3=statutory
├── calculated_at (TIMESTAMP)
└── notes (TEXT)

data_lineage
├── id (PK, SERIAL)
├── entity_type (VARCHAR) - 'district', 'bell_schedule', etc.
├── entity_id (VARCHAR) - reference to the entity
├── operation (VARCHAR) - 'create', 'update', 'import', 'calculate'
├── source_file (VARCHAR)
├── details (JSONB)
├── created_at (TIMESTAMP)
└── created_by (VARCHAR) - 'migration', 'manual', 'pipeline'
```

### Indexes

- districts: state, enrollment (for top-N queries)
- bell_schedules: district_id, year, grade_level
- lct_calculations: district_id, year
- data_lineage: entity_type, entity_id

### Constraints

- bell_schedules.instructional_minutes: CHECK (value BETWEEN 100 AND 600)
- bell_schedules.confidence: CHECK (value IN ('high', 'medium', 'low'))
- bell_schedules.method: CHECK (value IN ('automated_enrichment', 'human_provided'))
- bell_schedules.grade_level: CHECK (value IN ('elementary', 'middle', 'high'))
- lct_calculations.data_tier: CHECK (value IN (1, 2, 3))

---

## Implementation Progress

### Phase 1: Setup ✅ COMPLETE
- [x] Create working notes file
- [x] Create schema.sql
- [x] Set up PostgreSQL (via Homebrew, not Docker)
- [x] Test database connection

### Phase 2: Models ✅ COMPLETE
- [x] Create SQLAlchemy models
- [x] Create database utilities (connection, session)
- [x] Test model creation

### Phase 3: Migration ✅ COMPLETE
- [x] Migrate state_requirements from YAML (50 states)
- [x] Migrate districts from CSV (17,842 districts)
- [x] Migrate bell_schedules from JSON (214 records, 76 districts)
- [x] Validate data integrity

### Phase 4: Pipeline Updates ✅ COMPLETE
- [x] Create queries.py with high-level database functions
- [x] Create JSON export utility (export_json.py)
- [x] Test query utilities and export
- [x] Migrate Wyoming legacy data (5 districts, 15 schedules)
- [ ] Update enrichment workflow scripts (future enhancement)
- [ ] Update LCT calculation to use database (future enhancement)

### Phase 5: Documentation ✅ COMPLETE
- [x] Update CLAUDE.md with database infrastructure
- [x] Create DATABASE_SETUP.md
- [x] Create DATABASE_TEST_RESULTS.md
- [x] Update SESSION_HANDOFF.md

---

## Issues & Resolutions

### Issue 1: Bell schedule method constraint violation
**Date**: Dec 25, 2025
**Problem**: Bell schedule JSON had method values like 'web_scraping', 'fallback_statutory' not in original constraint
**Resolution**: Updated constraint to include all 9 method types found in data
**Notes**: Methods allowed: automated_enrichment, human_provided, statutory_fallback, web_scraping, fallback_statutory, pdf_extraction, manual_data_collection, district_policy, school_sample

### Issue 2: District ID format mismatch (leading zeros)
**Date**: Dec 25, 2025
**Problem**: Bell schedule JSON had IDs like '0626910' but CSV has '626910' (no leading zeros)
**Resolution**: Added ID normalization in import script (strip leading zeros)
**Notes**: 4 districts had leading zeros stripped during import

### Issue 3: Great Falls Elementary ID mismatch
**Date**: Dec 25, 2025
**Problem**: JSON has district_id '3000052' but NCES has '3013040' for Great Falls Elem
**Resolution**: Skipped during import with warning (needs fix in source JSON)
**Notes**: 1 of 77 districts (1.3%) not imported due to incorrect ID in source data
**Action**: Fix JSON to use correct NCES ID '3013040'

### Issue 4: Additional method types in Wyoming legacy data
**Date**: Dec 25, 2025
**Problem**: Wyoming 2023-24 files had method values not in original constraint (district_standardized_schedule, school_specific_schedules, school_hours_with_estimation, state_requirement_with_validation)
**Resolution**: Expanded method constraint to include all 13 method types found in data
**Notes**: Now supports comprehensive set of collection methods

### Issue 5: VARCHAR column sizes too small for descriptive data
**Date**: Dec 25, 2025
**Problem**: start_time/end_time VARCHAR(20) too small for values like "7:45 AM (Period 1)", method VARCHAR(30) too small for "state_requirement_with_validation"
**Resolution**:
- Expanded start_time/end_time to VARCHAR(50)
- Expanded method to VARCHAR(50)
- Had to drop dependent views temporarily (v_enriched_districts, v_state_summary, v_top_districts)
**Notes**: Views can be recreated if needed for future reporting

---

## Testing Checklist

### Data Validation ✅ COMPLETE
- [x] District count: 17,842 (normalized NCES dataset)
- [x] Bell schedule records: 230 (79 enriched districts, mixed 2023-24 and 2024-25 data)
- [x] State requirement count: 50
- [x] Wyoming legacy data: 5 districts, 15 schedules from 2023-24
- [x] Database integrity: All foreign keys, constraints, indexes working

### Functionality Tests
- [ ] Can query districts by state
- [ ] Can query top N by enrollment
- [ ] Can add new bell schedule
- [ ] Can update existing bell schedule
- [ ] Can export to JSON format
- [ ] Can run LCT calculation pipeline

### Performance Tests
- [ ] Query single district: < 10ms
- [ ] Query all districts by state: < 100ms
- [ ] Full LCT calculation: < 5 seconds

---

## Rollback Plan

If migration fails or causes issues:
1. All original files preserved in place
2. Database is additive (doesn't modify source files)
3. Can revert to file-based workflow by using original scripts
4. JSON export utility provides backup path

---

## Future Considerations

1. **PostGIS for geographic queries** - When adding map visualizations
2. **Supabase migration** - When ready for web deployment
3. **Census data integration** - New table for demographic data by zip code
4. **API layer** - FastAPI or similar for REST endpoints
5. **Caching layer** - Redis for frequently accessed data

---

## Session Log

### Session 1 (Dec 25, 2025)
- Created this working notes file
- Designed initial schema
- [Continue logging progress...]

---

**Last Updated**: December 25, 2025
