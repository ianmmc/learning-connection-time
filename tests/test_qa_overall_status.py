"""#918: the QA report's overall_status gates on pass_rate >= 95% AS WELL AS the hierarchy checks.

Calls the REAL `generate_qa_report` (the prior REQ-015 status test re-implemented the expression inline, so it
could not fail when the production gate changed)."""
import pandas as pd

from infrastructure.scripts.analyze import calculate_lct_variants as clv


def _report(n_valid: int, n_invalid: int, hierarchy_ok: bool = True):
    total = n_valid + n_invalid
    rows = [
        {
            "district_id": f"d{i}", "district_name": f"D{i}", "state": "XX",
            "staff_scope": "teachers_only", "lct_value": 20.0, "level_lct_notes": "",
        }
        for i in range(total)
    ]
    df = pd.DataFrame(rows)
    valid_df = df.iloc[:n_valid]
    low, high = (10.0, 20.0) if hierarchy_ok else (20.0, 10.0)
    # A containment pair (#1017 removed the level-scope pairs, which are not containment relations).
    summary = pd.DataFrame([
        {"staff_scope": "teachers_only", "districts": 1, "mean": low, "median": low, "min": low, "max": low},
        {"staff_scope": "teachers_core", "districts": 1, "mean": high, "median": high, "min": high, "max": high},
    ])
    return clv.generate_qa_report(df, valid_df, summary, "ts", "2024-25")


def test_pass_when_hierarchy_clean_and_pass_rate_above_floor():
    r = _report(n_valid=96, n_invalid=4)
    assert r["data_quality"]["pass_rate"] == 96.0
    assert r["overall_status"] == "PASS"


def test_pass_rate_exactly_at_floor_passes():
    assert _report(n_valid=95, n_invalid=5)["overall_status"] == "PASS"


def test_warning_when_pass_rate_below_floor_despite_clean_hierarchy():
    r = _report(n_valid=94, n_invalid=6)
    assert r["hierarchy_validation"] and all(c["passed"] for c in r["hierarchy_validation"].values())
    assert r["overall_status"] == "WARNING"


def test_warning_when_hierarchy_fails_even_at_full_pass_rate():
    r = _report(n_valid=100, n_invalid=0, hierarchy_ok=False)
    assert r["overall_status"] == "WARNING"


def test_1017_level_scopes_never_gate_the_hierarchy():
    """#1017: the level scopes divide a state-practice teacher split by fixed K-5 / 6-12 bands, so their
    order against teachers_only says nothing about data quality. Any ordering of them must leave the
    hierarchy (and so overall_status) untouched."""
    df = pd.DataFrame([{"district_id": "d", "district_name": "D", "state": "XX",
                        "staff_scope": "teachers_only", "lct_value": 20.0, "level_lct_notes": ""}])
    rows = [("teachers_only", 20.0), ("teachers_core", 21.0),
            ("teachers_elementary", 5.0), ("teachers_secondary", 99.0)]   # the "wrong" way round, both
    summary = pd.DataFrame([{"staff_scope": s, "districts": 1, "mean": m, "median": m, "min": m, "max": m}
                            for s, m in rows])
    r = clv.generate_qa_report(df, df, summary, "ts", "2024-25")
    scopes = {side["scope"] for c in r["hierarchy_validation"].values() for side in (c["lower"], c["higher"])}
    assert not scopes & set(clv.TEACHER_LEVEL_SCOPES)
    assert r["overall_status"] == "PASS"


def test_1017_qa_report_names_the_quarantined_scopes():
    r = _report(n_valid=100, n_invalid=0)
    assert r["quarantined_scopes"] == {s: clv.LEVEL_SPLIT_CAVEAT for s in clv.TEACHER_LEVEL_SCOPES}
    assert "#1017" in clv.LEVEL_SPLIT_CAVEAT
