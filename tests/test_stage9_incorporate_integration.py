"""Stage 9 — Incorporate: cross-DB integration (govdb + integration; needs BOTH Postgres DBs up).

Scope: the NOVEL Stage-9 behavior against real Postgres — the sanctioned LCT `bell_schedules` write
(council + statutory), verify-in-DB, the Stage-9 orphan reconcile, the governance 'incorporated'
ledger stamp, and idempotency/correction. The governance READ half (load_closing_argument /
decision_status) is unit-tested in test_closing_argument / test_stage8_approval and exercised
end-to-end by the live-DB smoke, so it is patched here at a documented seam — this test drives real
CA.fingerprint over the patched receipts and real DB writes on both sides.

Skips cleanly if either DB is unreachable (mirrors the gov_session fixture).
"""
import json

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from tests import benchmark_seed as BSEED
from infrastructure.acquisition.stage8_aggregate import approval as APV
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA
from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import receipts as RCPT
from infrastructure.acquisition.stage9_incorporate import incorporate as INC
from infrastructure.acquisition.stage9_incorporate import ledger as LEDGER

pytestmark = [pytest.mark.govdb, pytest.mark.integration]

TEST_DID = "9999901"
MISSING_DID = "9999909"
TEST_STATE = "ZZ"


# ----------------------------- fake governance receipts -----------------------------
def _council_band(gross=420, *, year="2024-25"):
    return {"gross_minutes": gross, "start_time": "08:00",
            "end_time": f"{8 + gross // 60:02d}:{gross % 60:02d}", "method": "modal",
            "sampling": {"n_sampled": 3, "n_total": 3, "coverage": 1.0, "plurality_share": 1.0},
            "schools": [{"school": "oak", "gross": gross, "start_time": "08:00",
                         "end_time": f"{8 + gross // 60:02d}:{gross % 60:02d}",
                         "school_year": year, "models": ["m1", "m2"],
                         "evidence": {"url": "https://d.org/oak"}}]}


def _fake_ca(did, *, council=None, unsatisfied=()):
    return {"district_id": did,
            "bands": {b: _council_band(**(kw or {})) for b, kw in (council or {}).items()},
            "negative_space": {"unsatisfied_bands": sorted(unsatisfied)},
            "slot_projection": {}, "provenance": {}}


def _patch_gov(monkeypatch, ca, *, approved=True, approval_id=1, disposition="approved",
               latest_disposition=None, latest_approval_id=None):
    """Patch the governance READ seam so the orchestrator sees `ca` as the approved+fresh receipt.
    `latest_disposition`/`latest_approval_id` override ONLY the second read (latest_decision) to
    simulate a concurrent gate@8 action landing between the two governance reads (the TOCTOU case)."""
    monkeypatch.setattr(CA, "load_closing_argument", lambda gs, did, **kw: ca)
    fp = CA.fingerprint(ca)
    monkeypatch.setattr(APV, "decision_status", lambda gs, did, current_fingerprint=None: {
        "decided": True, "disposition": disposition,
        "is_approved": approved, "is_stale": not approved,
        "latest": {"approval_id": approval_id, "disposition": disposition}})
    ld_disp = latest_disposition or disposition
    ld_id = latest_approval_id if latest_approval_id is not None else approval_id
    monkeypatch.setattr(APV, "latest_decision", lambda gs, did, with_receipt=False: {
        "approval_id": ld_id, "district_id": did, "disposition": ld_disp,
        "facts_fingerprint": fp, "receipt_json": json.dumps(ca)})
    return fp


# ----------------------------- DB helpers -----------------------------
def _require_dbs():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from infrastructure.database.connection import test_connection
    if not test_connection():
        pytest.skip("LCT production Postgres unavailable")


