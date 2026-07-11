"""Stage 5 ATTENTION scoring (the district-driven console).

Pure-function tests of the band model (record_attention / district_attention) — no DB — plus an
integration test of recompute_attention against the real governance Postgres via connection-scoped TEMP
tables (gov_session), so the SQL + rollup run on the actual engine without touching real data.

The load-bearing property under test is INVERTED CONFIDENCE: a clean tier-A target scores LOW (a swift
yes), while promising-but-unresolved records (image-only, signal/tier disagreement, buried-in-handbook)
and explicit flags score HIGH.
"""
import json

import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import attention as AT


def _cfg():
    return AT.load_config()


CLEAN = {"visual_text_gap": False, "positive_kw": ["bell schedule"], "proximity_pairs": 2,
         "has_table": True, "n_times_in_window": 6, "is_handbook": False, "harvest_pages": []}
IMAGE = {"visual_text_gap": True, "positive_kw": ["bell schedule"], "proximity_pairs": 0,
         "has_table": False, "n_times_in_window": 0, "is_handbook": False, "harvest_pages": []}
DISAGREE = {"visual_text_gap": False, "positive_kw": ["school hours"], "proximity_pairs": 1,
            "has_table": False, "n_times_in_window": 1, "is_handbook": False, "harvest_pages": []}
BURIED = {"visual_text_gap": False, "positive_kw": [], "proximity_pairs": 0, "instructional_time": True,
          "has_table": False, "n_times_in_window": 0, "is_handbook": True, "harvest_pages": [12, 13]}
JUNK = {"visual_text_gap": False, "positive_kw": [], "proximity_pairs": 0, "has_table": False,
        "n_times_in_window": 0, "is_handbook": False, "harvest_pages": []}


class TestRecordAttention:
    def test_clean_tier_a_is_low(self):
        """The crux of inverted-confidence: a clean tier-A target is a swift yes -> LOW attention."""
        a = AT.record_attention(CLEAN, "A", "unlabeled", _cfg())
        assert a["reasons"] == ["clean_target"] and a["score"] == 10

    def test_image_only_is_high(self):
        a = AT.record_attention(IMAGE, "C", "unlabeled", _cfg())
        assert a["reasons"] == ["image_only"] and a["score"] == 70

    def test_signal_text_disagreement_is_high(self):
        a = AT.record_attention(DISAGREE, "C", "unlabeled", _cfg())
        assert a["reasons"] == ["signal_text_disagree"] and a["score"] == 65

    def test_buried_handbook_is_elevated(self):
        a = AT.record_attention(BURIED, "B", "unlabeled", _cfg())
        assert a["reasons"] == ["buried_long_doc"] and a["score"] == 55

    def test_junk_is_lowest(self):
        a = AT.record_attention(JUNK, "D", "unlabeled", _cfg())
        assert a["reasons"] == ["low_signal"] and a["score"] == 5

    def test_resolved_zeros_out(self):
        a = AT.record_attention(CLEAN, "A", "labeled", _cfg())
        assert a["reasons"] == ["resolved"] and a["score"] == 0

    def test_flag_overrides_even_resolved(self):
        a = AT.record_attention(CLEAN, "A", "labeled", _cfg(), has_flag=True)
        assert a["reasons"][0] == "manual_flag" and a["score"] == 100


class TestDistrictAttention:
    def test_max_plus_capped_volume(self):
        cfg = _cfg()
        atts = [AT.record_attention(IMAGE, "C", "unlabeled", cfg),       # 70
                AT.record_attention(CLEAN, "A", "unlabeled", cfg)]       # 10
        d = AT.district_attention(atts, cfg)
        assert d["score"] == 70 + 1 * cfg["thresholds"]["district_volume_per_extra"]   # base 70 + 1 extra
        assert d["reasons"][0] == "image_only"

    def test_all_resolved_is_zero(self):
        cfg = _cfg()
        d = AT.district_attention([AT.record_attention(CLEAN, "A", "labeled", cfg)], cfg)
        assert d["score"] == 0 and d["reasons"] == ["resolved"]

    def test_district_flag_floors_at_manual_flag_weight(self):
        cfg = _cfg()
        atts = [AT.record_attention(JUNK, "D", "unlabeled", cfg)]        # 5
        d = AT.district_attention(atts, cfg, has_district_flag=True)
        assert d["score"] == cfg["weights"]["manual_flag"] and "manual_flag" in d["reasons"]


