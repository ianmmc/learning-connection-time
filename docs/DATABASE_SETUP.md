# PostgreSQL Database Setup Guide

**Last Updated**: December 28, 2025

This guide covers the complete setup and usage of the PostgreSQL database for the Learning Connection Time project.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Database Schema](#database-schema)
- [Materialized Views](#materialized-views)
- [Query Utilities](#query-utilities)
- [Data Management](#data-management)
- [Performance Optimization](#performance-optimization)
- [Troubleshooting](#troubleshooting)

---

## Overview

### Why PostgreSQL?

The project migrated from JSON files to PostgreSQL (December 2025) for:

1. **Token Efficiency**: Query specific data instead of loading entire files
2. **Data Integrity**: Foreign keys, check constraints, JSONB validation
3. **Performance**: Indexed lookups, materialized views, query optimization
4. **Scalability**: Handles 17K+ districts with ease
5. **Production-Ready**: Same engine locally (Docker) and in production (Supabase)

### Technology Stack

- **Database**: PostgreSQL 16
- **Containerization**: Docker Compose
- **ORM**: SQLAlchemy 2.x with declarative models
- **Python Driver**: psycopg2
- **Schema Management**: DDL scripts in `infrastructure/database/migrations/`

---

## Quick Start

### 1. Start the Database

```bash
# Start PostgreSQL in Docker
docker-compose up -d

# Verify it's running
docker ps | grep postgres
```

### 2. Connect to Database

```bash
# Using psql
psql -h localhost -p 5432 -U lct_user -d learning_connection_time

# Using Python
python -c "
from infrastructure.database.connection import session_scope
with session_scope() as session:
    from infrastructure.database.models import District
    count = session.query(District).count()
    print(f'Districts: {count}')
"
```

### 3. Import Data (First Time)

```bash
# Import all data from JSON files
python infrastructure/database/migrations/import_all_data.py

# Verify import
psql -d learning_connection_time -c "
SELECT
  (SELECT COUNT(*) FROM districts) as districts,
  (SELECT COUNT(*) FROM bell_schedules) as bell_schedules,
  (SELECT COUNT(DISTINCT district_id) FROM bell_schedules) as enriched_districts;
"
```

---

## Database Schema

### Core Tables

#### **districts**
Primary table containing all U.S. school districts.

| Column | Type | Description |
|--------|------|-------------|
| nces_id | VARCHAR(20) | Primary key, NCES district ID |
| name | VARCHAR(255) | District name |
| state | VARCHAR(2) | Two-letter state code |
| enrollment | INTEGER | Total K-12 enrollment |
| schools | INTEGER | Number of schools |
| locale_code | VARCHAR(10) | NCES locale classification |
| metadata | JSONB | Additional district info |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last update time |

**Indexes**:
- Primary key on `nces_id`
- Index on `state`
- Index on `enrollment` (for ranking queries)

#### **state_requirements**
State-specific instructional time requirements.

| Column | Type | Description |
|--------|------|-------------|
| state_code | VARCHAR(2) | Primary key, state code |
| state_name | VARCHAR(100) | Full state name |
| elementary_minutes | INTEGER | Elementary instructional minutes/day |
| middle_minutes | INTEGER | Middle school minutes/day |
| high_minutes | INTEGER | High school minutes/day |
| notes | TEXT | Source citations, special rules |
| updated_at | TIMESTAMP | Last update time |

#### **bell_schedules**
Actual bell schedule data collected from districts.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| district_id | VARCHAR(20) | Foreign key to districts |
| year | VARCHAR(10) | School year (e.g., "2025-26") |
| grade_level | VARCHAR(20) | elementary, middle, or high |
| instructional_minutes | INTEGER | Daily instructional minutes |
| start_time | VARCHAR(20) | School start time |
| end_time | VARCHAR(20) | School end time |
| lunch_duration | INTEGER | Lunch period in minutes |
| passing_periods | INTEGER | Passing period time |
| method | VARCHAR(50) | Collection method |
| confidence | VARCHAR(20) | Data confidence level |
| schools_sampled | JSONB | Array of school names |
| source_urls | JSONB | Array of source URLs |
| notes | TEXT | Additional context |
| created_at | TIMESTAMP | Record creation time |
| created_by | VARCHAR(100) | Who collected the data |

**Constraints**:
- Foreign key to `districts(nces_id)`
- Check constraint: `instructional_minutes BETWEEN 0 AND 600`
- Unique constraint: `(district_id, year, grade_level)`

#### **grade_level_enrollment**
K-12 enrollment by grade level.

| Column | Type | Description |
|--------|------|-------------|
| nces_id | VARCHAR(20) | Foreign key to districts |
| year | VARCHAR(10) | School year |
| grade | VARCHAR(5) | Grade level (KG, G01-G12) |
| enrollment | INTEGER | Students in grade |

#### **grade_level_staffing**
K-12 teacher counts by level.

| Column | Type | Description |
|--------|------|-------------|
| nces_id | VARCHAR(20) | Foreign key to districts |
| year | VARCHAR(10) | School year |
| category | VARCHAR(50) | Staff category |
| fte_count | DECIMAL(10,2) | Full-time equivalent count |

#### **lct_calculations**
Calculated LCT metrics for districts.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| district_id | VARCHAR(20) | Foreign key to districts |
| year | VARCHAR(10) | School year |
| scope | VARCHAR(50) | LCT variant (teachers_only, etc.) |
| instructional_minutes | INTEGER | Minutes used in calculation |
| staff_count | DECIMAL(10,2) | Staff FTE used |
| enrollment | INTEGER | Student enrollment used |
| lct_value | DECIMAL(10,2) | Calculated LCT in minutes |
| calculation_notes | TEXT | Data quality notes |
| run_id | VARCHAR(50) | Foreign key to calculation_runs |
| created_at | TIMESTAMP | Calculation timestamp |

#### **calculation_runs**
Tracks LCT calculation runs for incremental processing.

| Column | Type | Description |
|--------|------|-------------|
| run_id | VARCHAR(50) | Primary key, ISO timestamp |
| year | VARCHAR(10) | School year calculated |
| run_type | VARCHAR(30) | full or incremental |
| status | VARCHAR(20) | running, completed, failed |
| districts_processed | INTEGER | Number of districts |
| calculations_created | INTEGER | LCT records created |
| input_hash | VARCHAR(64) | SHA-256 of input data |
| output_files | JSONB | Array of output file paths |
| qa_summary | JSONB | QA validation results |
| started_at | TIMESTAMP | Run start time |
| completed_at | TIMESTAMP | Run completion time |
| duration_seconds | INTEGER | Total runtime |

**Tracks**:
- Which districts need recalculation (via `input_hash`)
- QA validation results (pass rate, outliers, etc.)
- Output file locations
- Runtime performance

#### **data_lineage**
Audit trail for all data operations.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| table_name | VARCHAR(100) | Affected table |
| operation | VARCHAR(50) | insert, update, delete |
| record_id | VARCHAR(100) | Affected record |
| changes | JSONB | Before/after values |
| source | VARCHAR(100) | Script or user |
| timestamp | TIMESTAMP | Operation time |

---

## Materialized Views

Materialized views pre-compute common queries for fast lookups. **Created**: December 28, 2025

### **mv_districts_with_lct_data**

Pre-joins districts with enrollment and staffing data.

```sql
SELECT nces_id, name, state, enrollment,
       elem_enrollment, sec_enrollment,
       elem_teachers, sec_teachers, ungraded_teachers
FROM mv_districts_with_lct_data
WHERE state = 'WI';
```

**Rows**: ~14,463 districts with complete data
**Refresh**: After importing new enrollment/staffing data

### **mv_state_enrichment_progress**

Campaign progress by state (for Option A workflow).

```sql
SELECT state, total_districts, enriched, unenriched,
       pct_enriched, total_enrollment, complete
FROM mv_state_enrichment_progress
ORDER BY enriched DESC;
```

**Columns**:
- `enriched`: Districts with bell schedules
- `complete`: TRUE if ≥3 districts enriched
- `total_enrollment`: State's total K-12 students

**Rows**: 55 states/territories
**Refresh**: After adding bell schedules

### **mv_unenriched_districts**

Fast lookup of districts needing enrichment.

```sql
SELECT nces_id, name, state, enrollment, rank_in_state
FROM mv_unenriched_districts
WHERE state = 'WI' AND rank_in_state <= 9;
```

**Rows**: ~17,342 districts without bell schedules
**Refresh**: After adding bell schedules

### **mv_lct_summary_stats**

Pre-computed LCT statistics by scope.

```sql
SELECT scope, district_count, mean_lct, median_lct,
       std_lct, min_lct, max_lct
FROM mv_lct_summary_stats
ORDER BY scope;
```

**Rows**: 7 scopes (all, instructional, teachers_only, etc.)
**Refresh**: After running LCT calculations

### Refreshing Views

```bash
# Refresh all views (recommended after data changes)
psql -d learning_connection_time -c "SELECT refresh_all_materialized_views();"

# Refresh individual view
psql -d learning_connection_time -c "REFRESH MATERIALIZED VIEW mv_state_enrichment_progress;"

# Check last refresh time (PostgreSQL 16+)
psql -d learning_connection_time -c "
SELECT schemaname, matviewname,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||matviewname)) as size
FROM pg_matviews
WHERE schemaname = 'public';
"
```

---

## Query Utilities

High-level Python functions in `infrastructure/database/queries.py`.

### Enrichment Queries

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import (
    get_next_enrichment_candidates,
    get_state_campaign_progress,
    add_bell_schedule
)

with session_scope() as session:
    # Get top 9 unenriched districts in Wisconsin
    candidates = get_next_enrichment_candidates(session, "WI", "2025-26", limit=9)
    for district in candidates:
        print(f"{district.name}: {district.enrollment:,} students")

    # Check state campaign progress
    progress = get_state_campaign_progress(session, "2025-26")
    for state in progress:
        if not state["complete"]:
            print(f"{state['state']}: {state['enriched']}/3 enriched")

    # Add bell schedule
    add_bell_schedule(
        session,
        district_id="5560580",
        year="2025-26",
        grade_level="elementary",
        instructional_minutes=360,
        start_time="8:00 AM",
        end_time="3:00 PM",
        method="web_scraping",
        confidence="high",
        source_urls=["https://example.com/schedule"]
    )
```

### LCT Calculation Queries

```python
from infrastructure.database.queries import (
    get_lct_summary_by_scope,
    get_districts_needing_calculation
)

with session_scope() as session:
    # Get LCT summary for teachers_only scope
    summary = get_lct_summary_by_scope(session, "teachers_only", "2023-24")
    print(f"Mean LCT: {summary['mean_lct']:.1f} minutes")
    print(f"Districts: {summary['district_count']}")

    # Get districts needing recalculation
    districts = get_districts_needing_calculation(session, last_run_id="20251228T012555Z")
    print(f"Districts to recalculate: {len(districts)}")
```

### General Queries

```python
from infrastructure.database.queries import (
    get_district_by_id,
    get_enrichment_summary,
    print_enrichment_report
)

with session_scope() as session:
    # Get single district
    district = get_district_by_id(session, "5560580")
    print(f"{district.name} ({district.state}): {district.enrollment:,} students")

    # Get enrichment summary
    summary = get_enrichment_summary(session, "2025-26")
    print(f"Enriched: {summary['enriched_districts']}/{summary['total_districts']}")
    print(f"Enrichment rate: {summary['enrichment_rate']:.2f}%")

    # Print formatted report
    print_enrichment_report(session)
```

---

## Data Management

### Import Data

```bash
# Import all data from JSON files (initial setup)
python infrastructure/database/migrations/import_all_data.py

# Import specific datasets
python infrastructure/database/migrations/import_districts.py
python infrastructure/database/migrations/import_bell_schedules.py
```

### Export Data

```bash
# Export to JSON (backward compatibility)
python infrastructure/database/export_json.py

# Custom export query
psql -d learning_connection_time -c "
COPY (
  SELECT d.nces_id, d.name, d.state, d.enrollment,
         bs.grade_level, bs.instructional_minutes
  FROM districts d
  JOIN bell_schedules bs ON d.nces_id = bs.district_id
  WHERE bs.year = '2025-26'
) TO '/tmp/enriched_districts.csv' CSV HEADER;
"
```

### Backup and Restore

```bash
# Backup entire database
docker exec postgres pg_dump -U lct_user learning_connection_time > backup_$(date +%Y%m%d).sql

# Backup specific table
docker exec postgres pg_dump -U lct_user -t bell_schedules learning_connection_time > bell_schedules_backup.sql

# Restore from backup
docker exec -i postgres psql -U lct_user learning_connection_time < backup_20251228.sql
```

---

## Performance Optimization

### Indexes

All critical columns are indexed:

```sql
-- Check existing indexes
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- Example: Add custom index for frequent query
CREATE INDEX idx_bell_schedules_year_level
ON bell_schedules(year, grade_level);
```

### Query Performance

```sql
-- Analyze query performance
EXPLAIN ANALYZE
SELECT d.name, bs.instructional_minutes
FROM districts d
JOIN bell_schedules bs ON d.nces_id = bs.district_id
WHERE d.state = 'WI' AND bs.year = '2025-26';

-- Update table statistics
ANALYZE districts;
ANALYZE bell_schedules;
```

### Maintenance

```bash
# Vacuum and analyze (monthly recommended)
psql -d learning_connection_time -c "VACUUM ANALYZE;"

# Check database size
psql -d learning_connection_time -c "
SELECT pg_size_pretty(pg_database_size('learning_connection_time')) as size;
"

# Check table sizes
psql -d learning_connection_time -c "
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

---

## Troubleshooting

### Connection Issues

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check logs
docker logs postgres

# Restart container
docker-compose restart

# Connect directly to container
docker exec -it postgres psql -U lct_user -d learning_connection_time
```

### Common Errors

**Error**: `psycopg2.OperationalError: FATAL: database "learning_connection_time" does not exist`

**Solution**: Create database first:
```bash
docker exec -it postgres psql -U lct_user -c "CREATE DATABASE learning_connection_time;"
```

**Error**: `relation "districts" does not exist`

**Solution**: Run schema creation:
```bash
psql -d learning_connection_time -f infrastructure/database/schema.sql
```

**Error**: `duplicate key value violates unique constraint`

**Solution**: District already exists. Use update query or delete first:
```python
from infrastructure.database.models import District
with session_scope() as session:
    existing = session.query(District).filter_by(nces_id="5560580").first()
    if existing:
        existing.name = "New Name"
        session.commit()
```

### Performance Issues

**Slow queries on large tables**:

1. Check if indexes exist: `\d+ districts` in psql
2. Run `ANALYZE` on the table
3. Check query plan with `EXPLAIN ANALYZE`
4. Consider adding more specific indexes

**Materialized views out of date**:

```bash
# Refresh all views
psql -d learning_connection_time -c "SELECT refresh_all_materialized_views();"
```

---

## Advanced Usage

### Custom Queries

```python
from infrastructure.database.connection import session_scope
from sqlalchemy import text

with session_scope() as session:
    # Raw SQL query
    result = session.execute(text("""
        SELECT state, COUNT(*) as district_count,
               AVG(enrollment) as avg_enrollment
        FROM districts
        GROUP BY state
        ORDER BY avg_enrollment DESC
        LIMIT 10
    """))

    for row in result:
        print(f"{row.state}: {row.district_count} districts, avg {row.avg_enrollment:.0f} students")
```

### Bulk Operations

```python
from infrastructure.database.models import BellSchedule

with session_scope() as session:
    # Bulk insert
    schedules = [
        BellSchedule(
            district_id=f"555{i:04d}",
            year="2025-26",
            grade_level="elementary",
            instructional_minutes=360,
            method="automated"
        )
        for i in range(100)
    ]
    session.bulk_save_objects(schedules)
    session.commit()
```

---

## See Also

- [Data Dictionary](data-dictionaries/database_schema_latest.md) - Auto-generated schema documentation
- [Query Functions](../infrastructure/database/queries.py) - High-level query utilities
- [Database Models](../infrastructure/database/models.py) - SQLAlchemy ORM models
- [Migration Scripts](../infrastructure/database/migrations/) - Data import/export scripts

---

**Last Updated**: December 28, 2025
**Database Version**: PostgreSQL 16
**Schema Version**: 2.0 (with materialized views and calculation tracking)
