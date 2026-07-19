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

# #201: every test here hits the governance DB via gov_session (rolling-back) + init_precious_schema —
# mark govdb so it runs in CI's governance-db job and is cleanly excluded from the DB-free job.
pytestmark = pytest.mark.govdb


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
        assert rec["batch_type"] == "first-run"   # #174: reconcile keys follow-up redo off the receipt
        assert rec["nces_year"] == "2024_25"
        assert rec["stratification"]["priority"] == ["enrollment", "state"]   # meta carried through
        assert [d["district_id"] for d in rec["districts"]] == ["D1", "D2"]    # pick order preserved
        d1 = rec["districts"][0]
        assert _ids_by_band(d1) == {"high": ["S_H"], "elementary": ["S_E1", "S_E2"]}
        assert d1["schools_by_band"]["elementary"]["n_selected"] == 2
        assert rec["n"] == 2

    def test_followup_shaping_round_trips(self, sess):
        # #160/#161: query_strategy (per band) + seed_urls (per district) survive create -> receipt
        doc = _doc("batch_test_followup")
        doc["districts"][0]["schools_by_band"]["high"]["query_strategy"] = "widen_queries"
        doc["districts"][0]["schools_by_band"]["elementary"]["query_strategy"] = "new_schools"
        doc["districts"][0]["seed_urls"] = ["http://x/handbook.pdf"]
        BS.create_batch(sess, doc, batch_type="follow-up", actor="t")
        rec = BS.to_receipt_doc(sess, "batch_test_followup")
        assert rec["batch_type"] == "follow-up"   # #174: the redo signal Stage 2/3/4 reconcile reads
        d1 = rec["districts"][0]
        assert d1["schools_by_band"]["high"]["query_strategy"] == "widen_queries"
        assert d1["schools_by_band"]["elementary"]["query_strategy"] == "new_schools"
        assert d1["seed_urls"] == ["http://x/handbook.pdf"]
        # a plain (first-run) district carries neither key
        assert "query_strategy" not in rec["districts"][1]["schools_by_band"]["elementary"]
        assert "seed_urls" not in rec["districts"][1]

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


