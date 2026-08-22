"""#672 criterion 1: an escalation rung that keeps FEWER candidates than the rung before it must
be VISIBLE and RECORDED, never indistinguishable from a rung that simply found nothing.

Background (measured, not assumed --
`docs/technical-notes/production-quality-control-research/2026-08-21-geo-ladder-regression-measure.py`):
over the live corpus, 10 of 56 consecutive rung pairs kept fewer candidates than their predecessor.
Eight are #719's own evidence set (a geo rung composed for a district that HAS a usable scoping
domain -- no longer composable since `630f2a5`). One is a plain domain-scoped rung that simply
returned fewer keepers. One is the mechanism #719 did NOT fix: Wyandanch `3631800`, batch_00034 ->
batch_00035, where a SUCCESSFUL derivation (share 0.400) was diluted below the 0.4 threshold
(0.179) by the widened rung's 3.8x larger result set, failing closed and discarding all 109 raw
URLs -- five of them on the district's own confirmed domain.

Note what these tests do and do not pin. They pin DETECTION. Whether a diluted rung should fall
back to the prior rung's derived host is a scoping-POLICY question (it would gate on an unconfirmed
`discovered_domain` proposal) and is deliberately left open.
"""
import json

import pytest

from infrastructure.acquisition.stage2_discover import discover_stage2 as D2


def _school(sid, kept, raw=None, wave2_kept=0):
    """A discovery.json school entry with `kept` wave-1 keepers out of `raw` gated results."""
    raw = kept + 2 if raw is None else raw
    return {
        "school_id": sid, "school": f"School {sid}", "bands": ["high"], "query": "q",
        "wave1_raw_urls": [f"https://h{i}.example/{sid}" for i in range(raw)],
        "wave1_gated": [{"url": f"https://h{i}.example/{sid}", "kept": i < kept,
                         "reason": "on-domain" if i < kept else "off-district"}
                        for i in range(raw)],
        "wave2_invoked": False, "wave2_raw_urls": [],
        "wave2_gated": [{"url": "https://w2.example/x", "kept": True}] * wave2_kept,
        "outcome": "found" if (kept or wave2_kept) else "manual_flag",
    }


# ------------------------------------------------------------------ the pure comparison
def test_kept_in_counts_both_waves():
    assert D2.kept_in(_school("s1", kept=3)) == 3
    assert D2.kept_in(_school("s1", kept=3, wave2_kept=2)) == 5
    assert D2.kept_in(_school("s1", kept=0)) == 0


def test_a_rung_that_keeps_fewer_is_reported():
    prior = [_school("s1", kept=4), _school("s2", kept=6)]
    new = [_school("s1", kept=1), _school("s2", kept=2)]
    reg = D2.rung_regression(prior, new)
    assert reg is not None
    assert (reg["kept_before"], reg["kept_after"]) == (10, 3)
    assert reg["n_schools_compared"] == 2
    assert reg["schools_zeroed"] == []


def test_schools_that_lost_every_candidate_are_named():
    prior = [_school("s1", kept=4), _school("s2", kept=6)]
    new = [_school("s1", kept=0, raw=31), _school("s2", kept=0, raw=26)]
    reg = D2.rung_regression(prior, new)
    assert reg["schools_zeroed"] == ["s1", "s2"]
    assert reg["kept_after"] == 0


def test_an_improving_or_equal_rung_is_not_reported():
    prior = [_school("s1", kept=2)]
    assert D2.rung_regression(prior, [_school("s1", kept=5)]) is None
    assert D2.rung_regression(prior, [_school("s1", kept=2)]) is None


def test_a_first_rung_has_nothing_to_compare_against():
    assert D2.rung_regression([], [_school("s1", kept=0)]) is None
    assert D2.rung_regression([_school("s1", kept=3)], []) is None


