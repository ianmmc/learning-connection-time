"""REQ-094 — the Stage 5→6 release generator: the deterministic record→representation descent that
emits one traceable `filtered.json` per district.

The descent (best_send / decide / build_doc) is PURE — unit-tested with synthetic records, no DB.
The DB read→build→write path (generate) is exercised against the real governance Postgres via the
gov_session fixture: a synthetic district/record/label/representation is inserted on the session
(test-specific ids), generate() writes filtered.json to a tmp dir, and the session is ROLLED BACK
at teardown so the live data is untouched.
"""
import json

import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import release as R
from infrastructure.acquisition.stage5_filter import build_signals as BS


def _rec(label=None, tier="A", reps=None, signals=None, facets=None, **over):
    base = {"rec_key": "d:1", "url": "http://x/a", "tier": tier, "category": "x",
            "label": label, "signals": signals or {}, "facets": facets or {},
            "is_emergent": 0, "intended_schools": [], "reps": reps or []}
    base.update(over)
    return base


def _text_rep(filename, n_times=0, n_chars=100, usable=1, source="pdftotext"):
    return {"source": source, "filename": filename, "file_kind": "text",
            "n_chars": n_chars, "n_times": n_times, "usable": usable}


# ----------------------------- best_send (one best representation) -----------------------------
def test_best_send_picks_densest_usable_text():
    reps = [_text_rep("a.txt", n_times=1), _text_rep("b.txt", n_times=5), _text_rep("c.txt", n_times=2)]
    assert R.best_send(reps, {}, {}) == [{"file": "b.txt", "kind": "text"}]


def test_best_send_image_when_visual_text_gap():
    reps = [_text_rep("a.txt", n_times=3),
            {"source": "capture:png", "filename": "page.png", "file_kind": "image", "usable": 1}]
    assert R.best_send(reps, {"visual_text_gap": True}, {}) == [{"file": "page.png", "kind": "image"}]


def test_best_send_image_when_human_facets_needs_vision():
    # v2.1 (REQ-114 Axis 3): the human's needs_vision facet routes to the image rep — this replaced
    # the v2.0 target_image_only flag (flags_json is a retired, inert archive).
    reps = [_text_rep("a.txt", n_times=9),
            {"source": "raster", "filename": "raster_p1.png", "file_kind": "image", "usable": 1}]
    assert R.best_send(reps, {}, {"needs_vision": "yes"}) == [{"file": "raster_p1.png", "kind": "image"}]
    # tri-state: only an explicit "yes" routes; "no"/"unsure"/absent do not
    assert R.best_send(reps, {}, {"needs_vision": "no"}) == [{"file": "a.txt", "kind": "text"}]