def _cleanup():
    from infrastructure.database.connection import session_scope as lct_scope
    dids = (TEST_DID, MISSING_DID)
    with lct_scope() as s:
        s.execute(text("DELETE FROM bell_schedules WHERE district_id = ANY(:d)"), {"d": list(dids)})
        s.execute(text("DELETE FROM district_grade_minutes WHERE district_id = ANY(:d)"), {"d": list(dids)})
        s.execute(text("DELETE FROM lct_calculations WHERE district_id = ANY(:d)"), {"d": list(dids)})
        s.execute(text("DELETE FROM districts WHERE nces_id = ANY(:d)"), {"d": list(dids)})
        s.execute(text("DELETE FROM state_requirements WHERE state = :st"), {"st": TEST_STATE})
    with gdb.session_scope() as gs:
        gs.execute(text("DELETE FROM state_event WHERE district_id = ANY(:d) AND stage = 9"),
                   {"d": list(dids)})
        # benchmark-guard test seeds a batch/batch_district row (tolerate missing tables on a fresh DB)
        for tbl, col in (("batch_district", "batch_id"), ("batch", "batch_id")):
            try:
                gs.execute(text(f"DELETE FROM {tbl} WHERE {col} = 'zz_bench_test'"))
            except Exception:
                gs.rollback()
        # #619 provenance-guard tests seed the record/capture + dispatch/extraction/fact chain
        for sql, params in (
                ("DELETE FROM school_fact WHERE district_id = ANY(:d)", {"d": list(dids)}),
                ("DELETE FROM extraction WHERE handoff_hash = 'zzbench619'", {}),
                ("DELETE FROM handoff WHERE handoff_hash = 'zzbench619'", {}),
                ("DELETE FROM record WHERE district_id = ANY(:d)", {"d": list(dids)}),
                ("DELETE FROM capture WHERE district_id = ANY(:d)", {"d": list(dids)})):
            try:
                gs.execute(text(sql), params)
            except Exception:
                gs.rollback()


def _bell_rows(did):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import BellSchedule
    with lct_scope() as s:
        rows = (s.query(BellSchedule).filter(BellSchedule.district_id == did.zfill(7))
                .order_by(BellSchedule.grade_level, BellSchedule.year).all())
        return [{"grade_level": r.grade_level, "year": r.year, "minutes": r.instructional_minutes,
                 "method": r.method, "minutes_basis": r.minutes_basis,
                 "raw_import": r.raw_import} for r in rows]


