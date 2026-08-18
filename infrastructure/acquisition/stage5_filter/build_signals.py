#!/usr/bin/env python3
"""Stage 5 review-app ingest + DETERMINISTIC signal computation (NO AI at runtime).

Walks data/raw/lea-website-captures/<district>/, reads Stage 3 (captures.json) + Stage 4
(processed.json), and for every ok record computes a vector of deterministic signals, a
likelihood TIER, a weak CATEGORY HYPOTHESIS, content-hash dedup, and a per-district topology
hypothesis. Writes to a SQLite DB that backs the review app.

This is the heart of the Stage 5 data-collection exercise: the script classifies/tiers, the
human supplies the ground-truth labels (a separate table), and labels are PRESERVED across
re-ingest so heuristics can be refined without losing hand-entered judgments. See
docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE5_FILTER_DESIGN.md.

Usage:  python3 build_signals.py [--root data/raw/lea-website-captures] [--db <path>]
"""
import argparse
import bisect
import hashlib
import json
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import paths  # noqa: E402  (single source of truth for runtime-state locations — REQ-087)
from infrastructure.acquisition.common import config_loader  # noqa: E402  (Stage 5 keyword knobs — REQ-088/093)
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (isolated governance Postgres engine/session — REQ-103)
from infrastructure.acquisition.common import cache_ingest as CI  # noqa: E402  (shared cross-stage cache schema + UPSERTs — REQ-103c, now common/)
from infrastructure.acquisition.stage5_filter import models  # noqa: F401,E402  (registers PRECIOUS Label/ClusterSplit on gdb.Base)
from infrastructure.acquisition.stage5_filter import attention as AT  # noqa: E402  (the district-driven attention score)
from infrastructure.acquisition.stage5_filter import combiner as COMB  # noqa: E402  (V2 labeling-function combiner — REQ-113)
from infrastructure.utilities import school_year as SY  # noqa: E402  (calendar-vocabulary SSOT; the content_school_year read — #107, NOT the LCT DB)

RAW_DIR = paths.RAW_CAPTURES
QUEUE_DIR = paths.QUEUE_DIR                   # Stage 1 batch_*.json (targeting + NCES denominator)
# Durable, version-controlled source of truth for the PRECIOUS human labels. The DB is a
# regenerable cache; this JSON is what survives DB loss and lives in git (gitignore re-includes
# it). Written on every label save (server) + at the end of each ingest; re-imported on ingest.
LABELS_JSON = paths.LABELS_JSON
# The v2.1 label object (REQ-114): primary + facets + note + status. The legacy v2.0 `flags_json`
# column is an inert archive (values folded into facets by migrate_label_v21; the human `duplicate`
# flag retired — programmatic dedup via record.duplicate_of + clustering owns that now). Not
# exported/imported/written anywhere; historical values live in the DB column + labels.json git history.
LABEL_COLS = ["rec_key", "primary_label", "facets_json", "note", "status", "updated_at"]
# Durable backup for the OTHER precious human signal: cluster SPLITS (a record the reviewer
# pulled out of an auto-cluster because it's genuinely unique). Like labels, survives DB wipe.
CLUSTER_SPLITS_JSON = paths.CLUSTER_SPLITS_JSON

NCES_YEAR = "2024_25"   # ccd_sch_029 source for the topology denominator (school counts)

# ---- near-duplicate clustering (deterministic, content-similarity, NO AI) ----
SHINGLE_K = 3              # word k-shingles
CLUSTER_THRESHOLD = 0.90  # Jaccard >= this clusters. CONSERVATIVE on purpose: the only remedy
# is split (no easy re-merge), so under-cluster (a few extra clicks) rather than over-cluster
# (wrongly hide a unique page). Stroudsburg's normal vs 2-hr-delay schedules differ enough to
# stay apart; printer-friendly/?id= variants of one page sit ~1.0.
TIER_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}

# ---- labeled-topology taxonomy (derived from human labels + NCES; see the design note) ----
# V2.1 target SHAPES (Ian, 2026-07-01): the primary axis is now the target's shape (single-choice),
# distinct because each shape derives minutes + routes to Stage 6/7 differently. Non-targets moved OFF
# this axis into multi-select confounder FACETS (a page can carry several) + the terminals target_absent
# / unusable. See STAGE5_FILTER_DESIGN §4.
TARGET_LABELS = {"school_start_end_list", "school_bell_table", "school_start_end_prose",
                 "district_hub_by_school", "district_hub_by_band",
                 "explicit_instructional_time", "target_other_shape"}
SCHOOL_LEVEL_LABELS = {"school_start_end_list", "school_bell_table", "school_start_end_prose"}
HUB_LABELS = {"district_hub_by_school", "district_hub_by_band"}
# The terminal (non-target) primary values — everything else a record can be on Axis 1.
NONTARGET_PRIMARIES = {"target_absent", "unusable"}
# One-time relabel map (v2.0 → v2.1), used by migrate_labels_v21. Non-target v2.0 labels don't appear here
# — they map to primary=target_absent + a confounder facet (the migration handles that separately).
LEGACY_LABEL_MAP = {
    "school_bell_schedule": "school_bell_table",
    "district_hub_schedule": "district_hub_by_school",   # by_school is the common case; human re-confirms by_band
    "nonstandard_format": "target_other_shape",
    "none": "target_absent",
    # unchanged: school_start_end_prose, explicit_instructional_time, unusable
}
# v2.0 non-target labels → the confounder facet they become (primary → target_absent).
LEGACY_NONTARGET_TO_FACET = {
    "board_schedule": "board", "sports_schedule": "sports", "academic_calendar": "academic_calendar",
    "community_calendar": "community_calendar", "transportation_schedule": "transportation",
    "embedded_feed": "news_feed", "other_schedule": "other_schedule",
}

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*([AaPp])?\.?[Mm]?\.?")
USABLE_MIN_CHARS = 120
PROXIMITY_CHARS = 220          # two times within this many chars = a plausible start/end pair
WINDOW_LO, WINDOW_HI = 7 * 60, 16 * 60   # plausible school-day window (minutes since midnight)
AFTER_5PM = 17 * 60

# Keyword classes are now config-as-data knobs (REQ-093) — tune them as config edits, not code.
POSITIVE_KW = config_loader.values("stage5_positive_kw")
NEG_BOARD = config_loader.values("stage5_neg_board")        # each negative class -> a likely non-target category
NEG_SPORTS = config_loader.values("stage5_neg_sports")
NEG_CALENDAR = config_loader.values("stage5_neg_calendar")
NEG_TRANSPORT = config_loader.values("stage5_neg_transport")
# Instructional-time declaration — ANCHORED so board-meeting "minutes" never false-positives.
# MINUTES-ONLY, deliberately. REQ-093 tried adding HOURS patterns ("7.5 hrs/day") to rescue
# DUNSEITH, but the MEASUREMENT HARNESS proved the broadening net-NEGATIVE: DUNSEITH's real
# "147 days x 7.5 hrs/day" sits in a VISUAL CALENDAR GRID that text extraction mangles into
# "...5 hrs" (no contiguous "/day"), so the regex can't match the real targets, while broad hours
# phrasings ("instructional hours", "hours per day") false-positived on marketing copy
# (Lindamood-Bell) and wrongly rescued a `none` record to tier B. Conclusion: hours-in-calendar is
# a VISION / de-chrome problem (REQ-091 / Tier-3), not a keyword-regex one. Reverted to minutes-only.
#
# #683 (2026-07-29, MEASURED over the labeled corpus — see the dated report in
# production-quality-control-research/): the prior form matched any "N minutes of class" and the
# bare phrase "minutes per day", which is an INTERVAL/RATE shape, not a DECLARATION of the day.
# Corpus truth: the signal fired on 15 records and was WRONG on 13 — "first 30 minutes of class"
# (an attendance deadline, #683's Bentonville case), "miss more than 15 minutes of class", "at
# least 30 minutes per day" of physical activity, "practice 10 minutes per day", "just a few
# minutes per day" (marketing), and bare "instructional minutes" state-compliance prose with no
# number at all. Only 2 were genuine ("240 instructional minutes per school day [Ed Code]",
# "181 instructional days with 495 minutes of instruction per day").
#
# A DECLARATION therefore requires all three, and the corpus says nothing weaker discriminates:
#   (1) a NUMBER — bare "instructional minutes" compliance prose declares no length;
#   (2) an INSTRUCTION referent — "minutes per class/subject/week" is a portion, not the day;
#   (3) DAY scope — "per day" / "per school day".
# Plus a preceding-token guard for INTERVAL antecedents only (first/last/within/during/after/…):
# "during the first 30 minutes of instruction per day" bounds a PART of the day. Threshold hedges
# (at least / more than / no more than / approximately) are deliberately NOT in the guard — the
# #704 review proved they reject the canonical STATUTORY phrasing ("at least 330 minutes of
# instruction per day" is a minimum-day declaration, semantically identical to Aspire's kept
# "a minimum of 240 instructional minutes per school day"), while doing ZERO corpus work: under
# the number+instruction+day-scope regex, every measured FP ("miss more than 15 minutes of
# class", "at least 30 minutes per day" of PE) already fails the regex itself — measured guard-
# changed-outcome records on the full corpus: 0 (see the measure script's --guard-audit).
# Overall measured effect: 13 wrong signals removed, both genuine ones kept, ZERO tier-A
# target-labeled records demoted (every one is carried by other detectors), 4 of the 6
# `target_absent` false-sends demoted out of tier A.
#
# STILL MINUTES-ONLY, deliberately — the REQ-093 hours reversion (see the block above) stands:
# hours-in-calendar is a VISION problem, not a keyword-regex one.
INSTRUCTIONAL_RE = re.compile(
    r"(\d{2,4})\s*(?:minutes|mins)\s+(?:of\s+)?instruction(?:al)?\s*(?:time\s+)?"
    r"per\s+(?:school\s+)?day"
    r"|(\d{2,4})\s*instructional\s+(?:minutes|mins)\s+per\s+(?:school\s+)?day", re.I)
# INTERVAL antecedents immediately BEFORE the number — the match bounds a part of the day, not
# its length. Anchored to the end of the preceding text so only the adjacent phrase counts;
# `(?:or\s+\w+\s+)?` catches the "first or last 10 minutes" conjunction (live: KIPP OKC).
# Threshold hedges are deliberately absent — see the declaration comment above (#704 review).
INSTRUCTIONAL_NEG_ANTE = re.compile(
    r"(?:first|last|final|within|during|after|every|each)\s+(?:or\s+\w+\s+)?$", re.I)


def instructional_declaration(text: str) -> bool:
    """Does the text DECLARE the instructional length of the school day? (#683) The ONE home for
    this question — `INSTRUCTIONAL_RE` alone is not the predicate: a match still has to survive the
    interval/threshold antecedent guard, and callers that skip it re-introduce the measured
    false-positive class (a 0.95-confidence `lf_explicit_minutes` vote on an attendance rule)."""
    for m in INSTRUCTIONAL_RE.finditer(text or ""):
        if not INSTRUCTIONAL_NEG_ANTE.search(text[max(0, m.start() - 40):m.start()]):
            return True
    return False
PERIOD_RE = re.compile(r"\bperiod\s*\d|\b\d(?:st|nd|rd|th)\s+period", re.I)

# ---- V2 (REQ-113) content-shape signals ----
# Words that, near a time-range, mark it as an INTENTIONAL "hours" statement (vs. an incidental time).
HOURS_INTENT_KW = ["school hours", "school day", "hours of operation", "start time", "end time",
                   "dismissal", "arrival", "first bell", "last bell", "bell schedule", "school starts",
                   "school ends", "class begins", "classes begin", "doors open", "instructional day"]
# Hours that belong to the OFFICE/STAFF, not the student day (the research's #1 confusable, §5.2).
OFFICE_HOURS_KW = ["office hours", "office is open", "main office", "front office", "staff hours",
                   "staff day", "workday", "work day", "teacher hours", "building hours", "administrative"]
# ---- The non-regular-day vocabulary (#537) — THREE regexes, ONE review surface. Edit them TOGETHER: ----
# a term added to the CLASS (what a non-regular day looks like) usually implies checking the GUARD (how a
# page names its regular day) and vice versa; a drift between them is a measured failure mode (PR #538
# review). NONSTANDARD_DAY_KW (the legacy anywhere-in-text class) is pinned as a SUBSET of
# NONSTANDARD_TERM_RE by test_nonstandard_term_re_covers_legacy_kw, so tuning the class can't silently
# strand the legacy signal.
# (1) The legacy anywhere-in-text class — kept as the SOFT-vote basis (weather/remote/delay variants only;
#     deliberately narrow, since a bare mention anywhere fires it — 37% of real targets mention these).
NONSTANDARD_DAY_KW = ["remote learning", "e-learning", "elearning", "weather event", "2-hour delay",
                      "2 hour delay", "two hour delay", "early dismissal schedule", "delayed start",
                      "virtual day", "snow day", "inclement weather", "distance learning"]
# (2) The FULL facet term class, used POSITIONALLY (#537 follow-on). The anywhere boolean above is a weak
# discriminator both ways (measured 2026-07-18 on the 44-record facet ground truth): it recalled 12/44
# (no summer/event/exam/foggy/substitute terms), and 63 of its 123 false claims were bare "inclement
# weather" POLICY prose nowhere near a schedule. What separates the non-regular-day PAGE (DASD's "Early
# Dismissal Bell Schedule" table) from a regular-day page that merely mentions delays is WHERE the term
# sits: titling a schedule, or adjacent to the in-window times themselves. Over-generic bare words are
# deliberately QUALIFIED ("registration"/"substitute" alone match ordinary school-site content — course
# registration, substitute-teacher hiring — a PR #538 review find): they fire only in an
# event-time/schedule phrasing.
NONSTANDARD_TERM_RE = re.compile(
    r"early dismissal|early release|late start|minimum day|half[- ]day|delayed (?:start|opening)|"
    r"(?:2|two)[- ]hour delay|remote learning|e.?learning|virtual (?:day|learning)|distance learning|"
    r"snow day|fog(?:gy)? day|inclement weather|weather event|summer (?:school|session|program|hours)|"
    r"extended school year|\besy\b|jump.?start|open house|"
    r"(?:student|kindergarten|fall|spring|school) registration|registration (?:day|night|dates?|times|schedule)|"
    r"back[- ]to[- ]school|exam schedule|final exam|finals schedule|substitute (?:bell )?(?:schedule|day)|act 80", re.I)
