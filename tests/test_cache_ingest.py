"""common/cache_ingest.py — the cross-stage DB cache as a LIVE, incrementally-UPSERTed working store.

Exercised against the real governance Postgres via CONNECTION-SCOPED TEMP tables (the gov_session
fixture) so the UPSERT semantics + the new `capture.err` column run on the actual engine without
touching real governance data. The TEMP tables are lifted from CI.CACHE_DDL so the columns can't drift.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import cache_ingest as CI

pytestmark = pytest.mark.integration


def _create_cache_temp(sess):
    for ddl in CI.CACHE_DDL:
        sess.execute(text(ddl.strip().replace("CREATE TABLE IF NOT EXISTS ", "CREATE TEMP TABLE ", 1)))


def test_capture_upsert_is_idempotent_and_updates(gov_session):
    _create_cache_temp(gov_session)
    caps = {"h1": {"url": "http://x/a", "ok": False, "kind": "html", "source": "discovered",
                   "err": "needs_oauth_reauth", "fingerprint": {"final_host": "x.org"}}}
    CI.upsert_capture_rows(gov_session, "d1", caps)
    row = gov_session.execute(text("SELECT ok, err, final_host FROM capture WHERE district_id='d1' AND hash='h1'")).first()
    assert row.ok == 0 and row.err == "needs_oauth_reauth" and row.final_host == "x.org"

    # re-running the stage UPDATES the row in place (no duplicate, no error)
    caps["h1"].update(ok=True, err=None)
    CI.upsert_capture_rows(gov_session, "d1", caps)
    assert gov_session.execute(text("SELECT COUNT(*) FROM capture WHERE district_id='d1'")).scalar() == 1
    row = gov_session.execute(text("SELECT ok, err FROM capture WHERE hash='h1'")).first()
    assert row.ok == 1 and row.err is None


def test_emergent_source_and_failure_reason_are_queryable(gov_session):
    _create_cache_temp(gov_session)
    caps = {
        "h1": {"url": "u1", "ok": True, "source": "discovered", "fingerprint": {"final_host": "a"}},
        "h2": {"url": "u2", "ok": True, "source": "emergent", "fingerprint": {"final_host": "a"}},
        "h3": {"url": "u3", "ok": False, "source": "discovered", "err": "security_block"},
    }
    CI.upsert_capture_rows(gov_session, "d1", caps)
    assert gov_session.execute(text("SELECT COUNT(*) FROM capture WHERE source='emergent'")).scalar() == 1
    assert gov_session.execute(text("SELECT err FROM capture WHERE ok=0")).scalar() == "security_block"


def test_discovery_upsert_rolls_up_waves(gov_session):
    _create_cache_temp(gov_session)
    disc = {"district_id": "d1", "schools": [
        {"school_id": "s1", "school": "A", "bands": ["elementary"], "query": "q",
         "wave1_gated": [{"url": "u1", "kept": True}], "wave2_invoked": False,
         "wave2_gated": [], "outcome": "found"}]}
    cand_map = {"http://x/p": {"schools": ["A"], "tools": ["brightdata"]}}
    CI.upsert_discovery_rows(gov_session, disc, cand_map)
    r = gov_session.execute(text("SELECT wave1_n_kept, outcome FROM discovery_school WHERE school_id='s1'")).first()
    assert r.wave1_n_kept == 1 and r.outcome == "found"
    assert gov_session.execute(text("SELECT n_schools FROM candidate WHERE url='http://x/p'")).scalar() == 1
