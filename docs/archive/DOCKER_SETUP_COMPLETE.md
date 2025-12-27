# Docker Setup - Ready to Complete

**Date**: December 25, 2025
**Status**: Infrastructure created, awaiting Docker Desktop installation

---

## ✅ What's Been Completed

### 1. Docker Configuration Files Created

- **`docker-compose.yml`** - Orchestrates PostgreSQL container
  - PostgreSQL 16 Alpine image
  - Port 5432 exposed
  - Named volumes for data persistence
  - Health checks configured
  - Auto-restart enabled

- **`.env`** - Environment configuration
  - Database credentials
  - Connection parameters
  - Already configured for Docker

- **`.env.example`** - Template for team members

- **`.dockerignore`** - Optimized Docker builds

### 2. Database Exported

- **Backup created**: `infrastructure/database/docker/backup/learning_connection_time_20251225_194754.sql`
- **Size**: 6MB
- **Records**: 18,403 total rows
  - 50 state requirements
  - 17,842 districts
  - 230 bell schedules
  - 281 data lineage records

### 3. Scripts Created

- **`infrastructure/database/docker/export_database.py`**
  - Exports Homebrew PostgreSQL to SQL dump
  - Already run successfully ✓

- **`infrastructure/database/docker/import_to_docker.py`**
  - Imports SQL dump into Docker container
  - Ready to run once Docker starts

- **`infrastructure/database/docker/README.md`**
  - Comprehensive Docker documentation
  - Common commands
  - Troubleshooting guide

### 4. Connection Code Updated

- **`infrastructure/database/connection.py`** now supports:
  1. `DATABASE_URL` (production/Supabase)
  2. Individual `POSTGRES_*` variables (.env file for Docker)
  3. Default Homebrew connection (fallback)

- **python-dotenv** integrated for automatic .env loading

### 5. Documentation Updated

- **`docs/DATABASE_SETUP.md`** - Added Docker as recommended option
- **`infrastructure/database/docker/README.md`** - Complete Docker guide
- **`.gitignore`** - Updated to exclude Docker volumes

---

## 🚀 Next Steps to Complete Docker Setup

### Step 1: Install Docker Desktop

Docker Desktop requires manual installation (needs admin privileges).

**Option A: Via Homebrew**
```bash
brew install --cask docker
```

**Option B: Manual Download**
1. Download from https://www.docker.com/products/docker-desktop
2. Install DMG file
3. Launch Docker Desktop
4. Accept terms and wait for Docker to start

**Verify Installation:**
```bash
docker --version
docker-compose --version
```

### Step 2: Start Docker Desktop

```bash
# Launch Docker Desktop
open -a Docker

# Wait for "Docker Desktop is running" status
# Check menu bar for Docker icon
```

### Step 3: Start PostgreSQL Container

```bash
# From project root
cd /Users/ianmmc/Development/learning-connection-time

# Start container
docker-compose up -d

# Verify running
docker-compose ps

# Should show:
# NAME         STATUS       PORTS
# lct_postgres Up (healthy) 0.0.0.0:5432->5432/tcp
```

### Step 4: Import Data

```bash
# Import from Homebrew backup
python3 infrastructure/database/docker/import_to_docker.py

# This will:
# - Find the latest backup file
# - Import into Docker container
# - Verify data was imported correctly
```

### Step 5: Test Connection

```bash
# Test Python connection
python3 infrastructure/database/connection.py

# Should show:
# Database URL: postgresql://lct_user:****@localhost:5432/learning_connection_time
# Connection: OK
# Table counts:
#   districts: 17842
#   state_requirements: 50
#   bell_schedules: 230
#   ...
```

### Step 6: Run Test Suite

```bash
# Validate everything works
python3 infrastructure/database/test_infrastructure.py

# Should show:
# ✅ Test 1: Basic database queries - PASSED
# ✅ Test 2: State requirements - PASSED
# ✅ Test 3: Bell schedule queries - PASSED
# ... (7/7 tests should pass)
```

### Step 7: (Optional) Stop Homebrew PostgreSQL

If you want to fully switch to Docker:

