# Database Setup Guide

This document describes how to set up and use the PostgreSQL database for the Learning Connection Time project.

## Overview

The project uses PostgreSQL to store district data, bell schedules, state requirements, and LCT calculations. This replaces the previous file-based approach for better query performance, data integrity, and token efficiency.

## Prerequisites

- macOS (tested on Darwin 25.1.0)
- Homebrew package manager
- Python 3.11+

## Installation

You have two options for running PostgreSQL locally: **Docker** (recommended) or **Homebrew**.

### Option 1: Docker (Recommended) ⭐

**Why Docker?**
- Consistent environment across development/production
- Easy setup and teardown
- Isolated from system
- Matches production (Supabase) more closely
- Infrastructure as code

**Setup:**

```bash
# 1. Install Docker Desktop (if not already installed)
brew install --cask docker
# Or download from https://www.docker.com/products/docker-desktop

# 2. Start Docker Desktop (wait for it to be ready)
open -a Docker

# 3. Start PostgreSQL container
docker-compose up -d

# 4. Verify container is running
docker-compose ps

# 5. Import data (if migrating from Homebrew)
python3 infrastructure/database/docker/import_to_docker.py

# 6. Test connection
python3 infrastructure/database/connection.py
```

**Environment Configuration:**

The `.env` file (already created) configures Docker connection:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=learning_connection_time
POSTGRES_USER=lct_user
POSTGRES_PASSWORD=lct_password
```

**Common Docker Commands:**

```bash
# Start containers
docker-compose up -d

# Stop containers (keeps data)
docker-compose stop

# View logs
docker-compose logs -f postgres

# Connect via psql
docker-compose exec postgres psql -U lct_user -d learning_connection_time

# Remove everything (including data!)
docker-compose down -v
```

**Full Docker documentation**: See `infrastructure/database/docker/README.md`

---

### Option 2: Homebrew (Alternative)

**Setup:**

```bash
# 1. Install PostgreSQL 16 via Homebrew
brew install postgresql@16

# 2. Start the service
brew services start postgresql@16

# 3. Add to PATH (add to ~/.zshrc or ~/.bashrc)
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"

# 4. Create the database
createdb learning_connection_time

# 5. Verify connection
psql -d learning_connection_time -c "SELECT 1;"

# 6. Initialize schema
psql -d learning_connection_time -f infrastructure/database/schema.sql
```

### Install Python Dependencies (Both Options)

```bash
pip install psycopg2-binary sqlalchemy python-dotenv
```

---

## Configuration

The database connection is configured in `infrastructure/database/connection.py`.

**Connection Priority:**
1. `DATABASE_URL` environment variable (for production, e.g., Supabase)
2. Individual `POSTGRES_*` variables from `.env` file (for Docker)
3. Default to Homebrew (localhost, system user, no password)

**Docker setup** (`.env` file):
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=learning_connection_time
POSTGRES_USER=lct_user
POSTGRES_PASSWORD=lct_password
```

**Homebrew setup** (no .env needed):
- Uses system user authentication
- No password required
- Connects to `postgresql://localhost:5432/learning_connection_time`

**Production setup** (Supabase):
```bash
DATABASE_URL=postgresql://user:password@host:port/database
```

## Database Structure

### Tables

| Table | Description | Records |
|-------|-------------|---------|
| `districts` | NCES CCD district data | ~17,842 |
| `state_requirements` | State instructional time minimums | 50 |
| `bell_schedules` | Enriched bell schedule data | ~214 |
| `lct_calculations` | Computed LCT metrics | varies |
| `data_lineage` | Audit trail for data changes | varies |

### Key Relationships

```
districts (1) ---> (many) bell_schedules
districts (1) ---> (many) lct_calculations
bell_schedules (1) ---> (many) lct_calculations
```

## Data Migration

To import data from files into the database:

```bash
# Full import (all data sources)
python infrastructure/database/migrations/import_all_data.py

# Dry run (preview without committing)
python infrastructure/database/migrations/import_all_data.py --dry-run

# Skip specific data types
python infrastructure/database/migrations/import_all_data.py --skip-districts
python infrastructure/database/migrations/import_all_data.py --skip-schedules
python infrastructure/database/migrations/import_all_data.py --skip-states
```

