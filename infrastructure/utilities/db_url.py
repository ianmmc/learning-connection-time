"""The ONE place a database URL becomes an SQLAlchemy engine URL (#930, REQ-103).

The Postgres driver is a decision this repo owns, never SQLAlchemy's default: 2.1 silently changed what a
bare `postgresql://` means (psycopg2 -> psycopg 3) and CI went red on an unchanged commit (#929). Both engine
builders (`infrastructure.database.connection`, `infrastructure.acquisition.common.db`) call this. The URL
RESOLVERS (`get_database_url`, `governance_url`) build libpq-form URLs but pass a `DATABASE_URL` /
`GOVERNANCE_DATABASE_URL` override through VERBATIM — a `+driver` in an override reaches libpq consumers
unstripped (`reset_database.py` strips it for `pg_dump` itself; `db._db_name` parses the path, so it is
indifferent). Normalize at the engine, never assume the resolver did.
"""
from sqlalchemy.engine import make_url

POSTGRES_DRIVERNAME = "postgresql+psycopg"

# psycopg 3 auto-prepares a statement on its 6th execution per connection and uses a GENERIC plan from
# the 11th; psycopg2 never did. Measured (#943): the gate@5 records query — ordered only by non-unique
# columns at the time — returned a different row order from the 11th call on one pooled connection,
# and a `SELECT *` after a DDL change raises 'cached plan must not change result type'. Transaction-mode
# poolers (the documented cloud DATABASE_URL path) reject prepared statements outright. Off, everywhere.
PSYCOPG_CONNECT_ARGS = {"prepare_threshold": None}


def engine_connect_args(url: str) -> dict:
    """`connect_args` for `create_engine(sqlalchemy_url(url), ...)`: the psycopg settings this repo pins
    (#943) when the URL is Postgres, `{}` for any other backend (tests build SQLite engines)."""
    return dict(PSYCOPG_CONNECT_ARGS) if make_url(sqlalchemy_url(url)).drivername == POSTGRES_DRIVERNAME else {}


def sqlalchemy_url(url: str) -> str:
    """Pin any Postgres URL (`postgresql://`, `postgres://`, `postgresql+<driver>://`) to psycopg 3;
    pass every other backend through untouched."""
    parsed = make_url(url)
    if parsed.get_backend_name() not in ("postgresql", "postgres"):
        return url
    return parsed.set(drivername=POSTGRES_DRIVERNAME).render_as_string(hide_password=False)
