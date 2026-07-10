"""REQ-121 / issue #210 — the gate-decision calibration log (the certifiable shadow-mode meter).

Pure record-building + agreement + the post-hoc θ-sweep tested on synthetic inputs; the writer + precious
table tested against the governance Postgres via the rolling-back gov_session fixture. This is ONLY the
instrument — θ selection / auto-policy are non-goals (deferred, governance-blocked)."""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import calibration as CAL  # noqa: E402
from infrastructure.acquisition.common import db as gdb  # noqa: E402

govdb = pytest.mark.govdb


# ----------------------------- decision vocabulary (role-scoped) -----------------------------
def test_normalize_decision_is_case_insensitive_and_role_scoped():
    assert CAL.normalize_decision("Accept") == "accept"
    assert CAL.normalize_decision("  REJECT ") == "reject"
    assert CAL.normalize_decision("banana") is None         # unknown -> None, never guessed
    assert CAL.normalize_decision(None) is None
    # #217 review: role-scoped membership — 'escalate' is auto-only, 'modified' human-only. The union
    # check used to accept both cross-role, silently corrupting agreement()'s semantics.
    assert CAL.normalize_decision("escalate", role="human") is None
    assert CAL.normalize_decision("escalate", role="auto") == "escalate"
    assert CAL.normalize_decision("modified", role="auto") is None
    assert CAL.normalize_decision("modified", role="human") == "modified"


def test_console_synonyms_are_not_this_layers_job():
    # #217 review: UI wording ("approved"/"send"/"hold") is translated at the WIRING layer
    # (process_governance), never in common/ — a synonym map here is app vocabulary leaking below the
    # layering boundary, drifting silently when a button is relabeled.
    for ui_word in ("approved", "send", "hold", "suppress", "edited"):
        assert CAL.normalize_decision(ui_word) is None


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
    assert CAL.agreement("escalate", "accept") is None     # role-invalid human value -> None, not a match


# ----------------------------- build_record -----------------------------
def test_build_record_carries_proxy_slices_and_computes_agreed():
    rec = CAL.build_record(
        "gate@5", "d1:rk1", district_id="d1", proxy_name="sort_score", proxy_value=0.82,
        human_decision="Accept", auto_recommendation="accept",
        slices={"state": "WI", "capture_path": "text", "school_level": "HS", "ignored": "x"},
        blinded=False, created_at="2026-07-10T00:00:00Z")
    assert rec["proxy_value"] == 0.82 and rec["proxy_name"] == "sort_score"
    assert rec["human_decision"] == "accept" and rec["auto_recommendation"] == "accept"
    assert rec["agreed"] is True
    assert rec["state"] == "WI" and rec["capture_path"] == "text" and rec["school_level"] == "HS"
    assert rec["batch_type"] is None and rec["run_kind"] is None    # missing slices -> None
    assert "ignored" not in rec                                     # unknown slice key dropped


def test_build_record_preserves_unknown_raw_strings_symmetrically():
    # #217 review: BOTH sides preserve an unrecognized value verbatim. The auto side used to collapse to
    # None — a typo'd/renamed recommendation became indistinguishable from 'auto never weighed in'.
    rec = CAL.build_record("gate@7", "x", proxy_name="council_agreement", proxy_value=None,
                           human_decision="quibble", auto_recommendation="banana", created_at="t")
    assert rec["human_decision"] == "quibble"
    assert rec["auto_recommendation"] == "banana"
    assert rec["agreed"] is None
    # absent auto recommendation is still a real NULL, distinct from a preserved unknown string
    rec2 = CAL.build_record("gate@7", "x", proxy_name="p", proxy_value=None,
                            human_decision="accept", created_at="t")
    assert rec2["auto_recommendation"] is None


def test_build_record_requires_a_human_decision():
    # #217 review: `None or str(None)` used to smuggle the literal string 'None' past NOT NULL as fake
    # data. The ground-truth label is the point of the record — a missing one is a caller bug, loudly.
    with pytest.raises(ValueError, match="human_decision"):
        CAL.build_record("gate@5", "x", proxy_name="p", proxy_value=0.5,
                         human_decision=None, created_at="t")


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


