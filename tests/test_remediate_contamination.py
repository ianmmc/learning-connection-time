"""#227 unscoped-discovery decontamination — guardrails for the remediation tooling.

Exercises the reversible core (manifest → label reset + signal/cache purge + domain set + audit event)
against a SYNTHETIC ZZ district so it never touches the real Millard rows. Confirms the manifest is
read-only, execute() is manifest-driven (the reviewed rec_keys are exactly what resets), the purge is
scoped + complete, the precious batch row survives with the corrected domain, prior audit history is
preserved, and the PR #242 review guards hold (no disk writes inside execute's transaction, verified
restore point, validated --domain, dot-boundary host counting, double-execute refusal)."""
import contextlib
import sys

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage1_queue.models import BatchDistrict   # noqa: F401 (register batch tables)
from infrastructure.acquisition.stage5_filter import models  # noqa: F401 (register precious tables)
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.process_governance import remediate_contamination as R

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

DID, BID = "ZZ227DIST", "ZZ227BATCH"
DOMAIN = "mpsomaha.org"


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
    # cache rows: 6 captures — 2 genuinely on-domain (bare + subdomain), 1 LOOKALIKE host
    # (evil<domain>, the dot-boundary trap), 3 plainly off
    hosts = [DOMAIN, f"es.{DOMAIN}", f"evil{DOMAIN}", "off3.example", "off4.example", "off5.example"]
    for i, host in enumerate(hosts):
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
def con():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    gdb.init_precious_schema()          # precious tables incl. label + calibration_event + batch_district
    DS.ensure_schema()                  # state_event + current_state view
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
    m = R.build_manifest(con, BID, DID, DOMAIN)
    assert m["domain"]["current"] == "" and m["domain"]["new"] == DOMAIN
    assert m["district_name"] == "ZZ Millard" and m["district_state"] == "NE"
    assert {r["rec_key"] for r in m["labels_to_reset"]} == {f"{DID}:0", f"{DID}:1"}
    # dot-boundary counting (PR #242 review): es.mpsomaha.org IS on-domain, evilmpsomaha.org is NOT
    assert m["captures"] == {"total": 6, "on_real_domain": 2, "off_domain": 4}
    assert m["purge_counts"]["record"] == 3 and m["purge_counts"]["capture"] == 6
    assert m["purge_counts"]["candidate"] == 1 and m["purge_counts"]["district"] == 1
    assert m["preserved"]["state_event"] == 1                  # the prior 'ingested' event
    # READ-ONLY: building the manifest changed nothing
    assert _n(con, "SELECT COUNT(*) FROM label WHERE rec_key LIKE :p AND status!='unlabeled'",
              p=f"{DID}:%") == 2
    assert _n(con, "SELECT COUNT(*) FROM record WHERE district_id=:d", d=DID) == 3


def test_execute_decontaminates_and_scopes_the_domain(con):
    m = R.build_manifest(con, BID, DID, DOMAIN)
    done = R.execute(con, m)
    con.flush()
    # 1. labels reset to a truthful unlabeled (both wrong-district labels cleared)
    assert done["labels_reset"] == 2
    assert _n(con, "SELECT COUNT(*) FROM label WHERE rec_key LIKE :p AND status!='unlabeled'", p=f"{DID}:%") == 0
    # 2. regenerable signal + cache rows purged (clean slate)
    for t in ("record", "district", "district_target", "capture", "candidate"):
        assert _n(con, f"SELECT COUNT(*) FROM {t} WHERE district_id=:d", d=DID) == 0, t
    assert done["cache_purged"]["capture"] == 6
    # 3. the domain is corrected on the PRECIOUS batch row (which itself survives)
    assert done["domain_set"] == DOMAIN
    assert _n(con, "SELECT COUNT(*) FROM batch_district WHERE batch_id=:b AND district_id=:d", b=BID, d=DID) == 1
    assert con.execute(text("SELECT domain FROM batch_district WHERE batch_id=:b AND district_id=:d"),
                       {"b": BID, "d": DID}).scalar() == DOMAIN


