#!/usr/bin/env python3
"""Stage 5 → 6 release generator (REQ-094): the deterministic record→representation descent that
emits one **`filtered.json`** per district — the traceable Stage-5 release artifact.

`filtered.json` is a REGENERABLE export of the governance DB's release decision (governance
§4/§5): for each **canonical** record (non-duplicate; cluster representative or singleton) it
records a `decision` (send | reject) + a `reason`, and for the sent ones the **one best
representation** the council should read. It is stamped with the per-district `(config, labels,
data)` fingerprints so staleness is detectable, and carries the district topology / NCES
denominator / completeness / a coarse cost estimate for Stage 6's go/no-go.

NO AI here — the descent is pure deterministic code (the Stage-5 binding constraint). This is the
same function the console's "Generate / Release" button (and a future scheduler) will call.

Release rule (tier-gated, Ian 2026-06-30): a record labeled with a TARGET label → **send**; a labeled
non-target → **reject**. Unlabeled records are gated by their Stage-5 likelihood **tier**: **A → send**
(auto-dispatch the confident targets), **B/C → hold** (a third decision — a maybe-target awaiting a human
label at gate@5; never auto-spent on), **D → reject**. So cost is committed only on labeled targets +
confident (tier-A) targets; the uncertain middle waits for judgment.

Usage:  python3 -m infrastructure.acquisition.stage5_filter.release [--district DID]
"""
import argparse
import hashlib
import json

from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM  # noqa: E402  (#718: the ONE benchmark/gt:// predicate home)
from infrastructure.acquisition.common import paths  # noqa: E402
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (governance Postgres — REQ-103)
from infrastructure.acquisition.common import receipts as RCPT  # noqa: E402  (REQ-164 audit receipts)
from infrastructure.utilities import school_year as SY  # noqa: E402  (calendar-vocabulary SSOT; the #241 validity floor — NOT the LCT DB)
from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402  (TARGET_LABELS)
from infrastructure.acquisition.common.timeutil import utcnow as _now

RAW_DIR = paths.RAW_CAPTURES
TARGET_LABELS = BS.TARGET_LABELS
HONEST_LABEL = "gross_bell_to_bell"   # REQ-055 — what the council's start/end numbers mean

# The CANONICAL-record predicate (cluster representative or singleton, non-duplicate) — the population
# the release rule runs over. Exported as a single source of truth so Stage 6's candidate count keys off
# the SAME definition instead of re-inlining it (avoids drift if "canonical" ever changes). `r` = record.
CANONICAL_RECORD_WHERE = "r.duplicate_of IS NULL AND (r.is_cluster_rep = 1 OR r.cluster_id IS NULL)"

# The "money-leak" review population (#516 FP lane): a tier-A record — which `decide()` would AUTO-SEND on
# the unlabeled path — that a human labeled `target_absent`. The machine would spend on a page the human
# already judged to hold no schedule; the disagreement is exactly the false-send the tuning loop chases.
# One home (like CANONICAL_RECORD_WHERE) so the console's FP-lane SQL can't drift from the tier-A auto-send
# definition `decide()` encodes — if that definition changes (e.g. a new eligibility gate), update HERE.
# `r` = record, `l` = its LEFT-JOINed label row.
MONEY_LEAK_WHERE = "r.tier = 'A' AND l.primary_label = 'target_absent'"




