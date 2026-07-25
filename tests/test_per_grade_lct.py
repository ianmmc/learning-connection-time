"""Per-grade → scope minutes weighting (#606) — PURE unit tests (no DB, no marker).

`weighted_scope_minutes` takes an injected `get_statutory` callable and a plain enrollment object,
so it exercises with zero DB. Covers the PR #607 review fixes: stored-statutory reuse (a grade's
statutory value is Stage 9's, resolved against its REAL serving band — never re-derived from the
canonical band), the ALL-years blend window (not just the modal year), and statutory memoization.
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


def _gm(minutes_by_grade, *, basis="gross_bell_to_bell", year="2024-25", bands=None, vouched=None):
    """6-tuples (minutes, method, basis, year, source_band, human_vouched); source_band defaults
    canonical. `vouched` is an optional set of grades whose row carries a gate@8 human vouch (#626)."""
    method = "council_extraction" if basis == "gross_bell_to_bell" else "statutory_fallback"
    vouched = vouched or set()
    return {g: (m, method, basis, year, (bands or {}).get(g, PGL._CANON_BAND[g]), g in vouched)
            for g, m in minutes_by_grade.items()}


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


def test_statutory_rows_are_reused_verbatim():
    # PR #607 fix: a statutory projection row's stored minutes (resolved by Stage 9 against the
    # grade's REAL band) are reused verbatim — never recomputed from the canonical band.
    gm = _gm({g: 333 for g in PGL.SEC_GRADES}, basis="statutory")   # a value no canon band has
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_statutory" and year is None
    assert minutes == 333   # stored value wins — not 330/350 canonical recomputes


def test_floating_band_statutory_grade_keeps_its_real_bands_value():
    # THE motivating case: a floating 7-9 middle whose schedule fell to statutory. Grade 09's
    # stored row carries the MIDDLE rate (330) with source_band='middle' — the old code
    # substituted the canonical high rate (350).
    gm = _gm({g: 450 for g in ["10", "11", "12"]}) | _gm(
        {g: 330 for g in ["07", "08", "09"]}, basis="statutory",
        bands={"07": "middle", "08": "middle", "09": "middle"})
    enr = _enr(**{"06": 0})   # elementary KG-06 district: grade 6 not in secondary population
    minutes, source, _ = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, enr, gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_mixed"
    assert minutes == round((3 * 330 + 3 * 450) / 6)   # grade 09 contributes 330, NOT 350


def test_empty_projection_falls_back_to_statutory():
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), {}, ["2024-25"], _get_statutory)
    assert source == "per_grade_statutory" and year is None


def test_temporal_window_drops_measured_to_statutory():
    # measured year 2024-25 can't form a ≤3-consecutive-year set with staff/enroll 2018-19 →
    # statutory, resolved per grade against its REAL source_band (canonical here)
    gm = _gm({g: 450 for g in PGL.SEC_GRADES}, year="2024-25")
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), gm, ["2018-19"], _get_statutory)
    assert source == "per_grade_statutory" and year is None
    assert minutes == round((3 * 330 + 4 * 350) / 7)   # 341


def test_temporal_window_checks_every_measured_year_not_just_modal():
    # PR #607 fix: majority of grades in-window (2024-25), one minority grade from an
    # out-of-window year — the WHOLE scope must drop to statutory, not blend the stale value.
    gm = (_gm({g: 430 for g in ["06", "07", "08", "09", "10", "11"]}, year="2024-25")
          | _gm({"12": 450}, year="2018-19"))
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(), gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_statutory" and year is None
    assert minutes == round((3 * 330 + 4 * 350) / 7)   # all statutory, per real band


def test_626_human_vouched_grade_exempt_from_window_keeps_council_value():
    # #626 (Dickinson shape): a human vouched for the middle band at gate@8; its stored vintage is
    # out of window (2016-17) but the high band is current (2025-26). The vouched middle is treated as
    # equivalent to an in-window schedule — the scope stays per_grade_bell on the council values, and
    # only the NON-vouched years gate the window (staff/enroll 2024-25 + high 2025-26 form a set).
    gm = (_gm({g: 426 for g in ["06", "07", "08"]}, year="2016-17", vouched={"06", "07", "08"})
          | _gm({g: 430 for g in ["09", "10", "11", "12"]}, year="2025-26"))
    minutes, source, year = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(),
                                                       gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_bell"                       # NOT dropped to statutory
    assert minutes == round((3 * 426 + 4 * 430) / 7)        # council values blended, vouched kept
    assert year == "2025-26"                                # rep_year = modal actual vintage