def _grade_rows(did):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import DistrictGradeMinutes
    with lct_scope() as s:
        rows = (s.query(DistrictGradeMinutes)
                .filter(DistrictGradeMinutes.district_id == did.zfill(7)).all())
        return {r.grade: {"minutes": r.instructional_minutes, "band": r.source_band,
                          "method": r.method} for r in rows}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Seed a synthetic LCT district (+ its state statutory row), yield its id, clean both DBs.
    RAW_CAPTURES is redirected to a tmp dir so Stage-9 audit receipts (REQ-164) never touch the real
    data/raw tree."""
    _require_dbs()
    monkeypatch.setattr(paths, "RAW_CAPTURES", tmp_path)
    gdb.init_precious_schema()   # ensure state_event exists
    _cleanup()
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import District, StateRequirement
    with lct_scope() as s:
        s.add(District(nces_id=TEST_DID, name="Stage9 Test District", state=TEST_STATE, year="2024-25"))
        s.add(StateRequirement(state=TEST_STATE, state_name="Ztest",
                               elementary_minutes=300, middle_minutes=330, high_minutes=350,
                               default_minutes=360))
    try:
        yield TEST_DID
    finally:
        _cleanup()


# ----------------------------- ledger round-trip (fully real, isolated) -----------------------------
def test_ledger_roundtrip(gov_session):
    gdb.init_precious_schema()
    LEDGER.record_incorporation(gov_session, "ZZLEDGER1", fingerprint="fp-abc", approval_id=5,
                                bands={"elementary": "council_extraction"}, actor="ian")
    gov_session.flush()
    got = LEDGER.latest_incorporation(gov_session, "ZZLEDGER1")
    assert got["fingerprint"] == "fp-abc" and got["approval_id"] == 5
    assert got["bands"] == {"elementary": "council_extraction"}
    assert LEDGER.latest_incorporation(gov_session, "NOPE") is None


def test_a_blocked_write_is_recorded_without_ever_looking_written(gov_session):
    """#682: the two ledger reads answer DIFFERENT questions and must not contaminate each other —
    `latest_incorporation` = "what is written" (the idempotency key, deliberately blind to failures),
    `latest_attempt` = "what happened last" (what the reviewer needs after clicking Approve). A later
    blocked attempt must never make a written district look unwritten to the idempotency check, or a
    re-run would silently re-write it."""
    gdb.init_precious_schema()
    LEDGER.record_incorporation(gov_session, "ZZLEDGER2", fingerprint="fp-1", approval_id=5,
                                bands={"elementary": "council_extraction"}, actor="ian")
    gov_session.flush()
    LEDGER.record_incorporation_blocked(gov_session, "ZZLEDGER2", status="not_eligible",
                                        reason="benchmark provenance — walled off", actor="ian",
                                        approval_id=6, fingerprint="fp-2")
    gov_session.flush()

    assert LEDGER.latest_incorporation(gov_session, "ZZLEDGER2")["fingerprint"] == "fp-1"
    att = LEDGER.latest_attempt(gov_session, "ZZLEDGER2")
    assert att["kind"] == "incorporation_blocked" and att["status"] == "not_eligible"
    assert "benchmark provenance" in att["note"] and att["fingerprint"] == "fp-2"
    assert LEDGER.latest_attempt(gov_session, "NOPE") is None


# ----------------------------- write + stamp -----------------------------
def test_incorporate_writes_bands_and_stamps(env, monkeypatch):
    ca = _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}})
    fp = _patch_gov(monkeypatch, ca, approval_id=7)

    res = INC.incorporate_district(env, actor="ian")
    assert res.status == "incorporated" and res.fingerprint == fp

    rows = {r["grade_level"]: r for r in _bell_rows(env)}
    assert set(rows) == {"elementary", "high"}
    assert rows["elementary"]["minutes"] == 400
    assert rows["elementary"]["method"] == "council_extraction"
    assert rows["elementary"]["minutes_basis"] == "gross_bell_to_bell"
    # #95 provenance: raw_import anchors the write to the exact signed decision
    assert rows["elementary"]["raw_import"]["facts_fingerprint"] == fp
    assert rows["elementary"]["raw_import"]["approval_id"] == 7

    # governance 'incorporated' stamp landed
    with gdb.session_scope() as gs:
        inc = LEDGER.latest_incorporation(gs, env)
    assert inc and inc["fingerprint"] == fp
    assert inc["bands"] == {"elementary": "council_extraction", "high": "council_extraction"}


def test_incorporate_writes_receipt_and_refreshes_twin(env, monkeypatch):
    """REQ-164 + #615: a standalone incorporation drops a Stage-9 audit receipt into the capture dir
    AND refreshes the district_status.json twin in the same code path."""
    ca = _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}})
    _patch_gov(monkeypatch, ca, approval_id=7)
    twin = []
    monkeypatch.setattr(INC.DS, "export_status", lambda gs: twin.append("refreshed"))

    res = INC.incorporate_district(env, actor="ian")
    assert res.status == "incorporated"
    assert twin == ["refreshed"]                    # #615: twin refreshed in-path (once, standalone)

    latest = RCPT.latest_receipt(env, "Stage9 Test District", "stage9_incorporate")
    assert latest is not None and latest.name.startswith("stage9_incorporate.")
    assert ".py-" in latest.name                    # writer-tagged, always-stamped
    doc = json.loads(latest.read_text())
    assert doc["stage"] == 9 and doc["district_id"] == env and doc["approval_id"] == 7
    assert {b["grade_level"] for b in doc["bands"]} == {"elementary", "high"}
    assert doc["grade_minutes"]                      # non-empty per-grade projection
    assert doc["authoritative"].startswith("gov_db:")   # audit projection, not a transmission vehicle


def test_batch_refreshes_twin_once_not_per_district(env, monkeypatch):
    """incorporate_batch exports the twin ONCE at the end, never per district (issue #49 O(N^2))."""
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}}))
    per_district, run_end = [], []
    monkeypatch.setattr(INC.DS, "export_status", lambda gs: per_district.append(1))
    monkeypatch.setattr(INC.DS, "export", lambda: run_end.append(1))

    res = INC.incorporate_batch([env], actor="ian")
    assert res[0].status == "incorporated"
    assert per_district == []                        # no per-district export in batch mode
    assert run_end == [1]                            # exactly one run-end twin refresh


def test_statutory_fallback_write(env, monkeypatch):
    # elementary satisfied; high CLAIMED-but-unsatisfied -> statutory fallback from StateRequirement ZZ
    ca = _fake_ca(env, council={"elementary": {"gross": 400}}, unsatisfied=["high"])
    _patch_gov(monkeypatch, ca)
    INC.incorporate_district(env)

    rows = {r["grade_level"]: r for r in _bell_rows(env)}
    assert rows["elementary"]["method"] == "council_extraction"
    hi = rows["high"]
    assert hi["method"] == "statutory_fallback" and hi["minutes_basis"] == "statutory"
    assert hi["minutes"] == 350   # ZZ high_minutes; never fabricated as a measurement
    assert hi["raw_import"]["fallback"] is True


