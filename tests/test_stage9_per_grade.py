"""Stage 9 per-grade projection (#605) — PURE unit tests (no DB, no marker).

Exercises grade→band mapping over the recognized partition shapes, floating bands, merged shapes,
the overlap tie-rule + flag, the canonical fallback, and statutory-label propagation.
"""
from infrastructure.acquisition.stage9_incorporate import per_grade as PG
from infrastructure.acquisition.stage9_incorporate.mapping import BandWrite


def _bw(band, minutes, spans, *, method="council_extraction", basis="gross_bell_to_bell",
        year="2024-25"):
    return BandWrite(grade_level=band, method=method, minutes_basis=basis, year=year,
                     year_basis="x", minutes=minutes,
                     raw_import={"band_grade_span": {"slot_spans": spans}})


def _by_grade(writes):
    return {gm.grade: gm for gm in PG.project(writes, fingerprint="fp", approval_id=1)}


def test_grade_tokens_are_k_through_12():
    assert PG.GRADE_TOKENS == ["KG", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]


def test_clean_three_band_partition():
    g = _by_grade([
        _bw("elementary", 400, [{"gslo": "KG", "gshi": "05"}]),
        _bw("middle", 430, [{"gslo": "06", "gshi": "08"}]),
        _bw("high", 450, [{"gslo": "09", "gshi": "12"}]),
    ])
    assert set(g) == set(PG.GRADE_TOKENS)                      # every K-12 grade covered
    assert g["03"].source_band == "elementary" and g["03"].minutes == 400
    assert g["07"].source_band == "middle" and g["07"].minutes == 430
    assert g["10"].source_band == "high" and g["10"].minutes == 450
    assert all(gm.overlap_flag is None for gm in g.values())   # clean partition — no overlaps


def test_floating_middle_7_9_no_overlap():
    # elementary KG-06, middle 07-09, high 10-12 — grade 6 is elementary, grade 9 is (only) middle
    g = _by_grade([
        _bw("elementary", 400, [{"gslo": "KG", "gshi": "06"}]),
        _bw("middle", 430, [{"gslo": "07", "gshi": "09"}]),
        _bw("high", 450, [{"gslo": "10", "gshi": "12"}]),
    ])
    assert g["06"].source_band == "elementary"
    assert g["09"].source_band == "middle" and g["09"].overlap_flag is None   # only middle serves it
    assert g["10"].source_band == "high"


def test_overlap_grade_uses_canonical_band_and_flags():
    # a 7-9 middle AND a 9-12 high both serve grade 9 -> tie-rule picks high (9's canonical band) + flags
    g = _by_grade([
        _bw("elementary", 400, [{"gslo": "KG", "gshi": "06"}]),
        _bw("middle", 430, [{"gslo": "07", "gshi": "09"}]),
        _bw("high", 450, [{"gslo": "09", "gshi": "12"}]),
    ])
    assert g["08"].source_band == "middle" and g["08"].overlap_flag is None
    assert g["09"].source_band == "high"          # canonical owner of grade 9
    assert g["09"].overlap_flag and "overlap" in g["09"].overlap_flag
    assert set(g["09"].serving_bands) == {"middle", "high"}


def test_merged_k8_band_covers_middle_grades():
    # a K-8 school under the 'elementary' band + a 9-12 high; grades 6-8 take elementary minutes
    g = _by_grade([
        _bw("elementary", 410, [{"gslo": "KG", "gshi": "08"}]),
        _bw("high", 450, [{"gslo": "09", "gshi": "12"}]),
    ])
    assert g["07"].source_band == "elementary" and g["07"].minutes == 410
    assert g["09"].source_band == "high"


def test_no_serving_band_leaves_grade_unprojected():
    # only elementary KG-05 present -> grades 6-12 get NO row (LCT falls back to statutory for them)
    g = _by_grade([_bw("elementary", 400, [{"gslo": "KG", "gshi": "05"}])])
    assert "05" in g and "06" not in g and "12" not in g


def test_canonical_fallback_when_no_live_span():
    # empty slot_spans -> band falls back to its canonical range (elementary KG-05)
    g = _by_grade([_bw("elementary", 400, [])])
    assert g["05"].source_band == "elementary"
    assert "06" not in g


def test_statutory_label_propagates_to_grades():
    g = _by_grade([
        _bw("elementary", 400, [{"gslo": "KG", "gshi": "05"}]),
        _bw("high", 350, [{"gslo": "09", "gshi": "12"}], method="statutory_fallback", basis="statutory"),
    ])
    assert g["03"].method == "council_extraction"
    assert g["10"].method == "statutory_fallback" and g["10"].minutes_basis == "statutory"


def test_grade_13_span_folds_into_high_range():
    # a 09-13 high school (grade 13 continuation) still covers grades 9-12; 13 itself is not an LCT token
    g = _by_grade([_bw("high", 450, [{"gslo": "09", "gshi": "13"}])])
    assert g["12"].source_band == "high"
    assert "13" not in g   # GRADE_TOKENS stops at 12
