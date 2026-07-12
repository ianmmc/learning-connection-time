"""gate@7 console API (REQ-117) — HTTP wiring, DB-free (fake session_scope + fake connection).
The heavy logic (detection/persistence/dedup) is unit-tested in test_stage7_requests / _persist."""
import contextlib

from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server as SRV

client = TestClient(SRV.app)


class _Result:
    def __init__(self, rows=None, rowcount=1, scalar=None):
        self._rows = [dict(r) for r in (rows or [])]
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar(self):
        return self._scalar

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        # direct iteration (e.g. _defer_76_districts's `{r[0] for r in rows}`) — tuple-ish rows
        return iter([tuple(r.values()) for r in self._rows])


class _Con:
    """Returns queued results in call order (one per execute)."""
    def __init__(self, results):
        self._results, self._i = results, 0

    def execute(self, *a, **k):
        r = self._results[self._i] if self._i < len(self._results) else _Result()
        self._i += 1
        return r

    def commit(self):
        pass

    def begin_nested(self):
        # the #211 demote-hook runs inside a SAVEPOINT (PR #248 review) — mock it as a no-op context
        # so hook queries still consume from the queue instead of dying on a missing attribute.
        return contextlib.nullcontext()


def _use(monkeypatch, con):
    @contextlib.contextmanager
    def _scope():
        yield con
    monkeypatch.setattr(SRV.gdb, "session_scope", _scope)


# ------------------------------- districts list -------------------------------
def test_districts_returns_rows(monkeypatch):
    _use(monkeypatch, _Con([_Result(rows=[
        {"district_id": "D1", "name": "One", "state": "AL", "handoff_hash": "h",
         "n_accepted": 5, "n_unresolved": 2, "cost_usd": 0.003, "n_reps": 4,
         "created_at": "t", "n_pending": 1, "n_requests": 2}])]))
    r = client.get("/api/extract/districts")
    assert r.status_code == 200
    assert r.json()[0]["district_id"] == "D1" and r.json()[0]["n_pending"] == 1


# ------------------------------- district detail -------------------------------
def test_district_detail_shape(monkeypatch):
    ext = _Result(rows=[{"extraction_id": 1, "handoff_hash": "h", "created_at": "t",
                         "created_by": "x", "cost_usd": 0.003, "n_accepted": 1,
                         "n_unresolved": 1, "n_reps": 1}])
    facts = _Result(rows=[
        {"extraction_id": 1, "handoff_hash": "h", "band": "elementary", "school": "a",
         "status": "accepted", "start_time": "08:00",
         "end_time": "14:00", "gross_minutes": 360, "method": "council_agree",
         "models_json": '["m1"]', "detail_json": None, "rec_key": "D1:aa", "source_file": "f"},
        {"extraction_id": 1, "handoff_hash": "h", "band": "high", "school": "b",
         "status": "unresolved", "start_time": None, "end_time": None,
         "gross_minutes": None, "method": "disagree", "models_json": None,
         "detail_json": '{"starts": {}}', "rec_key": "D1:bb", "source_file": "f"}])
    reqs = _Result(rows=[{"request_id": 9, "altitude": "district", "route": "7->2", "target": "D1",
                          "band": "high", "params_json": "{}", "reason": "gap", "status": "pending",
                          "reviewed_by": None, "reviewed_at": None, "review_note": None, "created_at": "t"}])
    meta = _Result(rows=[{"nces": 5, "sbb": None}])            # #237 detector inputs (multi-school LEA)
    _use(monkeypatch, _Con([ext, facts, meta, reqs]))
    body = client.get("/api/extract/district/D1").json()
    assert body["bands"]["elementary"]["gross_minutes"] == 360
    assert len(body["accepted"]) == 1 and len(body["unresolved"]) == 1
    assert body["requests"][0]["route"] == "7->2"
    assert body["contamination"] is None                       # not a single-school LEA -> no flag