def test_reader_labels_statutory_row(env, monkeypatch):
    # A statutory-only band (no competing measured row) — the reader must keep it distinguishable:
    # source 'statutory_fallback', no bell year (#94/#582), never counted as measured/enriched.
    _patch_gov(monkeypatch, _fake_ca(env, council={}, unsatisfied=["high"]))
    INC.incorporate_district(env)
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.scripts.analyze.calculate_lct_variants import get_instructional_minutes
    with lct_scope() as s:
        minutes, source, year = get_instructional_minutes(s, env, TEST_STATE, "high")
    assert source == "statutory_fallback" and year is None and minutes == 350


# ----------------------------- idempotency + correction -----------------------------
def test_idempotent_rerun_is_noop(env, monkeypatch):
    ca = _fake_ca(env, council={"elementary": {"gross": 420}})
    _patch_gov(monkeypatch, ca)
    first = INC.incorporate_district(env)
    assert first.status == "incorporated"
    second = INC.incorporate_district(env)
    assert second.status == "already_incorporated"
    assert len(_bell_rows(env)) == 1   # no duplicate row


def test_reapproval_correction_updates_in_place(env, monkeypatch):
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 420}}), approval_id=1)
    INC.incorporate_district(env)
    # a corrected re-approval (new gross -> new fingerprint) updates the SAME row
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 430}}), approval_id=2)
    res = INC.incorporate_district(env)
    assert res.status == "incorporated"
    rows = _bell_rows(env)
    assert len(rows) == 1 and rows[0]["minutes"] == 430


def _times(did, grade="elementary"):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import BellSchedule
    with lct_scope() as s:
        r = (s.query(BellSchedule).filter(BellSchedule.district_id == did.zfill(7),
                                          BellSchedule.grade_level == grade).first())
        return (r.start_time, r.end_time, r.instructional_minutes, bool(r.human_vouched))


def test_630_reapproval_to_mean_tiebreak_clears_stale_times(env, monkeypatch):
    """#630: v1 modal band carries real consistent times; v2 re-approval over the SAME (year, grade)
    key resolves mean_tiebreak — synthetic gross, receipt still carrying one school's times (a
    pre-#627 frozen shape). The UPDATE must NOT merge-preserve v1's (or the receipt's) stale times:
    the row lands minutes-only, and _verify_written now enforces the #627 invariant for council rows."""
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 415, "year": "2024-25"}}),
               approval_id=1)
    INC.incorporate_district(env)
    st, et, mins, _ = _times(env)
    assert (st, et, mins) == ("08:00", "14:55", 415)   # v1: real, consistent times
    # v2: same year key, mean_tiebreak 425 with a school's 415-span times (inconsistent → dropped)
    ca2 = _fake_ca(env)
    ca2["bands"]["elementary"] = {
        "gross_minutes": 425, "start_time": "08:00", "end_time": "14:55", "method": "mean_tiebreak",
        "sampling": {"n_sampled": 2, "n_total": 2, "coverage": 1.0, "plurality_share": 0.5},
        "schools": [
            {"school": "oak", "gross": 415, "start_time": "08:00", "end_time": "14:55",
             "school_year": "2024-25", "models": ["m1", "m2"], "evidence": {"url": "https://d.org/oak"}},
            {"school": "elm", "gross": 435, "start_time": "07:55", "end_time": "15:10",
             "school_year": "2024-25", "models": ["m1", "m2"], "evidence": {"url": "https://d.org/elm"}}]}
    _patch_gov(monkeypatch, ca2, approval_id=2)
    res = INC.incorporate_district(env)
    assert res.status == "incorporated"
    st, et, mins, _ = _times(env)
    assert (st, et, mins) == (None, None, 425), \
        f"stale times survived the UPDATE (#630): ({st!r}, {et!r}, {mins})"


def test_631_mapper_version_mismatch_triggers_rewrite(env, monkeypatch):
    """#631: an incorporation recorded under an older (or absent, pre-#631) MAPPING_VERSION is NOT
    'already_incorporated' — a plain re-run applies the current mapper's writes. A same-version
    re-run stays a no-op."""
    ca = _fake_ca(env, council={"elementary": {"gross": 420}})
    _patch_gov(monkeypatch, ca)
    assert INC.incorporate_district(env).status == "incorporated"
    assert INC.incorporate_district(env).status == "already_incorporated"
    # simulate a pre-#631 ledger event: strip the recorded mapper from the newest stamp
    with gdb.session_scope() as gs:
        row = gs.execute(text(
            "SELECT event_id, fingerprints_json FROM state_event "
            "WHERE district_id=:d AND checkpoint='incorporated' ORDER BY event_id DESC LIMIT 1"),
            {"d": env}).mappings().first()
        fp = json.loads(row["fingerprints_json"])
        fp.pop("mapper", None)
        gs.execute(text("UPDATE state_event SET fingerprints_json=:j WHERE event_id=:e"),
                   {"j": json.dumps(fp), "e": row["event_id"]})
    res = INC.incorporate_district(env)   # NO --force
    assert res.status == "incorporated", "a mapper-version mismatch must re-write without --force"
    assert INC.incorporate_district(env).status == "already_incorporated"


