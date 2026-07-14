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
