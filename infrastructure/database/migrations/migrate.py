#!/usr/bin/env python3
"""
Migration ledger + runner for Learning Connection Time.

Establishes a `schema_migrations` table that records which numbered migrations
(``NNN_*.sql``) have been applied, so the project can answer "what's applied?"
without guessing — the gap that allowed migration 014 to land half-applied.

Design choices:
- Each migration is applied **atomically together with its ledger record** in a
  single transaction. If the SQL fails, both roll back — no more half-applies and
  no false ledger entries.
- The ledger is keyed by filename (``version``), so the two ``014_*`` files are
  tracked as distinct entries.
- ``backfill`` records migrations as applied WITHOUT executing them, for a database
  whose schema already reflects them (the current state of this project).

Convention for NEW migrations (016+):
- Name them ``NNN_description.sql`` (zero-padded 3-digit prefix).
- Do NOT put your own ``BEGIN``/``COMMIT`` in the file — the runner wraps each
  migration in a transaction. Prefer idempotent DDL (``IF NOT EXISTS`` / ``IF EXISTS``).

Usage:
    python -m infrastructure.database.migrations.migrate status
    python -m infrastructure.database.migrations.migrate apply
    python -m infrastructure.database.migrations.migrate backfill --all
    python -m infrastructure.database.migrations.migrate backfill 016_foo.sql
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Reuse the project's connection logic (env / .env / Docker)
try:
    from infrastructure.database.connection import get_engine
except ImportError:  # pragma: no cover - allow running as a loose script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from infrastructure.database.connection import get_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent

# Only files matching NNN_*.sql are managed by the ledger. Unnumbered legacy
# scripts (create_*.sql, add_*.sql) predate the ledger and are intentionally
# excluded from automated apply.
NUMBERED_RE = re.compile(r"^\d{3}_.*\.sql$")

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by  TEXT,
    note        TEXT
);
COMMENT ON TABLE schema_migrations IS
    'Ledger of applied NNN_*.sql migrations. Managed by migrate.py.';
"""


def discover_migrations() -> List[Path]:
    """Return numbered migration files, sorted by filename."""
    return sorted(
        (p for p in MIGRATIONS_DIR.glob("*.sql") if NUMBERED_RE.match(p.name)),
        key=lambda p: p.name,
    )


def file_checksum(path: Path) -> str:
    """SHA-256 of a migration file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_ledger(engine: Engine) -> None:
    """Create the schema_migrations table if it does not exist."""
    with engine.begin() as conn:
        conn.exec_driver_sql(LEDGER_DDL)


def get_applied(engine: Engine) -> Dict[str, dict]:
    """Return {version: {checksum, applied_at, applied_by, note}} from the ledger."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT version, checksum, applied_at, applied_by, note "
                "FROM schema_migrations"
            )
        ).fetchall()
    return {
        r[0]: {"checksum": r[1], "applied_at": r[2], "applied_by": r[3], "note": r[4]}
        for r in rows
    }


def _record(conn, version: str, checksum: str, applied_by: str, note: str) -> None:
    conn.execute(
        text(
            "INSERT INTO schema_migrations (version, checksum, applied_by, note) "
            "VALUES (:v, :c, :b, :n) "
            "ON CONFLICT (version) DO UPDATE SET "
            "checksum = EXCLUDED.checksum, applied_at = now(), "
            "applied_by = EXCLUDED.applied_by, note = EXCLUDED.note"
        ),
        {"v": version, "c": checksum, "b": applied_by, "n": note},
    )


def cmd_status(engine: Engine) -> int:
    ensure_ledger(engine)
    applied = get_applied(engine)
    files = discover_migrations()
    file_names = {p.name for p in files}

    print(f"{'STATUS':<10}{'VERSION':<42}{'NOTE'}")
    print("-" * 80)
    pending = 0
    drift = 0
    for p in files:
        rec = applied.get(p.name)
        if rec is None:
            status = "PENDING"
            pending += 1
            note = ""
        elif rec["checksum"] and rec["checksum"] != file_checksum(p):
            status = "DRIFT"  # applied, but file changed since
            drift += 1
            note = "file changed since apply"
        else:
            status = "applied"
            note = rec.get("note") or ""
        print(f"{status:<10}{p.name:<42}{note}")

    # Ledger entries with no corresponding file (e.g., renamed/deleted)
    orphans = sorted(set(applied) - file_names)
    for v in orphans:
        print(f"{'ORPHAN':<10}{v:<42}{'in ledger, no file'}")

    print("-" * 80)
    print(
        f"{len(files)} numbered migrations | "
        f"applied={len(files) - pending} pending={pending} drift={drift} "
        f"orphans={len(orphans)}"
    )
    return 1 if (pending or drift) else 0


def cmd_apply(engine: Engine) -> int:
    ensure_ledger(engine)
    applied = get_applied(engine)
    files = discover_migrations()
    pending = [p for p in files if p.name not in applied]

    if not pending:
        print("No pending migrations. Schema is up to date.")
        return 0

    print(f"Applying {len(pending)} pending migration(s):")
    for p in pending:
        sql = p.read_text()
        try:
            # Migration SQL + ledger record commit together (atomic).
            with engine.begin() as conn:
                conn.exec_driver_sql(sql)
                _record(conn, p.name, file_checksum(p), "apply", "applied by migrate.py")
            print(f"  ✓ {p.name}")
        except Exception as e:  # noqa: BLE001 - surface and stop
            print(f"  ✗ {p.name} FAILED — rolled back:\n    {e}")
            print("Stopping. Fix the migration and re-run `apply`.")
            return 1
    print("All pending migrations applied.")
    return 0


def cmd_backfill(engine: Engine, versions: Optional[List[str]], note: str) -> int:
    """Record migrations as applied WITHOUT executing them (existing schema)."""
    ensure_ledger(engine)
    files = {p.name: p for p in discover_migrations()}

    if versions:
        targets = []
        for v in versions:
            if v not in files:
                print(f"  ! unknown migration: {v} (not a numbered file)")
                return 1
            targets.append(files[v])
    else:
        targets = list(files.values())

    applied = get_applied(engine)
    recorded = 0
    with engine.begin() as conn:
        for p in targets:
            if p.name in applied:
                print(f"  - {p.name} already in ledger, skipping")
                continue
            _record(conn, p.name, file_checksum(p), "backfill", note)
            print(f"  ✓ recorded {p.name}")
            recorded += 1
    print(f"Backfilled {recorded} migration(s).")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Migration ledger + runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Show applied vs pending migrations")
    sub.add_parser("apply", help="Apply pending migrations atomically")
    bf = sub.add_parser("backfill", help="Record migrations as applied without running")
    bf.add_argument("versions", nargs="*", help="Specific filenames (default: all)")
    bf.add_argument("--all", action="store_true", help="Backfill all numbered migrations")
    bf.add_argument(
        "--note",
        default="backfill: schema verified present",
        help="Note to store with backfilled records",
    )

    args = parser.parse_args(argv)
    engine = get_engine()

    if args.command == "status":
        return cmd_status(engine)
    if args.command == "apply":
        return cmd_apply(engine)
    if args.command == "backfill":
        versions = None if args.all else (args.versions or None)
        if versions is None and not args.all:
            print("Specify migration filenames or --all")
            return 2
        return cmd_backfill(engine, versions, args.note)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