def test_district_detail_is_cumulative_a_barren_retry_does_not_regress_the_view(monkeypatch):
    # REQ-122 / #232 (the Brownsville case): the header row is the LATEST run (a scoped 7->6 retry
    # that accepted nothing), but accepted/bands must still show run 1's solid facts — the facts
    # query spans ALL production runs and merge_fact_runs keeps the accepted winner per school.
    ext = _Result(rows=[{"extraction_id": 2, "handoff_hash": "h2", "created_at": "t2",
                         "created_by": "x", "cost_usd": 0.001, "n_accepted": 0,
                         "n_unresolved": 0, "n_reps": 1}])           # latest run: 0 accepted
    facts = _Result(rows=[                                           # cross-run query result
        {"extraction_id": 1, "handoff_hash": "h1", "band": "elementary", "school": "a",
         "status": "accepted", "start_time": "08:00", "end_time": "14:00", "gross_minutes": 360,
         "method": "council_agree", "models_json": '["m1"]', "detail_json": None,
         "rec_key": "D1:aa", "source_file": "f"},
        {"extraction_id": 2, "handoff_hash": "h2", "band": "elementary", "school": "a",
         "status": "unresolved", "start_time": None, "end_time": None, "gross_minutes": None,
         "method": "disagree", "models_json": None, "detail_json": None,
         "rec_key": "D1:aa", "source_file": "f"}])                   # the retry's barren echo
    _use(monkeypatch, _Con([ext, facts, _Result()]))
    body = client.get("/api/extract/district/D1").json()
    assert body["extraction"]["extraction_id"] == 2                  # header = latest run
    # the header's counts are overridden with the CUMULATIVE truth — the payload must never ship
    # a latest-run-only n_accepted (0 here) beside a non-empty accepted[] (REQ-122 one field deeper)
    assert body["extraction"]["n_accepted"] == len(body["accepted"]) == 1
    assert body["extraction"]["n_unresolved"] == len(body["unresolved"]) == 0
    assert len(body["accepted"]) == 1                                # run 1's fact survives
    assert body["accepted"][0]["extraction_id"] == 1                 # with its provenance
    assert body["unresolved"] == []                                  # accepted beats the retry echo
    assert body["bands"]["elementary"]["gross_minutes"] == 360       # rollup over the merge


def test_district_detail_404_when_no_extraction(monkeypatch):
    _use(monkeypatch, _Con([_Result(rows=[])]))   # ext query returns nothing
    assert client.get("/api/extract/district/ZZ").status_code == 404


# ------------------------------- request review (the mutation) -------------------------------
def test_review_approve_updates(monkeypatch):
    # the UPDATE now RETURNs the row's identity (#218: feeds the gate@7 calibration hook — the
    # follow-on extraction/district lookups + calibration INSERT drain the mock's empty defaults)
    _use(monkeypatch, _Con([_Result(rows=[{"district_id": "D1", "band": "high", "handoff_hash": "h"}])]))
    r = client.post("/api/extract/request/9", json={"status": "approved", "actor": "ian", "note": "go"})
    assert r.status_code == 200 and r.json() == {"request_id": 9, "status": "approved"}


def test_review_rejects_bad_status(monkeypatch):
    _use(monkeypatch, _Con([]))
    assert client.post("/api/extract/request/9", json={"status": "banana"}).status_code == 400


def test_review_404_when_no_such_request(monkeypatch):
    # rowcount=0 -> the endpoint disambiguates via a status SELECT; no row -> 404
    _use(monkeypatch, _Con([_Result(rowcount=0), _Result(scalar=None)]))
    assert client.post("/api/extract/request/999", json={"status": "rejected"}).status_code == 404


def test_review_executed_is_terminal_409(monkeypatch):
    """#135: an 'executed' directive must never be reopened/re-approved — the depth guard counts
    rows whose CURRENT status is executed, so a reopen would decrement the safety counter and allow
    unlimited paid re-fires. rowcount=0 + current status 'executed' -> 409, not a silent flip."""
    _use(monkeypatch, _Con([_Result(rowcount=0), _Result(scalar="executed")]))
    r = client.post("/api/extract/request/7", json={"status": "pending"})
    assert r.status_code == 409 and "terminal" in r.json()["detail"]


# ------------------------------- execution endpoints (REQ-118) -------------------------------
def test_compose_followup_endpoint(monkeypatch):
    captured = {}
    def _fake(**kw):
        captured.update(kw)
        return {"batch_id": "batch_00042", "n_requests": 3, "n_districts": 2,
                "targets": {"D1": ["high"], "D2": ["middle"]}, "spilled": [], "blocked": [], "skipped": []}
    monkeypatch.setattr(SRV.EX, "compose_followup_batch", _fake)
    r = client.post("/api/extract/compose-followup", json={"handoff_hash": "h", "actor": "zz", "cap": 5})
    assert r.status_code == 200
    assert r.json()["batch_id"] == "batch_00042" and r.json()["n_requests"] == 3
    assert captured["handoff_hash"] == "h" and captured["actor"] == "zz" and captured["cap"] == 5


def test_execute_endpoint_success(monkeypatch):
    monkeypatch.setattr(SRV.EX, "execute_alternate_dispatch",
                        lambda rid, **kw: {"ok": True, "handoff_hash": "NEW", "path": "/x",
                                           "alt_file": "raster_p-1.png", "council": {"k": "image"}})
    r = client.post("/api/extract/execute/7", json={"actor": "zz"})
    assert r.status_code == 200 and r.json()["handoff_hash"] == "NEW"


