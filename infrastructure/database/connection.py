# infrastructure/database/connection.py
"""
Database connection management for Learning Connection Time project.

Provides connection pooling, session management, and initialization utilities.
Uses Docker PostgreSQL (not Homebrew) - see .env for credentials.

IMPORTANT: Run `docker-compose up -d` before database operations.
"""

import os
import subprocess
import sys
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, will use system environment variables only
    pass


def _check_docker_postgres() -> None:
    """
    Check if Docker PostgreSQL container is running.
    Warns if Docker is not running or if Homebrew PostgreSQL might be in use.
    """
    # Check if we're using Docker credentials
    postgres_user = os.getenv("POSTGRES_USER", "")
    is_docker_config = postgres_user in ("lct_user", "postgres") and os.getenv("POSTGRES_PASSWORD")

    if not is_docker_config:
        return  # Not using Docker config, skip check

    try:
        # Check if Docker is running
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=lct_postgres", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            print(
                "\n⚠️  WARNING: Docker does not appear to be running.\n"
                "   The .env file is configured for Docker PostgreSQL (lct_user).\n"
                "   Run: docker-compose up -d\n",
                file=sys.stderr
            )
            return

        if "lct_postgres" not in result.stdout:
            print(
                "\n⚠️  WARNING: Docker PostgreSQL container (lct_postgres) is not running.\n"
                "   The .env file expects Docker PostgreSQL, not Homebrew.\n"
                "   Run: docker-compose up -d\n",
                file=sys.stderr
            )

    except FileNotFoundError:
        # Docker CLI not installed
        print(
            "\n⚠️  WARNING: Docker CLI not found.\n"
            "   The .env file is configured for Docker PostgreSQL.\n"
            "   Install Docker Desktop and run: docker-compose up -d\n",
            file=sys.stderr
        )
    except subprocess.TimeoutExpired:
        pass  # Docker command timed out, skip check
    except Exception:
        pass  # Don't fail on check errors


# Run Docker check on module import (only once)
_docker_check_done = False

# Default connection parameters
DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5432"
DEFAULT_DB = "learning_connection_time"
DEFAULT_USER = os.getenv("USER", "postgres")  # Use system user as fallback
DEFAULT_PASSWORD = ""

# Global engine instance (created lazily)
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_database_url() -> str:
    """
    Get the database connection URL.

    Priority:
    1. DATABASE_URL environment variable (for production/cloud, e.g., Supabase)
    2. Build from individual components (POSTGRES_HOST, POSTGRES_PORT, etc.)
    3. Default local development URL

    Individual environment variables:
    - POSTGRES_HOST: Database host (default: localhost)
    - POSTGRES_PORT: Database port (default: 5432)
    - POSTGRES_DB: Database name (default: learning_connection_time)
    - POSTGRES_USER: Database user (default: system user)
    - POSTGRES_PASSWORD: Database password (default: empty)

    Returns:
        Database connection URL string
    """
    # Priority 1: Full connection string (production/cloud)
    if os.getenv("DATABASE_URL"):
        return os.getenv("DATABASE_URL")

    # Priority 2: Build from individual components (Docker/.env file)
    host = os.getenv("POSTGRES_HOST", DEFAULT_HOST)
    port = os.getenv("POSTGRES_PORT", DEFAULT_PORT)
    database = os.getenv("POSTGRES_DB", DEFAULT_DB)
    user = os.getenv("POSTGRES_USER", DEFAULT_USER)
    password = os.getenv("POSTGRES_PASSWORD", DEFAULT_PASSWORD)

    # Build connection string
    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    else:
        return f"postgresql://{user}@{host}:{port}/{database}"


