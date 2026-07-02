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


def test_dispatch_handoff_is_immutable_on_repeat(tmp_path, monkeypatch):
    monkeypatch.setattr(REL, "load_district", lambda s, did: None)          # no districts -> empty package
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: [])
    monkeypatch.setattr(REL, "district_fingerprints", lambda s, did: {})
    monkeypatch.setattr(BR, "record_dispatch", lambda *a, **k: None)
    # freeze the clock so both calls produce the same filename, proving write() refuses to overwrite
    monkeypatch.setattr("infrastructure.acquisition.stage6_handoff.handoff._now", lambda: "2026-06-30T00:00:00Z")
    BR.dispatch_handoff(session=None, district_ids=[], root=tmp_path)
    with pytest.raises(FileExistsError):
        BR.dispatch_handoff(session=None, district_ids=[], root=tmp_path)


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
