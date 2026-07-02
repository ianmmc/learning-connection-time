"""Governance database — the acquisition pipeline's OWN isolated Postgres DB (REQ-103).

Deliberately self-contained: this module does NOT import `infrastructure.database` (the production
LCT side). Two databases, two connection modules, zero coupling — which is exactly what the
import-linter contract enforces (acquisition must not import the LCT layer) and what the
"isolated governance DB" decision calls for. See PIPELINE_GOVERNANCE_AND_STATE_2026-06.md §1a/§10.

Holds: the PRECIOUS tables (label, cluster_split, and the future state_event) as SQLAlchemy models
on `Base`, plus the REGENERABLE signal/cross-stage cache tables that the Stage-5 ingest creates via
its own DDL (dropped + rebuilt each run). The drop+rebuild ingest runs against THIS database, so it
can never reach `districts` / `bell_schedules` / `lct_calculations` in the production DB.

Config (priority order):
  1. GOVERNANCE_DATABASE_URL  (full URL — cloud/prod, e.g. Supabase)
  2. GOVERNANCE_DB_{HOST,PORT,NAME,USER,PASSWORD}  (defaults target the local lct_postgres container)
"""
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


class Base(DeclarativeBase):
    """Declarative base for the governance DB's PRECIOUS tables (models live near their stage)."""


def governance_url() -> str:
    """Resolve the governance database URL (its own config namespace, never the LCT DB's)."""
    if os.getenv("GOVERNANCE_DATABASE_URL"):
        return os.environ["GOVERNANCE_DATABASE_URL"]
    host = os.getenv("GOVERNANCE_DB_HOST", "localhost")
    port = os.getenv("GOVERNANCE_DB_PORT", "5432")
    name = os.getenv("GOVERNANCE_DB_NAME", "governance")
    user = os.getenv("GOVERNANCE_DB_USER", "governance_user")
    password = os.getenv("GOVERNANCE_DB_PASSWORD", "governance_pw")
    auth = f"{user}:{password}" if password else user
    return f"postgresql://{auth}@{host}:{port}/{name}"


def get_engine(database_url: Optional[str] = None, echo: bool = False) -> Engine:
    """Get or create the cached governance engine. Pass database_url to point elsewhere (tests)."""
    global _engine, _SessionLocal
    if _engine is None or database_url is not None:
        _engine = create_engine(database_url or governance_url(), echo=echo,
                                pool_size=5, max_overflow=10, pool_timeout=30, pool_recycle=1800)
        _SessionLocal = None  # rebind the factory to the new engine
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Transactional scope: commit on success, rollback on error, always close."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Additive, idempotent column migrations for the never-dropped PRECIOUS tables: create_all() creates a
# missing table but does NOT add a new column to a table that already exists, so a column added to a model
# after the table was first created must be ALTERed in. Raw SQL by table name (no stage-module import — the
# layering contract is about imports, not table names). Keep additive-only; never drop/rename here.
_PRECIOUS_ALTERS = [
    "ALTER TABLE label ADD COLUMN IF NOT EXISTS facets_json text",   # REQ-114 (V2 facet questionnaire)
]


def init_precious_schema() -> None:
    """Create the PRECIOUS tables registered on Base.metadata, if absent, + apply additive column
    migrations. Idempotent; never drops. The regenerable cache tables are NOT here — the ingest manages
    those via its own DDL. NOTE: the CALLER must import the precious model modules first (so they register
    on Base.metadata) — common/ deliberately does not import stage modules (layering contract)."""
    from sqlalchemy import text as _text
    eng = get_engine()
    Base.metadata.create_all(eng)
    with eng.begin() as con:
        for ddl in _PRECIOUS_ALTERS:
            con.execute(_text(ddl))
