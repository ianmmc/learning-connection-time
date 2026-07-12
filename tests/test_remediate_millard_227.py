"""#227 Millard decontamination — guardrails for the one-off remediation script.

Exercises the reversible core (manifest → label reset + signal/cache purge + domain set + audit event)
against a SYNTHETIC ZZ district (the script's constants are monkeypatched) so it never touches the real
Millard rows. Confirms the manifest is read-only, the purge is scoped + complete, the precious batch row
survives with the corrected domain, and prior audit history is preserved (not rewritten)."""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage1_queue.models import BatchDistrict   # noqa: F401 (register batch tables)
from infrastructure.acquisition.stage5_filter import models  # noqa: F401 (register precious tables)
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.process_governance import remediate_millard_227 as R

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

DID, BID = "ZZ227DIST", "ZZ227BATCH"


def _cleanup(s):
    s.execute(text("DELETE FROM label WHERE rec_key LIKE :p"), {"p": f"{DID}:%"})
    for t in ("representation",):
        s.execute(text(f"DELETE FROM {t} WHERE rec_key LIKE :p"), {"p": f"{DID}:%"})
    for t in ("record", "district", "district_target", "discovery_school", "candidate", "capture",
              "processed_doc", "state_event", "calibration_event"):
        s.execute(text(f"DELETE FROM {t} WHERE district_id=:d"), {"d": DID})
    s.execute(text("DELETE FROM batch_district WHERE district_id=:d"), {"d": DID})


def _seed(s):
    # a contaminated district: 3 records — 2 carry a non-unlabeled (wrong-district) label, 1 unlabeled.
    s.execute(text("INSERT INTO district (district_id, name, state, pipeline_state, attention_score, "
                   "attention_reasons_json, n_unlabeled, n_records) "
                   "VALUES (:d,'ZZ Millard','NE','filtered',0,'[]',1,3)"), {"d": DID})
    s.execute(text("INSERT INTO district_target (district_id, nces_total) VALUES (:d, 34)"), {"d": DID})
    for i, (pl, st) in enumerate([("target_absent", "labeled"), ("unusable", "labeled"), (None, "unlabeled")]):
        rk = f"{DID}:{i}"
        s.execute(text("INSERT INTO record (rec_key, district_id, url, tier, attention_score, "
                       "attention_reasons_json, is_cluster_rep) VALUES (:rk,:d,:u,'C',0,'[]',1)"),
                  {"rk": rk, "d": DID, "u": f"http://off{i}.example/bell"})
        s.execute(text("INSERT INTO label (rec_key, primary_label, status) VALUES (:rk,:pl,:st)"),
                  {"rk": rk, "pl": pl, "st": st})
    # cache rows: 5 captures (2 on the real domain, 3 off) + a candidate
    for i in range(5):
        host = "mpsomaha.org" if i < 2 else f"off{i}.example"
        s.execute(text("INSERT INTO capture (district_id, hash, url, final_host) VALUES (:d,:h,:u,:fh)"),
                  {"d": DID, "h": f"h{i}", "u": f"http://{host}/{i}", "fh": host})
    s.execute(text("INSERT INTO candidate (district_id, url) VALUES (:d,'http://x/c')"), {"d": DID})
    # the PRECIOUS batch_district row — blank domain is the bug (ORM add applies the column defaults)
    s.add(BatchDistrict(batch_id=BID, district_id=DID, name="ZZ Millard", state="NE", domain=""))
    # a PRIOR audit event that the remediation must PRESERVE, not rewrite
    from infrastructure.acquisition.common.district_status import INSERT_STATE_EVENT
    s.execute(INSERT_STATE_EVENT, {"district_id": DID, "name": "ZZ Millard", "state": "NE", "stage": 5,
              "stage_name": "filter", "checkpoint": None, "event_type": "ingested", "outcome": "filtered",
              "topology": None, "batch_id": BID, "fingerprints_json": None, "actor": "auto:stage5",
              "note": "prior", "created_at": "2026-07-11T06:00:00Z"})
    s.flush()


@pytest.fixture
def con(monkeypatch):
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    gdb.init_precious_schema()          # precious tables incl. label + calibration_event + batch_district
    DS.ensure_schema()                  # state_event + current_state view
    monkeypatch.setattr(R, "DISTRICT_ID", DID)
    monkeypatch.setattr(R, "BATCH_ID", BID)
    monkeypatch.setattr(R, "REC_PREFIX", f"{DID}:")
    monkeypatch.setattr(R.BSTORE, "write_receipt", lambda *a, **k: None)   # receipt regen tested elsewhere
    with gdb.session_scope() as s:
        BS.ensure_signal_schema(s)
        CI.ensure_cache_schema(s)
        _cleanup(s)
        _seed(s)
    try:
        with gdb.session_scope() as s:
            yield s
    finally:
        with gdb.session_scope() as s:
            _cleanup(s)


def _n(s, sql, **p):
    return int(s.execute(text(sql), p).scalar() or 0)


