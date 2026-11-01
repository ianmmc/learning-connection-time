"""#992: compare_sea_vs_federal_lct flags cross-vintage pairs and fails loud on an empty federal selection.

`--year` selects the FEDERAL vintage only; each state's SEA data is read at its registry vintage. Before the
fix the default silently compared IL/MI/NY across vintages under a header that read as one year, and a wrong
`--year` printed "No comparison data available." and exited 0."""
import pandas as pd
import pytest

from infrastructure.scripts.analyze import compare_sea_vs_federal_lct as cmp
from infrastructure.utilities.data_guards import DataGuardError


def _df(teachers=100.0, enrollment=1800):
    return pd.DataFrame([{"district_id": "1", "teachers": teachers, "enrollment_k12": enrollment,
                          "enrollment_k5": 900}])


class _Session:
    """Answers the `SELECT DISTINCT source_year` the empty-selection message uses."""
    def execute(self, *_a, **_k):
        return [("2023-24",), ("2024-25",)]


@pytest.fixture
def stub(monkeypatch):
    def install(federal_rows: bool):
        monkeypatch.setattr(cmp, "get_federal_data", lambda s, st, y: _df() if federal_rows else pd.DataFrame())
        monkeypatch.setattr(cmp, "get_sea_data",
                            lambda s, st, c: pd.DataFrame([{"district_id": "1", "teachers": 105.0, "enrollment_k12": 1800}]))
    return install


def test_results_carry_both_vintages_and_flag_cross_vintage_pairs(stub, capsys):
    stub(federal_rows=True)
    results = {r["state"]: r for r in cmp.compare_all(_Session(), "2024-25")}
    assert results["CA"]["sea_year"] == "2024-25" and results["CA"]["vintage_aligned"] is True
    assert results["IL"]["sea_year"] == "2023-24"
    assert results["IL"]["federal_year"] == "2024-25"
    assert results["IL"]["vintage_aligned"] is False
    assert "cross-vintage pair - SEA 2023-24 vs federal 2024-25" in capsys.readouterr().out


def test_empty_federal_selection_raises_instead_of_exiting_clean(stub):
    stub(federal_rows=False)
    with pytest.raises(DataGuardError, match=r"--year 2099-00.*available.*2024-25"):
        cmp.compare_all(_Session(), "2099-00")


def test_alignment_needs_both_sea_vintages_to_match_the_federal_one_1012(stub, capsys, monkeypatch):
    # The mixed pair MA carried until 2026-11-01 (2024-25 staff, 2025-26 enrollment), as a synthetic entry
    stub(federal_rows=True)
    monkeypatch.setattr(cmp, "SEA_STATES", {"CA": {"year": "2024-25", "table": "ca_staff_data"},
                                            "XX": {"year": "2024-25", "enroll_year": "2025-26", "table": "xx"}})
    results = {r["state"]: r for r in cmp.compare_all(_Session(), "2024-25")}
    xx = results["XX"]
    assert xx["sea_year"] == "2024-25" and xx["sea_enroll_year"] == "2025-26"
    assert xx["vintage_aligned"] is False
    assert "SEA 2024-25 (enrollment 2025-26) vs federal 2024-25" in capsys.readouterr().out
    assert results["CA"]["sea_enroll_year"] == "2024-25" and results["CA"]["vintage_aligned"] is True
