"""#684 — the STAFF-DAY confusable: an employee handbook's report-time table is not the student day.

Bentonville `0503060:a5f32ff869` drew four independent strong target votes off a genuine, well-formed
table of times — of the STAFF day. The shape is right; the referent is wrong.

These tests pin the MEASURED design decision as much as the behavior, because #684's stated
shape-of-fix ("widen OFFICE_HOURS_KW; vote on a staff word near a time") is the thing the corpus
REJECTED: presence of staff vocabulary near an in-window time fires on 84 labeled targets vs 88
non-targets (acc 0.512) and would have demoted 59 tier-A targets to save 10 false sends. What
discriminates is the employment-obligation CLAUSE scored relationally against student-referent
language. See the dated report in docs/technical-notes/production-quality-control-research/.
"""
import json

from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage5_filter import combiner as C
from infrastructure.acquisition.stage5_filter import detectors as D

# ONE canonical default-signal helper (PR #705 review [6]): importing the sibling file's sig()/decide()
# instead of keeping a near-copy, so a future signal key added there can't leave this file silently
# testing a stale baseline (the #199 join-the-set failure class, at test grain).
from test_stage5_detectors import decide, sig  # noqa: E402


# ---------------------------------------------------------------- the signal
# The live text of Bentonville pp.22-23, as `camelot_stream.txt` renders it (the basis that decided the
# record). Kept verbatim, mangled spacing and all — "S CHOOL WORK DAY" is what camelot actually emits,
# and a fix that only works on clean text would not have fixed this record.
BENTONVILLE_TEXT = (
    "the student contact day. Teachers will be expected to | | report according to the Board of "
    "Education approved academic calendar. | | S CHOOL WORK DAY | | Elementary staff with a school "
    "start time of 7:30 a.m. are to report to work by 7:15 a.m. and | | remain until 3:00 p.m. | | "
    "22 Bentonville Schools Employee Handbook Updated 07/2025 | | E lementary and Middle School staff "
    "with a school start time of 7:50 a.m. are to report to work by | | --- | | 7:30 a.m. and remain "
    "until 3:15 p.m. | | J unior High staff are to report at 8:05 - 3:50. | | H igh School staff on a "
    "regular bell schedule are to report to school by 8:25 am - 4:10 pm. Zero | | Hour staff members "
    "are to report from 7:00 am - 2:45 pm."
)
# A real student handbook's equivalent passage: the same clock times, a student subject.
STUDENT_TEXT = (
    "School hours are 7:50 a.m. to 3:15 p.m. Students may enter the building at 7:30 a.m. for "
    "breakfast. Students who arrive after 8:05 a.m. must report to the office for a tardy pass. "
    "Dismissal begins at 3:15 p.m.; car riders are released at 3:20 p.m."
)


def _counts(text):
    return BS.staff_duty_positional(text, [off for off, _ in BS.in_window_positions(text)])


def test_the_staff_duty_clause_owns_bentonvilles_times():
    duty, student = _counts(BENTONVILLE_TEXT)
    assert duty > student and duty >= 5, (duty, student)
    assert D.staff_day_owned(sig(staff_duty_times=duty, student_ref_times=student))


def test_a_student_handbook_with_the_same_times_is_untouched():
    # "must report to the office" is a REPORT verb with no staff subject governing it -> zero duty
    # clauses -> not staff-owned, no vote, no demotion.
    duty, student = _counts(STUDENT_TEXT)
    assert duty == 0
    # and the short-circuit: with no duty clause there is nothing to weigh, so the student scan is
    # SKIPPED and both counts are 0 — the documented cost saving. Verify the student vocabulary is
    # nonetheless real on this text (otherwise the relational half of the rule would be vacuous and
    # every test below it would pass for the wrong reason).
    assert student == 0
    assert len(BS.STUDENT_REF_RE.findall(STUDENT_TEXT)) >= 3
    assert not D.staff_day_owned(sig(staff_duty_times=duty, student_ref_times=student))


def test_a_duty_verb_without_a_staff_subject_does_not_count():
    # the full clause is required: SUBJECT governs VERB governs TIME.
    duty, _ = _counts("All students are to report at 8:05 a.m. and remain until 3:15 p.m.")
    assert duty == 0


