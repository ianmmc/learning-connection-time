# Docker Setup for Learning Connection Time Database

## Overview

This directory contains Docker configuration and utilities for running PostgreSQL in a container.

**Benefits of Docker:**
- Consistent environment across development/production
- Easy setup and teardown
- Isolated from system PostgreSQL
- Version controlled infrastructure
- Matches production (Supabase) more closely

---

## Quick Start

### 1. Install Docker Desktop

**macOS (via Homebrew):**
```bash
brew install --cask docker
```

**Manual installation:**
- Download from https://www.docker.com/products/docker-desktop
- Install and launch Docker Desktop
- Wait for Docker to start (icon in menu bar)

### 2. Start PostgreSQL Container

```bash
# From project root
docker-compose up -d

# Verify running
docker-compose ps

# Check logs
docker-compose logs postgres
```

### 3. Import Existing Data

**If you have Homebrew PostgreSQL with data:**

```bash
# Export from Homebrew (already done - see backup/ directory)
python3 infrastructure/database/docker/export_database.py

# Import to Docker
python3 infrastructure/database/docker/import_to_docker.py
```

**For fresh start:**
```bash
# Just run migrations
python3 infrastructure/database/migrations/import_all_data.py
```

### 4. Verify Setup

```bash
# Test connection
python3 infrastructure/database/connection.py

# Run test suite
python3 infrastructure/database/test_infrastructure.py
```

---

## Files in This Directory

- **README.md** - This file
- **export_database.py** - Export Homebrew PostgreSQL to SQL
- **import_to_docker.py** - Import SQL dump into Docker container
- **backup/** - Database backups and exports

---

## Environment Variables

Create `.env` file in project root (already created):

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=learning_connection_time
POSTGRES_USER=lct_user
POSTGRES_PASSWORD=lct_password
```

**For production (Supabase):**
```bash
DATABASE_URL=postgresql://user:password@host:port/database
```

The connection code automatically uses environment variables.

---

## Common Commands

### Container Management

```bash
# Start containers
docker-compose up -d

# Stop containers (keeps data)
docker-compose stop

# Remove containers (keeps data in volumes)
docker-compose down

# Remove everything including data volumes
docker-compose down -v

# Restart containers
docker-compose restart

# View logs
docker-compose logs -f postgres
```

### Database Access

```bash
# Connect via psql
docker-compose exec postgres psql -U lct_user -d learning_connection_time

# Run SQL file
docker-compose exec -T postgres psql -U lct_user -d learning_connection_time < file.sql

# Backup database
docker-compose exec postgres pg_dump -U lct_user learning_connection_time > backup.sql

# Restore database
docker-compose exec -T postgres psql -U lct_user -d learning_connection_time < backup.sql
```

### Python Scripts

```bash
# All Python scripts use .env automatically
python3 infrastructure/database/queries.py
python3 infrastructure/database/test_infrastructure.py
python3 infrastructure/database/example_workflow.py
```

---

## Troubleshooting

### Docker not starting

- Open Docker Desktop application
- Wait for "Docker Desktop is running" status
- Check System Preferences > Security if blocked

### Connection refused

```bash
# Check if container is running
docker-compose ps

# Check if PostgreSQL is healthy
docker-compose exec postgres pg_isready -U lct_user

# View logs
docker-compose logs postgres
```

### Port already in use

If Homebrew PostgreSQL is still running on port 5432:

**Option 1: Stop Homebrew PostgreSQL**
```bash
brew services stop postgresql@16
```

**Option 2: Use different port for Docker**
Edit `docker-compose.yml`:
```yaml
ports:
  - "5433:5432"  # External:Internal
```

Then update `.env`:
```bash
POSTGRES_PORT=5433
```

### Permission errors

```bash
# Fix volume permissions
docker-compose down
docker volume rm lct_postgres_data
docker-compose up -d
```

---

## Data Migration Strategy

### From Homebrew to Docker

1. **Export current data** (already done):
   ```bash
   python3 infrastructure/database/docker/export_database.py
   ```

2. **Start Docker container**:
   ```bash
   docker-compose up -d
   ```

3. **Import data**:
   ```bash
   python3 infrastructure/database/docker/import_to_docker.py
   ```

4. **Verify**:
   ```bash
   python3 infrastructure/database/test_infrastructure.py
   ```

5. **Stop Homebrew PostgreSQL** (optional):
   ```bash
   brew services stop postgresql@16
   ```

### Fresh Start (No Existing Data)

1. **Start Docker**:
   ```bash
   docker-compose up -d
   ```

2. **Run migrations**:
   ```bash
   python3 infrastructure/database/migrations/import_all_data.py
   ```

---

## Production Deployment

For Supabase or other cloud PostgreSQL:

1. **Set DATABASE_URL** in production environment
2. **Run schema.sql** to create tables
3. **Run migrations** to import data
4. **No Docker needed** - use cloud database directly

The same Python code works locally (Docker) and production (cloud).

---

## Backup Strategy

### Automated Backups

The `backup/` directory contains SQL exports. You can create cron jobs to automate:

```bash
# Daily backup
0 2 * * * docker-compose exec postgres pg_dump -U lct_user learning_connection_time > /path/to/backup/$(date +\%Y\%m\%d).sql
```

### Manual Backups

```bash
# Using export script
python3 infrastructure/database/docker/export_database.py

# Using pg_dump directly
docker-compose exec postgres pg_dump -U lct_user -d learning_connection_time -f /backup/manual_backup.sql
```

Backups are stored in `infrastructure/database/docker/backup/` which is volume-mounted in the container.

---

## Volume Management

Docker volumes persist data across container restarts.

```bash
# List volumes
docker volume ls | grep lct

# Inspect volume
docker volume inspect lct_postgres_data

# Remove volume (deletes all data!)
docker-compose down -v
```

**Volume location**: Docker manages volumes internally. Use `docker volume inspect` to find the mount point.

---

## Development Workflow

1. **Start Docker** (once per session):
   ```bash
   docker-compose up -d
   ```

2. **Work on code** (connection.py loads .env automatically)

3. **Run tests**:
   ```bash
   python3 infrastructure/database/test_infrastructure.py
   ```

4. **Stop when done** (optional):
   ```bash
   docker-compose stop
   ```

Data persists in volumes, so you can stop/start without data loss.

---

## Switching Between Homebrew and Docker

**Connection Priority** (see connection.py):
1. DATABASE_URL environment variable (production)
2. Individual POSTGRES_* variables (.env file)
3. Default to Homebrew (localhost, system user)

**To use Homebrew**:
- Remove or rename `.env` file
- Or unset POSTGRES_* variables

**To use Docker**:
- Use `.env` file (already configured)
- Or set POSTGRES_* environment variables

**To use production**:
- Set DATABASE_URL environment variable

---

## Next Steps After Docker Setup

1. **Run test suite** to verify everything works
2. **Continue enrichment campaign** (Rhode Island next)
3. **Use database queries** instead of JSON files
4. **Export to JSON** when needed for sharing

---

**Documentation**: See `docs/DATABASE_SETUP.md` for full database documentation
**Tests**: See `infrastructure/database/test_infrastructure.py`
**Examples**: See `infrastructure/database/example_workflow.py`
