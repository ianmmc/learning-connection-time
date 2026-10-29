"""#930 / REQ-103 — the Postgres driver is chosen explicitly, never by SQLAlchemy's default.

SQLAlchemy 2.1 silently changed what a bare `postgresql://` URL means (psycopg2 -> psycopg 3); CI went red for
two weeks on an unchanged commit (#929). Every engine now goes through ONE normalizer, so the driver is a
decision this repo owns — including for URLs arriving verbatim from DATABASE_URL / GOVERNANCE_DATABASE_URL."""
from types import SimpleNamespace

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
@pytest.mark.parametrize("raw", [
    "postgres://u:p@h:5432/x",            # SQLAlchemy rejects this scheme outright without the normalizer
    "postgresql+psycopg2://u:p@h:5432/x",  # a legacy override would pin the OLD driver without it
])
def test_both_engines_use_the_normalizer(monkeypatch, module, url_fn, raw):
    """A bare-URL env override still yields the chosen driver — asserted on the ENGINE each module builds.
    #945: the first cut fed only `postgresql://`, which SQLAlchemy 2.1 maps to psycopg 3 BY ITSELF, so the
    test passed with the normalizer deleted. These two forms are the ones that need it (mutation-checked)."""
    import importlib
    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, url_fn, lambda: raw)
    monkeypatch.setattr(mod, "_engine", None)
    monkeypatch.setattr(mod, "_SessionLocal", None)
    eng = mod.get_engine()
    try:
        assert eng.url.drivername == "postgresql+psycopg"
        assert eng.dialect.driver == "psycopg"
    finally:
        eng.dispose()
        monkeypatch.setattr(mod, "_engine", None)


@pytest.mark.parametrize("module,url_fn", [
    ("infrastructure.acquisition.common.db", "governance_url"),
    ("infrastructure.database.connection", "get_database_url"),
])
def test_both_engines_disable_auto_prepared_statements(monkeypatch, module, url_fn):
    """#943: both builders pass `connect_args=engine_connect_args(url)` — asserted on what reaches
    create_engine, so a builder that drops the kwarg fails here (the DB-free half; the govdb half proves
    the server never sees a prepared statement)."""
    import importlib
    from infrastructure.utilities.db_url import PSYCOPG_CONNECT_ARGS
    mod = importlib.import_module(module)
    seen = {}

    def fake_create_engine(url, **kw):
        seen["url"], seen["kw"] = str(url), kw
        return SimpleNamespace(dispose=lambda: None)
    monkeypatch.setattr(mod, "create_engine", fake_create_engine)
    monkeypatch.setattr(mod, url_fn, lambda: "postgresql://u:p@h:5432/x")
    monkeypatch.setattr(mod, "_engine", None)
    monkeypatch.setattr(mod, "_SessionLocal", None)
    mod.get_engine()
    monkeypatch.setattr(mod, "_engine", None)
    assert seen["kw"]["connect_args"] == PSYCOPG_CONNECT_ARGS == {"prepare_threshold": None}


def test_connect_args_only_for_postgres():
    from infrastructure.utilities.db_url import engine_connect_args
    assert engine_connect_args("postgresql://u@h/x") == {"prepare_threshold": None}
    assert engine_connect_args("sqlite:///:memory:") == {}
