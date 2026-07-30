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


def test_corpus_fp_class_still_rejected():
    """The measured false-positive class, pinned verbatim. Since the #704 review round these are
    rejected by the REGEX SHAPE itself (no instruction referent / no day scope / a parenthetical
    breaking adjacency), not by the antecedent guard — the threshold hedges were removed from the
    guard because they did zero corpus work while rejecting statutory declarations."""
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


# ---------------- #704 review round: the guard is INTERVAL-only, thresholds are declarations ----------------
def test_statutory_threshold_declarations_fire():
    """#704 review (CONFIRMED, fails against the first-shipped guard): "at least N minutes of
    instruction per day" IS the canonical statutory-minimum phrasing — semantically identical to
    the kept Aspire case ("a minimum of 240..."), differing only in wording. The threshold hedges
    were removed from the antecedent guard: measured on the full corpus they changed the outcome
    of ZERO records (every real FP already fails the number+instruction+day-scope regex), so they
    only cost this false-negative class. Symmetry pinned too ("no fewer than" was already True)."""
    for s in ("Elementary schools shall provide at least 330 minutes of instruction per day.",
              "The school day shall consist of no more than 400 minutes of instruction per day.",
              "The district requires no fewer than 330 minutes of instruction per day.",
              "Approximately 350 minutes of instruction per day are provided."):
        assert BS.instructional_declaration(s), s


def test_interval_guard_still_rejects_with_full_day_scope():
    """The guard's REAL work, exercised against the actual regex (#704 review: the old KIPP test
    string had no day scope, so the regex never matched and the or-conjunction clause was dead
    weight in that test) — a day-scoped interval must be rejected BY THE GUARD, incl. across the
    "or" conjunction, and at the very start of the string (the lookback's m.start()<40 edge)."""
    for s in ("during the first 30 minutes of instruction per day",
              "during the first or last 10 minutes of instruction per day",
              "first 30 minutes of instruction per day"):        # match near offset 0
        assert not BS.instructional_declaration(s), s
    # identical sentence, antecedent removed -> the regex fires: proves the guard did the work
    assert BS.instructional_declaration("30 minutes of instruction per day")


def test_empty_and_none_inputs_are_false():
    assert not BS.instructional_declaration("")
    assert not BS.instructional_declaration(None)


# ---------------- #704 review round: the recall-unchanged claim, enforced hermetically ----------------
# The measurement report claims the 4 target-labeled records that LOST the signal stay tier A on
# other detectors. That was verified live but enforced nowhere — a future weakening of
# lf_time_table / lf_prose_pair / lf_heading_hours could silently regress it. These are the REAL
# signals_json rows (trimmed of bulky page-level lists; trim verified tier-preserving), embedded
# 2026-07-29 with instructional_time already False.
import json as _json

