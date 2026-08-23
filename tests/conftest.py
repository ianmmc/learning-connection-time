"""
PostgreSQL Test Fixtures for pytest

Copy this to your project's tests/conftest.py and customize as needed.

Usage:
    pytest tests/ -v

Environment Variables:
    TEST_DATABASE_URL: Connection string for test database
    USE_REAL_DB: Set to "true" to use real database (integration tests)
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager
from datetime import datetime, date
from decimal import Decimal


# --- #201: DB-free test-job guard -------------------------------------------------------------------
# The CI test matrix splits into `test` (`-m "not integration"`, no database at all) and `governance-db`
# (`-m govdb`, a Postgres service container). Two failure modes this guards against:
#   (1) a `govdb` test that forgot the `integration` marker still matches `-m "not integration"`, so it
#       runs in the DB-free job and merely SKIPS (gov_session skips on an unreachable DB) — masking a test
#       that genuinely needs Postgres. `pytest_collection_modifyitems` enforces the marker doc's promise
#       ("every govdb is also integration") so those tests are cleanly EXCLUDED, not silently skipped.
#   (2) a genuinely DB-free test that opens a Postgres connection passes locally (Docker up) but skips or
#       fails confusingly in CI. `_guard_no_postgres_in_dbfree_tests` makes that a LOUD, named failure.

def pytest_collection_modifyitems(config, items):
    """#201: every `govdb` test is ALSO `integration` (the marker doc's stated contract), enforced here so
    the DB-free selection excludes them by marker rather than by the fixture's skip-on-unavailable."""
    for item in items:
        if item.get_closest_marker("govdb") and not item.get_closest_marker("integration"):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _guard_no_postgres_in_dbfree_tests(request):
    """#201: a test NOT marked integration/govdb that opens a Postgres connection is a latent bug — it
    passes locally with Docker up but skips/fails in CI's DB-free job. Fail it loudly, naming the fix.
    Non-Postgres engines (e.g. an in-memory SQLite) pass through untouched — only the postgresql backend
    is blocked, so this catches 'touched the real DB' precisely, not 'built any engine'."""
    if request.node.get_closest_marker("integration") or request.node.get_closest_marker("govdb"):
        yield
        return
    # Fixture-name check first: the connect() interception below can't see a SESSION-SCOPED fixture's
    # already-open cached connection (real_db_connection opens once for the whole session), so an
    # unmarked test requesting one would slip past the patch. Requesting a real-DB fixture at all is
    # the violation — fail on the request, not the (possibly absent) connect call.
    real_db_fixtures = {"real_db_connection", "real_db_transaction", "gov_session"} \
        .intersection(request.fixturenames)
    if real_db_fixtures:
        raise RuntimeError(
            f"DB-free test '{request.node.nodeid}' requests real-DB fixture(s) "
            f"{sorted(real_db_fixtures)} without @pytest.mark.integration/@pytest.mark.govdb — "
            f"add the marker (#201).")
    import psycopg2
    from sqlalchemy.engine import Engine
    real_engine_connect = Engine.connect
    real_pg_connect = psycopg2.connect
    nodeid = request.node.nodeid

    def _blocked(entrypoint):
        raise RuntimeError(
            f"DB-free test '{nodeid}' opened a Postgres connection via {entrypoint}. A test not marked "
            f"@pytest.mark.integration (or @pytest.mark.govdb for the isolated governance DB) must not "
            f"touch Postgres — it passes locally but skips/fails in CI's DB-free job. Add the marker, or "
            f"mock the database (#201).")

    def guarded_engine_connect(self, *a, **k):
        if self.url.get_backend_name() == "postgresql":
            _blocked("Engine.connect")
        return real_engine_connect(self, *a, **k)

    def guarded_pg_connect(*a, **k):
        _blocked("psycopg2.connect")

    Engine.connect = guarded_engine_connect
    psycopg2.connect = guarded_pg_connect
    try:
        yield
    finally:
        Engine.connect = real_engine_connect
        psycopg2.connect = real_pg_connect


# --- Governance Postgres fixture (REQ-103) ---

@pytest.fixture
def gov_session():
    """A Session on the ISOLATED governance Postgres DB (REQ-103), for unit tests that exercise the
    Stage-5 SQL against the real engine. Tests create CONNECTION-SCOPED TEMP tables on it (auto-
    dropped at close), so they never touch real governance data and need no cleanup. The session is
    bound to a single checked-out connection so the temp tables are visible to every statement.
    Skips cleanly if the governance DB isn't reachable (Docker down)."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from infrastructure.acquisition.common import db as gdb
    try:
        conn = gdb.get_engine().connect()
        conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    sess = Session(bind=conn)
    try:
        yield sess
    finally:
        sess.rollback()
        sess.close()
        conn.close()


# --- Configuration ---

TEST_DATABASE_URL = os.getenv(
    'TEST_DATABASE_URL',
    'postgresql://localhost:5432/test_db'
)
USE_REAL_DB = os.getenv('USE_REAL_DB', 'false').lower() == 'true'


# --- Mock Database Fixtures ---

@pytest.fixture
def mock_db_connection():
    """
    Mock psycopg2 connection for unit tests.

    Usage:
        def test_something(mock_db_connection):
            conn, cursor = mock_db_connection
            cursor.fetchall.return_value = [('row1',), ('row2',)]
            result = my_function(conn)
            assert result == expected
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # Setup context manager behavior
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    # Setup transaction behavior
    mock_conn.commit = MagicMock()
    mock_conn.rollback = MagicMock()

    return mock_conn, mock_cursor


