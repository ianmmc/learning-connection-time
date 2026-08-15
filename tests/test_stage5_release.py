

# ===================== #718: a target production can never receive =====================
def test_production_sendability_splits_gt_artifacts_from_real_targets():
    """MUST FAIL against pre-#718 code (no such function). Baldwin 0100270's live shape: 12 A/B-tier
    targets that all decide `send`, every one of them a `gt://` curation artifact the Stage-9 wall
    guarantees production can never receive — so the district read DONE-ENOUGH while holding zero
    production facts for 19 days, and a dispatch-gap sweep called it "clean"."""
    from infrastructure.acquisition.stage5_filter import release as REL
    rec = lambda k, url, label="school_bell_table": {                       # noqa: E731
        "rec_key": k, "url": url, "label": label, "tier": "A", "signals": {}, "facets": {},
        "reps": [{"file_kind": "text", "usable": True, "filename": f"{k}.txt", "n_chars": 900,
                  "n_times": 9}]}
    recs = [rec("d:1", "gt://gt_curation_x/0100270_Baldwin/a.pdf"),
            rec("d:2", "gt://gt_curation_x/0100270_Baldwin/b.pdf"),
            rec("d:3", "https://www.bcbe.org/bell")]
    sd = REL.production_sendability(recs)
    assert sd["n_send"] == 3 and sd["n_benchmark_only"] == 2
    assert sd["n_production_sendable"] == 1
    assert sd["benchmark_only"] == ["d:1", "d:2"]


def test_a_district_whose_every_target_is_gt_reads_zero_sendable():
    from infrastructure.acquisition.stage5_filter import release as REL
    recs = [{"rec_key": "d:1", "url": "gt://c/x.pdf", "label": "school_bell_table", "tier": "A",
             "signals": {}, "facets": {},
             "reps": [{"file_kind": "text", "usable": True, "filename": "a.txt", "n_chars": 10,
                       "n_times": 1}]}]
    sd = REL.production_sendability(recs)
    assert sd["n_send"] == 1 and sd["n_production_sendable"] == 0 and sd["n_benchmark_only"] == 1


def test_rejects_are_not_counted_either_way():
    from infrastructure.acquisition.stage5_filter import release as REL
    sd = REL.production_sendability([{"rec_key": "d:1", "url": "https://x/y", "label": None,
                                      "tier": "D", "signals": {}, "facets": {}, "reps": []}])
    assert sd == {"n_send": 0, "n_hold": 0, "n_benchmark_only": 0, "n_production_sendable": 0,
                  "benchmark_only": []}


def test_the_gt_predicate_has_one_home():
    """#718 review guard: three call sites were about to grow their own `startswith`."""
    from infrastructure.acquisition.common import benchmark as BM
    assert BM.is_benchmark_url("gt://c/x.pdf") and not BM.is_benchmark_url("https://x/y")
    assert not BM.is_benchmark_url(None) and not BM.is_benchmark_url("")


def test_stage6_js_flags_a_district_production_cannot_receive_718():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/stage6.js").read_text()
    assert 'data-feat="benchmark-only"' in js and "n_production_sendable" in js
    assert "benchmark-only" in js


# ===================== 2026-08-15 review round (#755/#762) =====================
def test_stage6_js_distinguishes_needs_labeling_from_needs_discovery_762():
    """#762: the remedy must match the blocker. Baldwin's real records are HELD tier-C awaiting a
    gate@5 label; the badge used to say "needs discovery" for exactly that shape — contradicting
    zero_yield_reason's own conclusion for the identical district, one file over. Only when nothing
    held could EVER reach production is discovery the answer."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/stage6.js").read_text()
    assert "label at gate@5" in js                       # the needs-labeling arm exists
    assert "n_send_production" in js                     # gated on TODAY's sendability (#755 name)
    assert "needs discovery, not dispatch" in js         # the discovery arm survives
    # the discovery claim must be in the arm gated on production_sendable == 0, not the labeling arm
    label_arm = js[js.index("label at gate@5") - 600:js.index("label at gate@5")]
    assert "needs discovery" not in label_arm.split("?")[-1]


import pytest as _pytest  # noqa: E402


@_pytest.mark.govdb
def test_the_sql_and_python_sendability_formulas_agree_755(gov_session):
    """#755: two independently-written formulas shared the name `n_production_sendable` and DISAGREED
    live on Baldwin (server: send-bucket only, 0; release.py: send+hold non-gt, 2) — the same commit
    telling two stories about the same district. Now: `n_send_production` = dispatchable TODAY;
    `n_production_sendable` = (send+hold) non-gt, the release.py formula, pinned equal here for every
    district the endpoint returns."""
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance import server as SRV
    from infrastructure.acquisition.stage5_filter import release as REL
    rows = TestClient(SRV.app).get("/api/handoff/candidates").json()
    for r in rows:
        py = REL.production_sendability(REL.load_district_records(gov_session, r["district_id"]))
        assert py["n_production_sendable"] == r["n_production_sendable"], r["district_id"]
        assert r["n_send_production"] == r["n_send"] - r["n_benchmark_only"]
