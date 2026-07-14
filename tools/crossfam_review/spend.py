"""A thread-safe hard-cap spend guard for the paid run.

Commandment #3 (tight cash spend) made concrete: the run must be physically incapable of blowing past
the cap even if a model reprices, a loop misbehaves, or many calls run concurrently. The guard is
reserve-then-settle: before a call, `reserve(estimate)` atomically checks the estimate against the
remaining cap and refuses if it wouldn't fit; after the call, `settle(estimate, actual)` swaps the
estimate for OpenRouter's real billed cost. Refused calls raise `BudgetExceeded`, which the
orchestrator catches to stop dispatching new work (in-flight calls still settle their real cost).

Reservations make the guard conservative under concurrency: N workers can't each independently decide
they fit and collectively overshoot, because each reservation is subtracted from the shared remaining
budget the instant it's granted — the classic check-then-act race that a bare "is total < cap?" test
would have. Actual bills replace estimates on settle, so a run of cheaper-than-estimated calls
reclaims headroom for later ones.
"""
from __future__ import annotations

import threading


class BudgetExceeded(RuntimeError):
    """A reservation was refused because it wouldn't fit under the cap. The run should stop dispatching."""


class SpendGuard:
    def __init__(self, cap_usd: float):
        if cap_usd <= 0:
            raise ValueError("cap must be positive")
        self._cap = float(cap_usd)
        self._settled = 0.0      # real billed cost, from OpenRouter usage.cost
        self._reserved = 0.0     # granted-but-not-yet-settled estimates for in-flight calls
        self._lock = threading.Lock()

    @property
    def cap(self) -> float:
        return self._cap

    def settled(self) -> float:
        with self._lock:
            return self._settled

    def committed(self) -> float:
        """Settled + reserved — the pessimistic view the guard actually enforces against the cap."""
        with self._lock:
            return self._settled + self._reserved

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._cap - self._settled - self._reserved)

    def reserve(self, estimate: float) -> None:
        """Atomically claim `estimate` USD of headroom, or raise BudgetExceeded. Estimate is clamped
        to ≥0 (a negative estimate must never *grant* budget)."""
        est = max(0.0, float(estimate))
        with self._lock:
            if self._settled + self._reserved + est > self._cap:
                raise BudgetExceeded(
                    f"reserve ${est:.4f} would exceed cap ${self._cap:.2f} "
                    f"(settled ${self._settled:.4f} + reserved ${self._reserved:.4f})")
            self._reserved += est

    def settle(self, estimate: float, actual: float | None) -> None:
        """Release the reservation and book the real cost. `actual` None (OpenRouter returned no cost)
        falls back to the estimate so spend is never under-counted. Called in a finally, so a failed
        call still releases its reservation (actual 0)."""
        est = max(0.0, float(estimate))
        real = est if actual is None else max(0.0, float(actual))
        with self._lock:
            self._reserved = max(0.0, self._reserved - est)
            self._settled += real

    def snapshot(self) -> dict:
        with self._lock:
            return {"cap": self._cap, "settled": round(self._settled, 6),
                    "reserved": round(self._reserved, 6),
                    "remaining": round(max(0.0, self._cap - self._settled - self._reserved), 6)}
