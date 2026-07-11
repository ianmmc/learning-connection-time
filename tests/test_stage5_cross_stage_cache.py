"""REQ-103c — the cross-stage cache: each district's raw stage artifacts (discovery / candidates /
captures / processed) ingested as queryable, regenerable rows beside the Stage-5 `record` signal view.

`ingest_cross_stage_cache` is exercised against the real governance Postgres via CONNECTION-SCOPED
TEMP tables (the gov_session fixture), so the SQL + funnel roll-ups run on the actual engine without
touching real governance data. The TEMP tables are derived from the live REBUILD_DDL so the test
can't drift from the production schema.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import cache_ingest as CI  # noqa: E402  (cache schema + UPSERTs now live here)
from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402

# #201: all 4 tests hit the governance DB via gov_session (CONNECTION-SCOPED TEMP tables) — mark govdb so
# they run in CI's governance-db job and are excluded from the DB-free job (was leaking as a skip).
pytestmark = pytest.mark.govdb

CACHE_TABLES = ("discovery_school", "candidate", "capture", "processed_doc")


def _create_cache_temp(sess):
    """Stand up the 4 cross-stage tables as TEMP, lifted verbatim from CI.CACHE_DDL (CREATE TABLE IF
    NOT EXISTS -> CREATE TEMP TABLE) so the columns always match what the UPSERTs write."""
    for ddl in CI.CACHE_DDL:
        sess.execute(text(ddl.strip().replace("CREATE TABLE IF NOT EXISTS ", "CREATE TEMP TABLE ", 1)))


def _fixtures():
    disc = {"district_id": "d1", "schools": [
        {"school_id": "s1", "school": "A Elem", "bands": ["elementary"], "query": "q",
         "wave1_raw_urls": ["u1", "u2"],
         "wave1_gated": [{"url": "u1", "kept": True}, {"url": "u2", "kept": False}],
         "wave2_invoked": True, "wave2_raw_urls": ["u3"],
         "wave2_gated": [{"url": "u3", "kept": True}], "outcome": "found"}]}
    cand_map = {"http://x/plan": {"schools": ["A Elem"], "tools": ["claude"]}}
    caps = {
        "h1": {"url": "http://x/a", "final_url": "http://x/a", "ok": True, "kind": "html",
               "source": "discovered", "found_on": None, "tools": ["claude"], "files": {"txt": "page.txt"},
               "modals_dismissed": True, "segmented": True, "text_times": 3,
               "fingerprint": {"final_host": "x"}},
        # h2 captured but FAILED — never reaches processed; must still land in `capture`.
        "h2": {"url": "http://x/b", "ok": False, "kind": None}}
    processed = {"h1": {"url": "http://x/a", "usable": True, "texts": [{}, {}]}}
    return disc, caps, processed, cand_map


def test_cross_stage_cache_row_counts(gov_session):
    disc, caps, processed, cand_map = _fixtures()
    _create_cache_temp(gov_session)
    BS.ingest_cross_stage_cache(gov_session, disc, caps, processed, cand_map)

    def count(t):
        return gov_session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
    assert count("discovery_school") == 1
    assert count("candidate") == 1
    assert count("capture") == 2           # both h1 and the FAILED h2
    assert count("processed_doc") == 1     # only the processed h1


def test_discovery_funnel_rollups(gov_session):
    disc, caps, processed, cand_map = _fixtures()
    _create_cache_temp(gov_session)
    BS.ingest_cross_stage_cache(gov_session, disc, caps, processed, cand_map)
    row = gov_session.execute(text(
        "SELECT wave1_n_raw, wave1_n_kept, wave2_invoked, wave2_n_raw, wave2_n_kept, outcome "
        "FROM discovery_school WHERE school_id='s1'")).mappings().first()
    assert row["wave1_n_raw"] == 2 and row["wave1_n_kept"] == 1   # one of two gated kept
    assert row["wave2_invoked"] == 1
    assert row["wave2_n_raw"] == 1 and row["wave2_n_kept"] == 1
    assert row["outcome"] == "found"


def test_capture_includes_failed_and_carries_final_host(gov_session):
    disc, caps, processed, cand_map = _fixtures()
    _create_cache_temp(gov_session)
    BS.ingest_cross_stage_cache(gov_session, disc, caps, processed, cand_map)
    rows = {r["hash"]: r for r in gov_session.execute(text(
        "SELECT hash, ok, final_host, text_times FROM capture WHERE district_id='d1'")).mappings()}
    assert rows["h1"]["ok"] == 1 and rows["h1"]["final_host"] == "x" and rows["h1"]["text_times"] == 3
    assert rows["h2"]["ok"] == 0           # the failed capture is recorded, not dropped


def test_candidate_carries_school_map(gov_session):
    disc, caps, processed, cand_map = _fixtures()
    _create_cache_temp(gov_session)
    BS.ingest_cross_stage_cache(gov_session, disc, caps, processed, cand_map)
    row = gov_session.execute(text(
        "SELECT url, n_schools, schools_json FROM candidate WHERE district_id='d1'")).mappings().first()
    assert row["url"] == "http://x/plan" and row["n_schools"] == 1
    assert "A Elem" in row["schools_json"]
