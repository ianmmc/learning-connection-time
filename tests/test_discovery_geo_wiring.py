"""#164 PR 2 (wiring): geo-scoped discovery end-to-end with injected search — no live SERP.

Covers: geo roster rendering (build_roster geo mode), the wave-1 → derive → re-gate flow
(apply_geo_derivation over a real run_wave1 pass), the fail-closed no-derivation outcome, the
discovery.json `geo_discovery` receipt, and build_batch's scope axis + dual-source admission."""
import json

import pytest

from infrastructure.acquisition.stage2_discover import discover_stage2 as D2


def _district(geo=True):
    d = {"district_id": "3173740", "name": "MILLARD PUBLIC SCHOOLS", "state": "NE",
         "domain": "", "band_processing_order": ["high"],
         "schools_by_band": {"high": {"schools": [
             {"school_id": "s1", "name": "Millard North High School"},
             {"school_id": "s2", "name": "Millard South High School"},
             {"school_id": "s3", "name": "Millard West High School"},
         ]}}}
    if geo:
        d["geo"] = {"city": "OMAHA", "zip": "68137"}
    return d


def test_build_roster_geo_renders_geo_queries():
    roster = D2.build_roster(_district(), geo=True)
    assert all(r["queries"][0].endswith("OMAHA 68137") for r in roster)
    assert all(len(r["queries"]) == 1 for r in roster)   # standard vocabulary, not widened


def test_build_roster_geo_widens_per_query_strategy():
    d = _district()
    d["schools_by_band"]["high"]["query_strategy"] = "widen_queries"
    roster = D2.build_roster(d, geo=True)
    assert all(len(r["queries"]) > 1 for r in roster)    # widened vocabulary, all geo-rendered
    assert all(q.endswith("OMAHA 68137") for r in roster for q in r["queries"])


def _search_that_finds_millard(q, domain):
    """Injected wave-1 search: every school's query returns mostly mpsomaha.org (with www/subdomain
    mixing — the #568 family-merge case) plus national same-name noise."""
    assert domain == ""   # geo mode NEVER passes a scoping domain to the provider
    return ("fake_serp", [
        "https://www.mpsomaha.org/schools/north/bell-schedule",
        "https://mpsomaha.org/schools/handbook.pdf",
        "https://hs.mpsomaha.org/daily-schedule",
        "https://reagan-tx.org/bell-schedule",        # the national noise geo tokens demote
    ])


def test_geo_wave1_derive_regate_keeps_only_the_derived_family():
    roster = D2.build_roster(_district(), geo=True)
    D2.run_wave1(roster, "", _search_that_finds_millard)
    # pre-derivation: fail-closed (the blank-domain refusal is the honest interim state)
    assert all(not g["kept"] for r in roster for g in r["wave1_gated"])
    derived, receipt = D2.apply_geo_derivation(roster)
    assert derived == "mpsomaha.org"                      # family-merged majority (9 of 12 = 75%)
    assert receipt["outcome"] == "derived" and receipt["n_schools"] == 3
    kept = {g["url"] for r in roster for g in r["wave1_gated"] if g["kept"]}
    assert kept == {"https://www.mpsomaha.org/schools/north/bell-schedule",
                    "https://mpsomaha.org/schools/handbook.pdf",
                    "https://hs.mpsomaha.org/daily-schedule"}
    # provider attribution survived the re-gate
    assert all(g.get("provider") == "fake_serp" for r in roster for g in r["wave1_gated"] if g["kept"])


def test_geo_no_derivation_stays_fail_closed():
    def scattered(q, domain):
        # every school hits a different host — no majority, nothing derivable
        return ("fake_serp", [f"https://site-{hash(q) % 97}.org/page"])
    roster = D2.build_roster(_district(), geo=True)
    D2.run_wave1(roster, "", scattered)
    derived, receipt = D2.apply_geo_derivation(roster)
    assert derived is None
    assert all(not g["kept"] for r in roster for g in r["wave1_gated"])   # kept NOTHING
    assert receipt["outcome"] in ("below threshold", "no results")


def test_write_discovery_carries_the_geo_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(D2, "RAW_DIR", tmp_path, raising=False)
    monkeypatch.setattr(D2.paths, "RAW_CAPTURES", tmp_path)
    roster = D2.build_roster(_district(), geo=True)
    D2.run_wave1(roster, "", _search_that_finds_millard)
    derived, receipt = D2.apply_geo_derivation(roster)
    ddir = D2.write_discovery(_district(), roster, "batch_00099", geo_receipt=receipt)
    doc = json.loads((ddir / "discovery.json").read_text())
    assert doc["geo_discovery"]["outcome"] == "derived"
    assert doc["geo_discovery"]["derived_host"] == "mpsomaha.org"
    assert "raw_tally" in doc["geo_discovery"]            # the auditor sees the raw split too


