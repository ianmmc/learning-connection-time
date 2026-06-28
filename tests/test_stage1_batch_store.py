"""Stage 1 batch working-store (REQ-102) — doc<->rows mapper + gate@1 edit/approve ops.

Runs against the isolated governance Postgres via the rolling-back `gov_session` fixture (skips if
Docker is down). Every test inserts within a transaction that's rolled back at teardown, so nothing
touches real governance data.
"""
import pytest

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BS
from infrastructure.acquisition.stage1_queue import models  # noqa: F401  (registers the batch tables)
from infrastructure.acquisition.stage1_queue.models import Batch


@pytest.fixture
def sess(gov_session):
    gdb.init_precious_schema()   # ensure batch/batch_district/batch_school exist (idempotent)
    return gov_session


def _doc(bid="batch_test_store"):
    return {
        "batch_id": bid, "created": "2026-06-27T00:00:00Z", "n": 2, "nces_year": "2024_25",
        "stratification": {"priority": ["enrollment", "state"]}, "school_cap_per_band": 12,
        "districts": [
            {"district_id": "D1", "name": "Alpha", "state": "AK", "domain": "alpha.org",
             "enrollment_k12": 500, "lea_claimed_bands": ["elementary", "high"],
             "nces_school_counts": {"total": 3, "by_level": {"Elementary": 2, "High": 1}},
             "band_processing_order": ["high", "elementary"],
             "schools_by_band": {
                 "high": {"n_candidates": 1, "n_unclaimed_at_selection": 1, "n_selected": 1,
                          "schools": [{"school_id": "S_H", "name": "Alpha High", "is_charter": "No",
                                       "level": "High", "gslo": "09", "gshi": "12"}]},
                 "elementary": {"n_candidates": 2, "n_unclaimed_at_selection": 2, "n_selected": 2,
                                "schools": [{"school_id": "S_E1", "name": "Alpha Elem 1", "is_charter": "No",
                                             "level": "Elementary", "gslo": "KG", "gshi": "05"},
                                            {"school_id": "S_E2", "name": "Alpha Elem 2", "is_charter": "No",
                                             "level": "Elementary", "gslo": "KG", "gshi": "05"}]}}},
            {"district_id": "D2", "name": "Beta", "state": "AL", "domain": "",
             "enrollment_k12": 100, "lea_claimed_bands": ["elementary"],
             "nces_school_counts": {"total": 1, "by_level": {"Elementary": 1}},
             "band_processing_order": ["elementary"],
             "schools_by_band": {
                 "elementary": {"n_candidates": 1, "n_unclaimed_at_selection": 1, "n_selected": 1,
                                "schools": [{"school_id": "S_BE", "name": "Beta Elem", "is_charter": "No",
                                             "level": "Elementary", "gslo": "KG", "gshi": "06"}]}}},
        ],
    }


def _ids_by_band(district_doc):
    return {b: sorted(s["school_id"] for s in v["schools"]) for b, v in district_doc["schools_by_band"].items()}


