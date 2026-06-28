"""Stage 3 (Capture) batch runner — the console's orchestration half (REQ-110).

The Node Playwright capture is replaced by a fake `_run` that writes a captures.json (so no browser,
no subprocess), and the DB cache hook is monkeypatched to a no-op, so these are pure-Python unit tests
of the orchestration: reconcile (filesystem-authoritative), per-district sequential capture + finish,
event feed, and error isolation. The pure rollup helper is tested directly.
"""
import json
import types

import pytest

from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage3_capture import capture_stage3 as C3
from infrastructure.acquisition.stage3_capture import headless as H3


@pytest.fixture
def inmem_registry(monkeypatch):
    reg = {"schema_version": 2, "districts": {}, "_events": []}
    monkeypatch.setattr(DS, "load", lambda: reg)
    monkeypatch.setattr(DS, "save", lambda r: len(r.get("_events", [])))
    # the cross-stage cache hook opens its own DB session — no-op it so the runner needs no Postgres
    monkeypatch.setattr(C3.CI, "cache_capture", lambda *a, **k: None)
    return reg


def _seed_district(root, did, name, *, captured=False):
    """Create a discovered (discovery.json + candidates.json) district dir under root. C3.find_districts
    reads the fields from discovery.json and uses the actual dir path, so the dir basename is arbitrary —
    it just has to match what the fake `_run` keys its records by (district['dir'].name)."""
    d = root / f"{did}_{name.lower().replace(' ', '_')}"
    d.mkdir(parents=True)
    (d / "discovery.json").write_text(json.dumps(
        {"district_id": did, "name": name, "state": "AK", "domain": f"{did}.org", "schools": []}))
    (d / "candidates.json").write_text(json.dumps({"candidates": [{"url": f"http://{did}.org/a"}]}))
    if captured:
        (d / "captures.json").write_text(json.dumps([{"hash": "h1", "url": "u", "ok": True}]))
    return d


def _fake_run(records_by_dir):
    """A fake subprocess.run: writes the district's captures.json (what the Node capture would do)."""
    def run(cmd, **kw):
        root, dir_name = cmd[3], cmd[4]
        from pathlib import Path
        Path(root, dir_name, "captures.json").write_text(json.dumps(records_by_dir.get(dir_name, [])))
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
    return run


def _batch(*dids):
    return {"batch_id": "batch_00077",
            "districts": [{"district_id": d, "name": f"D{d}", "state": "AK"} for d in dids]}


class TestRunBatch:
    def test_captures_each_todo_district_and_finishes(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        for did in ("111", "222"):
            _seed_district(tmp_path, did, f"D{did}")
        records = {f"111_d111": [{"hash": "a", "url": "u", "ok": True}],
                   f"222_d222": [{"hash": "b", "url": "u", "ok": True}]}
        events = []
        summary = H3.run_batch(_batch("111", "222"), _run=_fake_run(records),
                               on_event=lambda k, p: events.append((k, p.get("district_id"))))
        assert summary["todo"] == 2
        assert {r["outcome"] for r in summary["results"]} == {"captured_all"}
        assert ("dispatched", "111") in events and ("completed", "222") in events

    def test_partial_and_failed_outcomes(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111")
        records = {"111_d111": [{"hash": "a", "ok": True}, {"hash": "b", "ok": False, "err": "timeout"}]}
        summary = H3.run_batch(_batch("111"), _run=_fake_run(records))
        assert summary["results"][0]["outcome"] == "captured_partial"

    def test_already_captured_is_skipped_not_redone(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111", captured=True)
        ran = []
        summary = H3.run_batch(_batch("111"), _run=lambda *a, **k: ran.append(a) or types.SimpleNamespace(returncode=0, stdout="", stderr=""))
        assert summary["todo"] == 0 and summary["skipped"] == 1 and ran == []

    def test_node_failure_isolates_one_district(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        for did in ("111", "222"):
            _seed_district(tmp_path, did, f"D{did}")

        def run(cmd, **kw):
            root, dir_name = cmd[3], cmd[4]
            if dir_name == "111_d111":
                return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
            from pathlib import Path
            Path(root, dir_name, "captures.json").write_text(json.dumps([{"hash": "b", "ok": True}]))
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        summary = H3.run_batch(_batch("111", "222"), _run=run)
        by_id = {r["district_id"]: r for r in summary["results"]}
        assert by_id["111"]["outcome"] == "error"
        assert by_id["222"]["outcome"] == "captured_all"


def test_rollup_counts():
    districts = [
        {"status": "done", "outcome": "captured_all", "n_captures": 5, "n_failed": 0, "n_emergent": 1},
        {"status": "done", "outcome": "captured_partial", "n_captures": 3, "n_failed": 1, "n_emergent": 0},
        {"status": "todo", "outcome": None, "n_captures": 0, "n_failed": 0, "n_emergent": 0},
        {"status": "awaiting_discovery", "outcome": None, "n_captures": 0, "n_failed": 0, "n_emergent": 0},
    ]
    r = H3._rollup(districts)
    assert r == {"total": 4, "done": 2, "todo": 1, "awaiting_discovery": 1, "captured_all": 1,
                 "captured_partial": 1, "capture_failed_all": 0, "n_captures": 8, "n_failed": 1, "n_emergent": 1}