def test_write_discovery_merge_carries_the_prior_geo_receipt_forward(tmp_path, monkeypatch):
    """Review: a later DOMAIN-scoped follow-up merge (geo_receipt=None) must not silently drop the
    district's earlier derivation receipt from the LIVE manifest — the timestamped aside is attempt
    history, not where auditors look."""
    monkeypatch.setattr(D2, "RAW_DIR", tmp_path, raising=False)
    monkeypatch.setattr(D2.paths, "RAW_CAPTURES", tmp_path)
    roster = D2.build_roster(_district(), geo=True)
    D2.run_wave1(roster, "", _search_that_finds_millard)
    derived, receipt = D2.apply_geo_derivation(roster)
    D2.write_discovery(_district(), roster, "batch_00099", geo_receipt=receipt)
    # the follow-up round: domain-scoped, no geo receipt of its own
    d2 = _district(geo=False)
    d2["domain"] = "mpsomaha.org"
    roster2 = D2.build_roster(d2)
    D2.run_wave1(roster2, "mpsomaha.org",
                 lambda q, dom: ("fake_serp", ["https://mpsomaha.org/schools/handbook.pdf"]))
    ddir = D2.write_discovery(d2, roster2, "batch_00100", merge=True, geo_receipt=None)
    doc = json.loads((ddir / "discovery.json").read_text())
    assert doc["geo_discovery"]["derived_host"] == "mpsomaha.org"   # carried, not dropped


def test_discover_district_writes_the_derived_domain_back(tmp_path, monkeypatch):
    """Review: the derived host must land in discovery.json/candidates.json's TOP-LEVEL `domain`
    (the field Stage 3/4 status views read), not only inside the geo_discovery receipt."""
    from infrastructure.acquisition.stage2_discover import headless as H2
    monkeypatch.setattr(D2, "RAW_DIR", tmp_path, raising=False)
    monkeypatch.setattr(D2.paths, "RAW_CAPTURES", tmp_path)
    batch = {"batch_id": "batch_00099", "batch_type": "first-run", "discovery_scope": "geo"}
    district = _district()
    registry: dict = {}
    monkeypatch.setattr(H2.DS, "record_stage", lambda *a, **k: None)
    monkeypatch.setattr(D2.CI, "cache_discovery", lambda ddir: None)   # DB-free test
    H2.discover_district(batch, district, registry,
                         wave1_search=_search_that_finds_millard,
                         wave2_runner=lambda d, residual, dom: None)
    disc = next(tmp_path.rglob("discovery.json"))
    doc = json.loads(disc.read_text())
    assert doc["domain"] == "mpsomaha.org"
    cand = json.loads((disc.parent / "candidates.json").read_text())
    assert cand["domain"] == "mpsomaha.org"


# ---------------------------------------------------------------- build_batch scope axis
def test_build_batch_scope_validation():
    with pytest.raises(ValueError):
        from infrastructure.acquisition.stage1_queue import queue_batch as QB
        QB.build_batch("2024_25", 12, "batch_x", {"districts": {}}, scope="bogus")


def test_scope_combo_validation_keeps_only_the_benchmark_half():
    """#569's benchmark half stands forever: a geo batch_00000 would put derived-host discovery
    inside the GT wall. #646 dropped the TYPE half — see the next test for why."""
    from infrastructure.acquisition.stage1_queue import queue_batch as QB
    QB.validate_scope_combo("geo", "first-run")            # allowed
    QB.validate_scope_combo("domain", "benchmark")         # allowed
    QB.validate_scope_combo("geo", "follow-up")            # #646: allowed now
    with pytest.raises(ValueError) as e:
        QB.validate_scope_combo("geo", "benchmark")
    assert "GT wall" in str(e.value)


