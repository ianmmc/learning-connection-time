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
import sqlite3
import subprocess
from pathlib import Path

from infrastructure.acquisition.common import paths  # noqa: E402  (single source of truth for runtime-state locations — REQ-087)
from infrastructure.acquisition.common import config_loader  # noqa: E402  (Stage 5 keyword knobs — REQ-088/093)

RAW_DIR = paths.RAW_CAPTURES
QUEUE_DIR = paths.QUEUE_DIR                   # Stage 1 batch_*.json (targeting + NCES denominator)
DB_PATH = paths.REVIEW_DB
# Durable, version-controlled source of truth for the PRECIOUS human labels. The DB is a
# regenerable cache; this JSON is what survives DB loss and lives in git (gitignore re-includes
# it). Written on every label save (server) + at the end of each ingest; re-imported on ingest.
LABELS_JSON = paths.LABELS_JSON
LABEL_COLS = ["rec_key", "primary_label", "flags_json", "note", "status", "updated_at"]
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
TARGET_LABELS = {"school_bell_schedule", "school_start_end_prose", "district_hub_schedule",
                 "explicit_instructional_time", "nonstandard_format"}
SCHOOL_LEVEL_LABELS = {"school_bell_schedule", "school_start_end_prose"}

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


def load_candidates(ddir: Path) -> dict:
    """url -> {'schools': [...], 'tools': [...]} from a district's candidates.json (the Stage 2
    D_FLATTEN capture plan, carrying the URL->school map). {} if absent/unreadable. Records whose
    URL is NOT a key here were captured but never planned -> emergent (discovered mid-capture)."""
    cf = ddir / "candidates.json"
    if not cf.exists():
        return {}
    try:
        doc = json.loads(cf.read_text())
    except Exception:
        return {}
    return {c["url"]: {"schools": c.get("schools", []), "tools": c.get("tools", [])}
            for c in doc.get("candidates", []) if c.get("url")}


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
    has_hub = "district_hub_schedule" in targets
    school_level = [p for p in targets if p in SCHOOL_LEVEL_LABELS]
    if has_hub and school_level:
        return "mixed"
    if has_hub:
        return "district_hub"
    # exact, narrow incomplete_coverage criterion (user, 2026-06-25)
    if len(targets) == 1 and targets[0] == "school_bell_schedule" and nces_count and nces_count > 1:
        return "incomplete_coverage"
    if school_level:
        return "per_school"
    return "unknown"