def _h(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", "replace")).hexdigest()[:12]


# ----------------------------- the descent (PURE — no DB, no AI) -----------------------------
def _best_image(images: list) -> dict:
    """Prefer the rendered page screenshot (`capture:png`) over a rasterized PDF page."""
    return next((r for r in images if (r.get("source") or "").startswith("capture:png")), images[0])


# The floor slice must EARN its send: it is a recall-preserving filter, not a precision selector,
# so unlike the handbook branch (where ties go to the slice and no saving test applies) it also has
# to be materially smaller. Value chosen from the measured saving distribution, not asserted.
MIN_SLICE_SAVING_FRAC = 0.20


def prefer_timebearing_slice(slice_rep: dict, best_text: dict, reps: list = None,
                             min_saving_frac: float = MIN_SLICE_SAVING_FRAC) -> bool:
    """#821: send the absolute-floor slice only when it is (a) yield-competitive — the same #230
    rule the handbook branch uses, `n_times >= the densest text rep's` — AND (b) materially smaller.

    Deliberately NOT shared with the handbook branch: that branch's policy is fixed by the
    byte-identity guarantee and must not move when this one is tuned.

    On (a): the two counts are NOT like-for-like, and that asymmetry is load-bearing. A slice's
    `n_times` comes from `build_signals.time_positions` (regex PLUS `to_minutes` validity
    filtering); a general text rep's comes from Stage 4's different regex with NO validity filter.
    So for identical text `stage4_count >= build_signals_count`, and the slice is systematically
    DISADVANTAGED here. That means a provably lossless slice can still lose and fall back to the
    full read — fail-safe, and the reason the projected token saving is an upper bound. Do not
    "fix" this into a like-for-like comparison: aligning the counters would move the handbook
    branch too, which is exactly what the byte-identity guarantee forbids."""
    if not best_text:
        return True                                  # nothing to compare against; scoping is free
    if (slice_rep.get("n_times") or 0) < (best_text.get("n_times") or 0):
        return False
    slice_chars = slice_rep.get("n_chars") or 0
    # #838: the slice is cut from the PDF rendering, whose text rep is `pdftotext`. On an HTML
    # capture the densest text can be a DIFFERENT extraction (page.txt, an OCR rep) — so a slice
    # can "save" against what it displaces while being no smaller than, or larger than, its own
    # parent (3800038:df6bcfc4b7: a 1,786-char slice of a 1,783-char pdftotext, displacing a
    # 2,985-char page.txt). A slice that is not smaller than the document it was cut FROM is not
    # scoping that document; it is a re-labelled copy, and it must not win. Both tests apply: no
    # bigger than its parent AND a material saving against what it displaces — the second is the
    # one that matters for spend (that is what would otherwise be sent), the first is the one that
    # keeps the word "slice" honest.
    parent = next((r for r in (reps or []) if r.get("source") == "pdftotext"
                   and r.get("file_kind") == "text" and r.get("filename")), None)
    if parent and slice_chars >= (parent.get("n_chars") or 0):
        return False
    full = best_text.get("n_chars") or 0
    if not full:
        return False
    saved = (full - slice_chars) / full
    return saved >= min_saving_frac


def sendable_text_reps(reps: list) -> list:
    """The record's text reps eligible to BE the send — the "densest text" pool `best_send` ranks.

    ONE definition (#866), so the pool and the 7->6 swap set cannot drift: both are
    `NON_SWAPPABLE_SOURCES`. Spelling the exclusion inline made `best_send` a FOURTH site with a
    private copy of that set, and the drift it invites is concrete — a source added straight to
    the union (#685's hidden-panel rep, a future `segment:aside`) would be barred from every 7->6
    retry while staying eligible as the FIRST send, which is the exact shape #862 was filed to
    close. Exported because the measurement scripts replay this pool too (#869).

    Excluded, and why the two exclusions are the same rule seen twice:
      • page SLICES — a slice is a strict SUBSET of another rep of the same record, so ranking it
        as a general "densest text" candidate runs the ladder downward. With a second slice kind
        (#821) an `!= "harvest_slice"` test would let the timebearing slice in, where it would
        become its own `best_text` and the yield guard below would compare it with itself.
      • CHROME segments (header/footer/nav) — the de-chrome quarantine. REQ-091 does not screen
        chrome OUT (it keeps header/footer precisely because real school hours sometimes sit
        there); it screens them SEPARATELY, so they inform the keyword/category/roster SIGNALS
        while `page.txt` — the whole body, chrome included — is what a council reads. Sending an
        isolated nav menu is not that design; it is a nav menu. `usable` is NOT a real bar here:
        ingest hardcodes `usable=1` for every segment (build_signals.py) while page.txt/pdftotext
        carry Stage 4's >=120-char test, so chrome can be a thin page's only "usable" text
        (measured: 1 canonical record; it takes the image branch first, because `visual_text_gap`
        is by construction true when every real text rep is sub-usable — #868).

    RESIDUAL GAP, measured — do not restate the tidier claim this comment used to make. "The
    footer's evidence survives in page.txt" is FALSE on 5 live records: page.txt is read at
    DOM-ready+2.5s and the segments at end-of-capture, so a late-rendered footer holds clock times
    page.txt never saw (0103390:fb71b7cc63 — footer 12, page.txt 0). Chrome is barred from
    `alternates()` too, so no automated path reaches those times. All 5 are reject-decided today
    (0 dispatch affected) and the cause is the read-timing split, #863 — fix that and the claim
    becomes true rather than convenient. Watched by
    docs/technical-notes/production-quality-control-research/2026-08-19-chrome-first-send-measure.py,
    whose C3 must never report a SEND-decided record.
    """
    return [r for r in reps
            if r.get("file_kind") == "text" and r.get("usable") and r.get("filename")
            and r.get("source") not in NON_SWAPPABLE_SOURCES]


def best_send(reps: list, signals: dict, facets: dict) -> list:
    """The ONE best representation for the council to read (governance §4). reps: the record's
    representation rows ({source, filename, file_kind, n_chars, n_times, usable}). Returns a list
    of send entries (usually one): handbook → the PDF + harvest pages; image when text never
    captured the content (visual_text_gap / the human needs_vision facet, REQ-114 Axis 3);
    else the densest text."""
    facets = facets or {}
    signals = signals or {}
    usable_text = sendable_text_reps(reps)
    images = [r for r in reps if r.get("file_kind") == "image" and r.get("filename")]
    pdfs = [r for r in reps if r.get("file_kind") == "pdf" and r.get("filename")]
    # WHICH slice this record gets is decided ONCE, by select_slice (#834) — the same call ingest
    # made when it cut the slice. `handbookish` here means "select_slice chose the harvest slice":
    # a human page range (#109 — the human looked, so it outranks the auto harvest_pages), or a
    # handbook whose peak-relative harvest found pages. NB this is deliberately wider than the old
    # `is_handbook or (human_pages and buried_handbook == "yes")`: that extra `buried_handbook`
    # test was the second half of the #834 disagreement — ingest honoured a bare human range and
    # cut a harvest slice, this gate then refused to send it, and the record was ALSO denied the
    # floor. A reviewer who typed a page range but did not tick buried_handbook still looked.
    chosen = BS.select_slice(signals, facets)
    handbookish = bool(chosen and chosen[0] == BS.HARVEST_SLICE_SOURCE)
    harvest = chosen[1] if handbookish else []
    slice_rep = next((r for r in reps if r.get("source") == "harvest_slice" and r.get("filename")), None)

    # ONE densest-text computation (n_times, then n_chars) — shared by the handbook yield-compare
    # and the plain densest-text pick below, so the two can't diverge (and no double scan).
    best_text = max(usable_text, key=lambda r: ((r.get("n_times") or 0), (r.get("n_chars") or 0)),
                    default=None)

    # handbook → the materialized harvest-pages SLICE (Q2.1: a ~1-4 page text doc, not the whole PDF);
    # fall back to the PDF + a pages hint only when the slice wasn't materialized (older ingests).
    # #230: the slice is preferred only while its YIELD is competitive — round 1 used to send a thin
    # slice unconditionally while a far denser text rep sat unsent as an alternate (Redbank: slice
    # n_times=26 sent, pdftotext n_times=90 waiting), wasting a paid round before the 7->6 retry
    # self-corrected. Same ordering rule as the retry loop's rank_alternates: yield-bearing text by
    # n_times, ties to the slice (it's the purpose-built handbook rep).
    if handbookish and slice_rep:
        best_text_times = (best_text.get("n_times") or 0) if best_text else 0
        if (slice_rep.get("n_times") or 0) >= best_text_times:
            return [{"file": slice_rep["filename"], "kind": "text", "pages": harvest}]
        # a denser general text rep exists — fall through to the densest-text pick below
    # the PDF+pages fallback is ONLY for a handbook whose slice wasn't materialized (older ingests) —
    # gated on `not slice_rep`, or it would intercept the yield fall-through above and re-waste the
    # round on the whole PDF (adversarial review of the #230 fix caught exactly that).
    if handbookish and not slice_rep and harvest and pdfs:
        return [{"file": pdfs[0]["filename"], "kind": "pdf", "pages": harvest}]
    if (facets.get("needs_vision") == "yes" or signals.get("visual_text_gap")) and images:
        return [{"file": _best_image(images)["filename"], "kind": "image"}]
    # #821 the ABSOLUTE page floor. Sits AFTER the vision branch — a record whose text never
    # captured the content is exactly where a slice OF that text is worst, and vision is right.
    #
    # Gated on what select_slice() CHOSE for this record (#834), not on a hand-written "is this a
    # handbook" test. The two must agree with ingest, and a separate predicate here didn't: it
    # hid the floor slice on 35 live handbooks whose peak-relative harvest found nothing (so the
    # floor was the only scoping they had), and starved 8 human-labelled records. select_slice is
    # the ONE arbiter both sides call. The hijack this guard was protecting against — a handbook
    # whose HARVEST slice lost the #230 compare falling through into a floor slice — is still
    # impossible: if select_slice chose harvest, a floor rep is never sent (nor cut), and if it
    # chose the floor, there is no harvest slice to fall through FROM.
    tb_rep = None
    if chosen and chosen[0] == BS.TIMEBEARING_SLICE_SOURCE:
        tb_rep = next((r for r in reps if r.get("source") == BS.TIMEBEARING_SLICE_SOURCE
                       and r.get("filename")), None)
    if tb_rep and prefer_timebearing_slice(tb_rep, best_text, reps):
        return [{"file": tb_rep["filename"], "kind": "text",
                 "pages": signals.get("timebearing_pages") or []}]
    if best_text:
        return [{"file": best_text["filename"], "kind": "text"}]
    # degenerate fallbacks (a target with no usable text rep): any image, else any pdf
    if images:
        return [{"file": _best_image(images)["filename"], "kind": "image"}]
    if pdfs:
        return [{"file": pdfs[0]["filename"], "kind": "pdf"}]
    return []


# The quarantined de-chrome segments (header/footer/nav) are NOT swappable schedule representations —
# they're the chrome we deliberately screened OUT. (segment:main, the de-chromed body, IS a candidate.)
CHROME_SOURCES = {"segment:header", "segment:footer", "segment:nav"}
# The FULL set of sources that are never a 7->6 swap candidate (#837), defined ONCE for the three
# collectors (release.alternates, stage7_run's alternates SQL, stage7_execute.live_alternates) —
# each of which used to spell its own exclusion (`in CHROME_SOURCES` / `NOT LIKE 'segment:%'` /
# `.startswith("segment:")`), the implemented-twice-drifts class. Chrome, because it was screened
# out on purpose; page SLICES, because a slice is a strict SUBSET of another rep of the same
# record — retrying a subset of text that already failed is the 7->6 ladder run downward
# ("partial-text -> FULLER text -> vision", rank_alternates), and a slice with high n_times used to
# outrank the vision escalation. Measured live: 126 unsent slices carried n_times >= the sent full
# text; 2 were already the top-ranked alternate.
# TWO roles, deliberately ONE set (#862/#866): a source in here is neither a 7->6 swap candidate
# NOR eligible to be the first send (`sendable_text_reps`). They were separate rules until #862 —
# chrome was barred from the retry ladder but reachable as the first send, and only the accident
# that segment n_times was NULL kept it from winning. If the two roles ever need to diverge, SPLIT
# the constant rather than re-spelling one of them at a call site.
NON_SWAPPABLE_SOURCES = frozenset(CHROME_SOURCES) | BS.SLICE_SOURCES


def alternates(reps: list, exclude: set) -> list:
    """The record's OTHER usable candidate representations (beyond the winner) — usable text reps +
    images + pdfs, distinct by filename — that a reviewer could swap to at gate@6 (REQ-094 follow-up,
    governance §11g). Only target-flagged records get alternates (the record is the target unit)."""
    out, seen = [], set(exclude)
    for r in reps:
        fn = r.get("filename")
        if not fn or fn in seen:
            continue
        if (r.get("source") or "") in NON_SWAPPABLE_SOURCES:   # chrome + slices (#837)
            continue
        # #856: `usable` gates EVERY kind, as it does in the other two collectors (stage7_run's
        # SQL `usable = 1`, stage7_execute.live_alternates). This site used to check it for text
        # only — latent (ingest hardcodes usable=1 for pdf/image today) but the very asymmetry
        # #841 unified the source rule to remove, and an ingest that ever marks a corrupt raster
        # unusable would have re-opened the three-way disagreement here.
        if not r.get("usable"):
            continue
        fk = r.get("file_kind")
        if fk not in ("text", "image", "pdf"):
            continue
        out.append({"file": fn, "kind": fk})
        seen.add(fn)
    return out


# #241 pre-2017-18 VALIDITY FLOOR — a REQ-026 correctness guarantee, NOT a money lever (obs. 6). A doc
# whose content school year predates the CRDC 2017-18 federal input we blend against breaks REQ-026's
# ≤3-year span no matter how good its times look. Semantics = HOLD (suppress-to-review), never reject:
# reversible, preserves a district whose ONLY evidence is old (Brashear's 2012-13 Timetracker). Applies
# to the AUTO path only — an explicit human target label is the override.
_VALIDITY_FLOOR_START = SY.start_year(SY.SPED_BASELINE_YEAR)   # 2017


# #674: the human's HOLD override — the converse of #241's send override. The floor gave a reviewer
# a way to force-SEND a below-floor record ("preserve a district whose ONLY evidence is old") but no
# way to force-HOLD one, and the two standing rules composed into a guarantee: the labeling doctrine
# REQUIRES a correctly-shaped 2014-15 schedule to be target-labeled (withholding the label teaches
# the detector the shape is not a target), and a target label is an unconditional send. So following
# the labeling rule correctly guaranteed out-of-window material reached paid extraction. TAOS
# `3500127` shipped two such reps in a frozen production dispatch.
#
# A FACET, deliberately, not a label: `primary_label` carries SHAPE and must stay uncorrupted as
# training signal, while this is a FITNESS-FOR-USE judgment about the instance. The two axes are
# orthogonal and `decide()` already receives both. Semantics are HOLD, never reject (#241's posture):
# reversible, and the record + its shape label survive intact and countable.
OUT_OF_WINDOW_FACET = "out_of_window"


def human_held_out_of_window(facets) -> bool:
    """True iff a human marked this record out of the approved temporal window at gate@5 (#674).
    Checked BEFORE the target-label branch in `decide`, because it exists precisely to override it."""
    return (facets or {}).get(OUT_OF_WINDOW_FACET) == "yes"


# The SQL twin of `human_held_out_of_window`, defined ONCE next to it (like CANONICAL_RECORD_WHERE)
# so the gate@6 candidate counts (server.handoff_candidates) mirror decide()'s first branch from one
# spelling — the query used to hand-copy this expression five times (#855). `l` = the LEFT-JOINed
# label row. GUARDED (#857): `::jsonb` on malformed text raises and would fail the whole aggregate
# query, not one row; `pg_input_is_valid` (PG16) reads such a row as NOT held, the same "survive a
# bad shape" posture as the Python-side `harness.parse_facets` (#199). NULL facets → NULL → ''.
OUT_OF_WINDOW_WHERE = (
    "COALESCE(CASE WHEN pg_input_is_valid(l.facets_json, 'jsonb') "
    f"THEN l.facets_json::jsonb->>'{OUT_OF_WINDOW_FACET}' END, '') = 'yes'")


def pre_validity_floor(content_school_year) -> bool:
    """True iff a KNOWN content school year is older than the 2017-18 CRDC baseline. Unknown/absent/
    malformed ⇒ False (coexists; never treated as oldest — the #254 unknown-year rule). Public because
    the gate@6 candidate badge (server.handoff_candidates) and the gate@5 calibration hook
    (gate_calibration) must mirror this same auto-HOLD to stay consistent with decide() — the SINGLE
    source of truth for the floor (a code review flagged those two call sites reading tier as a stale
    proxy for decide())."""
    try:
        return SY.start_year(content_school_year) < _VALIDITY_FLOOR_START
    except (ValueError, TypeError):
        return False


def decide(rec: dict) -> dict:
    """The release decision for one canonical record. Returns {decision, reason, send, alternates}."""
    label = rec.get("label")
    sig = rec.get("signals") or {}
    facets = rec.get("facets") or {}
    reps = rec.get("reps", [])
    # #674: an explicit human out-of-window judgment HOLDS the record even when it is target-labeled
    # — the only override that was missing. Deliberately FIRST: the whole defect was that the target
    # branch below returns unconditionally, so any check placed after it is unreachable for exactly
    # the population this protects. No automatic recency veto is introduced anywhere (#241 measured
    # that actively harmful: it removed 1 false-send while vetoing 17 real targets).
    if human_held_out_of_window(facets):
        return {"decision": "hold", "reason": "human:out-of-window", "send": [], "alternates": []}
    if label in TARGET_LABELS:
        send = best_send(reps, sig, facets)
        reason = f"target-label:{label}" + ("" if send else ";no-usable-rep")
        return {"decision": "send", "reason": reason, "send": send,
                "alternates": alternates(reps, {s["file"] for s in send})}
    if label:                                   # labeled, non-target
        return {"decision": "reject", "reason": f"non-target:{label}", "send": [], "alternates": []}
    # unlabeled → TIER-GATED auto-dispatch (Ian, 2026-06-30): only tier **A** auto-sends to the paid
    # council. **B/C are HELD pending a human label at gate@5** — the uncertain middle isn't spent on
    # blindly; it waits for judgment (and the learning loop should turn more of it into confident A's).
    # D is a confident reject. `hold` is a THIRD decision, distinct from `reject` (not-a-target): it means
    # "a maybe-target awaiting your label," so the funnel + UI can surface it as the label queue.
    tier = rec.get("tier")
    if tier == "A":
        send = best_send(reps, sig, facets)
        if send:
            # #241 validity floor: a pre-2017-18 content school year HOLDS the auto-send for review
            # (a REQ-026 correctness guard; ~0 money — obs. 6). The human overrides by labeling it a
            # target (the branch above), which is what preserves a district whose only evidence is old.
            csy = sig.get("content_school_year")
            if pre_validity_floor(csy):
                return {"decision": "hold", "reason": f"stale:pre-{SY.SPED_BASELINE_YEAR}-validity-floor:{csy}",
                        "send": [], "alternates": []}
            return {"decision": "send", "reason": "auto:tier-A", "send": send,
                    "alternates": alternates(reps, {s["file"] for s in send})}
        return {"decision": "reject", "reason": "auto:tier-A;no-usable-rep", "send": [], "alternates": []}
    if tier in ("B", "C"):
        return {"decision": "hold", "reason": f"unlabeled-tier-{tier}", "send": [], "alternates": []}
    return {"decision": "reject", "reason": f"auto:tier-{tier or '?'}", "send": [], "alternates": []}


def production_sendability(records: list) -> dict:
    """#718 — split a district's records by what production can ACTUALLY receive:

        {n_send, n_hold, n_benchmark_only, n_production_sendable, benchmark_only: [rec_key, ...]}

    `decide()` is deliberately untouched: a `gt://` curation artifact legitimately decides `send` —
    for a BENCHMARK dispatch. What was missing is the production question, and everywhere readiness
    was measured it went unasked, so an unsendable target counted as a dispatchable one. A district
    whose only targets are `gt://` therefore read as DONE-ENOUGH instead of BLOCKED — the inverse of
    the truth. Live: Baldwin `0100270` showed 12 A/B-tier targets, all `gt://`, and had produced zero
    production facts for 19 days; a dispatch-gap sweep reported it "clean".

    The dispatch-time walls (#618/#644 freeze guard) held throughout, so nothing wrong ever shipped —
    this is an ACCOUNTING defect, and the number an operator needs is `n_production_sendable`."""
    out = {"n_send": 0, "n_hold": 0, "n_benchmark_only": 0, "n_production_sendable": 0,
           "benchmark_only": []}
    for rec in records or []:
        d = decide(rec)["decision"]
        if d not in ("send", "hold"):
            continue
        out["n_send" if d == "send" else "n_hold"] += 1
        if BM.is_benchmark_url(rec.get("url")):
            out["n_benchmark_only"] += 1
            out["benchmark_only"].append(rec.get("rec_key"))
        else:
            out["n_production_sendable"] += 1
    return out


def build_doc(district: dict, records: list, fingerprints: dict) -> dict:
    """Assemble one district's filtered.json from its canonical records (pure). Every canonical
    record appears with its decision + reason (traceable); the council reads the send[] subset."""
    decided = []
    for rec in records:
        d = decide(rec)
        decided.append({
            "rec_key": rec["rec_key"], "url": rec.get("url"), "tier": rec.get("tier"),
            "category": rec.get("category"), "label": rec.get("label"),
            "emergent": bool(rec.get("is_emergent")), "intended_schools": rec.get("intended_schools") or [],
            "decision": d["decision"], "reason": d["reason"], "send": d["send"],
            "alternates": d["alternates"]})
    n_send = sum(1 for r in decided if r["decision"] == "send")
    n_hold = sum(1 for r in decided if r["decision"] == "hold")
    n_files = sum(len(r["send"]) for r in decided)
    return {
        "district_id": district["district_id"], "district_dir": district.get("district_dir"),
        "generated_at": _now(), "label": HONEST_LABEL, "fingerprints": fingerprints,
        "topology": district.get("labeled_topology"),
        "nces_denominator": district.get("nces_denominator"),
        "completeness": {"n_canonical": len(decided), "n_send": n_send,
                         "n_reject": len(decided) - n_send - n_hold, "n_hold": n_hold},
        "cost_estimate": {"n_records": n_send, "n_files": n_files,
                          "note": "council $ is finalized at Stage 6 dispatch (depends on the model set)"},
        "records": decided,
    }


# ----------------------------- DB readers (governance Postgres) -----------------------------
def load_district(session, district_id: str):
    d = session.execute(text(
        """SELECT d.district_id, d.name, d.state, d.district_dir, d.labeled_topology, d.nces_school_count,
                  t.nces_by_level_json
           FROM district d LEFT JOIN district_target t ON t.district_id = d.district_id
           WHERE d.district_id = :d"""), {"d": district_id}).mappings().first()
    if not d:
        return None
    return {"district_id": d["district_id"], "name": d["name"], "state": d["state"],
            "district_dir": d["district_dir"], "labeled_topology": d["labeled_topology"],
            "nces_denominator": {"total": d["nces_school_count"],
                                 "by_level": json.loads(d["nces_by_level_json"]) if d["nces_by_level_json"] else {}}}


_RECORD_COLS = ("""r.rec_key, r.url, r.tier, r.category_hypothesis, r.signals_json, r.is_emergent,
                   r.intended_schools_json, l.primary_label, l.facets_json""")
_REP_COLS = ("source", "filename", "file_kind", "n_chars", "n_times", "usable")


def _shape_record(r, reps) -> dict:
    """One record row + its rep rows → the release dict (the ONE shaping used by both loaders; #148)."""
    return {
        "rec_key": r["rec_key"], "url": r["url"], "tier": r["tier"],
        "category": r["category_hypothesis"], "signals": json.loads(r["signals_json"] or "{}"),
        "is_emergent": r["is_emergent"],
        "intended_schools": json.loads(r["intended_schools_json"] or "[]"),
        "label": r["primary_label"], "facets": json.loads(r["facets_json"] or "{}"),
        "reps": [{k: x[k] for k in _REP_COLS} for x in reps]}


def _reps_by_key(session, rec_keys: list) -> dict:
    """{rec_key: [rep, ...]} for the given records in ONE query (#148: replaces the per-record fetch)."""
    out: dict = {}
    if not rec_keys:
        return out
    for x in session.execute(text(
            f"SELECT rec_key, {', '.join(_REP_COLS)} FROM representation WHERE rec_key = ANY(:k)"),
            {"k": rec_keys}).mappings():
        out.setdefault(x["rec_key"], []).append(x)
    return out


def load_district_records(session, district_id: str) -> list:
    """The district's CANONICAL records (non-dup; cluster rep or singleton) with label, signals,
    facets, and representation rows — the population the release rule runs over."""
    recs = session.execute(text(
        f"""SELECT {_RECORD_COLS}
           FROM record r LEFT JOIN label l ON l.rec_key = r.rec_key
           WHERE r.district_id = :d AND {CANONICAL_RECORD_WHERE}
           ORDER BY r.tier, r.sort_score DESC"""), {"d": district_id}).mappings().all()
    reps = _reps_by_key(session, [r["rec_key"] for r in recs])
    return [_shape_record(r, reps.get(r["rec_key"], [])) for r in recs]


def load_districts_records(session, district_ids) -> dict:
    """{district_id: [record, ...]} for MANY districts in two queries — the bulk twin of
    load_district_records (#637: stage4_attribution called the per-district loader in a loop over
    the whole labeled TARGET corpus, an N+1 that grows with every labeled district). Same canonical
    filter + shaping; per-district record order preserved (tier, sort_score DESC)."""
    dids = list(district_ids)
    if not dids:
        return {}
    recs = session.execute(text(
        f"""SELECT r.district_id, {_RECORD_COLS}
           FROM record r LEFT JOIN label l ON l.rec_key = r.rec_key
           WHERE r.district_id = ANY(:d) AND {CANONICAL_RECORD_WHERE}
           ORDER BY r.district_id, r.tier, r.sort_score DESC"""), {"d": dids}).mappings().all()
    reps = _reps_by_key(session, [r["rec_key"] for r in recs])
    out: dict = {}
    for r in recs:
        out.setdefault(r["district_id"], []).append(_shape_record(r, reps.get(r["rec_key"], [])))
    return out


def load_records_by_key(session, rec_keys) -> list:
    """Like `load_district_records` but scoped to specific `rec_keys` — the 7->6 executor needs only
    the approved requests' target records, not the whole district (#148: it was loading ALL records +
    an N+1 rep query per record just to look up a handful). Two queries total, canonical-filtered."""
    keys = list(rec_keys)
    if not keys:
        return []
    recs = session.execute(text(
        f"""SELECT {_RECORD_COLS}
           FROM record r LEFT JOIN label l ON l.rec_key = r.rec_key
           WHERE r.rec_key = ANY(:k) AND {CANONICAL_RECORD_WHERE}"""), {"k": keys}).mappings().all()
    reps = _reps_by_key(session, [r["rec_key"] for r in recs])
    return [_shape_record(r, reps.get(r["rec_key"], [])) for r in recs]


def district_fingerprints(session, district_id: str) -> dict:
    """Per-district (config, labels, data) fingerprints (governance §6 staleness). config is the
    global config dir; labels/data are scoped to THIS district so a change elsewhere doesn't
    spuriously mark it stale."""
    cfg = "".join(sorted(f.read_text() for f in paths.CONFIG_DIR.glob("*.json"))) \
        if paths.CONFIG_DIR.exists() else ""
    labels = session.execute(text(
        """SELECT r.rec_key, l.primary_label, l.status, l.facets_json
           FROM record r JOIN label l ON l.rec_key = r.rec_key
           WHERE r.district_id = :d AND l.status != 'unlabeled' ORDER BY r.rec_key"""),
        {"d": district_id}).fetchall()
    data = session.execute(text(
        "SELECT rec_key, tier, category_hypothesis, signals_json FROM record "
        "WHERE district_id = :d ORDER BY rec_key"), {"d": district_id}).fetchall()
    return {"config": _h(cfg),
            "labels": _h("|".join("·".join(map(str, r)) for r in labels)),
            "data": _h("|".join("·".join(map(str, r)) for r in data))}


def generate(session, district_id: str = None, root=None) -> list:
    """Generate filtered.json for one district (district_id given) or all. Writes to each district's
    dir under `root`; returns a per-district summary. The console button / scheduler call this."""
    root = root or RAW_DIR
    if district_id:
        dids = [district_id]
    else:
        dids = [r[0] for r in session.execute(text("SELECT district_id FROM district ORDER BY district_id")).fetchall()]
    summary = []
    for did in dids:
        district = load_district(session, did)
        if not district:
            continue
        doc = build_doc(district, load_district_records(session, did), district_fingerprints(session, did))
        ddir = root / (district["district_dir"] or did)
        written = None
        if ddir.exists():
            # REQ-164: an always-stamped audit receipt via the shared writer (was a fixed filtered.json
            # overwritten in place). ddir is the DB-authoritative capture dir; nothing reads filtered.json
            # as pipeline input (Stage 6 reads the release projection from gov_db), so it's audit-only.
            # Basename follows the `stage<N>_<stage_name>` convention shared by every stage's receipt --
            # the stage number leads so a filesystem/name sort groups a district's receipts in pipeline
            # order (the unified naming decision, 2026-07-23).
            written = str(RCPT.write_receipt(did, district["name"], "stage5_filter", doc, ddir=ddir))
        summary.append({"district_id": did, "topology": doc["topology"],
                        "n_canonical": doc["completeness"]["n_canonical"],
                        "n_send": doc["completeness"]["n_send"], "written": written})
    return summary


def main():
    ap = argparse.ArgumentParser(description="Stage 5→6 release generator — filtered.json (REQ-094)")
    ap.add_argument("--district", default=None, help="one district_id (default: all)")
    a = ap.parse_args()
    with gdb.session_scope() as s:
        summary = generate(s, a.district)
    n_written = sum(1 for r in summary if r["written"])
    total_send = sum(r["n_send"] for r in summary)
    print(f"generated {n_written} filtered.json ({total_send} records to send across {len(summary)} districts)")
    for r in summary:
        flag = "" if r["written"] else "  (dir missing — not written)"
        print(f"  [{r['topology'] or '?':18}] {r['district_id']}: "
              f"{r['n_send']}/{r['n_canonical']} send{flag}")


if __name__ == "__main__":
    main()