def test_execute_is_manifest_driven_not_repredicated(con):
    """PR #242 review: execute() must reset exactly the rec_keys the reviewed manifest enumerates.
    A label applied AFTER the manifest was built (concurrent console use) must NOT be swept up."""
    m = R.build_manifest(con, BID, DID, DOMAIN)
    con.execute(text("UPDATE label SET primary_label='school_bell_table', status='labeled' "
                     "WHERE rec_key=:rk"), {"rk": f"{DID}:2"})   # labeled after the review snapshot
    done = R.execute(con, m)
    con.flush()
    assert done["labels_reset"] == 2                            # only the two reviewed rows
    assert con.execute(text("SELECT status FROM label WHERE rec_key=:rk"),
                       {"rk": f"{DID}:2"}).scalar() == "labeled"   # the post-review label survives


def test_execute_makes_no_disk_writes(con, monkeypatch):
    """PR #242 review (transaction safety): execute() runs entirely inside the caller's open
    transaction — labels.json/receipt writes happen ONLY post-commit in main(). If execute ever
    calls the exporters, a mid-transaction failure would leave disk ahead of a rolled-back DB."""
    def _boom(*a, **k):
        raise AssertionError("execute() must not write disk receipts mid-transaction")
    monkeypatch.setattr(R.BS, "export_labels", _boom)
    monkeypatch.setattr(R.BSTORE, "write_receipt", _boom)
    m = R.build_manifest(con, BID, DID, DOMAIN)
    R.execute(con, m)   # must not raise


def test_execute_preserves_prior_audit_and_appends_a_remediation_event(con):
    m = R.build_manifest(con, BID, DID, DOMAIN)
    R.execute(con, m)
    con.flush()
    events = con.execute(text("SELECT event_type, outcome FROM state_event WHERE district_id=:d "
                              "ORDER BY event_id"), {"d": DID}).fetchall()
    types = [e[0] for e in events]
    assert "ingested" in types, "the prior audit event must be preserved, not rewritten"
    assert ("remediated" in types), "a remediation audit event must be appended"
    assert events[-1] == ("remediated", "decontaminated")


# ----------------------------- restore point (no DB) -----------------------------
def test_restore_point_is_verified_and_recorded(tmp_path, monkeypatch):
    src_labels = tmp_path / "labels.json"; src_labels.write_text('[{"x": 1}]')
    src_status = tmp_path / "district_status.json"; src_status.write_text("{}")
    monkeypatch.setattr(R.paths, "LABELS_JSON", src_labels)
    monkeypatch.setattr(R.paths, "STATUS_FILE", src_status)
    monkeypatch.setattr(R.paths, "ACQUISITION", tmp_path / "acq")
    m = {"district_id": DID, "generated_at": "2026-07-12T00:00:00Z"}
    rdir = R._write_restore_point(m)
    assert (rdir / "labels.json").read_text() == '[{"x": 1}]'
    assert (rdir / "manifest.json").exists()
    assert m["restore_point"]["backed_up"] == [str(rdir / "labels.json"), str(rdir / "district_status.json")]
    assert m["restore_point"]["absent_sources"] == []


def test_restore_point_records_absent_sources_instead_of_silently_skipping(tmp_path, monkeypatch):
    monkeypatch.setattr(R.paths, "LABELS_JSON", tmp_path / "nope-labels.json")
    monkeypatch.setattr(R.paths, "STATUS_FILE", tmp_path / "nope-status.json")
    monkeypatch.setattr(R.paths, "ACQUISITION", tmp_path / "acq")
    m = {"district_id": DID, "generated_at": "2026-07-12T00:00:00Z"}
    R._write_restore_point(m)
    assert len(m["restore_point"]["absent_sources"]) == 2 and m["restore_point"]["backed_up"] == []


