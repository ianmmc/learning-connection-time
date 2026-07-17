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

from infrastructure.acquisition.common import paths  # noqa: E402
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (governance Postgres — REQ-103)
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


def best_send(reps: list, signals: dict, facets: dict) -> list:
    """The ONE best representation for the council to read (governance §4). reps: the record's
    representation rows ({source, filename, file_kind, n_chars, n_times, usable}). Returns a list
    of send entries (usually one): handbook → the PDF + harvest pages; image when text never
    captured the content (visual_text_gap / the human needs_vision facet, REQ-114 Axis 3);
    else the densest text."""
    facets = facets or {}
    signals = signals or {}
    # the harvest slice is a purpose-built handbook rep — never a general "densest text" candidate
    usable_text = [r for r in reps if r.get("file_kind") == "text" and r.get("usable") and r.get("filename")
                   and r.get("source") != "harvest_slice"]
    images = [r for r in reps if r.get("file_kind") == "image" and r.get("filename")]
    pdfs = [r for r in reps if r.get("file_kind") == "pdf" and r.get("filename")]
    harvest = signals.get("harvest_pages") or []
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
    if signals.get("is_handbook") and slice_rep:
        best_text_times = (best_text.get("n_times") or 0) if best_text else 0
        if (slice_rep.get("n_times") or 0) >= best_text_times:
            return [{"file": slice_rep["filename"], "kind": "text", "pages": harvest}]
        # a denser general text rep exists — fall through to the densest-text pick below
    # the PDF+pages fallback is ONLY for a handbook whose slice wasn't materialized (older ingests) —
    # gated on `not slice_rep`, or it would intercept the yield fall-through above and re-waste the
    # round on the whole PDF (adversarial review of the #230 fix caught exactly that).
    if signals.get("is_handbook") and not slice_rep and harvest and pdfs:
        return [{"file": pdfs[0]["filename"], "kind": "pdf", "pages": harvest}]
    if (facets.get("needs_vision") == "yes" or signals.get("visual_text_gap")) and images:
        return [{"file": _best_image(images)["filename"], "kind": "image"}]
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


def alternates(reps: list, exclude: set) -> list:
    """The record's OTHER usable candidate representations (beyond the winner) — usable text reps +
    images + pdfs, distinct by filename — that a reviewer could swap to at gate@6 (REQ-094 follow-up,
    governance §11g). Only target-flagged records get alternates (the record is the target unit)."""
    out, seen = [], set(exclude)
    for r in reps:
        fn = r.get("filename")
        if not fn or fn in seen:
            continue
        if (r.get("source") or "") in CHROME_SOURCES:   # quarantined chrome, not a schedule rep
            continue
        fk = r.get("file_kind")
        if fk == "text" and not r.get("usable"):
            continue
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
            out = ddir / "filtered.json"
            tmp = out.with_name("filtered.json.tmp")
            tmp.write_text(json.dumps(doc, indent=2))
            tmp.replace(out)   # atomic; regenerable (overwritten each run)
            written = str(out)
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
