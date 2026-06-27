# Archived: DB schema data dictionary (superseded 2026-06-27)

These two files (`database_schema_latest.md` + its `..._20251228T...md` timestamped twin — byte-identical)
were an **auto-generated snapshot of the database schema from 2025-12-28**. Archived because they were
**stale** (predated migrations 003–015; missing tables/columns — PROJECT_HISTORY "known latent issues" #19)
and **redundant** with the authoritative sources.

**Authoritative schema now:**
- `infrastructure/database/models.py` — the SQLAlchemy ORM models (the source of truth).
- `docs/DATABASE_SETUP.md` — the human-readable schema overview.

**To regenerate a fresh snapshot if ever wanted:** `python3 infrastructure/scripts/utilities/generate_data_dictionary.py`
(writes to `docs/data-dictionaries/` by default). The generator itself was kept; only the stale output was archived.