def test_staffed_is_not_a_staff_subject():
    """PR #705 review [1]: the subject regex is \\b-anchored — bare "staff" substring-matched inside
    "staffed"/"staffing", so a genuine bell page saying "the building remains fully staffed" near a
    "remain until" phrase read as a duty clause and was wrongly pulled out of auto-send. MUST FAIL
    against the unanchored regex (verified duty=1 pre-fix)."""
    text = ("School hours are 7:50 a.m. to 3:15 p.m. Our building remains fully staffed and secure "
            "each morning. Everyone must remain until 3:15 p.m., when the buses leave the front loop.")
    duty, _ = _counts(text)
    assert duty == 0
    # and the same page still auto-sends (the whole point — it is a genuine target)
    r = decide(n_times_in_window=3, proximity_pairs=2, positive_kw=["school hours"],
               staff_duty_times=duty, student_ref_times=0)
    assert r["decision"] == "send" and r["tier"] == "A"


def test_report_attendance_is_not_a_duty_clause():
    """PR #705 review [2]: "report" always requires a duty destination/preposition — the bare
    "are to report"/"must report" alternatives matched every sense of the verb, so routine
    attendance-taking prose beside a genuine bell schedule demoted the real tier-A send. The `at`
    alternative is \\b-anchored so "report at" can't substring-match "report attendance". MUST FAIL
    against the first-shipped regex (verified duty=1 pre-fix)."""
    duty, _ = _counts("Teachers are to report attendance by 7:45 a.m. daily using the electronic "
                      "system. The instructional day runs from 7:50 a.m. to 3:00 p.m.")
    assert duty == 0
    # while the genuinely-destinationed forms all still count (the Bentonville shapes):
    for phrase in ("Staff are to report to work by 7:15 a.m.",
                   "Junior High staff are to report at 8:05 a.m.",
                   "Zero Hour staff members are to report from 7:00 a.m.",
                   "High School staff report to school by 8:25 a.m."):
        d, _ = _counts(phrase)
        assert d >= 1, phrase


def test_a_staff_subject_without_a_duty_verb_does_not_count():
    # this is the shape #684 proposed voting on, and the corpus said it is a coin flip: a real bell
    # page routinely names staff beside its times ("Staff are available 8:00 a.m. - 3:30 p.m." is a
    # borderline the measurement declined to chase, but a bare mention must never fire).
    duty, _ = _counts("Our teachers welcome students at 7:45 a.m. School hours are 8:00 a.m. - 3:00 p.m.")
    assert duty == 0


def test_student_referents_at_the_times_outrank_a_lone_duty_clause():
    # 6 of the corpus's 7 duty-clause records are exactly this shape (Alliance 3805460: 1 duty clause,
    # 23 student-referent times). The relational test is what keeps them out — a bare `duty >= 1` rule
    # would have demoted every one of them.
    text = STUDENT_TEXT + " Staff are to report to work by 7:30 a.m. " + STUDENT_TEXT
    duty, student = _counts(text)
    assert duty >= 1 and student > duty
    assert not D.staff_day_owned(sig(staff_duty_times=duty, student_ref_times=student))


def test_offsets_are_scoped_to_one_basis():
    # in-window offsets never cross texts (the #538 lesson): passing another text's offsets must not
    # manufacture governed times.
    duty, student = BS.staff_duty_positional(BENTONVILLE_TEXT, [])
    assert (duty, student) == (0, 0)


# ---------------------------------------------------------------- the detector + combiner
def test_bentonville_is_no_longer_a_tier_a_auto_send():
    """#684's acceptance line. The signal values are the REAL ones the corpus scan measured for
    `0503060:a5f32ff869` (duty 9 / student 0); the rest of the sig is its live stored signals_json.
    MUST FAIL against pre-#684 code, where `lf_heading_hours` sends STRONG_STRUCTURAL unconditionally."""
    r = decide(n_times_in_window=12, proximity_pairs=30, table_time_density=12, table_period_rows=0,
               has_table=True, is_handbook=True, harvest_pages=[4, 23],
               positive_kw=["bell schedule", "school hours", "school day", "start time", "arrival"],
               heading_hours_hits=4, heading_hours_labels=["bell schedule"],
               staff_duty_times=9, student_ref_times=0)
    assert r["decision"] == "review" and r["tier"] == "B", r
    assert "lf_staff_day" in r["fired"]
    # the structural target is gone (that is the load-bearing half — nothing can undermine it)
    assert "lf_heading_hours" not in r["fired"] and "lf_office_hours" in r["fired"]