def test_comparison_is_scoped_to_the_schools_this_rung_requeried():
    """A follow-up MERGE unions the prior round into the doc, so a whole-document comparison could
    never regress -- the union is >= the prior by construction. That is a comparison of the
    post-state with itself, the exact shape the repo's standing lesson calls a measurement that
    cannot fail. Only the re-queried subset answers the question."""
    prior = [_school("s1", kept=4), _school("s2", kept=9)]
    # This rung re-queried s1 only; s2 is carried over untouched and must not mask s1's loss.
    new = [_school("s1", kept=0, raw=31)]
    reg = D2.rung_regression(prior, new)
    assert reg is not None, "s2's carried-over 9 keepers must not hide s1 going to zero"
    assert (reg["kept_before"], reg["kept_after"], reg["n_schools_compared"]) == (4, 0, 1)


def test_a_school_absent_from_the_prior_rung_is_ignored():
    """A newly added school has no predecessor to be worse than -- counting it would manufacture
    a phantom regression on any roster that grew."""
    assert D2.rung_regression([_school("s1", kept=2)],
                              [_school("s1", kept=2), _school("s9", kept=0)]) is None


# ------------------------------------------------------------------ the wiring
def _district():
    return {"district_id": "3631800", "name": "WYANDANCH UNION FREE SCHOOL DISTRICT",
            "state": "NY", "domain": "", "band_processing_order": ["high"],
            "schools_by_band": {"high": {"schools": [{"school_id": "s1", "name": "Wyandanch HS"}]}}}


def _roster_with(kept, raw):
    """A roster shaped like run_wave1's output, with `kept` of `raw` gated URLs kept."""
    return [{
        "school_id": "s1", "school": "Wyandanch HS", "bands": ["high"], "query": "q",
        "wave1_raw_urls": [f"https://h{i}.example/x" for i in range(raw)],
        "wave1_provider": "brightdata", "wave1_providers": ["brightdata"],
        "wave1_gated": [{"url": f"https://h{i}.example/x", "kept": i < kept} for i in range(raw)],
        "wave2_invoked": False, "wave2_raw_urls": [], "wave2_gated": [],
    }]


@pytest.fixture
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(D2, "RAW_DIR", tmp_path, raising=False)
    monkeypatch.setattr(D2.paths, "RAW_CAPTURES", tmp_path)
    # finish_district projects the freshly built docs into the DB cache (#616) -- no Postgres here.
    monkeypatch.setattr(D2.CI, "cache_discovery_docs", lambda *a, **k: None)
    return tmp_path


@pytest.fixture
def inmem_registry():
    """A plain in-memory registry: finish_district records straight into the dict it is handed,
    so no DS.load/DS.save swap is needed (mirrors test_stage2_headless.py's fixture, minus the
    run_batch plumbing this file does not exercise)."""
    return {"schema_version": 2, "districts": {}, "_events": []}


def test_discovery_json_records_the_regression(_isolated):
    """The falsifier for criterion 1, in the shape the live Wyandanch pair had: rung 1 keeps 10 of
    36, rung 2 finds 109 raw and keeps 0. Must fail against a build with no rung_regression block."""
    ddir = D2.write_discovery(_district(), _roster_with(kept=10, raw=36), "batch_00034")
    assert "rung_regression" not in json.loads((ddir / "discovery.json").read_text()), \
        "the FIRST rung has no predecessor and must not claim a regression"

    ddir = D2.write_discovery(_district(), _roster_with(kept=0, raw=109), "batch_00035")
    doc = json.loads((ddir / "discovery.json").read_text())
    reg = doc.get("rung_regression")
    assert reg is not None, "a rung that went 10 kept -> 0 kept must say so in the receipt"
    assert (reg["kept_before"], reg["kept_after"]) == (10, 0)
    assert reg["schools_zeroed"] == ["s1"]


def test_a_better_rung_writes_no_regression_block(_isolated):
    D2.write_discovery(_district(), _roster_with(kept=2, raw=10), "batch_00034")
    ddir = D2.write_discovery(_district(), _roster_with(kept=7, raw=40), "batch_00035")
    assert "rung_regression" not in json.loads((ddir / "discovery.json").read_text())


def test_the_prior_rung_is_read_even_without_merge(_isolated):
    """Detection must not depend on merge=True: a domain-scoped rung regressed in the live corpus
    (`0101920` batch_00013 -> batch_00026, 322 -> 309) with no geo derivation involved at all."""
    D2.write_discovery(_district(), _roster_with(kept=5, raw=20), "batch_00013", merge=False)
    ddir = D2.write_discovery(_district(), _roster_with(kept=3, raw=20), "batch_00026", merge=False)
    doc = json.loads((ddir / "discovery.json").read_text())
    assert doc["rung_regression"]["kept_before"] == 5
    assert doc["rung_regression"]["kept_after"] == 3


