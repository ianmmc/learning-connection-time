"""REQ-121 / issue #210 — the gate-decision calibration log (the certifiable shadow-mode meter).

Pure record-building + agreement + the post-hoc θ-sweep tested on synthetic inputs; the writer + precious
table tested against the governance Postgres via the rolling-back gov_session fixture. This is ONLY the
instrument — θ selection / auto-policy are non-goals (deferred, governance-blocked)."""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import calibration as CAL  # noqa: E402

govdb = pytest.mark.govdb


# ----------------------------- decision vocabulary -----------------------------
def test_normalize_decision_maps_console_synonyms_and_rejects_unknown():
    assert CAL.normalize_decision("Approved") == "accept"
    assert CAL.normalize_decision("suppress") == "reject"
    assert CAL.normalize_decision("hold") == "escalate"
    assert CAL.normalize_decision("edited") == "modified"
    assert CAL.normalize_decision("  SEND ") == "accept"
    assert CAL.normalize_decision("banana") is None        # unknown -> None, never guessed
    assert CAL.normalize_decision(None) is None


# ----------------------------- agreement (only in the unilateral-auto region) -----------------------------
def test_agreement_defined_only_where_auto_would_act_unilaterally():
    assert CAL.agreement("accept", "accept") is True
    assert CAL.agreement("reject", "reject") is True
    assert CAL.agreement("reject", "accept") is False
    assert CAL.agreement("accept", "reject") is False
    # 'modified' = accepted but auto's output was wrong -> disagreement with a unilateral auto-accept
    assert CAL.agreement("modified", "accept") is False
    # auto would ESCALATE (defer to human) -> not a unilateral-auto data point -> None
    assert CAL.agreement("accept", "escalate") is None
    assert CAL.agreement("reject", None) is None
    assert CAL.agreement("accept", "banana") is None       # unknown auto rec -> None


# ----------------------------- build_record -----------------------------
def test_build_record_carries_proxy_slices_and_computes_agreed():
    rec = CAL.build_record(
        "gate@5", "d1:rk1", district_id="d1", proxy_name="sort_score", proxy_value=0.82,
        human_decision="approve", auto_recommendation="accept",
        slices={"state": "WI", "capture_path": "text", "school_level": "HS", "ignored": "x"},
        blinded=False, created_at="2026-07-10T00:00:00Z")
    assert rec["proxy_value"] == 0.82 and rec["proxy_name"] == "sort_score"
    assert rec["human_decision"] == "accept" and rec["auto_recommendation"] == "accept"
    assert rec["agreed"] is True
    assert rec["state"] == "WI" and rec["capture_path"] == "text" and rec["school_level"] == "HS"
    assert rec["batch_type"] is None and rec["run_kind"] is None    # missing slices -> None
    assert "ignored" not in rec                                     # unknown slice key dropped


def test_build_record_preserves_an_unknown_raw_decision_rather_than_dropping_it():
    # a decision the vocab doesn't recognize is logged verbatim (never silently nulled) so no signal is lost.
    rec = CAL.build_record("gate@7", "x", proxy_name="council_agreement", proxy_value=None,
                           human_decision="quibble", created_at="t")
    assert rec["human_decision"] == "quibble" and rec["agreed"] is None


# ----------------------------- the post-hoc θ-sweep the schema must enable -----------------------------
def _rows():
    # continuous proxy + human decision; the log is enough to replay any θ post-hoc.
    return [
        {"proxy_value": 0.9, "human_decision": "accept", "state": "WI"},   # high & accepted
        {"proxy_value": 0.8, "human_decision": "accept", "state": "WI"},
        {"proxy_value": 0.6, "human_decision": "reject", "state": "CA"},   # mid & rejected
        {"proxy_value": 0.3, "human_decision": "reject", "state": "CA"},   # low & rejected
        {"proxy_value": None, "human_decision": "accept", "state": "CA"},  # unplaceable -> skipped
    ]


def test_sweep_replays_thresholds_and_reports_error_rate():
    sweep = CAL.sweep_worst_slice(_rows(), thetas=[0.5, 0.7], direction="high_accept")
    at05 = next(s for s in sweep if s["theta"] == 0.5)
    # θ=0.5: auto-accepts 0.9/0.8/0.6, rejects 0.3. Humans: accept/accept/reject/reject.
    # the 0.6 row (auto-accept, human-reject) is the one error -> 1/4.
    assert at05["n"] == 4 and at05["errors"] == 1 and at05["error_rate"] == 0.25
    at07 = next(s for s in sweep if s["theta"] == 0.7)
    # θ=0.7: auto-accepts 0.9/0.8, rejects 0.6/0.3 -> matches all humans -> 0 errors.
    assert at07["errors"] == 0 and at07["error_rate"] == 0.0


def test_sweep_reports_the_worst_slice():
    sweep = CAL.sweep_worst_slice(_rows(), thetas=[0.5], direction="high_accept", slice_key="state")
    worst = sweep[0]["worst_slice"]
    # at θ=0.5 the only error is the CA 0.6 row -> CA is the worst slice (1/2 vs WI 0/2).
    assert worst["value"] == "CA" and worst["errors"] == 1 and worst["n"] == 2 and worst["error_rate"] == 0.5


def test_sweep_empty_is_safe():
    assert CAL.sweep_worst_slice([], thetas=[0.5]) == [{"theta": 0.5, "n": 0, "errors": 0,
                                                        "error_rate": None, "worst_slice": None}]


# ----------------------------- writer + precious table (governance Postgres) -----------------------------
@govdb
def test_record_calibration_persists_and_the_table_is_precious(gov_session):
    # the precious table is created from the model via init_precious_schema (CalibrationEvent registered on
    # gdb.Base by importing this module); here we create it on the connection-scoped session and round-trip.
    gov_session.execute(text("""CREATE TEMP TABLE calibration_event (
        event_id serial PRIMARY KEY, gate text, item_id text, district_id text, proxy_name text,
        proxy_value double precision, human_decision text, auto_recommendation text, agreed boolean,
        blinded boolean, state text, capture_path text, batch_type text, run_kind text, school_level text,
        created_at text)"""))
    rec = CAL.build_record("gate@5", "d1:rk1", district_id="d1", proxy_name="sort_score", proxy_value=0.82,
                           human_decision="accept", auto_recommendation="accept",
                           slices={"state": "WI", "capture_path": "text"}, created_at="2026-07-10T00:00:00Z")
    CAL.record_calibration(gov_session, rec)
    row = gov_session.execute(text(
        "SELECT gate, proxy_value, human_decision, agreed, state FROM calibration_event")).mappings().one()
    assert row["gate"] == "gate@5" and row["proxy_value"] == 0.82
    assert row["human_decision"] == "accept" and row["agreed"] is True and row["state"] == "WI"