def test_it_is_a_hold_not_a_veto():
    """#241's posture, and the issue's own read: an employee handbook can carry the student table too,
    so the outcome is the human queue, never a drop to D."""
    r = decide(n_times_in_window=12, proximity_pairs=30, table_time_density=12, has_table=True,
               positive_kw=["bell schedule"], staff_duty_times=9, student_ref_times=0)
    assert r["decision"] == "review" and r["tier"] == "B"


def test_a_real_target_carrying_staff_vocabulary_still_auto_sends():
    """The measured recall guard, from a real corpus positive: Portage `5501770:96bba5deeb`
    (`school_start_end_prose`, tier A) fires `lf_office_hours` and has OFFICE_HOURS_KW terms within
    140 chars of its in-window times — the exact record #684's proposed presence rule would have
    demoted. Its measured #684 counts are 0 duty / 0 staff-owned bases, so it is untouched."""
    r = decide(n_times_in_window=8, proximity_pairs=6, positive_kw=["school hours", "dismissal"],
               heading_hours_hits=2, heading_hours_labels=["school hours"],
               staff_duty_times=0, student_ref_times=0)
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_staff_day" not in r["fired"] and "lf_heading_hours" in r["fired"]


def test_the_hard_undermine_demotes_the_table_and_the_prose_pair():
    """Both non-structural target votes must fall too, or the record still auto-sends on lf_prose_pair.
    This is why lf_staff_day is registered `hard`, not `soft`: a soft wrong-DAY mention deliberately
    leaves a real table sending (#60/#528), but here the table IS the staff day."""
    r = decide(table_time_density=10, has_table=True, proximity_pairs=4, positive_kw=["school day"],
               staff_duty_times=4, student_ref_times=1)
    assert r["decision"] == "review" and r["tier"] == "B"
    assert {"lf_time_table", "lf_prose_pair"} <= set(r["fired"])


def test_absent_signal_fields_are_inert():
    """#702 absence-vs-empty: a record scored before this signal existed (no keys at all in its stored
    signals_json) must behave exactly as before — absence is not a verdict in either direction."""
    s = sig(n_times_in_window=12, proximity_pairs=30, table_time_density=12, has_table=True,
            positive_kw=["bell schedule"], heading_hours_hits=4, heading_hours_labels=["bell schedule"])
    del s["staff_duty_times"], s["student_ref_times"]
    r = C.score_record(s)
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_staff_day" not in r["fired"] and "lf_heading_hours" in r["fired"]


def test_footer_hours_on_a_staff_owned_page_is_the_office_confusable():
    """PR #705 review [0]: lf_footer_hours is STRONG_STRUCTURAL too, and its own `office` flag is the
    11-term presence test the #684 measurement rejected (acc 0.512) — unguarded, a staff-duty page
    whose footer block slips those keywords re-opened the exact auto-send #684 closed, just via the
    footer path instead of the heading. MUST FAIL pre-fix (verified: send/A with lf_staff_day fired
    but powerless)."""
    r = decide(footer_hours={"hit": True, "times": 2, "office": False},
               n_times_in_window=9, proximity_pairs=3, positive_kw=["school hours"],
               staff_duty_times=9, student_ref_times=0)
    assert r["decision"] == "review" and r["tier"] == "B", r
    assert "lf_footer_hours" not in r["fired"] and "lf_office_hours" in r["fired"]
    assert "lf_staff_day" in r["fired"]


def test_explicit_minutes_on_a_staff_owned_page_holds_for_review():
    """PR #705 review [0], third STRONG_STRUCTURAL member: on a staff-owned page the declaration
    downgrades to a WEAK target (still visible evidence — unlike a heading/footer, the declaration is
    instruction-referent by construction), and the lf_staff_day hard undermine routes it to review.
    MUST FAIL pre-fix (send/A)."""
    r = decide(instructional_time=True, n_times_in_window=9, proximity_pairs=3,
               positive_kw=["school day"], staff_duty_times=9, student_ref_times=0)
    assert r["decision"] == "review" and r["tier"] == "B", r
    # the declaration evidence is downgraded, not silenced — and never falls through to suppress
    assert "lf_explicit_minutes" in r["fired"] and "lf_staff_day" in r["fired"]
    r2 = decide(instructional_time=True, staff_duty_times=3, student_ref_times=0)
    assert r2["decision"] == "review", "a lone declaration on a staff-owned page must HOLD, never drop"


