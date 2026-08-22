

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
    # #861: both gt:// records DECIDE send, so both land in n_benchmark_only and n_hold_gt is 0 —
    # the same decomposition the candidates SQL uses, under the same two names.
    assert sd["n_send"] == 3 and sd["n_benchmark_only"] == 2 and sd["n_hold_gt"] == 0
    assert sd["n_production_sendable"] == 1
    assert sd["benchmark_only"] == ["d:1", "d:2"]   # the rec_key list still spans send+hold


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
    assert sd == {"n_send": 0, "n_hold": 0, "n_benchmark_only": 0, "n_hold_gt": 0,
                  "n_production_sendable": 0, "benchmark_only": []}


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


def test_stage6_js_badges_a_district_whose_every_held_record_is_gt_853():
    """#853 (PR #850 review): the unsendable badge was gated on n_send > 0, so a district whose
    only targets are gt:// and were marked out-of-window at gate@5 (#674 moves them into n_hold)
    lost the badge the moment the human acted — reachable only via the wordless "has held" filter.
    A third arm reads `n_hold_gt` (now exposed by the candidates SQL) for the n_send == 0 case."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/stage6.js").read_text()
    assert "n_hold_gt" in js                                 # the signal has a UI consumer
    assert 'data-held-gt=' in js                             # the arm's DOM hook
    assert "benchmark-only held" in js
    arm = js[js.index("data-held-gt="):js.index("data-held-gt=") + 400]
    assert "needs discovery, not dispatch" in arm            # same conclusion as the red arm
    # gated on the n_send == 0 shape, not on n_send > 0 like the two arms above it
    gate = js[js.index("data-held-gt=") - 900:js.index("data-held-gt=")]
    assert "!(c.n_send > 0) && c.n_hold_gt > 0" in gate


def test_869_gate5_densest_badge_excludes_chrome_and_mirrors_the_python_set():
    """#869: the evidence pane badged "densest" over ALL text reps, chrome included, so a footer
    could be named the record's best text while best_send structurally refuses to send it — the
    gate@5 pane disagreeing with the send rule, under a posture that asks the human to trust it.
    The client mirrors release.CHROME_SOURCES; pinned member-for-member because a mirrored
    constant is the drift pair this codebase keeps re-learning."""
    import re
    from pathlib import Path as _P
    from infrastructure.acquisition.stage5_filter import release as REL
    js = (_P(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/app.js").read_text()
    m = re.search(r"const CHROME_SOURCES = new Set\(\[([^\]]*)\]\)", js)
    assert m, "app.js lost the CHROME_SOURCES mirror"
    assert set(re.findall(r'"([^"]+)"', m.group(1))) == set(REL.CHROME_SOURCES)
    # and the badge computation actually applies it (not just declares it)
    assert "ordered.filter((r) => !CHROME_SOURCES.has(r.source))" in js
    # segment:main must NOT be excluded — it is a legitimate send (#841)
    assert "segment:main" not in m.group(1)


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


def test_861_a_held_gt_record_lands_in_n_hold_gt_not_n_benchmark_only():
    """#861: `n_benchmark_only` is the gt:// share of the SEND bucket; `n_hold_gt` is the hold
    half — the same decomposition, under the same names, as the candidates SQL.

    This case did not exist in the DB-free fixtures: every gt:// record in them DECIDES send, so
    the pre-#861 lumped counter and the split one agreed and the unit suite could not tell them
    apart (only the govdb parity test could). A held gt:// record is what separates them.
    """
    from infrastructure.acquisition.stage5_filter import release as REL
    rec = lambda k, url, facets: {                                          # noqa: E731
        "rec_key": k, "url": url, "label": "school_bell_table", "tier": "A",
        "signals": {}, "facets": facets,
        "reps": [{"file_kind": "text", "usable": True, "filename": f"{k}.txt", "n_chars": 900,
                  "n_times": 9}]}
    recs = [
        rec("d:1", "gt://c/send.pdf", {}),                          # gt, decides send
        rec("d:2", "gt://c/held.pdf", {"out_of_window": "yes"}),    # gt, HELD (#674)
        rec("d:3", "https://www.bcbe.org/bell", {}),                # real, send
    ]
    sd = REL.production_sendability(recs)
    assert sd["n_send"] == 2 and sd["n_hold"] == 1
    assert sd["n_benchmark_only"] == 1, "only the SENT gt:// record belongs to this name"
    assert sd["n_hold_gt"] == 1, "the held gt:// record has its own name, matching the SQL"
    assert sd["n_production_sendable"] == 1
    # The rec_key list deliberately still spans both — it answers "which records", and splitting
    # it would push the union onto every caller.
    assert sd["benchmark_only"] == ["d:1", "d:2"]
