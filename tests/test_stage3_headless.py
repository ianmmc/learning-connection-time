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
    monkeypatch.setattr(DS, "save", lambda r, **kw: len(r.get("_events", [])))
    monkeypatch.setattr(DS, "export", lambda: 0)   # run-end export (issue #49) — no Postgres in tests
    # the cross-stage cache hook + the #168 abandon guard each open their own DB session — no-op both
    # so the runner needs no Postgres
    monkeypatch.setattr(C3.CI, "cache_capture", lambda *a, **k: None)
    monkeypatch.setattr(H3.BG, "assert_runnable", lambda *a, **k: None)
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
        {"status": "manual_flag_all", "outcome": "manual_flag_all", "n_captures": 0, "n_failed": 0, "n_emergent": 0},
        {"status": "failed", "outcome": "failed", "n_captures": 0, "n_failed": 0, "n_emergent": 0},
        {"status": "timed_out", "outcome": "timed_out", "n_captures": 0, "n_failed": 0, "n_emergent": 0},
        {"status": "todo", "outcome": None, "n_captures": 0, "n_failed": 0, "n_emergent": 0},
        {"status": "awaiting_discovery", "outcome": None, "n_captures": 0, "n_failed": 0, "n_emergent": 0},
    ]
    r = H3._rollup(districts)
    # resolved = captured (2) + flagged (1); failed + timed_out are retriable, NOT resolved/todo
    assert r == {"total": 7, "done": 2, "manual_flag_all": 1, "todo": 1, "failed": 2,
                 "awaiting_discovery": 1, "resolved": 3, "captured_all": 1, "captured_partial": 1,
                 "capture_failed_all": 0, "n_captures": 8, "n_failed": 1, "n_emergent": 1}


def test_no_link_districts_are_skipped_before_playwright(tmp_path, monkeypatch, inmem_registry):
    """A district whose candidates.json is empty (Stage 2 manual_flag_all) must NOT be dispatched to
    the Node capture — we know it has no links before sending it in. It gets no Stage-3 artifact/event."""
    monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
    monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
    _seed_district(tmp_path, "111", "D111")
    d2 = _seed_district(tmp_path, "222", "D222")
    (d2 / "candidates.json").write_text(json.dumps({"candidates": []}))   # no-link district
    ran = []

    def run(cmd, **kw):
        ran.append(cmd[4])   # the district dir the Node capture was invoked on
        from pathlib import Path
        Path(cmd[3], cmd[4], "captures.json").write_text(json.dumps([{"hash": "a", "ok": True}]))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    summary = H3.run_batch(_batch("111", "222"), _run=run)
    assert summary["todo"] == 1 and summary["no_links"] == 1
    assert ran == ["111_d111"]                        # only the with-links district hit Playwright
    assert not (d2 / "captures.json").exists()         # no Stage-3 artifact for the no-link district


class TestCorruptManifestMessage:
    """#267 — a truncated captures.json (crash mid-write) must fail finish_district with the
    delete-then-reconstruct recovery spelled out, not a bare JSONDecodeError (the silent-wedge
    state: reconcile skips forever, reconstruct refuses)."""

    def test_finish_district_names_the_recovery_path(self, tmp_path):
        (tmp_path / "captures.json").write_text('[{"url": "u", "ok": tru')   # truncated
        district = {"dir": tmp_path, "district_id": "D9", "name": "N", "state": "AK"}
        with pytest.raises(RuntimeError) as ei:
            C3.finish_district(district, registry={"districts": {}})
        assert "corrupt captures.json" in str(ei.value) and "reconstruct" in str(ei.value)
