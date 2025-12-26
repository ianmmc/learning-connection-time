#!/usr/bin/env python3
"""
Import database backup into Docker PostgreSQL container.

This script imports the SQL dump from Homebrew PostgreSQL into the Docker container.
Run this after starting the Docker container with `docker-compose up -d`.
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime


def get_latest_backup() -> Path:
    """Find the most recent backup file."""
    backup_dir = Path(__file__).parent / "backup"
    backups = list(backup_dir.glob("learning_connection_time_*.sql"))

    if not backups:
        print("No backup files found in infrastructure/database/docker/backup/")
        print("Run export_database.py first to create a backup.")
        sys.exit(1)

    # Sort by modification time, newest first
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return backups[0]


def import_to_docker(backup_file: Path):
    """Import SQL dump into Docker container."""

    print(f"Importing database from: {backup_file}")
    print(f"File size: {backup_file.stat().st_size / 1024:.1f} KB")
    print(f"Modified: {datetime.fromtimestamp(backup_file.stat().st_mtime)}")

    # Check if Docker container is running
    try:
        result = subprocess.run(
            ["docker-compose", "ps", "-q", "postgres"],
            capture_output=True,
            text=True,
            check=True
        )
        if not result.stdout.strip():
            print("\nError: Docker container is not running")
            print("Start it with: docker-compose up -d")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\nError checking Docker status: {e}")
        print("Make sure Docker Desktop is running and docker-compose is available")
        sys.exit(1)

    print("\n✓ Docker container is running")

    # Import data using psql in the container
    print("\nImporting data...")
    try:
        with open(backup_file, 'r') as f:
            subprocess.run(
                [
                    "docker-compose", "exec", "-T", "postgres",
                    "psql", "-U", "lct_user", "-d", "learning_connection_time"
                ],
                stdin=f,
                check=True
            )
        print("\n✓ Import successful!")

    except subprocess.CalledProcessError as e:
        print(f"\nError during import: {e}")
        sys.exit(1)

    # Verify data was imported
    print("\nVerifying import...")
    try:
        result = subprocess.run(
            [
                "docker-compose", "exec", "-T", "postgres",
                "psql", "-U", "lct_user", "-d", "learning_connection_time",
                "-c", "SELECT COUNT(*) FROM districts;"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)

        result = subprocess.run(
            [
                "docker-compose", "exec", "-T", "postgres",
                "psql", "-U", "lct_user", "-d", "learning_connection_time",
                "-c", "SELECT COUNT(*) FROM bell_schedules;"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)

    except subprocess.CalledProcessError as e:
        print(f"Verification failed: {e}")
        sys.exit(1)

    print("\n✅ Database successfully imported to Docker!")
    print("\nNext steps:")
    print("1. Test connection: python3 infrastructure/database/connection.py")
    print("2. Run tests: python3 infrastructure/database/test_infrastructure.py")
    print("3. Continue enrichment campaign!")


if __name__ == "__main__":
    try:
        backup_file = get_latest_backup()
        import_to_docker(backup_file)
    except KeyboardInterrupt:
        print("\nImport cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\nImport failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