# ----------------------------------------------------------------- recompute_attention (DB integration)
def _temp_schema(s):
    """Minimal TEMP record/label/district tables for recompute_attention (the columns it reads/writes)."""
    s.execute(text("""CREATE TEMP TABLE district (district_id text PRIMARY KEY, attention_score double precision,
        attention_reasons_json text, pipeline_state text, n_unlabeled integer, n_flagged integer)"""))
    s.execute(text("""CREATE TEMP TABLE record (rec_key text PRIMARY KEY, district_id text, tier text,
        signals_json text, duplicate_of text, is_cluster_rep integer, cluster_id text,
        attention_score double precision, attention_reasons_json text)"""))
    s.execute(text("CREATE TEMP TABLE label (rec_key text PRIMARY KEY, status text DEFAULT 'unlabeled')"))
    s.execute(text("""CREATE TEMP TABLE followup_flag (id serial PRIMARY KEY, scope text, target_id text,
        district_id text, directive text, actor text, created_at text, resolved_at text)"""))


def _add_record(s, did, rk, tier, sig, status="unlabeled"):
    s.execute(text("INSERT INTO record (rec_key, district_id, tier, signals_json, is_cluster_rep) "
                   "VALUES (:rk,:d,:t,:sg,1)"), {"rk": rk, "d": did, "t": tier, "sg": json.dumps(sig)})
    s.execute(text("INSERT INTO label (rec_key, status) VALUES (:rk,:st)"), {"rk": rk, "st": status})


@pytest.mark.govdb   # #201: hits the governance DB via gov_session (TEMP tables) — the pure band-model tests above stay DB-free
def test_recompute_attention_persists_record_and_district(gov_session):
    _temp_schema(gov_session)
    gov_session.execute(text("INSERT INTO district (district_id) VALUES ('d1')"))
    _add_record(gov_session, "d1", "d1:a", "C", IMAGE)              # image_only (70), unlabeled
    _add_record(gov_session, "d1", "d1:b", "A", CLEAN, "labeled")  # resolved (0)
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    out = BS.recompute_attention(gov_session, "d1")

    # record scores persisted
    rows = {r[0]: (r[1], json.loads(r[2])) for r in gov_session.execute(text(
        "SELECT rec_key, attention_score, attention_reasons_json FROM record WHERE district_id='d1'"))}
    assert rows["d1:a"][0] == 70 and rows["d1:a"][1] == ["image_only"]
    assert rows["d1:b"][0] == 0 and rows["d1:b"][1] == ["resolved"]
    # district rollup persisted: image_only drives it; 1 unlabeled canonical; partial coverage
    drow = gov_session.execute(text("SELECT attention_score, pipeline_state, n_unlabeled FROM district WHERE district_id='d1'")).first()
    assert drow[0] == 70 and drow[1] == "partial" and drow[2] == 1
    assert out["reasons"][0] == "image_only"


@pytest.mark.govdb   # #201
def test_recompute_attention_all_labeled_is_complete(gov_session):
    _temp_schema(gov_session)
    gov_session.execute(text("INSERT INTO district (district_id) VALUES ('d2')"))
    _add_record(gov_session, "d2", "d2:a", "A", CLEAN, "labeled")
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.recompute_attention(gov_session, "d2")
    drow = gov_session.execute(text("SELECT attention_score, pipeline_state, n_unlabeled FROM district WHERE district_id='d2'")).first()
    assert drow[0] == 0 and drow[1] == "complete" and drow[2] == 0


@pytest.mark.govdb   # #201
def test_recompute_attention_honors_unresolved_followup_flag(gov_session):
    """An unresolved record flag floors that record (and so the district) at the manual-flag weight —
    even though its signals are a clean tier-A that would otherwise score low."""
    _temp_schema(gov_session)
    gov_session.execute(text("INSERT INTO district (district_id) VALUES ('d3')"))
    _add_record(gov_session, "d3", "d3:a", "A", CLEAN, "unlabeled")   # would be clean_target (10)
    gov_session.execute(text("INSERT INTO followup_flag (scope, target_id, district_id, resolved_at) "
                             "VALUES ('record','d3:a','d3', NULL)"))
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.recompute_attention(gov_session, "d3")
    rec = gov_session.execute(text("SELECT attention_score, attention_reasons_json FROM record WHERE rec_key='d3:a'")).first()
    assert rec[0] == 100 and "manual_flag" in json.loads(rec[1])
    nf = gov_session.execute(text("SELECT n_flagged FROM district WHERE district_id='d3'")).scalar()
    assert nf == 1