class TestWorkingDoc:
    """#555 review: to_working_doc is the console's DB batch resolve — canonical batch_doc +
    live batch_status — while to_receipt_doc stays DELIBERATELY status-free (batch_guard relies
    on the on-disk receipt carrying no status a CLI loader could wrongly trust)."""

    def test_working_doc_is_receipt_doc_plus_status(self, sess):
        BS.create_batch(sess, _doc(), actor="test")
        wd = BS.to_working_doc(sess, "batch_test_store")
        assert wd["batch_status"] == "draft"
        assert {k: v for k, v in wd.items() if k != "batch_status"} == \
            BS.to_receipt_doc(sess, "batch_test_store")

    def test_receipt_doc_never_carries_status(self, sess):
        BS.create_batch(sess, _doc(), actor="test")
        BS.approve_batch(sess, "batch_test_store", "test")
        rec = BS.to_receipt_doc(sess, "batch_test_store")
        assert "batch_status" not in rec and "status" not in rec

    def test_working_doc_unknown_batch_is_none(self, sess):
        assert BS.to_working_doc(sess, "batch_nope_999") is None

    def test_meta_key_cannot_shadow_computed_fields(self, sess):
        """The meta_json spread comes FIRST in the doc literal, so a stray meta key named after
        a computed/explicit field loses to the real value instead of silently replacing it."""
        BS.create_batch(sess, _doc(), actor="test")
        b = sess.get(Batch, "batch_test_store")
        b.meta_json = {**(b.meta_json or {}), "n": 999, "nces_year": "1999_00"}
        sess.flush()
        rec = BS.to_receipt_doc(sess, "batch_test_store")
        assert rec["n"] == 2 and rec["nces_year"] == "2024_25"
        wd = BS.to_working_doc(sess, "batch_test_store")
        assert wd["n"] == 2 and wd["nces_year"] == "2024_25"
        view = BS.to_view(sess, "batch_test_store")
        assert view["status"] == "draft" and view["nces_year"] == "2024_25"


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

    def test_reject_then_restore_is_reversible(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.reject_school(sess, "batch_test_store", "D1", "S_E1")
        BS.restore_school(sess, "batch_test_store", "D1", "S_E1")
        BS.reject_district(sess, "batch_test_store", "D2")
        BS.restore_district(sess, "batch_test_store", "D2")
        rec = BS.to_receipt_doc(sess, "batch_test_store")
        assert [d["district_id"] for d in rec["districts"]] == ["D1", "D2"]   # D2 back
        elem = rec["districts"][0]["schools_by_band"]["elementary"]
        assert {s["school_id"] for s in elem["schools"]} == {"S_E1", "S_E2"}  # S_E1 back

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

    def test_abandon_sets_terminal_status_and_audit(self, sess):
        # #168: a draft can be retired to a terminal `abandoned` status carrying who/when/why.
        BS.create_batch(sess, _doc(), actor="t")
        BS.abandon_batch(sess, "batch_test_store", "ian", reason="superseded")
        b = sess.get(Batch, "batch_test_store")
        assert b.status == "abandoned" and b.abandoned_by == "ian" and b.abandoned_at
        assert b.abandon_reason == "superseded"
        view = BS.to_view(sess, "batch_test_store")
        assert view["status"] == "abandoned" and view["abandon_reason"] == "superseded"
        row = next(r for r in BS.list_batches(sess) if r["batch_id"] == "batch_test_store")
        assert row["status"] == "abandoned" and row["abandoned_by"] == "ian"

    def test_abandon_is_terminal_no_approve_reopen_or_edit(self, sess):
        # #168: abandoned is terminal — approve/reopen/edit all refuse it (no silent resurrection).
        BS.create_batch(sess, _doc(), actor="t")
        BS.abandon_batch(sess, "batch_test_store", "ian")
        with pytest.raises(BS.BatchLocked):
            BS.approve_batch(sess, "batch_test_store", "ian")
        with pytest.raises(BS.BatchLocked):
            BS.reopen_batch(sess, "batch_test_store", "ian")
        with pytest.raises(BS.BatchLocked):
            BS.reject_school(sess, "batch_test_store", "D1", "S_E1")

    def test_abandon_refuses_an_ever_approved_batch(self, sess):
        # #168 review: abandon is NEVER-APPROVED-only. Once approved, a batch's schools are committed as
        # attempted; the durable first_approved_at survives reopen, so BOTH direct abandon AND the
        # reopen->abandon path are refused (closing the #162 poison the terminal status would otherwise
        # reintroduce for an already-ran batch).
        BS.create_batch(sess, _doc(), actor="t")
        BS.approve_batch(sess, "batch_test_store", "ian")
        with pytest.raises(BS.BatchLocked):
            BS.abandon_batch(sess, "batch_test_store", "ian")   # approved -> refused
        BS.reopen_batch(sess, "batch_test_store", "ian")        # back to draft, but first_approved_at stays set
        with pytest.raises(BS.BatchLocked):
            BS.abandon_batch(sess, "batch_test_store", "ian")   # reopen->abandon STILL refused (bypass closed)
        assert sess.get(Batch, "batch_test_store").status == "draft"

    def test_first_approved_at_is_durable_across_reopen(self, sess):
        # #168 review: approve stamps the durable first_approved_at; reopen clears approved_at but NOT
        # first_approved_at (the honest "were these schools ever committed to discovery" signal).
        BS.create_batch(sess, _doc(), actor="t")
        BS.approve_batch(sess, "batch_test_store", "ian")
        fa = sess.get(Batch, "batch_test_store").first_approved_at
        assert fa
        BS.reopen_batch(sess, "batch_test_store", "ian")
        b = sess.get(Batch, "batch_test_store")
        assert b.approved_at is None and b.first_approved_at == fa


class TestReservation:
    """Issue #46 — the create path reserves the batch id up front, in its own short transaction,
    before the 10-20s build_batch; a concurrent create can no longer draw the same number."""

    def test_reserve_returns_sequential_ids_and_persists_placeholder(self, sess):
        bid1 = BS.reserve_next_batch(sess, actor="t")
        bid2 = BS.reserve_next_batch(sess, actor="t")
        n1, n2 = int(bid1[6:]), int(bid2[6:])
        assert n2 == n1 + 1                      # the flushed placeholder claims the number
        b = sess.get(Batch, bid1)
        assert b is not None and b.status == "reserving" and b.created_by == "t"

    def test_create_batch_upgrades_a_reservation_in_place(self, sess):
        bid = BS.reserve_next_batch(sess, actor="t")
        doc = _doc(bid)
        BS.create_batch(sess, doc, actor="ian")   # must NOT raise a duplicate-PK error
        b = sess.get(Batch, bid)
        assert b.status == "draft" and b.created_by == "ian" and b.nces_year == "2024_25"
        # and the receipt content is the real batch
        receipt = BS.to_receipt_doc(sess, bid)
        assert [d["district_id"] for d in receipt["districts"]] == ["D1", "D2"]

    def test_release_reservation_frees_the_number(self, sess):
        bid = BS.reserve_next_batch(sess, actor="t")
        BS.release_reservation(sess, bid)
        assert sess.get(Batch, bid) is None
        assert BS.reserve_next_batch(sess, actor="t") == bid   # the number is reusable

    def test_release_never_deletes_a_real_batch(self, sess):
        BS.create_batch(sess, _doc(), actor="t")
        BS.release_reservation(sess, "batch_test_store")       # status='draft', not 'reserving'
        assert sess.get(Batch, "batch_test_store") is not None


class TestReceiptAtomicity:
    """Issue #50 — write_receipt goes tmp + os.replace so a crash mid-write can't leave a truncated
    receipt (mirrors export_status)."""

    def test_write_receipt_writes_via_replace_and_leaves_no_tmp(self, sess, tmp_path, monkeypatch):
        import json as _json
        monkeypatch.setattr(BS.paths, "QUEUE_DIR", tmp_path)
        BS.create_batch(sess, _doc(), actor="t")
        out = BS.write_receipt(sess, "batch_test_store")
        assert out == tmp_path / "batch_test_store.json"
        assert _json.loads(out.read_text())["batch_id"] == "batch_test_store"
        assert list(tmp_path.glob("*.tmp")) == []              # tmp file was replaced away

    def test_crash_between_tmp_and_replace_keeps_the_old_receipt(self, sess, tmp_path, monkeypatch):
        monkeypatch.setattr(BS.paths, "QUEUE_DIR", tmp_path)
        BS.create_batch(sess, _doc(), actor="t")
        out = tmp_path / "batch_test_store.json"
        out.write_text('{"old": "receipt"}')                   # the prior good receipt
        def boom(src, dst):
            raise OSError("simulated crash at replace")
        monkeypatch.setattr(BS.paths.os, "replace", boom)      # #554: the pattern lives in paths.atomic_write_json now
        with pytest.raises(OSError):
            BS.write_receipt(sess, "batch_test_store")
        assert out.read_text() == '{"old": "receipt"}'         # untouched — no partial overwrite


class TestCreateBatchCollision:
    """#264 — a non-reserving batch already owning the id must refuse cleanly, not die on the
    PK IntegrityError at flush."""

    def test_create_over_existing_draft_raises_batch_locked(self, sess):
        BS.create_batch(sess, _doc("batch_collide"), actor="t")
        with pytest.raises(BS.BatchLocked, match="already exists \\(draft\\)"):
            BS.create_batch(sess, _doc("batch_collide"), actor="t")

    def test_reservation_upgrade_still_works(self, sess):
        bid = BS.reserve_next_batch(sess, actor="t")
        BS.create_batch(sess, _doc(bid), actor="t")   # the one sanctioned same-id path
        assert sess.get(Batch, bid).status == "draft"


class TestBatchScopedProgress:
    """#339 — progress counts must come from the batch's OWN events; a district's first-run
    progress must not bleed into a later follow-up batch containing it."""

    @staticmethod
    def _event(sess, district_id, stage, batch_id, outcome="ok"):
        from infrastructure.acquisition.common.district_status import INSERT_STATE_EVENT
        sess.execute(INSERT_STATE_EVENT, {
            "district_id": district_id, "name": "N", "state": "AK", "stage": stage,
            "stage_name": f"stage{stage}", "checkpoint": None, "event_type": outcome,
            "outcome": outcome, "topology": None, "batch_id": batch_id,
            "fingerprints_json": None, "actor": "t", "note": None,
            "created_at": "2026-07-18T00:00:00Z"})

    def test_followup_batch_shows_no_progress_from_first_run(self, sess):
        BS.create_batch(sess, _doc("batch_first"), actor="t")
        BS.create_batch(sess, _doc("batch_follow"), batch_type="follow-up", actor="t")
        for stage in (2, 3, 4):
            self._event(sess, "D1", stage, "batch_first")
        prog = BS._batch_progress(sess)
        assert prog["batch_first"]["discovered"] == 1
        assert prog["batch_first"]["processed"] == 1
        # pre-#339 this read 1/1/1 — the first run's global snapshot bled in
        assert prog["batch_follow"]["discovered"] == 0
        assert prog["batch_follow"]["captured"] == 0
        assert prog["batch_follow"]["processed"] == 0

    def test_followup_batch_counts_its_own_events(self, sess):
        BS.create_batch(sess, _doc("batch_first2"), actor="t")
        BS.create_batch(sess, _doc("batch_follow2"), batch_type="follow-up", actor="t")
        self._event(sess, "D1", 4, "batch_first2")
        self._event(sess, "D1", 2, "batch_follow2")
        prog = BS._batch_progress(sess)
        assert prog["batch_follow2"]["discovered"] == 1
        assert prog["batch_follow2"]["captured"] == 0   # its own redo hasn't captured yet

    def test_flagged_is_batch_scoped_and_latest_wins(self, sess):
        BS.create_batch(sess, _doc("batch_flag"), actor="t")
        self._event(sess, "D2", 2, "batch_flag", outcome="manual_flag_all")
        prog = BS._batch_progress(sess)
        assert prog["batch_flag"]["flagged"] == 1
        self._event(sess, "D2", 2, "batch_flag", outcome="found_all")   # later event supersedes
        assert BS._batch_progress(sess)["batch_flag"]["flagged"] == 0