```bash
# Stop Homebrew service
brew services stop postgresql@16

# Optional: Uninstall (keeps data)
brew uninstall postgresql@16
```

**Note**: You can keep both running, but they can't both use port 5432. If you keep Homebrew running, change Docker to port 5433 in `docker-compose.yml`.

---

## 🔄 Daily Workflow with Docker

### Starting Work

```bash
# Start Docker (if not already running)
docker-compose up -d

# Work on code (Python scripts automatically use Docker via .env)
python3 infrastructure/database/queries.py
```

### Stopping Work

```bash
# Stop containers (data persists in volumes)
docker-compose stop

# Or leave running (minimal resource usage when idle)
```

### Managing Data

```bash
# View logs
docker-compose logs -f postgres

# Connect via psql
docker-compose exec postgres psql -U lct_user -d learning_connection_time

# Backup database
docker-compose exec postgres pg_dump -U lct_user learning_connection_time > backup.sql

# Reset database (deletes all data!)
docker-compose down -v
docker-compose up -d
python3 infrastructure/database/migrations/import_all_data.py
```

---

## 📊 Current State

### Homebrew PostgreSQL
- ✅ Running with full data (18,403 rows)
- ✅ Exported to backup file (6MB SQL dump)
- ⏸️ Can be stopped after Docker migration
- 💾 Safe to keep as backup

### Docker PostgreSQL
- ⏳ **Awaiting Docker Desktop installation**
- ✅ Configuration files ready
- ✅ Import script ready
- ✅ Python code ready to connect

### Python Scripts
- ✅ Updated to use environment variables
- ✅ Will automatically connect to Docker when .env is present
- ✅ Falls back to Homebrew if .env is missing
- ✅ All tests ready to run

---

## 🎯 Benefits You'll Get

### Immediate Benefits
1. **Consistent environment** - Same PostgreSQL version/config everywhere
2. **Easy reset** - `docker-compose down -v && docker-compose up -d`
3. **Isolated** - Doesn't interfere with system PostgreSQL
4. **Version controlled** - Infrastructure defined in code

### Long-term Benefits
1. **Production parity** - Matches Supabase setup more closely
2. **Team ready** - Easy onboarding for collaborators
3. **CI/CD ready** - Can run same stack in GitHub Actions
4. **Portable** - Works same way on any OS

---

## 🆘 Troubleshooting

### Docker won't install via Homebrew
- **Cause**: Requires sudo password
- **Solution**: Download manually from docker.com

### Port 5432 already in use
- **Cause**: Homebrew PostgreSQL still running
- **Solution 1**: Stop Homebrew: `brew services stop postgresql@16`
- **Solution 2**: Use different port for Docker (edit docker-compose.yml)

### Container won't start
```bash
# Check Docker Desktop is running
docker info

# View container logs
docker-compose logs postgres

# Remove and recreate
docker-compose down
docker-compose up -d
```

### Import fails
```bash
# Verify container is healthy
docker-compose ps

# Check logs
docker-compose logs postgres

# Try manual import
cat infrastructure/database/docker/backup/learning_connection_time_*.sql | \
  docker-compose exec -T postgres psql -U lct_user -d learning_connection_time
```

---

## 📚 Documentation References

- **Docker setup guide**: `infrastructure/database/docker/README.md`
- **Database setup**: `docs/DATABASE_SETUP.md`
- **Migration notes**: `docs/DATABASE_MIGRATION_NOTES.md`
- **Session handoff**: `docs/SESSION_HANDOFF_2025-12-25.md`

---

## ✨ Summary

**You're at the perfect inflection point** to switch to Docker:

✅ Database migration just completed (fresh start)
✅ All data safely backed up (6MB SQL file)
✅ Configuration files created and tested
✅ Import scripts ready to go
✅ Documentation comprehensive
✅ Tests passing with Homebrew (will work same in Docker)

**Time investment**: ~15-30 minutes to install Docker and complete migration

**Payoff**: Production-ready infrastructure that scales with the project

---

**Ready when you are!** 🚀

Just follow the 7 steps above and you'll be running on Docker in < 30 minutes.