def test_636_vouched_band_lands_on_bell_schedules(env, monkeypatch):
    """#636: the gate@8 vouch is persisted on bell_schedules (the band source of truth), not only
    on the projection — a note-only human_override on an included school sets it; a plain council
    band leaves it False."""
    ca = _fake_ca(env, council={"elementary": {"gross": 420}, "high": {"gross": 430}})
    ca["bands"]["elementary"]["schools"][0]["human_override"] = {
        "start_time": None, "end_time": None, "reason": "verified by eye", "actor": "ian"}
    _patch_gov(monkeypatch, ca)
    INC.incorporate_district(env)
    assert _times(env, "elementary")[3] is True
    assert _times(env, "high")[3] is False
    # and the projection inherits per owning band
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import DistrictGradeMinutes
    with lct_scope() as s:
        by_grade = {r.grade: r.human_vouched for r in
                    s.query(DistrictGradeMinutes)
                    .filter(DistrictGradeMinutes.district_id == env.zfill(7)).all()}
    assert by_grade["03"] is True and by_grade["10"] is False


# ----------------------------- #605 per-grade projection -----------------------------
def test_per_grade_projection_written(env, monkeypatch):
    # council elementary + high (fake CA has empty slot_projection -> canonical fallback:
    # elementary=KG-05, high=09-12). Grades 6-8 have no serving band -> no rows.
    ca = _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}})
    _patch_gov(monkeypatch, ca)
    res = INC.incorporate_district(env)
    g = _grade_rows(env)
    assert set(g) == {"KG", "01", "02", "03", "04", "05", "09", "10", "11", "12"}
    assert g["03"] == {"minutes": 400, "band": "elementary", "method": "council_extraction"}
    assert g["10"] == {"minutes": 450, "band": "high", "method": "council_extraction"}
    assert "07" not in g
    assert res.grades == 10 and res.overlaps == 0


def test_per_grade_reprojects_and_reconciles_on_reapproval(env, monkeypatch):
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}}),
               approval_id=1)
    INC.incorporate_district(env)
    assert "10" in _grade_rows(env)
    # v2: high band drops out -> its grades (09-12) must be reconciled away
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}}), approval_id=2)
    INC.incorporate_district(env)
    g = _grade_rows(env)
    assert set(g) == {"KG", "01", "02", "03", "04", "05"}
    assert "09" not in g and "12" not in g


def test_council_to_statutory_flip_reconciles_orphan(env, monkeypatch):
    # v1: elementary is a council band (year 2024-25)
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 420, "year": "2024-25"}}))
    INC.incorporate_district(env)
    assert _bell_rows(env)[0]["method"] == "council_extraction"
    # v2: elementary loses consensus -> statutory fallback (current-year key). The old council row
    # (different year) must be reconciled away, leaving exactly one statutory elementary row.
    _patch_gov(monkeypatch, _fake_ca(env, council={}, unsatisfied=["elementary"]))
    INC.incorporate_district(env)
    rows = [r for r in _bell_rows(env) if r["grade_level"] == "elementary"]
    assert len(rows) == 1
    assert rows[0]["method"] == "statutory_fallback" and rows[0]["minutes"] == 300  # ZZ elem


