"""Per-gate manual/auto mode store (REQ-108, #104) — the ramp-up control surface's backing table.

The pure validation (invalid gate/mode raises) is DB-free; the persistence + resolver are exercised
against the real governance Postgres via the gov_session fixture, writes rolled back at teardown. Every
gate must default to MANUAL until a human opts it in (high-supervision-first).
"""
import pytest

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import gate_mode as GM


# ----------------------------- pure validation (no DB) -----------------------------
def test_invalid_gate_and_mode_raise():
    class _NoDB:  # must raise BEFORE any DB access
        def execute(self, *a, **k):
            raise AssertionError("validation must precede DB access")
    with pytest.raises(ValueError):
        GM.set_configured_mode(_NoDB(), "gate@9", "manual")
    with pytest.raises(ValueError):
        GM.set_configured_mode(_NoDB(), "gate@5", "on")
    with pytest.raises(ValueError):
        GM.get_configured_mode(_NoDB(), "not-a-gate")


# ----------------------------- persistence + resolver (govdb) -----------------------------
@pytest.mark.govdb
def test_every_gate_defaults_to_manual_when_unset(gov_session):
    gdb.init_precious_schema()
    for g in GM.GATES:
        assert GM.effective_gate_mode(gov_session, g) == "manual"
    gov_session.rollback()


@pytest.mark.govdb
def test_global_default_applies_to_unset_gates(gov_session):
    gdb.init_precious_schema()
    GM.set_configured_mode(gov_session, "default", "auto", actor="ian")
    # a gate with no override inherits the global default...
    assert GM.get_configured_mode(gov_session, "gate@6") == "auto"
    # ...but a per-gate override wins over the default
    GM.set_configured_mode(gov_session, "gate@6", "manual", actor="ian")
    assert GM.get_configured_mode(gov_session, "gate@6") == "manual"
    assert GM.get_configured_mode(gov_session, "gate@7") == "auto"     # still inherits default
    gov_session.rollback()


@pytest.mark.govdb
def test_set_is_an_idempotent_upsert(gov_session):
    gdb.init_precious_schema()
    GM.set_configured_mode(gov_session, "gate@1", "auto", actor="a")
    GM.set_configured_mode(gov_session, "gate@1", "manual", actor="b")   # update, not a 2nd row
    assert GM.get_configured_mode(gov_session, "gate@1") == "manual"
    n = gov_session.execute(
        __import__("sqlalchemy").text("SELECT COUNT(*) FROM gate_mode WHERE gate='gate@1'")).scalar()
    assert n == 1
    gov_session.rollback()


@pytest.mark.govdb
def test_license_state_is_independent_of_configured_mode(gov_session):
    gdb.init_precious_schema()
    # #211's demote-hook writes license_state; it must NOT disturb the human's configured toggle
    GM.set_configured_mode(gov_session, "gate@5", "auto", actor="ian")
    GM.set_license_state(gov_session, "gate@5", "manual", actor="auto:audit")   # demoted by the control law
    assert GM.get_configured_mode(gov_session, "gate@5") == "auto"     # human toggle untouched
    assert GM.get_license_state(gov_session, "gate@5") == "manual"
    gov_session.rollback()


@pytest.mark.govdb
def test_set_license_state_on_a_fresh_row_does_not_materialize_a_toggle(gov_session):
    gdb.init_precious_schema()
    GM.set_license_state(gov_session, "gate@5", "auto", actor="auto:audit")
    assert GM.get_configured_mode(gov_session, "gate@5") == "manual"   # still the inherited default
    assert GM.get_license_state(gov_session, "gate@5") == "auto"
    # the license-only row is NOT a human override — the Settings UI must not render one (PR #248 review)
    assert GM.all_modes(gov_session)["gate@5"]["is_override"] is False
    gov_session.rollback()


@pytest.mark.govdb
def test_license_write_preserves_global_default_inheritance(gov_session):
    # THE PR #248 review scenario: human sets ONLY the global default to auto; gate@5 has no own row.
    # The demote-hook's first license write must not pin gate@5 to manual — configured_mode stays NULL
    # (inherit), so the gate keeps tracking the global toggle in BOTH directions afterwards.
    gdb.init_precious_schema()
    GM.set_configured_mode(gov_session, "default", "auto", actor="ian")
    assert GM.get_configured_mode(gov_session, "gate@5") == "auto"          # inherited
    GM.set_license_state(gov_session, "gate@5", "auto", actor="auto:audit")  # fresh-row license write
    assert GM.get_configured_mode(gov_session, "gate@5") == "auto"          # STILL inherited, not clobbered
    GM.set_configured_mode(gov_session, "default", "manual", actor="ian")   # human demotes the global
    assert GM.get_configured_mode(gov_session, "gate@5") == "manual"        # inheritance still live
    gov_session.rollback()


@pytest.mark.govdb
def test_all_modes_reports_defaults_overrides_and_license(gov_session):
    gdb.init_precious_schema()
    GM.set_configured_mode(gov_session, "default", "manual", actor="ian")
    GM.set_configured_mode(gov_session, "gate@7", "auto", actor="ian")
    GM.set_license_state(gov_session, "gate@5", "manual", actor="auto:audit")
    m = GM.all_modes(gov_session)
    assert set(m) == {GM.GLOBAL, *GM.GATES}
    assert m["gate@7"] == {"configured_mode": "auto", "license_state": None, "is_override": True}
    assert m["gate@6"]["configured_mode"] == "manual" and m["gate@6"]["is_override"] is False  # inherited
    # a license-only row carries the license but is NOT an override (configured_mode NULL = inherit)
    assert m["gate@5"]["license_state"] == "manual" and m["gate@5"]["is_override"] is False
    assert m["gate@5"]["configured_mode"] == "manual"   # rendered as the inherited default
    gov_session.rollback()
