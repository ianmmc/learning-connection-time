"""Stage 6 gate@6 console API (REQ-101) — HTTP wiring for the handoff view.

Endpoint wiring is tested DB-free (monkeypatch the session_scope + the H6 bridge — the bridge itself is
unit-tested in test_stage6_dispatch.py). Two read-only endpoints (candidates / handoffs) get a govdb
smoke test against the real governance DB.
"""
import contextlib

import pytest
from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server as SRV

client = TestClient(SRV.app)


@contextlib.contextmanager
def _fake_scope():
    yield "SESS"


# ----------------------------- endpoint wiring (DB-free) -----------------------------
def test_preview_returns_the_package(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    pkg = {"districts": [], "cost": {"total_usd": 0.0, "n_reps": 0, "provenance": "bootstrap"}}
    monkeypatch.setattr(SRV.H6, "build_handoff_package", lambda con, ids, *a, **k: pkg)
    r = client.post("/api/handoff/preview", json={"district_ids": ["X"]})
    assert r.status_code == 200
    assert r.json()["cost"]["provenance"] == "bootstrap"


def test_dispatch_returns_summary(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    doc = {"handoff_hash": "abc123", "created_at": "2026-06-30T00:00:00Z",
           "districts": [{"district_id": "0100810"}],
           "cost": {"total_usd": 0.00102, "n_reps": 1, "provenance": "bootstrap"}}
    monkeypatch.setattr(SRV.H6, "dispatch_handoff", lambda con, ids, **k: (doc, "/data/handoffs/x.json"))
    r = client.post("/api/handoff/dispatch", json={"district_ids": ["0100810"], "actor": "ian"})
    assert r.status_code == 200
    body = r.json()
    assert body["handoff_hash"] == "abc123"
    assert body["handoff_id"].startswith("handoff_abc123_")
    assert body["n_reps"] == 1 and body["n_districts"] == 1
    assert body["provenance"] == "bootstrap" and body["path"] == "/data/handoffs/x.json"


def test_dispatch_requires_districts():
    r = client.post("/api/handoff/dispatch", json={"district_ids": []})
    assert r.status_code == 400


# ----------------------------- read-only smoke (real DB) -----------------------------
@pytest.mark.govdb
@pytest.mark.integration
def test_candidates_and_handoffs_lists():
    c = client.get("/api/handoff/candidates")
    assert c.status_code == 200 and isinstance(c.json(), list)
    if c.json():
        row = c.json()[0]
        assert "district_id" in row and "n_send" in row and "n_hold" in row
        # #171 + #198 review: dispatch-history signal + server-computed benchmark flag per candidate
        for k in ("batch_id", "n_dispatched", "last_dispatched_at", "n_extracted", "is_benchmark"):
            assert k in row
    h = client.get("/api/handoffs")
    assert h.status_code == 200 and isinstance(h.json(), list)


@pytest.mark.integration
def test_candidates_badge_holds_pre_2017_tier_a_via_the_241_floor(gov_session, monkeypatch):
    """#241 (code-review fix): the n_send badge must NOT count an unlabeled tier-A record whose
    content_school_year is pre-2017-18 — decide() HOLDs it, so it belongs in n_hold. Seeds three
    unlabeled tier-A records (rolled back) and checks the SQL mirrors the floor."""
    import contextlib
    import json as _json

    from sqlalchemy import text as _text
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    did = "CAND241"
    gov_session.execute(_text(
        "INSERT INTO district (district_id, name, district_dir, labeled_topology, nces_school_count, n_records)"
        " VALUES (:d, 'T', 'cand241_dir', 'per_school', 3, 3)"), {"d": did})
    for h, csy in [("stale", "2012-13"), ("recent", "2025-26"), ("noyear", None)]:
        sig = {"n_times": 4, **({"content_school_year": csy} if csy else {})}
        gov_session.execute(BS.INSERT_RECORD, {
            "rec_key": f"{did}:{h}", "district_id": did, "district_dir": "cand241_dir", "url": f"http://x/{h}",
            "hash": h, "kind": "html", "final_url": None, "content_hash": h, "duplicate_of": None,
            "tier": "A", "sort_score": 50.0, "category_hypothesis": "school_bell_table",
            "signals_json": _json.dumps(sig), "intended_schools_json": "[]",
            "candidate_tools_json": "[]", "is_emergent": 0})
    # no labels -> all three are unlabeled tier-A

    @contextlib.contextmanager
    def _scope():
        yield gov_session                      # same (uncommitted) txn, so the endpoint sees the seed
    monkeypatch.setattr(SRV.gdb, "session_scope", _scope)
    row = {r["district_id"]: r for r in SRV.handoff_candidates()}[did]
    assert row["n_send"] == 2                   # recent + unknown-year send; the pre-2017 one does NOT
    assert row["n_hold"] == 1                   # the pre-2017-18 stale record is floor-held
    gov_session.rollback()


@pytest.mark.integration
def test_candidates_n_extracted_counts_benchmark_run_kind_too(gov_session, monkeypatch):
    """#662 review: n_extracted must NOT be scoped to run_kind='production'. It answers "has
    extraction work already happened here" — the signal #171 built to prevent a wasted re-dispatch —
    and a district whose only extractions are run_kind='benchmark' (the historical GT harness, or a
    future Council Lab A/B) has just as truly been touched. Scoping this to production would have
    made all 27 batch_00000 districts read n_extracted=0 the moment the #662 migration landed,
    despite carrying 940+ human-verified facts — inviting the exact wasted redispatch this signal
    exists to prevent. `is_benchmark` (batch membership) stays the separate nuance signal."""
    import contextlib
    from sqlalchemy import text as _text
    from infrastructure.acquisition.stage6_handoff import models as M6   # noqa: F401 (register)
    from infrastructure.acquisition.stage7_extract import models as M7   # noqa: F401 (register)
    SRV.gdb.init_precious_schema()
    did = "CANDBENCH662"
    gov_session.execute(_text(
        "INSERT INTO district (district_id, name, district_dir, labeled_topology, nces_school_count, "
        "n_records) VALUES (:d, 'T', 'candbench662_dir', 'per_school', 1, 0)"), {"d": did})
    gov_session.execute(_text(
        "INSERT INTO extraction (handoff_hash, district_id, run_kind, created_at, created_by, "
        "n_reps, n_calls, n_judge_calls, n_errors, prompt_tokens, completion_tokens, cost_usd, "
        "n_accepted, n_unresolved) VALUES ('candbench662h', :d, 'benchmark', 'now', 'zz', 1, 1, 0, "
        "0, 0, 0, 0.0, 3, 0)"), {"d": did})
    gov_session.flush()

    @contextlib.contextmanager
    def _scope():
        yield gov_session
    monkeypatch.setattr(SRV.gdb, "session_scope", _scope)
    row = {r["district_id"]: r for r in SRV.handoff_candidates()}[did]
    assert row["n_extracted"] == 1, "a run_kind='benchmark' extraction must still count as extracted"
    gov_session.rollback()


# ----------------------------- preview→freeze staleness gate (issue #37) -----------------------------
from infrastructure.acquisition.stage6_handoff import handoff as HND


def _pkg():
    return {"districts": [{"district_id": "0100810", "records": [
                {"rec_key": "0100810:abc", "decision": "send",
                 "reps": [{"file": "page.txt", "kind": "text", "councils": ["low-cost-text"],
                           "est_usd": 0.001}]}]}],
            "cost": {"total_usd": 0.001, "n_reps": 1, "provenance": "bootstrap"},
            "verified_only": False}


def _bundle():
    """The gate hashes a bundle, not a bare package (#659) — one assembly, checked and then frozen."""
    from infrastructure.acquisition.process_governance.stage6_dispatch import ReleaseBundle
    return ReleaseBundle(package=_pkg(), metas={}, skipped=[])


def test_preview_returns_the_identity_token(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.H6, "build_handoff_package", lambda con, ids, *a, **k: _pkg())
    r = client.post("/api/handoff/preview", json={"district_ids": ["0100810"]})
    assert r.status_code == 200
    body = r.json()
    assert body["preview_identity"] == HND.package_identity(_pkg())


def test_dispatch_with_stale_identity_is_409(monkeypatch):
    """The release changed between preview and approve (a label edit / re-ingest): the assembly the
    gate hashes no longer matches what the human reviewed -> 409, nothing frozen.

    #659: the gate now hashes a `release_bundle` and hands THAT SAME bundle to dispatch_handoff,
    rather than hashing one build and freezing an independently rebuilt second one."""
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.H6, "release_bundle", lambda con, ids, **k: _bundle())
    frozen = {"called": False}
    monkeypatch.setattr(SRV.H6, "dispatch_handoff",
                        lambda *a, **k: frozen.update(called=True) or ({}, ""))
    stale_pkg = _pkg()   # what an earlier preview hashed: the same district, a different record
    stale_pkg["districts"][0]["records"][0]["rec_key"] = "0100810:zzz"
    stale = HND.package_identity(stale_pkg)
    r = client.post("/api/handoff/dispatch",
                    json={"district_ids": ["0100810"], "expected_identity": stale})
    assert r.status_code == 409
    assert "re-preview" in r.json()["detail"]
    assert frozen["called"] is False               # nothing was frozen/recorded


def test_dispatch_with_matching_identity_freezes(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.H6, "release_bundle", lambda con, ids, **k: _bundle())
    doc = {"handoff_hash": "abc123", "created_at": "2026-07-02T00:00:00Z",
           "districts": [{"district_id": "0100810"}],
           "cost": {"total_usd": 0.001, "n_reps": 1, "provenance": "bootstrap"}}
    monkeypatch.setattr(SRV.H6, "dispatch_handoff", lambda con, ids, **k: (doc, "/x.json"))
    r = client.post("/api/handoff/dispatch",
                    json={"district_ids": ["0100810"],
                          "expected_identity": HND.package_identity(_pkg())})
    assert r.status_code == 200 and r.json()["handoff_hash"] == "abc123"


def test_the_gate_hashes_and_freezes_the_SAME_assembly(monkeypatch):
    """#659 — the staleness gate's whole purpose is that what was reviewed is what gets frozen.

    It used to compute the identity from one `build_handoff_package` call and then hand
    `dispatch_handoff` a bare id list, which independently rebuilt an equivalent package. Anything
    that changed between the two builds — a label edit, a re-price — passed the gate and was frozen
    unseen. Now one bundle is built, hashed, and passed through.

    Also the expensive half of a dispatch (per-district release input + routing + pricing), so a
    large in-flight selection was being assembled twice per operator click."""
    from infrastructure.acquisition.process_governance.stage6_dispatch import ReleaseBundle
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    built = []

    def _bundle_once(con, ids, **k):
        b = ReleaseBundle(package=_pkg(), metas={"0100810": {}}, skipped=[])
        built.append(b)
        return b

    seen = {}
    monkeypatch.setattr(SRV.H6, "release_bundle", _bundle_once)
    monkeypatch.setattr(SRV.H6, "dispatch_handoff",
                        lambda con, ids, **k: seen.update(bundle=k.get("bundle")) or (
                            {"handoff_hash": "h1", "created_at": "2026-07-26T00:00:00Z",
                             "districts": [], "cost": {}}, "/x.json"))
    r = client.post("/api/handoff/dispatch",
                    json={"district_ids": ["0100810"],
                          "expected_identity": HND.package_identity(_pkg())})

    assert r.status_code == 200
    assert len(built) == 1, "the release was assembled more than once for one dispatch"
    assert seen["bundle"] is built[0], "the frozen assembly is not the one the gate hashed"


def test_a_dispatch_without_a_staleness_token_still_assembles_exactly_once(monkeypatch):
    """The bare CLI/test POST path: with no identity to check there is nothing to pre-build, so the
    endpoint passes bundle=None and dispatch_handoff does its own single assembly. Pinned because
    the obvious refactor — always pre-build — would add a second build to this path."""
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.H6, "release_bundle",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not pre-build")))
    seen = {}
    monkeypatch.setattr(SRV.H6, "dispatch_handoff",
                        lambda con, ids, **k: seen.update(bundle=k.get("bundle")) or (
                            {"handoff_hash": "h2", "created_at": "2026-07-26T00:00:00Z",
                             "districts": [], "cost": {}}, "/x.json"))
    r = client.post("/api/handoff/dispatch", json={"district_ids": ["0100810"]})

    assert r.status_code == 200
    assert seen["bundle"] is None
