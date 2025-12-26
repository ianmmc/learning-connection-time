#!/usr/bin/env python3
"""
Export current database to SQL dump for Docker migration.

This script exports the current Homebrew PostgreSQL database to a SQL file
that can be imported into the Docker container.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.database.connection import get_engine
from sqlalchemy import text, create_engine as create_engine_direct


def export_database():
    """Export database using Python instead of pg_dump."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path(__file__).parent / "backup" / f"learning_connection_time_{timestamp}.sql"

    print(f"Exporting database to: {backup_file}")

    # Connect directly to Homebrew PostgreSQL (no password, system user)
    import os
    user = os.getenv("USER", "postgres")
    homebrew_url = f"postgresql://{user}@localhost:5432/learning_connection_time"

    print(f"Connecting to Homebrew PostgreSQL as user: {user}")

    engine = create_engine_direct(homebrew_url)

    with open(backup_file, 'w') as f:
        # Export schema and data using Python
        with engine.connect() as conn:
            # Get all table data
            tables = ['state_requirements', 'districts', 'bell_schedules', 'lct_calculations', 'data_lineage']

            f.write("-- Database export for Docker migration\n")
            f.write(f"-- Exported: {datetime.now().isoformat()}\n")
            f.write("-- Source: Homebrew PostgreSQL\n\n")

            for table in tables:
                print(f"Exporting table: {table}")

                # Get row count
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = count_result.scalar()

                if count == 0:
                    print(f"  Skipping empty table: {table}")
                    continue

                print(f"  Rows: {count}")

                # Export table data
                f.write(f"-- Table: {table} ({count} rows)\n")

                # Get column names
                col_result = conn.execute(text(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = '{table}'
                    ORDER BY ordinal_position
                """))
                columns = [row[0] for row in col_result]

                # Export rows
                result = conn.execute(text(f"SELECT * FROM {table}"))
                for row in result:
                    # Build INSERT statement
                    values = []
                    for val in row:
                        if val is None:
                            values.append("NULL")
                        elif isinstance(val, str):
                            # Escape single quotes
                            escaped = val.replace("'", "''")
                            values.append(f"'{escaped}'")
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        elif isinstance(val, dict):
                            # JSONB columns
                            import json
                            escaped = json.dumps(val).replace("'", "''")
                            values.append(f"'{escaped}'::jsonb")
                        elif isinstance(val, list):
                            # Array columns
                            import json
                            escaped = json.dumps(val).replace("'", "''")
                            values.append(f"'{escaped}'::jsonb")
                        else:
                            values.append(f"'{str(val)}'")

                    insert = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(values)});\n"
                    f.write(insert)

                f.write("\n")

    print(f"\nExport complete: {backup_file}")
    print(f"File size: {backup_file.stat().st_size / 1024:.1f} KB")

    return backup_file


if __name__ == "__main__":
    try:
        export_database()
    except Exception as e:
        print(f"Export failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
