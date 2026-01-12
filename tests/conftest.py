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