# ----------------------------- main() guards (no DB) -----------------------------
@contextlib.contextmanager
def _null_scope():
    yield None


def _stub_main_env(monkeypatch, *, domain_current, called):
    monkeypatch.setattr(R.gdb, "init_precious_schema", lambda: None)
    monkeypatch.setattr(R.gdb, "session_scope", _null_scope)
    monkeypatch.setattr(R, "build_manifest", lambda con, b, d, dom: {
        "batch_id": b, "district_id": d, "generated_at": "2026-07-12T00:00:00Z",
        "district_name": "X", "district_state": "NE",
        "domain": {"current": domain_current, "new": dom}, "labels_to_reset": [],
        "captures": {}, "purge_counts": {}, "preserved": {}, "disk_dir": None})
    monkeypatch.setattr(R, "_write_restore_point", lambda m: called.__setitem__("restore", True) or "rdir")
    monkeypatch.setattr(R, "execute", lambda con, m: called.__setitem__("execute", True) or {})
    monkeypatch.setattr(R, "_disk_dir", lambda did: None)      # never touch the real filesystem
    monkeypatch.setattr(R.BS, "export_labels", lambda con: 0)  # post-commit exporters stubbed
    monkeypatch.setattr(R.BSTORE, "write_receipt", lambda con, b: None)


def test_second_execute_is_refused_when_already_remediated(monkeypatch, capsys):
    """A SECOND --execute after a scoped re-run would purge the re-acquired good data. The enforcing
    guard must REFUSE (not just warn) when the domain is already non-blank, unless --force."""
    called = {"execute": False, "restore": False}
    _stub_main_env(monkeypatch, domain_current="mpsomaha.org", called=called)
    monkeypatch.setattr(sys, "argv", ["prog", "--execute"])
    R.main()
    assert called["execute"] is False and called["restore"] is False
    assert "REFUSING" in capsys.readouterr().out


def test_force_overrides_the_already_remediated_guard(monkeypatch):
    """--force is the explicit escape hatch: it proceeds even when the domain is already set."""
    called = {"execute": False}
    _stub_main_env(monkeypatch, domain_current="mpsomaha.org", called=called)
    monkeypatch.setattr(sys, "argv", ["prog", "--execute", "--force"])
    R.main()
    assert called["execute"] is True


def test_junk_domain_argument_is_refused(monkeypatch):
    """PR #242 review: the --domain side door gets the same #229 validation as Stage-1 admission —
    a junk value must never be written into batch_district.domain."""
    called = {"execute": False}
    _stub_main_env(monkeypatch, domain_current="", called=called)
    for bad in ("N/A", "http://", "none", "375 LEE ST"):
        monkeypatch.setattr(sys, "argv", ["prog", "--execute", "--domain", bad])
        with pytest.raises(SystemExit, match="#229"):
            R.main()
    assert called["execute"] is False


def test_cli_targets_are_arguments_not_constants(monkeypatch, capsys):
    """PR #242 review (altitude): the next contaminated district is a CLI invocation, not a
    copy-pasted script — --batch-id/--district-id flow through to the manifest."""
    seen = {}
    called = {"execute": False}
    _stub_main_env(monkeypatch, domain_current="", called=called)
    monkeypatch.setattr(R, "build_manifest", lambda con, b, d, dom: seen.update(b=b, d=d) or {
        "batch_id": b, "district_id": d, "generated_at": "x", "district_name": None,
        "district_state": None, "domain": {"current": "", "new": dom}, "labels_to_reset": [],
        "captures": {}, "purge_counts": {}, "preserved": {}, "disk_dir": None})
    monkeypatch.setattr(sys, "argv", ["prog", "--batch-id", "batch_00099", "--district-id", "1234567",
                                      "--domain", "other.k12.ne.us"])
    R.main()
    assert seen == {"b": "batch_00099", "d": "1234567"}