def recompute_labeled_topology(con, district_id: str) -> str:
    """Recompute + persist district.labeled_topology from the live labels. Cheap (no NCES read —
    nces_school_count is stored on the district at ingest). Called at ingest and on every save."""
    row = con.execute("SELECT nces_school_count FROM district WHERE district_id=?", (district_id,)).fetchone()
    nces_count = row[0] if row else None
    primaries = [r[0] for r in con.execute(
        """SELECT l.primary_label FROM record r JOIN label l ON l.rec_key=r.rec_key
           WHERE r.district_id=? AND r.duplicate_of IS NULL
             AND (r.is_cluster_rep=1 OR r.cluster_id IS NULL)
             AND l.status!='unlabeled' AND l.primary_label IS NOT NULL""", (district_id,))]
    topo = derive_labeled_topology(primaries, nces_count)
    con.execute("UPDATE district SET labeled_topology=? WHERE district_id=?", (topo, district_id))
    return topo


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

    # De-chrome: signals over MAIN when a usable page.main.txt segment exists, else the full page.
    dechromed = bool(main_text and len(main_text.strip()) >= USABLE_MIN_CHARS)
    best_text = main_text if dechromed else full_best   # time-signal basis
    all_text = main_text if dechromed else full_all      # keyword/roster basis
    all_lc = all_text.lower()

    # Time signals (on the richest single representation).
    tps = time_positions(best_text)
    n_times = len(tps)
    in_window = [m for _, m in tps if WINDOW_LO <= m <= WINDOW_HI]
    after5 = [m for _, m in tps if m >= AFTER_5PM]
    # proximity pairs: distinct times within PROXIMITY_CHARS, both in window
    prox = 0
    for i in range(len(tps)):
        for j in range(i + 1, len(tps)):
            if tps[j][0] - tps[i][0] > PROXIMITY_CHARS:
                break
            if tps[i][1] != tps[j][1] and WINDOW_LO <= tps[i][1] <= WINDOW_HI and WINDOW_LO <= tps[j][1] <= WINDOW_HI:
                prox += 1

    pos = keyword_hits(all_lc, POSITIVE_KW)
    neg = {"board": keyword_hits(all_lc, NEG_BOARD), "sports": keyword_hits(all_lc, NEG_SPORTS),
           "calendar": keyword_hits(all_lc, NEG_CALENDAR), "transport": keyword_hits(all_lc, NEG_TRANSPORT)}
    neg_total = sum(len(v) for v in neg.values())
    instructional = bool(INSTRUCTIONAL_RE.search(all_text))
    has_table = any(t.get("source", "") in ("pdfplumber_lines", "camelot_stream", "camelot_hybrid")
                    and t.get("usable") and "---" in read(t) for t in usable)
    period_hits = len(PERIOD_RE.findall(all_text))
    roster_hits = sum(1 for rn in roster_norm if rn and rn in all_lc)

    # visual exists but text is thin -> possible missed content
    has_visual = bool(files.get("png") or (files.get("bin") and not files.get("txt"))) or "pdf" in files
    visual_text_gap = has_visual and max_chars < USABLE_MIN_CHARS

    # Per-page n_times for any PDF present (handbook-harvest signal).
    pages = []
    pdf_name = files.get("pdf") or (files.get("bin") if str(files.get("bin", "")).lower().endswith(".pdf") else None)
    if pdf_name:
        pdf = record_dir / pdf_name
        if pdf.exists():
            for p in range(1, min(pdf_page_count(pdf), 15) + 1):
                pages.append({"page": p, "n_times": len(time_positions(pdf_page_text(pdf, p)))})

    sig = {
        "n_times": n_times, "n_times_in_window": len(in_window), "times_after_5pm": len(after5),
        "proximity_pairs": prox, "positive_kw": pos, "negative_kw": neg, "neg_total": neg_total,
        "instructional_time": instructional, "has_table": has_table, "period_hits": period_hits,
        "roster_school_names_hit": roster_hits, "visual_text_gap": visual_text_gap,
        "max_text_chars": max_chars, "pages": pages,
        "is_handbook": is_handbook_doc(all_lc, files, len(pages), max_chars),
        "harvest_pages": harvest_schedule_pages(pages),
        "dechromed": dechromed,   # REQ-091: signals computed over MAIN (chrome removed)?
    }
    # Clustering dedups by WHOLE-page content, so it uses the full best text, not the de-chromed main.
    return sig, full_best


# Tier-decision thresholds, extracted as a tunable params dict (REQ-096). Defaults reproduce the
# original hardcoded behavior EXACTLY — the frontier/grid search varies these over the stored
# signals (no re-ingest) to find the recall-constrained precision optimum. NOT yet config-as-data
# knobs: they live here next to the logic until the frontier search settles them; promotion to
# config/ comes after. (Score weights below are a separate, later optimization.)
DEFAULT_TIER_PARAMS = {
    "min_chars_d": 40,       # below this many chars AND no pages -> tier D (unusable)
    "neg_dom_min": 2,        # neg_total >= this (and > #positives, and win <= win_max) -> neg-dominant
    "neg_dom_win_max": 2,    # neg-dominant only when in-window times are this few
    "prox_min_a": 1,         # proximity pairs >= this (+ a positive/instr signal) -> tier A
    "win_min_b": 2,          # in-window times >= this -> tier B (the fallthrough plausible case)
}