def test_every_strong_structural_detector_consults_the_staff_day_predicate():
    """The structural closure pin (PR #705 review [0]): a STRONG_STRUCTURAL vote sends
    UNCONDITIONALLY, so EVERY member's source must consult staff_day_owned — adding a fourth
    structural detector without the guard fails here, not in production."""
    import inspect
    for name in C.STRONG_STRUCTURAL:
        fn = getattr(D, name)
        assert "staff_day_owned" in inspect.getsource(fn), \
            f"{name} is STRONG_STRUCTURAL but never consults staff_day_owned()"


def test_an_explicit_office_heading_still_wins_over_the_staff_day_arm():
    """Ordering pin: the pre-existing label test runs first, so its more specific reason survives."""
    r = decide(heading_hours_hits=1, heading_hours_labels=["office hours"],
               staff_duty_times=5, student_ref_times=0)
    reasons = " ".join(r["reasons"])
    assert "office-hours heading" in reasons


def test_staff_day_alone_suppresses_like_the_other_hard_negatives():
    """Counterfactually identical to lf_news_feed/lf_district_homepage firing alone: staff-owned times
    with no pair, table, or structure had nothing extractable. With a pair, lf_weak_times fires and the
    combiner routes to review instead — pinned below so the boundary is deliberate, not incidental."""
    assert decide(n_times_in_window=3, staff_duty_times=3, student_ref_times=0)["tier"] == "D"
    r = decide(n_times_in_window=3, proximity_pairs=1, staff_duty_times=3, student_ref_times=0)
    assert r["decision"] == "review" and r["tier"] == "B"


# ---------------------------------------------------------------- the lockstep registries
def test_staff_day_is_registered_everywhere_it_must_be():
    from infrastructure.acquisition.stage5_filter.harness import DETECTOR_FACET, DETECTOR_POLARITY
    assert D.lf_staff_day in D.DETECTORS
    assert D.UNDERMINE_CLASS["lf_staff_day"] == "hard"
    assert "lf_staff_day" in C.UNDERMINE_TIMES and "lf_staff_day" in C.HARD_NEGATIVE
    assert DETECTOR_POLARITY["lf_staff_day"] == "negative"
    # shares the coarse office/building-hours facet with lf_office_hours (one human claim, one checkbox)
    assert DETECTOR_FACET["lf_staff_day"] == {"office_building_hours"}
    assert DETECTOR_FACET["lf_office_hours"] == {"office_building_hours"}