# ----------------------------- #606 per-grade weighting (real table read) -----------------------------
def test_per_grade_weighted_secondary_minutes(env, monkeypatch):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import EnrollmentByGrade
    from infrastructure.scripts.analyze.calculate_lct_variants import get_statutory_minutes
    from infrastructure.scripts.analyze.per_grade_lct import (
        SEC_GRADES, get_district_grade_minutes, weighted_scope_minutes)

    # seed equal per-grade enrollment (100 each, K-12)
    with lct_scope() as s:
        cols = {"enrollment_kindergarten": 100, **{f"enrollment_grade_{n}": 100 for n in range(1, 13)}}
        s.add(EnrollmentByGrade(district_id=env, source_year="2024-25", data_source="nces_ccd", **cols))

    # incorporate all three bands -> per-grade projection covers K-12 (canonical fallback ranges)
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400},
                                                   "middle": {"gross": 430}, "high": {"gross": 450}}))
    INC.incorporate_district(env)

    with lct_scope() as s:
        gm = get_district_grade_minutes(s, env.zfill(7))
        enr = s.query(EnrollmentByGrade).filter(EnrollmentByGrade.district_id == env.zfill(7)).first()
        minutes, source, year = weighted_scope_minutes(
            s, TEST_STATE, SEC_GRADES, enr, gm, ["2024-25"], get_statutory_minutes)

    # secondary = enrollment-weighted middle(6-8)=430 + high(9-12)=450 → NOT high-only, NOT 450
    assert minutes == round((3 * 430 + 4 * 450) / 7)   # 441
    assert source == "per_grade_bell" and year == "2024-25"


# ----------------------------- eligibility + fail-loud -----------------------------
def test_not_approved_writes_nothing(env, monkeypatch):
    ca = _fake_ca(env, council={"elementary": {"gross": 420}})
    _patch_gov(monkeypatch, ca, approved=False, disposition="sent_back")
    res = INC.incorporate_district(env)
    assert res.status == "not_eligible" and res.reason == "sent_back"
    assert _bell_rows(env) == []
    with gdb.session_scope() as gs:
        assert LEDGER.latest_incorporation(gs, env) is None


def test_missing_lct_district_fails_loud(env, monkeypatch):
    ca = _fake_ca(MISSING_DID, council={"elementary": {"gross": 420}})
    _patch_gov(monkeypatch, ca)
    with pytest.raises(ValueError, match="not found in LCT"):
        INC.incorporate_district(MISSING_DID)
    assert _bell_rows(MISSING_DID) == []


# ----------------------------- the benchmark wall (PR #607 review; re-keyed by #619) --------------
def _seed_benchmark_membership(did):
    """Put `did` in a batch_type='benchmark' batch — the batch_00000 shape. Pre-#619 this ALONE
    refused the district's writes, permanently (batch_district rows are never deleted)."""
    with gdb.session_scope() as gs:
        gs.execute(text(
            "INSERT INTO batch (batch_id, batch_type, status, nces_year, created_at, created_by, "
            "meta_json) VALUES ('zz_bench_test', 'benchmark', 'approved', '2024-25', 'now', "
            "'zz-test', '{}') ON CONFLICT (batch_id) DO NOTHING"))
        gs.execute(text(
            "INSERT INTO batch_district (batch_id, district_id, ord, name, state, domain, "
            "lea_claimed_bands, nces_school_counts, band_processing_order, band_meta, included) "
            "VALUES ('zz_bench_test', :d, 0, 'Stage9 Test', 'ZZ', 'zz.test', '[]', '{}', '[]', "
            "'{}', true)"), {"d": did})


def _seed_rep(did, rec_key, hash_, source):
    """One record + its capture — the real arm-2 provenance path. Opens its own session (this module
    seeds outside the caller's transaction); the SQL is the shared one (#661)."""
    with gdb.session_scope() as gs:
        BSEED.ensure_schema(gs)
        BSEED.seed_rep(gs, did, rec_key, hash_, source)


def _ca_with_rep(did, *, rec_key, gross=420, excluded=False):
    """A one-band closing argument whose single school names `rec_key` — the write-bearing evidence
    the #619 wall interrogates."""
    ca = _fake_ca(did, council={"elementary": {"gross": gross}})
    school = ca["bands"]["elementary"]["schools"][0]
    school["rec_key"] = rec_key
    if excluded:
        # the real shape: closing_argument attaches the band_exclusion row itself, not a bool
        school["excluded"] = {"reason": "stale injected rep", "actor": "ian"}
    return ca


def test_benchmark_batch_membership_alone_no_longer_refuses(env, monkeypatch):
    """THE #619 ACCEPTANCE TEST — the exact case that was broken. A district that was in batch_00000
    and has since been honestly re-run through a production batch CAN be incorporated.

    Pre-#619 the seeded membership row alone refused this write forever, because `batch_district`
    rows are never deleted: the guard keyed on district IDENTITY, while every documented reason for
    it (injected reps, deliberately older school years, don't inflate coverage stats) is about the
    specific extraction. Nothing about this receipt's evidence is benchmark, so it writes."""
    _seed_benchmark_membership(env)
    _seed_rep(env, f"{env}:cleanrep", "cleanrep", "discovered")
    _patch_gov(monkeypatch, _ca_with_rep(env, rec_key=f"{env}:cleanrep"))

    res = INC.incorporate_district(env)
    assert res.status == "incorporated"
    assert {r["grade_level"]: r["minutes"] for r in _bell_rows(env)} == {"elementary": 420}


