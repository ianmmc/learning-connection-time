"""Guards for the two ingest failure shapes that printed a plausible number and exited 0.

S1 (#970): a source's own TOTAL row was summed in as a component (a 2.000× denominator), and a label
vocabulary that matched nothing in the file became an empty category instead of a parse error.
S2 (#972): a year-scoped selection matched zero rows and the run reported "Updated: 0" as success.

DB-free on purpose — importable by the migrations, the extract scripts and the measurement scripts
alike. Design + inventory: docs/technical-notes/production-quality-control-research/
2026-10-30-total-row-and-year-default-guards-plan.md
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sized
from typing import NamedTuple


class DataGuardError(SystemExit):
    """A guard fired. Subclasses SystemExit so an unguarded CLI exits non-zero with the message,
    while tests can still catch it by type."""

    def __init__(self, message: str) -> None:
        super().__init__(f"DATA GUARD: {message}")
        self.message = message


class TotalReconciliation(NamedTuple):
    """Receipt from reconcile_total — log it; a guard that leaves no trace is decoration (#793)."""
    label: str
    component_sum: float
    reference_total: float
    ratio: float
    n_compared: int
    n_disagree: int


def reconcile_total(
    component_sum: float,
    reference_total: float,
    *,
    label: str,
    tolerance: float = 0.005,
    n_compared: int = 1,
    n_disagree: int = 0,
) -> TotalReconciliation:
    """Compare a sum we computed from component rows against the total the SOURCE itself publishes.

    Fails loud when the two disagree by more than `tolerance` (relative). Reports the exact-integer-
    multiple signature separately: `component_sum / reference_total` within 0.1% of an integer ≥ 2 is
    the fingerprint of "the total row was summed in with its own components" (#970 was 2.000×), which
    deserves a different message from a generic drift.

    `n_compared` / `n_disagree` are pass-through bookkeeping for per-entity reconciliations whose
    caller already counted row-level disagreements (e.g. per-LEA) and now checks the aggregate.
    """
    if reference_total is None or reference_total <= 0:
        raise DataGuardError(f"{label}: reference total is {reference_total!r}; nothing to reconcile against")
    ratio = float(component_sum) / float(reference_total)
    receipt = TotalReconciliation(label, float(component_sum), float(reference_total), ratio,
                                  n_compared, n_disagree)
    nearest = round(ratio)
    if nearest >= 2 and abs(ratio - nearest) <= 0.001:
        raise DataGuardError(
            f"{label}: component sum is {ratio:.3f}× the source's own total "
            f"({component_sum:,.0f} vs {reference_total:,.0f}) — an exact integer multiple is the "
            f"signature of the total row being summed in as a component (#970)"
        )
    if abs(ratio - 1.0) > tolerance:
        raise DataGuardError(
            f"{label}: component sum {component_sum:,.0f} vs source total {reference_total:,.0f} "
            f"(ratio {ratio:.4f}) exceeds tolerance ±{tolerance:.2%}"
        )
    return receipt


def require_labels_seen(expected: Collection[str], seen: Iterable[str], *, label: str) -> None:
    """A category vocabulary the parser filters on must actually occur in the file. A member that is
    never seen is a spelling drift ('Separate School' vs 'Separate School, Age 6-21', #970) or a
    vintage relabel ('Ages 6-21' → 'School Age' in the 2024-25 IDEA files) — a parse error, never an
    empty category."""
    missing = sorted(set(expected) - set(seen))
    if missing:
        raise DataGuardError(
            f"{label}: {len(missing)} expected label(s) never seen in the source — {missing}. "
            f"The file's vocabulary has drifted from the parser's; fix the labels, do not ship zeros."
        )


def require_nonempty_selection(rows: Sized, *, what: str, available: object) -> None:
    """A year-scoped (or otherwise keyed) selection that returns nothing is a wrong-key bug, not an
    empty workload. `available` is whatever the caller can cheaply say about the keys the source DOES
    carry (a list of years, a dict per table) — it goes in the message so the fix is one edit away."""
    if len(rows) == 0:
        raise DataGuardError(f"{what}: selection matched 0 rows; available: {available!r}")
