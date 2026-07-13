"""Stage 6 (Dispatch) draft-dispatch working store — the pre-freeze DispatchDraft/DispatchDraftDistrict
CRUD/lifecycle. Runs against the isolated governance Postgres via the rolling-back `gov_session` fixture
(skips if Docker is down) — mirrors tests/test_stage1_batch_store.py's pattern. The Stage-5 release read
(`stage6_dispatch.district_release_input`, called internally by `build_handoff_package`/
`dispatch_handoff`) is monkeypatched exactly as tests/test_stage6_dispatch.py already does, so no real
Stage-5 `record`/`label` rows are needed — only the new draft tables' own persistence is under test.
"""
import pytest

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import stage6_dispatch as H6
from infrastructure.acquisition.process_governance import stage6_draft_store as DS6
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage6_handoff import draft_models  # noqa: F401  (registers the draft tables)
from infrastructure.acquisition.stage6_handoff.draft_models import DispatchDraft, DispatchDraftDistrict
from infrastructure.acquisition.stage6_handoff.models import Handoff  # noqa: F401  (registers `handoff`)

pytestmark = pytest.mark.govdb


@pytest.fixture
def sess(gov_session):
    gdb.init_precious_schema()   # ensure dispatch_draft/dispatch_draft_district/handoff exist (idempotent)
    return gov_session


def _fake_release(monkeypatch, district_id="0100810", rec_key="a", label="school_bell_table"):
    """The exact monkeypatch shape test_stage6_dispatch.py uses — no real Stage-5 rows needed."""
    reps = [{"source": "extracted", "filename": "extracted.txt", "file_kind": "text",
             "n_chars": 1200, "n_times": 4, "usable": 1}]
    records = [{"rec_key": rec_key, "url": "u", "tier": "A", "category": None,
                "signals": {"visual_text_gap": False}, "is_emergent": 0, "intended_schools": [],
                "label": label, "flags": [], "reps": reps}]

    def load_district(s, did):
        if did != district_id:
            return None
        return {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                "labeled_topology": "per_school", "nces_denominator": {"total": 1, "by_level": {}}}

    monkeypatch.setattr(REL, "load_district", load_district)
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: records if did == district_id else [])
    monkeypatch.setattr(REL, "district_fingerprints", lambda s, did: {"config": "c", "labels": "l", "data": "d"})