def test_execute_endpoint_refused_is_409(monkeypatch):
    monkeypatch.setattr(SRV.EX, "execute_alternate_dispatch",
                        lambda rid, **kw: {"ok": False, "blocked": True, "reason": "depth guard: max rounds"})
    r = client.post("/api/extract/execute/7", json={})
    assert r.status_code == 409 and "depth guard" in r.json()["detail"]


# ------------------------------- #235: Stage 4->5 ingest hand-off -------------------------------
def test_ingest_failure_is_recorded_durably_per_district(monkeypatch):
    """#235: a failed Stage-5 ingest used to leave only an in-memory job event + stdout — district
    history showed a clean stage-4 finish then silence, indistinguishable from 'nothing new
    surfaced'. The failure must land in the durable district_status registry."""
    batch = {"batch_id": "batch_zz", "districts": [
        {"district_id": "D1", "name": "A", "state": "IA"},
        {"district_id": "D2", "name": "B", "state": "IA"}]}
    monkeypatch.setattr(SRV.H4, "status_for_batch",
                        lambda b: {"rollup": {"resolved": 2, "total": 2}})
    monkeypatch.setattr(SRV.BS, "ingest_batch",
                        lambda ids: (_ for _ in ()).throw(RuntimeError("boom")))
    recorded = []
    monkeypatch.setattr(SRV.DS, "load", lambda: {"reg": True})
    monkeypatch.setattr(SRV.DS, "record_stage",
                        lambda reg, did, name, state, **kw: recorded.append((did, kw)))
    saved = []
    monkeypatch.setattr(SRV.DS, "save", lambda reg: saved.append(reg))
    events = []
    SRV._ingest_stage5_if_complete(batch, lambda name, payload: events.append(name))
    assert events == ["stage5_ingest_failed"]
    assert [d for d, _ in recorded] == ["D1", "D2"]
    assert all(kw["outcome"] == "ingest_failed" and kw["stage"] == 5 for _, kw in recorded)
    assert saved, "the registry write must actually be flushed to disk"


def test_stage4_and_ingest_are_one_operation_at_every_call_site():
    """#235 root cause: autoflow was a second H4.run_batch call site that forgot the ingest the
    first one remembered. The invariant now lives in ONE helper (run_stage4_with_ingest) — guard
    that (a) the helper really chains run_batch -> ingest, and (b) NO call site anywhere in the
    server invokes H4.run_batch directly anymore."""
    import inspect
    helper = inspect.getsource(SRV.run_stage4_with_ingest)
    assert "H4.run_batch" in helper and "_ingest_stage5_if_complete" in helper
    rest = inspect.getsource(SRV).replace(helper, "")
    assert "H4.run_batch" not in rest, \
        "a call site bypasses run_stage4_with_ingest — that's how #235 happened the first time"


def test_bookkeeping_failure_is_not_mislabeled_as_ingest_failure(monkeypatch):
    """#240 review: BS.ingest_batch succeeding but the registry bookkeeping throwing must NOT
    durably mark districts ingest_failed — the Stage-5 data is genuinely committed."""
    batch = {"batch_id": "batch_zz3", "districts": [{"district_id": "D1", "name": "A", "state": "IA"}]}
    monkeypatch.setattr(SRV.H4, "status_for_batch",
                        lambda b: {"rollup": {"resolved": 1, "total": 1}})
    monkeypatch.setattr(SRV.BS, "ingest_batch",
                        lambda ids: {"districts": ["D1"], "n_districts": 1, "n_records": 3, "n_send": 1})
    monkeypatch.setattr(SRV.DS, "load",
                        lambda: (_ for _ in ()).throw(RuntimeError("registry unreadable")))
    events = []
    SRV._ingest_stage5_if_complete(batch, lambda name, payload: events.append(name))
    assert events == ["stage5_bookkeeping_failed"]   # NOT stage5_ingest_failed


def test_ingest_deferral_is_surfaced_not_silent(monkeypatch):
    """#235 review: rollup-incomplete used to return with NO event — in autoflow (which terminates
    at gate@5) that silence is the same 'nothing new surfaced' failure the fix targets."""
    batch = {"batch_id": "batch_zz2", "districts": [{"district_id": "D1", "name": "A", "state": "IA"}]}
    monkeypatch.setattr(SRV.H4, "status_for_batch",
                        lambda b: {"rollup": {"resolved": 0, "total": 1}})
    events = []
    SRV._ingest_stage5_if_complete(batch, lambda name, payload: events.append((name, payload)))
    assert [n for n, _ in events] == ["stage5_ingest_deferred"]
    assert events[0][1]["resolved"] == 0 and events[0][1]["total"] == 1


