"""#160 (epic #163) — the differentiated SERP query-template config, its renderer, and its
consumption in Stage 2 discovery (`TestFollowUpQueryConsumption` below).

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


class TestWave1PerUrlProvenance:
    """#341 — a mid-set failover must not lose which provider surfaced which URL."""

    def test_failover_mid_set_keeps_first_serving_provider_per_url(self):
        roster = D2.build_roster(_fu_district("widen_queries"))
        calls = []

        def fake_search(q, domain):
            calls.append(q)
            if len(calls) == 1:
                return ("brightdata", ["http://d.org/bell", "http://d.org/shared"])
            return ("serper", ["http://d.org/hours", "http://d.org/shared"])

        D2.run_wave1(roster, "d.org", fake_search)
        r = roster[0]
        by_url = {g["url"]: g["provider"] for g in r["wave1_gated"]}
        assert by_url["http://d.org/bell"] == "brightdata"
        assert by_url["http://d.org/hours"] == "serper"
        assert by_url["http://d.org/shared"] == "brightdata"   # first to surface it wins
        assert r["wave1_providers"] == ["brightdata", "serper"]
        assert r["wave1_provider"] == "serper"                 # scalar summary stays last-wins

    def test_flatten_prefers_per_url_provider_over_scalar(self):
        roster = D2.build_roster(_fu_district("widen_queries"))
        calls = []

        def fake_search(q, domain):
            calls.append(q)
            provider = "brightdata" if len(calls) == 1 else "serper"
            return (provider, [f"http://d.org/p{len(calls)}"])

        D2.run_wave1(roster, "d.org", fake_search)
        tools = {c["url"]: c["tools"] for c in D2.flatten(roster)}
        assert tools["http://d.org/p1"] == ["brightdata"]      # pre-fix: all attributed to "serper"

    def test_flatten_falls_back_to_scalar_for_pre_341_rows(self):
        # a pre-#341 discovery.json row has no per-entry provider — the scalar still attributes
        row = {"school": "Old High", "wave1_provider": "brightdata",
               "wave1_gated": [{"url": "http://d.org/x", "kept": True}],
               "wave2_gated": []}
        assert D2.flatten([row])[0]["tools"] == ["brightdata"]


class TestAtomicDiscoveryWrite:
    """#265 — crash-safe manifests: no partial JSON, and candidates.json lands before discovery.json."""

    def test_no_tmp_files_left_behind(self, tmp_path, monkeypatch):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        district = {"district_id": "D3", "name": "Atomicville", "state": "IA", "domain": "a.org"}
        d = D2.write_discovery(district, roster=[], batch_id="batch_00099")
        assert (d / "discovery.json").exists() and (d / "candidates.json").exists()
        assert not list(d.glob("*.tmp"))

    def test_discovery_json_is_written_last(self, tmp_path, monkeypatch):
        # reconcile() keys "done" on discovery.json existing — a crash between the two writes
        # must leave the district re-runnable (candidates present, discovery absent).
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        order = []
        real = D2._atomic_write_json

        def spy(path, doc):
            order.append(path.name)
            real(path, doc)

        monkeypatch.setattr(D2, "_atomic_write_json", spy)
        district = {"district_id": "D4", "name": "Orderville", "state": "IA", "domain": "o.org"}
        D2.write_discovery(district, roster=[], batch_id="batch_00099")
        assert order == ["candidates.json", "discovery.json"]


class TestMergeRetrySurvivesCrash:
    """Review finding on #265: a crash between the candidates and discovery writes on a
    merge=True redo must not cause the retry to discard the union (the orphaned
    candidates.json) or the prior schools (living only in the newest renamed-aside file)."""

    @staticmethod
    def _roster(url):
        return [{"school_id": "s1", "school": "Fresh High", "bands": ["high"],
                 "query": "q", "queries": ["q"],
                 "wave1_raw_urls": [url], "wave1_provider": "brightdata",
                 "wave1_providers": ["brightdata"],
                 "wave1_gated": [{"url": url, "kept": True, "reason": "on-domain",
                                  "provider": "brightdata"}],
                 "wave2_invoked": False, "wave2_raw_urls": [], "wave2_gated": []}]

    def test_orphaned_candidates_union_survives_retry(self, tmp_path, monkeypatch):
        import json
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        district = {"district_id": "D5", "name": "Crashville", "state": "IA", "domain": "c.org"}
        # Round 1 completes normally.
        d = D2.write_discovery(district, self._roster("http://c.org/round1"), "batch_1")
        # Simulate a crashed round 2: rename-aside already happened, the union candidates.json
        # was written, but discovery.json was never rewritten (the #265 crash window).
        (d / "discovery.json").rename(d / "discovery.20990101T000000Z.json")
        cands = json.loads((d / "candidates.json").read_text())
        cands["candidates"].append({"url": "http://c.org/round2", "schools": ["Fresh High"],
                                    "tools": ["serper"], "batch_id": "batch_2"})
        (d / "candidates.json").write_text(json.dumps(cands))
        # The retry (round 3, merge=True) must union in BOTH prior rounds' candidates and
        # recover round 1's schools from the aside file.
        D2.write_discovery(district, self._roster("http://c.org/round3"), "batch_3", merge=True)
        urls = {c["url"] for c in json.loads((d / "candidates.json").read_text())["candidates"]}
        assert {"http://c.org/round1", "http://c.org/round2", "http://c.org/round3"} <= urls
        schools = json.loads((d / "discovery.json").read_text())["schools"]
        assert schools and schools[0]["school_id"] == "s1"   # recovered via the aside fallback

    def test_orphaned_candidates_renamed_aside_not_clobbered(self, tmp_path, monkeypatch):
        import json
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        district = {"district_id": "D6", "name": "Orphanville", "state": "IA", "domain": "o.org"}
        d = D2.lea_dir("D6", "Orphanville")
        d.mkdir(parents=True)
        # An orphaned candidates.json with NO discovery.json (first-run crash in the window).
        (d / "candidates.json").write_text(json.dumps(
            {"district_id": "D6", "candidates": [{"url": "http://o.org/orphan"}]}))
        D2.write_discovery(district, self._roster("http://o.org/fresh"), "batch_9")
        # write-once in spirit: the orphan was renamed aside, not overwritten in place
        assert list(d.glob("candidates.*.json")), "orphaned candidates.json must be preserved"


class TestWave1ProviderAccounting:
    """Review finding on #341: an empty-but-successful answer still counts as serving, and a
    failed final query must not be double-counted or misattributed."""

    def test_empty_result_provider_still_listed(self):
        roster = D2.build_roster(_fu_district("widen_queries"))
        calls = []

        def fake_search(q, domain):
            calls.append(q)
            if len(calls) == 1:
                return ("brightdata", [])          # ran fine, found nothing (the common case)
            return ("serper", [f"http://d.org/x{len(calls)}"])

        D2.run_wave1(roster, "d.org", fake_search)
        assert roster[0]["wave1_providers"] == ["brightdata", "serper"]

    def test_failed_query_provider_not_listed(self):
        roster = D2.build_roster(_fu_district("widen_queries"))
        calls = []

        def fake_search(q, domain):
            calls.append(q)
            if len(calls) == 1:
                return ("brightdata", ["http://d.org/a"])
            raise RuntimeError("network blip")     # every later query fails

        D2.run_wave1(roster, "d.org", fake_search)
        r = roster[0]
        assert r["wave1_providers"] == ["brightdata"]   # the failed attempts served nothing
        assert r["wave1_provider"] == "brightdata"      # last SUCCESSFUL query's provider
