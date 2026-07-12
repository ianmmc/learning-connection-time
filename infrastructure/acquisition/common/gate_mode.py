#!/usr/bin/env python3
"""Per-gate manual/auto mode — the ramp-up model's control surface (REQ-108, issue #104).

The persisted backing store that §11b's per-gate manual/auto toggle needs, and that every #209 guardrail's
demote-hook has been waiting on. `exploration_audit.resolve_gate_mode`, `promotion_flow`'s champion swap,
and the gate@5 demote-hook all READ a stored `configured_mode`/`license_state` that had no home until now
(governance §11b: "no backing settings table anywhere in the codebase today — every gate is de-facto
always-manual").

Two stored fields per gate:
  - `configured_mode` ∈ {manual, auto}: the HUMAN's toggle — the ramp-up decision. A global-default row
    ('default') plus per-gate overrides ('gate@1'..'gate@8'). Defaults to **manual** (high-supervision-first).
  - `license_state` ∈ {manual, auto} | None: the LIVE deadband state the exploration-audit control law
    (#211) demotes/re-promotes for a gate configured auto. NULL for gates without a control law. Distinct
    from `configured_mode`: the control law moves the license WITHIN the autonomy the human licensed; it
    never flips the human's configured toggle.

This module is base-layer (cross-gate, like `calibration.CalibrationEvent` / `district_status.StateEvent`):
the precious table + get/set/resolve helpers. It deliberately does NOT branch any gate's behavior — each
gate stays manual until its own auto path is built (#211 for gate@5) — and it does NOT apply the gate@5
license layering (that is `exploration_audit.resolve_gate_mode`'s job, wired live in #211).
`effective_gate_mode` here returns the configured mode with the global-default fallback; that is the one
lookup a gate/guardrail calls today, and it always resolves to manual until a human sets a gate auto.
Design authority: PIPELINE_GOVERNANCE_AND_STATE_2026-06.md §11b.
"""
from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb  # noqa: E402  (base-layer common→common import)
from infrastructure.acquisition.common.timeutil import utcnow as _now

MODES = ("manual", "auto")
DEFAULT_MODE = "manual"            # high-supervision-first: the ramp-up model's starting posture
GLOBAL = "default"                 # the global-default row key
GATES = ("gate@1", "gate@5", "gate@6", "gate@7", "gate@8")   # gate@8 is forward-looking (not built yet, #89)
_VALID_KEYS = frozenset((GLOBAL,) + GATES)


class GateMode(gdb.Base):
    """PRECIOUS per-gate mode row (upsert-only, never dropped). One row per key: 'default' (the global
    default) + 'gate@1'..'gate@8' overrides. A missing gate row means 'inherit the global default'; a
    missing default means DEFAULT_MODE — so an empty table reads as every-gate-manual, the safe posture."""
    __tablename__ = "gate_mode"
    gate: Mapped[str] = mapped_column(String, primary_key=True)        # 'default' | 'gate@1'..'gate@8'
    # server_default (not an ORM default): the write paths are raw text() upserts that bypass ORM defaults,
    # so the omit-and-get-manual contract must live in the DDL to hold (the calibration.py #217 lesson).
    configured_mode: Mapped[str] = mapped_column(String, server_default=text("'manual'"))
    license_state: Mapped[str | None] = mapped_column(String)          # deadband state (#211); NULL if no control law
    updated_at: Mapped[str] = mapped_column(String)
    actor: Mapped[str | None] = mapped_column(String)


def _validate_gate(gate):
    if gate not in _VALID_KEYS:
        raise ValueError(f"gate must be one of {sorted(_VALID_KEYS)} (got {gate!r})")


def _validate_mode(mode):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES} (got {mode!r})")


def get_configured_mode(con, gate):
    """The gate's configured mode: its own override if set, else the global-default row, else DEFAULT_MODE.
    Absence means inherit — an unset gate is never an error (it just resolves to manual by default)."""
    _validate_gate(gate)
    own = con.execute(text("SELECT configured_mode FROM gate_mode WHERE gate=:g"), {"g": gate}).scalar()
    if own:
        return own
    dflt = con.execute(text("SELECT configured_mode FROM gate_mode WHERE gate=:g"), {"g": GLOBAL}).scalar()
    return dflt or DEFAULT_MODE


def effective_gate_mode(con, gate):
    """The one lookup a gate/guardrail calls to learn its live mode. For #104 this IS the configured mode
    (with global-default fallback). gate@5's exploration-audit license layering (resolve_gate_mode over
    license_state + a live window_count) is wired in #211; until then a gate is exactly its configured
    mode, and every gate defaults manual — so this returns 'manual' everywhere until a human opts a gate in."""
    return get_configured_mode(con, gate)


def set_configured_mode(con, gate, mode, actor=None):
    """Upsert a gate's (or the global default's) configured mode. Validates both — a typo'd gate or mode
    RAISES rather than silently no-op'ing (the exploration_audit raise-on-unknown discipline: a bad toggle
    value must surface as a wiring bug, never masquerade as a conservative manual)."""
    _validate_gate(gate)
    _validate_mode(mode)
    con.execute(text(
        "INSERT INTO gate_mode (gate, configured_mode, updated_at, actor) VALUES (:g,:m,:t,:a) "
        "ON CONFLICT (gate) DO UPDATE SET configured_mode=:m, updated_at=:t, actor=:a"),
        {"g": gate, "m": mode, "t": _now(), "a": actor})


def get_license_state(con, gate):
    """The live deadband license state for a gate (the #211 demote-hook's stored state), or None if unset."""
    _validate_gate(gate)
    return con.execute(text("SELECT license_state FROM gate_mode WHERE gate=:g"), {"g": gate}).scalar()


def set_license_state(con, gate, state, actor=None):
    """Persist a gate's live deadband license state (auto|manual) — the #211 demote-hook writes this. On a
    fresh row it seeds configured_mode=manual (the license is meaningful only once the human sets the gate
    auto anyway); on an existing row it touches ONLY license_state, never the human's configured toggle."""
    _validate_gate(gate)
    _validate_mode(state)
    con.execute(text(
        "INSERT INTO gate_mode (gate, configured_mode, license_state, updated_at, actor) "
        "VALUES (:g, :cm, :s, :t, :a) "
        "ON CONFLICT (gate) DO UPDATE SET license_state=:s, updated_at=:t, actor=:a"),
        {"g": gate, "cm": DEFAULT_MODE, "s": state, "t": _now(), "a": actor})


def all_modes(con):
    """Every gate's resolved state for the Settings UI + the precious backup: {gate: {configured_mode,
    license_state, is_override}} with defaults filled for unset gates, plus the 'default' global row.
    `is_override` distinguishes a stored per-gate value from an inherited default (so the UI can show it)."""
    rows = {r["gate"]: (r["configured_mode"], r["license_state"]) for r in con.execute(text(
        "SELECT gate, configured_mode, license_state FROM gate_mode")).mappings().all()}
    default_mode = (rows.get(GLOBAL) or (DEFAULT_MODE, None))[0]
    out = {GLOBAL: {"configured_mode": default_mode, "license_state": None,
                    "is_override": GLOBAL in rows}}
    for g in GATES:
        r = rows.get(g)
        out[g] = {"configured_mode": r[0] if r else default_mode,
                  "license_state": r[1] if r else None,
                  "is_override": r is not None}
    return out