def test_gate7_console_knows_the_withdrawn_status():
    """#233 review + the UI-visibility rule: an auto-withdrawn request must not render as a
    'pending' badge (the card would claim pending while its footer says withdrawn-by-auto)."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent   # the test_arch_manifest.py convention (cwd-proof)
    js = (repo / "infrastructure/acquisition/process_governance/static/stage7.js").read_text()
    assert 'r.status === "withdrawn"' in js, "requestCard must badge the withdrawn status explicitly"


def test_reopening_a_withdrawn_request_reruns_the_premise_check(monkeypatch):
    """#240 review: a Reopen (status->pending) must re-run the #233 premise check — if the gap is
    still satisfied the row re-withdraws immediately with a fresh note (no silent resurrection of
    already-done work); if the gap genuinely re-opened, it stays pending."""
    _use(monkeypatch, _Con([_Result(rows=[{"district_id": "D1", "band": None, "handoff_hash": "h"}])]))
    monkeypatch.setattr(SRV.R7, "withdraw_satisfied_requests",
                        lambda con, did: [(9, "auto-withdrawn: band 'high' still covered (#233)")])
    r = client.post("/api/extract/request/9", json={"status": "pending", "actor": "ian"})
    body = r.json()
    assert body["status"] == "withdrawn" and body["rewithdrawn"] is True
    # ... and when the premise NO LONGER holds, the reopen sticks
    _use(monkeypatch, _Con([_Result(rows=[{"district_id": "D1", "band": None, "handoff_hash": "h"}])]))
    monkeypatch.setattr(SRV.R7, "withdraw_satisfied_requests", lambda con, did: [])
    r2 = client.post("/api/extract/request/9", json={"status": "pending", "actor": "ian"})
    assert r2.json() == {"request_id": 9, "status": "pending"}


# ------------------------------- gate-mode settings (#104) -------------------------------
def test_gate_mode_list_fills_defaults_and_inherits(monkeypatch):
    # one stored row (global default = auto); unset gates inherit it, none are overridden
    _use(monkeypatch, _Con([_Result(rows=[
        {"gate": "default", "configured_mode": "auto", "license_state": None}])]))
    body = client.get("/api/gate-mode").json()
    assert body["settings"]["default"]["configured_mode"] == "auto"
    assert body["settings"]["gate@6"]["configured_mode"] == "auto"        # inherited
    assert body["settings"]["gate@6"]["is_override"] is False
    assert set(body["settings"]) == {"default", *SRV.GM.GATES}


def test_gate_mode_set_rejects_bad_gate_or_mode(monkeypatch):
    # validation precedes any DB access -> 400, no session needed
    assert client.post("/api/gate-mode", json={"gate": "gate@9", "mode": "auto"}).status_code == 400
    assert client.post("/api/gate-mode", json={"gate": "gate@5", "mode": "on"}).status_code == 400


def test_gate_mode_set_persists_and_backs_up(monkeypatch):
    # set_configured_mode (INSERT) -> commit -> _backup_gate_mode (SELECT, quarantined under pytest)
    _use(monkeypatch, _Con([_Result(), _Result(rows=[
        {"gate": "gate@7", "configured_mode": "auto", "license_state": None,
         "updated_at": "t", "actor": "ian"}])]))
    r = client.post("/api/gate-mode", json={"gate": "gate@7", "mode": "auto", "actor": "ian"})
    assert r.status_code == 200 and r.json() == {"ok": True, "gate": "gate@7", "mode": "auto"}


# ------------------------------- exploration audit (gate@5 reject audit, #211) -------------------------------
def test_exploration_audit_status_is_dormant_and_well_shaped(monkeypatch):
    # execute order for GET /api/exploration-audit with an EMPTY reject bucket — ONE population draw
    # serves the meter, the resolve, and the pending queue (PR #248 review: it used to run twice):
    #   1 reject_population SELECT (the endpoint's single audit_sample draw) -> []
    #   2 get_configured_mode own -> None, 3 get_configured_mode default -> None (=> "manual")
    #   4 get_license_state -> None
    _use(monkeypatch, _Con([_Result(rows=[]), _Result(scalar=None), _Result(scalar=None),
                            _Result(scalar=None)]))
    body = client.get("/api/exploration-audit").json()
    # DORMANT: configured manual → effective manual, empty bucket → zero window, all-None quality
    assert body["configured_mode"] == "manual" and body["effective_mode"] == "manual"
    assert body["population_size"] == 0 and body["window_count"] == 0 and body["pending"] == []
    assert body["quality"]["rejection_quality"] is None
    assert body["floor_n"] == 300 and body["promote_n"] == 360