class TestCreateAndLifecycle:
    def test_create_draft_is_empty_and_draft_status(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        d = sess.get(DispatchDraft, draft_id)
        assert d.status == "draft" and d.verified_only is False and d.created_by == "ian"

    def test_draft_numbering_increments(self, sess):
        a = DS6.create_draft(sess, actor="ian")
        b = DS6.create_draft(sess, actor="ian")
        assert a != b
        na = int(a.split("_")[1])
        nb = int(b.split("_")[1])
        assert nb == na + 1

    def test_abandon_refuses_non_draft_status(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.abandon_draft(sess, draft_id, "ian", "superseded")
        with pytest.raises(DS6.DraftLocked):
            DS6.abandon_draft(sess, draft_id, "ian")

    def test_abandon_succeeds_on_draft(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.abandon_draft(sess, draft_id, "ian", "changed my mind")
        d = sess.get(DispatchDraft, draft_id)
        assert d.status == "abandoned" and d.abandon_reason == "changed my mind" and d.abandoned_by == "ian"


class TestDistrictEdits:
    def test_add_district_creates_included_row(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        row = sess.get(DispatchDraftDistrict, (draft_id, "0100810"))
        assert row.included is True and row.overrides_json == {}

    def test_remove_then_restore_never_deletes_the_row(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        DS6.remove_district(sess, draft_id, "0100810")
        row = sess.get(DispatchDraftDistrict, (draft_id, "0100810"))
        assert row is not None and row.included is False    # soft, never hard-deleted
        DS6.restore_district(sess, draft_id, "0100810")
        assert sess.get(DispatchDraftDistrict, (draft_id, "0100810")).included is True

    def test_edits_refuse_on_non_draft_status(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        DS6.abandon_draft(sess, draft_id, "ian")
        with pytest.raises(DS6.DraftLocked):
            DS6.add_district(sess, draft_id, "0101410")
        with pytest.raises(DS6.DraftLocked):
            DS6.remove_district(sess, draft_id, "0100810")

    def test_set_and_clear_override_scoped_to_the_right_district(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "D1")
        DS6.add_district(sess, draft_id, "D2")
        DS6.set_override(sess, draft_id, "D1", "D1:hash1", "extracted.txt", "image")
        DS6.set_override(sess, draft_id, "D2", "D2:hash2", "extracted.txt", "low-cost-text")
        r1 = sess.get(DispatchDraftDistrict, (draft_id, "D1"))
        r2 = sess.get(DispatchDraftDistrict, (draft_id, "D2"))
        assert r1.overrides_json == {"D1:hash1::extracted.txt": "image"}
        assert r2.overrides_json == {"D2:hash2::extracted.txt": "low-cost-text"}   # no cross-district leak
        DS6.clear_override(sess, draft_id, "D1", "D1:hash1", "extracted.txt")
        assert sess.get(DispatchDraftDistrict, (draft_id, "D1")).overrides_json == {}
        assert sess.get(DispatchDraftDistrict, (draft_id, "D2")).overrides_json == {"D2:hash2::extracted.txt": "low-cost-text"}

    def test_set_verified_only_flips_the_per_draft_bool(self, sess):
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.set_verified_only(sess, draft_id, True)
        assert sess.get(DispatchDraft, draft_id).verified_only is True
        DS6.set_verified_only(sess, draft_id, False)
        assert sess.get(DispatchDraft, draft_id).verified_only is False


class TestToView:
    def test_to_view_shows_both_included_and_removed_districts(self, sess, monkeypatch):
        _fake_release(monkeypatch, district_id="0100810")
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        DS6.add_district(sess, draft_id, "removed_one")
        DS6.remove_district(sess, draft_id, "removed_one")
        v = DS6.to_view(sess, draft_id)
        ids_flags = {d["district_id"]: d["included"] for d in v["districts"]}
        assert ids_flags == {"0100810": True, "removed_one": False}
        assert "preview_identity" in v and v["preview_identity"]

    def test_to_view_package_only_includes_included_districts(self, sess, monkeypatch):
        _fake_release(monkeypatch, district_id="0100810")
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        DS6.add_district(sess, draft_id, "excluded_district")
        DS6.remove_district(sess, draft_id, "excluded_district")
        v = DS6.to_view(sess, draft_id)
        assert [d["district_id"] for d in v["package"]["districts"]] == ["0100810"]

    def test_to_view_unknown_draft_raises_keyerror(self, sess):
        with pytest.raises(KeyError):
            DS6.to_view(sess, "draft_nonexistent")


class TestFreeze:
    def test_freeze_happy_path_produces_handoff_and_updates_draft(self, sess, monkeypatch, tmp_path):
        _fake_release(monkeypatch, district_id="0100810")
        monkeypatch.setattr(H6.HND, "DEFAULT_ROOT", tmp_path)
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")

        doc = DS6.freeze_draft(sess, draft_id, "ian")

        d = sess.get(DispatchDraft, draft_id)
        assert d.status == "dispatched"
        assert d.handoff_hash == doc["handoff_hash"]
        assert d.dispatched_by == "ian" and d.dispatched_at
        # the same-shape handoff a direct dispatch_handoff() call would have produced
        assert doc["districts"][0]["district_id"] == "0100810"

    def test_freeze_refuses_on_non_draft_status(self, sess, monkeypatch):
        _fake_release(monkeypatch, district_id="0100810")
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        DS6.abandon_draft(sess, draft_id, "ian")
        with pytest.raises(DS6.DraftLocked):
            DS6.freeze_draft(sess, draft_id, "ian")

    def test_freeze_with_zero_included_districts_refuses(self, sess, monkeypatch, tmp_path):
        monkeypatch.setattr(H6.HND, "DEFAULT_ROOT", tmp_path)
        draft_id = DS6.create_draft(sess, actor="ian")
        # 0 districts ever added -> the empty-selection guard in dispatch_handoff() fires
        with pytest.raises(ValueError, match="no districts"):
            DS6.freeze_draft(sess, draft_id, "ian")

    def test_freeze_with_stale_expected_identity_raises(self, sess, monkeypatch, tmp_path):
        _fake_release(monkeypatch, district_id="0100810")
        monkeypatch.setattr(H6.HND, "DEFAULT_ROOT", tmp_path)
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        with pytest.raises(ValueError, match="changed since"):
            DS6.freeze_draft(sess, draft_id, "ian", expected_identity="not-the-real-hash")
        # nothing froze — the draft stays draft, nothing written
        assert sess.get(DispatchDraft, draft_id).status == "draft"

    def test_freeze_with_matching_expected_identity_succeeds(self, sess, monkeypatch, tmp_path):
        _fake_release(monkeypatch, district_id="0100810")
        monkeypatch.setattr(H6.HND, "DEFAULT_ROOT", tmp_path)
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        v = DS6.to_view(sess, draft_id)
        doc = DS6.freeze_draft(sess, draft_id, "ian", expected_identity=v["preview_identity"])
        assert sess.get(DispatchDraft, draft_id).status == "dispatched"
        assert doc["handoff_hash"]


class TestListDispatchRows:
    def test_synthetic_direct_freeze_handoff_reads_as_non_draft_origin(self, sess):
        """A Handoff row with no matching dispatch_draft (e.g. the Stage 7->6 back-edge, which freezes
        directly) must come back tagged as non-draft-origin — the join-absence discriminator."""
        sess.add(Handoff(handoff_id="handoff_synth_20260713T000000Z", handoff_hash="synth1",
                        path="/x.json", n_districts=1, n_reps=1, total_usd=0.001,
                        cost_provenance="bootstrap", district_ids=["0100810"], council_ids=["image"]))
        sess.flush()
        rows = DS6.list_dispatch_rows(sess)
        synth = [r for r in rows if r.get("handoff_hash") == "synth1"][0]
        assert synth["from_draft"] is False

    def test_draft_authored_handoff_reads_as_draft_origin(self, sess, monkeypatch, tmp_path):
        _fake_release(monkeypatch, district_id="0100810")
        monkeypatch.setattr(H6.HND, "DEFAULT_ROOT", tmp_path)
        draft_id = DS6.create_draft(sess, actor="ian")
        DS6.add_district(sess, draft_id, "0100810")
        doc = DS6.freeze_draft(sess, draft_id, "ian")
        rows = DS6.list_dispatch_rows(sess)
        authored = [r for r in rows if r.get("handoff_hash") == doc["handoff_hash"]][0]
        assert authored["from_draft"] is True

    def test_abandoned_and_draft_rows_both_appear(self, sess):
        d1 = DS6.create_draft(sess, actor="ian")
        d2 = DS6.create_draft(sess, actor="ian")
        DS6.abandon_draft(sess, d2, "ian")
        rows = DS6.list_dispatch_rows(sess)
        by_id = {r["draft_id"]: r for r in rows if r["kind"] == "draft"}
        assert by_id[d1]["status"] == "draft" and by_id[d2]["status"] == "abandoned"