def test_sweep_low_accept_serves_the_lower_is_better_proxies():
    # REQ-121 lists gate@7's n_unresolved — a LOWER-is-more-confident proxy — so low_accept is a needed
    # branch, not speculation; it just must be tested (#217 review). n_unresolved 0/1 -> accepted by the
    # human; 5/9 -> rejected. θ=2 under low_accept reproduces the humans exactly.
    rows = [
        {"proxy_value": 0.0, "human_decision": "accept"},
        {"proxy_value": 1.0, "human_decision": "accept"},
        {"proxy_value": 5.0, "human_decision": "reject"},
        {"proxy_value": 9.0, "human_decision": "reject"},
    ]
    sweep = CAL.sweep_worst_slice(rows, thetas=[2.0], direction="low_accept")
    assert sweep[0]["errors"] == 0 and sweep[0]["error_rate"] == 0.0


def test_sweep_rejects_an_unknown_direction():
    # #217 review: a one-character typo used to fall silently into the low_accept branch and INVERT the
    # certification read (0.0 -> 1.0 on identical data). Must be a loud error in autonomy-licensing math.
    with pytest.raises(ValueError, match="direction"):
        CAL.sweep_worst_slice(_rows(), thetas=[0.5], direction="High_Accept")


def test_sweep_reports_the_worst_slice():
    sweep = CAL.sweep_worst_slice(_rows(), thetas=[0.5], direction="high_accept", slice_key="state")
    worst = sweep[0]["worst_slice"]
    # at θ=0.5 the only error is the CA 0.6 row -> CA is the worst slice (1/2 vs WI 0/2).
    assert worst["value"] == "CA" and worst["errors"] == 1 and worst["n"] == 2 and worst["error_rate"] == 0.5


def test_sweep_empty_is_safe():
    assert CAL.sweep_worst_slice([], thetas=[0.5]) == [{"theta": 0.5, "n": 0, "errors": 0,
                                                        "error_rate": None, "worst_slice": None}]


# ----------------------------- registration + writer + the REAL table DDL -----------------------------
def test_calibration_event_registers_on_base_metadata():
    # #217 review: the table must be creatable by init_precious_schema without any caller remembering a
    # registration import — db.init_precious_schema now imports this module itself; here we pin the model
    # side: importing calibration registers the table, and human_decision is NOT NULL on the real model.
    assert "calibration_event" in gdb.Base.metadata.tables
    col = CAL.CalibrationEvent.__table__.c.human_decision
    assert col.nullable is False
    assert CAL.CalibrationEvent.__table__.c.blinded.server_default is not None


@govdb
def test_record_calibration_persists_via_the_real_model_ddl(gov_session):
    # #217 review: exercise the REAL model DDL (not a permissive hand-rolled schema), so NOT NULL /
    # server_default drift on the model is caught here. checkfirst: init_precious_schema (or a prior
    # run) may already have created the precious table; the insert rolls back with the fixture either way.
    CAL.CalibrationEvent.__table__.create(bind=gov_session.connection(), checkfirst=True)
    rec = CAL.build_record("gate@5", "test:217:rk1", district_id="d1", proxy_name="sort_score",
                           proxy_value=0.82, human_decision="accept", auto_recommendation="accept",
                           slices={"state": "WI", "capture_path": "text"}, created_at="2026-07-10T00:00:00Z")
    CAL.record_calibration(gov_session, rec)
    row = gov_session.execute(text(
        """SELECT gate, proxy_value, human_decision, agreed, state FROM calibration_event
           WHERE item_id = 'test:217:rk1'""")).mappings().one()
    assert row["gate"] == "gate@5" and row["proxy_value"] == 0.82
    assert row["human_decision"] == "accept" and row["agreed"] is True and row["state"] == "WI"


@govdb
def test_human_decision_not_null_is_enforced_by_the_real_ddl(gov_session):
    # the NOT NULL constraint is load-bearing (the corpus must never hold a null ground-truth label);
    # exercised against the real DDL under a savepoint so the outer transaction stays usable.
    from sqlalchemy.exc import IntegrityError
    CAL.CalibrationEvent.__table__.create(bind=gov_session.connection(), checkfirst=True)
    rec = CAL.build_record("gate@5", "test:217:rk2", proxy_name="p", proxy_value=0.5,
                           human_decision="accept", created_at="t")
    rec["human_decision"] = None                       # bypass build_record's guard to hit the DB's own
    nested = gov_session.begin_nested()
    with pytest.raises(IntegrityError):
        gov_session.execute(CAL._INSERT, rec)
        nested.commit()
    nested.rollback()