def tier_and_category(sig: dict, roster_size: int, params: dict = None):
    p = params or DEFAULT_TIER_PARAMS
    n, win, prox = sig["n_times"], sig["n_times_in_window"], sig["proximity_pairs"]
    pos, neg, instr = sig["positive_kw"], sig["negative_kw"], sig["instructional_time"]
    neg_total = sig["neg_total"]
    all_after5 = n > 0 and sig["times_after_5pm"] == n
    neg_dominant = neg_total >= p["neg_dom_min"] and neg_total > len(pos) and win <= p["neg_dom_win_max"]

    # ---- likelihood tier (confident, sortable) ----
    if sig["max_text_chars"] < p["min_chars_d"] and not sig["pages"]:
        tier = "D"
    elif prox >= p["prox_min_a"] and (pos or instr) and not neg_dominant and not all_after5:
        tier = "A"
    elif instr and not all_after5:
        # An explicit instructional-time declaration (minutes OR hours) is a target signal even with
        # no clock-time pair and even amid calendar/board keywords -> rescue to B, never hard-drop
        # (REQ-093: DUNSEITH buries "7.5 hrs/day" in an academic calendar). Checked before the n==0
        # and neg_dominant drops; the strong-target A branch above still wins when it qualifies.
        tier = "B"
    elif n == 0:
        tier = "D"
    elif (neg_dominant or all_after5):
        tier = "C"
    elif win >= p["win_min_b"]:
        tier = "B"
    else:
        tier = "C"
    score = (prox * 10) + win * 2 + len(pos) * 3 + (25 if instr else 0) - neg_total * 4 - (15 if all_after5 else 0)

    # ---- weak category hypothesis (HIDDEN in UI until the human labels) ----
    nb = {k: len(v) for k, v in neg.items()}
    if sig["max_text_chars"] < 40:
        cat = "unusable"
    elif instr:
        cat = "explicit_instructional_time"
    elif nb["board"] >= 1 and nb["board"] >= max(nb["sports"], nb["calendar"]):
        cat = "board_schedule"
    elif nb["sports"] >= 1 and nb["sports"] >= max(nb["board"], nb["calendar"]):
        cat = "sports_schedule"
    elif nb["calendar"] >= 2:
        cat = "academic_calendar"
    elif nb["transport"] >= 1 and win >= 1:
        cat = "transportation_schedule"
    elif roster_size and sig["roster_school_names_hit"] >= 3 and sig["has_table"]:
        cat = "district_hub_schedule"
    elif sig["period_hits"] >= 2 or (sig["has_table"] and win >= 2):
        cat = "school_bell_schedule"
    elif 2 <= win <= 6 and any(k in pos for k in ("start time", "end time", "dismissal", "arrival", "school hours")):
        cat = "school_start_end_prose"
    elif win >= 1 or instr:
        cat = "nonstandard_format"
    else:
        cat = "none"
    return tier, score, cat


# ----------------------------- DB -----------------------------
# PRECIOUS human data: created once, NEVER dropped on re-ingest. label = the ground-truth
# labels; cluster_split = records the reviewer pulled out of an auto-cluster (a durable override).
LABEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS label (
  rec_key TEXT PRIMARY KEY, primary_label TEXT, flags_json TEXT, note TEXT,
  status TEXT DEFAULT 'unlabeled', updated_at TEXT);
CREATE TABLE IF NOT EXISTS cluster_split (
  rec_key TEXT PRIMARY KEY, created_at TEXT);
"""
# Regenerable tables: dropped + rebuilt every ingest so schema/signal changes always apply.
REBUILD_SCHEMA = """
DROP TABLE IF EXISTS district; DROP TABLE IF EXISTS record; DROP TABLE IF EXISTS representation;
DROP TABLE IF EXISTS district_target;
CREATE TABLE district (
  district_id TEXT PRIMARY KEY, name TEXT, state TEXT, district_dir TEXT,
  batch_id TEXT, guessed_topology TEXT, labeled_topology TEXT, nces_school_count INTEGER,
  n_records INTEGER);
CREATE TABLE record (
  rec_key TEXT PRIMARY KEY, district_id TEXT, district_dir TEXT, url TEXT, hash TEXT,
  kind TEXT, final_url TEXT, content_hash TEXT, duplicate_of TEXT,
  tier TEXT, sort_score REAL, category_hypothesis TEXT, signals_json TEXT,
  cluster_id TEXT, is_cluster_rep INTEGER, cluster_size INTEGER,
  intended_schools_json TEXT, candidate_tools_json TEXT, is_emergent INTEGER);
