"""Tests for the REQ-164 Phase 4 receipt backfill (infrastructure/acquisition/maintenance/backfill_receipts.py).

The behavioral guarantees (timestamp source chain, _benchmark tagging, idempotency, dry-run,
captures-untouched) run DB-free by injecting benchmark_ids + status_doc. Two govdb tests cover the real
SQL (state_event timestamp source + batch_type='benchmark' detection).
"""
import json
import re

import pytest

from infrastructure.acquisition.common import paths, receipts
from infrastructure.acquisition.common import timeutil as TU
from infrastructure.acquisition.maintenance import backfill_receipts as BF

DID = "3501110"
NAME = "GALLUP"


@pytest.fixture
def cap_root(tmp_path, monkeypatch):
    """RAW_CAPTURES -> tmp so nothing touches the real tree (mirrors test_receipts.cap_root)."""
    monkeypatch.setattr(paths, "RAW_CAPTURES", tmp_path)
    return tmp_path


def _ddir(root):
    d = root / f"{DID}_gallup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _status(stage, at):
    return {"districts": {DID: {"history": [{"stage": stage, "stage_name": "process",
                                             "outcome": "processed_all", "at": at}]}}}


# ----------------------------- timeutil conversion helpers -----------------------------
def test_fs_stamp_from_iso_converts_and_tolerates_offset():
    assert TU.fs_stamp_from_iso("2026-07-22T15:55:40Z") == "20260722T155540Z"
    assert TU.fs_stamp_from_iso("2026-07-22T15:55:40+00:00") == "20260722T155540Z"


def test_fs_stamp_from_iso_raises_on_garbage_so_caller_can_fall_through():
    with pytest.raises(ValueError):
        TU.fs_stamp_from_iso("not-a-timestamp")


def test_fs_stamp_from_epoch():
    # 2026-07-22T15:55:40Z == 1784735740 epoch seconds (UTC)
    assert TU.fs_stamp_from_epoch(1784735740) == "20260722T155540Z"


# ----------------------------- timestamp sourcing (DB-free) -----------------------------
def test_filtered_backfill_uses_state_event_via_status_fallback(cap_root):
    """A filtered.json with a matching stage-5 twin history entry is renamed to the exact fs_stamp
    derived from that ISO timestamp (state_event's offline equivalent)."""
    d = _ddir(cap_root)
    (d / "filtered.json").write_text(json.dumps({"winner": "u"}))
    plans = BF.run(cap_root, benchmark_ids=set(), status_doc=_status(5, "2026-07-22T15:55:40Z"))
    assert len(plans) == 1 and plans[0].source == "district_status"
    assert not (d / "filtered.json").exists()
    got = receipts.latest_receipt(DID, NAME, "filtered")
    assert got is not None
    assert re.match(r"^filtered\.20260722T155540Z\.py-[0-9a-f]{8}\.json$", got.name), got.name


def test_orphan_falls_back_to_mtime_and_warns(cap_root, capsys):
    d = _ddir(cap_root)
    (d / "filtered.json").write_text(json.dumps({"winner": "u"}))
    plans = BF.run(cap_root, benchmark_ids=set(), status_doc={})   # no twin entry -> mtime
    assert len(plans) == 1 and plans[0].source == "mtime"
    out = capsys.readouterr().out
    assert "[warn]" in out and "st_mtime" in out
    assert receipts.latest_receipt(DID, NAME, "filtered") is not None


# ----------------------------- benchmark tagging (DB-free) -----------------------------
def test_benchmark_dir_gets_benchmark_suffix_invisible_to_production_resolver(cap_root):
    d = _ddir(cap_root)
    (d / "filtered.json").write_text(json.dumps({"winner": "u"}))
    BF.run(cap_root, benchmark_ids={DID}, status_doc=_status(5, "2026-07-22T15:55:40Z"))
    # tagged basename, and the production resolver must NOT see it (the .-anchored glob)
    assert receipts.latest_receipt(DID, NAME, "filtered") is None
    tagged = receipts.latest_receipt(DID, NAME, "filtered_benchmark")
    assert tagged is not None and tagged.name.startswith("filtered_benchmark.")


# ----------------------------- scope + idempotency + dry-run (DB-free) -----------------------------
def test_deferred_and_node_artifacts_untouched(cap_root):
    """processed/discovery/candidates are still done-markers read by fixed name (deferred conversion),
    and captures.json is a Node handoff — the backfill must leave all four alone (filtered-only scope)."""
    d = _ddir(cap_root)
    for fixed in ("captures.json", "discovery.json", "candidates.json", "processed.json"):
        (d / fixed).write_text(json.dumps([{"hash": "a"}]))
    plans = BF.run(cap_root, benchmark_ids=set(), status_doc={})
    assert plans == []
    for fixed in ("captures.json", "discovery.json", "candidates.json", "processed.json"):
        assert (d / fixed).exists()


def test_idempotent_rerun_is_a_noop(cap_root):
    d = _ddir(cap_root)
    (d / "filtered.json").write_text(json.dumps({"winner": "u"}))
    assert len(BF.run(cap_root, benchmark_ids=set(), status_doc=_status(5, "2026-07-22T15:55:40Z"))) == 1
    assert BF.run(cap_root, benchmark_ids=set(), status_doc=_status(5, "2026-07-22T15:55:40Z")) == []


def test_dry_run_mutates_nothing(cap_root):
    d = _ddir(cap_root)
    (d / "filtered.json").write_text(json.dumps({"winner": "u"}))
    plans = BF.run(cap_root, dry_run=True, benchmark_ids=set(),
                   status_doc=_status(5, "2026-07-22T15:55:40Z"))
    assert len(plans) == 1
    assert (d / "filtered.json").exists()                # still there
    assert receipts.latest_receipt(DID, NAME, "filtered") is None


# ----------------------------- real SQL (govdb) -----------------------------
@pytest.mark.govdb
def test_state_event_timestamp_source(gov_session):
    """_stamp_from_state_event runs the real query and converts created_at to fs_stamp form."""
    from infrastructure.acquisition.common import db as gdb
    gdb.init_precious_schema()
    gov_session.execute(__import__("sqlalchemy").text(
        "INSERT INTO state_event (district_id, stage, event_type, created_at) "
        "VALUES (:d, 4, 'processed_all', '2026-07-22T15:55:40Z')"), {"d": "TSTBF01"})
    gov_session.flush()
    assert BF._stamp_from_state_event(gov_session, "TSTBF01", 4) == "20260722T155540Z"
    assert BF._stamp_from_state_event(gov_session, "TSTBF01", 5) is None
    gov_session.rollback()


@pytest.mark.govdb
def test_load_benchmark_ids_keys_on_batch_type(gov_session):
    """Real batch_type='benchmark' JOIN — a benchmark member is returned, a first-run member is not."""
    from infrastructure.acquisition.common import db as gdb
    from infrastructure.acquisition.stage1_queue import models as M
    gdb.init_precious_schema()
    for bid, btype in (("batch_bmk", "benchmark"), ("batch_reg", "first-run")):
        gov_session.add(M.Batch(batch_id=bid, batch_type=btype, status="approved",
                                nces_year="2024-25", created_by="test"))
    gov_session.add(M.BatchDistrict(batch_id="batch_bmk", district_id="TSTBFBM", name="BM", state="ZZ"))
    gov_session.add(M.BatchDistrict(batch_id="batch_reg", district_id="TSTBFRG", name="RG", state="ZZ"))
    gov_session.flush()
    ids = BF.load_benchmark_ids(gov_session)
    assert "TSTBFBM" in ids and "TSTBFRG" not in ids
    gov_session.rollback()
