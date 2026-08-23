"""Stage 4 (Process) batch runner — the console's orchestration half (REQ-111).

Unlike Stage 2/3 there is no external worker to fake: Stage 4 does the harvesting IN-PROCESS, so these
tests drive `run_batch` against real (tiny, text-only) on-disk captures — a usable .txt rep needs no
pdftotext/tesseract subprocess. The DB cache hook is monkeypatched to a no-op so the runner needs no
Postgres. Pure-Python unit tests of the orchestration: reconcile (filesystem-authoritative), per-district
sequential process + finish, event feed, and error isolation. The pure rollup helper is tested directly.
"""
import json

import pytest

from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage4_process import headless as H4
from infrastructure.acquisition.stage4_process import process_stage4 as C4


@pytest.fixture
def inmem_registry(monkeypatch):
    reg = {"schema_version": 2, "districts": {}, "_events": []}
    monkeypatch.setattr(DS, "load", lambda: reg)
    monkeypatch.setattr(DS, "save", lambda r, **kw: len(r.get("_events", [])))
    monkeypatch.setattr(DS, "export", lambda: 0)   # run-end export (issue #49) — no Postgres in tests
    # the cross-stage cache hook + the #168 abandon guard each open their own DB session — no-op both
    # so the runner needs no Postgres
    monkeypatch.setattr(C4.CI, "cache_processed_records", lambda *a, **k: None)  # #616 in-memory hook
    monkeypatch.setattr(H4.BG, "assert_runnable", lambda *a, **k: None)
    return reg


USABLE_TXT = "School begins at 8:20 AM and dismisses at 3:20 PM. " * 6  # > 120 printable chars


def _seed_district(root, did, name, *, records=None, processed=False):
    """A captured district dir (discovery.json + captures.json + the referenced capture files). Each
    record in `records` is (hash, ok, txt_or_None): a usable page.txt when txt is given."""
    d = root / f"{did}_{name.lower().replace(' ', '_')}"
    d.mkdir(parents=True)
    (d / "discovery.json").write_text(json.dumps(
        {"district_id": did, "name": name, "state": "AK", "domain": f"{did}.org", "schools": []}))
    caps = []
    for h, ok, txt in (records or [("h1", True, USABLE_TXT)]):
        rec = {"hash": h, "url": f"http://{did}.org/{h}", "ok": ok, "files": {}}
        if ok and txt is not None:
            rdir = d / "captures" / h
            rdir.mkdir(parents=True)
            (rdir / "page.txt").write_text(txt)
            rec["files"] = {"txt": "page.txt"}
        caps.append(rec)
    (d / "captures.json").write_text(json.dumps(caps))
    if processed:
        (d / "processed.json").write_text(json.dumps([]))
    return d


def _batch(*dids):
    return {"batch_id": "batch_00088",
            "districts": [{"district_id": d, "name": f"D{d}", "state": "AK"} for d in dids]}


