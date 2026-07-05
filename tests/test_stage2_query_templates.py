"""#160 (Chunk 2, epic #163) — the differentiated SERP query-template config foundation.

Pins the config-as-data knob + its renderer WITHOUT wiring it into discovery yet (that's Chunk 4).
Pure-function / config tests — no DB, no network.
"""
from infrastructure.acquisition.common import config_loader as CFG
from infrastructure.acquisition.stage2_discover import discover_stage2 as D2


class TestQueryTemplateConfig:
    def test_knob_loads_with_entries_shape(self):
        doc = CFG.load("stage2_query_templates")
        assert doc["knob"] == "stage2_query_templates"
        assert doc["entries"] and all("value" in e for e in doc["entries"])

    def test_every_template_renders_with_only_school_and_state(self):
        # a template referencing any other placeholder would raise here — the guarded contract
        for tmpl in CFG.values("stage2_query_templates"):
            rendered = tmpl.format(school="Marion High School", state="IA")
            assert "{" not in rendered and "}" not in rendered


class TestDifferentiatedQueries:
    def test_renders_school_and_state_into_each(self):
        qs = D2.differentiated_queries("Marion High School", "IA")
        assert qs and all("Marion High School" in q and "IA" in q for q in qs)

    def test_order_matches_config_order(self):
        templates = CFG.values("stage2_query_templates")
        qs = D2.differentiated_queries("X School", "ND")
        assert qs == [t.format(school="X School", state="ND") for t in templates]

    def test_set_is_distinct_from_the_default_wave1_query(self):
        # the whole point: a 7->2 retry must NOT re-run the query that already found nothing
        default = D2.query_for("Marion High School", "IA")
        qs = D2.differentiated_queries("Marion High School", "IA")
        assert default not in qs
        assert len(set(qs)) == len(qs)              # no dup phrasings within the set

    def test_covers_the_intended_angles(self):
        qs = " || ".join(D2.differentiated_queries("S", "ST")).lower()
        assert "filetype:pdf" in qs                 # the source-PDF angle (composes with site: scoping)
        assert "handbook" in qs                     # the handbook-scoped angle
        assert "dismissal" in qs or "school hours" in qs   # the alternate-vocabulary angle

    def test_no_template_hardcodes_site_scoping(self):
        # the search fns (brightdata_search/serper_search) append `site:{district_domain}` themselves —
        # a template must never hardcode its own site: operator, which would collide.
        for q in D2.differentiated_queries("S", "ST"):
            assert "site:" not in q
