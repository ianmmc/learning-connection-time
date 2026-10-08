"""#930 / REQ-103 — the Postgres driver is chosen explicitly, never by SQLAlchemy's default.

SQLAlchemy 2.1 silently changed what a bare `postgresql://` URL means (psycopg2 -> psycopg 3); CI went red for
two weeks on an unchanged commit (#929). Every engine now goes through ONE normalizer, so the driver is a
decision this repo owns — including for URLs arriving verbatim from DATABASE_URL / GOVERNANCE_DATABASE_URL."""
import pytest

from infrastructure.utilities.db_url import sqlalchemy_url


@pytest.mark.parametrize("raw", [
    "postgresql://u:p@h:5432/governance",
    "postgres://u:p@h:5432/governance",            # the Heroku-style scheme SQLAlchemy itself rejects
    "postgresql+psycopg2://u:p@h:5432/governance",  # a legacy override must not pin the old driver
    "postgresql+psycopg://u:p@h:5432/governance",
])
def test_every_postgres_form_resolves_to_psycopg3(raw):
    assert sqlalchemy_url(raw).startswith("postgresql+psycopg://")


def test_credentials_host_db_and_query_survive_untouched():
    out = sqlalchemy_url("postgresql://us%40er:p%2Fw@db.example:6543/governance?sslmode=require")
    assert out == "postgresql+psycopg://us%40er:p%2Fw@db.example:6543/governance?sslmode=require"


def test_non_postgres_urls_pass_through():
    # tests build in-memory SQLite engines; the normalizer must not touch other backends
    assert sqlalchemy_url("sqlite:///:memory:") == "sqlite:///:memory:"


@pytest.mark.parametrize("module,url_fn", [
    ("infrastructure.acquisition.common.db", "governance_url"),
    ("infrastructure.database.connection", "get_database_url"),
])
def test_both_engines_use_the_normalizer(monkeypatch, module, url_fn):
    """A bare-URL env override still yields the chosen driver — asserted on the ENGINE each module builds,
    not on the helper, so a call site that forgets the normalizer fails here."""
    import importlib
    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, url_fn, lambda: "postgresql://u:p@h:5432/x")
    monkeypatch.setattr(mod, "_engine", None)
    monkeypatch.setattr(mod, "_SessionLocal", None)
    eng = mod.get_engine()
    try:
        assert eng.dialect.driver == "psycopg"
    finally:
        eng.dispose()
        monkeypatch.setattr(mod, "_engine", None)
