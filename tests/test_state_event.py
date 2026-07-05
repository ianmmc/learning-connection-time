"""REQ-099 — the cross-stage lifecycle log: district_status migrated from a JSON registry to an
append-only `state_event` table + derived `current_state` view in the isolated governance Postgres.

Two layers:
  - the in-memory `registry` ops (record_stage / already_attempted) are PURE dict logic — tested
    with no DB, exactly as before, so the stage scripts' reconcile paths stay DB-free.
  - the DB layer (the state_event INSERT + the current_state projection) is tested against the real
    governance Postgres via the gov_session fixture; inserts are made on the session and ROLLED BACK
    at teardown (test-specific district_ids, so the live 36-district data is never touched).
"""
from sqlalchemy import text

from infrastructure.acquisition.common import district_status as DS


def _empty():
    return {"schema_version": DS.SCHEMA_VERSION, "last_updated": None, "districts": {}, "_events": []}


# ----------------------------- in-memory registry ops (no DB) -----------------------------
def test_record_stage_updates_snapshot_and_history():
    reg = _empty()
    DS.record_stage(reg, "0200600", "Fairbanks", "AK", stage=1, stage_name="queue", outcome="queued")
    d = reg["districts"]["0200600"]
    assert d["furthest_stage"] == 1 and d["stage_name"] == "queue" and d["outcome"] == "queued"
    assert len(d["history"]) == 1
    DS.record_stage(reg, "0200600", "Fairbanks", "AK", stage=2, stage_name="discover",
                    outcome="found_hub", topology="hub")
    d = reg["districts"]["0200600"]
    assert d["furthest_stage"] == 2 and d["topology"] == "hub" and len(d["history"]) == 2


def test_already_attempted_only_at_stage_3():
    reg = _empty()
    assert not DS.already_attempted(reg, "0200600")
    DS.record_stage(reg, "0200600", "Fairbanks", "AK", stage=1, stage_name="queue", outcome="queued")
    assert not DS.already_attempted(reg, "0200600")     # Stage 1 only -> still eligible for redraw
    DS.record_stage(reg, "0200600", "Fairbanks", "AK", stage=3, stage_name="capture", outcome="captured")
    assert DS.already_attempted(reg, "0200600")          # Stage 3 reached -> excluded


def test_furthest_stage_is_monotonic_max_not_latest():
    """A re-discovery event (lower stage) after capture must NOT lower furthest_stage — the
    attempt exclusion has to stay sticky. (Old JSON registry set furthest_stage = latest stage.)"""
    reg = _empty()
    DS.record_stage(reg, "d", "n", "ZZ", stage=4, stage_name="process", outcome="processed_all")
    DS.record_stage(reg, "d", "n", "ZZ", stage=2, stage_name="discover", outcome="re_discovery")
    assert reg["districts"]["d"]["furthest_stage"] == 4
    assert DS.already_attempted(reg, "d")


def test_record_stage_buffers_event_with_defaults():
    reg = _empty()
    DS.record_stage(reg, "d", "n", "ZZ", stage=3, stage_name="capture", outcome="captured")
    ev = reg["_events"][-1]
    assert ev["event_type"] == "captured"      # progression: event_type defaults to the outcome
    assert ev["actor"] == "auto:stage3"        # progression: actor defaults to auto:stage{N}
    assert ev["stage"] == 3 and ev["checkpoint"] is None


def test_checkpoint_event_does_not_move_furthest_stage():
    reg = _empty()
    DS.record_stage(reg, "d", "n", "ZZ", stage=3, stage_name="capture", outcome="captured")
    DS.record_stage(reg, "d", "n", "ZZ", checkpoint="CP-A", event_type="approved", actor="ian")
    d = reg["districts"]["d"]
    assert d["furthest_stage"] == 3            # checkpoint has no stage -> furthest_stage unchanged
    ev = reg["_events"][-1]
    assert ev["checkpoint"] == "CP-A" and ev["event_type"] == "approved" and ev["actor"] == "ian"
    assert ev["stage"] is None


# ----------------------------- DB layer: state_event + current_state (rolled back) -----------------------------
def _insert(sess, did, **over):
    row = {"district_id": did, "name": "N", "state": "ZZ", "stage": None, "stage_name": None,
           "checkpoint": None, "event_type": "event", "outcome": None, "topology": None,
           "batch_id": None, "fingerprints_json": None, "actor": "auto", "note": "",
           "created_at": "2026-06-26T00:00:00Z"}
    row.update(over)
    sess.execute(DS.INSERT_STATE_EVENT, row)