@pytest.fixture
def mock_cursor_factory():
    """
    Factory for creating mock cursors with preset return values.

    Usage:
        def test_query(mock_cursor_factory):
            cursor = mock_cursor_factory(
                fetchall=[('row1',), ('row2',)],
                fetchone=('single',),
                rowcount=2
            )
    """
    def factory(fetchall=None, fetchone=None, rowcount=0):
        cursor = MagicMock()
        cursor.fetchall.return_value = fetchall or []
        cursor.fetchone.return_value = fetchone
        cursor.rowcount = rowcount
        cursor.description = [('column1',), ('column2',)]
        return cursor
    return factory


# --- Sample Data Fixtures ---

@pytest.fixture
def sample_district():
    """Sample district record matching typical schema."""
    return {
        'nces_id': '0612345',
        'name': 'Test Unified School District',
        'state': 'CA',
        'enrollment': 5000,
        'staff_count': 250,
        'instructional_minutes': 360,
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    }


@pytest.fixture
def sample_districts(sample_district):
    """Multiple sample districts for batch testing."""
    districts = []
    for i in range(5):
        d = sample_district.copy()
        d['nces_id'] = f'061234{i}'
        d['name'] = f'Test District {i}'
        d['enrollment'] = 1000 * (i + 1)
        districts.append(d)
    return districts


@pytest.fixture
def sample_lct_data():
    """Sample LCT calculation data."""
    return {
        'district_id': 'TEST001',
        'instructional_minutes': 360,
        'staff_count': 50,
        'enrollment': 1000,
        'expected_lct': Decimal('18.00')  # (360 * 50) / 1000
    }


# --- Database Transaction Fixtures ---

@pytest.fixture
def db_transaction(mock_db_connection):
    """
    Context manager for database transactions in tests.
    Automatically rolls back after test.
    """
    conn, cursor = mock_db_connection

    @contextmanager
    def transaction():
        try:
            yield conn, cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return transaction


# --- Real Database Fixtures (Integration Tests) ---

@pytest.fixture(scope='session')
def real_db_connection():
    """
    Real database connection for integration tests.
    Only used when USE_REAL_DB=true.

    WARNING: This connects to a real database. Use with caution.
    """
    if not USE_REAL_DB:
        pytest.skip("Skipping real database test (USE_REAL_DB not set)")

    import psycopg2
    conn = psycopg2.connect(TEST_DATABASE_URL)
    yield conn
    conn.close()


@pytest.fixture
def real_db_transaction(real_db_connection):
    """
    Real database transaction that rolls back after test.
    Ensures tests don't pollute the database.
    """
    conn = real_db_connection
    conn.autocommit = False

    yield conn

    conn.rollback()  # Always rollback after test


# --- Assertion Helpers ---

@pytest.fixture
def assert_query_contains():
    """Helper to assert SQL query contains expected clauses."""
    def checker(cursor, *expected_clauses):
        call_args = cursor.execute.call_args
        if call_args is None:
            raise AssertionError("No query was executed")

        query = call_args[0][0].lower()
        for clause in expected_clauses:
            assert clause.lower() in query, \
                f"Query missing expected clause: {clause}\nQuery was: {query}"

    return checker


@pytest.fixture
def assert_query_params():
    """Helper to assert query was called with expected parameters."""
    def checker(cursor, expected_params):
        call_args = cursor.execute.call_args
        if call_args is None:
            raise AssertionError("No query was executed")

        actual_params = call_args[0][1] if len(call_args[0]) > 1 else {}
        assert actual_params == expected_params, \
            f"Query params mismatch.\nExpected: {expected_params}\nActual: {actual_params}"

    return checker


# --- Snapshot Testing Helpers ---

@pytest.fixture
def snapshot_serializer():
    """
    Custom serializer for snapshot testing with database results.
    Handles datetime, Decimal, and other non-JSON types.
    """
    import json

    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return str(obj)
            return super().default(obj)

    def serialize(data):
        return json.dumps(data, cls=CustomEncoder, indent=2, sort_keys=True)

    return serialize


@pytest.fixture(autouse=True)
def _no_transient_backoff_sleep(monkeypatch):
    """#711: the transient-retry backoff sleeps for real seconds. A test suite must never sleep —
    the retry LOGIC is what is under test, not the wall clock (leaving it live took the openrouter
    suite from ~1s to ~25s). Zeroed for every test; a test that wants to assert the backoff
    schedule reads TRANSIENT_BACKOFF_S from the module rather than waiting for it."""
    try:
        from infrastructure.acquisition.stage7_extract import openrouter as _OR
        monkeypatch.setattr(_OR, "TRANSIENT_BACKOFF_S", ())
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_openrouter_client_cache():
    """#148: `openrouter._client` is lru-cached per (key, timeout) for connection reuse. Tests swap
    `openai.OpenAI` for a fake per test — clear the cache before each so a prior test's cached fake
    client is never served (same (key, timeout))."""
    try:
        from infrastructure.acquisition.stage7_extract import openrouter as _OR
        _OR._client.cache_clear()
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------- #897: the console client
# The ONE construction of the gate@5 client's source path, shared by every source-pin test (the
# expression was hand-spelled in 5 test files / 10+ sites before this). Derived from the PACKAGE
# location — test_gate1_api.py's idiom — so a repo-layout move cannot silently break it the way a
# repo-relative literal would.
def _app_js_path():
    from pathlib import Path
    from infrastructure.acquisition import process_governance as _PG
    return Path(_PG.__file__).parent / "static" / "app.js"


@pytest.fixture(scope="session")
def app_js() -> str:
    """The gate@5 console client source, read once per session for source-pin tests."""
    return _app_js_path().read_text()
