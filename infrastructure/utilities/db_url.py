"""The ONE place a database URL becomes an SQLAlchemy engine URL (#930, REQ-103).

The Postgres driver is a decision this repo owns, never SQLAlchemy's default: 2.1 silently changed what a
bare `postgresql://` means (psycopg2 -> psycopg 3) and CI went red on an unchanged commit (#929). Both engine
builders (`infrastructure.database.connection`, `infrastructure.acquisition.common.db`) call this; the URL
resolvers stay libpq-form so `pg_dump` and `db._db_name` keep reading them as-is.
"""
from sqlalchemy.engine import make_url

POSTGRES_DRIVERNAME = "postgresql+psycopg"


def sqlalchemy_url(url: str) -> str:
    """Pin any Postgres URL (`postgresql://`, `postgres://`, `postgresql+<driver>://`) to psycopg 3;
    pass every other backend through untouched."""
    parsed = make_url(url)
    if parsed.get_backend_name() not in ("postgresql", "postgres"):
        return url
    return parsed.set(drivername=POSTGRES_DRIVERNAME).render_as_string(hide_password=False)