CREATE TABLE representation (
  rec_key TEXT, source TEXT, filename TEXT, file_kind TEXT,
  n_chars INTEGER, n_times INTEGER, usable INTEGER);
-- Stage 1 targeting provenance (the funnel's "targeted" end + the NCES denominator). One row
-- per district when a batch_*.json entry exists; the topology denominator (nces_total) prefers
-- this over the live CSV. Regenerable.
CREATE TABLE district_target (
  district_id TEXT PRIMARY KEY, batch_id TEXT, nces_year TEXT, nces_total INTEGER,
  nces_by_level_json TEXT, enrollment_k12 INTEGER, lea_claimed_bands_json TEXT,
  schools_by_band_json TEXT);
"""

BIN_KINDS = {"png": "image", "pdf": "pdf", "bin": "binary"}


def export_labels(con, out: Path = LABELS_JSON) -> int:
    """Dump all non-unlabeled rows to a tracked JSON (atomic write). The label backup."""
    rows = con.execute(
        f"SELECT {','.join(LABEL_COLS)} FROM label WHERE status!='unlabeled' ORDER BY rec_key").fetchall()
    data = [dict(zip(LABEL_COLS, r)) for r in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(out)   # atomic
    return len(data)


def export_splits(con, out: Path = CLUSTER_SPLITS_JSON) -> int:
    """Dump the precious cluster-split rec_keys to a tracked JSON (atomic). The split backup."""
    rows = [r[0] for r in con.execute("SELECT rec_key FROM cluster_split ORDER BY rec_key")]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2))
    tmp.replace(out)
    return len(rows)


def import_splits(con, src: Path = CLUSTER_SPLITS_JSON) -> int:
    """Restore cluster splits from JSON into the table (recovery path after a DB wipe; a no-op
    on normal re-ingest since cluster_split is never dropped). Must run BEFORE clustering so the
    overrides are honored when components are recomputed."""
    if not src.exists():
        return 0
    n = 0
    for rk in json.loads(src.read_text()):
        con.execute("INSERT OR IGNORE INTO cluster_split (rec_key, created_at) VALUES (?, NULL)", (rk,))
        n += 1
    return n


def import_labels(con, src: Path = LABELS_JSON) -> int:
    """Restore labels from the JSON into the DB -- but ONLY for records the DB currently has
    as unlabeled, so a stale export can never clobber a live DB label. This restores labels
    after a DB wipe/rebuild; on a normal re-ingest (label table preserved) it's a no-op."""
    if not src.exists():
        return 0
    n = 0
    for d in json.loads(src.read_text()):
        cur = con.execute("SELECT status FROM label WHERE rec_key=?", (d["rec_key"],)).fetchone()
        if not cur or cur[0] != "unlabeled":
            continue
        con.execute("UPDATE label SET primary_label=?, flags_json=?, note=?, status=?, updated_at=? WHERE rec_key=?",
                    (d.get("primary_label"), d.get("flags_json"), d.get("note"),
                     d.get("status", "labeled"), d.get("updated_at"), d["rec_key"]))
        n += 1
    return n


def ingest(root: Path, db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(LABEL_SCHEMA)      # ensure the precious tables exist; never dropped
    con.executescript(REBUILD_SCHEMA)    # drop + rebuild the regenerable tables
    import_splits(con)                   # restore cluster splits to the table if it was wiped
    splits = {r[0] for r in con.execute("SELECT rec_key FROM cluster_split")}
    batches = load_batches()             # did -> Stage-1 targeting entry (preferred NCES denominator)
    nces = nces_school_counts()          # did -> distinct regular-school count (live CSV FALLBACK)

    for ddir in sorted(p for p in root.iterdir() if p.is_dir()):
        cj, pj, dj = ddir / "captures.json", ddir / "processed.json", ddir / "discovery.json"
        if not (cj.exists() and pj.exists() and dj.exists()):
            continue
        disc = json.loads(dj.read_text())
        # Dedup + drop short stems: schools sharing the district name ("Marion High"/"Marion
        # Middle" both -> "marion") must not over-count roster hits (would false-positive hub).
        roster_norm = sorted({rn for s in disc.get("schools", [])
                              if len(rn := norm_school(s.get("school", ""))) >= 4})
        roster_size = len(roster_norm)
        caps = {r["hash"]: r for r in json.loads(cj.read_text())}
        processed = {r["hash"]: r for r in json.loads(pj.read_text())}
        cand_map = load_candidates(ddir)   # url -> {schools, tools}; misses = emergent

        seen_content = {}   # content_hash -> canonical rec_key
        district_records = []
        cluster_items = []  # (rec_key, shingle_set, tier, sort_score) for near-dup clustering
        for h, prec in processed.items():
            cap = caps.get(h, {})
            rec_key = f"{disc['district_id']}:{h}"
            rdir = ddir / "captures" / h
            files = cap.get("files") or {}

            # De-chrome (REQ-091): if a Stage-3 page.main.txt segment exists, signals compute over it.
            mp = rdir / "page.main.txt"
            main_text = mp.read_text(errors="replace") if mp.exists() else None
            sig, best_text = compute_signals(rdir, prec.get("texts", []), roster_norm, files, main_text)
            tier, score, cat = tier_and_category(sig, roster_size)

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

            con.execute(
                """INSERT INTO record (rec_key, district_id, district_dir, url, hash, kind,
                     final_url, content_hash, duplicate_of, tier, sort_score, category_hypothesis,
                     signals_json, intended_schools_json, candidate_tools_json, is_emergent)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec_key, disc["district_id"], ddir.name, prec["url"], h, cap.get("kind"),
                 cap.get("final_url"), content_hash, dup_of, tier, score, cat, json.dumps(sig),
                 json.dumps(intended_schools), json.dumps(cand_tools), is_emergent))
            con.execute("INSERT OR IGNORE INTO label (rec_key) VALUES (?)", (rec_key,))
            cluster_items.append((rec_key, shingles(best_text), tier, score))

            # representations: text reps (from processed.json) + binaries on disk
            for t in prec.get("texts", []):
                con.execute("INSERT INTO representation VALUES (?,?,?,?,?,?,?)",
                            (rec_key, t["source"], t.get("text_file"), "text",
                             t.get("n_chars", 0), t.get("n_times", 0), int(bool(t.get("usable")))))
            for key, fname in files.items():
                fk = BIN_KINDS.get(key)
                if not fk:
                    continue
                if str(fname).lower().endswith(".pdf"):
                    fk = "pdf"
                elif str(fname).lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp", "gif"):
                    fk = "image"
                con.execute("INSERT INTO representation VALUES (?,?,?,?,?,?,?)",
                            (rec_key, f"capture:{key}", fname, fk, None, None, 1))
            # rasterized pages (Stage 4) as image reps for visual inspection
            for rp in sorted(rdir.glob("raster_p*.png")):
                con.execute("INSERT INTO representation VALUES (?,?,?,?,?,?,?)",
                            (rec_key, "raster", rp.name, "image", None, None, 1))
            # Stage-3 DOM segments (REQ-091) as inspectable text reps when present: main (de-chromed
            # body, what signals run on) + the quarantined chrome (header/footer/nav, screened separately).
            for seg in ("page.main.txt", "page.header.txt", "page.footer.txt", "page.nav.txt"):
                sp = rdir / seg
                if sp.exists():
                    con.execute("INSERT INTO representation VALUES (?,?,?,?,?,?,?)",
                                (rec_key, f"segment:{seg.split('.')[1]}", seg, "text",
                                 len(sp.read_text(errors='replace')), None, 1))
            district_records.append((rec_key, sig, tier, dup_of))

        # near-duplicate clustering (content-similarity; honors human splits) -> UPDATE records
        for rk, (cid, is_rep, size) in cluster_district(cluster_items, splits).items():
            con.execute("UPDATE record SET cluster_id=?, is_cluster_rep=?, cluster_size=? WHERE rec_key=?",
                        (cid, is_rep, size, rk))

        # guessed topology (coarse, deterministic, from SIGNALS — noisy; kept to measure the heuristic)
        non_dup = [(rk, s, tr) for rk, s, tr, d in district_records if not d]
        sched = [(rk, s) for rk, s, tr in non_dup if tr in ("A", "B")]
        max_roster_on_one = max((s["roster_school_names_hit"] for _, s in sched), default=0)
        if roster_size and max_roster_on_one >= max(2, roster_size * 0.5):
            topo = "hub"
        elif len(sched) >= 2:
            topo = "per_school"
        else:
            topo = "unknown"
        # NCES denominator: PREFER the Stage-1 batch (captured at queue time, with provenance);
        # fall back to the live CSV count when no batch entry exists for this district.
        did7 = str(disc["district_id"]).zfill(7)
        bt = batches.get(did7)
        nces_counts = (bt or {}).get("nces_school_counts") or {}
        nces_total = nces_counts.get("total", nces.get(did7))
        con.execute(
            """INSERT INTO district (district_id, name, state, district_dir, batch_id,
                 guessed_topology, labeled_topology, nces_school_count, n_records)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (disc["district_id"], disc.get("name"), disc.get("state"), ddir.name,
             disc.get("batch_id"), topo, None, nces_total, len(district_records)))
        if bt:
            con.execute(
                """INSERT INTO district_target (district_id, batch_id, nces_year, nces_total,
                     nces_by_level_json, enrollment_k12, lea_claimed_bands_json, schools_by_band_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (disc["district_id"], bt.get("_batch_id"), bt.get("_nces_year"),
                 nces_counts.get("total"), json.dumps(nces_counts.get("by_level", {})),
                 bt.get("enrollment_k12"), json.dumps(bt.get("lea_claimed_bands", [])),
                 json.dumps(bt.get("schools_by_band", {}))))

    # Restore any labels the DB is missing from the JSON source of truth (no-op on a normal
    # re-ingest where the label table was preserved; the recovery path after a DB wipe).
    restored = import_labels(con)
    # labeled_topology is derived from the (now-restored) human labels + the stored NCES count.
    for (did,) in con.execute("SELECT district_id FROM district").fetchall():
        recompute_labeled_topology(con, did)
    con.commit()
    n_rec = con.execute("SELECT COUNT(*) FROM record").fetchone()[0]
    n_lab = con.execute("SELECT COUNT(*) FROM label WHERE status!='unlabeled'").fetchone()[0]
    n_dist = con.execute("SELECT COUNT(*) FROM district").fetchone()[0]
    by_tier = dict(con.execute("SELECT tier, COUNT(*) FROM record GROUP BY tier").fetchall())
    n_clustered = con.execute("SELECT COUNT(*) FROM record WHERE cluster_id IS NOT NULL").fetchone()[0]
    n_clusters = con.execute("SELECT COUNT(DISTINCT cluster_id) FROM record WHERE cluster_id IS NOT NULL").fetchone()[0]
    by_topo = dict(con.execute("SELECT labeled_topology, COUNT(*) FROM district GROUP BY labeled_topology").fetchall())
    n_targeted = con.execute("SELECT COUNT(*) FROM district_target").fetchone()[0]
    n_emergent = con.execute("SELECT COUNT(*) FROM record WHERE is_emergent=1").fetchone()[0]
    exported = export_labels(con)        # keep the JSON backups in sync with the DB
    exported_splits = export_splits(con)
    con.close()
    print(f"ingest done: {n_dist} districts, {n_rec} records, {n_lab} labeled "
          f"({restored} restored from labels.json), {exported} exported to labels.json")
    print(f"clustering: {n_clustered} records in {n_clusters} clusters; {exported_splits} splits backed up")
    print(f"stage-1/2 ingest: {n_targeted} districts with batch targeting; {n_emergent} emergent records (captured, not a candidate)")
    print("by tier:", by_tier)
    print("labeled_topology:", by_topo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(RAW_DIR))
    ap.add_argument("--db", default=str(DB_PATH))
    a = ap.parse_args()
    ingest(Path(a.root), Path(a.db))


if __name__ == "__main__":
    main()
