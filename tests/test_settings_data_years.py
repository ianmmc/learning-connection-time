"""Settings console — data-year visibility (#254 adjacents, 2026-07-14).

The current school year is DERIVED (July-1 rollover, utilities/school_year.py) and surfaced in the
Settings view so a human can see the rollover happened; the NCES primary vintage is hand-bumped on
ingest and shown beside it. These are must-be-visible console facts, so they get regression tests
(the UI-visibility discipline): the API contract server-side, and a DOM-presence assertion that the
Settings view actually renders the block and the General Settings group nav.
"""
from pathlib import Path

from infrastructure.utilities import school_year as SY

STATIC = Path("infrastructure/acquisition/process_governance/static")


def _client():
    from fastapi.testclient import TestClient

    from infrastructure.acquisition.process_governance import server

    return TestClient(server.app)


class TestDataYearsApi:
    def test_returns_the_derived_vocabulary(self):
        r = _client().get("/api/data-years")
        assert r.status_code == 200
        d = r.json()
        assert d["current_school_year"] == SY.current_school_year()
        assert d["nces_primary_year"] == SY.NCES_PRIMARY_YEAR
        assert d["acceptable_bell_years"] == list(SY.ACCEPTABLE_BELL_YEARS)
        assert d["acceptable_bell_years"][0] == d["current_school_year"]

    def test_covid_years_are_listed_for_the_disclaimer(self):
        d = _client().get("/api/data-years").json()
        assert "2019-20" in d["covid_excluded_years"]
        assert d["current_school_year"] not in d["covid_excluded_years"]


class TestSettingsViewRendersIt:
    def test_settings_js_fetches_and_renders_the_block(self):
        js = (STATIC / "settings.js").read_text()
        assert "/api/data-years" in js
        assert "settings-years" in js
        assert "Current school year" in js

    def test_settings_nav_keeps_the_general_settings_group(self):
        js = (STATIC / "settings.js").read_text()
        assert "General Settings" in js
        assert "settings-nav" in js


class TestExclusionsView:
    """#229 UX rework (Ian, 2026-07-14): the standing pre-queue exclusion corpus reads in
    Settings → Exclusions; the gate@1 batch view collapses its per-batch refusal receipt to a
    count. Endpoint degrades honestly without the NCES CSVs (CI has none)."""

    def test_endpoint_degrades_without_nces_files(self, monkeypatch):
        # the live derivation needs the NCES CSVs + the LCT enrollment DB (the sanctioned Stage-1
        # edge) — neither exists in the DB-free job, so both paths are exercised via the seams
        from infrastructure.acquisition.process_governance import server as SRV
        monkeypatch.setattr(SRV.SS_SAMPLING, "latest_nces_year", lambda: None)
        d = _client().get("/api/exclusions").json()
        assert d["available"] is False and d["reason"]

    def test_endpoint_serves_the_snapshot_contract(self, monkeypatch):
        from infrastructure.acquisition.process_governance import server as SRV
        canned = {"available": True, "nces_year": "2024_25",
                  "no_domain": {"count": 2, "by_state": {"ID": 2},
                                "districts": [{"district_id": "1", "name": "A", "state": "ID", "website": ""},
                                              {"district_id": "2", "name": "B", "state": "ID", "website": "x"}]},
                  "grade_span_gap": {"count": 0, "districts": []},
                  "school_criteria": SRV.SS_SAMPLING.SCHOOL_CRITERIA_TEXT}
        monkeypatch.setattr(SRV.SS_SAMPLING, "latest_nces_year", lambda: "2024_25")
        monkeypatch.setattr(SRV, "_exclusions_snapshot", lambda year: canned)
        d = _client().get("/api/exclusions").json()
        assert d["no_domain"]["count"] == len(d["no_domain"]["districts"])
        assert sum(d["no_domain"]["by_state"].values()) == d["no_domain"]["count"]
        assert "virtual" in d["school_criteria"]

    def test_settings_view_carries_the_exclusions_group(self):
        js = (STATIC / "settings.js").read_text()
        for marker in ('data-feat="exclusions-nav"', 'data-feat="exclusions-no-domain"',
                       'data-feat="exclusions-gap"', 'data-feat="exclusions-criteria"',
                       "/api/exclusions", 'data-group-panel="exclusions"'):
            assert marker in js, f"settings.js lost the Exclusions marker {marker!r}"

    def test_gate1_receipt_is_collapsed_not_removed(self):
        js = (STATIC / "gate1.js").read_text()
        assert 'data-feat="domain-excluded-collapsed"' in js
        assert "<details" in js and "domain_excluded" in js   # receipt still renders, collapsed