NONSTANDARD_NEAR_CHARS = 140   # a term within this many chars of an in-window time = the times are that day's
NONSTANDARD_HEAD_CHARS = 40    # a term this close BEFORE schedule/hours/bell = the term TITLES the schedule
# Word-bounded on purpose: bare "schedule"/"bell" substring-matched inside "unscheduled"/"Bellevue"
# (PR #538 review find), spuriously titling a schedule that isn't there.
NONSTANDARD_SCHED_RE = re.compile(r"\bschedules?\b|\bhours\b|\bbell\b", re.I)
# (3) The dial-back GUARD (measured 2026-07-18, rule S3): a page that ALSO declares its regular day is a
# regular-day page listing its variant sections, not a non-regular-day page — a real bell page routinely
# carries a "Minimum Day"/"Late Start" row beside the regular rows. On the load-bearing records the guard
# restored 16/37 wrongly-demoted real targets at a cost of 1/43 regained false-sends. Vocabulary covers
# the district phrasings for "the default day" (regular/daily/normal/traditional/standard — the last two
# added after the PR #538 review showed "Traditional Schedule" sites slipped the guard).
NONSTANDARD_REGULAR_RE = re.compile(
    r"regular (?:bell )?schedule|regular (?:school )?day|daily schedule|normal schedule|regular hours|"
    r"traditional (?:bell )?schedule|standard (?:bell )?schedule|standard (?:school )?day", re.I)


def nonstandard_positional(text: str, tpos: list) -> tuple:
    """(near_times, heading) occurrence counts for the non-regular-day term class (#537).
    `tpos` = in-window time char offsets in the SAME text (the max-evidence time basis). Counts, not
    booleans, on purpose: the strong/soft detector split reads them as truthy, but the magnitudes feed
    the guard-dominance measurement (STAGE5 change log 2026-07-18) and the console's evidence readout.
    The near check bisects a sorted offset list (was a linear any() per match — O(m·t), a PR #538
    review find; a big handbook has hundreds of both)."""
    tpos = sorted(tpos)
    near = heading = 0
    for m in NONSTANDARD_TERM_RE.finditer(text):
        lo = m.start() - NONSTANDARD_NEAR_CHARS
        i = bisect.bisect_left(tpos, lo)
        if i < len(tpos) and tpos[i] <= m.end() + NONSTANDARD_NEAR_CHARS:
            near += 1
        if NONSTANDARD_SCHED_RE.search(text[m.end():m.end() + NONSTANDARD_HEAD_CHARS]):
            heading += 1
    return near, heading


# ---- The STAFF-DAY confusable (#684) — the research's #1 confusable, §5.2, at CLAUSE grain ----
# An employee handbook's report-time table has every shape a bell schedule has (in-window pairs, a real
# table, "bell schedule"/"school start time"/"school hours" verbatim) — the shape is right, the REFERENT
# is wrong. #684's opening hypothesis was to widen OFFICE_HOURS_KW to the observed phrasings and vote on
# a staff word NEAR a time. MEASURED over the labeled corpus (3,559 records; see the dated report in
# production-quality-control-research/), that is a COIN FLIP: "an OFFICE_HOURS_KW term within 140 chars
# of an in-window time" fires on 84 labeled targets and 88 labeled non-targets (acc 0.512) and would
# demote 59 tier-A TARGETS to save 10 false sends. Widening the vocabulary made it worse, not better
# (acc 0.532), and a doc-level /employee handbook/ match is net-NEGATIVE too — 11 of its 17 labeled hits
# are real targets (districts publish bell tables inside and beside staff handbooks). Presence of staff
# language is simply not the signal; it is everywhere on real school pages.
#
# What DOES discriminate is the employment-obligation CLAUSE — a staff SUBJECT governing a duty VERB
# governing the time ("Elementary staff ... are to report to work by 7:15 a.m. and remain until 3:00
# p.m.") — scored RELATIONALLY against student-referent language over the same times: do the duty
# clauses govern MORE of this basis's in-window times than student referents do? Measured: acc 1.000,
# ZERO labeled targets, 7 records carry a duty clause at all and exactly ONE reads staff-owned
# (Bentonville `0503060:a5f32ff869`, #684's case). Deliberately a COMPARISON, not a tuned dominance
# threshold — a threshold picked off one record is the "measurement that could not fail" (CLAUDE.md's
# standing lesson). Stable: the verdict is identical for student windows of 140 / 220 / 300 chars.
# Word-bounded on purpose (PR #705 review [1] — the same substring-collision class the
# NONSTANDARD_SCHED_RE fix below already guards): bare "staff" substring-matched inside
# "staffed"/"understaffed"/"staffing", so a real bell page saying "the building remains fully
# staffed" near a "remain until" phrase read as a duty clause and was wrongly pulled out of auto-send.
STAFF_DUTY_SUBJ_RE = re.compile(
    r"\b(?:staff|faculty|teachers?|employees?|certified (?:staff|personnel|employees?)|"
    r"classified (?:staff|personnel|employees?)|paraprofessionals?|instructional assistants?|"
    r"principals?|administrators?|secretar(?:y|ies)|custodians?|bus drivers?)\b", re.I)
# The obligation VERB. Every arm is an employment duty, never a student instruction — a student handbook
# says "students should arrive by", not "are to report to work by" / "remain until" / "clock in".
# "report" ALWAYS requires a duty destination/preposition (PR #705 review [2]): the first-shipped bare
# "are to report"/"must report" alternatives matched every sense of the verb — "teachers are to report
# ATTENDANCE by 7:45" is attendance-taking beside a genuine bell schedule, not a workday declaration —
# and `at`/`by`/`from` are \b-anchored so "report at" can't substring-match "report attendance".
STAFF_DUTY_RE = re.compile(
    r"report(?:s|ing)?\s+(?:to\s+work|to\s+school|for\s+duty|at\b|by\b|from\b)|"
    r"remain\s+until|remain\s+on\s+duty|on\s+duty\s+(?:from|by|until)|"
    r"duty\s+(?:begins|ends|day)|clock\s+in|sign\s+in|work\s*day\s+(?:is|begins|shall)|"
    r"contract(?:ed)?\s+day", re.I)
# The competing referent: whose day is this time? A page that talks about students at its times has a
# student day on it, whatever else it also carries (#241's HOLD posture — a document can hold both).
STUDENT_REF_RE = re.compile(
    r"\bstudents?\b|\bpupils?\b|\bchildren\b|kindergart|\bgrades?\s+\d|\bk-?\d|\bpre-?k\b|"
    r"classes\s+(?:begin|start)|first\s+bell|tardy\s+bell|car\s+rider|bus\s+rider|breakfast|"
    r"\bhomeroom\b|\bdismissal\b|\barrival\b", re.I)
STAFF_DUTY_SUBJ_CHARS = 90    # a staff SUBJECT this far BEFORE the duty verb governs it
STAFF_DUTY_TIME_CHARS = 90    # a time this far AFTER the duty verb is the one it governs
STUDENT_REF_NEAR_CHARS = 140  # same "near a time" grain as NONSTANDARD_NEAR_CHARS (measured plateau)


def _offsets_between(tpos: list, lo: int, hi: int) -> set:
    """The sorted in-window offsets falling in [lo, hi] — ONE spelling of the bisect-window collect
    (PR #705 review [5]: the duty and student scans each hand-rolled this loop, and a windowing tweak
    applied to one and not the other would silently desync the two counts the #684 comparison rests on)."""
    out = set()
    i = bisect.bisect_left(tpos, lo)
    while i < len(tpos) and tpos[i] <= hi:
        out.add(tpos[i])
        i += 1
    return out


def staff_duty_positional(text: str, tpos: list) -> tuple:
    """(duty_governed, student_governed) in-window time COUNTS for ONE text basis (#684).
    `tpos` = in-window time char offsets in the SAME text — offsets never cross texts (the #538 lesson),
    which is why this is per-basis and the caller compares within a basis, never across them.
    A duty-governed time needs the full clause: a staff SUBJECT before the verb AND a time after it."""
    tpos = sorted(tpos)
    if not text or not tpos:
        return 0, 0
    duty, student = set(), set()
    for m in STAFF_DUTY_RE.finditer(text):
        if not STAFF_DUTY_SUBJ_RE.search(text[max(0, m.start() - STAFF_DUTY_SUBJ_CHARS):m.start()]):
            continue
        duty |= _offsets_between(tpos, m.end(), m.end() + STAFF_DUTY_TIME_CHARS)
    # The student scan runs ONLY when there is a duty clause for it to weigh against — the same
    # scan-only-when-there-is-evidence-to-guard shape as the #537 S3 guard above it, and load-bearing
    # for ingest cost: 7 of 3,559 corpus records carry a duty clause at all (re-measured unchanged
    # after the #705 review tightened the verbs — every corpus clause was already a destination form),
    # so this skips a whole-text regex pass on 99.8% of records (and on the 130-330k-char handbooks it
    # matters most).
    if not duty:
        return 0, 0
    for m in STUDENT_REF_RE.finditer(text):
        student |= _offsets_between(tpos, m.start() - STUDENT_REF_NEAR_CHARS,
                                    m.end() + STUDENT_REF_NEAR_CHARS)
    return len(duty), len(student)


# A heading-like occurrence of an hours-intent phrase (heading-proximity, research §2.2/§4.3).
HEADING_HOURS_RE = re.compile(
    r"(office hours|school hours|school day hours|hours of operation|bell schedule|school day|"
    r"daily schedule|arrival (?:and|&) dismissal|start and end times?)\b[:\-–—\s]*", re.I)
HEADING_PROX_CHARS = 140   # a time within this many chars AFTER an hours heading = a heading-hours hit
# NB: there is deliberately NO per-page scan cap. One lived here (15, then 60) and made pages past it
# structurally invisible — the cap itself, not the document, was the reason a target went unseen.
# `pdf_page_texts` scans the whole document in one call; do not reintroduce a ceiling here.
# A CMS news/social-feed URL shape (the #1 tier-A pollutant — incidental post times). A DOWN-WEIGHT signal.
# #226: "feed" matches as a BOUNDED token only — bare-substring would hit "feeder" (a real K-12 term:
# feeder pattern/schools) and "feedback". Left bound = separator (or camelCase for query tokens like
# smartSiteFeed/psqFeed); right bound = any non-letter.
FEED_URL_RE = re.compile(
    r"/live-feed|/announcements?\b|/news(?:/|\?|$)|[?&]page_no=|/o/[^/]+/(?:live-feed|article/\d)"
    r"|live[-_]feeds?(?![A-Za-z])"           # live_feeds/<id> permalinks, live_feed_image S3 rehosts
    r"|(?:^|[/?&=_.\-])feeds?(?![A-Za-z])"   # generic bounded token: /feed/, /feeds/, ?feed=, news-feed
    r"|[a-z]feeds?(?![a-z])",                # word-glued token, ANY case under re.I: smartSiteFeed,
    re.I)                                    # smartsitefeed, PSQFEED= — the right bound still blocks feeder/feedback
                                             # (the #539-review case-scope fix: the old (?-i:[a-z]Feed) variant
                                             # matched only exact-case camelCase and missed case-normalized URLs)


def feed_url(url: str) -> bool:
    return bool(FEED_URL_RE.search(url or ""))


# #532: a landing/homepage URL shape — the domain root or a bare CMS org slug (/o/<slug>), nothing deeper.
# The URL half of the page-focus signal (§3a obs. 1): lf_district_homepage combines it with roster-name
# breadth to spot a many-schools LANDING page (whose times are incidental news/event teasers), without
# touching deep pages that legitimately hit many roster names (a real district hub's /schedules/ page).
ROOTISH_URL_RE = re.compile(r"^https?://[^/?#]+(?:/|/o/[^/?#]+/?)?(?:[?#].*)?$", re.I)


def rootish_url(url: str) -> bool:
    return bool(ROOTISH_URL_RE.match(url or ""))


def _capture_fingerprint(cap: dict) -> dict:
    """A capture row's Stage-3 fingerprint, whichever shape the caller holds (#688): a DISK
    captures.json row carries `fingerprint` (a nested dict); a DB `capture` row carries
    `fingerprint_json` (a JSON string — cache_ingest maps disk→DB). The promotion accessors read
    disk rows at ingest but were written against the DB key, so cms_hint/embed_hosts were None/[]
    on all 3,559 records while 2,653 capture fingerprints held real vendor hints — invisible
    because None is a legal value and nothing asserted corpus-level non-nullness (the seam is now
    pinned by assert_fingerprint_promotion, run inside every full ingest)."""
    fp = cap.get("fingerprint")
    if isinstance(fp, dict):
        return fp
    try:
        return json.loads(cap.get("fingerprint_json") or "{}") or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def cms_hint_of(cap: dict) -> str | None:
    """The Stage-3 cms_hint for a capture (REQ-115): promoted from the buried fingerprint into a record signal
    — a GROUPING key for per-detector accuracy, not a score input."""
    return _capture_fingerprint(cap).get("cms_hint")


def embed_hosts_of(cap: dict) -> list:
    """Categorized iframe/embed host tags for a capture (REQ-115) — social/calendar/doc-viewer/other, from
    the Stage-3 fingerprint. Empty for pre-REQ-115 captures (the field isn't on disk yet); populated for
    future captures + used structurally by lf_news_feed / lf_calendar_widget."""
    return list(_capture_fingerprint(cap).get("embed_hosts") or [])


def in_window_positions(text: str):
    """Time positions (char_offset, minutes) that fall inside the plausible school-day window."""
    return [(off, m) for off, m in time_positions(text) if WINDOW_LO <= m <= WINDOW_HI]


def proximity_pairs(tps: list) -> int:
    """Distinct in-window times within PROXIMITY_CHARS of each other = plausible start/end pair(s)."""
    prox = 0
    for i in range(len(tps)):
        for j in range(i + 1, len(tps)):
            if tps[j][0] - tps[i][0] > PROXIMITY_CHARS:
                break
            if tps[i][1] != tps[j][1] and WINDOW_LO <= tps[i][1] <= WINDOW_HI and WINDOW_LO <= tps[j][1] <= WINDOW_HI:
                prox += 1
    return prox


def hours_block(text: str) -> dict:
    """A time-range in `text` that reads as an intentional hours statement: an in-window proximity pair
    with an hours-intent word nearby. Returns {hit, times, office} — `office` flags the staff/office
    confusable. Used for the footer/header segment scan (REQ-113 §2a-1) and heading proximity."""
    lc = (text or "").lower()
    iw = in_window_positions(text or "")
    hit = proximity_pairs(iw) >= 1 and any(k in lc for k in HOURS_INTENT_KW)
    office = any(k in lc for k in OFFICE_HOURS_KW)
    return {"hit": bool(hit), "times": len(iw), "office": bool(office)}


