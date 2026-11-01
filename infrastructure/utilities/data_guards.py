"""Guards for the two ingest failure shapes that printed a plausible number and exited 0.

S1 (#970): a source's own TOTAL row was summed in as a component (a 2.000× denominator), and a label
vocabulary that matched nothing in the file became an empty category instead of a parse error.
S2 (#972): a year-scoped selection matched zero rows and the run reported "Updated: 0" as success.

DB-free on purpose — importable by the migrations, the extract scripts and the measurement scripts
alike. Design + inventory: docs/technical-notes/production-quality-control-research/
2026-10-30-total-row-and-year-default-guards-plan.md
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Iterable, Sized
from decimal import InvalidOperation
from typing import NamedTuple


class DataGuardError(SystemExit):
    """A guard fired. Subclasses SystemExit so an unguarded CLI exits non-zero with the message,
    while tests can still catch it by type."""

    def __init__(self, message: str) -> None:
        super().__init__(f"DATA GUARD: {message}")
        self.message = message

    def __reduce__(self):
        # BaseException's default replays the already-prefixed args through __init__, which would
        # prefix again on every pickle/copy round trip (#994).
        return (type(self), (self.message,))


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
    max_disagree: int | None = None,
) -> TotalReconciliation:
    """Compare a sum we computed from component rows against the total the SOURCE itself publishes.

    Fails loud when the two disagree by more than `tolerance` (relative). Reports the exact-integer-
    multiple signature separately: `component_sum / reference_total` within 0.1% of an integer ≥ 2 is
    the fingerprint of "the total row was summed in with its own components" (#970 was 2.000×), which
    deserves a different message from a generic drift.

    `n_compared` / `n_disagree` are bookkeeping for per-entity reconciliations whose caller already
    counted row-level disagreements (e.g. per-LEA) and now checks the aggregate. `max_disagree`
    ENFORCES that count: a dropped or relabeled small category moves a few rows but not the aggregate
    (measured: dropping 'Grade 13' from the CCD mapping left the ratio at 0.99996 with 150 LEAs
    differing — #976), so the aggregate tolerance alone cannot see it.
    """
    if reference_total is None:
        raise DataGuardError(f"{label}: reference total is None; nothing to reconcile against")
    component_sum = _finite(component_sum, label=label, what="component sum")
    reference_total = _finite(reference_total, label=label, what="reference total")
    if reference_total <= 0:
        raise DataGuardError(f"{label}: reference total is {reference_total!r}; nothing to reconcile against")
    if max_disagree is not None and n_disagree > max_disagree:
        raise DataGuardError(
            f"{label}: {n_disagree:,} of {n_compared:,} rows disagree with the source's own per-row "
            f"total (cap {max_disagree}) — a category was dropped or relabeled; the aggregate tolerance "
            f"cannot see a small one (#976)"
        )
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


def _finite(value: object, *, label: str, what: str) -> float:
    """float(value), or a labelled guard failure. NaN fails `<= 0` and would fall through to round()
    (ValueError) or, without it, PASS the tolerance check; inf overflows; pd.NA raises TypeError —
    none of them may escape as anything an `except Exception` loader would swallow (#994)."""
    try:
        f = float(value)
    except (TypeError, ValueError, InvalidOperation):
        f = math.nan
    if not math.isfinite(f):
        raise DataGuardError(f"{label}: {what} is {value!r}, not a finite number")
    return f


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


def _resolve(available: object) -> object:
    return available() if callable(available) else available


def require_nonempty_selection(rows: Sized, *, what: str, available: object | Callable[[], object]) -> None:
    """A year-scoped (or otherwise keyed) selection that returns nothing is a wrong-key bug, not an
    empty workload. `available` says which keys the source DOES carry (a list of years, a dict per
    table) — it goes in the message so the fix is one edit away. Pass a CALLABLE when computing it
    costs a query: it is evaluated only on failure (#995)."""
    if not isinstance(rows, Sized):
        raise TypeError(f"require_nonempty_selection({what}) needs a sized collection, got "
                        f"{type(rows).__name__} — materialize it (list(...), .fetchall()) first")
    if len(rows) == 0:
        raise DataGuardError(f"{what}: selection matched 0 rows; available: {_resolve(available)!r}")


def require_year_carried(year: str, carried: Iterable[str] | Callable[[], Iterable[str]], *, what: str) -> None:
    """The declared `year` must be one the source carries — the membership form of
    require_nonempty_selection, so callers stop manufacturing a list to take its len() (#995)."""
    years = sorted(y for y in _resolve(carried) if y)
    if year not in years:
        raise DataGuardError(f"{what}: carries no rows for year={year}; available: {years!r}")
