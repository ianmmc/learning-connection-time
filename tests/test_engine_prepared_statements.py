"""#943 — the server never sees an auto-prepared statement from this repo's engines.

psycopg 3 prepares a statement server-side on its 6th execution per connection and switches to a GENERIC
plan on the 11th; psycopg2 never did. The gate@5 records query changed row order from the 11th call on one
pooled connection (its ORDER BY was not total at the time — #947), and a `SELECT *` after a DDL change raises
'cached plan must not change result type'. The DB-free half of this pin (tests/test_db_url.py) proves both
builders pass the kwarg; this half proves what the SERVER sees, on a real pooled connection."""
import pytest
from sqlalchemy import text

from infrastructure.utilities.db_url import PSYCOPG_CONNECT_ARGS


@pytest.mark.govdb
def test_twelve_executions_prepare_nothing_server_side(gov_session):
    raw = gov_session.connection().connection.dbapi_connection
    assert PSYCOPG_CONNECT_ARGS["prepare_threshold"] is None and raw.prepare_threshold is None   # the engine applied the pin
    q = text("SELECT CAST(:n AS int) + 1")           # table-free: the mechanism is per statement, not per table
    for i in range(12):
        assert gov_session.execute(q, {"n": i}).scalar() == i + 1
    prepared = gov_session.execute(text("SELECT count(*) FROM pg_prepared_statements")).scalar()
    assert prepared == 0, f"{prepared} statement(s) auto-prepared on this connection — prepare_threshold is not None"