def test_the_staff_day_predicate_has_exactly_one_home():
    """`lf_heading_hours` must consult the SHARED predicate, not re-spell the comparison — a second
    spelling is how the structural-target suppression and the negative vote would drift apart."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "infrastructure/acquisition/stage5_filter/detectors.py").read_text()
    assert src.count("staff_duty_times\", 0) > ") == 1, \
        "the duty>student comparison must live only in staff_day_owned()"
    assert src.count("staff_day_owned(sig)") >= 2   # the definition's callers: lf_staff_day + lf_heading_hours


def test_console_ports_the_staff_duty_regexes_verbatim():
    """#521 no-drift: the heat-strip paints staff-duty evidence, so its regexes are verbatim ports of
    the Python. Unlike #683's `$`-anchored guard, the SUBJECT regex is unanchored — so the JS lookback
    must be CODEPOINT-exact, not merely wide enough."""
    import re
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    m_duty = re.search(r"const DN_STAFF_DUTY = /(.+)/gi;", js)
    m_subj = re.search(r"const DN_STAFF_SUBJ = /(.+)/i;", js)
    assert m_duty and m_subj, "DN_STAFF_DUTY/DN_STAFF_SUBJ must be present in this exact shape"
    assert m_duty.group(1) == BS.STAFF_DUTY_RE.pattern
    assert m_subj.group(1) == BS.STAFF_DUTY_SUBJ_RE.pattern
    assert f"DN_STAFF_SUBJ_CHARS = {BS.STAFF_DUTY_SUBJ_CHARS};" in js
    assert "Array.from(wide).slice(-DN_STAFF_SUBJ_CHARS)" in js, "the lookback must be codepoint-exact"
    # PR #705 review [3]: the clause test is THREE-part — the port must also require the verb to
    # govern an in-window time within STAFF_DUTY_TIME_CHARS after it, or the strip marks duty
    # sentences the score never counted (contradicting #521's mirrors-never-re-derives guardrail).
    assert f"DN_STAFF_TIME_CHARS = {BS.STAFF_DUTY_TIME_CHARS};" in js
    assert "const tps = dnTimeOffsets(text)" in js, "the port must consult the in-window time offsets"
    assert "o >= end && o <= end + fwd" in js, "a match with no governed time must not paint"
    # and it must be gated on the SERVER's vote, never re-derived client-side
    assert 'd.name === "lf_staff_day"' in js
    assert "dnStaffDutyOffsets" in js


def test_console_surfaces_the_staff_day_confusable_to_the_labeler():
    """UI-visibility requirement (the standing rule for console rework): the staff-day shape must be
    reachable at gate@5 — the coarse office/building-hours checkbox is hinted by BOTH detectors and its
    tooltip names the employee-handbook shape, so a human can record the disagreement the tuning loop
    consumes."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert '["lf_office_hours", "lf_staff_day"]' in js, \
        "office_building_hours must be hinted by both detectors"
    assert "Array.isArray(det)" in js, "the multi-detector hint must actually be applied"
    assert "EMPLOYEE/STAFF day (#684)" in js, "the tooltip must name the staff-day shape"
    # the OBJECTIVE signals panel must show the demoting evidence itself, not merely imply it via a
    # pre-checked box — a labeler who disagrees needs to see the counts the scorer acted on.
    assert "staff duty-day times (#684)" in js, "the signals panel must carry the staff-day row"
    assert "s.staff_duty_times || 0" in js, \
        "the row must tolerate a record whose signals predate the field (#702 absence-vs-empty)"
    # Playwright-verified end-to-end against the live record on 2026-07-29 (11/11 checks):
    # infrastructure/scraper/verify_684_console.mjs


def test_measure_script_reads_the_shared_text_bases():
    """PR #705 review [4]: the rerunnable measurement script must derive its text bases from the LIVE
    `build_signals.text_bases` — a hand-copied duplicate silently drifts from what the scorer stores,
    invalidating a re-run's 'acc 1.000' claim without anyone noticing."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "docs/technical-notes/"
           "production-quality-control-research/2026-07-29-issue684-staff-day-measure.py").read_text()
    assert "BS.text_bases(" in src
    # the tell-tale of a re-implemented basis selection is the table-source list spelled locally
    assert "camelot_hybrid" not in src, "basis selection must not be re-implemented in the script"
    # and compute_signals itself must consume the same helper (one selection, two consumers)
    import inspect
    assert "text_bases(" in inspect.getsource(BS.compute_signals)


def test_event_weight_is_registered_and_signed():
    assert D.EVENT_WEIGHTS["staff_duty"] == (-1, 0.7)
    assert D.EVENT_CONFIDENCE_SOURCE["staff_duty"] == "lf_staff_day"
    vote = D.lf_staff_day(sig(staff_duty_times=2, student_ref_times=0), D.DEFAULT_DETECTOR_PARAMS)
    assert vote.confidence == D.EVENT_WEIGHTS["staff_duty"][1]


def test_the_signal_is_emitted_by_compute_signals(tmp_path):
    """End-to-end through the real signal builder, not just the helper: the two keys must reach
    signals_json, or the detector reads absence forever (the #688 failure mode)."""
    (tmp_path / "camelot_stream.txt").write_text("| --- |\n" + BENTONVILLE_TEXT)
    texts = [{"usable": True, "text_file": "camelot_stream.txt", "source": "camelot_stream",
              "n_times": 12, "n_chars": len(BENTONVILLE_TEXT)}]
    s, _, _ = BS.compute_signals(tmp_path, texts, [], {})
    assert s["staff_duty_times"] > s["student_ref_times"] >= 0
    assert json.loads(json.dumps(s))["staff_duty_times"] == s["staff_duty_times"]   # JSON-safe
    assert "lf_staff_day" in C.score_record(s)["fired"]
