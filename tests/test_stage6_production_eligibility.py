"""#679 (epic #617) — production-dispatch selection is provenance-AWARE, not provenance-blind.

`release.best_send` / the dispatch-time narrowing passes used to optimise WITHOUT the eligibility
constraint the freeze guard enforces: a benchmark-provenance rep (capture source 'benchmark_gt',
structurally incapable of riding in a production dispatch) could still win a "best" contest — and
on Bangor (`2302820`) the injected `district_hub_by_band` tied its fresh twin on both tiebreak
terms, won by iteration order, and hub-priority held the fresh capture of the SAME page. Deselecting
the winner (the guard's own instruction) left the district with ZERO sends.

The rule (Ian, 2026-07-28): while `dispatch_type='production'`, a benchmark-provenance rep is
excluded from the DEFAULT send set — HELD (visible, badged), never dropped — applied BEFORE every
narrowing pass so none of them ever crowns an ineligible candidate. An explicit benchmark dispatch
re-admits them (the Council Lab opt-in). NOT a reversal of #662 decision 4: display (badge, never
hide) and selection (eligibility) are different axes.

DB-free tests follow test_stage6_dispatch_bridge's convention (session=None, readers monkeypatched);
the govdb tests exercise the REAL provenance path (capture.source joined through record) — the
Bangor acceptance test among them is the falsifier the issue names.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import stage6_dispatch as BR
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage6_handoff import handoff as HND
from tests import benchmark_seed as BSEED

govdb = pytest.mark.govdb

REASON = BR.INELIGIBLE_PRODUCTION_REASON


# ---------------------- DB-free (readers + provenance monkeypatched) ----------------------
def _rec(rec_key, label, n_times=26, year=None, schools=(), url=None):
    sig = {"content_school_year": f"{year}-{(year + 1) % 100:02d}" if year else None}
    return {"rec_key": rec_key, "url": url or f"http://x/{rec_key}", "tier": "A", "category": None,
            "signals": sig, "is_emergent": 0, "intended_schools": list(schools),
            "label": label, "facets": {},
            "reps": [{"source": "extracted", "filename": "e.txt", "file_kind": "text",
                      "n_chars": 1000, "n_times": n_times, "usable": 1}]}


def _patch(monkeypatch, records, flagged=frozenset()):
    monkeypatch.setattr(REL, "load_district",
                        lambda s, d: {"district_id": d, "name": "X", "state": "ZZ",
                                      "district_dir": "x", "labeled_topology": "mixed",
                                      "nces_denominator": {"total": 3, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, d: records)
    monkeypatch.setattr(BR.BM, "benchmark_provenance_rec_keys",
                        lambda s, keys: {k for k in keys if k in flagged})


def test_the_bangor_tie_the_fresh_hub_wins_under_production(monkeypatch):
    """THE acceptance test (issue #679): two `district_hub_by_band` records tied on both hub-tiebreak
    terms (year unknown, equal density), the INJECTED one first in iteration order — exactly Bangor's
    `fa6e7dd32d` vs `d08b186269`. Under a production dispatch the fresh hub must be the one send;
    before the fix `max()` crowned the injected copy and hub-priority held the fresh one, so
    deselecting the winner left zero sends."""
    records = [_rec("d:gt", "district_hub_by_band"),      # injected copy FIRST — the tie must not
               _rec("d:fresh", "district_hub_by_band")]   # be broken by iteration order
    _patch(monkeypatch, records, flagged={"d:gt"})
    _, out = BR.district_release_input(None, "D679")
    by = {r["rec_key"]: r for r in out}
    assert by["d:fresh"]["decision"] == "send"            # the fresh hub carries the dispatch
    assert by["d:gt"]["decision"] == "hold"               # excluded, never dropped
    assert by["d:gt"]["reason"] == REASON
    assert [r["rec_key"] for r in out if r["decision"] == "send"] == ["d:fresh"]


def test_eligibility_applies_before_every_narrowing_pass(monkeypatch):
    """Ordering is the fix's load-bearing property: an ineligible rep must be invisible to
    prefer-recent too, or a NEWER injected sibling holds the district's only fresh evidence
    (`stale-sibling`) while eligibility then removes the injected winner — zero sends again, by a
    different pass than Bangor's."""
    records = [_rec("d:gt", "school_bell_table", year=2025, schools=["HS"]),
               _rec("d:fresh", "school_bell_table", year=2023, schools=["HS"])]
    _patch(monkeypatch, records, flagged={"d:gt"})
    _, out = BR.district_release_input(None, "D679")
    by = {r["rec_key"]: r for r in out}
    assert by["d:fresh"]["decision"] == "send"            # the older-but-fresh sibling still sends
    assert by["d:gt"]["reason"] == REASON


def test_worcester_shape_default_selection_excludes_gt_reps(monkeypatch):
    """The deselect-busywork harm: per-school topology, no hubs — every gt:// target-labeled send is
    excluded from the default set (Worcester composes 26, not 34), each still present in the package
    for the console to render badged."""
    records = [_rec(f"d:fresh{i}", "school_bell_table") for i in range(3)] + \
              [_rec(f"d:gt{i}", "school_start_end_list") for i in range(2)]
    _patch(monkeypatch, records, flagged={"d:gt0", "d:gt1"})
    pkg = BR.build_handoff_package(session=None, district_ids=["D679"])
    block = pkg["districts"][0]
    sends = [r for r in block["records"] if r["decision"] == "send"]
    assert {r["rec_key"] for r in sends} == {"d:fresh0", "d:fresh1", "d:fresh2"}
    held = [r for r in block["records"] if r["reason"] == REASON]
    assert {r["rec_key"] for r in held} == {"d:gt0", "d:gt1"}
    assert all(r["reps"] == [] for r in held)             # held reps are never routed/priced


def test_a_benchmark_dispatch_readmits_them_and_flips_the_identity(monkeypatch):
    """The Council Lab opt-in: `dispatch_type='benchmark'` re-admits gt:// reps to selection — and
    the two packages compute DIFFERENT identities, so a preview-as-production / freeze-as-benchmark
    flip 409s (issue #37) instead of silently re-selecting."""
    records = [_rec("d:fresh", "school_bell_table"), _rec("d:gt", "school_start_end_list")]
    _patch(monkeypatch, records, flagged={"d:gt"})
    prod = BR.build_handoff_package(session=None, district_ids=["D679"])
    bench = BR.build_handoff_package(session=None, district_ids=["D679"],
                                     dispatch_type=BM.DISPATCH_BENCHMARK)
    prod_sends = {r["rec_key"] for r in prod["districts"][0]["records"] if r["decision"] == "send"}
    bench_sends = {r["rec_key"] for r in bench["districts"][0]["records"] if r["decision"] == "send"}
    assert prod_sends == {"d:fresh"}
    assert bench_sends == {"d:fresh", "d:gt"}
    assert not any(r["reason"] == REASON for r in bench["districts"][0]["records"])
    assert HND.package_identity(prod) != HND.package_identity(bench)


# ---------------------- the freeze guard reads SELECTED reps (#679 scope fix) ----------------------
def _guard_pkg(records, district_id="ZZ679G"):
    return {"districts": [{"district_id": district_id, "records": records}],
            "cost": {"total_usd": 0.0, "n_reps": 0, "provenance": "bootstrap"},
            "verified_only": False, "dispatch_type": BM.DISPATCH_PRODUCTION}


@govdb
def test_a_held_gt_rep_no_longer_refuses_the_freeze(signals):
    """`benchmark_reps_in_package` used to key on EVERY package record — but a held record dispatches
    nothing, and the eligibility pass HOLDS ineligible gt:// reps by design; flagging those holds
    would re-refuse the exact dispatch the hold made freezable."""
    s = signals
    BSEED.seed_rep(s, "ZZ679G", "ZZ679G:gt", "g679", BM.BENCHMARK_CAPTURE_SOURCE)
    BSEED.seed_rep(s, "ZZ679G", "ZZ679G:ok", "k679", "discovered")
    pkg = _guard_pkg([
        {"rec_key": "ZZ679G:gt", "decision": "hold", "reason": REASON, "reps": []},
        {"rec_key": "ZZ679G:ok", "decision": "send",
         "reps": [{"file": "e.txt", "kind": "text", "councils": ["low-cost-text"]}]}])
    assert BR.benchmark_reps_in_package(s, pkg) == []
    BR.assert_dispatch_type_allowed(s, pkg)               # must not raise
    # ...while a gt:// rep that IS selected (a hand-built back-edge package) still refuses:
    bad = _guard_pkg([{"rec_key": "ZZ679G:gt", "decision": "send",
                       "reps": [{"file": "e.txt", "kind": "text", "councils": ["low-cost-text"]}]}])
    with pytest.raises(ValueError, match="ZZ679G:gt"):
        BR.assert_dispatch_type_allowed(s, bad)


# ---------------------- govdb: the REAL provenance path, end to end ----------------------
@pytest.fixture
def signals(gov_session):
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    gdb.init_precious_schema()
    BS.ensure_signal_schema(gov_session)
    CI.ensure_cache_schema(gov_session)
    return gov_session


def _seed_release_district(s, did, recs):
    """A composable release-path district: the district row + per-record label/representation rows on
    top of the shared record+capture seeder (#661). `recs` = [(rec_key, hash, source, label,
    sort_score)] — higher sort_score lists FIRST (the iteration-order knob the Bangor tie needs)."""
    s.execute(text(
        "INSERT INTO district (district_id, name, state, district_dir, labeled_topology, "
        "nces_school_count) VALUES (:d, :n, 'ZZ', :dd, 'mixed', 3) "
        "ON CONFLICT (district_id) DO NOTHING"),
        {"d": did, "n": f"ZZ {did}", "dd": f"{did}_x"})
    for rec_key, hash_, source, label, score in recs:
        BSEED.seed_rep(s, did, rec_key, hash_, source)
        s.execute(text("UPDATE record SET sort_score = :sc WHERE rec_key = :k"),
                  {"sc": score, "k": rec_key})
        s.execute(text(
            "INSERT INTO label (rec_key, primary_label, status) VALUES (:k, :l, 'labeled') "
            "ON CONFLICT (rec_key) DO UPDATE SET primary_label = EXCLUDED.primary_label, "
            "status = 'labeled'"), {"k": rec_key, "l": label})
        s.execute(text(
            "INSERT INTO representation (rec_key, source, filename, file_kind, n_chars, n_times, "
            "usable) VALUES (:k, 'extracted', 'e.txt', 'text', 1000, 26, 1)"), {"k": rec_key})
    s.flush()


@govdb
def test_bangor_acceptance_the_one_send_is_the_fresh_hub(signals):
    """The issue's falsifier on the REAL provenance path (capture.source joined through record): two
    hub records tied on (year, n_times), the injected one iterating first — the production compose
    must select the fresh hub as the district's ONE send, and the resulting package must pass the
    freeze guard it used to refuse."""
    s = signals
    _seed_release_district(s, "ZZ679B", [
        ("ZZ679B:gt", "bg679", BM.BENCHMARK_CAPTURE_SOURCE, "district_hub_by_band", 2.0),
        ("ZZ679B:fresh", "bf679", "discovered", "district_hub_by_band", 1.0)])
    bundle = BR.release_bundle(s, ["ZZ679B"])
    block = bundle.package["districts"][0]
    by = {r["rec_key"]: r for r in block["records"]}
    assert by["ZZ679B:fresh"]["decision"] == "send"
    assert by["ZZ679B:gt"]["decision"] == "hold" and by["ZZ679B:gt"]["reason"] == REASON
    assert block["n_send_reps"] == 1
    assert BR.benchmark_reps_in_package(s, bundle.package) == []
    BR.assert_dispatch_type_allowed(s, bundle.package)    # the freeze this issue exists to unblock


@govdb
def test_bangor_as_a_benchmark_dispatch_readmits_the_injected_hub(signals):
    """The same district composed as an explicit benchmark A/B: no eligibility hold, and the identity
    differs from the production compose so the preview token can never be reused across the flip."""
    s = signals
    _seed_release_district(s, "ZZ679C", [
        ("ZZ679C:gt", "cg679", BM.BENCHMARK_CAPTURE_SOURCE, "district_hub_by_band", 2.0),
        ("ZZ679C:fresh", "cf679", "discovered", "district_hub_by_band", 1.0)])
    prod = BR.release_bundle(s, ["ZZ679C"]).package
    bench = BR.release_bundle(s, ["ZZ679C"], dispatch_type=BM.DISPATCH_BENCHMARK).package
    assert not any(r["reason"] == REASON
                   for d in bench["districts"] for r in d["records"])
    assert HND.package_identity(prod) != HND.package_identity(bench)


# ---------------------- console visibility (the UI-visibility rule; static-source pin) ----------------------
def test_gate6_console_renders_the_excluded_reps_badged():
    """#662 decision 4 regression pin: exclusion from SELECTION must not become exclusion from
    DISPLAY. The console renders a held-ineligible row (badged, with the re-admit affordance) keyed
    on the server-computed reason — one spelling, pinned here against the Python constant."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/stage6.js").read_text()
    assert 'data-feat="s6-bm-ineligible"' in js
    assert REASON in js                                   # the client keys on the server's spelling
    assert "re-admit" in js                               # the affordance is stated where the human acts
