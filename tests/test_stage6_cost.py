"""Stage 6 cost estimator (REQ-101, slice 3).

Estimates the OpenRouter $ for routing a representation to a council: per-model call cost summed over
the 2 voters + (escalation_rate × judge). Reads a config-as-data cost model (`council_cost_model.json`)
that ships as a clearly-labeled BOOTSTRAP (flat per-call costs from prior measurement) and is later
replaced by the size-scaled token model that `cost_benchmark.py` fits on current clean reps
(STAGE6_HANDOFF_DESIGN §3C). Pure (dicts in, numbers out) — no DB, no stage imports, no network.
"""
import math

import pytest

from infrastructure.acquisition.stage6_handoff import cost

CANDIDATE_6 = {
    "google/gemini-2.5-flash", "google/gemini-2.5-flash-lite",
    "mistralai/mistral-small-24b-instruct-2501", "mistralai/mistral-large-2512",
    "deepseek/deepseek-v3.2", "qwen/qwen3-235b-a22b-2507",
}

# A synthetic MEASURED cost model exercising the size-scaled token path (independent of the shipped file).
MEASURED = {
    "provenance": "measured",
    "assumptions": {"escalation_rate": 0.5},
    "models": {
        "fam-a/v1": {"price_in_per_mtok": 1.0, "price_out_per_mtok": 2.0,
                     "input_tokens_per_char": 0.25, "input_base_tokens": 100,
                     "output_tokens_per_school": 20, "output_base_tokens": 10},
        "fam-b/v1": {"per_call_usd": 0.001},   # mixed: this model still flat
        "fam-c/v1": {"price_in_per_mtok": 1.0, "price_out_per_mtok": 1.0,
                     "input_tokens_per_char": 0.0, "input_base_tokens": 0,
                     "output_tokens_per_school": 0, "output_base_tokens": 0},
    },
}


# --------------------------- the shipped bootstrap ---------------------------
def test_bootstrap_loads_and_covers_candidate_6():
    cm = cost.load_cost_model()
    assert cm["provenance"] == "bootstrap"        # honestly labeled until measured
    assert CANDIDATE_6 <= set(cm["models"])
    assert "escalation_rate" in cm["assumptions"]


def test_bootstrap_call_cost_is_the_flat_per_call_value():
    cm = cost.load_cost_model()
    # bootstrap entries are flat per_call_usd; rep size is ignored on the flat path
    c = cost.estimate_call_cost("mistralai/mistral-small-24b-instruct-2501", {"n_chars": 9999}, cm)
    assert c == cm["models"]["mistralai/mistral-small-24b-instruct-2501"]["per_call_usd"]


# --------------------------- the measured token path ---------------------------
def test_measured_token_cost_is_size_scaled():
    rep = {"n_chars": 1000, "n_times": 5}
    # in = 100 + 0.25*1000 = 350 tok -> 350e-6 * 1.0 ; out = 10 + 20*5 = 110 tok -> 110e-6 * 2.0
    c = cost.estimate_call_cost("fam-a/v1", rep, MEASURED)
    assert math.isclose(c, (350 * 1.0 + 110 * 2.0) / 1e6, rel_tol=1e-9)


def test_measured_model_can_still_be_flat():
    c = cost.estimate_call_cost("fam-b/v1", {"n_chars": 5000}, MEASURED)
    assert c == 0.001


def test_school_count_uses_n_schools_then_n_times():
    cm = MEASURED
    # fam-a input_base_tokens=100 -> in=100 tok even at n_chars=0; out=10+20*3=70 tok
    expected = (100 * 1.0 + (10 + 20 * 3) * 2.0) / 1e6
    assert math.isclose(cost.estimate_call_cost("fam-a/v1", {"n_chars": 0, "n_schools": 3}, cm), expected, rel_tol=1e-9)
    # falls back to n_times when n_schools absent
    assert math.isclose(cost.estimate_call_cost("fam-a/v1", {"n_chars": 0, "n_times": 3}, cm), expected, rel_tol=1e-9)


# --------------------------- council + handoff rollups ---------------------------
def test_council_cost_is_voters_plus_escalation_times_judge():
    council = {"id": "c", "voters": ["fam-b/v1", "fam-c/v1"], "judge": "fam-b/v1"}
    rep = {"n_chars": 0, "n_times": 0}
    # voters: 0.001 + 0.0 ; judge fam-b flat 0.001 ; escalation 0.5 -> + 0.0005
    c = cost.estimate_council_cost(rep, council, MEASURED)
    assert math.isclose(c, 0.001 + 0.0 + 0.5 * 0.001, rel_tol=1e-9)


def test_unknown_model_raises():
    with pytest.raises(cost.CostModelError, match="no-such"):
        cost.estimate_call_cost("no-such/model", {"n_chars": 10}, MEASURED)


def test_missing_escalation_rate_raises():
    # a malformed cost model (no assumptions.escalation_rate) must NOT silently default — a wrong rate
    # mis-states the $ at the gate@6 spend gate.
    council = {"voters": ["fam-b/v1", "fam-c/v1"], "judge": "fam-b/v1"}
    no_esc = {"provenance": "measured", "assumptions": {}, "models": MEASURED["models"]}
    with pytest.raises(cost.CostModelError, match="escalation_rate"):
        cost.estimate_council_cost({"n_chars": 0}, council, no_esc)


def test_measured_path_uses_default_n_schools_when_count_missing():
    # a rep with neither n_schools nor n_times falls back to the configured floor (1), not 0 — so output
    # is never silently priced as pure base on the measured token path.
    c = cost.estimate_call_cost("fam-a/v1", {"n_chars": 0}, MEASURED)   # in=100, out=10+20*1=30
    assert math.isclose(c, (100 * 1.0 + 30 * 2.0) / 1e6, rel_tol=1e-9)
