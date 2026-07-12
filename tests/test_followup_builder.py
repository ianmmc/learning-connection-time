"""#162/#160/#161 (Chunk 4, epic #163) — build_followup_batch shaping: prefer UNTRIED schools for a
re-targeted band, signal query_strategy (new_schools vs widen_queries), and carry 7->3 seed_urls.
NCES readers monkeypatched with synthetic data — no NCES files, no DB."""
from infrastructure.acquisition.stage1_queue import queue_batch as Q1


def _sch(sid, name, band):
    return {"school_id": sid, "name": name, "level": band.capitalize(), "gslo": "09", "gshi": "12",
            "is_charter": "No", "bands": [band]}


def _patch_nces(monkeypatch, index):
    did = next(iter(index))
    monkeypatch.setattr(Q1.S, "lea_info", lambda y: {did: {"name": "Testville", "state": "IA",
                                                            "website": "test.org", "claimed_bands": {"high"}}})
    monkeypatch.setattr(Q1.S, "school_index", lambda y: index)
    monkeypatch.setattr(Q1.S, "school_level_counts", lambda y: {did: {"total": 9, "by_level": {}}})
    monkeypatch.setattr(Q1, "load_enrollment", lambda: {did: 5000})


def test_untried_schools_preferred_and_strategy_is_new_schools(monkeypatch):
    idx = {"D1": {"high": [_sch("s1", "Tried High", "high"), _sch("s2", "Fresh High", "high")]}}
    _patch_nces(monkeypatch, idx)
    doc, skipped = Q1.build_followup_batch(
        "2024_25", "batch_00099", {"D1": ["high"]}, attempted_by_did={"D1": {"s1"}})
    d = doc["districts"][0]
    picked = [s["school_id"] for s in d["schools_by_band"]["high"]["schools"]]
    assert picked == ["s2"]                                     # only the UNTRIED school
    assert d["schools_by_band"]["high"]["query_strategy"] == "new_schools"


def test_all_attempted_falls_back_to_widen_queries(monkeypatch):
    idx = {"D1": {"high": [_sch("s1", "A High", "high"), _sch("s2", "B High", "high")]}}
    _patch_nces(monkeypatch, idx)
    doc, _ = Q1.build_followup_batch(
        "2024_25", "batch_00099", {"D1": ["high"]}, attempted_by_did={"D1": {"s1", "s2"}})
    d = doc["districts"][0]
    picked = {s["school_id"] for s in d["schools_by_band"]["high"]["schools"]}
    assert picked == {"s1", "s2"}                               # no untried -> fall back to the full set
    assert d["schools_by_band"]["high"]["query_strategy"] == "widen_queries"   # -> Stage 2 differentiated


def test_seed_urls_carried_onto_the_district(monkeypatch):
    idx = {"D1": {"high": [_sch("s1", "A High", "high")]}}
    _patch_nces(monkeypatch, idx)
    doc, _ = Q1.build_followup_batch(
        "2024_25", "batch_00099", {"D1": ["high"]},
        seed_urls_by_did={"D1": ["http://x/handbook.pdf", "http://y/bell"]})
    assert doc["districts"][0]["seed_urls"] == ["http://x/handbook.pdf", "http://y/bell"]


def test_no_shaping_args_is_backward_compatible(monkeypatch):
    # no attempted/seed passed -> every school is "untried", strategy new_schools, no seed urls
    idx = {"D1": {"high": [_sch("s1", "A High", "high")]}}
    _patch_nces(monkeypatch, idx)
    doc, _ = Q1.build_followup_batch("2024_25", "batch_00099", {"D1": ["high"]})
    d = doc["districts"][0]
    assert [s["school_id"] for s in d["schools_by_band"]["high"]["schools"]] == ["s1"]
    assert d["schools_by_band"]["high"]["query_strategy"] == "new_schools" and d["seed_urls"] == []


def test_followup_skips_a_blank_domain_district_instead_of_running_unscoped(monkeypatch):
    """#229: a 7->2 rediscover for a district whose NCES website is blank would run UNSCOPED,
    national-scope discovery (the Millard contamination, #227). build_followup_batch must SKIP it
    with the #229 reason, not emit a domain-less district."""
    idx = {"D1": {"high": [_sch("s1", "A High", "high")]}}
    monkeypatch.setattr(Q1.S, "lea_info", lambda y: {"D1": {"name": "Nodomain", "state": "NE",
                                                             "website": "", "claimed_bands": {"high"}}})
    monkeypatch.setattr(Q1.S, "school_index", lambda y: idx)
    monkeypatch.setattr(Q1.S, "school_level_counts", lambda y: {"D1": {"total": 9, "by_level": {}}})
    monkeypatch.setattr(Q1, "load_enrollment", lambda: {"D1": 5000})
    doc, skipped = Q1.build_followup_batch("2024_25", "batch_00099", {"D1": ["high"]})
    assert doc["districts"] == []
    assert skipped == [{"district_id": "D1", "reason": "no usable scoping domain -- would run UNSCOPED discovery (#229)"}]


def test_followup_skips_a_junk_domain_that_normalizes_to_a_nonsense_host(monkeypatch):
    """The raw NCES WEBSITE column carries junk that is non-blank but useless: 'http://N/A' -> host
    'n', physical addresses -> '375 lee st'. These must be refused too -- a bare non-emptiness check
    would let them through into unscoped discovery."""
    idx = {"D1": {"high": [_sch("s1", "A High", "high")]}}
    monkeypatch.setattr(Q1.S, "lea_info", lambda y: {"D1": {"name": "Junk", "state": "NE",
                                                            "website": "http://N/A", "claimed_bands": {"high"}}})
    monkeypatch.setattr(Q1.S, "school_index", lambda y: idx)
    monkeypatch.setattr(Q1.S, "school_level_counts", lambda y: {"D1": {"total": 9, "by_level": {}}})
    monkeypatch.setattr(Q1, "load_enrollment", lambda: {"D1": 5000})
    doc, skipped = Q1.build_followup_batch("2024_25", "batch_00099", {"D1": ["high"]})
    assert doc["districts"] == [] and len(skipped) == 1 and "#229" in skipped[0]["reason"]
