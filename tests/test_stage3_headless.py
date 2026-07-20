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
        msg = str(ei.value)
        assert "corrupt captures.json" in msg
        # The suggested command must ACTUALLY PARSE against the real reconstruct subparser
        # (review: the first draft cited a nonexistent <batch.json> positional).
        cmd_tail = msg.split("capture_stage3 ", 1)[1].rstrip("`").split()
        assert cmd_tail == ["reconstruct", "D9"]


class TestRetryPartial:
    """#116 — partial retry: re-attempt ONLY the retryable failures (not_attempted/not_recovered)
    of a batch's already-captured districts; one-attempt errs (security_block, needs_oauth_reauth)
    carry verbatim, and districts with nothing retryable are never dispatched."""

    def _seed_partial(self, root, did, name, captures, cand_urls=None):
        """One writer per file: candidates.json is written exactly once (review fix — the earlier
        seed-then-overwrite made it ambiguous which plan a test actually exercised)."""
        d = _seed_district(root, did, name)
        if cand_urls is not None:
            (d / "candidates.json").write_text(
                json.dumps({"candidates": [{"url": u} for u in cand_urls]}))
        (d / "captures.json").write_text(json.dumps(captures))
        return d

    def test_only_districts_with_retryable_planned_failures_are_dispatched(
            self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        # 111: deadline-truncated -> retryable
        self._seed_partial(tmp_path, "111", "D111",
                           [{"hash": "a", "url": "http://111.org/a", "ok": False,
                             "err": "not_attempted (capture deadline reached)"}])
        # 222: only a one-attempt failure -> NOT dispatched
        self._seed_partial(tmp_path, "222", "D222",
                           [{"hash": "b", "url": "http://222.org/a", "ok": False,
                             "err": "security_block"}])
        # 333: fully captured -> NOT dispatched
        self._seed_partial(tmp_path, "333", "D333",
                           [{"hash": "c", "url": "http://333.org/a", "ok": True}])
        ran = []

        def run(cmd, **kw):
            ran.append(cmd)
            from pathlib import Path
            Path(cmd[3], cmd[4], "captures.json").write_text(
                json.dumps([{"hash": "a", "url": "http://111.org/a", "ok": True}]))
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        plan_sha = H3._plan_sha256(tmp_path / "111_d111")   # BEFORE the run overwrites captures
        summary = H3.retry_partial(_batch("111", "222", "333"), _run=run)
        assert summary["todo"] == 1
        assert [c[4] for c in ran] == ["111_d111"]
        assert "retryable-only" in ran[0]               # the Node run gets the #116 mode flag
        # review: the plan fingerprint rides along so Node can detect a concurrent Stage-2 rewrite
        assert ran[0][-1] == f"plan-sha256={plan_sha}"
        assert summary["results"][0]["outcome"] == "captured_all"   # honest re-resolve

    def test_retryable_failure_off_the_capture_plan_does_not_trigger(
            self, tmp_path, monkeypatch, inmem_registry):
        """An emergent record's retryable err can't retry via the delta re-run (its URL isn't
        planned), so it must not dispatch the district — #117's recovery territory."""
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        self._seed_partial(tmp_path, "111", "D111",
                           [{"hash": "a", "url": "http://elsewhere.org/emergent", "ok": False,
                             "source": "emergent",
                             "err": "not_attempted (capture deadline reached)"}])
        summary = H3.retry_partial(_batch("111"), _run=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not dispatch")))
        assert summary["todo"] == 0

    def test_uncaptured_district_is_not_touched_by_retry(self, tmp_path, monkeypatch, inmem_registry):
        """retry is for partials — a district with no captures.json belongs to `run`, not `retry`."""
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111")   # discovered, never captured
        summary = H3.retry_partial(_batch("111"), _run=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not dispatch")))
        assert summary["todo"] == 0

    def test_plan_sha_matches_the_node_side_pin(self, tmp_path):
        """Cross-language parity (#116 review): _plan_sha256 must equal mjs planSha256 for the
        same plan — the same literal is pinned in capture_records.test.mjs. Fragment-stripped,
        sorted, deduped."""
        d = tmp_path / "x"
        d.mkdir()
        (d / "candidates.json").write_text(json.dumps({"candidates": [
            {"url": "https://x.org/a"}, {"url": "https://x.org/b"}, {"url": "https://x.org/b#other"}]}))
        assert H3._plan_sha256(d) == \
            "048ef948ceafd914c4c1fbbb1ca2f55820564573dfa5a5e2a19fe3914e216cef"

    def test_unreadable_manifest_is_loud_not_nothing_to_retry(
            self, tmp_path, monkeypatch, inmem_registry):
        """Review (#267 convention): a corrupt/mis-shaped manifest must NEVER silently read as
        'nothing retryable' — the district is reported `unreadable` (summary + event stream),
        skipped, and the rest of the batch proceeds."""
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        d = self._seed_partial(tmp_path, "111", "D111",
                               [{"hash": "a", "url": "http://111.org/a", "ok": False,
                                 "err": "not_attempted (capture deadline reached)"}])
        # top-level list where a dict is expected -> AttributeError inside _retryable_failures
        (d / "candidates.json").write_text(json.dumps([{"url": "http://111.org/a"}]))
        events = []
        summary = H3.retry_partial(_batch("111"), on_event=lambda k, p: events.append((k, p)),
                                   _run=lambda *a, **k: (_ for _ in ()).throw(
                                       AssertionError("must not dispatch")))
        assert summary["todo"] == 0
        assert summary["unreadable"][0]["district_id"] == "111"
        assert "AttributeError" in summary["unreadable"][0]["error"]
        kinds = [k for k, _ in events]
        assert "retry_unreadable" in kinds
        reconciled = next(p for k, p in events if k == "retry_reconciled")
        assert reconciled["unreadable"] == ["111"]

    def test_fragment_variants_still_match_the_plan(self, tmp_path, monkeypatch, inmem_registry):
        """URL matching uses _strip_fragment parity — a candidates.json URL with a #fragment must
        still match the manifest record Node stored fragment-stripped."""
        monkeypatch.setattr(C3, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H3, "RAW_DIR", tmp_path)
        self._seed_partial(tmp_path, "111", "D111",
                           [{"hash": "a", "url": "http://111.org/a", "ok": False,
                             "err": "not_recovered (capture interrupted before completion)"}],
                           cand_urls=["http://111.org/a#top"])
        assert H3._retryable_failures(tmp_path / "111_d111") == 1
