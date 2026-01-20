#!/usr/bin/env python3
"""
Apply migration 009: Update calculation_runs for temporal blending support.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from sqlalchemy import text

# Read the migration file
migration_file = project_root / "infrastructure" / "database" / "migrations" / "009_update_calculation_runs.sql"

with open(migration_file, 'r') as f:
    sql = f.read()

# Apply to database (execute as single block)
with session_scope() as session:
    try:
        session.execute(text(sql))
        session.commit()
        print("✅ Migration 009 applied successfully")
    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        session.rollback()
        sys.exit(1)
