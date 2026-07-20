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


# ---------------------------------------------------------------- build_batch scope axis
def test_build_batch_scope_validation():
    with pytest.raises(ValueError):
        from infrastructure.acquisition.stage1_queue import queue_batch as QB
        QB.build_batch("2024_25", 12, "batch_x", {"districts": {}}, scope="bogus")


def test_scope_combo_validation_geo_composes_first_runs_only():
    """#569 review: benchmark is NEVER geo (a geo batch_00000 would put derived-host discovery
    inside the GT wall); follow-up geo loops arrive via the PR-3 escalation builders only."""
    from infrastructure.acquisition.stage1_queue import queue_batch as QB
    QB.validate_scope_combo("geo", "first-run")            # allowed
    QB.validate_scope_combo("domain", "benchmark")         # allowed
    with pytest.raises(ValueError):
        QB.validate_scope_combo("geo", "benchmark")
    with pytest.raises(ValueError):
        QB.validate_scope_combo("geo", "follow-up")


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
