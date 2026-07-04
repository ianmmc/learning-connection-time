"""REQ-051 budget governor — bound OpenRouter spend per-district and globally, resumably.

Pure accounting over config-as-data caps; NO DB/network (the `common` layer imports nothing above
it). The caller (the Stage-7 executor, the request-execution back-edges) seeds a governor from
DURABLE recorded spend — `SUM(extraction.cost_usd)` for the handoff — so a resumed run continues
under the SAME ceiling rather than starting the count over, then consults the governor before each
paid unit of work and records the actuals after. This split keeps the money math testable in
isolation and puts the (mockable) DB seed + estimate in the app layer.

Three caps, all optional (None ⇒ that dimension is unbounded — the governor is a no-op there):
  * ``per_run_usd``        — a global run ceiling; breach ⇒ the run HALTS (governance §11b: auto
                             through the paid stages is cost-gated).
  * ``per_district_usd``   — a per-district ceiling; breach ⇒ that district is SKIPPED, the run
                             continues (one hard district must not consume the whole budget).
  * ``max_request_rounds`` — the request-more-evidence depth guard (STAGE7 §3F): the max re-request
                             rounds a district×band may fire, so the 7→6/3/2/1 loop provably
                             terminates and never re-extracts unbounded.

Caps ship as a BOOTSTRAP knob (`common/config/budget.json`) tuned up/down under the ramp-up model.
"""
from __future__ import annotations

from dataclasses import dataclass

from infrastructure.acquisition.common import config_loader


@dataclass(frozen=True)
class Budget:
    """The caps, resolved from the `budget` knob. A None field is an unbounded dimension."""
    per_district_usd: float | None = None
    per_run_usd: float | None = None
    max_request_rounds: int | None = None


def load_budget() -> Budget:
    """Resolve the live caps from the config-as-data `budget` knob (`common/config/budget.json`)."""
    caps = config_loader.load("budget").get("caps", {})
    pd = caps.get("per_district_usd")
    pr = caps.get("per_run_usd")
    rounds = caps.get("max_request_rounds")
    return Budget(
        per_district_usd=None if pd is None else float(pd),
        per_run_usd=None if pr is None else float(pr),
        max_request_rounds=None if rounds is None else int(rounds),
    )


class BudgetGovernor:
    """A running spend accountant against a `Budget`. Seed `run_spent`/`district_spent` from durable
    recorded spend for resume; query `*_would_exceed(est)` before spending; `record()` the actuals
    after. Pure and side-effect-free apart from its own running totals."""

    def __init__(self, budget: Budget, *, run_spent: float = 0.0, district_spent: dict | None = None):
        self.budget = budget
        self.run_spent = float(run_spent or 0.0)
        self.district_spent: dict = {k: float(v) for k, v in (district_spent or {}).items()}

    # -- queries (pure; `est` = the projected ADDITIONAL spend, default 0 ⇒ check already-spent) --
    def run_would_exceed(self, est: float = 0.0) -> bool:
        cap = self.budget.per_run_usd
        return cap is not None and (self.run_spent + max(0.0, est)) > cap

    def district_would_exceed(self, district_id: str, est: float = 0.0) -> bool:
        cap = self.budget.per_district_usd
        if cap is None:
            return False
        return (self.district_spent.get(district_id, 0.0) + max(0.0, est)) > cap

    def rounds_exhausted(self, rounds_used: int) -> bool:
        """The depth guard: True once a district×band has already fired `max_request_rounds` rounds."""
        cap = self.budget.max_request_rounds
        return cap is not None and rounds_used >= cap

    # -- mutation --
    def record(self, district_id: str, cost_usd) -> None:
        c = max(0.0, float(cost_usd or 0.0))   # None (no usage.cost) ⇒ 0; never credit the budget
        self.run_spent += c
        self.district_spent[district_id] = self.district_spent.get(district_id, 0.0) + c

    def remaining_run(self) -> float | None:
        cap = self.budget.per_run_usd
        return None if cap is None else max(0.0, cap - self.run_spent)