def heading_hours_hits(text: str) -> dict:
    """Count time-ranges that sit just after an hours-intent HEADING (heading-proximity), capturing the
    matched heading phrase(s) — turns the office-vs-school-hours confusable into a structured field."""
    labels, hits = [], 0
    for m in HEADING_HOURS_RE.finditer(text or ""):
        window = text[m.end(): m.end() + HEADING_PROX_CHARS]
        if in_window_positions(window):
            hits += 1
            labels.append(m.group(1).lower())
    return {"count": hits, "labels": sorted(set(labels))}


# ----------------------------- helpers -----------------------------
def md5_file(p: Path) -> str:
    h = hashlib.md5()
    h.update(p.read_bytes())
    return h.hexdigest()


def md5_text(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", "replace")).hexdigest()


def to_minutes(hh: int, mm: int, ap: str | None) -> int | None:
    if ap:
        ap = ap.lower()
        if ap == "p" and hh != 12:
            hh += 12
        elif ap == "a" and hh == 12:
            hh = 0
    else:
        # bare time in a school context: 1-6 -> afternoon, 7-12 -> morning/noon
        if 1 <= hh <= 6:
            hh += 12
    if hh > 23 or mm > 59:
        return None
    return hh * 60 + mm


def time_positions(text: str):
    out = []
    for m in TIME_RE.finditer(text):
        mins = to_minutes(int(m.group(1)), int(m.group(2)), m.group(3))
        if mins is not None:
            out.append((m.start(), mins))
    return out


def keyword_hits(text_lc: str, kws: list) -> list:
    return [k.strip() for k in kws if k in text_lc]


# The subprocess failures we expect from a poppler tool on a bad file or a slow box. Deliberately
# NOT a bare `except Exception` (#831): a TypeError/AttributeError from a caller bug would be
# swallowed and re-read as "the tool failed", which is precisely the silent-loss class this
# module exists to remove.
_TOOL_ERRORS = (subprocess.TimeoutExpired, OSError)


def pdf_page_count(pdf: Path):
    """The page count `pdfinfo` reports, or **None when it could not be determined** — a timeout,
    a missing binary, a non-zero exit, or a `Pages:` line that never appears.

    Returning None (not 1) on failure is the #830 fix. The old `return 1` sentinel COLLIDED with a
    real value: a caller cross-checking a correct 50-way `pdftotext` split against a "count" of 1
    threw the correct result away and kept page 1 only — a genuinely multi-page document silently
    read as single-page, with `harvest_pages` / `timebearing_pages` / `lf_no_times` all computed
    on the truncated view. `None` makes "unknown" distinguishable from "one"."""
    try:
        r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30)
    except _TOOL_ERRORS:
        return None
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def pdf_page_text(pdf: Path, page: int) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
                               capture_output=True, text=True, timeout=30).stdout or ""
    except _TOOL_ERRORS:
        return ""


# Whole-document extraction gets real headroom: the per-page primitive's 30s is per PAGE (never
# slow), but one call over a 783-page PDF is a different order of work.
PDFTOTEXT_TIMEOUT_S = 180
# #831(5): the per-page FALLBACK's own worst case is n × 30s, and n is no longer capped at 60. On
# the corpus's largest document (1,017 pages) that is theoretically ~8.5h — but only if EVERY page
# times out, and a per-page call takes ~20-50ms in practice. Rather than reintroduce a page cap
# (the exact bug #828 removed), the fallback stops early once it has spent this much wall-clock,
# and stops loudly: whatever it did read is returned and the shortfall is visible in the mismatch
# between len(result) and the page count, which `page_time_signals` consumers can see.
PDF_FALLBACK_BUDGET_S = 600

# Fallback telemetry (#831(4)): WHY the one-call path was rejected, counted per process so an
# ingest can report how often each branch fired instead of the cause being invisible without DB
# archaeology. Keys are stable strings; consumers may read this after ingest and reset it.
PDF_TEXTS_FALLBACKS = Counter()



class PageTexts(list):
    """The list `pdf_page_texts` returns, plus ONE flag: `complete` — did the scan reach every
    page? A plain list to every existing caller (15 tests, 2 measurement scripts, the ingest); the
    one consumer that must not scope over a truncated prefix (`time_bearing_pages`'s lossless
    claim, #839) reads `.complete`. Kept as a subclass rather than a tuple return so the contract
    change costs no caller anything and there is no second `pdfinfo` to compute it."""
    __slots__ = ("complete",)

    def __init__(self, texts=(), *, complete: bool = True):
        super().__init__(texts)
        self.complete = complete


def pdf_page_texts(pdf: Path) -> "PageTexts":
    """Per-page text for the WHOLE document — `out[N-1]` is page N. ONE `pdftotext -layout` call,
    split on the form feed pdftotext emits between pages (measured identical to the per-page
    `-f/-l` extraction, and ~3x faster on a 154-page doc: one fork instead of N).

    NEVER returns [] for a real PDF. That guarantee is load-bearing, not defensive style: an empty
    `pages` empties `harvest_pages`, which re-arms `lf_no_times` (detectors.py) and can suppress a
    record out of dispatch entirely — a silently lost district rather than a visible error.

    TRUST ORDER when the two poppler tools disagree (#830):
      * whole-doc `pdftotext` succeeded (rc 0, non-empty) and `pdfinfo` agrees, or `pdfinfo` is
        UNKNOWN (None) → trust the split. A split we already hold is direct evidence; a count that
        could not be read is no evidence, and must never veto it.
      * both succeeded but DISAGREE → fall back to the per-page loop over `pdfinfo`'s count. This
        is the one place the count outranks the split, because a genuine disagreement means one
        tool mis-parsed and per-page `-f/-l` is the independent tiebreaker.
      * whole-doc call failed → per-page loop over `pdfinfo`'s count, or over 1 page if that is
        unknown too (still never [])."""
    n = pdf_page_count(pdf)                       # int, or None = could not be determined
    out, rc = None, None
    try:
        r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                           capture_output=True, text=True, timeout=PDFTOTEXT_TIMEOUT_S)
        out, rc = r.stdout, r.returncode
    except subprocess.TimeoutExpired:
        PDF_TEXTS_FALLBACKS["whole_doc_timeout"] += 1
    except OSError:
        PDF_TEXTS_FALLBACKS["whole_doc_oserror"] += 1
    # #831(2): success is rc 0 AND non-empty stdout, not stdout truthiness alone — poppler can exit
    # non-zero after writing partial output on a malformed-but-parseable file, and a partial read
    # accepted as complete is exactly the silent truncation this function exists to prevent.
    if out and rc == 0:
        parts = out.split("\f")
        # pdftotext writes a trailing form feed after the LAST page, leaving one empty tail part.
        # Drop exactly that one — and do NOT strip the whole output first, or a legitimately blank
        # final page loses its slot and every page number shifts. Page numbers are user-visible:
        # the `pages` send hint and the human `_pages_list` label both index into this.
        if parts and not parts[-1]:
            parts.pop()
        if parts and (n is None or len(parts) == n):
            if n is None:
                PDF_TEXTS_FALLBACKS["count_unknown_trusted_split"] += 1
            return PageTexts(parts, complete=True)
        PDF_TEXTS_FALLBACKS["count_disagrees" if n is not None else "empty_split"] += 1
    elif out is not None:
        PDF_TEXTS_FALLBACKS["whole_doc_nonzero_rc" if rc else "whole_doc_empty"] += 1
    # Per-page fallback, over the count we trust — or 1 page when nothing could be determined.
    n = n or 1
    started = time.monotonic()
    pages = []
    for p in range(1, n + 1):
        if time.monotonic() - started > PDF_FALLBACK_BUDGET_S:
            PDF_TEXTS_FALLBACKS["fallback_budget_exhausted"] += 1
            break
        # #835: ONE element shape leaves this function. pdf_page_text keeps the trailing form feed
        # pdftotext emits per page; the split path above consumed it as the separator. Strip it
        # here so BOTH paths return bare page text and `page_text_from` (the single place that
        # restores it) cannot double it — which it did on this path: "text\f\f".
        pages.append(pdf_page_text(pdf, p).removesuffix("\f"))
    # #839: a fallback that stopped short (budget) has silently dropped the document's tail. Say
    # so on the result rather than let a prefix masquerade as the whole document downstream.
    return PageTexts(pages, complete=(len(pages) >= n))


# One home for the school-identity key (REQ-117; PR #247 review): this module carried its own
# weaker copy (substring .replace(), no word boundaries, missing the #236 district suffixes), so
# Stage 5's topology denominator silently disagreed with Stage 7/8's school-identity key — the exact
# drift class the shared function exists to prevent.
from infrastructure.acquisition.common import school_match as SM  # noqa: E402
from infrastructure.acquisition.common.school_match import norm_school  # noqa: E402,F401


# ----------------------------- NCES school counts (topology denominator) -----------------------------
def nces_school_counts(year: str = NCES_YEAR) -> dict:
    """did(7-digit) -> count of DISTINCT open, regular, graded schools (ccd_sch_029, via
    school_sampling.school_index). This is the true school count — NOT what discovery/capture
    happened to yield — used to confirm single_school and the incomplete_coverage gap. Best
    effort: returns {} if the NCES files aren't present, and topology degrades gracefully."""
    try:
        from infrastructure.acquisition.common import school_sampling as ss

        idx = ss.school_index(year)
    except Exception:
        return {}
    return {did: len({s["school_id"] for b in bands.values() for s in b})
            for did, bands in idx.items()}


# ----------------------------- Stage 1 batch + Stage 2 candidates (funnel ingredients) -----------------------------
def load_batches(queue_dir: Path = QUEUE_DIR) -> dict:
    """did(7) -> per-district Stage-1 targeting entry, enriched with the batch's nces_year. Reads
    every batch_*.json. The 'targeted' end of the funnel + the authoritative NCES denominator
    (nces_school_counts.total), captured at queue time. Best effort: {} if the dir is absent."""
    out = {}
    if not queue_dir.exists():
        return out
    for bf in sorted(queue_dir.glob("batch_*.json")):
        try:
            doc = json.loads(bf.read_text())
        except Exception:
            continue
        year = doc.get("nces_year")
        for d in doc.get("districts", []):
            did = str(d.get("district_id", "")).zfill(7)
            out[did] = {**d, "_nces_year": year, "_batch_id": doc.get("batch_id")}
    return out


# The Stage-2 capture-plan loader moved to common/cache_ingest.py (shared with the per-stage cache
# hooks). Re-exported here for the callers/tests that reference build_signals.load_candidates.
load_candidates = CI.load_candidates