class TestRunBatch:
    def test_processes_each_todo_district_and_finishes(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        for did in ("111", "222"):
            _seed_district(tmp_path, did, f"D{did}")
        events = []
        summary = H4.run_batch(_batch("111", "222"),
                               on_event=lambda k, p: events.append((k, p.get("district_id"))))
        assert summary["todo"] == 2
        assert {r["outcome"] for r in summary["results"]} == {"processed_all"}
        assert ("dispatched", "111") in events and ("completed", "222") in events
        # processed.json actually written (the Stage-5 input)
        assert (tmp_path / "111_d111" / "processed.json").exists()

    def test_partial_outcome(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        # one usable record + one ok record whose text is below the usable bar -> processed_partial
        _seed_district(tmp_path, "111", "D111",
                       records=[("h1", True, USABLE_TXT), ("h2", True, "short")])
        summary = H4.run_batch(_batch("111"))
        assert summary["results"][0]["outcome"] == "processed_partial"

    def test_no_usable_text_any_when_nothing_clears_the_bar(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111", records=[("h1", True, "short")])
        summary = H4.run_batch(_batch("111"))
        assert summary["results"][0]["outcome"] == "no_usable_text_any"

    def test_already_processed_is_skipped_not_redone(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111", processed=True)
        summary = H4.run_batch(_batch("111"))
        assert summary["todo"] == 0 and summary["skipped"] == 1

    def test_error_isolates_one_district(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        for did in ("111", "222"):
            _seed_district(tmp_path, did, f"D{did}")
        orig = C4.finish_district

        def boom(d, registry, batch_id=None):     # mirrors finish_district's #647 signature
            if d["district_id"] == "111":
                raise RuntimeError("boom")
            return orig(d, registry, batch_id)

        monkeypatch.setattr(C4, "finish_district", boom)
        summary = H4.run_batch(_batch("111", "222"))
        by_id = {r["district_id"]: r for r in summary["results"]}
        assert by_id["111"]["outcome"] == "error"
        assert by_id["222"]["outcome"] == "processed_all"

    def test_awaiting_capture_district_drops_out_of_todo(self, tmp_path, monkeypatch, inmem_registry):
        """A district with no captures.json (Stage 3 not done) is not Stage 4's concern yet — it never
        appears in find_batch_districts, so todo excludes it."""
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111")
        # 222: discovered but not captured (discovery.json + candidates.json, no captures.json)
        d2 = tmp_path / "222_d222"
        d2.mkdir(parents=True)
        (d2 / "discovery.json").write_text(json.dumps(
            {"district_id": "222", "name": "D222", "state": "AK", "schools": []}))
        (d2 / "candidates.json").write_text(json.dumps({"candidates": [{"url": "u"}]}))
        summary = H4.run_batch(_batch("111", "222"))
        assert summary["todo"] == 1
        assert {r["district_id"] for r in summary["results"]} == {"111"}


class TestConsistencyBlastRadius:
    """#78: a captures.json/disk mismatch quarantines ONE district (excluded, surfaced like
    `failed` with a distinct `inconsistent` outcome); registry-ahead-of-disk keeps the hard
    SystemExit; already-processed districts aren't consistency-gated retroactively."""

    def test_inconsistent_district_is_quarantined_not_run_halting(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111")
        d = _seed_district(tmp_path, "222", "D222")
        (d / "captures" / "h1" / "page.txt").unlink()   # manifest claims page.txt; disk disagrees
        events = []
        summary = H4.run_batch(_batch("111", "222"),
                               on_event=lambda k, p: events.append((k, p.get("district_id"))))
        by_id = {r["district_id"]: r for r in summary["results"]}
        assert by_id["222"]["outcome"] == "inconsistent"
        assert "page.txt" in by_id["222"]["error"]
        assert by_id["111"]["outcome"] == "processed_all"          # blast radius: one district
        assert ("failed", "222") in events                          # surfaced like a failed district
        assert not (tmp_path / "222_d222" / "processed.json").exists()

    def test_registry_ahead_of_disk_keeps_the_hard_stop(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        _seed_district(tmp_path, "111", "D111")   # captured, NOT processed on disk
        inmem_registry["districts"]["111"] = {"furthest_stage": 4}   # registry claims Stage 4+
        with pytest.raises(SystemExit):
            H4.run_batch(_batch("111"))

    def test_already_processed_district_is_not_consistency_gated(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
        d = _seed_district(tmp_path, "111", "D111", processed=True)
        (d / "captures" / "h1" / "page.txt").unlink()   # inconsistent, but Stage 4 already done
        summary = H4.run_batch(_batch("111"))
        assert summary["skipped"] == 1 and summary["results"] == []

    def test_finish_district_raises_district_scoped_error_not_systemexit(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(C4, "RAW_DIR", tmp_path)
        d = _seed_district(tmp_path, "111", "D111")
        (d / "captures" / "h1" / "page.txt").unlink()
        district = C4.find_districts(tmp_path)[0]
        with pytest.raises(C4.InconsistentCapturesError):
            C4.finish_district(district, inmem_registry)


def test_rollup_counts():
    districts = [
        {"status": "done", "outcome": "processed_all", "n_docs": 5, "n_usable": 5, "n_not_usable": 0},
        {"status": "done", "outcome": "processed_partial", "n_docs": 4, "n_usable": 3, "n_not_usable": 1},
        {"status": "done", "outcome": "no_usable_text_any", "n_docs": 2, "n_usable": 0, "n_not_usable": 2},
        {"status": "manual_flag_all", "outcome": "manual_flag_all", "n_docs": 0, "n_usable": 0, "n_not_usable": 0},
        {"status": "awaiting_capture", "outcome": None, "n_docs": 0, "n_usable": 0, "n_not_usable": 0},
        {"status": "awaiting_discovery", "outcome": None, "n_docs": 0, "n_usable": 0, "n_not_usable": 0},
        {"status": "failed", "outcome": "failed", "n_docs": 0, "n_usable": 0, "n_not_usable": 0},
        {"status": "todo", "outcome": None, "n_docs": 0, "n_usable": 0, "n_not_usable": 0},
    ]
    r = H4._rollup(districts)
    # resolved = processed (3, incl. no_usable_text_any) + flagged (1); failed is retriable, NOT resolved
    assert r == {"total": 8, "done": 3, "manual_flag_all": 1, "todo": 1, "failed": 1,
                 "awaiting_capture": 1, "awaiting_discovery": 1, "resolved": 4,
                 "processed_all": 1, "processed_partial": 1, "no_usable_text_any": 1,
                 "n_docs": 11, "n_usable": 8, "n_not_usable": 3}


class TestWinningSourcesTolerance:
    """#348 — one malformed texts[] entry must not 500 the batch status endpoint."""

    def test_non_dict_entries_are_skipped(self, tmp_path):
        import json as _json
        from infrastructure.acquisition.stage4_process import headless as H4
        (tmp_path / "processed.json").write_text(_json.dumps([
            {"texts": [None, "junk", {"source": "pdftotext", "usable": True},
                       {"usable": True}, {"source": "camelot_stream", "usable": False}]},
        ]))
        assert H4.winning_sources(tmp_path) == ["pdftotext"]


class TestDiskDocCount:
    """#347 — the freshness signal the self-heal compares against the cache row count."""

    def test_counts_records_and_zero_on_garbage(self, tmp_path):
        import json as _json
        from infrastructure.acquisition.stage4_process import headless as H4
        (tmp_path / "processed.json").write_text(_json.dumps([{}, {}, {}]))
        assert H4._disk_doc_count(tmp_path) == 3
        (tmp_path / "processed.json").write_text("{corrupt")
        assert H4._disk_doc_count(tmp_path) == 0
        assert H4._disk_doc_count(tmp_path / "missing") == 0


class TestWinningSourcesTopLevelTolerance:
    """Review completion of #348: a malformed TOP-LEVEL docs entry (null / non-dict) must be
    skipped like a malformed texts[] entry — either could 500 the status endpoint."""

    def test_top_level_null_and_string_entries_are_skipped(self, tmp_path):
        import json as _json
        from infrastructure.acquisition.stage4_process import headless as H4
        (tmp_path / "processed.json").write_text(_json.dumps(
            [None, "junk", {"texts": [{"source": "pdftotext", "usable": True}]}]))
        assert H4.winning_sources(tmp_path) == ["pdftotext"]
        assert H4._disk_doc_count(tmp_path) == 3   # count stays honest (raw record count)

    def test_non_list_top_level_reads_as_empty(self, tmp_path):
        from infrastructure.acquisition.stage4_process import headless as H4
        (tmp_path / "processed.json").write_text('{"not": "a list"}')
        assert H4.winning_sources(tmp_path) == []
        assert H4._disk_doc_count(tmp_path) == 0


# ------------------ #647: a redo batch's Stage-4 status is BATCH-scoped ------------------
@pytest.mark.govdb
def test_647_a_redo_batch_awaits_this_batchs_capture_before_processing(gov_session, monkeypatch, tmp_path):
    """The Stage-4 twin, plus the part that is NOT just a copy: `captured` is this stage's UPSTREAM
    GATE. Leaving it on disk state would tell a redo district it is ready to process while its
    re-capture has not happened — reading `todo` when the honest answer is `awaiting_capture`, and
    handing the operator a Run button that would process last round's artifacts."""
    import contextlib
    from sqlalchemy import text
    from infrastructure.acquisition.common import db as gdb
    from infrastructure.acquisition.common import district_status as DS
    from infrastructure.acquisition.stage4_process import headless as H4
    gdb.init_precious_schema()
    monkeypatch.setattr(DS.gdb, "session_scope", lambda: contextlib.nullcontext(gov_session))

    did = "ZZ647D"
    ddir = tmp_path / "ZZ647D_Redo"
    ddir.mkdir(parents=True)
    (ddir / "captures.json").write_text("[]")
    (ddir / "processed.json").write_text("[]")
    (ddir / "candidates.json").write_text('{"candidates": [{"url": "http://z/a"}]}')
    (ddir / "discovery.json").write_text(
        '{"district_id": "ZZ647D", "name": "Redo4", "state": "ZZ", "domain": "z.org"}')
    monkeypatch.setattr(H4, "RAW_DIR", tmp_path)
    monkeypatch.setattr(H4, "stage2_complete", lambda root: [
        {"district_id": did, "name": "Redo4", "state": "ZZ", "domain": "z.org", "dir": ddir}])

    batch = {"batch_id": "batch_zz647d", "batch_type": "follow-up", "redo_attempted": True,
             "districts": [{"district_id": did, "name": "Redo4", "state": "ZZ", "domain": "z.org"}]}

    # nothing dispatched by THIS batch: gated on its own capture, not "todo", not "done"
    assert H4.status_for_batch(batch)["districts"][0]["status"] == "awaiting_capture"

    # #671: this batch DISPATCHED the capture but has not finished it — the upstream gate is still
    # owed, so the honest answer stays `awaiting_capture`, not `todo`.
    gov_session.execute(text(
        "INSERT INTO state_event (district_id, stage_name, event_type, batch_id, created_at, actor) "
        "VALUES (:d, 'capture', 'dispatched', :b, 'now', 'zz')"), {"d": did, "b": "batch_zz647d"})
    gov_session.flush()
    assert H4.status_for_batch(batch)["districts"][0]["status"] == "awaiting_capture"

    # this batch CAPTURED it -> now genuinely todo for processing
    gov_session.execute(text(
        "INSERT INTO state_event (district_id, stage_name, event_type, stage, batch_id, "
        "created_at, actor) VALUES (:d, 'capture', 'captured_all', 3, :b, 'now', 'zz')"),
        {"d": did, "b": "batch_zz647d"})
    gov_session.flush()
    assert H4.status_for_batch(batch)["districts"][0]["status"] == "todo"

    # #671: dispatching the PROCESS does not finish it either — this is the exact state the 7 live
    # districts (batch_00024/26/27/29, dispatched 2026-07-22) have been stuck in, reading `done`
    # off a prior run's processed.json for over a month.
    gov_session.execute(text(
        "INSERT INTO state_event (district_id, stage_name, event_type, batch_id, created_at, actor) "
        "VALUES (:d, 'process', 'dispatched', :b, 'now', 'zz')"), {"d": did, "b": "batch_zz647d"})
    gov_session.flush()
    stuck = H4.status_for_batch(batch)["districts"][0]
    assert stuck["status"] == "todo"
    assert stuck["n_docs"] == 0               # not the prior run's doc counts

    # …and once a process OUTCOME lands, done
    gov_session.execute(text(
        "INSERT INTO state_event (district_id, stage_name, event_type, stage, batch_id, "
        "created_at, actor) VALUES (:d, 'process', 'processed_all', 4, :b, 'now', 'zz')"),
        {"d": did, "b": "batch_zz647d"})
    gov_session.flush()
    assert H4.status_for_batch(batch)["districts"][0]["status"] == "done"


def test_647_stage4_finish_district_stamps_the_batch(monkeypatch, tmp_path):
    """Every one of the 128 pre-existing stage=4 events carries batch_id NULL. This closes it."""
    from infrastructure.acquisition.stage4_process import process_stage4 as C4
    ddir = tmp_path / "ZZ647E_Stamp"
    ddir.mkdir(parents=True)
    seen = {}
    monkeypatch.setattr(C4, "check_file_consistency", lambda d: [])
    monkeypatch.setattr(C4, "process_district", lambda d: [])
    monkeypatch.setattr(C4, "write_processed", lambda d, r: None)
    monkeypatch.setattr(C4, "compute_outcome", lambda r: "processed_all")
    monkeypatch.setattr(C4.DS, "record_stage", lambda *a, **k: seen.update(k))
    monkeypatch.setattr(C4.CI, "cache_processed_records", lambda *a, **k: None)
    district = {"district_id": "ZZ647E", "name": "Stamp4", "state": "ZZ", "dir": ddir}

    C4.finish_district(district, {}, "batch_zz647e")
    assert seen["batch_id"] == "batch_zz647e" and seen["stage"] == 4
    seen.clear()
    C4.finish_district(district, {})            # CLI path, no batch — unchanged
    assert seen["batch_id"] is None
