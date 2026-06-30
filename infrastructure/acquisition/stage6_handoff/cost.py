"""Stage 6 cost estimator (REQ-101): price a representation's routing to a council.

A council call costs `Σ_voters(call) + escalation_rate × judge(call)` — the cascade shape (2 voters,
judge only on disagreement). Per-model rates come from the config-as-data `council_cost_model.json`,
which supports two shapes per model:
  * **token model** (size-scaled): `price_in/out_per_mtok` + `input_tokens_per_char`/`input_base_tokens`
    + `output_tokens_per_school`/`output_base_tokens` — the measured form `cost_benchmark.py` fits;
  * **flat**: `per_call_usd` — the shipped bootstrap form (prior measurement, no size scaling).

Pure: dicts in, numbers out. No DB, no other-stage imports, no network. Imports only `common`.
The cost model's `provenance` ("bootstrap" | "measured") rides through so callers can label estimates.
"""
from infrastructure.acquisition.common import config_loader

KNOB = "council_cost_model"


class CostModelError(ValueError):
    """The cost model lacks rates for a requested model (or is malformed)."""


def load_cost_model() -> dict:
    """The shipped cost model document (bootstrap until `cost_benchmark.py` rewrites it as measured)."""
    return config_loader.load(KNOB)


def _n_schools(rep: dict) -> float:
    """Per-page school count for output-token scaling — explicit `n_schools`, else `n_times` as a proxy."""
    rep = rep or {}
    v = rep.get("n_schools")
    if v is None:
        v = rep.get("n_times")
    return float(v or 0)


def estimate_call_cost(model_id: str, rep: dict, cost_model: dict) -> float:
    """The $ for ONE model reading ONE representation. Token model if present (size-scaled), else flat."""
    m = (cost_model.get("models") or {}).get(model_id)
    if m is None:
        raise CostModelError(f"cost model has no rates for '{model_id}'")
    if "per_call_usd" in m:
        return float(m["per_call_usd"])
    # size-scaled token model
    in_tok = float(m.get("input_base_tokens", 0)) + float(m.get("input_tokens_per_char", 0)) * float((rep or {}).get("n_chars", 0) or 0)
    out_tok = float(m.get("output_base_tokens", 0)) + float(m.get("output_tokens_per_school", 0)) * _n_schools(rep)
    return in_tok / 1e6 * float(m["price_in_per_mtok"]) + out_tok / 1e6 * float(m["price_out_per_mtok"])


def estimate_council_cost(rep: dict, council: dict, cost_model: dict) -> float:
    """The $ for routing one rep to one council: both voters + escalation_rate × the judge."""
    esc = float((cost_model.get("assumptions") or {}).get("escalation_rate", 1.0))
    voters = sum(estimate_call_cost(v, rep, cost_model) for v in council["voters"])
    judge = estimate_call_cost(council["judge"], rep, cost_model)
    return voters + esc * judge


def estimate_handoff_cost(items, cost_model: dict) -> dict:
    """Total estimate over a handoff's (rep, council) items. Returns {total_usd, n_items, provenance}."""
    items = list(items)
    total = sum(estimate_council_cost(rep, council, cost_model) for rep, council in items)
    return {"total_usd": total, "n_items": len(items),
            "provenance": cost_model.get("provenance", "unknown")}
