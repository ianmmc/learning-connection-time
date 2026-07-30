"""#683 — `instructional_time` must mark a DECLARATION of the school day, not an interval in it.

`lf_explicit_minutes` turns this signal into the bank's highest-confidence target vote (strong,
0.95) and names `explicit_instructional_time` as the category, so a false fire sends a document
with no bell schedule to paid extraction (the `MONEY_LEAK_WHERE` population).

Every string below is VERBATIM from the labeled corpus (the record it came from is named), which
is what makes this a regression pin rather than a restatement of the regex: the old form fired on
15 records and was wrong on 13 of them. Measured report:
`docs/technical-notes/production-quality-control-research/2026-07-29-issue683-instructional-declaration-measurement.md`
"""
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage5_filter import combiner as COMB


# --------- the FALSE-POSITIVE class: a number bounding a PART of the day, or no number at all ---
def test_bentonville_attendance_deadline_is_not_a_declaration():
    """#683's filing case — Bentonville `0503060:a5f32ff869`, an employee handbook whose ONLY
    match was a clerical deadline. Ian labeled it `target_absent`; it was a tier-A auto-send."""
    assert not BS.instructional_declaration(
        "Attendance must be submitted during the first 30 minutes of class.")


def test_interval_and_threshold_antecedents_are_not_declarations():
    for s in (
        # KIPP OKC `4000766:97161c6a76` / `:2f764d7fa2` — the "first or last" conjunction
        "not permitted to use the restroom during the first or last 10 minutes of class.",
        # `3800038:f962d4236d` — an attendance threshold
        "Students who miss more than 15 minutes of class will be marked absent.",
        # Huntington `4824000:af06722adb` — a physical-activity rate
        "moderate or vigorous physical activity for at least 30 minutes per day",
        # `0503060:55586405a4` — a course-catalog load CEILING, not the day's length
        "no more than, 360 minutes of instruction (4 periods) per day",
    ):
        assert not BS.instructional_declaration(s), s


def test_non_day_referents_are_not_declarations():
    for s in (
        "The expectation is that students practice 10 minutes per day or 70 minutes per week.",  # 5510620
        "A reading opportunity of 60 minutes per day will be promoted",                          # 1730540
        "release your inner explorer, just a few minutes per day.",                              # 1725260
        "Approximately 60 minutes per class will be devoted to participation",                   # 0503060
        "students received a total of 90 minutes of instruction in each subject",                # 4700148
    ):
        assert not BS.instructional_declaration(s), s


def test_number_less_compliance_prose_is_not_a_declaration():
    """Bare 'instructional minutes' states that minutes are TRACKED, never how many — `0513530`
    and `0634320` both auto-sent on exactly this."""
    for s in ("District runs an Alternate Calendar that is based on Instructional Minutes.",
              "verify compliance with the instructional minutes required by the state",
              "15. Physical education instructional minutes;"):
        assert not BS.instructional_declaration(s), s


# --------------------- the TRUE positives: both survivors, kept verbatim ---------------------
def test_genuine_declarations_still_fire():
    """The only 2 of 15 corpus records whose signal was correct — the coverage this fix must not
    cost. `4700148:00f553bcfc` and `0602095:6e8db3e114` (a `school_start_end_list` target)."""
    assert BS.instructional_declaration(
        "We have 181 instructional days with 495 minutes of instruction per day.")
    assert BS.instructional_declaration(
        "Students must be enrolled in a minimum of 240 instructional minutes per school day")
    # the pattern's original stated intent (design note / #683's own framing)
    assert BS.instructional_declaration("students receive 330 minutes of instruction per day")
    assert BS.instructional_declaration("The elementary day provides 360 minutes of "
                                        "instructional time per day")


def test_req093_hours_reversion_still_holds():
    """The prior measured reversion is untouched: hours phrasings stay OUT (a vision problem —
    they false-positived on marketing copy), as does board-meeting 'minutes'."""
    for s in ("our instructional hours are flexible", "147 days x 7.5 hrs/day",
              "board meeting minutes approved"):
        assert not BS.instructional_declaration(s), s


# ------------------------------- the vote it drives -------------------------------
def test_the_signal_still_drives_the_strong_vote_when_it_is_true():
    """The fix narrows WHEN the signal fires, never what it means downstream: a genuine
    declaration still earns the strong `explicit_instructional_time` vote (the DUNSEITH rescue —
    a calendar record with no clock times stays alive on it)."""
    sig = {"visual_text_gap": False, "positive_kw": [], "proximity_pairs": 0, "n_times": 0,
           "n_times_in_window": 0, "instructional_time": True, "has_table": False,
           "period_hits": 0, "neg_total": 2, "harvest_pages": [],
           "negative_kw": {"board": [], "sports": [], "calendar": ["academic calendar"],
                           "transport": []}}
    out = COMB.score_record(sig)
    assert out["decision"] == "send" and out["tier"] == "A"
    assert out["category"] == "explicit_instructional_time"


def test_predicate_is_the_one_home_not_the_bare_regex():
    """`INSTRUCTIONAL_RE` alone is NOT the predicate — the antecedent guard is half the rule, so a
    caller that re-spells `INSTRUCTIONAL_RE.search(...)` re-introduces the false-positive class.
    Pin that the production call site routes through the shared helper (#683)."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "infrastructure/acquisition/stage5_filter/build_signals.py").read_text()
    assert "instructional = instructional_declaration(all_text)" in src
    assert "INSTRUCTIONAL_RE.search(all_text)" not in src
    # the guard really is load-bearing: same sentence, antecedent removed -> it fires
    assert BS.INSTRUCTIONAL_RE.search("during the first 30 minutes of instruction per day")
    assert not BS.instructional_declaration("during the first 30 minutes of instruction per day")