def test_best_send_handbook_prefers_the_materialized_slice():
    # Q2.1: when the harvest_slice.txt rep exists, send THAT (a small text doc), not the whole PDF —
    # and the slice is never chosen as a plain "densest text" for a non-handbook.
    reps = [_text_rep("harvest_slice.txt", n_times=30, n_chars=900, source="harvest_slice"),
            _text_rep("a.txt", n_times=4),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    sig = {"is_handbook": True, "harvest_pages": [4, 9]}
    assert R.best_send(reps, sig, {}) == [{"file": "harvest_slice.txt", "kind": "text", "pages": [4, 9]}]


def _tb_rep(n_times, n_chars):
    return _text_rep(BS.TIMEBEARING_SLICE_FILE, n_times=n_times, n_chars=n_chars,
                     source=BS.TIMEBEARING_SLICE_SOURCE)


# ---- #821 the ABSOLUTE time-bearing page floor ----
def test_best_send_sends_the_floor_slice_for_a_non_handbook_multipage_pdf():
    # MUST FAIL TODAY: page scoping was reachable only through the handbook door, so this record's
    # whole 90k-char text was sent. Same yield, 90% fewer characters.
    reps = [_tb_rep(n_times=80, n_chars=9_000),
            _text_rep("pdftotext.txt", n_times=80, n_chars=90_000),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    sig = {"is_handbook": False, "harvest_pages": [], "timebearing_pages": [1, 12, 13]}
    assert R.best_send(reps, sig, {}) == [
        {"file": BS.TIMEBEARING_SLICE_FILE, "kind": "text", "pages": [1, 12, 13]}]


def test_best_send_floor_slice_loses_the_230_yield_guard():
    # The #230 rule applies unchanged: a slice that clips half the table must never shadow the
    # full read, however much smaller it is.
    reps = [_tb_rep(n_times=26, n_chars=2_000),
            _text_rep("pdftotext.txt", n_times=90, n_chars=90_000)]
    sig = {"is_handbook": False, "timebearing_pages": [4]}
    assert R.best_send(reps, sig, {}) == [{"file": "pdftotext.txt", "kind": "text"}]


def test_best_send_floor_slice_declined_when_the_saving_is_trivial():
    # It is a recall-preserving filter that must also EARN its send — a slice that saves 2% is
    # churn, not scoping (unlike the handbook branch, where ties go to the slice unconditionally).
    reps = [_tb_rep(n_times=80, n_chars=88_000),
            _text_rep("pdftotext.txt", n_times=80, n_chars=90_000)]
    sig = {"is_handbook": False, "timebearing_pages": [1, 2, 3]}
    assert R.best_send(reps, sig, {}) == [{"file": "pdftotext.txt", "kind": "text"}]


def test_best_send_floor_slice_never_enters_the_densest_text_pool():
    # If the slice were a general "densest text" candidate it would become its own best_text and
    # the yield guard would degenerate into comparing it with itself.
    reps = [_tb_rep(n_times=5, n_chars=100),
            _text_rep("page.txt", n_times=9, n_chars=400)]
    sig = {"is_handbook": False, "timebearing_pages": [2]}
    assert R.best_send(reps, sig, {}) == [{"file": "page.txt", "kind": "text"}]


def test_best_send_vision_outranks_the_floor_slice():
    # A record whose text never captured the content is exactly where a slice OF that text is
    # worst — vision is the right answer and must win.
    reps = [_tb_rep(n_times=3, n_chars=200),
            _text_rep("a.txt", n_times=3, n_chars=9_000),
            {"source": "capture:png", "filename": "page.png", "file_kind": "image", "usable": 1}]
    sig = {"is_handbook": False, "timebearing_pages": [1], "visual_text_gap": True}
    assert R.best_send(reps, sig, {}) == [{"file": "page.png", "kind": "image"}]


def test_best_send_sends_the_floor_slice_on_a_handbook_with_no_harvest_peak():
    # #834 case 1 (35 live records) — MUST FAIL against the old `not handbookish` guard. A handbook
    # whose peak-relative harvest found nothing has the floor as its ONLY scoping; ingest cut it,
    # and best_send hid it (0904830:71acfa3404: 1,017 pages sent whole, a 19-page slice dead).
    reps = [_tb_rep(n_times=12, n_chars=50_721),
            _text_rep("pdftotext.txt", n_times=12, n_chars=2_860_753),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    sig = {"is_handbook": True, "harvest_pages": [], "timebearing_pages": list(range(1, 20))}
    assert R.best_send(reps, sig, {}) == [
        {"file": BS.TIMEBEARING_SLICE_FILE, "kind": "text", "pages": list(range(1, 20))}]


def test_best_send_honours_a_bare_human_page_range_without_buried_handbook():
    # #834 case 2 (8 live records) — MUST FAIL today. A reviewer typed a page range but did not tick
    # buried_handbook. Ingest cut a harvest slice from that range; the old send gate demanded
    # buried_handbook == "yes" and refused it — and the floor was denied too because the harvest
    # branch had fired. ONE predicate: the human looked, the harvest slice is what gets sent.
    reps = [_text_rep("harvest_slice.txt", n_times=9, n_chars=1_500, source="harvest_slice"),
            _text_rep("pdftotext.txt", n_times=9, n_chars=40_000),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    sig = {"is_handbook": False, "harvest_pages": [], "timebearing_pages": [1, 4]}
    facets = {"_pages_list": [4]}                       # NO buried_handbook key at all
    assert R.best_send(reps, sig, facets) == [{"file": "harvest_slice.txt", "kind": "text", "pages": [4]}]


def test_best_send_and_ingest_agree_on_every_slice_shape():
    # The #834 property, asserted directly: for every combination of the inputs that drive the
    # decision, the kind best_send is willing to SEND equals the kind select_slice says to CUT.
    import itertools
    for is_hb, harvest, floor, human in itertools.product(
            (True, False), ([], [4]), ([], [1, 4]), ({}, {"_pages_list": [4]})):
        sig = {"is_handbook": is_hb, "harvest_pages": harvest, "timebearing_pages": floor}
        chosen = BS.select_slice(sig, human)
        # give best_send BOTH slice reps, generously sized so only the gate decides
        reps = [_text_rep("harvest_slice.txt", n_times=9, n_chars=100, source="harvest_slice"),
                _tb_rep(n_times=9, n_chars=100),
                _text_rep("pdftotext.txt", n_times=9, n_chars=100_000),
                {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
        sent = R.best_send(reps, sig, human)[0]["file"]
        if chosen is None:
            assert sent == "pdftotext.txt", (sig, human, sent)
        else:
            assert sent == BS.SLICE_FILE_BY_SOURCE[chosen[0]], (sig, human, chosen, sent)


def test_best_send_floor_slice_must_be_smaller_than_its_own_parent():
    # #838: on an HTML capture the densest text can be a DIFFERENT extraction from the pdftotext
    # the slice was cut from. 3800038:df6bcfc4b7 — a 1,786-char slice of a 1,783-char pdftotext,
    # "saving" 40% against a 2,985-char page.txt. Not smaller than the document it was cut FROM is
    # not scoping; it must not win.
    reps = [_tb_rep(n_times=6, n_chars=1_786),
            _text_rep("pdftotext.txt", n_times=5, n_chars=1_783),
            _text_rep("page.txt", n_times=6, n_chars=2_985, source="txt"),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    sig = {"is_handbook": False, "timebearing_pages": [1, 2]}
    assert R.best_send(reps, sig, {}) == [{"file": "page.txt", "kind": "text"}]
    # ...and a genuinely smaller slice still wins on the same shape
    reps[0] = _tb_rep(n_times=6, n_chars=900)
    assert R.best_send(reps, sig, {})[0]["file"] == BS.TIMEBEARING_SLICE_FILE


def test_gate5_console_shows_the_floor_scoping_decision(app_js):
    """#840 — the UI-visibility rule: under the manual-gate posture the reviewer must SEE that
    page-scoping is happening, which pages survive, and why. The floor now shapes ~700 live sends
    and the per-page card was blind to it (it knew only the harvest ★). Static-source assertions
    on app.js, the same convention as test_684's console checks; the markers must be data-driven
    from the stored signals so they cannot drift from what was actually cut."""
    from pathlib import Path
    js = app_js
    assert "s.timebearing_pages" in js, "the card must read the floor signal"
    assert "◆" in js and "★" in js, "two selectors, two DISTINCT markers"
    assert 'data-scoping="${harvestGoverns ? "harvest" : (floorGoverns ? "floor" : "none")}"' in js, \
        "the table must name which selector governs the send (a DOM hook for Playwright)"
    assert "time-bearing floor" in js, "the meta line must name the floor when it applies"
    assert 'p.instr ? " · instr"' in js, "an instructional-declaration page must be marked"
    # precedence mirrors select_slice: harvest only when is_handbook AND harvest_pages
    assert "const harvestGoverns = !!(s.is_handbook && harvest.size);" in js


def test_862_chrome_is_never_the_first_send_but_main_may_be():
    """#862: best_send's densest-text pool never referenced CHROME_SOURCES — chrome stayed out only
    while its n_times was NULL (#841 scored it; 4 live records then picked page.nav/footer.txt).
    A footer with the most clock times must NOT be chosen; the full page (chrome included) still
    carries that evidence and IS chosen. segment:main is deliberately still eligible: measured
    (#863), it is the fullest read on 5 send-decided records."""
    reps = [_text_rep("page.txt", n_times=5),
            _text_rep("page.footer.txt", n_times=20, source="segment:footer"),   # mis-segmented chrome
            _text_rep("page.nav.txt", n_times=9, source="segment:nav"),
            _text_rep("page.header.txt", n_times=9, source="segment:header")]
    assert R.best_send(reps, {}, {}) == [{"file": "page.txt", "kind": "text"}]
    reps.append(_text_rep("page.main.txt", n_times=88, source="segment:main"))
    assert R.best_send(reps, {}, {}) == [{"file": "page.main.txt", "kind": "text"}]


def test_866_no_non_swappable_source_can_ever_be_the_first_send():
    """#866: the pool and the 7->6 swap set are ONE set, pinned BEHAVIOURALLY. The first draft
    asserted `CHROME_SOURCES <= NON_SWAPPABLE_SOURCES`, which is true by construction (the
    definition IS that union) and never touches best_send — a verdict that cannot fail. This
    loops the real set through the real function, so a source added straight to the union
    (#685's hidden-panel rep, a future segment:aside) is locked out of the FIRST SEND too, which
    is the drift #862 exists to close."""
    assert R.NON_SWAPPABLE_SOURCES                       # the sweep is not vacuous
    for src in sorted(R.NON_SWAPPABLE_SOURCES):
        reps = [_text_rep("page.txt", n_times=1),
                _text_rep("x.txt", n_times=99, source=src)]   # far denser, still ineligible
        assert R.best_send(reps, {}, {}) == [{"file": "page.txt", "kind": "text"}], src
    # ...and the pool helper is what best_send actually reads (one definition, not two)
    for src in sorted(R.NON_SWAPPABLE_SOURCES):
        assert R.sendable_text_reps([_text_rep("x.txt", n_times=99, source=src)]) == [], src


def test_868_chrome_is_not_a_usable_text_rep_of_last_resort():
    """#868: segments are ingested `usable=1` unconditionally while page.txt carries Stage 4's
    >=120-char bar, so chrome can be a record's only "usable" text. Post-#862 that pool is empty
    and best_send falls to the image branch. Pinned as INTENDED: chrome is the de-chrome
    quarantine, not a text rep of last resort, and a page whose every real text rep is sub-usable
    is by construction `visual_text_gap` (build_signals: has_visual and max_chars < USABLE_MIN),
    which routes to vision one branch EARLIER anyway. Measured live: 1 canonical record has a
    chrome-only usable pool; 0 reach this fallback."""
    reps = [_text_rep("page.txt", n_times=0, n_chars=27, usable=0),      # below Stage 4's bar
            _text_rep("page.header.txt", n_times=0, n_chars=618, source="segment:header"),
            {"source": "capture:png", "filename": "page.png", "file_kind": "image", "usable": 1}]
    assert R.sendable_text_reps(reps) == []
    assert R.best_send(reps, {}, {}) == [{"file": "page.png", "kind": "image"}]
    # the real-world route: such a record is visual_text_gap, so it never depends on the fallback
    assert R.best_send(reps, {"visual_text_gap": True}, {}) == [{"file": "page.png", "kind": "image"}]
    # with no binary rep at all the record honestly reports no usable rep rather than sending chrome
    assert R.best_send(reps[:2], {}, {}) == []


def test_alternates_never_offer_a_slice_as_a_swap_candidate():
    # #837: a slice is a strict SUBSET of another rep of the same record — retrying it after the
    # full text failed is the 7->6 ladder run downward. Both slice kinds excluded, chrome still is.
    reps = [_text_rep("pdftotext.txt", n_times=9),
            _text_rep("harvest_slice.txt", n_times=9, source="harvest_slice"),
            _tb_rep(n_times=9, n_chars=100),
            _text_rep("page.header.txt", n_times=2, source="segment:header"),
            {"source": "raster", "filename": "raster_p1.png", "file_kind": "image", "usable": 1}]
    got = {a["file"] for a in R.alternates(reps, exclude={"pdftotext.txt"})}
    assert got == {"raster_p1.png"}
    assert BS.SLICE_SOURCES <= R.NON_SWAPPABLE_SOURCES and R.CHROME_SOURCES <= R.NON_SWAPPABLE_SOURCES


@pytest.mark.parametrize("extra", [False, True])
def test_best_send_handbook_records_are_byte_identical(extra):
    """P3: this widens scoping to records that had none — it must not re-route an existing one.
    Every handbook case is re-asserted with a timebearing_slice rep ALSO present; the presence of
    the new rep must change nothing. (In production the two are mutually exclusive at
    materialization, so this is belt-and-braces against a mis-ordered branch.)"""
    def maybe(reps):
        return reps + [_tb_rep(n_times=999, n_chars=10)] if extra else reps

    # slice preferred
    reps = maybe([_text_rep("harvest_slice.txt", n_times=30, n_chars=900, source="harvest_slice"),
                  _text_rep("a.txt", n_times=4),
                  {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}])
    sig = {"is_handbook": True, "harvest_pages": [4, 9], "timebearing_pages": [1, 2]}
    assert R.best_send(reps, sig, {}) == [
        {"file": "harvest_slice.txt", "kind": "text", "pages": [4, 9]}]

    # pdf+pages fallback when no slice was materialized
    reps = maybe([_text_rep("a.txt", n_times=4),
                  {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}])
    sig = {"is_handbook": True, "harvest_pages": [2, 3], "timebearing_pages": [1, 2]}
    assert R.best_send(reps, sig, {}) == [{"file": "page.pdf", "kind": "pdf", "pages": [2, 3]}]

    # #230: a denser general text rep beats the slice
    reps = maybe([_text_rep("harvest_slice.txt", n_times=26, source="harvest_slice"),
                  _text_rep("pdftotext.txt", n_times=90),
                  {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}])
    sig = {"is_handbook": True, "harvest_pages": [12], "timebearing_pages": [1, 2]}
    assert R.best_send(reps, sig, {}) == [{"file": "pdftotext.txt", "kind": "text"}]


def test_best_send_handbook_falls_back_to_pdf_when_no_slice():
    reps = [_text_rep("a.txt", n_times=4),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    sig = {"is_handbook": True, "harvest_pages": [2, 3]}
    assert R.best_send(reps, sig, {}) == [{"file": "page.pdf", "kind": "pdf", "pages": [2, 3]}]


def test_best_send_handbook_slice_loses_to_a_denser_general_text_rep():
    # #230 (Redbank Valley): the slice used to be sent UNCONDITIONALLY — round 1 dispatched
    # harvest_slice.txt (n_times=26) while pdftotext.txt (n_times=90) sat unsent as an alternate,
    # wasting a paid round before the 7->6 retry self-corrected. Yield now decides. The rep set
    # INCLUDES the pdf rep every real handbook record carries — the review of this fix caught the
    # pdf+pages fallback intercepting the fall-through and sending the whole PDF instead.
    reps = [_text_rep("harvest_slice.txt", n_times=26, source="harvest_slice"),
            _text_rep("pdftotext.txt", n_times=90),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    sig = {"is_handbook": True, "harvest_pages": [12]}
    assert R.best_send(reps, sig, {}) == [{"file": "pdftotext.txt", "kind": "text"}]


def test_best_send_handbook_slice_wins_ties_and_zero_yield_records():
    # ties go to the slice (the purpose-built handbook rep) ...
    reps = [_text_rep("harvest_slice.txt", n_times=8, source="harvest_slice"),
            _text_rep("a.txt", n_times=8)]
    sig = {"is_handbook": True, "harvest_pages": [3]}
    assert R.best_send(reps, sig, {}) == [{"file": "harvest_slice.txt", "kind": "text", "pages": [3]}]
    # ... and a slice-only record (no usable general text) still sends the slice, even at 0 yield
    only_slice = [_text_rep("harvest_slice.txt", n_times=0, source="harvest_slice")]
    assert R.best_send(only_slice, sig, {}) == [{"file": "harvest_slice.txt", "kind": "text", "pages": [3]}]


def test_best_send_empty_when_no_reps():
    assert R.best_send([], {}, {}) == []


# ----------------------------- decide (the release rule) -----------------------------
def test_decide_target_label_sends():
    rec = _rec(label="school_bell_table", reps=[_text_rep("page.txt", n_times=4)])
    d = R.decide(rec)
    assert d["decision"] == "send"
    assert d["reason"] == "target-label:school_bell_table"
    assert d["send"] == [{"file": "page.txt", "kind": "text"}]


def test_decide_labeled_non_target_rejects():
    d = R.decide(_rec(label="board_schedule", reps=[_text_rep("page.txt", n_times=4)]))
    assert d["decision"] == "reject" and d["reason"] == "non-target:board_schedule" and d["send"] == []


@pytest.mark.parametrize("label", sorted(BS.NONTARGET_PRIMARIES))
def test_a_non_target_label_beats_tier_A_auto_send(label):
    """THE money-leak guard: a tier-A record is the ONE unlabeled shape that auto-sends to the paid
    council, so a human's `target_absent` / `unusable` verdict has to win against it — that verdict is
    the only thing standing between a confident-but-wrong detector and a paid call.

    Pinned as its own test because the guarantee rests entirely on BRANCH ORDER in `decide()`: the
    `if label:` reject precedes the tier read, so `tier` is never consulted once a label exists. Nothing
    else enforces that — reorder the branches and the general labeled-non-target test above still passes
    (it uses no tier-A auto-send path), while every A-scored record a reviewer rejected starts spending.

    Live case (#683/#684, Bentonville `0503060:a5f32ff869`): an employee handbook drew FOUR strong
    target votes off staff report-times plus a `30 minutes of class` false positive, landing tier A with
    `decision: send`. The human label is what stopped it — and #683/#684 will edit exactly this
    detector/tier surface, which is why this is pinned before that work rather than after."""
    # a maximally "sendable" record: dense usable text, current school year (clears the #241 floor)
    rec = _rec(label=label, tier="A", reps=[_text_rep("handbook.txt", n_times=40, n_chars=5000)],
               signals={"content_school_year": "2025-26"})
    d = R.decide(rec)
    assert d["decision"] == "reject"
    assert d["reason"] == f"non-target:{label}"
    assert d["send"] == []          # nothing routed, nothing priced, nothing spent
    assert d["alternates"] == []    # and no swap-to candidate offered at gate@6 either
    # the SAME record unlabeled is the thing this label overrode — proves the assertion above is not
    # passing for some unrelated reason (a broken rep, a floor hold), which would make the pin hollow.
    assert R.decide(_rec(**{**rec, "label": None}))["decision"] == "send"


def test_stale_pre_2017_tier_a_is_held_by_validity_floor():
    # #241: a doc whose content school year predates the CRDC 2017-18 federal baseline breaks REQ-026's
    # blend window against it — HOLD (suppress-to-review) on the auto path; never sent, never lost.
    # ~0 money (obs. 6: 4 tier-A pre-floor records, all real targets). Human re-affirms via a label.
    d = R.decide(_rec(label=None, tier="A", reps=[_text_rep("p.txt", n_times=5)],
                      signals={"content_school_year": "2012-13"}))
    assert d["decision"] == "hold"
    assert "stale" in d["reason"] and "2012-13" in d["reason"]
    assert d["send"] == []


def test_validity_floor_admits_the_2017_18_baseline_and_newer():
    # the floor is PRE-2017-18; the 2017-18 baseline itself (and anything newer) is acceptable
    for csy in ("2017-18", "2018-19", "2025-26"):
        d = R.decide(_rec(tier="A", reps=[_text_rep("p.txt", n_times=5)],
                          signals={"content_school_year": csy}))
        assert d["decision"] == "send" and d["reason"] == "auto:tier-A", csy


def test_validity_floor_is_inert_without_a_content_year():
    # the floor only fires on a KNOWN pre-floor year; unknown/absent coexists (never auto-oldest)
    for csy in (None, ""):
        d = R.decide(_rec(tier="A", reps=[_text_rep("p.txt", n_times=5)],
                          signals={"content_school_year": csy}))
        assert d["decision"] == "send", repr(csy)


def test_human_target_label_overrides_the_stale_floor():
    # the floor guards the AUTO path only — an explicit human target label IS the override (Brashear:
    # a district whose only evidence is old still gets sent once a human affirms it)
    d = R.decide(_rec(label="school_bell_table", tier="A", reps=[_text_rep("p.txt", n_times=5)],
                      signals={"content_school_year": "2012-13"}))
    assert d["decision"] == "send"


def test_decide_target_with_no_usable_rep_flags_it():
    d = R.decide(_rec(label="school_bell_table", reps=[]))
    assert d["decision"] == "send" and d["reason"].endswith(";no-usable-rep") and d["send"] == []


def test_decide_unlabeled_is_tier_gated():
    # only tier A auto-dispatches; B/C are HELD pending a gate@5 label; D is a confident reject
    a = R.decide(_rec(label=None, tier="A", reps=[_text_rep("p.txt", n_times=2)]))
    assert a["decision"] == "send" and a["reason"] == "auto:tier-A"
    for t in ("B", "C"):
        h = R.decide(_rec(label=None, tier=t, reps=[_text_rep("p.txt", n_times=2)]))
        assert h["decision"] == "hold" and h["reason"] == f"unlabeled-tier-{t}" and h["send"] == []
    d = R.decide(_rec(label=None, tier="D"))
    assert d["decision"] == "reject" and d["reason"] == "auto:tier-D"


def test_decide_unlabeled_tier_a_with_no_usable_rep_rejects():
    d = R.decide(_rec(label=None, tier="A", reps=[]))
    assert d["decision"] == "reject" and "no-usable-rep" in d["reason"]


# ----------------------------- alternates (gate@6 representation override) -----------------------------
def test_alternates_excludes_winner_and_lists_other_usable():
    reps = [_text_rep("winner.txt", n_times=9), _text_rep("other.txt", n_times=2),
            _text_rep("garbled.txt", usable=0),  # unusable text excluded
            {"source": "capture:png", "filename": "page.png", "file_kind": "image", "usable": 1},
            # #856: `usable` gates EVERY kind, not text only (live rows always carry the column)
            {"source": "raster", "filename": "bad_p1.png", "file_kind": "image", "usable": 0}]
    alts = R.alternates(reps, exclude={"winner.txt"})
    files = {a["file"] for a in alts}
    assert files == {"other.txt", "page.png"}          # winner + BOTH unusables excluded; image kept


def test_decide_target_carries_alternates_not_the_winner():
    reps = [_text_rep("winner.txt", n_times=9), _text_rep("alt.txt", n_times=3),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf", "usable": 1}]
    d = R.decide(_rec(label="school_bell_table", reps=reps))
    assert d["send"] == [{"file": "winner.txt", "kind": "text"}]
    alt_files = {a["file"] for a in d["alternates"]}
    assert alt_files == {"alt.txt", "page.pdf"}        # the swappable options, winner excluded


def test_decide_reject_has_no_alternates():
    d = R.decide(_rec(label="board_schedule", reps=[_text_rep("p.txt", n_times=4)]))
    assert d["alternates"] == []


def test_alternates_excludes_quarantined_chrome_segments():
    reps = [_text_rep("winner.txt", n_times=9),
            _text_rep("page.main.txt", n_times=4, source="segment:main"),    # de-chromed body: a candidate
            _text_rep("page.header.txt", n_times=1, source="segment:header"),  # chrome: excluded
            _text_rep("page.footer.txt", n_times=1, source="segment:footer"),  # chrome: excluded
            _text_rep("page.nav.txt", n_times=1, source="segment:nav")]        # chrome: excluded
    alts = {a["file"] for a in R.alternates(reps, exclude={"winner.txt"})}
    assert alts == {"page.main.txt"}


# ----------------------------- build_doc (traceable artifact) -----------------------------
def test_build_doc_is_traceable_with_completeness_and_header():
    district = {"district_id": "d", "district_dir": "d_dir", "labeled_topology": "per_school",
                "nces_denominator": {"total": 3, "by_level": {}}}
    records = [_rec(rec_key="d:1", label="school_bell_table", reps=[_text_rep("p1.txt", n_times=4)]),
               _rec(rec_key="d:2", label="board_schedule", reps=[_text_rep("p2.txt", n_times=4)]),
               _rec(rec_key="d:3", label="none")]
    doc = R.build_doc(district, records, {"config": "c", "labels": "l", "data": "x"})
    assert doc["completeness"] == {"n_canonical": 3, "n_send": 1, "n_reject": 2, "n_hold": 0}
    assert doc["topology"] == "per_school" and doc["label"] == "gross_bell_to_bell"
    assert doc["fingerprints"] == {"config": "c", "labels": "l", "data": "x"}
    # every canonical record present with a decision (traceable), only the target carries send[]
    by_key = {r["rec_key"]: r for r in doc["records"]}
    assert len(by_key) == 3
    assert by_key["d:1"]["decision"] == "send" and by_key["d:1"]["send"]
    assert by_key["d:2"]["decision"] == "reject" and by_key["d:2"]["reason"] == "non-target:board_schedule"
    assert by_key["d:3"]["decision"] == "reject"


# ----------------------------- generate (DB → filtered.json), rolled back -----------------------------
def _seed_district(sess, did, district_dir):
    sess.execute(text(
        "INSERT INTO district (district_id, name, district_dir, labeled_topology, nces_school_count, n_records) "
        "VALUES (:d, 'Test', :dir, 'per_school', 3, 1)"), {"d": did, "dir": district_dir})
    sess.execute(BS.INSERT_RECORD, {
        "rec_key": f"{did}:h1", "district_id": did, "district_dir": district_dir, "url": "http://x/a",
        "hash": "h1", "kind": "html", "final_url": None, "content_hash": "ch1", "duplicate_of": None,
        "tier": "A", "sort_score": 50.0, "category_hypothesis": "school_bell_table",
        "signals_json": json.dumps({"n_times": 4}), "intended_schools_json": json.dumps(["A Elem"]),
        "candidate_tools_json": "[]", "is_emergent": 0})
    sess.execute(text(
        "INSERT INTO label (rec_key, primary_label, facets_json, status) "
        "VALUES (:rk, 'school_bell_table', '{}', 'labeled')"), {"rk": f"{did}:h1"})
    sess.execute(BS.INSERT_REP, {"rec_key": f"{did}:h1", "source": "pdftotext", "filename": "page.txt",
                                 "file_kind": "text", "n_chars": 200, "n_times": 4, "usable": 1})


# #201: this test seeds the SIGNAL tables (district/record/representation) which gov_session does NOT
# bootstrap — it needs a pre-populated DB, so it's integration-only (run locally), NOT govdb (a fresh CI
# container lacks those tables). The other 16 tests in this file are pure release.decide logic (DB-free).
@pytest.mark.integration
def test_generate_writes_traceable_filtered_json(gov_session, tmp_path):
    did = "RELTEST"
    (tmp_path / "reltest_dir").mkdir()
    _seed_district(gov_session, did, "reltest_dir")

    summary = R.generate(gov_session, district_id=did, root=tmp_path)
    assert len(summary) == 1 and summary[0]["n_send"] == 1

    # REQ-164: filtered is now an always-stamped audit receipt (was a fixed filtered.json). The write
    # lands in the DB-authoritative capture dir (root/district_dir); `written` carries the stamped path.
    from pathlib import Path
    written = Path(summary[0]["written"])
    assert written.parent == tmp_path / "reltest_dir"
    assert written.name.startswith("stage5_filter.") and ".py-" in written.name
    doc = json.loads(written.read_text())
    assert doc["district_id"] == did and doc["topology"] == "per_school"
    assert doc["completeness"] == {"n_canonical": 1, "n_send": 1, "n_reject": 0, "n_hold": 0}
    assert set(doc["fingerprints"]) == {"config", "labels", "data"}
    rec = doc["records"][0]
    assert rec["decision"] == "send" and rec["send"] == [{"file": "page.txt", "kind": "text"}]
    assert rec["intended_schools"] == ["A Elem"]
    gov_session.rollback()


def test_handbook_yield_rule_matches_rank_alternates_ordering():
    """#240 review: best_send's slice-vs-text yield comparison and the retry loop's rank_alternates
    are two encodings of ONE rule (yield-bearing text by n_times first). The two layers can't import
    each other (import-linter siblings), so THIS cross-layer test is the drift guard: if the
    ranking rule ever changes on one side, this fails and the other side gets re-aligned."""
    from infrastructure.acquisition.stage7_extract.requests import rank_alternates
    reps = [_text_rep("harvest_slice.txt", n_times=26, source="harvest_slice"),
            _text_rep("pdftotext.txt", n_times=90),
            _text_rep("page.txt", n_times=4)]
    sig = {"is_handbook": True, "harvest_pages": [12]}
    sent = R.best_send(reps, sig, {})[0]["file"]
    alts = [{"kind": "text", "n_times": r["n_times"], "file": r["filename"]} for r in reps]
    assert sent == rank_alternates(alts)[0]["file"], \
        "Stage 5's initial pick disagrees with the retry loop's yield ranking"


# ---- #109: the human-labeled page range outranks the auto harvest_pages ----
def test_human_pages_list_outranks_auto_harvest_pages():
    reps = [{"source": "harvest_slice", "filename": "harvest_slice.txt", "file_kind": "text",
             "n_times": 12, "usable": 1}]
    sig = {"is_handbook": True, "harvest_pages": [4, 9]}
    facets = {"buried_handbook": "yes", "_pages_list": [7, 8, 9]}
    assert R.best_send(reps, sig, facets) == [{"file": "harvest_slice.txt", "kind": "text",
                                              "pages": [7, 8, 9]}]


def test_human_pages_qualify_a_doc_the_auto_classifier_missed():
    # buried_handbook + a human range on a record with is_handbook=False (the auto miss): the
    # PDF+pages fallback must engage exactly as it would for an auto-classified handbook.
    reps = [{"source": "capture:pdf", "filename": "doc.pdf", "file_kind": "pdf", "usable": 1}]
    facets = {"buried_handbook": "yes", "_pages_list": [16, 17]}
    assert R.best_send(reps, {}, facets) == [{"file": "doc.pdf", "kind": "pdf", "pages": [16, 17]}]


def test_no_human_pages_means_auto_behavior_unchanged():
    reps = [{"source": "harvest_slice", "filename": "harvest_slice.txt", "file_kind": "text",
             "n_times": 12, "usable": 1}]
    sig = {"is_handbook": True, "harvest_pages": [4, 9]}
    assert R.best_send(reps, sig, {"buried_handbook": "yes"}) == \
        [{"file": "harvest_slice.txt", "kind": "text", "pages": [4, 9]}]


def test_labeled_pages_of_handles_str_dict_and_junk():
    assert BS.labeled_pages_of('{"_pages_list": [3, 5]}') == [3, 5]
    assert BS.labeled_pages_of({"_pages_list": [3, "5"]}) == [3, 5]
    assert BS.labeled_pages_of({"_pages_list": [0, -2]}) == []      # non-positive filtered
    assert BS.labeled_pages_of(None) == []
    assert BS.labeled_pages_of("{not json") == []
    assert BS.labeled_pages_of({"buried_handbook": "yes"}) == []    # facet without a range


# --------------------- #674: the human's out-of-window HOLD (Option 1 + 3) ---------------------
class TestOutOfWindowHold674:
    """#674 — the human override was one-directional. #241 let a target label force-SEND a
    below-floor record ("preserve a district whose ONLY evidence is old") but gave no way to
    force-HOLD one. Composed with the labeling doctrine — which REQUIRES a correctly-shaped
    2014-15 schedule to be target-labeled, because withholding the label teaches the detector the
    shape is not a target — following the rules correctly GUARANTEED out-of-window material
    reached paid extraction. TAOS 3500127 shipped two such reps in a frozen production dispatch."""

    def _taos(self, facets=None):
        """TAOS `3500127:47750e00fb`: target-labeled, content_school_year 2014-15 — the record
        #674 names as the falsifier."""
        return {"rec_key": "3500127:47750e00fb", "tier": "A",
                "label": "school_start_end_prose",
                "signals": {"content_school_year": "2014-15"},
                "facets": facets or {},
                "reps": [{"filename": "Parent-Student-Handbook-2014-15.pdf", "file_kind": "text",
                          "source": "pdftotext", "n_times": 20, "n_chars": 9000, "usable": 1}]}

    def test_the_falsifier_a_marked_record_does_not_send(self):
        """MUST FAIL against today's code: the target-label branch returns send unconditionally."""
        d = R.decide(self._taos({"out_of_window": "yes"}))
        assert d["decision"] == "hold"
        assert d["reason"] == "human:out-of-window"
        assert d["send"] == []

    def test_without_the_mark_the_target_label_still_sends(self):
        """#241's send override is intact — this issue adds the converse, it does not invert it."""
        assert R.decide(self._taos())["decision"] == "send"

    def test_the_shape_label_survives_the_hold(self):
        """The record stays countable as training signal: the hold is a FITNESS judgment and must
        not touch primary_label."""
        rec = self._taos({"out_of_window": "yes"})
        R.decide(rec)
        assert rec["label"] == "school_start_end_prose"      # untouched by the decision

    def test_the_mark_holds_an_in_window_record_too(self):
        """It is a human judgment, not a floor: a reviewer may know a current-looking document is
        the wrong instance. No automatic recency veto is introduced — only this explicit mark."""
        rec = self._taos({"out_of_window": "yes"})
        rec["signals"] = {"content_school_year": "2024-25"}
        assert R.decide(rec)["decision"] == "hold"

    def test_no_automatic_veto_above_the_241_floor(self):
        """Guards against re-introducing the measured-harmful behaviour: on 473 labeled tier-A
        records a stale veto at the bell-year floor removed 1 false-send while vetoing 17 real
        targets and RAISED the false-send rate. Only the explicit mark holds."""
        rec = self._taos()
        rec["signals"] = {"content_school_year": "2019-20"}    # old, but above the 2017-18 floor
        assert R.decide(rec)["decision"] == "send"
        rec["label"] = None
        assert R.decide(rec)["decision"] == "send"             # unlabeled tier A: still sends

    def test_the_facet_is_not_a_training_confounder(self):
        """A fitness judgment must never enter the confounder set — counting it would teach the
        loop that an out-of-window document has a non-target SHAPE, the exact corruption the facet
        exists to avoid."""
        from infrastructure.acquisition.stage5_filter import harness as H
        assert "out_of_window" in H._NON_CONFOUNDER_FACETS