def test_current_state_projects_max_stage_and_latest_snapshot(gov_session):
    DS.ensure_schema()                          # real table + view (committed, idempotent)
    did = "TST0001"
    _insert(gov_session, did, stage=1, stage_name="queue", outcome="queued",
            event_type="queued", created_at="2026-06-26T00:00:01Z")
    _insert(gov_session, did, stage=4, stage_name="process", outcome="processed_all",
            topology="hub", batch_id="batch_TST", event_type="processed_all",
            created_at="2026-06-26T00:00:02Z")
    # a later checkpoint event (no stage) must not change furthest_stage or the stage snapshot
    _insert(gov_session, did, checkpoint="CP-A", event_type="approved", actor="ian",
            created_at="2026-06-26T00:00:03Z")
    r = gov_session.execute(text(
        "SELECT furthest_stage, stage_name, outcome, topology, batch_id, last_event_type, last_checkpoint "
        "FROM current_state WHERE district_id=:d"), {"d": did}).mappings().first()
    assert r["furthest_stage"] == 4                      # MAX(stage), not the latest event's stage
    assert r["stage_name"] == "process" and r["outcome"] == "processed_all"   # from the latest STAGE event
    assert r["topology"] == "hub" and r["batch_id"] == "batch_TST"
    assert r["last_event_type"] == "approved" and r["last_checkpoint"] == "CP-A"  # latest event of any kind
    gov_session.rollback()


def test_current_state_name_state_survive_null_writers(gov_session):
    """#165 — name/state resolve to the latest NON-NULL value across all events, so a writer that
    doesn't carry them (the old stage-7 extract wrote state NULL; gate@6 writes name='') can't null
    the header. batch_id deliberately STAYS event-accurate (the latest stage event's value, NULL
    included) — batch membership's authority is batch_district."""
    DS.ensure_schema()
    did = "TST0165"
    _insert(gov_session, did, stage=1, stage_name="queue", outcome="queued",
            name="Marionville", state="IA", batch_id="batch_TST",
            event_type="queued", created_at="2026-07-04T00:00:01Z")
    # a gate@6 checkpoint event with empty name + NULL state (the old writer shape)
    _insert(gov_session, did, name="", state=None, checkpoint="gate@6",
            event_type="dispatched", created_at="2026-07-04T00:00:02Z")
    # a stage-7 extract event with state NULL and batch_id NULL (the exact #165 shape)
    _insert(gov_session, did, name="Marionville", state=None, stage=7, stage_name="extract",
            outcome="extracted", event_type="extracted", created_at="2026-07-04T00:00:03Z")
    r = gov_session.execute(text(
        "SELECT name, state, furthest_stage, stage_name, batch_id "
        "FROM current_state WHERE district_id=:d"), {"d": did}).mappings().first()
    assert r["name"] == "Marionville"
    assert r["state"] == "IA"                    # survived two null/empty-state writers
    assert r["furthest_stage"] == 7 and r["stage_name"] == "extract"
    assert r["batch_id"] is None                 # event-accurate by design (not latest-non-null)
    gov_session.rollback()


def test_save_then_load_round_trips_through_db(gov_session):
    """record_stage -> the buffered events INSERT into state_event -> current_state reflects them.
    Done on the rolled-back session (no commit, no save()) so the live data is untouched."""
    DS.ensure_schema()
    did = "TST0002"
    reg = _empty()
    DS.record_stage(reg, did, "N", "ZZ", stage=1, stage_name="queue", outcome="queued")
    DS.record_stage(reg, did, "N", "ZZ", stage=3, stage_name="capture", outcome="captured")
    for ev in reg["_events"]:
        gov_session.execute(DS.INSERT_STATE_EVENT, ev)
    r = gov_session.execute(text(
        "SELECT furthest_stage, stage_name, outcome FROM current_state WHERE district_id=:d"),
        {"d": did}).mappings().first()
    assert r["furthest_stage"] == 3 and r["stage_name"] == "capture" and r["outcome"] == "captured"
    gov_session.rollback()


# ----------------------------- save(export=...) / export() — issue #49 (no DB: all faked) -----------------------------
def _fake_db(monkeypatch, exports: list):
    """Stub the schema/session/export plumbing so the save() control flow is testable DB-free."""
    import contextlib

    class _Con:
        def execute(self, *a, **k):
            pass

        def commit(self):
            pass

    @contextlib.contextmanager
    def scope():
        yield _Con()

    monkeypatch.setattr(DS, "ensure_schema", lambda: None)
    monkeypatch.setattr(DS.gdb, "session_scope", scope)
    monkeypatch.setattr(DS, "export_status", lambda s, out=None: exports.append(1) or 0)


def test_save_default_exports_the_backup(monkeypatch):
    exports: list = []
    _fake_db(monkeypatch, exports)
    reg = _empty()
    DS.record_stage(reg, "TSTX", "N", "ZZ", stage=1, stage_name="queue", outcome="queued")
    assert DS.save(reg) == 1
    assert exports == [1]                    # single-call behavior unchanged for normal callers
    assert reg["_events"] == []


def test_save_export_false_defers_the_backup(monkeypatch):
    """Batch runners save per district with export=False (O(N²) fix) and export once at run end."""
    exports: list = []
    _fake_db(monkeypatch, exports)
    reg = _empty()
    for i in range(3):
        DS.record_stage(reg, f"TSTX{i}", "N", "ZZ", stage=2, stage_name="discover", outcome="found_all")
        DS.save(reg, export=False)
    assert exports == []                     # no per-district regeneration
    DS.export()
    assert exports == [1]                    # exactly one full regeneration at run end