def test_benchmark_provenance_rep_refuses(env, monkeypatch):
    """ARM 2 (derived): an injected `gt://` rep among the write-bearing evidence refuses the write —
    with NO benchmark batch membership anywhere, which is what makes this provenance and not identity.

    This is the arm that covers the one real MIXED handoff (`f33790e63820`), a genuine production
    dispatch holding three curated-GT PDFs. Its 227 accepted facts were held back only by the
    district-keyed wall this issue retires; arm 2 is what keeps holding them."""
    _seed_rep(env, f"{env}:gtrep", "gtrep", BM.BENCHMARK_CAPTURE_SOURCE)
    _patch_gov(monkeypatch, _ca_with_rep(env, rec_key=f"{env}:gtrep"))

    res = INC.incorporate_district(env)
    assert res.status == "not_eligible" and "benchmark provenance" in res.reason
    assert _bell_rows(env) == [] and _grade_rows(env) == {}


def test_benchmark_dispatch_refuses_even_with_production_reps(env, monkeypatch):
    """ARM 1 (stamped): a fact produced against a `dispatch_type='benchmark'` handoff (#618) refuses
    the write even though its rep is an ordinary discovered capture.

    This is precisely the case arm 2 CANNOT see — a Council Lab A/B composed entirely of production
    reps carries no rep-level signal at all — which is why the guard has two arms and not one."""
    from infrastructure.acquisition.stage6_handoff import models as M6   # noqa: F401 (register)
    from infrastructure.acquisition.stage7_extract import models as M7   # noqa: F401 (register)
    _seed_rep(env, f"{env}:cleanrep2", "cleanrep2", "discovered")
    with gdb.session_scope() as gs:
        gdb.init_precious_schema()
        BSEED.seed_handoff(gs, "zzbench619", dispatch_type=BM.DISPATCH_BENCHMARK)
        eid = BSEED.seed_extraction(gs, "zzbench619", env)
        fid = BSEED.seed_fact(gs, eid, env, f"{env}:cleanrep2")

    ca = _ca_with_rep(env, rec_key=f"{env}:cleanrep2")
    ca["bands"]["elementary"]["schools"][0]["fact_id"] = fid
    _patch_gov(monkeypatch, ca)

    res = INC.incorporate_district(env)
    assert res.status == "not_eligible" and "benchmark provenance" in res.reason
    assert _bell_rows(env) == []


def test_a_struck_benchmark_school_does_not_refuse_the_write(env, monkeypatch):
    """The auditable ESCAPE HATCH, and why the wall can be ANY-of rather than a blunt district ban: a
    school the human struck at gate@8 (`band_exclusion`, #257) is applied BEFORE the mode, so it is
    not a source of the band's value and must not refuse the write on its behalf.

    This is the path a re-run district (#620) uses to shed injected evidence it no longer relies on —
    a recorded human decision, not a code exception. Same skip `collect_source_urls` makes (#632)."""
    _seed_rep(env, f"{env}:gtrep2", "gtrep2", BM.BENCHMARK_CAPTURE_SOURCE)
    _patch_gov(monkeypatch, _ca_with_rep(env, rec_key=f"{env}:gtrep2", excluded=True))

    res = INC.incorporate_district(env)
    assert res.status == "incorporated"


def test_legacy_row_collision_fails_loud(env, monkeypatch):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database import queries as Q
    # a hand-verified row already occupies (env, 2024-25, elementary) — the SAME key a council
    # write would land on (council resolves to its band_consensus year 2024-25)
    with lct_scope() as s:
        Q.add_bell_schedule(s, env, "2024-25", "elementary", 390, start_time="8:00 AM",
                            end_time="2:30 PM", method="human_provided", confidence="high",
                            notes="hand-verified from the district calendar", created_by="ian")
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}}))
    with pytest.raises(RuntimeError, match="refuses to overwrite non-Stage-9"):
        INC.incorporate_district(env)
    # NOTHING was written or overwritten — the human row is intact, no council rows, no grade rows
    rows = {r["grade_level"]: r for r in _bell_rows(env)}
    assert set(rows) == {"elementary"}
    assert rows["elementary"]["method"] == "human_provided" and rows["elementary"]["minutes"] == 390
    assert _grade_rows(env) == {}
    with gdb.session_scope() as gs:
        assert LEDGER.latest_incorporation(gs, env) is None