# ------------------------------------------------------------------ the durable trace
def test_the_regression_reaches_the_state_event_note(_isolated, inmem_registry):
    """#672 criterion 1's "visible and recorded" half. The receipt on disk is the audit trail; the
    state_event note is what a later reader actually sees. #734 made the geo derivation failure
    durable for exactly this reason -- the job log dies with the process -- and a rung regression
    needs the same treatment, MORE so because most of them never reach manual_flag_all: the
    measured corpus lost keepers across found_all -> found_partial transitions, which read as
    ordinary progress."""
    D2.finish_district(_district(), _roster_with(kept=10, raw=36), "batch_00034", inmem_registry)
    D2.finish_district(_district(), _roster_with(kept=0, raw=109), "batch_00035", inmem_registry)
    notes = [e.get("note") or "" for e in inmem_registry.get("_events", [])
             if e.get("district_id") == "3631800"]
    assert any("rung_regression" in n and "10 -> 0" in n for n in notes), notes
    assert any("lost every candidate" in n for n in notes)


def test_a_geo_refusal_and_a_regression_are_both_reported(_isolated, inmem_registry):
    """Wyandanch was BOTH. A note that substituted one for the other would drop half the diagnosis,
    so the two are appended, not exclusive."""
    D2.finish_district(_district(), _roster_with(kept=10, raw=36), "batch_00034", inmem_registry)
    d = {**_district(), "_geo_refused": 109}
    D2.finish_district(d, _roster_with(kept=0, raw=109), "batch_00035", inmem_registry)
    note = [e.get("note") or "" for e in inmem_registry.get("_events", [])
            if e.get("district_id") == "3631800"][-1]
    assert "geo_derivation_failed" in note and "rung_regression" in note, note


# ------------------------------------------------------------------ review findings (PR #872)
def test_878_duplicate_prior_school_ids_are_aggregated_and_surfaced():
    """#878: a dict comprehension keyed on school_id kept only the LAST entry, so a prior doc
    carrying the same school twice produced a wrong kept_before and an unauditable verdict.

    Aggregating is the honest answer to "what did the prior rung keep for this school", and the
    anomaly is RECORDED rather than raised — this runs mid-batch, and halting a live capture over
    a duplicate in a historical manifest would trade a cosmetic problem for a real one.
    """
    prior = [_school("s1", kept=3), _school("s1", kept=4), _school("s2", kept=2)]
    new = [_school("s1", kept=1), _school("s2", kept=2)]
    reg = D2.rung_regression(prior, new)
    assert reg is not None
    # last-write-wins would have read s1's prior as 4, not 7 -> kept_before 6, not 9
    assert reg["kept_before"] == 9, "both s1 entries must count, not just the one that sorts last"
    assert reg["kept_after"] == 3
    assert reg["duplicate_prior_school_ids"] == ["s1"], "the anomaly must be visible in the receipt"


def test_878_the_clean_case_records_no_duplicate_key():
    reg = D2.rung_regression([_school("s1", kept=4)], [_school("s1", kept=1)])
    assert "duplicate_prior_school_ids" not in reg, "no anomaly, no noise in the receipt"


def test_877_the_prior_document_is_read_once(_isolated, monkeypatch):
    """#877: write_discovery parsed the same discovery.json twice on every merge — once for the
    rung comparison and again inside the merge branch."""
    D2.write_discovery(_district(), _roster_with(kept=5, raw=20), "batch_00034")
    calls = []
    real = D2._prior_doc

    def counting(d, live, stem):
        calls.append(stem)
        return real(d, live, stem)

    monkeypatch.setattr(D2, "_prior_doc", counting)
    D2.write_discovery(_district(), _roster_with(kept=2, raw=30), "batch_00035", merge=True)
    assert calls.count("discovery") == 1, f"discovery.json parsed {calls.count('discovery')}x: {calls}"
