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


# ----------------------------- #160 consumption in Stage 2 discovery (Chunk 4) -----------------------------
def _fu_district(strategy=None):
    band = {"schools": [{"school_id": "s1", "name": "Fresh High", "level": "High"}]}
    if strategy:
        band["query_strategy"] = strategy
    return {"district_id": "D1", "name": "D", "state": "IA", "domain": "d.org",
            "schools_by_band": {"high": band}}


class TestFollowUpQueryConsumption:
    def test_first_run_school_runs_only_the_default_query(self):
        r = D2.build_roster(_fu_district())[0]           # no strategy -> single default query
        assert r["queries"] == [r["query"]]

    def test_widen_queries_band_adds_the_differentiated_set(self):
        r = D2.build_roster(_fu_district("widen_queries"))[0]
        assert r["queries"][0] == r["query"]             # default first
        assert r["queries"][1:] == D2.differentiated_queries("Fresh High", "IA")
        assert any("filetype:pdf" in q for q in r["queries"])

    def test_new_schools_band_keeps_single_default(self):
        r = D2.build_roster(_fu_district("new_schools"))[0]
        assert r["queries"] == [r["query"]]              # untried schools -> default query, not widened

    def test_run_wave1_runs_every_query_and_unions_dedup(self):
        roster = D2.build_roster(_fu_district("widen_queries"))
        calls = []

        def fake_search(q, domain):
            calls.append(q)
            return ("brightdata", [f"http://d.org/{len(calls)}", "http://d.org/shared"])

        D2.run_wave1(roster, "d.org", fake_search)
        assert len(calls) == len(roster[0]["queries"]) > 1          # every widened query ran
        raw = roster[0]["wave1_raw_urls"]
        assert raw.count("http://d.org/shared") == 1                # order-preserving dedup across queries


class TestSeedUrlInjection:
    def test_seed_urls_land_in_candidates_json(self, tmp_path, monkeypatch):
        # #161: a district's seed_urls are injected as capture targets (tool 'seed_7to3') so Stage 3
        # captures them through the existing candidates.json pipe — no discovery, no Stage-3 change.
        import json
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        district = {"district_id": "D1", "name": "Testville", "state": "IA", "domain": "d.org",
                    "seed_urls": ["http://d.org/handbook.pdf"]}
        d = D2.write_discovery(district, roster=[], batch_id="batch_00099")
        cands = json.loads((d / "candidates.json").read_text())["candidates"]
        seed = [c for c in cands if c["url"] == "http://d.org/handbook.pdf"]
        assert len(seed) == 1 and seed[0]["tools"] == ["seed_7to3"]

    def test_no_seed_urls_is_a_noop(self, tmp_path, monkeypatch):
        import json
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        district = {"district_id": "D2", "name": "Plainville", "state": "IA", "domain": "p.org"}
        d = D2.write_discovery(district, roster=[], batch_id="batch_00099")
        assert json.loads((d / "candidates.json").read_text())["candidates"] == []