def test_legacy_collision_surfaced_in_dry_run(env, monkeypatch):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database import queries as Q
    with lct_scope() as s:
        Q.add_bell_schedule(s, env, "2024-25", "elementary", 390, method="human_provided",
                            created_by="ian")
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}}))
    res = INC.incorporate_district(env, dry_run=True)
    assert res.status == "dry_run" and "conflict" in (res.reason or "")
    assert any(c["existing_method"] == "human_provided" for c in res.conflicts)


def test_statutory_flip_clears_council_times(env, monkeypatch):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import BellSchedule
    from infrastructure.utilities.school_year import current_school_year

    def _elem_row():
        with lct_scope() as s:
            r = s.query(BellSchedule).filter(BellSchedule.district_id == env,
                                             BellSchedule.grade_level == "elementary").first()
            return {"method": r.method, "start_time": r.start_time, "end_time": r.end_time}

    cur = current_school_year()   # council's consensus year == current => v1/v2 share the key,
                                  # so the flip is an in-place UPDATE and the time-clear code fires
    # v1: council elementary with real times, at the CURRENT school year
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 420, "year": cur}}),
               approval_id=1)
    INC.incorporate_district(env)
    v1 = _elem_row()
    assert v1["method"] == "council_extraction" and v1["start_time"] == "08:00"
    # v2: elementary loses consensus -> statutory fallback (also at cur); stale times must clear
    _patch_gov(monkeypatch, _fake_ca(env, council={}, unsatisfied=["elementary"]), approval_id=2)
    INC.incorporate_district(env)
    row = _elem_row()
    assert row["method"] == "statutory_fallback"
    assert row["start_time"] is None and row["end_time"] is None


def test_toctou_decision_changed_between_reads_writes_nothing(env, monkeypatch):
    # eligibility gate sees 'approved', but the receipt fetch reads a NEWER 'sent_back' decision
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 420}}),
               approval_id=1, latest_disposition="sent_back", latest_approval_id=2)
    res = INC.incorporate_district(env)
    assert res.status == "not_eligible" and res.reason == "decision_changed_during_read"
    assert _bell_rows(env) == []
    with gdb.session_scope() as gs:
        assert LEDGER.latest_incorporation(gs, env) is None


def test_dry_run_resolves_statutory_minutes(env, monkeypatch):
    # dry-run must preview the RESOLVED statutory number, not literal None
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}}, unsatisfied=["high"]))
    res = INC.incorporate_district(env, dry_run=True)
    assert res.status == "dry_run" and _bell_rows(env) == []
    hi = next(w for w in res.written if w["grade_level"] == "high")
    assert hi["minutes"] == 350 and hi["method"] == "statutory_fallback"   # ZZ high, not None


def test_grade_minutes_verified_in_db(env, monkeypatch):
    # the projection table gets a Rule #6 verify too (happy path: rows match what was projected)
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}}))
    res = INC.incorporate_district(env)
    assert res.status == "incorporated" and res.grades == len(_grade_rows(env))


def test_statutory_minutes_case_insensitive_and_zero_safe(env):
    from infrastructure.acquisition.stage9_incorporate.incorporate import _statutory_minutes
    from infrastructure.database.connection import session_scope as lct_scope
    with lct_scope() as s:
        # lowercase state resolves via the canonical (uppercasing) lookup — PR #607 review
        assert _statutory_minutes(s, "zz", "high") == 350
        assert _statutory_minutes(s, "ZZ", "middle") == 330
        # an unknown state falls to the 360 default
        assert _statutory_minutes(s, "QQ", "high") == 360


def test_dry_run_flags_retraction(env, monkeypatch):
    # incorporate a district, then dry-run an EMPTY re-approval — the preview must warn that a
    # real run would RETRACT the prior bands (not silently look like a never-incorporated no_bands)
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}}))
    INC.incorporate_district(env)
    _patch_gov(monkeypatch, _fake_ca(env, council={}), approval_id=2)   # empty re-approval, new fp
    res = INC.incorporate_district(env, dry_run=True)
    assert res.status == "dry_run" and "RETRACT" in (res.reason or "")
    # dry-run wrote nothing: the prior rows are still present
    assert len(_bell_rows(env)) == 2