## Query Utilities

The `infrastructure/database/queries.py` module provides high-level functions:

### District Queries

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import (
    get_district_by_id,
    get_top_districts,
    get_unenriched_districts,
    search_districts
)

with session_scope() as session:
    # Get a specific district
    district = get_district_by_id(session, "622710")

    # Get top 10 districts by enrollment
    top_10 = get_top_districts(session, limit=10)

    # Get unenriched districts with 10k+ enrollment
    candidates = get_unenriched_districts(session, min_enrollment=10000)

    # Search by name
    results = search_districts(session, "Los Angeles")
```

### Bell Schedule Queries

```python
from infrastructure.database.queries import (
    get_bell_schedule,
    add_bell_schedule,
    add_district_bell_schedules
)

with session_scope() as session:
    # Get existing schedule
    schedule = get_bell_schedule(session, "622710", "2024-25", "elementary")

    # Add a new schedule
    add_bell_schedule(
        session,
        district_id="622710",
        year="2024-25",
        grade_level="high",
        instructional_minutes=375,
        start_time="8:00 AM",
        end_time="3:30 PM",
        method="human_provided",
        confidence="high"
    )
```

### Reporting

```python
from infrastructure.database.queries import get_enrichment_summary, print_enrichment_report

with session_scope() as session:
    # Get summary statistics
    summary = get_enrichment_summary(session)
    print(f"Enriched: {summary['enriched_districts']} districts")

    # Print full report
    print_enrichment_report(session)
```

## JSON Export (Backward Compatibility)

To export database contents back to JSON format:

```bash
# Export consolidated JSON file
python infrastructure/database/export_json.py

# Export individual files per district
python infrastructure/database/export_json.py --individual-files

# Export specific year
python infrastructure/database/export_json.py --year 2024-25

# Include reference CSV
python infrastructure/database/export_json.py --include-reference-csv
```

## Common Tasks

### Check Database Status

```bash
# Connect to database
psql -d learning_connection_time

# View record counts
SELECT
    (SELECT COUNT(*) FROM districts) as districts,
    (SELECT COUNT(*) FROM state_requirements) as states,
    (SELECT COUNT(*) FROM bell_schedules) as schedules,
    (SELECT COUNT(DISTINCT district_id) FROM bell_schedules) as enriched_districts;
```

### Add New Bell Schedule

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import add_bell_schedule

with session_scope() as session:
    add_bell_schedule(
        session,
        district_id="1234567",
        year="2024-25",
        grade_level="elementary",
        instructional_minutes=360,
        start_time="8:30 AM",
        end_time="3:30 PM",
        lunch_duration=30,
        passing_periods=15,
        method="human_provided",
        confidence="high",
        schools_sampled=["Main Elementary", "Central Elementary"],
        source_urls=["https://example.com/bell-schedule.pdf"]
    )
```

### Update Enrichment Stats

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report

with session_scope() as session:
    print_enrichment_report(session)
```

## Troubleshooting

### Connection Refused

```bash
# Check if PostgreSQL is running
brew services list | grep postgresql

# Start if needed
brew services start postgresql@16
```

### Database Doesn't Exist

```bash
# Create the database
createdb learning_connection_time
```

### Missing Tables

```bash
# Reapply schema
psql -d learning_connection_time -f infrastructure/database/schema.sql
```

### psycopg2 Not Installed

```bash
pip install psycopg2-binary
```

## Performance Notes

- District lookups by ID: < 1ms
- Top N queries by enrollment: < 10ms
- Full enrichment summary: < 100ms
- JSON export (all districts): < 1s

## File Locations

| File | Purpose |
|------|---------|
| `infrastructure/database/schema.sql` | Database schema DDL |
| `infrastructure/database/models.py` | SQLAlchemy ORM models |
| `infrastructure/database/connection.py` | Connection utilities |
| `infrastructure/database/queries.py` | High-level query functions |
| `infrastructure/database/export_json.py` | JSON export utility |
| `infrastructure/database/migrations/import_all_data.py` | Data migration script |
| `docs/DATABASE_MIGRATION_NOTES.md` | Migration working notes |

---

**Last Updated**: December 25, 2025
