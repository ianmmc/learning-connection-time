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

RAW_DIR = Path("data/raw/lea-website-captures")
DB_PATH = Path("data/acquisition/stage5_review/review.db")

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*([AaPp])?\.?[Mm]?\.?")
USABLE_MIN_CHARS = 120
PROXIMITY_CHARS = 220          # two times within this many chars = a plausible start/end pair
WINDOW_LO, WINDOW_HI = 7 * 60, 16 * 60   # plausible school-day window (minutes since midnight)
AFTER_5PM = 17 * 60

POSITIVE_KW = ["bell schedule", "bell times", "school hours", "school day", "start time",
               "end time", "dismissal", "arrival", "first bell", "last bell", "homeroom",
               "period 1", "1st period", "drop-off", "drop off", "pick-up", "pick up"]
# Negative keyword classes (each maps to a likely non-target category).
NEG_BOARD = ["board of education", "board of trustees", "board meeting", "school board",
             "trustees", "agenda", "regular meeting", "work session"]
NEG_SPORTS = ["athletic", "athletics", "sports", "tournament", "varsity", "scrimmage",
              " vs ", " vs.", "game schedule", "booster"]
NEG_CALENDAR = ["academic calendar", "school calendar", "holiday", "early release",
                "early dismissal", "no school", "in-service", "in service", "first day of school",
                "last day of school", "winter break", "spring break"]
NEG_TRANSPORT = ["bus route", "bus schedule", "transportation department", "bus stop", "bus number"]
# Instructional-time declaration — ANCHORED so board-meeting "minutes" never false-positives.
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


# ----------------------------- signal computation -----------------------------
def compute_signals(record_dir: Path, texts: list, roster_norm: list, files: dict):
    """All deterministic, no AI. `texts` = processed.json texts[]; `files` = captures.json files{}."""
    # Gather text: best (max n_times, usable) for time density; union of usable reps for keywords.
    usable = [t for t in texts if t.get("usable") and t.get("text_file")]
    def read(t):
        try:
            return (record_dir / t["text_file"]).read_text(errors="replace")
        except Exception:
            return ""
    best = max(usable, key=lambda t: t.get("n_times", 0), default=None)
    best_text = read(best) if best else ""
    all_text = "\n".join(read(t) for t in usable)
    all_lc = all_text.lower()
    max_chars = max((t.get("n_chars", 0) for t in texts), default=0)

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

    return {
        "n_times": n_times, "n_times_in_window": len(in_window), "times_after_5pm": len(after5),
        "proximity_pairs": prox, "positive_kw": pos, "negative_kw": neg, "neg_total": neg_total,
        "instructional_time": instructional, "has_table": has_table, "period_hits": period_hits,
        "roster_school_names_hit": roster_hits, "visual_text_gap": visual_text_gap,
        "max_text_chars": max_chars, "pages": pages,
    }


def tier_and_category(sig: dict, roster_size: int):
    n, win, prox = sig["n_times"], sig["n_times_in_window"], sig["proximity_pairs"]
    pos, neg, instr = sig["positive_kw"], sig["negative_kw"], sig["instructional_time"]
    neg_total = sig["neg_total"]
    all_after5 = n > 0 and sig["times_after_5pm"] == n
    neg_dominant = neg_total >= 2 and neg_total > len(pos) and win <= 2

    # ---- likelihood tier (confident, sortable) ----
    if sig["max_text_chars"] < 40 and not sig["pages"]:
        tier = "D"
    elif n == 0:
        tier = "D"
    elif prox >= 1 and (pos or instr) and not neg_dominant and not all_after5:
        tier = "A"
    elif (neg_dominant or all_after5):
        tier = "C"
    elif win >= 2 or instr:
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
# label is the PRECIOUS human data: created once, NEVER dropped on re-ingest.
LABEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS label (
  rec_key TEXT PRIMARY KEY, primary_label TEXT, flags_json TEXT, note TEXT,
  status TEXT DEFAULT 'unlabeled', updated_at TEXT);
"""
# Regenerable tables: dropped + rebuilt every ingest so schema/signal changes always apply.
REBUILD_SCHEMA = """
DROP TABLE IF EXISTS district; DROP TABLE IF EXISTS record; DROP TABLE IF EXISTS representation;
CREATE TABLE district (
  district_id TEXT PRIMARY KEY, name TEXT, state TEXT, district_dir TEXT,
  batch_id TEXT, topology_hypothesis TEXT, n_records INTEGER);
CREATE TABLE record (
  rec_key TEXT PRIMARY KEY, district_id TEXT, district_dir TEXT, url TEXT, hash TEXT,
  kind TEXT, final_url TEXT, content_hash TEXT, duplicate_of TEXT,
  tier TEXT, sort_score REAL, category_hypothesis TEXT, signals_json TEXT);
CREATE TABLE representation (
  rec_key TEXT, source TEXT, filename TEXT, file_kind TEXT,
  n_chars INTEGER, n_times INTEGER, usable INTEGER);
"""

BIN_KINDS = {"png": "image", "pdf": "pdf", "bin": "binary"}


def ingest(root: Path, db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(LABEL_SCHEMA)      # ensure the precious table exists; never dropped
    con.executescript(REBUILD_SCHEMA)    # drop + rebuild the regenerable tables

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

        seen_content = {}   # content_hash -> canonical rec_key
        district_records = []
        for h, prec in processed.items():
            cap = caps.get(h, {})
            rec_key = f"{disc['district_id']}:{h}"
            rdir = ddir / "captures" / h
            files = cap.get("files") or {}

            sig = compute_signals(rdir, prec.get("texts", []), roster_norm, files)
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

            con.execute(
                "INSERT INTO record VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec_key, disc["district_id"], ddir.name, prec["url"], h, cap.get("kind"),
                 cap.get("final_url"), content_hash, dup_of, tier, score, cat, json.dumps(sig)))
            con.execute("INSERT OR IGNORE INTO label (rec_key) VALUES (?)", (rec_key,))

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
            district_records.append((rec_key, sig, tier, dup_of))

        # topology hypothesis (coarse, deterministic)
        non_dup = [(rk, s, tr) for rk, s, tr, d in district_records if not d]
        sched = [(rk, s) for rk, s, tr in non_dup if tr in ("A", "B")]
        max_roster_on_one = max((s["roster_school_names_hit"] for _, s in sched), default=0)
        if roster_size and max_roster_on_one >= max(2, roster_size * 0.5):
            topo = "hub"
        elif len(sched) >= 2:
            topo = "per_school"
        else:
            topo = "unknown"
        con.execute("INSERT INTO district VALUES (?,?,?,?,?,?,?)",
                    (disc["district_id"], disc.get("name"), disc.get("state"), ddir.name,
                     disc.get("batch_id"), topo, len(district_records)))

    con.commit()
    n_rec = con.execute("SELECT COUNT(*) FROM record").fetchone()[0]
    n_lab = con.execute("SELECT COUNT(*) FROM label WHERE status!='unlabeled'").fetchone()[0]
    n_dist = con.execute("SELECT COUNT(*) FROM district").fetchone()[0]
    by_tier = dict(con.execute("SELECT tier, COUNT(*) FROM record GROUP BY tier").fetchall())
    con.close()
    print(f"ingest done: {n_dist} districts, {n_rec} records, {n_lab} already-labeled preserved")
    print("by tier:", by_tier)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(RAW_DIR))
    ap.add_argument("--db", default=str(DB_PATH))
    a = ap.parse_args()
    ingest(Path(a.root), Path(a.db))


if __name__ == "__main__":
    main()
