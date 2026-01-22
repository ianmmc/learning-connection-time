#!/usr/bin/env python3
"""
Apply corrected temporal validation SQL migration.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from sqlalchemy import text

# Read the migration file
migration_file = project_root / "infrastructure" / "database" / "migrations" / "008_add_temporal_validation.sql"

with open(migration_file, 'r') as f:
    sql = f.read()

# Apply to database (execute as single block)
with session_scope() as session:
    try:
        session.execute(text(sql))
        session.commit()
        print("✅ Migration applied successfully")
    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        session.rollback()
        sys.exit(1)