def test_626_non_vouched_out_of_window_still_drops():
    # Guard the scope: WITHOUT a vouch, the same out-of-window middle correctly drops the whole scope
    # to statutory (the exemption is strictly the human determination, not a blanket window relaxation).
    gm = (_gm({g: 426 for g in ["06", "07", "08"]}, year="2016-17")
          | _gm({g: 430 for g in ["09", "10", "11", "12"]}, year="2025-26"))
    _, source, _ = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(),
                                              gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_statutory"


def test_626_vouched_does_not_rescue_a_non_vouched_stale_sibling():
    # A vouch exempts only ITS grade's year. A second, NON-vouched out-of-window band in the same scope
    # still forces statutory — the window is not globally disabled by one vouched band.
    gm = (_gm({g: 426 for g in ["06", "07", "08"]}, year="2016-17", vouched={"06", "07", "08"})
          | _gm({g: 430 for g in ["09", "10", "11", "12"]}, year="2016-17"))   # high: stale, NOT vouched
    _, source, _ = PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, _enr(),
                                              gm, ["2024-25"], _get_statutory)
    assert source == "per_grade_statutory"


def test_638_grade_band_split_matches_school_sampling_bands():
    """#638 fitness: per_grade_lct's LCT-side grade→band vocabulary (GRADES/ELEM_GRADES/SEC_GRADES/
    _CANON_BAND) is a second copy of school_sampling's BANDS/GRADE_ORD, forced apart by the
    import-linter boundary (LCT-side must not import acquisition code — so THIS TEST is the pin).
    If the band boundaries ever move in school_sampling.BANDS, Stage 9 would project a grade into
    one band while weighted_scope_minutes weights it into a different scope — silent LCT drift."""
    from infrastructure.acquisition.common.school_sampling import BANDS, GRADE_ORD
    # same grade-token vocabulary (school_sampling additionally knows PK/13, outside LCT range)
    assert set(PGL.GRADES) <= set(GRADE_ORD)
    for g in PGL.GRADES:
        owning = [b for b, rng in BANDS.items() if GRADE_ORD[g] in rng]
        assert owning == [PGL._CANON_BAND[g]], (
            f"grade {g}: school_sampling.BANDS says {owning}, per_grade_lct._CANON_BAND says "
            f"{PGL._CANON_BAND[g]} — the two grade→band definitions diverged (#638)")
    # the scope split is the same partition
    assert PGL.ELEM_GRADES == [g for g in PGL.GRADES if PGL._CANON_BAND[g] == "elementary"]
    assert PGL.SEC_GRADES == [g for g in PGL.GRADES if PGL._CANON_BAND[g] in ("middle", "high")]
    assert PGL.ELEM_GRADES + PGL.SEC_GRADES == PGL.GRADES


def test_638_statutory_default_single_home():
    """#638: the statutory last-resort default has ONE policy home (models.STATUTORY_DEFAULT_MINUTES);
    both consumers import it rather than carrying independent literals."""
    from infrastructure.database.models import STATUTORY_DEFAULT_MINUTES
    from infrastructure.acquisition.stage9_incorporate import incorporate as INC
    assert INC.STATUTORY_DEFAULT_MINUTES is STATUTORY_DEFAULT_MINUTES
    import inspect
    from infrastructure.scripts.analyze import calculate_lct_variants as CLV
    src = inspect.getsource(CLV.get_statutory_minutes)
    assert "STATUTORY_DEFAULT_MINUTES" in src and "return 360" not in src


def test_zero_enrollment_returns_none():
    enr = _enr(**{g: 0 for g in PGL.SEC_GRADES})
    assert PGL.weighted_scope_minutes(None, "XX", PGL.SEC_GRADES, enr, _gm({}), ["2024-25"], _get_statutory) is None


def test_elementary_scope_covers_k5():
    gm = _gm({g: 380 for g in PGL.ELEM_GRADES})
    minutes, source, _ = PGL.weighted_scope_minutes(None, "XX", PGL.ELEM_GRADES, _enr(), gm, ["2024-25"], _get_statutory)
    assert minutes == 380 and source == "per_grade_bell"


def test_cached_statutory_memoizes_per_state_band():
    calls = []
    def counting(session, state, band):
        calls.append((state, band))
        return _STAT[band], "state_requirement", None
    cached = PGL.cached_statutory(counting)
    for _ in range(5):
        cached(None, "XX", "middle")
        cached(None, "XX", "high")
    assert calls == [("XX", "middle"), ("XX", "high")]   # one underlying call per (state, band)