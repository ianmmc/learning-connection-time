"""Per-grade → scope minutes weighting (#606) — PURE unit tests (no DB, no marker).

`weighted_scope_minutes` takes an injected `get_statutory` callable and a plain enrollment object,
so it exercises with zero DB.
"""
from types import SimpleNamespace

from infrastructure.scripts.analyze import per_grade_lct as PGL

# statutory minimums by band, for the injected fallback
_STAT = {"elementary": 300, "middle": 330, "high": 350}


def _get_statutory(session, state, band):
    return _STAT[band], "state_requirement", None


def _enr(**counts):
    """EnrollmentByGrade stand-in: pass grade tokens KG/01../12 → counts (default 100 each)."""
    base = {PGL._ENROLL_ATTR[g]: 100 for g in PGL.GRADES}
    for g, n in counts.items():
        base[PGL._ENROLL_ATTR[g]] = n
    return SimpleNamespace(**base)


def _gm(minutes_by_grade, *, basis="gross_bell_to_bell", year="2024-25"):
    return {g: (m, "council_extraction", basis, year) for g, m in minutes_by_grade.items()}


def test_secondary_weights_mid_and_high():
    # middle grades (6-8) = 430, high grades (9-12) = 450, equal enrollment → (3·430 + 4·450)/7
    gm = _gm({g: 430 for g in ["06", "07", "08"]} | {g: 450 for g in ["09", "10", "11", "12"]})
    out = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), gm, ["2024-25"], _get_statutory)
    minutes, source, year = out
    assert minutes == round((3 * 430 + 4 * 450) / 7)   # 441
    assert source == "per_grade_bell" and year == "2024-25"


def test_secondary_enrollment_weighting_shifts_toward_larger_grades():
    # tiny middle, huge high → weighted minutes pulled toward the high value
    gm = _gm({g: 400 for g in ["06", "07", "08"]} | {g: 460 for g in ["09", "10", "11", "12"]})
    enr = _enr(**{"06": 1, "07": 1, "08": 1, "09": 500, "10": 500, "11": 500, "12": 500})
    minutes, source, _ = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, enr, gm, ["2024-25"], _get_statutory)
    assert 455 <= minutes <= 460 and source == "per_grade_bell"


def test_mixed_when_some_grades_fall_back_to_statutory():
    # only high grades measured; middle grades have no projection row → per-grade statutory
    gm = _gm({g: 450 for g in ["09", "10", "11", "12"]})
    minutes, source, _ = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_mixed"
    assert minutes == round((3 * 330 + 4 * 450) / 7)   # middle→statutory 330, high→450


def test_all_statutory_scope_is_labeled_and_yearless():
    gm = _gm({g: 350 for g in PGL.SEC_GRADES}, basis="statutory")   # statutory rows → per-grade canon band
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_statutory" and year is None
    # each grade falls back to ITS canonical band: middle 6-8→330, high 9-12→350
    assert minutes == round((3 * 330 + 4 * 350) / 7)   # 341


def test_empty_projection_falls_back_to_statutory():
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), {}, ["2024-25"], _get_statutory)
    assert source == "per_grade_statutory" and year is None


def test_temporal_window_drops_measured_to_statutory():
    # measured year 2024-25 can't form a ≤3-consecutive-year set with staff/enroll 2018-19 → statutory
    gm = _gm({g: 450 for g in PGL.SEC_GRADES}, year="2024-25")
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), gm, ["2018-19"], _get_statutory)
    assert source == "per_grade_statutory" and year is None
    # fell back to per-grade statutory (mid 330, high 350), not the measured 450
    assert minutes == round((3 * 330 + 4 * 350) / 7)   # 341


def test_zero_enrollment_returns_none():
    enr = _enr(**{g: 0 for g in PGL.SEC_GRADES})
    assert PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, enr, _gm({}), ["2024-25"], _get_statutory) is None


def test_elementary_scope_covers_k5():
    gm = _gm({g: 380 for g in PGL.ELEM_GRADES})
    minutes, source, _ = PGL.weighted_scope_minutes(None, "XX", PGL.ELEM_GRADES, _enr(), gm, ["2024-25"], _get_statutory)
    assert minutes == 380 and source == "per_grade_bell"