def test_build_manifest_reports_contamination_and_is_readonly(con):
    m = R.build_manifest(con)
    assert m["domain"]["current"] == ""                        # the blank-domain bug
    assert {r["rec_key"] for r in m["labels_to_reset"]} == {f"{DID}:0", f"{DID}:1"}
    assert m["captures"] == {"total": 5, "on_real_domain": 2, "off_domain": 3}
    assert m["purge_counts"]["record"] == 3 and m["purge_counts"]["capture"] == 5
    assert m["purge_counts"]["candidate"] == 1 and m["purge_counts"]["district"] == 1
    assert m["preserved"]["state_event"] == 1                  # the prior 'ingested' event
    # READ-ONLY: building the manifest changed nothing
    assert _n(con, "SELECT COUNT(*) FROM label WHERE rec_key LIKE :p AND status!='unlabeled'",
              p=f"{DID}:%") == 2
    assert _n(con, "SELECT COUNT(*) FROM record WHERE district_id=:d", d=DID) == 3


def test_execute_decontaminates_and_scopes_the_domain(con):
    m = R.build_manifest(con)
    done = R.execute(con, m, "mpsomaha.org")
    con.flush()
    # 1. labels reset to a truthful unlabeled (both wrong-district labels cleared)
    assert done["labels_reset"] == 2
    assert _n(con, "SELECT COUNT(*) FROM label WHERE rec_key LIKE :p AND status!='unlabeled'", p=f"{DID}:%") == 0
    # 2. regenerable signal + cache rows purged (clean slate)
    for t in ("record", "district", "district_target", "capture", "candidate"):
        assert _n(con, f"SELECT COUNT(*) FROM {t} WHERE district_id=:d", d=DID) == 0, t
    assert done["cache_purged"]["capture"] == 5
    # 3. the domain is corrected on the PRECIOUS batch row (which itself survives)
    assert done["domain_set"] == "mpsomaha.org"
    assert _n(con, "SELECT COUNT(*) FROM batch_district WHERE batch_id=:b AND district_id=:d", b=BID, d=DID) == 1
    assert con.execute(text("SELECT domain FROM batch_district WHERE batch_id=:b AND district_id=:d"),
                       {"b": BID, "d": DID}).scalar() == "mpsomaha.org"


def test_execute_preserves_prior_audit_and_appends_a_remediation_event(con):
    m = R.build_manifest(con)
    R.execute(con, m, "mpsomaha.org")
    con.flush()
    events = con.execute(text("SELECT event_type, outcome FROM state_event WHERE district_id=:d "
                              "ORDER BY event_id"), {"d": DID}).fetchall()
    types = [e[0] for e in events]
    assert "ingested" in types, "the prior audit event must be preserved, not rewritten"
    assert ("remediated" in types), "a remediation audit event must be appended"
    assert events[-1] == ("remediated", "decontaminated")


import contextlib
import sys


@contextlib.contextmanager
def _null_scope():
    yield None


def test_second_execute_is_refused_when_already_remediated(monkeypatch, capsys):
    """Review finding: a SECOND --execute after a scoped re-run would purge the re-acquired good data.
    The enforcing guard must REFUSE (not just warn) when the domain is already non-blank, unless --force."""
    called = {"execute": False, "restore": False}
    monkeypatch.setattr(R.gdb, "init_precious_schema", lambda: None)
    monkeypatch.setattr(R.gdb, "session_scope", _null_scope)
    monkeypatch.setattr(R, "build_manifest", lambda con, domain=R.DEFAULT_DOMAIN: {
        "domain": {"current": "mpsomaha.org", "new": None}, "labels_to_reset": [],
        "captures": {}, "purge_counts": {}, "preserved": {}, "disk_dir": None})
    monkeypatch.setattr(R, "_write_restore_point", lambda m: called.__setitem__("restore", True))
    monkeypatch.setattr(R, "execute", lambda *a, **k: called.__setitem__("execute", True) or {})
    monkeypatch.setattr(R, "_disk_dir", lambda: None)   # never touch the real filesystem
    monkeypatch.setattr(sys, "argv", ["prog", "--execute"])
    R.main()
    assert called["execute"] is False and called["restore"] is False
    assert "REFUSING" in capsys.readouterr().out


def test_force_overrides_the_already_remediated_guard(monkeypatch):
    """--force is the explicit escape hatch: it proceeds even when the domain is already set."""
    called = {"execute": False}
    monkeypatch.setattr(R.gdb, "init_precious_schema", lambda: None)
    monkeypatch.setattr(R.gdb, "session_scope", _null_scope)
    monkeypatch.setattr(R, "build_manifest", lambda con, domain=R.DEFAULT_DOMAIN: {
        "domain": {"current": "mpsomaha.org", "new": None}, "labels_to_reset": [],
        "captures": {}, "purge_counts": {}, "preserved": {}, "disk_dir": None})
    monkeypatch.setattr(R, "_write_restore_point", lambda m: None)
    monkeypatch.setattr(R, "execute", lambda *a, **k: called.__setitem__("execute", True) or {})
    monkeypatch.setattr(R, "_disk_dir", lambda: None)
    monkeypatch.setattr(sys, "argv", ["prog", "--execute", "--force"])
    R.main()
    assert called["execute"] is True