class TestRoundTrip:
    def test_create_then_receipt_reproduces_content(self, sess):
        BS.create_batch(sess, _doc(), actor="tester")
        rec = BS.to_receipt_doc(sess, "batch_test_store")
        assert rec["batch_id"] == "batch_test_store"
        assert rec["nces_year"] == "2024_25"
        assert rec["stratification"]["priority"] == ["enrollment", "state"]   # meta carried through
        assert [d["district_id"] for d in rec["districts"]] == ["D1", "D2"]    # pick order preserved
        d1 = rec["districts"][0]
        assert _ids_by_band(d1) == {"high": ["S_H"], "elementary": ["S_E1", "S_E2"]}
        assert d1["schools_by_band"]["elementary"]["n_selected"] == 2
        assert rec["n"] == 2

    def test_multiband_school_collapses_to_one_row(self, sess):
        doc = _doc("batch_test_mb")
        # the high school also serves middle -> appears in both bands
        doc["districts"][0]["band_processing_order"] = ["high", "middle", "elementary"]
        doc["districts"][0]["schools_by_band"]["middle"] = {
            "n_candidates": 1, "n_unclaimed_at_selection": 0, "n_selected": 1,
            "schools": [{"school_id": "S_H", "name": "Alpha High", "is_charter": "No",
                         "level": "Secondary", "gslo": "07", "gshi": "12"}]}
        BS.create_batch(sess, doc, actor="t")
        from infrastructure.acquisition.stage1_queue.models import BatchSchool
        rows = list(sess.scalars(__import__("sqlalchemy").select(BatchSchool).where(
            BatchSchool.batch_id == "batch_test_mb", BatchSchool.school_id == "S_H")))
        assert len(rows) == 1 and sorted(rows[0].bands) == ["high", "middle"]
        rec = BS.to_receipt_doc(sess, "batch_test_mb")
        sbb = rec["districts"][0]["schools_by_band"]
        assert "S_H" in [s["school_id"] for s in sbb["high"]["schools"]]
        assert "S_H" in [s["school_id"] for s in sbb["middle"]["schools"]]


class TestGate1Edits:
    def test_reject_school_drops_it_from_receipt(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.reject_school(sess, "batch_test_store", "D1", "S_E1")
        rec = BS.to_receipt_doc(sess, "batch_test_store")
        elem = rec["districts"][0]["schools_by_band"]["elementary"]
        assert [s["school_id"] for s in elem["schools"]] == ["S_E2"]
        assert elem["n_selected"] == 1   # live recount

    def test_reject_district_drops_it_from_receipt_but_view_keeps_it(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.reject_district(sess, "batch_test_store", "D2")
        rec = BS.to_receipt_doc(sess, "batch_test_store")
        assert [d["district_id"] for d in rec["districts"]] == ["D1"]
        assert rec["n"] == 1
        view = BS.to_view(sess, "batch_test_store")
        d2 = next(d for d in view["districts"] if d["district_id"] == "D2")
        assert d2["included"] is False
        assert view["n_included"] == 1

    def test_add_school_inserts_with_manual_source(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.add_school(sess, "batch_test_store", "D2",
                      {"school_id": "S_NEW", "name": "Beta High", "level": "High", "gslo": "09", "gshi": "12"},
                      ["high"])
        rec = BS.to_receipt_doc(sess, "batch_test_store")
        d2 = next(d for d in rec["districts"] if d["district_id"] == "D2")
        assert "S_NEW" in [s["school_id"] for s in d2["schools_by_band"]["high"]["schools"]]
        view = BS.to_view(sess, "batch_test_store")
        d2v = next(d for d in view["districts"] if d["district_id"] == "D2")
        newrow = next(s for s in d2v["schools_by_band"]["high"]["schools"] if s["school_id"] == "S_NEW")
        assert newrow["source"] == "manual_add"


class TestLifecycle:
    def test_approve_sets_status_and_stamp(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.approve_batch(sess, "batch_test_store", "ian")
        b = sess.get(Batch, "batch_test_store")
        assert b.status == "approved" and b.approved_by == "ian" and b.approved_at

    def test_editing_locked_after_approval(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.approve_batch(sess, "batch_test_store", "ian")
        with pytest.raises(BS.BatchLocked):
            BS.reject_school(sess, "batch_test_store", "D1", "S_E1")

    def test_reopen_unlocks_editing(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.approve_batch(sess, "batch_test_store", "ian")
        BS.reopen_batch(sess, "batch_test_store", "ian")
        b = sess.get(Batch, "batch_test_store")
        assert b.status == "draft" and b.approved_at is None
        BS.reject_school(sess, "batch_test_store", "D1", "S_E1")   # no longer raises

    def test_list_batches_reports_included_count(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.reject_district(sess, "batch_test_store", "D2")
        rows = [b for b in BS.list_batches(sess) if b["batch_id"] == "batch_test_store"]
        assert len(rows) == 1 and rows[0]["n_districts"] == 1 and rows[0]["status"] == "draft"
