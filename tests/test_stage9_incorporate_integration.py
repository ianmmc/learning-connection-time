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
from infrastructure.acquisition.stage8_aggregate import approval as APV
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA
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
def env():
    """Seed a synthetic LCT district (+ its state statutory row), yield its id, clean both DBs."""
    _require_dbs()
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


# ----------------------------- PR #607 review fixes -----------------------------
def test_benchmark_district_refused(env, monkeypatch):
    # A batch_00000-style benchmark membership walls the district off from Stage-9 writes.
    with gdb.session_scope() as gs:
        gs.execute(text(
            "INSERT INTO batch (batch_id, batch_type, status, nces_year, created_at, created_by, "
            "meta_json) VALUES ('zz_bench_test', 'benchmark', 'approved', '2024-25', 'now', "
            "'zz-test', '{}') ON CONFLICT (batch_id) DO NOTHING"))
        gs.execute(text(
            "INSERT INTO batch_district (batch_id, district_id, ord, name, state, domain, "
            "lea_claimed_bands, nces_school_counts, band_processing_order, band_meta, included) "
            "VALUES ('zz_bench_test', :d, 0, 'Stage9 Test', 'ZZ', 'zz.test', '[]', '{}', '[]', "
            "'{}', true)"), {"d": env})
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 420}}))
    res = INC.incorporate_district(env)
    assert res.status == "not_eligible" and "benchmark" in res.reason
    assert _bell_rows(env) == [] and _grade_rows(env) == {}


def test_legacy_human_row_protected(env, monkeypatch):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database import queries as Q
    # a hand-verified row already occupies (env, 2024-25, elementary)
    with lct_scope() as s:
        Q.add_bell_schedule(s, env, "2024-25", "elementary", 390, start_time="8:00 AM",
                            end_time="2:30 PM", method="human_provided", confidence="high",
                            notes="hand-verified from the district calendar", created_by="ian")
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 400}, "high": {"gross": 450}}))
    res = INC.incorporate_district(env)
    assert res.status == "incorporated"
    rows = {r["grade_level"]: r for r in _bell_rows(env)}
    # the human row is untouched (method + minutes preserved), the council high still lands
    assert rows["elementary"]["method"] == "human_provided" and rows["elementary"]["minutes"] == 390
    assert rows["high"]["method"] == "council_extraction"
    assert any(p["grade_level"] == "elementary" and p["existing_method"] == "human_provided"
               for p in res.protected)
    # the protected band contributes NO Stage-9 grade-minutes rows
    assert "03" not in _grade_rows(env) and "10" in _grade_rows(env)


def test_statutory_flip_clears_council_times(env, monkeypatch):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import BellSchedule

    def _elem_row():
        with lct_scope() as s:
            r = s.query(BellSchedule).filter(BellSchedule.district_id == env,
                                             BellSchedule.grade_level == "elementary").first()
            return {"method": r.method, "start_time": r.start_time, "end_time": r.end_time}

    # v1: council elementary with real times
    _patch_gov(monkeypatch, _fake_ca(env, council={"elementary": {"gross": 420}}), approval_id=1)
    INC.incorporate_district(env)
    assert _elem_row()["start_time"] == "08:00"
    # v2: elementary loses consensus -> statutory fallback; stale council times must be cleared
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
