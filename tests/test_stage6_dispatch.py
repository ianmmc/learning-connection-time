"""Stage 6 dispatch recording (REQ-101, slice 6): the precious `handoff` index row + the
`dispatched` state_event, and the `dispatch_handoff` orchestration (freeze -> write -> record),
stopping at — not crossing — the Stage 6->7 seam (no paid calls).
"""
import json

import pytest

from infrastructure.acquisition.process_governance import stage6_dispatch as BR
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage6_handoff.models import Handoff


# --------------------------- the model ---------------------------
def test_handoff_model_columns():
    h = Handoff(handoff_id="handoff_abc_20260630T000000Z", handoff_hash="abc", path="/x.json",
                n_districts=1, n_reps=2, total_usd=0.005, cost_provenance="bootstrap",
                district_ids=["0100810"], council_ids=["low-cost-text"])
    assert h.__tablename__ == "handoff"
    assert h.handoff_hash == "abc" and h.n_reps == 2 and h.council_ids == ["low-cost-text"]


# --------------------------- orchestration (monkeypatched; no DB) ---------------------------
def test_dispatch_handoff_freezes_writes_and_records(tmp_path, monkeypatch):
    reps = [{"source": "extracted", "filename": "extracted.txt", "file_kind": "text",
             "n_chars": 1200, "n_times": 4, "usable": 1}]
    records = [{"rec_key": "a", "url": "u", "tier": "A", "category": None,
                "signals": {"visual_text_gap": False}, "is_emergent": 0, "intended_schools": [],
                "label": "school_bell_table", "flags": [], "reps": reps}]
    monkeypatch.setattr(REL, "load_district",
                        lambda s, did: {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                                        "labeled_topology": "per_school",
                                        "nces_denominator": {"total": 1, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: records)
    monkeypatch.setattr(REL, "district_fingerprints",
                        lambda s, did: {"config": "c", "labels": "l", "data": "d"})
    # #618: these tests pass session=None and monkeypatch every DB accessor; stub the guard's
    # provenance READ (not the guard itself) so assert_dispatch_type_allowed still runs for real.
    monkeypatch.setattr(BR, "benchmark_reps_in_package", lambda session, package: [])
    monkeypatch.setattr(BR.BM, "benchmark_provenance_rec_keys", lambda s, k: set())  # #679, same reason

    captured = {}
    monkeypatch.setattr(BR, "record_dispatch",
                        lambda session, doc, path, actor="human", metas=None: captured.update(doc=doc, path=path, actor=actor))

    doc, path = BR.dispatch_handoff(session=None, district_ids=["0100810"],
                                    created_by="ian", root=tmp_path)

    # the immutable artifact was actually written, and matches the returned doc
    assert path.exists()
    assert json.loads(path.read_text())["handoff_hash"] == doc["handoff_hash"]
    assert doc["fingerprints"]["0100810"] == {"config": "c", "labels": "l", "data": "d"}
    assert set(doc["councils"]) == {"low-cost-text"}              # only the used council frozen in
    # recording was invoked with the frozen doc + the written path
    assert captured["doc"]["handoff_hash"] == doc["handoff_hash"]
    assert captured["path"] == path and captured["actor"] == "ian"


def test_dispatch_writes_per_district_capture_receipt(tmp_path, monkeypatch):
    """REQ-164: dispatch drops a per-district gate@6 audit receipt into the capture dir, pointing at
    the authoritative handoff file."""
    from infrastructure.acquisition.common import paths
    from infrastructure.acquisition.common import receipts as RCPT
    monkeypatch.setattr(paths, "RAW_CAPTURES", tmp_path / "caps")
    reps = [{"source": "extracted", "filename": "e.txt", "file_kind": "text", "n_chars": 10,
             "n_times": 1, "usable": 1}]
    records = [{"rec_key": "a", "url": "u", "tier": "A", "category": None,
                "signals": {"visual_text_gap": False}, "is_emergent": 0, "intended_schools": [],
                "label": "school_bell_table", "flags": [], "reps": reps}]
    monkeypatch.setattr(REL, "load_district",
                        lambda s, did: {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                                        "labeled_topology": "per_school",
                                        "nces_denominator": {"total": 1, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: records)
    monkeypatch.setattr(REL, "district_fingerprints",
                        lambda s, did: {"config": "c", "labels": "l", "data": "d"})
    # #618: these tests pass session=None and monkeypatch every DB accessor; stub the guard's
    # provenance READ (not the guard itself) so assert_dispatch_type_allowed still runs for real.
    monkeypatch.setattr(BR, "benchmark_reps_in_package", lambda session, package: [])
    monkeypatch.setattr(BR.BM, "benchmark_provenance_rec_keys", lambda s, k: set())  # #679, same reason
    monkeypatch.setattr(BR, "record_dispatch",
                        lambda session, doc, path, actor="human", metas=None: None)

    # a globally-unique district id so latest_receipt can never pick up another test's same-second
    # receipt (RAW_CAPTURES isolation can fall to the shared pytest quarantine when an earlier test
    # reloads the paths module — a unique id makes the assertion robust regardless).
    doc, path = BR.dispatch_handoff(session=None, district_ids=["6660066"],
                                    created_by="ian", root=tmp_path)

    cap = RCPT.latest_receipt("6660066", "", "stage6_dispatch")
    assert cap is not None and ".py-" in cap.name
    d = json.loads(cap.read_text())
    assert d["stage"] == 6 and d["checkpoint"] == "gate@6" and d["district_id"] == "6660066"
    assert d["handoff_file"] == path.name and d["handoff_hash"] == doc["handoff_hash"]


def test_dispatch_handoff_is_immutable_on_repeat(tmp_path, monkeypatch):
    monkeypatch.setattr(REL, "load_district",
                        lambda s, did: {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                                        "labeled_topology": "per_school",
                                        "nces_denominator": {"total": 1, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: [])
    monkeypatch.setattr(REL, "district_fingerprints", lambda s, did: {})
    # #618: these tests pass session=None and monkeypatch every DB accessor; stub the guard's
    # provenance READ (not the guard itself) so assert_dispatch_type_allowed still runs for real.
    monkeypatch.setattr(BR, "benchmark_reps_in_package", lambda session, package: [])
    monkeypatch.setattr(BR.BM, "benchmark_provenance_rec_keys", lambda s, k: set())  # #679, same reason
    monkeypatch.setattr(BR, "record_dispatch", lambda *a, **k: None)
    # freeze the clock so both calls produce the same filename, proving write() refuses to overwrite
    monkeypatch.setattr("infrastructure.acquisition.stage6_handoff.handoff._now", lambda: "2026-06-30T00:00:00Z")
    BR.dispatch_handoff(session=None, district_ids=["0100810"], root=tmp_path)
    with pytest.raises(FileExistsError):
        BR.dispatch_handoff(session=None, district_ids=["0100810"], root=tmp_path)


def test_dispatch_handoff_refuses_an_empty_effective_selection(tmp_path, monkeypatch):
    # issue #53: all-unknown districts must NOT freeze a 0-district handoff — refuse loudly,
    # surfacing the skipped ids
    monkeypatch.setattr(REL, "load_district", lambda s, did: None)
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: [])
    monkeypatch.setattr(REL, "district_fingerprints", lambda s, did: {})
    # #618: these tests pass session=None and monkeypatch every DB accessor; stub the guard's
    # provenance READ (not the guard itself) so assert_dispatch_type_allowed still runs for real.
    monkeypatch.setattr(BR, "benchmark_reps_in_package", lambda session, package: [])
    monkeypatch.setattr(BR.BM, "benchmark_provenance_rec_keys", lambda s, k: set())  # #679, same reason
    monkeypatch.setattr(BR, "record_dispatch", lambda *a, **k: None)
    with pytest.raises(ValueError, match="9999999"):
        BR.dispatch_handoff(session=None, district_ids=["9999999"], root=tmp_path)
    with pytest.raises(ValueError, match="no districts were selected"):
        BR.dispatch_handoff(session=None, district_ids=[], root=tmp_path)
    assert not list(tmp_path.iterdir())          # nothing was frozen/written


# --------------------------- the real DB index insert ---------------------------
@pytest.mark.govdb
@pytest.mark.integration
def test_insert_handoff_row_against_postgres(gov_session):
    # create the real Handoff table on the rolled-back fixture connection (no pollution)
    Handoff.__table__.create(bind=gov_session.connection(), checkfirst=True)
    doc = {"handoff_hash": "deadbeef0001", "created_at": "2026-06-30T00:00:00Z", "created_by": "ian",
           "councils": {"low-cost-text": {}}, "fingerprints": {},
           "cost": {"total_usd": 0.00204, "n_reps": 2, "provenance": "bootstrap"},
           "districts": [{"district_id": "0100810"}, {"district_id": "0101410"}]}
    hid = BR.insert_handoff_row(gov_session, doc, "/data/handoffs/x.json")
    assert hid == "handoff_deadbeef0001_20260630T000000Z"
    row = gov_session.get(Handoff, hid)
    assert row.n_districts == 2 and row.n_reps == 2
    assert row.cost_provenance == "bootstrap" and row.status == "dispatched"
    assert row.district_ids == ["0100810", "0101410"]
    assert row.council_ids == ["low-cost-text"]


def _fake_release(monkeypatch):
    reps = [{"source": "extracted", "filename": "extracted.txt", "file_kind": "text",
             "n_chars": 1200, "n_times": 4, "usable": 1}]
    records = [{"rec_key": "a", "url": "u", "tier": "A", "category": None,
                "signals": {"visual_text_gap": False}, "is_emergent": 0, "intended_schools": [],
                "label": "school_bell_table", "flags": [], "reps": reps}]
    monkeypatch.setattr(REL, "load_district",
                        lambda s, did: {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                                        "labeled_topology": "per_school",
                                        "nces_denominator": {"total": 1, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: records)
    monkeypatch.setattr(REL, "district_fingerprints",
                        lambda s, did: {"config": "c", "labels": "l", "data": "d"})
    # #618: these tests pass session=None and monkeypatch every DB accessor; stub the guard's
    # provenance READ (not the guard itself) so assert_dispatch_type_allowed still runs for real.
    monkeypatch.setattr(BR, "benchmark_reps_in_package", lambda session, package: [])
    monkeypatch.setattr(BR.BM, "benchmark_provenance_rec_keys", lambda s, k: set())  # #679, same reason


def test_status_backup_exports_only_after_the_file_write_succeeds(tmp_path, monkeypatch):
    """Issue #39: dispatch_handoff used to export district_status.json from flushed-not-committed
    events BEFORE the handoff file write — a write failure rolled the DB back but left phantom
    `dispatched` events baked into the git-tracked backup. The export must run truly last."""
    _fake_release(monkeypatch)
    monkeypatch.setattr(BR, "record_dispatch", lambda *a, **k: None)
    exports = []
    monkeypatch.setattr(BR.DS, "export_status", lambda session, out=None: exports.append(1) or 0)

    # (a) the file write raises -> NO export happened
    orig_write = BR.HND.write

    def boom(doc, root=None):
        raise OSError("disk full")

    monkeypatch.setattr(BR.HND, "write", boom)
    with pytest.raises(OSError):
        BR.dispatch_handoff(session=None, district_ids=["0100810"], root=tmp_path)
    assert exports == []

    # (b) the file write succeeds -> exactly one export, after it
    monkeypatch.setattr(BR.HND, "write", orig_write)
    BR.dispatch_handoff(session=None, district_ids=["0100810"], root=tmp_path)
    assert exports == [1]