_DEMOTED_SIGNAL_FIXTURES = _json.loads("""\
{"3800038:f962d4236d":{"cms_hint":null,"content_school_year":"2025-\n\
26","dechromed":false,"decision":"send","embed_hosts":[],"footer_hours":{"hit":false,"office":fa\n\
lse,"times":0},"harvest_pages":[5],"has_table":true,"header_hours":{"hit":false,"office":false,"\n\
times":0},"heading_hours_hits":3,"heading_hours_labels":["school day"],"instructional_time":fals\n\
e,"is_handbook":true,"max_text_chars":321019,"n_times":63,"n_times_in_window":59,"neg_total":14,\n\
"negative_kw":{"board":["school board"],"calendar":["school calendar","holiday","early\n\
release","early dismissal","no school","in service","first day of\n\
school"],"sports":["athletic","athletics","sports","varsity"],"transport":["bus\n\
route","transportation department"]},"nonstandard_day":false,"nonstandard_heading":0,"nonstandar\n\
d_near_times":2,"period_hits":2,"positive_kw":["school hours","school day","dismissal","pick\n\
up","class schedule"],"proximity_pairs":730,"regular_day_language":true,"roster_school_names_hit\n\
":2,"schedule_link_only":false,"table_period_rows":0,"table_time_density":51,"times_after_5pm":2\n\
,"url_feed_pattern":false,"url_rootish":false,"visual_text_gap":false},"4000766:2f764d7fa2":{"cm\n\
s_hint":null,"content_school_year":"2022-\n\
23","dechromed":false,"decision":"send","embed_hosts":[],"footer_hours":{"hit":false,"office":fa\n\
lse,"times":0},"harvest_pages":[13,14],"has_table":true,"header_hours":{"hit":false,"office":fal\n\
se,"times":0},"heading_hours_hits":4,"heading_hours_labels":["school day","school hours"],"instr\n\
uctional_time":false,"is_handbook":true,"max_text_chars":119292,"n_times":47,"n_times_in_window"\n\
:33,"neg_total":3,"negative_kw":{"board":["agenda"],"calendar":["first day of school"],"sports":\n\
["sports"],"transport":[]},"nonstandard_day":false,"nonstandard_heading":1,"nonstandard_near_tim\n\
es":4,"period_hits":0,"positive_kw":["school hours","school day","arrival","homeroom","pick up"]\n\
,"proximity_pairs":22,"regular_day_language":false,"roster_school_names_hit":1,"schedule_link_on\n\
ly":false,"table_period_rows":0,"table_time_density":21,"times_after_5pm":6,"url_feed_pattern":f\n\
alse,"url_rootish":false,"visual_text_gap":false},"4000766:97161c6a76":{"cms_hint":null,"content\n\
_school_year":"2023-\n\
24","dechromed":false,"decision":"send","embed_hosts":[],"footer_hours":{"hit":false,"office":fa\n\
lse,"times":0},"harvest_pages":[8,13,22],"has_table":true,"header_hours":{"hit":false,"office":f\n\
alse,"times":0},"heading_hours_hits":4,"heading_hours_labels":["school day","school hours"],"ins\n\
tructional_time":false,"is_handbook":true,"max_text_chars":130756,"n_times":80,"n_times_in_windo\n\
w":71,"neg_total":2,"negative_kw":{"board":["agenda"],"calendar":["first day of school"],"sports\n\
":[],"transport":[]},"nonstandard_day":true,"nonstandard_heading":1,"nonstandard_near_times":5,"\n\
period_hits":0,"positive_kw":["school hours","school day","dismissal","arrival","homeroom","pick\n\
up"],"proximity_pairs":525,"regular_day_language":false,"roster_school_names_hit":1,"schedule_li\n\
nk_only":false,"table_period_rows":0,"table_time_density":12,"times_after_5pm":5,"url_feed_patte\n\
rn":false,"url_rootish":false,"visual_text_gap":false},"4824000:af06722adb":{"cms_hint":"sharpsc\n\
hool.com","content_school_year":"2025-\n\
26","dechromed":false,"decision":"send","embed_hosts":[],"footer_hours":{"hit":false,"office":fa\n\
lse,"times":0},"harvest_pages":[],"has_table":true,"header_hours":{"hit":false,"office":false,"t\n\
imes":0},"heading_hours_hits":0,"heading_hours_labels":[],"instructional_time":false,"is_handboo\n\
k":true,"max_text_chars":333197,"n_times":7,"n_times_in_window":5,"neg_total":11,"negative_kw":{\n\
"board":["board of education","board of trustees","board meeting","school\n\
board","trustees","agenda"],"calendar":["early\n\
dismissal"],"sports":["athletic","athletics","sports"],"transport":["bus route"]},"nonstandard_d\n\
ay":true,"nonstandard_heading":0,"nonstandard_near_times":0,"period_hits":0,"positive_kw":["scho\n\
ol hours","school day","start time","dismissal","arrival","drop-off","pick up","class schedule"]\n\
,"proximity_pairs":3,"regular_day_language":false,"roster_school_names_hit":2,"schedule_link_onl\n\
y":false,"table_period_rows":0,"table_time_density":5,"times_after_5pm":2,"url_feed_pattern":fal\n\
se,"url_rootish":false,"visual_text_gap":false}}""".replace("\n", ""))


def test_target_records_that_lost_the_signal_stay_tier_A():
    for rk, sig in _DEMOTED_SIGNAL_FIXTURES.items():
        assert sig["instructional_time"] is False, rk       # the fixture really lacks the signal
        out = COMB.score_record(dict(sig))
        assert out["tier"] == "A" and out["decision"] == "send", \
            f"{rk}: a target-labeled record lost tier A without instructional_time — " \
            f"the #683 recall-unchanged claim regressed (see the measurement report)"
