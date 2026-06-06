"""
Tests for the migration ledger + runner (infrastructure/database/migrations/migrate.py).

Pure-logic tests (discovery, checksum, naming convention) always run.
Ledger round-trip tests run only when the database is reachable, and clean up
after themselves using a sentinel version that maps to no real file.

Covers REQ-040 (migration ledger / no half-applied migrations).
"""

import hashlib

import pytest

from infrastructure.database.migrations import migrate


# --- Pure-logic tests (no database required) ---

class TestMigrationDiscovery:
    def test_discovers_numbered_migrations(self):
        files = migrate.discover_migrations()
        names = [p.name for p in files]
        # Known numbered migrations must be present
        assert "002_add_staff_counts.sql" in names
        assert "015_fix_nces_id_leading_zeros.sql" in names
        # Both 014_* files are tracked distinctly (the numbering collision)
        assert "014_add_security_blocking.sql" in names
        assert "014_add_staff_scope_to_lct.sql" in names

    def test_excludes_unnumbered_legacy_scripts(self):
        names = [p.name for p in migrate.discover_migrations()]
        # Legacy ad-hoc scripts and apply_*.py helpers are NOT ledger-managed
        assert "create_materialized_views.sql" not in names
        assert "add_self_contained_columns.sql" not in names
        assert not any(n.startswith("apply_") for n in names)

    def test_discovery_is_sorted(self):
        names = [p.name for p in migrate.discover_migrations()]
        assert names == sorted(names)

    def test_numbered_regex(self):
        assert migrate.NUMBERED_RE.match("016_new_thing.sql")
        assert migrate.NUMBERED_RE.match("014_add_staff_scope_to_lct.sql")
        assert not migrate.NUMBERED_RE.match("create_materialized_views.sql")
        assert not migrate.NUMBERED_RE.match("add_self_contained_columns.sql")
        assert not migrate.NUMBERED_RE.match("16_too_short.sql")
        assert not migrate.NUMBERED_RE.match("016_new_thing.py")

    def test_file_checksum_is_stable_sha256(self):
        files = migrate.discover_migrations()
        assert files, "expected at least one numbered migration"
        p = files[0]
        c1 = migrate.file_checksum(p)
        c2 = migrate.file_checksum(p)
        assert c1 == c2
        assert c1 == hashlib.sha256(p.read_bytes()).hexdigest()
        assert len(c1) == 64


# --- Ledger round-trip tests (require a reachable database) ---

@pytest.fixture
def engine_or_skip():
    """Return a live engine, or skip if the database is not reachable."""
    try:
        from infrastructure.database.connection import get_engine
        eng = get_engine()
        with eng.connect():
            pass
        return eng
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database not reachable: {e}")


class TestMigrationLedger:
    SENTINEL = "999_test_sentinel.sql"

    def test_ensure_ledger_idempotent(self, engine_or_skip):
        # Calling twice must not error
        migrate.ensure_ledger(engine_or_skip)
        migrate.ensure_ledger(engine_or_skip)
        applied = migrate.get_applied(engine_or_skip)
        assert isinstance(applied, dict)

    def test_known_migrations_recorded_as_applied(self, engine_or_skip):
        applied = migrate.get_applied(engine_or_skip)
        # After this session's backfill, the core migrations are tracked
        assert "014_add_staff_scope_to_lct.sql" in applied
        assert "015_fix_nces_id_leading_zeros.sql" in applied

    def test_record_and_readback_then_cleanup(self, engine_or_skip):
        from sqlalchemy import text
        eng = engine_or_skip
        migrate.ensure_ledger(eng)
        try:
            with eng.begin() as conn:
                migrate._record(conn, self.SENTINEL, "deadbeef", "test", "sentinel")
            applied = migrate.get_applied(eng)
            assert self.SENTINEL in applied
            assert applied[self.SENTINEL]["checksum"] == "deadbeef"
            assert applied[self.SENTINEL]["applied_by"] == "test"
        finally:
            with eng.begin() as conn:
                conn.execute(
                    text("DELETE FROM schema_migrations WHERE version = :v"),
                    {"v": self.SENTINEL},
                )
        # Confirm cleanup
        assert self.SENTINEL not in migrate.get_applied(eng)

    def test_status_clean_when_all_applied(self, engine_or_skip):
        # All numbered migrations were backfilled, so status should report 0 pending
        rc = migrate.cmd_status(engine_or_skip)
        assert rc == 0, "expected 0 pending/drift after backfill"
