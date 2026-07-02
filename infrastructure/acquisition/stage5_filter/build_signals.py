#!/usr/bin/env python3
"""Stage 5 review-app ingest + DETERMINISTIC signal computation (NO AI at runtime).

Walks data/raw/lea-website-captures/<district>/, reads Stage 3 (captures.json) + Stage 4
(processed.json), and for every ok record computes a vector of deterministic signals, a
likelihood TIER, a weak CATEGORY HYPOTHESIS, content-hash dedup, and a per-district topology
hypothesis. Writes to a SQLite DB that backs the review app.

This is the heart of the Stage 5 data-collection exercise: the script classifies/tiers, the
human supplies the ground-truth labels (a separate table), and labels are PRESERVED across
re-ingest so heuristics can be refined without losing hand-entered judgments. See
docs/technical-notes/STAGE5_FILTER_DESIGN_2026-06.md.

Usage:  python3 build_signals.py [--root data/raw/lea-website-captures] [--db <path>]
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import paths  # noqa: E402  (single source of truth for runtime-state locations — REQ-087)
from infrastructure.acquisition.common import config_loader  # noqa: E402  (Stage 5 keyword knobs — REQ-088/093)
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (isolated governance Postgres engine/session — REQ-103)
from infrastructure.acquisition.common import cache_ingest as CI  # noqa: E402  (shared cross-stage cache schema + UPSERTs — REQ-103c, now common/)
from infrastructure.acquisition.stage5_filter import models  # noqa: F401,E402  (registers PRECIOUS Label/ClusterSplit on gdb.Base)
from infrastructure.acquisition.stage5_filter import attention as AT  # noqa: E402  (the district-driven attention score)
from infrastructure.acquisition.stage5_filter import combiner as COMB  # noqa: E402  (V2 labeling-function combiner — REQ-113)

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
INSTRUCTIONAL_RE = re.compile(
    r"(\d{2,4})\s*(?:minutes|mins)\s+(?:of|per)\s+(?:instruction|instructional|class|learning)"
    r"|(?:instructional\s+minutes|minutes\s+per\s+day|minutes\s+of\s+instruction)", re.I)
PERIOD_RE = re.compile(r"\bperiod\s*\d|\b\d(?:st|nd|rd|th)\s+period", re.I)

# ---- V2 (REQ-113) content-shape signals ----
# Words that, near a time-range, mark it as an INTENTIONAL "hours" statement (vs. an incidental time).
HOURS_INTENT_KW = ["school hours", "school day", "hours of operation", "start time", "end time",
                   "dismissal", "arrival", "first bell", "last bell", "bell schedule", "school starts",
                   "school ends", "class begins", "classes begin", "doors open", "instructional day"]
# Hours that belong to the OFFICE/STAFF, not the student day (the research's #1 confusable, §5.2).
OFFICE_HOURS_KW = ["office hours", "office is open", "main office", "front office", "staff hours",
                   "staff day", "workday", "work day", "teacher hours", "building hours", "administrative"]
# A schedule that exists but is NOT the standard school day (weather/remote/delay-only variants).
NONSTANDARD_DAY_KW = ["remote learning", "e-learning", "elearning", "weather event", "2-hour delay",
                      "2 hour delay", "two hour delay", "early dismissal schedule", "delayed start",
                      "virtual day", "snow day", "inclement weather", "distance learning"]
# A heading-like occurrence of an hours-intent phrase (heading-proximity, research §2.2/§4.3).
HEADING_HOURS_RE = re.compile(
    r"(office hours|school hours|school day hours|hours of operation|bell schedule|school day|"
    r"daily schedule|arrival (?:and|&) dismissal|start and end times?)\b[:\-–—\s]*", re.I)
HEADING_PROX_CHARS = 140   # a time within this many chars AFTER an hours heading = a heading-hours hit
HANDBOOK_MAX_PAGES = 60    # per-page scan cap (was 15 — targets cited on pp.16-22 were structurally invisible)
# A CMS news/social-feed URL shape (the #1 tier-A pollutant — incidental post times). A DOWN-WEIGHT signal.
FEED_URL_RE = re.compile(r"/live-feed|/announcements?\b|/news(?:/|\?|$)|[?&]page_no=|/o/[^/]+/(?:live-feed|article/\d)", re.I)


def feed_url(url: str) -> bool:
    return bool(FEED_URL_RE.search(url or ""))


def cms_hint_of(cap: dict) -> str | None:
    """The Stage-3 cms_hint for a capture (REQ-115): promoted from the buried fingerprint into a record signal
    — a GROUPING key for per-detector accuracy, not a score input."""
    try:
        return (json.loads(cap.get("fingerprint_json") or "{}") or {}).get("cms_hint")
    except (json.JSONDecodeError, TypeError):
        return None


def embed_hosts_of(cap: dict) -> list:
    """Categorized iframe/embed host tags for a capture (REQ-115) — social/calendar/doc-viewer/other, from
    the Stage-3 fingerprint. Empty for pre-REQ-115 captures (the field isn't on disk yet); populated for
    future captures + used structurally by lf_news_feed / lf_calendar_widget."""
    try:
        fp = json.loads(cap.get("fingerprint_json") or "{}") or {}
    except (json.JSONDecodeError, TypeError):
        return []
    return list(fp.get("embed_hosts") or [])


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


def pdf_page_count(pdf: Path) -> int:
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30).stdout
        for line in out.splitlines():
            if line.startswith("Pages:"):
                return int(line.split()[1])
    except Exception:
        pass
    return 1


def pdf_page_text(pdf: Path, page: int) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
                               capture_output=True, text=True, timeout=30).stdout or ""
    except Exception:
        return ""


def norm_school(name: str) -> str:
    n = name.lower()
    for suf in ["elementary school", "middle school", "high school", "intermediate school",
                "elementary", "middle", "high", "school", "academy", "isd", "district"]:
        n = n.replace(suf, " ")
    return re.sub(r"[^a-z0-9 ]", " ", n).strip()


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


# ----------------------------- labeled topology -----------------------------
def derive_labeled_topology(primaries: list, nces_count) -> str:
    """primaries: primary_label strings for a district's labeled CANONICAL records (non-dup,
    cluster representatives). nces_count: distinct NCES regular schools, or None. One value.
    Precedence is deliberate and documented in STAGE5_FILTER_DESIGN_2026-06.md."""
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


def compute_signals(record_dir: Path, texts: list, roster_norm: list, files: dict, main_text: str = None):
    """All deterministic, no AI. `texts` = processed.json texts[]; `files` = captures.json files{}.
    `main_text` = the Stage-3 DE-CHROMED page (page.main.txt) when present (REQ-091): the time /
    keyword / roster signals are then computed over MAIN instead of the full page, so footer
    building-hours and school-switcher nav can't inject false signal. Graceful: a too-thin main
    falls back to the full text, so segmentation can never make things worse."""
    # Gather text: best (max n_times, usable) for time density; union of usable reps for keywords.
    usable = [t for t in texts if t.get("usable") and t.get("text_file")]
    def read(t):
        try:
            return (record_dir / t["text_file"]).read_text(errors="replace")
        except Exception:
            return ""
    best = max(usable, key=lambda t: t.get("n_times", 0), default=None)
    full_best = read(best) if best else ""
    full_all = "\n".join(read(t) for t in usable)
    max_chars = max((t.get("n_chars", 0) for t in texts), default=0)

    # De-chrome: KEYWORD/roster signals over MAIN when a usable page.main.txt segment exists (its measured
    # win: footer building-hours + school-switcher nav can't inject false CATEGORY signal). But TIME signals
    # use the MAX-EVIDENCE source (REQ-113 §2a-1): de-chrome must never *zero* a real school-hours time that
    # lives in the footer or survives only in an OCR/raster rep. So the time basis is whichever of {main,
    # full_best} carries more in-window times — never main exclusively.
    dechromed = bool(main_text and len(main_text.strip()) >= USABLE_MIN_CHARS)
    all_text = main_text if dechromed else full_all      # keyword/roster basis (de-chrome win preserved)
    all_lc = all_text.lower()
    candidates = [full_best] + ([main_text] if dechromed else [])
    best_text = max(candidates, key=lambda t: len(in_window_positions(t)), default="")  # time-signal basis

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
    instructional = bool(INSTRUCTIONAL_RE.search(all_text))
    # table time-DENSITY, not just a boolean: the in-window time count in the richest table rep + its period rows.
    table_reps = [read(t) for t in usable if t.get("source", "") in
                  ("pdfplumber_lines", "camelot_stream", "camelot_hybrid") and "---" in read(t)]
    table_time_density = max((len(in_window_positions(t)) for t in table_reps), default=0)
    table_period_rows = max((len(PERIOD_RE.findall(t)) for t in table_reps), default=0)
    has_table = bool(table_reps)
    period_hits = len(PERIOD_RE.findall(all_text))
    roster_hits = sum(1 for rn in roster_norm if rn and rn in all_lc)
    nonstandard_day = any(k in all_lc for k in NONSTANDARD_DAY_KW)

    # visual exists but text is thin -> possible missed content
    has_visual = bool(files.get("png") or (files.get("bin") and not files.get("txt"))) or "pdf" in files
    visual_text_gap = has_visual and max_chars < USABLE_MIN_CHARS

    # Per-page n_times for any PDF present (handbook-harvest signal).
    pages = []
    pdf_name = files.get("pdf") or (files.get("bin") if str(files.get("bin", "")).lower().endswith(".pdf") else None)
    if pdf_name:
        pdf = record_dir / pdf_name
        if pdf.exists():
            for p in range(1, min(pdf_page_count(pdf), HANDBOOK_MAX_PAGES) + 1):
                pages.append({"page": p, "n_times": len(time_positions(pdf_page_text(pdf, p)))})

    sig = {
        "n_times": n_times, "n_times_in_window": len(in_window), "times_after_5pm": len(after5),
        "proximity_pairs": prox, "positive_kw": pos, "negative_kw": neg, "neg_total": neg_total,
        "instructional_time": instructional, "has_table": has_table, "period_hits": period_hits,
        "roster_school_names_hit": roster_hits, "visual_text_gap": visual_text_gap,
        "max_text_chars": max_chars, "pages": pages,
        "is_handbook": is_handbook_doc(all_lc, files, len(pages), max_chars),
        "harvest_pages": harvest_schedule_pages(pages),
        "dechromed": dechromed,   # REQ-091: KEYWORD signals computed over MAIN (chrome removed)?
        # ---- V2 (REQ-113) ----
        "footer_hours": footer, "header_hours": header,
        "heading_hours_hits": headings["count"], "heading_hours_labels": headings["labels"],
        "table_time_density": table_time_density, "table_period_rows": table_period_rows,
        "nonstandard_day": nonstandard_day,
    }
    # Clustering dedups by WHOLE-page content, so it uses the full best text, not the de-chromed main.
    return sig, full_best


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


def export_labels(s, out: Path = LABELS_JSON) -> int:
    """Dump all non-unlabeled rows to a tracked JSON (atomic write). The label backup."""
    rows = s.execute(text(
        f"SELECT {','.join(LABEL_COLS)} FROM label WHERE status!='unlabeled' ORDER BY rec_key")).fetchall()
    data = [dict(zip(LABEL_COLS, r)) for r in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(out)   # atomic
    return len(data)


def export_splits(s, out: Path = CLUSTER_SPLITS_JSON) -> int:
    """Dump the precious cluster-split rec_keys to a tracked JSON (atomic). The split backup."""
    rows = [r[0] for r in s.execute(text("SELECT rec_key FROM cluster_split ORDER BY rec_key"))]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2))
    tmp.replace(out)
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
# DERIVED artifact home (issue #58): slices are ingest OUTPUT, so they live under data/acquisition/
# (regenerable), never under data/raw/ (write-once Stage-3 captures — Critical Rule 5). Pre-#58
# ingests wrote harvest_slice.txt next to the raw capture; resolve_harvest_slice() keeps those
# readable (read fallback to the old location; writes go ONLY to the new one).
HARVEST_SLICES_DIR = paths.HARVEST_SLICES_DIR


def harvest_slice_path(district_id: str, rec_key: str) -> Path:
    """The canonical WRITE location for one record's harvest slice:
    data/acquisition/harvest_slices/<district_id>/<rec_key with ':'→'_'>.txt"""
    return HARVEST_SLICES_DIR / str(district_id) / f"{rec_key.replace(':', '_')}.txt"


def resolve_harvest_slice(district_id: str, district_dir: str, rec_key: str) -> Path | None:
    """Where a record's harvest slice actually IS: the new derived-artifact location first, else the
    legacy pre-#58 location inside the raw capture dir (RAW_DIR/<district_dir>/captures/<hash>/
    harvest_slice.txt). Returns None when neither exists. Consumers materializing a rep whose
    source == 'harvest_slice' should call this instead of joining the capture dir themselves."""
    new = harvest_slice_path(district_id, rec_key)
    if new.exists():
        return new
    rec_hash = rec_key.split(":", 1)[-1]
    legacy = RAW_DIR / district_dir / "captures" / rec_hash / HARVEST_SLICE_FILE
    return legacy if legacy.exists() else None


def build_harvest_slice(harvest_pages: list, page_text_fn):
    """Q2.1 (Ian 2026-06-30): materialize the high-signal HARVEST PAGES of a long doc (a handbook, or a
    big district-hub listing) as a small standalone text slice, so Stage 6 dispatches just those ~1-4
    pages — not the whole 60-100-page PDF (cost containment; the paid council reads the slice, and the
    measured cost model prices the slice's tokens). `page_text_fn(page)->str` extracts one page's text.
    Returns `(slice_text, rep_kwargs)` ready for INSERT_REP, or None when nothing usable extracts."""
    slice_text = "\n\n".join((page_text_fn(p) or "") for p in (harvest_pages or []))
    if not slice_text.strip():
        return None
    return slice_text, {"source": HARVEST_SLICE_SOURCE, "filename": HARVEST_SLICE_FILE,
                        "file_kind": "text", "n_chars": len(slice_text),
                        "n_times": len(time_positions(slice_text)), "usable": 1}


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
    # Dedup + drop short stems: schools sharing the district name ("Marion High"/"Marion
    # Middle" both -> "marion") must not over-count roster hits (would false-positive hub).
    roster_norm = sorted({rn for sc in disc.get("schools", [])
                          if len(rn := norm_school(sc.get("school", ""))) >= 4})
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
    for h, prec in processed.items():
        cap = caps.get(h, {})
        rec_key = f"{did}:{h}"
        rdir = ddir / "captures" / h
        files = cap.get("files") or {}

        # De-chrome (REQ-091): if a Stage-3 page.main.txt segment exists, signals compute over it.
        mp = rdir / "page.main.txt"
        main_text = mp.read_text(errors="replace") if mp.exists() else None
        sig, best_text = compute_signals(rdir, prec.get("texts", []), roster_norm, files, main_text)
        # V2 (REQ-113): record-level signals the text scan can't see, then the labeling-function combiner.
        sig["cms_hint"] = cms_hint_of(cap)
        sig["url_feed_pattern"] = feed_url(prec["url"]) or feed_url(cap.get("final_url") or "")
        sig["embed_hosts"] = embed_hosts_of(cap)
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
        # Q2.1: for a handbook (or any record carrying harvest_pages), materialize just those high-signal
        # pages as a small `harvest_slice.txt` text rep — so Stage 6 dispatches the slice, not the whole PDF.
        hp = sig.get("harvest_pages") or []
        if sig.get("is_handbook") and hp:
            pdf_name = files.get("pdf") or (files.get("bin")
                       if str(files.get("bin", "")).lower().endswith(".pdf") else None)
            pdf = rdir / pdf_name if pdf_name else None
            if pdf and pdf.exists():
                built = build_harvest_slice(hp, lambda p: pdf_page_text(pdf, p))
                if built:
                    slice_text, rep_kwargs = built
                    # write to the DERIVED-artifact home, never into the raw capture dir (issue #58)
                    sp = harvest_slice_path(did, rec_key)
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
        sess.execute(text("UPDATE record SET cluster_id=:cid, is_cluster_rep=:rep, "
                          "cluster_size=:sz WHERE rec_key=:rk"),
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
    if regenerate_filtered and ingested:
        n_written, n_send = _regenerate_filtered(sorted(set(ingested)))
    summary = {"districts": sorted(set(ingested)), "n_districts": len(set(ingested)),
               "n_records": n_rec, "n_filtered_written": n_written, "n_send": n_send}
    print(f"ingest_batch: {summary['n_districts']} districts, {n_rec} records re-ingested; "
          f"filtered.json regenerated for {n_written} ({n_send} records to send)")
    return summary


def ingest(root: Path):
    """FULL ingest into the isolated governance Postgres DB (REQ-103): drop + rebuild every derived
    signal table over EVERY Stage-4-complete district on disk. The PRECIOUS tables are created from the
    models (never dropped); the whole pass is one transaction (atomic re-ingest). For the incremental,
    batch-scoped path the Stage-4 console uses, see ingest_batch()."""
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
    print(f"ingest done: {n_dist} districts, {n_rec} records, {n_lab} labeled "
          f"({restored} restored from labels.json), {exported} exported to labels.json")
    print(f"clustering: {n_clustered} records in {n_clusters} clusters; {exported_splits} splits backed up")
    print(f"stage-1/2 ingest: {n_targeted} districts with batch targeting; {n_emergent} emergent records (captured, not a candidate)")
    print(f"cross-stage cache: {cache['discovery_school']} discovery_school, {cache['candidate']} candidate, "
          f"{cache['capture']} capture, {cache['processed_doc']} processed_doc rows")
    print("by tier:", by_tier)
    print("labeled_topology:", by_topo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(RAW_DIR))
    ap.add_argument("--no-release", action="store_true",
                    help="skip regenerating filtered.json after ingest")
    a = ap.parse_args()
    ingest(Path(a.root))
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