def get_engine(database_url: Optional[str] = None, echo: bool = False) -> Engine:
    """
    Get or create the SQLAlchemy engine.

    Uses connection pooling for efficient database access.

    Args:
        database_url: Optional override for database URL
        echo: If True, log all SQL statements (useful for debugging)

    Returns:
        SQLAlchemy Engine instance
    """
    global _engine, _docker_check_done

    # Check Docker on first connection attempt
    if not _docker_check_done:
        _docker_check_done = True
        _check_docker_postgres()

    if _engine is None or database_url is not None:
        url = database_url or get_database_url()
        _engine = create_engine(
            url,
            echo=echo,
            pool_size=5,  # Maximum number of connections in pool
            max_overflow=10,  # Additional connections beyond pool_size
            pool_timeout=30,  # Seconds to wait for available connection
            pool_recycle=1800,  # Recycle connections after 30 minutes
        )

    return _engine


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker:
    """
    Get the session factory.

    Args:
        engine: Optional engine instance (uses global if not provided)

    Returns:
        SQLAlchemy sessionmaker instance
    """
    global _SessionLocal

    if _SessionLocal is None or engine is not None:
        eng = engine or get_engine()
        _SessionLocal = sessionmaker(
            bind=eng,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    return _SessionLocal


def get_session() -> Session:
    """
    Create a new database session.

    Note: Caller is responsible for closing the session.
    For automatic cleanup, use the session_scope() context manager.

    Returns:
        New SQLAlchemy Session instance
    """
    SessionLocal = get_session_factory()
    return SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of operations.

    Usage:
        with session_scope() as session:
            session.add(new_district)
            # Commits automatically on success
            # Rolls back on exception

    Yields:
        SQLAlchemy Session instance
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Optional[Engine] = None) -> None:
    """
    Initialize the database schema.

    Creates all tables defined in models.py if they don't exist.
    For a fresh database, run schema.sql instead for the full schema
    including triggers, views, and comments.

    Args:
        engine: Optional engine instance (uses global if not provided)
    """
    from .models import Base

    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)


def test_connection(engine: Optional[Engine] = None) -> bool:
    """
    Test the database connection.

    Args:
        engine: Optional engine instance (uses global if not provided)

    Returns:
        True if connection successful, False otherwise
    """
    eng = engine or get_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


def get_table_counts(engine: Optional[Engine] = None) -> dict:
    """
    Get row counts for all main tables.

    Useful for verifying data migration.

    Args:
        engine: Optional engine instance (uses global if not provided)

    Returns:
        Dictionary mapping table names to row counts
    """
    eng = engine or get_engine()
    tables = ["districts", "state_requirements", "bell_schedules", "lct_calculations", "data_lineage"]
    counts = {}

    with eng.connect() as conn:
        for table in tables:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = result.scalar()

    return counts


def reset_database(engine: Optional[Engine] = None, confirm: bool = False) -> bool:
    """
    Drop and recreate all tables.

    WARNING: This will delete all data!

    Args:
        engine: Optional engine instance (uses global if not provided)
        confirm: Must be True to proceed (safety check)

    Returns:
        True if reset successful, False otherwise
    """
    if not confirm:
        print("Database reset requires confirm=True")
        return False

    from .models import Base

    eng = engine or get_engine()
    try:
        Base.metadata.drop_all(bind=eng)
        Base.metadata.create_all(bind=eng)
        return True
    except Exception as e:
        print(f"Database reset failed: {e}")
        return False


# Convenience function for CLI scripts
def print_connection_info():
    """Print current database connection information."""
    url = get_database_url()
    # Mask password if present
    if "@" in url:
        parts = url.split("@")
        if ":" in parts[0]:
            user_pass = parts[0].rsplit(":", 1)
            if len(user_pass) == 2:
                url = f"{user_pass[0]}:****@{parts[1]}"

    print(f"Database URL: {url}")

    if test_connection():
        print("Connection: OK")
        counts = get_table_counts()
        print("Table counts:")
        for table, count in counts.items():
            print(f"  {table}: {count}")
    else:
        print("Connection: FAILED")


if __name__ == "__main__":
    # Quick test when run directly
    print_connection_info()