def test_a_domainless_already_attempted_district_is_reachable_by_some_composer(monkeypatch):
    """#646 — the STRUCTURAL regression test, written against the intersection rather than the two
    districts that happened to hit it (more will, as districts reach furthest_stage >= 3).

    Three individually-correct rules met in a dead end: a DOMAIN-scoped follow-up refuses a
    domain-less district (#229 — an unscoped rediscover is the #227 contamination), geo is exactly
    what exists for that case but composed first-runs only (#569), and first-run drops an
    already-attempted district. Domain-less AND already-attempted ⇒ no composer would take it.
    MUST FAIL against pre-#646 code, on the middle rule."""
    from infrastructure.acquisition.stage1_queue import queue_batch as QB
    did = "1602100"                                        # West Ada: empty WEBSITE in BOTH CCD vintages
    monkeypatch.setattr(QB.S, "lea_info", lambda year: {
        did: {"name": "JOINT SCHOOL DISTRICT NO. 2", "state": "ID", "website": "", "status": "Open",
              "lea_type": "x", "claimed_bands": {"high"}, "city": "MERIDIAN", "zip": "83642"}})
    monkeypatch.setattr(QB.S, "school_index", lambda year: {
        did: {"high": [{"school_id": "s1", "name": "Rocky Mountain High", "level": "High"}]}})
    monkeypatch.setattr(QB.S, "school_level_counts", lambda year: {})
    monkeypatch.setattr(QB, "load_enrollment", lambda: {})

    # rule 1: the domain-scoped follow-up still refuses it, correctly — that guard is not the bug
    _, skipped = QB.build_followup_batch("2024_25", "b", {did: ["high"]}, scope="domain",
                                         discovered_domains={})
    assert skipped and "#229" in skipped[0]["reason"]

    # rule 2 (the one #646 narrowed) + the compose that was unreachable
    QB.validate_scope_combo("geo", "follow-up")
    doc, skipped = QB.build_followup_batch("2024_25", "b", {did: ["high"]}, scope="geo",
                                           discovered_domains={})
    assert [d["district_id"] for d in doc["districts"]] == [did] and not skipped
    assert doc["discovery_scope"] == "geo"                 # the route is recorded ON the batch


def test_geo_purity_now_rests_on_the_honest_predicate_not_the_batch_type(monkeypatch):
    """What #569's type gate was really standing in for — "don't geo-compose free-form" — is now
    enforced where districts are KNOWN, and enforced better: #719 refuses a geo compose for any
    district that HAS a usable scoping domain. So geo+follow-up can only ever mean the districts geo
    exists for; a free-form geo follow-up over domained districts is still impossible."""
    from infrastructure.acquisition.stage1_queue import queue_batch as QB
    monkeypatch.setattr(QB.S, "lea_info", lambda year: {
        "0503060": {"name": "BENTONVILLE", "state": "AR", "website": "www.bentonvillek12.org",
                    "status": "Open", "lea_type": "x", "claimed_bands": {"high"},
                    "city": "BENTONVILLE", "zip": "72712"}})
    monkeypatch.setattr(QB.S, "school_index", lambda year: {
        "0503060": {"high": [{"school_id": "s1", "name": "Bentonville High", "level": "High"}]}})
    monkeypatch.setattr(QB.S, "school_level_counts", lambda year: {})
    monkeypatch.setattr(QB, "load_enrollment", lambda: {})
    doc, skipped = QB.build_followup_batch("2024_25", "b", {"0503060": ["high"]}, scope="geo",
                                           discovered_domains={})
    assert not doc["districts"]
    assert "geo compose refused" in skipped[0]["reason"] and "bentonvillek12.org" in skipped[0]["reason"]


# ---------------------------------------------------------------- follow-up geo scope (PR 3a)
def test_followup_geo_scope_skips_the_domain_guard_and_carries_geo_fields(monkeypatch):
    from infrastructure.acquisition.stage1_queue import queue_batch as QB
    monkeypatch.setattr(QB.S, "lea_info", lambda year: {
        "3173740": {"name": "MILLARD", "state": "NE", "website": "", "status": "Open",
                    "lea_type": "x", "claimed_bands": {"high"}, "city": "OMAHA", "zip": "68137"}})
    monkeypatch.setattr(QB.S, "school_index", lambda year: {
        "3173740": {"high": [{"school_id": "s1", "name": "Millard North"}]}})
    monkeypatch.setattr(QB.S, "school_level_counts", lambda year: {})
    monkeypatch.setattr(QB, "load_enrollment", lambda: {})
    # domain scope refuses (blank NCES website, nothing confirmed)...
    doc, skipped = QB.build_followup_batch("2024_25", "batch_x", {"3173740": ["high"]})
    assert not doc["districts"] and skipped[0]["reason"].startswith("no usable scoping domain")
    # ...geo scope composes, with the geo fields and no domain
    doc, skipped = QB.build_followup_batch("2024_25", "batch_x", {"3173740": ["high"]}, scope="geo")
    assert doc["discovery_scope"] == "geo" and not skipped
    d = doc["districts"][0]
    assert d["domain"] == "" and d["geo"] == {"city": "OMAHA", "zip": "68137"}
    # ...and a CONFIRMED discovered domain returns the district to DOMAIN follow-ups
    doc, skipped = QB.build_followup_batch("2024_25", "batch_x", {"3173740": ["high"]},
                                           discovered_domains={"3173740": "mpsomaha.org"})
    assert not skipped and doc["districts"][0]["domain"] == "mpsomaha.org"
    assert doc["districts"][0]["domain_source"] == "discovered"
    assert doc["discovery_scope"] == "domain"
