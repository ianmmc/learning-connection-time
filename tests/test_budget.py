"""REQ-051 budget governor (common/budget.py) — pure accounting + config-as-data caps, no DB/network.
Bounds OpenRouter spend per-district and globally and the request-loop depth; seeded from durable
recorded spend so a resumed run continues under the same ceiling. Enforced in the Stage-7 executor
and the request-execution back-edges."""
from infrastructure.acquisition.common import budget as BUD


def _b(per_district=None, per_run=None, rounds=None):
    return BUD.Budget(per_district_usd=per_district, per_run_usd=per_run, max_request_rounds=rounds)


def test_record_accumulates_run_and_per_district():
    g = BUD.BudgetGovernor(_b())
    g.record("D1", 0.01)
    g.record("D1", 0.02)
    g.record("D2", 0.05)
    assert round(g.run_spent, 4) == 0.08
    assert round(g.district_spent["D1"], 4) == 0.03
    assert round(g.district_spent["D2"], 4) == 0.05


def test_seed_from_durable_spend():
    # a resumed run seeds prior spend so it continues under the SAME ceiling
    g = BUD.BudgetGovernor(_b(per_run=1.0), run_spent=0.9, district_spent={"D1": 0.4})
    assert g.run_spent == 0.9
    assert g.district_spent["D1"] == 0.4


def test_run_cap_would_exceed_with_estimate():
    g = BUD.BudgetGovernor(_b(per_run=1.0), run_spent=0.9)
    assert g.run_would_exceed(0.2) is True     # 0.9 + 0.2 > 1.0
    assert g.run_would_exceed(0.05) is False    # 0.9 + 0.05 <= 1.0


def test_run_cap_already_over_halts_with_no_estimate():
    g = BUD.BudgetGovernor(_b(per_run=1.0), run_spent=1.5)
    assert g.run_would_exceed() is True         # already over, est defaults to 0


def test_district_cap_independent_of_run():
    g = BUD.BudgetGovernor(_b(per_district=0.10), district_spent={"D1": 0.09})
    assert g.district_would_exceed("D1", 0.02) is True
    assert g.district_would_exceed("D1", 0.005) is False
    assert g.district_would_exceed("D2", 0.5) is True    # a fresh district, est alone over cap
    assert g.district_would_exceed("D9") is False        # unseen district, no est


def test_none_caps_never_block():
    g = BUD.BudgetGovernor(_b())   # all caps None (governor disabled)
    g.record("D1", 999.0)
    assert g.run_would_exceed(999.0) is False
    assert g.district_would_exceed("D1", 999.0) is False
    assert g.rounds_exhausted(999) is False


def test_rounds_exhausted_depth_guard():
    g = BUD.BudgetGovernor(_b(rounds=2))
    assert g.rounds_exhausted(0) is False
    assert g.rounds_exhausted(1) is False
    assert g.rounds_exhausted(2) is True       # cap reached -> no further request rounds
    assert g.rounds_exhausted(3) is True


def test_remaining_run():
    assert BUD.BudgetGovernor(_b(per_run=1.0), run_spent=0.3).remaining_run() == 0.7
    assert BUD.BudgetGovernor(_b(per_run=1.0), run_spent=1.5).remaining_run() == 0.0   # clamped >=0
    assert BUD.BudgetGovernor(_b()).remaining_run() is None                            # no cap


def test_record_coerces_none_and_negatives():
    g = BUD.BudgetGovernor(_b())
    g.record("D1", None)      # a call with no usage.cost -> treated as 0
    g.record("D1", -0.5)      # never credit the budget
    assert g.run_spent == 0.0


def test_load_budget_reads_the_knob():
    b = BUD.load_budget()      # the shipped common/config/budget.json
    assert b.per_run_usd is not None and b.per_run_usd > 0
    assert b.per_district_usd is not None and b.per_district_usd > 0
    assert b.max_request_rounds is not None and b.max_request_rounds >= 1