# ----------------------------- near-duplicate clustering -----------------------------
def shingles(text: str, k: int = SHINGLE_K) -> frozenset:
    toks = re.sub(r"\s+", " ", text.lower()).strip().split()
    if len(toks) < k:
        return frozenset(toks)
    return frozenset(" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_district(items: list, splits: set):
    """items: [(rec_key, shingle_set, tier, sort_score), ...] for one district's records.
    splits: rec_keys the human forced to stand alone (never merged). Returns
    {rec_key: (cluster_id_or_None, is_rep, cluster_size)} via connected components over
    Jaccard >= CLUSTER_THRESHOLD. Singletons get cluster_id None (no badge in the UI)."""
    parent = {rk: rk for rk, *_ in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    n = len(items)
    for i in range(n):
        rk_i, sh_i = items[i][0], items[i][1]
        if rk_i in splits:
            continue
        for j in range(i + 1, n):
            rk_j, sh_j = items[j][0], items[j][1]
            if rk_j in splits:
                continue
            if jaccard(sh_i, sh_j) >= CLUSTER_THRESHOLD:
                parent[find(rk_i)] = find(rk_j)

    meta = {rk: (tier, score) for rk, _, tier, score in items}
    comps = {}
    for rk, *_ in items:
        comps.setdefault(find(rk), []).append(rk)

    out = {}
    did = items[0][0].split(":")[0] if items else ""
    for idx, (_, members) in enumerate(sorted(comps.items())):
        if len(members) == 1:
            out[members[0]] = (None, 1, 1)
            continue
        cid = f"{did}:c{idx}"
        rep = min(members, key=lambda rk: (TIER_RANK.get(meta[rk][0], 9), -meta[rk][1], rk))
        for rk in members:
            out[rk] = (cid, 1 if rk == rep else 0, len(members))
    return out


def canonical_invariant_violations(sess) -> list:
    """The rec_keys that break the canonical invariant (#158): a MULTI-MEMBER cluster's
    REPRESENTATIVE (is_cluster_rep=1, cluster_id set) that ALSO carries duplicate_of. Such a record —
    and every sibling in its cluster — is silently dropped from release/dispatch
    (CANONICAL_RECORD_WHERE matches neither). Empty list == healthy.
    NOT a violation: a SINGLETON (cluster_id NULL) carrying duplicate_of — that's the normal shape of
    an unclustered exact content-dup (correctly suppressed; its first-seen partner is canonical), and
    singletons also carry is_cluster_rep=1 (cluster_district emits (None,1,1)).
    Used by the repair below and its regression test."""
    return [r[0] for r in sess.execute(text(
        "SELECT rec_key FROM record WHERE is_cluster_rep = 1 AND cluster_id IS NOT NULL "
        "AND duplicate_of IS NOT NULL"))]


def repair_canonical_invariant(sess) -> int:
    """Backfill-repair existing violations (#158): clear duplicate_of on every MULTI-MEMBER cluster
    representative that still carries it, restoring exactly one canonical member per cluster.
    Scoped to cluster_id IS NOT NULL — singleton duplicate_of rows are legitimate dedup state and are
    never touched. Idempotent — a second run finds nothing. Returns the number of records repaired.
    The forward path (the cluster-write above) already enforces the invariant on ingest; this heals
    rows written before the fix."""
    n = sess.execute(text(
        "UPDATE record SET duplicate_of = NULL "
        "WHERE is_cluster_rep = 1 AND cluster_id IS NOT NULL "
        "AND duplicate_of IS NOT NULL")).rowcount
    return n


# ----------------------------- labeled topology -----------------------------
def derive_labeled_topology(primaries: list, nces_count) -> str:
    """primaries: primary_label strings for a district's labeled CANONICAL records (non-dup,
    cluster representatives). nces_count: distinct NCES regular schools, or None. One value.
    Precedence is deliberate and documented in STAGE5_FILTER_DESIGN.md."""
    labeled = [p for p in primaries if p]
    if not labeled:
        return "unknown"                 # not reviewed yet
    targets = [p for p in labeled if p in TARGET_LABELS]
    if not targets:
        return "none_found"              # reviewed, nothing on-target -> re-discovery signal
    if nces_count == 1:
        return "single_school"           # NCES-confirmed one-school LEA
    has_hub = any(p in HUB_LABELS for p in targets)
    school_level = [p for p in targets if p in SCHOOL_LEVEL_LABELS]
    if has_hub and school_level:
        return "mixed"
    if has_hub:
        return "district_hub"
    # exact, narrow incomplete_coverage criterion (user, 2026-06-25): a single full single-school bell
    # TABLE for a >1-school district = a coverage gap. Deliberately narrow — a single prose/list start-end
    # stays per_school. (v2.1: school_bell_table is the direct rename of the old school_bell_schedule.)
    if len(targets) == 1 and targets[0] == "school_bell_table" and nces_count and nces_count > 1:
        return "incomplete_coverage"
    if school_level:
        return "per_school"
    return "unknown"


def recompute_labeled_topology(s, district_id: str) -> str:
    """Recompute + persist district.labeled_topology from the live labels. Cheap (no NCES read —
    nces_school_count is stored on the district at ingest). Called at ingest and on every save.
    `s` is a governance Session/Connection (SQLAlchemy execute API)."""
    row = s.execute(text("SELECT nces_school_count FROM district WHERE district_id=:did"),
                    {"did": district_id}).fetchone()
    nces_count = row[0] if row else None
    primaries = [r[0] for r in s.execute(text(
        """SELECT l.primary_label FROM record r JOIN label l ON l.rec_key=r.rec_key
           WHERE r.district_id=:did AND r.duplicate_of IS NULL
             AND (r.is_cluster_rep=1 OR r.cluster_id IS NULL)
             AND l.status!='unlabeled' AND l.primary_label IS NOT NULL"""),
        {"did": district_id})]
    topo = derive_labeled_topology(primaries, nces_count)
    s.execute(text("UPDATE district SET labeled_topology=:topo WHERE district_id=:did"),
              {"topo": topo, "did": district_id})
    return topo


def recompute_attention(s, district_id: str, cfg: dict = None) -> dict:
    """Recompute + persist the ATTENTION score for one district's records AND the district rollup, from
    the live signals + label state (attention.py). Called at ingest and on every label save, so the
    console's working store stays current. Canonical records (non-duplicate cluster reps / singletons —
    mirroring recompute_labeled_topology) drive the district rollup + pipeline_state; every record still
    gets its own score (for record-level filtering). `s` is a governance Session/Connection. Returns the
    district {score, reasons}."""
    cfg = cfg or AT.load_config()
    # Unresolved follow-up flags (the top attention tier): per-record + a district-level directive.
    flagged = {r[0] for r in s.execute(text(
        "SELECT target_id FROM followup_flag WHERE district_id=:did AND scope='record' AND resolved_at IS NULL"),
        {"did": district_id})}
    district_flagged = (s.execute(text(
        "SELECT COUNT(*) FROM followup_flag WHERE district_id=:did AND scope='district' AND resolved_at IS NULL"),
        {"did": district_id}).scalar() or 0) > 0
    rows = s.execute(text(
        """SELECT r.rec_key, r.tier, r.signals_json, r.duplicate_of, r.is_cluster_rep, r.cluster_id,
                  COALESCE(l.status, 'unlabeled') AS status
           FROM record r LEFT JOIN label l ON l.rec_key=r.rec_key
           WHERE r.district_id=:did"""), {"did": district_id}).mappings().all()
    canon_atts, n_unlabeled = [], 0
    for r in rows:
        try:
            sig = json.loads(r["signals_json"]) if r["signals_json"] else {}
        except (json.JSONDecodeError, TypeError):
            sig = {}
        att = AT.record_attention(sig, r["tier"], r["status"], cfg, has_flag=r["rec_key"] in flagged)
        s.execute(text("UPDATE record SET attention_score=:sc, attention_reasons_json=:rj WHERE rec_key=:rk"),
                  {"sc": att["score"], "rj": json.dumps(att["reasons"]), "rk": r["rec_key"]})
        if r["duplicate_of"] is None and (r["is_cluster_rep"] == 1 or r["cluster_id"] is None):
            canon_atts.append(att)
            if r["status"] == "unlabeled":
                n_unlabeled += 1
    n_labeled = len(canon_atts) - n_unlabeled
    pipeline_state = "untouched" if n_labeled == 0 else "complete" if n_unlabeled == 0 else "partial"
    dist = AT.district_attention(canon_atts, cfg, has_district_flag=district_flagged)
    s.execute(text(
        """UPDATE district SET attention_score=:sc, attention_reasons_json=:rj, pipeline_state=:ps,
              n_unlabeled=:nu, n_flagged=:nf WHERE district_id=:did"""),
        {"sc": dist["score"], "rj": json.dumps(dist["reasons"]), "ps": pipeline_state,
         "nu": n_unlabeled, "nf": len(flagged) + (1 if district_flagged else 0), "did": district_id})
    return dist


# ----------------------------- signal computation -----------------------------
# ----------------------------- handbook page-harvesting (REQ-092) -----------------------------
HANDBOOK_HARVEST_MIN = 6   # a PDF page with >= this many clock times is a likely schedule page


def is_handbook_doc(text_lc: str, files: dict, n_pages: int, max_chars: int) -> bool:
    """A multi-topic student/parent handbook: the word 'handbook' in the text or a filename AND
    real document length (multi-page PDF, or a lot of text). Pairs with the human buried_in_long_doc
    flag — the schedule is in here somewhere, just not the whole point of the doc."""
    blob = (text_lc or "") + " " + " ".join(str(v).lower() for v in (files or {}).values())
    return "handbook" in blob and (n_pages > 1 or max_chars > 8000)


def page_text_from(page_texts: list, page: int) -> str:
    """One page's text in the EXACT form `pdf_page_text` returns it — including the trailing form
    feed pdftotext emits per page.

    `pdf_page_texts` returns BARE page text on both of its paths (#835 — the split path consumes
    the form feed as its separator; the fallback strips it), so this is the ONE place the per-page
    form feed is restored, and a slice cut from the cached texts is byte-identical to a slice cut
    by re-extracting. Verified across every harvest page in the corpus on the split path
    (`pdf_page_text(pdf, p) == pdf_page_texts(pdf)[p-1] + "\\f"`, 185/185) and by test on the
    fallback path, which used to double it.
    Without this, all 131 existing harvest slices would silently change by one character per page
    on the next re-ingest — a cosmetic diff, but one that breaks the byte-identity guarantee the
    handbook path is held to. Out-of-range page ⇒ "" (the caller decides whether to re-extract)."""
    return (page_texts[page - 1] + "\f") if 0 < page <= len(page_texts) else ""


def page_time_signals(page_texts: list) -> list:
    """Per-page evidence the page-scoping selectors read: `[{"page", "n_times", "instr"}, ...]`,
    page numbers 1-based. ONE producer for that shape so a selector can never be fed a dict built
    a second way.

    `instr` is `instructional_declaration()` — the colon-free `explicit_instructional_time` class
    the clock-time count structurally cannot see ("495 minutes of instruction per day" carries no
    clock time at all). Counting it here is free (the text is already in hand) and keeps a page
    whose only payload is an instructional declaration from reading as empty."""
    return [{"page": i, "n_times": len(time_positions(t or "")),
             "instr": instructional_declaration(t or "")}
            for i, t in enumerate(page_texts, 1)]


def time_bearing_pages(pages: list, *, keep_first: bool = True, keep_neighbors: bool = True,
                       complete: bool = True) -> list:
    """#821 — the ABSOLUTE page floor: the pages that could plausibly carry schedule or
    instructional-time content. Keep page N iff it has a clock time, OR declares instructional
    minutes, OR is the first page, OR neighbours a time-bearing page.

    LOSSLESS on the time signal by construction — every page with a time is kept. That is the
    whole difference from `harvest_schedule_pages`, a peak-RELATIVE standout selector that cuts at
    max(6, peak*0.5) and measurably drops 26.3% of the corpus's clock times (and selects nothing at
    all in 887 of 1,640 multi-page docs). Per-page time counts follow a power law, not a normal
    distribution, so a threshold set off the peak discards the tail; an absolute floor cannot.

    The three non-time terms each answer a measured failure, not a hypothetical:
      * `instr`  — `explicit_instructional_time` evidence is colon-free ("495 minutes of instruction
                   per day") and scores n_times == 0. Memphis 4700148:00f553bcfc p39 is exactly this
                   and is that record's ONLY such page; a bare n_times>0 floor drops it.
      * first    — the masthead carries the district/school name and year the council needs to
                   ATTRIBUTE times to a school.
      * neighbor — a roster table's names column and its times can straddle a page break. Sampled
                   150 records: 86 had a school name appearing only on a zero-time page.

    Returns [] — meaning "no scoping, send the whole thing" — when there is nothing to scope
    (<=1 page), nothing qualifies, EVERY page qualifies (a slice identical to the document is
    pure duplication), or the scan that produced `pages` was INCOMPLETE (#839: `complete=False`
    means unscanned tail pages are absent from `pages`, so "every page with a time is kept" would
    be a claim about a prefix, not the document — decline, send whole). The keep_* switches exist
    so the corpus sweep can measure each term's cost rather than assume it."""
    if not pages or len(pages) <= 1 or not complete:
        return []
    nums = {p["page"] for p in pages}
    bearing = {p["page"] for p in pages if (p.get("n_times") or 0) > 0}
    anchor = bearing | {p["page"] for p in pages if p.get("instr")}
    if not anchor:
        # Nothing to scope AROUND. `keep_first`/`keep_neighbors` are MODIFIERS on a real signal,
        # not signals themselves — without this guard a document with no time content anywhere
        # would be "scoped" to its cover page, which is both useless and lossy-looking.
        return []
    keep = set(anchor)
    if keep_first:
        keep.add(min(nums))
    if keep_neighbors:
        for n in bearing:
            keep |= {n - 1, n + 1}
    keep &= nums
    if keep == nums:
        return []
    return sorted(keep)


def harvest_schedule_pages(pages: list, min_times: int = HANDBOOK_HARVEST_MIN) -> list:
    """Deterministic harvest: in a multi-page doc, the page number(s) whose clock-time count stands
    out are the likely schedule page(s) -> Stage 6/7 sends ONLY these to the council, not the whole
    (expensive, noisy) doc. Reuses the existing per-page n_times signal. Empty if nothing stands out
    (no page clears the floor) or it's a single page. PROVEN on Pittsylvania (p2/p3/p4)."""
    if not pages or len(pages) <= 1:
        return []
    mx = max(p["n_times"] for p in pages)
    if mx < min_times:
        return []
    cut = max(min_times, mx * 0.5)   # the standout page(s): at/above half the peak, floor at min_times
    return [p["page"] for p in pages if p["n_times"] >= cut]


def text_bases(record_dir: Path, texts: list, main_text: str = None) -> dict:
    """The record's text-basis SELECTION — the ONE home (PR #705 review [4]: the rerunnable #684
    measurement script hand-copied this logic, and a hand copy silently drifts from what the live
    scorer actually stores, invalidating a re-run without anyone noticing). Returns
    {usable, full_best, full_all, max_chars, dechromed, all_text, best_text, table_reps}:
      - best_text: the TIME-signal basis (max in-window of {full_best, main}) — REQ-113 §2a-1
      - all_text:  the KEYWORD/roster basis (de-chromed main when usable, else the union)
      - table_reps: the table-source usable reps (lf_time_table's evidence basis)
    Consumed by compute_signals and by any measurement script replaying per-basis signals.

    De-chrome: KEYWORD/roster signals over MAIN when a usable page.main.txt segment exists (its measured
    win: footer building-hours + school-switcher nav can't inject false CATEGORY signal). But TIME signals
    use the MAX-EVIDENCE source: de-chrome must never *zero* a real school-hours time that lives in the
    footer or survives only in an OCR/raster rep. So the time basis is whichever of {main, full_best}
    carries more in-window times — never main exclusively."""
    usable = [t for t in texts if t.get("usable") and t.get("text_file")]
    _read_cache: dict = {}

    def read(t):
        # #353: memoize by text_file — a usable rep is read for full_best/full_all AND (for table
        # sources) once more in the table_reps filter + value; without caching a table rep was read
        # up to 4× from disk. One read per file; the cache is per-record-call (never stale).
        fn = t["text_file"]
        if fn in _read_cache:
            return _read_cache[fn]
        try:
            txt = (record_dir / fn).read_text(errors="replace")
        except Exception:
            txt = ""
        _read_cache[fn] = txt
        return txt

    best = max(usable, key=lambda t: t.get("n_times", 0), default=None)
    full_best = read(best) if best else ""
    full_all = "\n".join(read(t) for t in usable)
    max_chars = max((t.get("n_chars", 0) for t in texts), default=0)
    dechromed = bool(main_text and len(main_text.strip()) >= USABLE_MIN_CHARS)
    all_text = main_text if dechromed else full_all      # keyword/roster basis (de-chrome win preserved)
    candidates = [full_best] + ([main_text] if dechromed else [])
    best_text = max(candidates, key=lambda t: len(in_window_positions(t)), default="")  # time-signal basis
    table_reps = [read(t) for t in usable if t.get("source", "") in
                  ("pdfplumber_lines", "camelot_stream", "camelot_hybrid") and "---" in read(t)]
    return {"usable": usable, "full_best": full_best, "full_all": full_all, "max_chars": max_chars,
            "dechromed": dechromed, "all_text": all_text, "best_text": best_text,
            "table_reps": table_reps}


def compute_signals(record_dir: Path, texts: list, roster_norm: list, files: dict, main_text: str = None):
    """All deterministic, no AI. `texts` = processed.json texts[]; `files` = captures.json files{}.
    `main_text` = the Stage-3 DE-CHROMED page (page.main.txt) when present (REQ-091): the time /
    keyword / roster signals are then computed over MAIN instead of the full page, so footer
    building-hours and school-switcher nav can't inject false signal. Graceful: a too-thin main
    falls back to the full text, so segmentation can never make things worse.
    Text-basis selection (best/all/table) lives in `text_bases` — shared with the measurement scripts."""
    tb = text_bases(record_dir, texts, main_text)
    full_best, full_all, max_chars = tb["full_best"], tb["full_all"], tb["max_chars"]
    dechromed, all_text, best_text, table_reps = (
        tb["dechromed"], tb["all_text"], tb["best_text"], tb["table_reps"])
    all_lc = all_text.lower()

    # Time signals (on the max-evidence single representation).
    tps = time_positions(best_text)
    n_times = len(tps)
    in_window = in_window_positions(best_text)
    after5 = [m for _, m in tps if m >= AFTER_5PM]
    prox = proximity_pairs(tps)

    # Segment-scoped hours blocks (REQ-113): school hours very often live ONLY in the footer/header.
    def seg(name):
        p = record_dir / name
        return p.read_text(errors="replace") if p.exists() else ""
    footer = hours_block(seg("page.footer.txt"))
    header = hours_block(seg("page.header.txt"))
    headings = heading_hours_hits(all_text if dechromed else full_all)

    pos = keyword_hits(all_lc, POSITIVE_KW)
    neg = {"board": keyword_hits(all_lc, NEG_BOARD), "sports": keyword_hits(all_lc, NEG_SPORTS),
           "calendar": keyword_hits(all_lc, NEG_CALENDAR), "transport": keyword_hits(all_lc, NEG_TRANSPORT)}
    neg_total = sum(len(v) for v in neg.values())
    instructional = instructional_declaration(all_text)
    # table time-DENSITY, not just a boolean: the in-window time count in the richest table rep + its period rows.
    table_time_density = max((len(in_window_positions(t)) for t in table_reps), default=0)
    table_period_rows = max((len(PERIOD_RE.findall(t)) for t in table_reps), default=0)
    has_table = bool(table_reps)
    period_hits = len(PERIOD_RE.findall(all_text))
    # #826: match the (already-normalized) roster keys against a document put into the SAME
    # character space. `all_lc` stays raw-lowercase for keyword scanning — those patterns expect
    # real punctuation — so the roster basis is its own normalization, computed once per record.
    roster_basis = SM.norm_document(all_text)
    roster_hits = sum(1 for rn in roster_norm if rn and rn in roster_basis)
    nonstandard_day = any(k in all_lc for k in NONSTANDARD_DAY_KW)
    # positional non-regular-day evidence (#537): computed over the TIME basis (best_text) AND every
    # table rep — each against its OWN in-window offsets (offsets never cross texts). The table pass
    # closes a PR #538 review find: the lf_time_table evidence this signal undermines comes from
    # table_reps, which can be a DIFFERENT physical representation than best_text — a camelot-extracted
    # "Early Dismissal Bell Schedule" table whose surrounding prose (the best_text) never says so.
    # Every positional signal below reads the same (text, its own in-window offsets) pairs, computed ONCE
    # — the offset scan is a regex pass over the whole rep, and a big handbook has several table reps.
    time_bases = [(best_text, [off for off, _ in in_window])]
    time_bases += [(t, [off for off, _ in in_window_positions(t)]) for t in table_reps]
    ns_near = ns_heading = 0
    for t, offs in time_bases:
        tn, th = nonstandard_positional(t, offs)
        ns_near, ns_heading = max(ns_near, tn), max(ns_heading, th)
    # The S3 guard scans the SAME bases the positional evidence came from, and only when there is
    # positional evidence to guard (it is consulted nowhere else — a per-record regex saved on the
    # majority of records, PR #538 review).
    regular_day_language = bool((ns_near or ns_heading) and any(
        NONSTANDARD_REGULAR_RE.search(t) for t in [best_text, *table_reps]))
    # Staff-day ownership (#684) — the SAME bases the wrong-day positional evidence scans, for the same
    # reason: the staff report-time table can live in a camelot rep whose surrounding prose (the
    # best_text) never frames it. Reported as the counts of the basis reading MOST strongly staff-owned
    # (max duty − student margin), so the detector's `staff_duty_times > student_ref_times` test
    # reproduces exactly "ANY basis is staff-owned" from two stored integers — no third field to drift.
    # ANY, not ALL: a mixed page (a real student table AND a staff table) is precisely the record a human
    # should adjudicate, and the sensitivity scan showed ALL is the fragile combinator (it drops
    # Bentonville at a 500-char student window; ANY holds from 100 to 500).
    # NB the stored pair is the VERDICT's basis, not a page census: a record whose only duty clause loses
    # the comparison (Alliance `3805460:84db5b8100` — 1 duty clause vs 23 student-referent times) stores
    # 0/0, because no basis reached a positive margin. So `staff_duty_times == 0` means "no basis reads
    # staff-owned", NOT "no duty clause on the page" — the two are different questions and only the first
    # one scores.
    staff_duty_times = student_ref_times = 0
    for t, offs in time_bases:
        d, s = staff_duty_positional(t, offs)
        if d - s > staff_duty_times - student_ref_times:
            staff_duty_times, student_ref_times = d, s

    # visual exists but text is thin -> possible missed content
    has_visual = bool(files.get("png") or (files.get("bin") and not files.get("txt"))) or "pdf" in files
    visual_text_gap = has_visual and max_chars < USABLE_MIN_CHARS

    # Per-page evidence for any PDF present (the page-scoping selectors). Scans the WHOLE document:
    # the former HANDBOOK_MAX_PAGES=60 cap made pages 61+ structurally invisible to every consumer
    # (Memphis 4700148:8d0058ac10 is 154 pages and lost 111 of its 942 times that way). The cap had
    # already been raised once, 15 -> 60, for this same class of miss; it is now gone rather than
    # raised again, and one whole-document call is cheaper than the per-page loop it replaces.
    pages, page_texts = [], []
    pdf_name = files.get("pdf") or (files.get("bin") if str(files.get("bin", "")).lower().endswith(".pdf") else None)
    if pdf_name:
        pdf = record_dir / pdf_name
        if pdf.exists():
            page_texts = pdf_page_texts(pdf)
            pages = page_time_signals(page_texts)

    sig = {
        "n_times": n_times, "n_times_in_window": len(in_window), "times_after_5pm": len(after5),
        "proximity_pairs": prox, "positive_kw": pos, "negative_kw": neg, "neg_total": neg_total,
        "instructional_time": instructional, "has_table": has_table, "period_hits": period_hits,
        "roster_school_names_hit": roster_hits, "visual_text_gap": visual_text_gap,
        "max_text_chars": max_chars, "pages": pages,
        "is_handbook": is_handbook_doc(all_lc, files, len(pages), max_chars),
        "harvest_pages": harvest_schedule_pages(pages),
        # #821: computed UNCONDITIONALLY, like harvest_pages — so a corpus sweep can replay the
        # floor from the DB alone, without re-extracting every PDF.
        "timebearing_pages": time_bearing_pages(pages, complete=getattr(page_texts, "complete", True)),
        "dechromed": dechromed,   # REQ-091: KEYWORD signals computed over MAIN (chrome removed)?
        # ---- V2 (REQ-113) ----
        "footer_hours": footer, "header_hours": header,
        "heading_hours_hits": headings["count"], "heading_hours_labels": headings["labels"],
        "table_time_density": table_time_density, "table_period_rows": table_period_rows,
        "nonstandard_day": nonstandard_day,
        "nonstandard_near_times": ns_near, "nonstandard_heading": ns_heading,
        "regular_day_language": regular_day_language,
        "staff_duty_times": staff_duty_times, "student_ref_times": student_ref_times,   # #684
    }
    # Clustering dedups by WHOLE-page content, so it uses the full best text, not the de-chromed main.
    # `page_texts` rides along so the ingest loop can materialize a page slice from the SAME
    # extraction the per-page counts were computed over — re-extracting there would be a second
    # chance to drift from the numbers the signal stored. [] for a non-PDF record.
    return sig, full_best, page_texts


# The V1 tier cascade (`tier_and_category` + DEFAULT_TIER_PARAMS) was DELETED here (issue #56):
# ingest scores through the V2 detectors+combiner (combiner.score_record, REQ-113) and the frontier
# grid-searches detectors.DEFAULT_DETECTOR_PARAMS — nothing live read the V1 path anymore
# (grep/grimp-verified: its only remaining consumers were frontier.py and its tests, both re-pointed).


# ----------------------------- DB (isolated governance Postgres — REQ-103) -----------------------------
# PRECIOUS human data (label = ground-truth labels; cluster_split = records the reviewer pulled out
# of an auto-cluster) is created via gdb.init_precious_schema() from the SQLAlchemy models and is
# NEVER dropped on re-ingest.
#
# Regenerable cache tables: dropped + rebuilt every ingest so schema/signal changes always apply.
# Postgres DDL run on the ISOLATED governance DB — the drop can't reach districts/bell_schedules/
# lct_calculations in the production LCT database. (sqlite INTEGER bool columns stay `integer` here;
# the code reads/writes 0/1 and the UI expects 0/1, so behavior is identical. sqlite REAL → double
# precision.) Each statement is run discretely (no executescript on Postgres).
# The DERIVED signal tables, split into DROP + CREATE so two ingest modes can share one schema:
#   - full ingest()        -> DROP then CREATE (a clean global rebuild — schema changes always apply)
#   - incremental ingest_batch() -> CREATE IF NOT EXISTS, then a per-district DELETE+re-INSERT (only the
#     batch's districts are touched; prior batches are left intact — the cost stays proportional to the
#     batch, not the whole corpus). The CREATE statements use IF NOT EXISTS so they're valid in BOTH
#     modes (after a DROP the table is absent, so it's still created).
_SIGNAL_DROP_DDL = [
    "DROP TABLE IF EXISTS district CASCADE",
    "DROP TABLE IF EXISTS record CASCADE",
    "DROP TABLE IF EXISTS representation CASCADE",
    "DROP TABLE IF EXISTS district_target CASCADE",
]
_SIGNAL_CREATE_DDL = [
    # `attention_*` (REQ-111 follow-on, the district-driven console): the inverted-confidence "needs my
    # judgment" score + its reason codes, computed by recompute_attention() — see attention.py. On
    # `district`: the rollup + the label-coverage `pipeline_state` + counts the left pane sorts/groups on.
    """CREATE TABLE IF NOT EXISTS district (
        district_id text PRIMARY KEY, name text, state text, district_dir text,
        batch_id text, guessed_topology text, labeled_topology text, nces_school_count integer,
        n_records integer, attention_score double precision, attention_reasons_json text,
        pipeline_state text, n_unlabeled integer, n_flagged integer)""",
    """CREATE TABLE IF NOT EXISTS record (
        rec_key text PRIMARY KEY, district_id text, district_dir text, url text, hash text,
        kind text, final_url text, content_hash text, duplicate_of text,
        tier text, sort_score double precision, category_hypothesis text, signals_json text,
        cluster_id text, is_cluster_rep integer, cluster_size integer,
        intended_schools_json text, candidate_tools_json text, is_emergent integer,
        attention_score double precision, attention_reasons_json text)""",
    """CREATE TABLE IF NOT EXISTS representation (
        rec_key text, source text, filename text, file_kind text,
        n_chars integer, n_times integer, usable integer)""",
    # Stage 1 targeting provenance (the funnel's "targeted" end + the NCES denominator). One row
    # per district when a batch_*.json entry exists; the topology denominator (nces_total) prefers
    # this over the live CSV. Regenerable.
    """CREATE TABLE IF NOT EXISTS district_target (
        district_id text PRIMARY KEY, batch_id text, nces_year text, nces_total integer,
        nces_by_level_json text, enrollment_k12 integer, lea_claimed_bands_json text,
        schools_by_band_json text)""",
    # PR #248 review: the #211 reject-population query (exploration_live) filters record on tier='D'
    # from save_label's transaction — index it, or that's a full-scan join on the hottest write path.
    "CREATE INDEX IF NOT EXISTS ix_record_tier ON record (tier)",
]
# Additive column migrations for the never-dropped incremental path: a table created before a column
# existed won't pick it up from CREATE IF NOT EXISTS, so ensure_signal_schema applies these too. (The
# full ingest() drops+recreates, so it gets the columns from the CREATE above; this is for ingest_batch.)
_SIGNAL_ALTERS = [
    "ALTER TABLE district ADD COLUMN IF NOT EXISTS attention_score double precision",
    "ALTER TABLE district ADD COLUMN IF NOT EXISTS attention_reasons_json text",
    "ALTER TABLE district ADD COLUMN IF NOT EXISTS pipeline_state text",
    "ALTER TABLE district ADD COLUMN IF NOT EXISTS n_unlabeled integer",
    "ALTER TABLE district ADD COLUMN IF NOT EXISTS n_flagged integer",
    "ALTER TABLE record ADD COLUMN IF NOT EXISTS attention_score double precision",
    "ALTER TABLE record ADD COLUMN IF NOT EXISTS attention_reasons_json text",
]
# Backwards-compatible alias: the full drop+rebuild list (what ingest() runs).
REBUILD_DDL = _SIGNAL_DROP_DDL + _SIGNAL_CREATE_DDL


def ensure_signal_schema(sess) -> None:
    """Create the derived signal tables if absent + apply additive column migrations (the incremental
    path — never drops). Caller owns the session."""
    for ddl in _SIGNAL_CREATE_DDL:
        sess.execute(text(ddl))
    for ddl in _SIGNAL_ALTERS:
        sess.execute(text(ddl))


def migrate_label_v21(primary, flags, facets):
    """PURE: map ONE v2.0 label (primary_label + flags[] + facets{}) to the v2.1 schema. Returns
    (new_primary, new_facets). Deterministic + reversible-in-spirit (git holds the pre-migration
    labels.json). Ambiguous target splits land on a sensible default the HUMAN re-confirms:
    district_hub_schedule → by_school (by_band is rarer); a target's prose-vs-list shape is left as the
    v2.0 value carried forward. Non-targets → primary target_absent + the confounder facet. v2.0 FLAGS
    fold in: building_hours_visible → office_building_hours facet; buried_in_long_doc / target_image_only
    stay as facets. `duplicate` has NO facet successor — retired outright (2026-07-01): programmatic
    dedup (record.duplicate_of + near-dup clustering) owns duplicates; flags_json is now an inert
    archive column (no live reads/writes)."""
    flags = flags or []
    facets = dict(facets or {})
    if primary in LEGACY_NONTARGET_TO_FACET:            # a v2.0 non-target -> absent + confounder facet
        facets[LEGACY_NONTARGET_TO_FACET[primary]] = "yes"
        new_primary = "target_absent"
    else:
        new_primary = LEGACY_LABEL_MAP.get(primary, primary)   # rename, else unchanged (prose/minutes/unusable/already-v2.1)
    if "building_hours_visible" in flags:
        facets["office_building_hours"] = "yes"
    if "buried_in_long_doc" in flags:
        facets["buried_handbook"] = "yes"
    if "target_image_only" in flags:
        facets["needs_vision"] = "yes"
    return new_primary, facets


def migrate_labels_v21(sess, *, dry_run=True, force=False):
    """Apply migrate_label_v21 to every non-unlabeled row. dry_run just tallies. Real run UPDATEs
    primary_label + facets_json in place (labels are precious → the caller exports labels.json after,
    and git holds the prior backup as the restore point).

    RE-RUN GUARD (issue #59): this is a ONE-TIME migration. A second real run would re-fold the
    legacy v2.0 flags_json into facets_json, silently overwriting any facet edits the human made
    since (the exact data v2.1 re-tagging is producing). A real run therefore REFUSES when it
    detects it already ran — any label already carrying a v2.1-vocabulary primary AND non-empty
    facets — unless force=True is passed explicitly (with a loud warning)."""
    rows = sess.execute(text(
        "SELECT rec_key, primary_label, flags_json, facets_json FROM label WHERE status!='unlabeled'")).fetchall()
    from collections import Counter
    valid = TARGET_LABELS | NONTARGET_PRIMARIES     # every migrated primary must land in the v2.1 vocabulary
    if not dry_run:
        already = [rk for rk, primary, _fj, facj in rows
                   if primary in valid and json.loads(facj or "{}")]
        if already and not force:
            raise RuntimeError(
                f"migrate_labels_v21 refused: it appears to have already run — {len(already)} labels "
                f"are already in the v2.1 vocabulary with non-empty facets (e.g. {already[:3]}). "
                f"Re-running would re-fold legacy flags over newer HUMAN facet edits. "
                f"Pass force=True only if you are certain (git holds the restore point).")
        if already and force:
            print(f"[WARNING] migrate_labels_v21 force=True: re-folding legacy flags over "
                  f"{len(already)} already-migrated labels — human facet edits may be overwritten.")
    moves = Counter()
    for rk, primary, fj, facj in rows:
        flags = json.loads(fj or "[]")
        facets = json.loads(facj or "{}")
        new_primary, new_facets = migrate_label_v21(primary, flags, facets)
        assert new_primary in valid, f"migration produced an out-of-vocabulary primary: {new_primary!r}"
        moves[f"{primary} -> {new_primary}"] += 1
        if not dry_run:
            sess.execute(text("UPDATE label SET primary_label=:p, facets_json=:f WHERE rec_key=:rk"),
                         {"p": new_primary, "f": json.dumps(new_facets), "rk": rk})
    return moves


def delete_district_signal_rows(sess, district_id: str) -> None:
    """Remove one district's rows from every derived signal table so a re-ingest is idempotent (the
    incremental DELETE+INSERT; a no-op in full ingest() where the tables were just recreated empty).
    representation has no district_id, so it's cleared via its records first. PRECIOUS label/cluster_split
    are NOT touched — labels survive a re-ingest (rec_key is stable)."""
    sess.execute(text("DELETE FROM representation WHERE rec_key IN "
                      "(SELECT rec_key FROM record WHERE district_id=:d)"), {"d": district_id})
    for tbl in ("record", "district", "district_target"):
        sess.execute(text(f"DELETE FROM {tbl} WHERE district_id=:d"), {"d": district_id})
# The cross-stage cache (discovery_school/candidate/capture/processed_doc, REQ-103c) is NO LONGER part
# of this drop+rebuild list: it graduated to a LIVE, incrementally-upserted working store maintained by
# every stage's finish hook (common/cache_ingest.py), so the console reads fresh rows for an in-flight
# batch. It is created IF NOT EXISTS + UPSERTed (never dropped under in-flight data), and a full ingest()
# re-upserts every complete district below. The DERIVED signal tables above stay drop+rebuild (an
# all-or-nothing recomputation).

BIN_KINDS = {"png": "image", "pdf": "pdf", "bin": "binary"}


def reset_labels_bulk(s, rec_keys: list, ts: str) -> int:
    """#228: return labels to the truthful UNLABELED state — primary/facets/note nulled,
    status='unlabeled' — in ONE bulk statement. THE single source of truth for what 'reset' means
    (PR #242 review: the console endpoint and the remediation tooling each hand-rolled their own
    reset SQL, a silent-drift risk). A plain UPDATE, not an upsert: ingest guarantees every record
    a label row (the bare INSERT..ON CONFLICT DO NOTHING seed), so there is never a row to create,
    and rows already unlabeled are deliberately untouched (their updated_at stays honest).
    Leaves the legacy flags_json archive column alone, same as UPSERT_LABEL. Returns the number of
    rows that actually carried a label (the meaningful resets)."""
    if not rec_keys:
        return 0
    return s.execute(text(
        """UPDATE label SET primary_label=NULL, facets_json=NULL, note=NULL, status='unlabeled',
                            updated_at=:ts
           WHERE rec_key = ANY(:ks) AND status != 'unlabeled'"""),
        {"ts": ts, "ks": list(rec_keys)}).rowcount


def export_labels(s, out: Path = LABELS_JSON) -> int:
    """Dump all non-unlabeled rows to a tracked JSON (atomic write). The label backup.
    Under pytest the tracked file is quarantine-redirected (issue #178)."""
    out = paths.guard_tracked_backup(out)
    rows = s.execute(text(
        f"SELECT {','.join(LABEL_COLS)} FROM label WHERE status!='unlabeled' ORDER BY rec_key")).fetchall()
    data = [dict(zip(LABEL_COLS, r)) for r in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    paths.atomic_write_json(out, data)   # atomic
    return len(data)


def export_splits(s, out: Path = CLUSTER_SPLITS_JSON) -> int:
    """Dump the precious cluster-split rec_keys to a tracked JSON (atomic). The split backup.
    Under pytest the tracked file is quarantine-redirected (issue #178)."""
    out = paths.guard_tracked_backup(out)
    rows = [r[0] for r in s.execute(text("SELECT rec_key FROM cluster_split ORDER BY rec_key"))]
    out.parent.mkdir(parents=True, exist_ok=True)
    paths.atomic_write_json(out, rows)
    return len(rows)


def import_splits(s, src: Path = CLUSTER_SPLITS_JSON) -> int:
    """Restore cluster splits from JSON into the table (recovery path after a DB wipe; a no-op
    on normal re-ingest since cluster_split is never dropped). Must run BEFORE clustering so the
    overrides are honored when components are recomputed."""
    if not src.exists():
        return 0
    n = 0
    for rk in json.loads(src.read_text()):
        s.execute(text("INSERT INTO cluster_split (rec_key, created_at) VALUES (:rk, NULL) "
                       "ON CONFLICT (rec_key) DO NOTHING"), {"rk": rk})
        n += 1
    return n


def import_labels(s, src: Path = LABELS_JSON) -> int:
    """Restore labels from the JSON into the DB -- but ONLY for records the DB currently has
    as unlabeled, so a stale export can never clobber a live DB label. This restores labels
    after a DB wipe/rebuild; on a normal re-ingest (label table preserved) it's a no-op."""
    if not src.exists():
        return 0
    n = 0
    for d in json.loads(src.read_text()):
        cur = s.execute(text("SELECT status FROM label WHERE rec_key=:rk"),
                        {"rk": d["rec_key"]}).fetchone()
        if not cur or cur[0] != "unlabeled":
            continue
        s.execute(text("UPDATE label SET primary_label=:pl, facets_json=:fac, note=:nt, "
                       "status=:st, updated_at=:ua WHERE rec_key=:rk"),
                  {"pl": d.get("primary_label"), "fac": d.get("facets_json"),
                   "nt": d.get("note"), "st": d.get("status", "labeled"), "ua": d.get("updated_at"),
                   "rk": d["rec_key"]})
        n += 1
    return n


REC_COLS = ("rec_key", "district_id", "district_dir", "url", "hash", "kind", "final_url",
            "content_hash", "duplicate_of", "tier", "sort_score", "category_hypothesis",
            "signals_json", "intended_schools_json", "candidate_tools_json", "is_emergent")
INSERT_RECORD = text(
    "INSERT INTO record (" + ", ".join(REC_COLS) + ") "
    "VALUES (" + ", ".join(f":{c}" for c in REC_COLS) + ")")
INSERT_REP = text(
    "INSERT INTO representation (rec_key, source, filename, file_kind, n_chars, n_times, usable) "
    "VALUES (:rec_key, :source, :filename, :file_kind, :n_chars, :n_times, :usable)")


def _rep(rec_key, source, filename, file_kind, n_chars, n_times, usable):
    return {"rec_key": rec_key, "source": source, "filename": filename, "file_kind": file_kind,
            "n_chars": n_chars, "n_times": n_times, "usable": usable}


HARVEST_SLICE_SOURCE = "harvest_slice"
HARVEST_SLICE_FILE = "harvest_slice.txt"
# #821: the ABSOLUTE page floor's slice — a different question from the harvest slice (see
# time_bearing_pages), so a distinct source/filename rather than a widened harvest_slice. Keeping
# them separate is what makes "handbook records are byte-identical" structural: materialization is
# mutually exclusive, so a handbook record never carries one of these at all.
TIMEBEARING_SLICE_SOURCE = "timebearing_slice"
TIMEBEARING_SLICE_FILE = "timebearing_slice.txt"
# ONE table of the derived page-slice kinds. Every consumer reads THIS rather than testing a
# filename it spells itself — a second slice kind added without collapsing those tests is exactly
# the implemented-twice-drifts class (#798/#810/#799/#816).
SLICE_FILE_BY_SOURCE = {HARVEST_SLICE_SOURCE: HARVEST_SLICE_FILE,
                        TIMEBEARING_SLICE_SOURCE: TIMEBEARING_SLICE_FILE}
SLICE_SOURCES = frozenset(SLICE_FILE_BY_SOURCE)
SLICE_SOURCE_BY_FILE = {f: s for s, f in SLICE_FILE_BY_SOURCE.items()}   # #836: the cheap inverse
# DERIVED artifact home (issue #58): slices are ingest OUTPUT, so they live under data/acquisition/
# (regenerable), never under data/raw/ (write-once Stage-3 captures — Critical Rule 5). Pre-#58
# ingests wrote harvest_slice.txt next to the raw capture; resolve_slice() keeps those
# readable (read fallback to the old location; writes go ONLY to the new one).
HARVEST_SLICES_DIR = paths.HARVEST_SLICES_DIR


def slice_path(district_id: str, rec_key: str, source: str = HARVEST_SLICE_SOURCE) -> Path:
    """The canonical WRITE location for one record's derived page slice:
    data/acquisition/harvest_slices/<district_id>/<rec_key with ':'→'_'>[.<kind>].txt

    The harvest slice keeps its historical unsuffixed name so no existing artifact moves; any other
    slice kind gets a suffixed sibling, so the two can coexist for one record."""
    stem = rec_key.replace(":", "_")
    if source != HARVEST_SLICE_SOURCE:
        stem = f"{stem}.{source}"
    return HARVEST_SLICES_DIR / str(district_id) / f"{stem}.txt"


def harvest_slice_path(district_id: str, rec_key: str) -> Path:
    """Back-compat wrapper — the harvest slice's canonical write location."""
    return slice_path(district_id, rec_key, HARVEST_SLICE_SOURCE)


def resolve_slice(district_id: str, district_dir: str, rec_key: str, filename: str) -> Path | None:
    """Where a record's derived page slice actually IS, keyed by the FILENAME a consumer already
    holds: the new derived-artifact location first, else (harvest only) the legacy pre-#58 location
    inside the raw capture dir. Returns None when `filename` is not a slice at all, or when no slice
    exists — so a caller needs no membership test of its own, which is the point: the four sites
    that used to compare against HARVEST_SLICE_FILE by hand now all ask this one function."""
    source = SLICE_SOURCE_BY_FILE.get(filename)      # #836: O(1), and the ONE membership test
    if source is None:
        return None
    new = slice_path(district_id, rec_key, source)
    if new.exists():
        return new
    if source != HARVEST_SLICE_SOURCE:
        return None                      # only the harvest slice ever lived in the legacy location
    rec_hash = rec_key.split(":", 1)[-1]
    legacy = RAW_DIR / district_dir / "captures" / rec_hash / HARVEST_SLICE_FILE
    return legacy if legacy.exists() else None


def resolve_harvest_slice(district_id: str, district_dir: str, rec_key: str) -> Path | None:
    """Back-compat wrapper — resolve specifically the harvest slice."""
    return resolve_slice(district_id, district_dir, rec_key, HARVEST_SLICE_FILE)


# #517: the schedule-intent vocabulary for the link-only shape — a page whose keywords CLAIM a bell
# schedule while carrying (near-)zero in-window time content is a REFERENCE to a schedule that lives
# one hop away (a "Bell Schedules" link-hub page, a documents/bell-schedule viewer stub). Measured on
# the census labels 2026-07-18: 78/78 such records are target_absent (all tier D) — zero collateral
# against real targets by construction (a real target HAS times). A RECALL affordance, not a confounder.
SCHED_INTENT_KW = ("schedule", "bell", "school hours", "start time")


def schedule_link_only(sig: dict) -> bool:
    kw = [str(k).lower() for k in (sig.get("positive_kw") or [])]
    intent = any(t in k for k in kw for t in SCHED_INTENT_KW)
    return bool(intent and (sig.get("n_times_in_window") or 0) <= 1
                and not (sig.get("table_time_density") or 0))


def labeled_pages_of(facets_json_str) -> list:
    """#109: the HUMAN-labeled page range for a long doc — v2.1 Axis-3's `_pages_list`, the parsed
    print-dialog-style range the console writes into label.facets_json alongside `buried_handbook`.
    Ground truth for WHERE the schedule lives, so it outranks the AUTO harvest_pages wherever both
    exist (the auto detector guesses from keyword/time density; the human looked). Empty/absent/
    malformed ⇒ [] — the auto path wins, never an error."""
    try:
        facets = (json.loads(facets_json_str) if isinstance(facets_json_str, str) else facets_json_str) \
            if facets_json_str else {}
        pages = (facets or {}).get("_pages_list") or []
        return [int(p) for p in pages if int(p) > 0]
    except (ValueError, TypeError, json.JSONDecodeError):
        return []


def select_slice(signals: dict, facets) -> "tuple[str, list] | None":
    """THE ONE page-slice decision (#834): which slice kind — if any — this record gets, and over
    which pages. `(source, pages)`, or None for "no scoping; send the document whole".

    Ingest materializes exactly what this returns; `best_send` sends a slice rep ONLY if its source
    matches what this returns. Both sides call this function, so they structurally cannot disagree
    — which they did when each carried its own hand-written predicate: ingest cut a floor slice for
    35 live handbooks whose peak-relative harvest found nothing, and best_send's separate
    `handbookish` guard then hid every one of them (a 1,017-page handbook sent whole while a
    lossless 19-page slice sat unreachable); and 8 human-labelled records got a harvest slice
    best_send would not send AND were denied the floor because the harvest branch had already
    fired. The implemented-twice-drifts class (#798/#810), a third time — in the very PR that
    named it.

    Precedence, deliberately: a HUMAN page range beats everything (the human looked — #109); a
    handbook whose peak-relative harvest found pages takes the harvest slice; otherwise the
    absolute floor. A handbook whose harvest found NOTHING is not "unscoped" — it is exactly the
    document the floor exists for."""
    facets = facets or {}
    if isinstance(facets, str):
        try:
            facets = json.loads(facets) or {}
        except (ValueError, TypeError):
            facets = {}
    human = labeled_pages_of(facets)
    if human:
        return HARVEST_SLICE_SOURCE, human
    harvest = signals.get("harvest_pages") or []
    if signals.get("is_handbook") and harvest:
        return HARVEST_SLICE_SOURCE, harvest
    floor = signals.get("timebearing_pages") or []
    if floor:
        return TIMEBEARING_SLICE_SOURCE, floor
    return None


def build_slice(page_nums: list, page_text_fn, source: str = HARVEST_SLICE_SOURCE):
    """Materialize the selected PAGES of a long doc as a small standalone text rep, so Stage 6
    dispatches just those pages — not the whole PDF (cost containment; the paid council reads the
    slice, and the measured cost model prices the slice's tokens). `page_text_fn(page)->str`
    extracts one page's text. Returns `(slice_text, rep_kwargs)` ready for INSERT_REP, or None when
    nothing usable extracts. ONE builder for every slice kind — the kind only changes WHICH pages
    were selected and what the rep is called."""
    slice_text = "\n\n".join((page_text_fn(p) or "") for p in (page_nums or []))
    if not slice_text.strip():
        return None
    return slice_text, {"source": source, "filename": SLICE_FILE_BY_SOURCE[source],
                        "file_kind": "text", "n_chars": len(slice_text),
                        "n_times": len(time_positions(slice_text)), "usable": 1}


def build_harvest_slice(harvest_pages: list, page_text_fn):
    """Q2.1 (Ian 2026-06-30): the HARVEST-pages slice — a handbook's ~1-4 high-signal pages.
    Behaviour-preserving wrapper over `build_slice`."""
    return build_slice(harvest_pages, page_text_fn, HARVEST_SLICE_SOURCE)


# ---- cross-stage cache (REQ-103c): the queryable/auditable mirror of each stage's raw artifact,
# alongside the Stage-5 `record` signal view. All REGENERABLE (dropped + rebuilt each ingest). ----
# The cross-stage cache UPSERTs live in common/cache_ingest.py now (shared with the per-stage hooks);
# build_signals delegates to them via ingest_cross_stage_cache() below.


def ingest_cross_stage_cache(sess, disc, caps, processed, cand_map):
    """REQ-103c: project one district's raw stage artifacts (discovery/candidates/captures/processed)
    into the queryable cross-stage cache so the governance console can read the funnel directly. The
    schema + UPSERTs are owned by common/cache_ingest.py (the same code the per-stage finish hooks use
    to keep the cache live); a full ingest() re-upserts every complete district here."""
    did = disc["district_id"]
    CI.upsert_discovery_rows(sess, disc, cand_map)
    CI.upsert_capture_rows(sess, did, caps)
    CI.upsert_processed_rows(sess, did, processed)


def ingest_district(sess, ddir: Path, *, splits: set, batches: dict, nces: dict) -> str | None:
    """Ingest ONE district dir into the derived signal tables + the cross-stage cache. Self-contained
    (dedup/clustering/topology are all per-district), so it's the shared unit of BOTH the full ingest()
    and the incremental ingest_batch(). Starts with a per-district DELETE so a re-ingest is idempotent
    (a no-op in full ingest() where the tables were just recreated empty; the load-bearing reset in the
    incremental path). Returns the district_id, or None if the dir isn't Stage-4-complete (no
    captures/processed/discovery)."""
    cj, pj, dj = ddir / "captures.json", ddir / "processed.json", ddir / "discovery.json"
    if not (cj.exists() and pj.exists() and dj.exists()):
        return None
    disc = json.loads(dj.read_text())
    did = disc["district_id"]
    # Dedup, drop short stems ("Marion High"/"Marion Middle" both -> "marion"), and drop any entry
    # colliding with the DISTRICT's own normalized name (#826) — one shared construction in
    # `common/school_match.py` so a measurement script and the ingest cannot disagree about what a
    # roster key is.
    roster_norm = SM.roster_match_keys([sc.get("school", "") for sc in disc.get("schools", [])],
                                       disc.get("name"))
    roster_size = len(roster_norm)
    caps = {r["hash"]: r for r in json.loads(cj.read_text())}
    processed = {r["hash"]: r for r in json.loads(pj.read_text())}
    cand_map = load_candidates(ddir)   # url -> {schools, tools}; misses = emergent
    delete_district_signal_rows(sess, did)   # idempotent re-ingest (incremental); no-op in full ingest
    # Stale-slice cleanup (issue #58): drop the district's old derived slices before regenerating,
    # so a record whose harvest_pages shrank/vanished can't leave an orphaned slice behind.
    shutil.rmtree(HARVEST_SLICES_DIR / did, ignore_errors=True)
    ingest_cross_stage_cache(sess, disc, caps, processed, cand_map)   # REQ-103c (upsert; already idempotent)

    seen_content = {}   # content_hash -> canonical rec_key
    district_records = []
    cluster_items = []  # (rec_key, shingle_set, tier, sort_score) for near-dup clustering
    # #109: the district's human facets in ONE query (the #543-#547 review flagged the original
    # per-record SELECT as an N+1 inside this loop). Label rows are precious and survive re-ingest.
    district_facets = dict(sess.execute(
        text("SELECT rec_key, facets_json FROM label WHERE rec_key LIKE :p AND facets_json IS NOT NULL"),
        {"p": f"{did}:%"}).fetchall())
    for h, prec in processed.items():
        cap = caps.get(h, {})
        rec_key = f"{did}:{h}"
        rdir = ddir / "captures" / h
        files = cap.get("files") or {}

        # De-chrome (REQ-091): if a Stage-3 page.main.txt segment exists, signals compute over it.
        mp = rdir / "page.main.txt"
        main_text = mp.read_text(errors="replace") if mp.exists() else None
        sig, best_text, page_texts = compute_signals(rdir, prec.get("texts", []), roster_norm,
                                                     files, main_text)
        # V2 (REQ-113): record-level signals the text scan can't see, then the labeling-function combiner.
        sig["cms_hint"] = cms_hint_of(cap)
        sig["url_feed_pattern"] = feed_url(prec["url"]) or feed_url(cap.get("final_url") or "")
        sig["url_rootish"] = rootish_url(prec["url"]) or rootish_url(cap.get("final_url") or "")
        sig["embed_hosts"] = embed_hosts_of(cap)
        # Deterministic content school-year read from the URL/final-URL (#107; never inferred — REQ-054).
        # Rides signals_json for #107's prefer-recent dispatch ranking + #241's pre-2017-18 validity floor.
        sig["content_school_year"] = SY.content_school_year(prec["url"], cap.get("final_url") or "")
        # #517: the one-hop-away shape — schedule-intent keywords, (near-)zero in-window times. A recall
        # AFFORDANCE (attention chip + the link_followup retry receipt), never a scoring input.
        sig["schedule_link_only"] = schedule_link_only(sig)
        scored = COMB.score_record(sig)
        sig["detectors"] = scored["votes"]            # the fired votes, persisted for harness + UI pre-fill
        sig["decision"] = scored["decision"]          # send | suppress | review (the routing decision)
        tier, score, cat = scored["tier"], scored["sort_score"], scored["category"]

        # content hash for dedup: prefer the primary binary, else the best text content
        content_hash = None
        binp = files.get("bin") or files.get("pdf")
        if binp and (rdir / binp).exists():
            content_hash = md5_file(rdir / binp)
        else:
            best = max((t for t in prec.get("texts", []) if t.get("usable")),
                       key=lambda t: t.get("n_chars", 0), default=None)
            if best:
                try:
                    content_hash = md5_text((rdir / best["text_file"]).read_text(errors="replace"))
                except Exception:
                    content_hash = None
        dup_of = seen_content.get(content_hash) if content_hash else None
        if content_hash and not dup_of:
            seen_content[content_hash] = rec_key

        # candidates.json join (URL -> intended school(s) + discovery tools); a record whose
        # URL was never a planned candidate is EMERGENT (discovered during capture).
        cand = cand_map.get(prec["url"]) or cand_map.get(cap.get("final_url") or "")
        intended_schools = cand["schools"] if cand else []
        cand_tools = cand["tools"] if cand else []
        is_emergent = 0 if cand else 1

        sess.execute(INSERT_RECORD, {
            "rec_key": rec_key, "district_id": did, "district_dir": ddir.name,
            "url": prec["url"], "hash": h, "kind": cap.get("kind"),
            "final_url": cap.get("final_url"), "content_hash": content_hash, "duplicate_of": dup_of,
            "tier": tier, "sort_score": score, "category_hypothesis": cat,
            "signals_json": json.dumps(sig), "intended_schools_json": json.dumps(intended_schools),
            "candidate_tools_json": json.dumps(cand_tools), "is_emergent": is_emergent})
        sess.execute(text("INSERT INTO label (rec_key) VALUES (:rk) ON CONFLICT (rec_key) DO NOTHING"),
                     {"rk": rec_key})
        cluster_items.append((rec_key, shingles(best_text), tier, score))

        # representations: text reps (from processed.json) + binaries on disk
        for t in prec.get("texts", []):
            sess.execute(INSERT_REP, _rep(rec_key, t["source"], t.get("text_file"), "text",
                                          t.get("n_chars", 0), t.get("n_times", 0),
                                          int(bool(t.get("usable")))))
        # Q2.1: materialize a page SLICE as a small standalone text rep, so Stage 6 dispatches the
        # slice, not the whole PDF. WHICH slice — human range (#109; the label rows are precious and
        # survive re-ingest, so they're queryable right here) > handbook harvest > absolute floor
        # (#821) — is decided by select_slice(), the ONE predicate best_send also calls (#834), so
        # what is cut here and what may be sent there cannot disagree.
        pdf_name = files.get("pdf") or (files.get("bin")
                   if str(files.get("bin", "")).lower().endswith(".pdf") else None)
        # #833: same exists() guard compute_signals applies. A capture that NAMES a PDF absent from
        # disk otherwise leaves `pdf` truthy here while page_texts stayed [] upstream, and the
        # closure below would spawn pdftotext against a file that isn't there for every requested
        # page — harmless (pdf_page_text returns "") but a wasted subprocess each time.
        pdf = rdir / pdf_name if pdf_name else None
        if pdf is not None and not pdf.exists():
            pdf = None
        # `page_texts` came back from compute_signals, so a slice is cut from the SAME extraction
        # the per-page counts were computed over — re-extracting here would be a second chance to
        # drift from the numbers the signal stored. `page_text_from` restores the per-page form
        # feed so the bytes match what re-extraction would have produced. Falls back to a direct
        # read for a page the cached scan didn't reach.
        def page_text_of(p, _pt=page_texts, _pdf=pdf):
            return page_text_from(_pt, p) if 0 < p <= len(_pt) else (pdf_page_text(_pdf, p) if _pdf else "")

        chosen = select_slice(sig, district_facets.get(rec_key))
        if chosen and pdf:                        # pdf is already None when absent (#833)
            source, page_nums = chosen
            built = build_slice(page_nums, page_text_of, source)
            if built:
                slice_text, rep_kwargs = built
                # write to the DERIVED-artifact home, never into the raw capture dir (issue #58)
                sp = slice_path(did, rec_key, source)
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(slice_text)
                sess.execute(INSERT_REP, _rep(rec_key, **rep_kwargs))
        for key, fname in files.items():
            fk = BIN_KINDS.get(key)
            if not fk:
                continue
            if str(fname).lower().endswith(".pdf"):
                fk = "pdf"
            elif str(fname).lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp", "gif"):
                fk = "image"
            sess.execute(INSERT_REP, _rep(rec_key, f"capture:{key}", fname, fk, None, None, 1))
        # rasterized pages (Stage 4) as image reps for visual inspection
        for rp in sorted(rdir.glob("raster_p*.png")):
            sess.execute(INSERT_REP, _rep(rec_key, "raster", rp.name, "image", None, None, 1))
        # Stage-3 DOM segments (REQ-091) as inspectable text reps when present: main (de-chromed
        # body, what signals run on) + the quarantined chrome (header/footer/nav, screened separately).
        for seg in ("page.main.txt", "page.header.txt", "page.footer.txt", "page.nav.txt"):
            sp = rdir / seg
            if sp.exists():
                sess.execute(INSERT_REP, _rep(rec_key, f"segment:{seg.split('.')[1]}", seg, "text",
                                              len(sp.read_text(errors='replace')), None, 1))
        district_records.append((rec_key, sig, tier, dup_of))

    # near-duplicate clustering (content-similarity; honors human splits) -> UPDATE records
    for rk, (cid, is_rep, size) in cluster_district(cluster_items, splits).items():
        # INVARIANT (#158): a MULTI-MEMBER cluster's REPRESENTATIVE is the canonical record for its
        # cluster, so it must NOT itself carry duplicate_of. Content-hash dedup (duplicate_of,
        # first-seen wins) and shingle clustering (is_cluster_rep, by tier/score) pick their keeper
        # INDEPENDENTLY and can disagree — when the chosen rep happens to be a content-dup of a
        # cluster sibling, the release CANONICAL_RECORD_WHERE
        # (`duplicate_of IS NULL AND (is_cluster_rep=1 OR cluster_id IS NULL)`) matches NEITHER
        # member and the whole cluster is silently dropped from dispatch. Clearing the rep's
        # duplicate_of makes it the one canonical member; non-reps are excluded by cluster membership
        # regardless. SCOPE: multi-member reps ONLY (cid is not None) — singletons also arrive here
        # with is_rep=1 (cluster_district emits (None,1,1)), and a singleton carrying duplicate_of is
        # a LEGITIMATE state (an unclustered exact content-dup, correctly suppressed while its
        # first-seen partner is canonical); clearing those would wipe content-hash dedup on every
        # re-ingest. Deterministic (rep choice unchanged) and idempotent across re-ingest.
        sess.execute(text("UPDATE record SET cluster_id=:cid, is_cluster_rep=:rep, cluster_size=:sz"
                          + (", duplicate_of=NULL" if (is_rep and cid is not None) else "")
                          + " WHERE rec_key=:rk"),
                     {"cid": cid, "rep": is_rep, "sz": size, "rk": rk})

    # guessed topology (coarse, deterministic, from SIGNALS — noisy; kept to measure the heuristic)
    non_dup = [(rk, sg, tr) for rk, sg, tr, d in district_records if not d]
    sched = [(rk, sg) for rk, sg, tr in non_dup if tr in ("A", "B")]
    max_roster_on_one = max((sg["roster_school_names_hit"] for _, sg in sched), default=0)
    if roster_size and max_roster_on_one >= max(2, roster_size * 0.5):
        topo = "hub"
    elif len(sched) >= 2:
        topo = "per_school"
    else:
        topo = "unknown"
    # NCES denominator: PREFER the Stage-1 batch (captured at queue time, with provenance);
    # fall back to the live CSV count when no batch entry exists for this district.
    did7 = str(did).zfill(7)
    bt = batches.get(did7)
    nces_counts = (bt or {}).get("nces_school_counts") or {}
    nces_total = nces_counts.get("total", nces.get(did7))
    sess.execute(text(
        """INSERT INTO district (district_id, name, state, district_dir, batch_id,
             guessed_topology, labeled_topology, nces_school_count, n_records)
           VALUES (:district_id, :name, :state, :district_dir, :batch_id,
             :guessed_topology, :labeled_topology, :nces_school_count, :n_records)"""),
        {"district_id": did, "name": disc.get("name"), "state": disc.get("state"),
         "district_dir": ddir.name, "batch_id": disc.get("batch_id"), "guessed_topology": topo,
         "labeled_topology": None, "nces_school_count": nces_total, "n_records": len(district_records)})
    if bt:
        sess.execute(text(
            """INSERT INTO district_target (district_id, batch_id, nces_year, nces_total,
                 nces_by_level_json, enrollment_k12, lea_claimed_bands_json, schools_by_band_json)
               VALUES (:district_id, :batch_id, :nces_year, :nces_total,
                 :nces_by_level_json, :enrollment_k12, :lea_claimed_bands_json, :schools_by_band_json)"""),
            {"district_id": did, "batch_id": bt.get("_batch_id"),
             "nces_year": bt.get("_nces_year"), "nces_total": nces_counts.get("total"),
             "nces_by_level_json": json.dumps(nces_counts.get("by_level", {})),
             "enrollment_k12": bt.get("enrollment_k12"),
             "lea_claimed_bands_json": json.dumps(bt.get("lea_claimed_bands", [])),
             "schools_by_band_json": json.dumps(bt.get("schools_by_band", {}))})
    return did


def _regenerate_filtered(district_ids: list) -> tuple[int, int]:
    """Regenerate filtered.json for the given districts (or all if None) in a SEPARATE session, after
    the ingest has committed so reads see the new signals. Local import avoids a build_signals<->release
    module cycle (same pattern as main()). Returns (n_written, n_send)."""
    from infrastructure.acquisition.stage5_filter import release
    n_written = n_send = 0
    with gdb.session_scope() as s:
        rows = []
        if district_ids is None:
            rows = release.generate(s, root=RAW_DIR)
        else:
            for did in district_ids:
                rows.extend(release.generate(s, district_id=did, root=RAW_DIR))
        n_written = sum(1 for r in rows if r["written"])
        n_send = sum(r["n_send"] for r in rows)
    return n_written, n_send


def ingest_batch(district_ids: list, root: Path = RAW_DIR, *, regenerate_filtered: bool = True) -> dict:
    """INCREMENTAL Stage-5 ingest for ONE batch's districts (the Stage-4 batch-completion hook). Unlike
    ingest() this does NOT drop the signal tables — it ensures them (CREATE IF NOT EXISTS) and re-ingests
    ONLY the given districts (per-district DELETE+INSERT), so prior batches are untouched and the cost
    stays proportional to the batch, not the whole on-disk corpus. PRECIOUS label/cluster_split survive
    (rec_key is stable). Then regenerates filtered.json for just these districts. Returns a summary."""
    gdb.init_precious_schema()           # PRECIOUS label + cluster_split (models); never dropped
    ingested: list = []
    with gdb.session_scope() as sess:
        ensure_signal_schema(sess)       # CREATE IF NOT EXISTS — never drops prior batches
        CI.ensure_cache_schema(sess)
        import_splits(sess)
        splits = {r[0] for r in sess.execute(text("SELECT rec_key FROM cluster_split"))}
        batches = load_batches()
        nces = nces_school_counts()
        for did in district_ids:
            # Resolve did -> its dir directly (O(batch), not a corpus scan): dirs are named `<did>_<slug>`.
            for ddir in sorted(p for p in root.glob(f"{did}_*") if p.is_dir()):
                if ingest_district(sess, ddir, splits=splits, batches=batches, nces=nces):
                    ingested.append(did)
        # Restore-before-export, mirroring ingest(): after the loop has seeded label rows, restore
        # any labels from the JSON backup (no-op on a healthy DB) — so the export_labels below can
        # never truncate the precious backup after a DB wipe (fable review 2026-07-01, finding 2.3).
        import_labels(sess)
        att_cfg = AT.load_config()
        for did in set(ingested):
            recompute_labeled_topology(sess, did)
            recompute_attention(sess, did, att_cfg)
        export_labels(sess)              # keep the JSON backups in sync with the DB
        export_splits(sess)
        n_rec = sess.execute(text("SELECT COUNT(*) FROM record WHERE district_id = ANY(:ids)"),
                             {"ids": ingested or [""]}).scalar()
    n_written = n_send = 0
    regen_error = None
    if regenerate_filtered and ingested:
        # Runs AFTER the DB transaction above committed. filtered.json is a REGENERABLE receipt
        # (the DB is the working store), so a failure here must not raise and mislabel the
        # committed ingest as failed (#240 review) — record it in the summary and move on.
        try:
            n_written, n_send = _regenerate_filtered(sorted(set(ingested)))
        except Exception as e:  # noqa: BLE001
            regen_error = f"{type(e).__name__}: {e}"
            print(f"[warn] ingest committed but filtered.json regen failed ({regen_error}); "
                  f"re-run release.write_filtered for these districts")
    summary = {"districts": sorted(set(ingested)), "n_districts": len(set(ingested)),
               "n_records": n_rec, "n_filtered_written": n_written, "n_send": n_send,
               **({"filtered_regen_error": regen_error} if regen_error else {})}
    print(f"ingest_batch: {summary['n_districts']} districts, {n_rec} records re-ingested; "
          f"filtered.json regenerated for {n_written} ({n_send} records to send)")
    return summary


def assert_fingerprint_promotion(sess) -> tuple:
    """#688 seam fitness (corpus-level, two COUNT queries): if ANY capture fingerprint carries a
    cms_hint, SOME record signal must carry one — the promotion path reads disk rows the accessors
    must match, and a key-shape mismatch here is silent (None is a legal 'unknown CMS', no detector
    fires differently, so the bug survived from REQ-115 until 2026-07-29). Raises SystemExit INSIDE
    the ingest transaction (the assert_floor discipline: the broken ingest never commits)."""
    n_fp = sess.execute(text(
        "SELECT COUNT(*) FROM capture WHERE (fingerprint_json::jsonb ->> 'cms_hint') IS NOT NULL")).scalar()
    n_rec = sess.execute(text(
        "SELECT COUNT(*) FROM record WHERE (signals_json::jsonb ->> 'cms_hint') IS NOT NULL")).scalar()
    if n_fp and not n_rec:
        raise SystemExit(
            f"fingerprint promotion is DEAD (#688): {n_fp} capture fingerprint(s) carry cms_hint but "
            f"0 record signals do — the cms_hint_of/embed_hosts_of accessors no longer match the "
            f"capture-row shape they are handed. Aborting before commit.")
    return n_fp, n_rec


def ingest(root: Path, assert_floor: bool = False):
    """FULL ingest into the isolated governance Postgres DB (REQ-103): drop + rebuild every derived
    signal table over EVERY Stage-4-complete district on disk. The PRECIOUS tables are created from the
    models (never dropped); the whole pass is one transaction (atomic re-ingest). For the incremental,
    batch-scoped path the Stage-4 console uses, see ingest_batch().

    assert_floor (#208): run harness.assert_floor INSIDE the transaction — a recall-floor violation
    raises SystemExit BEFORE the commit, so the bad config's tiers never reach the working store."""
    gdb.init_precious_schema()           # PRECIOUS label + cluster_split (models); never dropped
    ingested: list = []
    with gdb.session_scope() as sess:
        for ddl in REBUILD_DDL:          # drop + rebuild the DERIVED signal tables
            sess.execute(text(ddl))
        CI.ensure_cache_schema(sess)     # cross-stage cache is live/never-dropped — ensure, then upsert below
        import_splits(sess)              # restore cluster splits to the table if it was wiped
        splits = {r[0] for r in sess.execute(text("SELECT rec_key FROM cluster_split"))}
        batches = load_batches()         # did -> Stage-1 targeting entry (preferred NCES denominator)
        nces = nces_school_counts()      # did -> distinct regular-school count (live CSV FALLBACK)

        for ddir in sorted(p for p in root.iterdir() if p.is_dir()):
            did = ingest_district(sess, ddir, splits=splits, batches=batches, nces=nces)
            if did:
                ingested.append(did)

        # Restore any labels the DB is missing from the JSON source of truth (no-op on a normal
        # re-ingest where the label table was preserved; the recovery path after a DB wipe).
        restored = import_labels(sess)
        # labeled_topology + attention are derived from the (now-restored) human labels + stored signals.
        att_cfg = AT.load_config()
        for did in ingested:
            recompute_labeled_topology(sess, did)
            recompute_attention(sess, did, att_cfg)
        n_rec = sess.execute(text("SELECT COUNT(*) FROM record")).scalar()
        n_lab = sess.execute(text("SELECT COUNT(*) FROM label WHERE status!='unlabeled'")).scalar()
        n_dist = sess.execute(text("SELECT COUNT(*) FROM district")).scalar()
        by_tier = dict(sess.execute(text("SELECT tier, COUNT(*) FROM record GROUP BY tier")).fetchall())
        n_clustered = sess.execute(text("SELECT COUNT(*) FROM record WHERE cluster_id IS NOT NULL")).scalar()
        n_clusters = sess.execute(text(
            "SELECT COUNT(DISTINCT cluster_id) FROM record WHERE cluster_id IS NOT NULL")).scalar()
        by_topo = dict(sess.execute(text(
            "SELECT labeled_topology, COUNT(*) FROM district GROUP BY labeled_topology")).fetchall())
        n_targeted = sess.execute(text("SELECT COUNT(*) FROM district_target")).scalar()
        n_emergent = sess.execute(text("SELECT COUNT(*) FROM record WHERE is_emergent=1")).scalar()
        # cross-stage cache row counts (REQ-103c)
        cache = {t: sess.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                 for t in ("discovery_school", "candidate", "capture", "processed_doc")}
        exported = export_labels(sess)        # keep the JSON backups in sync with the DB
        exported_splits = export_splits(sess)
        # #688 seam fitness — always on (structural invariant, not config-dependent): a full ingest
        # that would leave the fingerprint promotion dead aborts inside the transaction.
        n_fp_hint, n_rec_hint = assert_fingerprint_promotion(sess)
        if assert_floor:
            # ENFORCE the recall floor INSIDE the transaction (#208): a violation raises SystemExit here,
            # session_scope never commits, and close() discards the whole re-ingest (transactional DDL) —
            # the console keeps serving the prior config's tiers. Local import: harness imports this module.
            from infrastructure.acquisition.stage5_filter import harness
            floor_rec = harness.assert_floor(sess)
    if assert_floor:
        print(f"recall floor OK: tier-{harness.FLOOR_TIER} recall={floor_rec} >= {harness.RECALL_FLOOR}")
    print(f"ingest done: {n_dist} districts, {n_rec} records, {n_lab} labeled "
          f"({restored} restored from labels.json), {exported} exported to labels.json")
    print(f"clustering: {n_clustered} records in {n_clusters} clusters; {exported_splits} splits backed up")
    print(f"stage-1/2 ingest: {n_targeted} districts with batch targeting; {n_emergent} emergent records (captured, not a candidate)")
    print(f"fingerprint promotion (#688): {n_fp_hint} capture fingerprints with cms_hint -> {n_rec_hint} records with the signal")
    print(f"cross-stage cache: {cache['discovery_school']} discovery_school, {cache['candidate']} candidate, "
          f"{cache['capture']} capture, {cache['processed_doc']} processed_doc rows")
    print("by tier:", by_tier)
    print("labeled_topology:", by_topo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(RAW_DIR))
    ap.add_argument("--no-release", action="store_true",
                    help="skip regenerating filtered.json after ingest")
    ap.add_argument("--assert-floor", action="store_true",
                    help="enforce the labeled-set recall floor (harness.FLOOR_TIER recall >= RECALL_FLOOR) "
                         "INSIDE the ingest transaction — a violation aborts WITHOUT committing, leaving the "
                         "prior config's tiers live (#208). Off by default so a routine batch ingest isn't "
                         "gated; a config change / automation requires it.")
    a = ap.parse_args()
    ingest(Path(a.root), assert_floor=a.assert_floor)
    # Event-driven: the first scoring pass (and any re-ingest after new discovery adds URLs/reps)
    # regenerates each district's filtered.json projection — no manual trigger (REQ-094). Local
    # import avoids a build_signals<->release module cycle; runs AFTER ingest commits so reads see it.
    if not a.no_release:
        from infrastructure.acquisition.stage5_filter import release
        with gdb.session_scope() as s:
            summary = release.generate(s, root=Path(a.root))
        print(f"filtered.json: regenerated {sum(1 for r in summary if r['written'])} "
              f"({sum(r['n_send'] for r in summary)} records to send)")


if __name__ == "__main__":
    main()
