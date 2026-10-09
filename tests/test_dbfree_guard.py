"""#201 — the DB-free test-job guard's own self-test.

These tests are UNMARKED (no integration/govdb), so the autouse guard in conftest is active for them. They
prove the guard converts a Postgres-connection attempt into a loud, named failure instead of a real
connection — which is exactly what stops a DB-free test from silently passing locally + skipping in CI.
Because the guard blocks BEFORE any socket opens, these tests need no database and run in the DB-free job."""
import psycopg
import pytest

from infrastructure.acquisition.common import db as gdb


def test_guard_blocks_the_governance_engine_connect():
    # gdb.get_engine() only builds the (lazy) Engine — .connect() is where the guard intercepts.
    with pytest.raises(RuntimeError, match="must not touch Postgres"):
        gdb.get_engine().connect()


def test_guard_blocks_raw_psycopg_connect():
    with pytest.raises(RuntimeError, match="psycopg.connect"):
        psycopg.connect("postgresql://unused/never-opened")


def test_guard_names_the_offending_test_and_the_fix():
    # the message must be actionable: it names the marker to add + that mocking is the alternative.
    with pytest.raises(RuntimeError, match="pytest.mark.integration"):
        gdb.get_engine().connect()



def test_guard_blocks_legacy_psycopg2_when_still_installed():
    """#930: a local env upgraded in place keeps psycopg2 — an unpatched raw driver would bypass the guard."""
    psycopg2 = pytest.importorskip("psycopg2")
    with pytest.raises(RuntimeError, match="psycopg2.connect"):
        psycopg2.connect("postgresql://unused/never-opened")
