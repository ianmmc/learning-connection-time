"""Governance database — the acquisition pipeline's OWN isolated Postgres DB (REQ-103).

Deliberately self-contained: this module does NOT import `infrastructure.database` (the production
LCT side). Two databases, two connection modules, zero coupling — which is exactly what the
import-linter contract enforces (acquisition must not import the LCT layer) and what the
"isolated governance DB" decision calls for. See PIPELINE_GOVERNANCE_AND_STATE.md §1a/§10.

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


# Additive, idempotent column migrations (+ their one-time idempotent backfills) for the never-dropped
# PRECIOUS tables: create_all() creates a missing table but does NOT add a new column to a table that
# already exists, so a column added to a model after the table was first created must be ALTERed in. Raw
# SQL by table name (no stage-module import — the layering contract is about imports, not table names).
# Keep additive-only; never drop/rename here. Backfills must be guarded so re-running is a no-op.
_PRECIOUS_ALTERS = [
    "ALTER TABLE label ADD COLUMN IF NOT EXISTS facets_json text",   # REQ-114 (V2 facet questionnaire)
    "ALTER TABLE extraction_request ADD COLUMN IF NOT EXISTS executed_ref text",   # REQ-118 (execution lineage)
    "ALTER TABLE extraction_request ADD COLUMN IF NOT EXISTS executed_at text",    # REQ-118 (execution lineage)
    "ALTER TABLE batch_district ADD COLUMN IF NOT EXISTS followup_json json",      # #161 (7->3 seed URLs)
    "ALTER TABLE batch ADD COLUMN IF NOT EXISTS abandoned_at text",                # #168 (terminal abandon audit)
    "ALTER TABLE batch ADD COLUMN IF NOT EXISTS abandoned_by text",                # #168
    "ALTER TABLE batch ADD COLUMN IF NOT EXISTS abandon_reason text",              # #168
    "ALTER TABLE batch ADD COLUMN IF NOT EXISTS first_approved_at text",           # #168 review (durable ever-approved)
    "ALTER TABLE batch ADD COLUMN IF NOT EXISTS discovery_scope text DEFAULT 'domain'",  # #164 (scope-pure batches: domain | geo)
    # #164 review: per-district admission-source audit trail + geo render tokens. Without these the
    # DB round-trip (create_batch -> to_working_doc) silently dropped both, and a geo batch ran
    # UNSCOPED queries (#227 class). Nullable, additive, going-forward only.
    "ALTER TABLE batch_district ADD COLUMN IF NOT EXISTS domain_source text",
    "ALTER TABLE batch_district ADD COLUMN IF NOT EXISTS geo_json json",
    # Backfill: any currently-approved batch was approved at least once. Guarded (only fills NULLs) →
    # idempotent no-op on re-run. Covers pre-existing rows so the abandon guard + attempted-set logic
    # see their ever-approved history. (A row reopened-and-left-draft before this column existed can't
    # be recovered from approved_at, but none exist in practice; going forward first_approved_at is durable.)
    "UPDATE batch SET first_approved_at = approved_at WHERE first_approved_at IS NULL AND approved_at IS NOT NULL",
    # #148: first-class run-kind for extractions, replacing the `handoff_hash NOT LIKE '%-image'` hack.
    "ALTER TABLE extraction ADD COLUMN IF NOT EXISTS run_kind text NOT NULL DEFAULT 'production'",
    # #618 (epic #617): the benchmark DISPATCH type. Defaults production so every existing frozen
    # handoff and open draft reads as production — batch_00000's historical handoffs are retagged
    # explicitly by the #617 backfill, never by this default.
    "ALTER TABLE dispatch_draft ADD COLUMN IF NOT EXISTS dispatch_type text NOT NULL DEFAULT 'production'",
    "ALTER TABLE handoff ADD COLUMN IF NOT EXISTS dispatch_type text NOT NULL DEFAULT 'production'",
    # #617 Phase 2c: the DECLARED redo lever. Deliberately NULLABLE with NO default and NO backfill —
    # NULL means "not declared" and common/batch_types.redoes_attempted falls back to the historical
    # `batch_type == 'follow-up'` rule, so every existing batch (batch_00000's frozen gt:// artifacts
    # above all) keeps byte-identical reconcile behavior. Only new composers declare a value.
    "ALTER TABLE batch ADD COLUMN IF NOT EXISTS redo_attempted boolean",
    # #120: reps left unsent by the mode-stability early-exit (detail lives in the disk receipt).
    "ALTER TABLE extraction ADD COLUMN IF NOT EXISTS n_reps_skipped integer NOT NULL DEFAULT 0",
    # STAGE8 §2a.6: per-fact council evidence (verbatim quote / locus / stated minutes) from the v2
    # extraction prompt. Additive, NULL for pre-v2 rows (going-forward only, no backfill).
    "ALTER TABLE school_fact ADD COLUMN IF NOT EXISTS evidence_json text",
    # #254: per-fact school-year + applies-to READINGS from the v3 extraction prompt. Additive, NULL
    # for pre-v3 rows (going-forward only, no backfill — the evidence_json precedent above).
    "ALTER TABLE school_fact ADD COLUMN IF NOT EXISTS school_year text",
    "ALTER TABLE school_fact ADD COLUMN IF NOT EXISTS campus_names_json text",
    "ALTER TABLE school_fact ADD COLUMN IF NOT EXISTS applies_to text",
    # #213 / PR #220 review: DB-enforce the config_pointer singleton (id = 1). create_all applies the
    # model's CheckConstraint on a FRESH table; this covers a table created before the constraint existed.
    # Guarded by a pg_constraint lookup → idempotent no-op on every re-run (additive, never drops).
    """DO $$ BEGIN
        IF to_regclass('config_pointer') IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'config_pointer_singleton') THEN
            ALTER TABLE config_pointer ADD CONSTRAINT config_pointer_singleton CHECK (id = 1);
        END IF;
    END $$""",
    # Backfill: the ONLY probe ever produced was the `-image` vision variant (image_handoff_variant's
    # default council). Flip those legacy rows so the console filter matches pre-migration behavior.
    # Guarded (only flips still-default rows) → a no-op on every re-run. Real handoff hashes are 12 hex
    # chars and never contain '-', so this can't misclassify a production run.
    "UPDATE extraction SET run_kind = 'probe' WHERE handoff_hash LIKE '%-image' AND run_kind = 'production'",
    # #240 review (#234's widened dedup + #233's withdraw scan): serve the natural-ask lookup with a
    # composite index — the OR-on-status clause otherwise degrades to a district-wide scan per detected
    # request. create_all builds it on FRESH tables (declared on the model); this covers existing DBs.
    "CREATE INDEX IF NOT EXISTS ix_extraction_request_ask "
    "ON extraction_request (district_id, target, altitude, route)",
    # PR #248 review: gate_mode.configured_mode is NULLABLE (NULL = inherit the global default) so the
    # #211 license writer never materializes a configured toggle the human didn't set. A table created
    # under the earlier NOT-NULL + server-default model must shed both. DROP NOT NULL / DROP DEFAULT are
    # idempotent in Postgres (no-ops when already absent); to_regclass guards a missing table.
    """DO $$ BEGIN
        IF to_regclass('gate_mode') IS NOT NULL THEN
            ALTER TABLE gate_mode ALTER COLUMN configured_mode DROP NOT NULL;
            ALTER TABLE gate_mode ALTER COLUMN configured_mode DROP DEFAULT;
        END IF;
    END $$""",
]


def init_precious_schema() -> None:
    """Create the PRECIOUS tables registered on Base.metadata, if absent, + apply additive column
    migrations. Idempotent; never drops. The regenerable cache tables are NOT here — the ingest manages
    those via its own DDL. NOTE: the CALLER must import the STAGE-level precious model modules first (so
    they register on Base.metadata) — common/ deliberately does not import stage modules (layering
    contract). COMMON-level precious models are imported HERE (a common→common import is inside the base
    layer, so the contract permits it): otherwise their registration depends on every init caller
    remembering an import, and a forgotten one surfaces as 'relation does not exist' at first write
    (#217 review — calibration_event was registered nowhere in the live app)."""
    from sqlalchemy import text as _text
    from infrastructure.acquisition.common import calibration  # noqa: F401  (registers calibration_event; local: calibration imports this module)
    from infrastructure.acquisition.common import gate_mode  # noqa: F401  (registers gate_mode, #104; local: gate_mode imports this module)
    from infrastructure.acquisition.common import discovery_policy  # noqa: F401  (registers discovery_policy_event, #164)
    from infrastructure.acquisition.common import discovered_domain  # noqa: F401  (registers discovered_domain, #164)
    eng = get_engine()
    Base.metadata.create_all(eng)
    with eng.begin() as con:
        for ddl in _PRECIOUS_ALTERS:
            con.execute(_text(ddl))
