"""Stage 8 — the "closing argument": assemble one district's per-band determination into a
reviewable + freezable evidence package (STAGE8_AGGREGATE_DESIGN_2026-06 §2).

The metaphor (Ian, 2026-07-13): gate@8 is an attorney's closing argument — state the claim, marshal
the evidence, confront the gaps honestly. This module builds that package for one district so a human
(later, an auto-gate) can reconstruct the chain from a published LCT minute all the way back to the
discovered URL and the capture, WITHOUT re-running anything.

Split, mirroring aggregate.py / test_aggregate.py:
  - `build_closing_argument(...)` is PURE — no DB, no disk — so the composition is unit-testable with
    synthetic inputs (tests/test_closing_argument.py);
  - `load_closing_argument(session, district_id)` is the thin I/O wrapper that gathers the ingredients
    (school_fact via the cumulative merge, the immutable Stage-6 handoff for URL/reps, state_event for
    capture time, district_target for the NCES denominator) and calls the pure builder.

Provenance is the IMMUTABLE handoff + state_event (both precious), NOT the regenerable
record->capture join that can dangle after a Stage-5 re-ingest (design note §2a.1).
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter

from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import school_sampling as SS
from infrastructure.acquisition.common.school_match import norm_school as _norm
from infrastructure.acquisition.stage8_aggregate import aggregate as AGG

# band -> the single NCES LEVEL key that maps to it (inverse of SS.LEVEL_BAND, 1:1 for the clean
# three). "Other"/"Secondary"/ambiguous levels map to NO band and are surfaced as a caveat, mirroring
# SS.real_bands_for_district's own treatment — so a band denominator is never silently inflated.
_BAND_LEVEL = {band: level for level, band in SS.LEVEL_BAND.items()}


def _models(f):
    """Parse a school_fact row's models_json into a list; tolerant of already-parsed / missing."""
    m = f.get("models") if "models" in f else f.get("models_json")
    if isinstance(m, list):
        return m
    if not m:
        return []
    try:
        return json.loads(m)
    except (TypeError, ValueError):
        return []


def _plurality_share(schools):
    """Share of a band's accepted schools whose gross equals the MODAL gross — how concentrated
    the determination is. 1.0 = every sampled school agrees; a low value flags a scattered band
    whose single mode is thin evidence (the in-sample sufficiency signal, design note §2b)."""
    grosses = [s.get("gross") for s in schools if s.get("gross") is not None]
    if not grosses:
        return None
    top = Counter(grosses).most_common(1)[0][1]
    return round(top / len(grosses), 3)


def _band_denominator(band, nces_by_level):
    """N_total for a band = the clean-LEVEL NCES count that maps to it (Elementary/Middle/High).
    Conservative and honest: ambiguous levels are not attributed to any band."""
    level = _BAND_LEVEL.get(band)
    if not level:
        return None
    return (nces_by_level or {}).get(level)


def _override(human_determination):
    """Parse a school_fact.human_determination into the recorded human override (§2a.3), or None. Stored
    as a JSON record {start_time, end_time, reason, actor, at} by the gate@8 override endpoint; the
    council's original times are preserved on the fact (never destroyed). Tolerant of the empty-string
    default + any legacy plain-string value (returned under `note`)."""
    if not human_determination:
        return None
    try:
        d = json.loads(human_determination)
        return d if isinstance(d, dict) else {"note": str(human_determination)}
    except (TypeError, ValueError):
        return {"note": str(human_determination)}


def _council_evidence(evidence_json):
    """Parse a school_fact.evidence_json ({model: {quote, locus, stated_minutes, ...}}, v2 only) into
    a render-ready summary + the full per-model detail. Returns None for pre-v2 rows (evidence absent),
    so the receipt says so honestly rather than implying a quote we never captured (§2a.6)."""
    if not evidence_json:
        return None
    try:
        by_model = json.loads(evidence_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(by_model, dict) or not by_model:
        return None
    quote = next((e.get("quote") for e in by_model.values() if (e or {}).get("quote")), "")
    locus = next((e.get("locus") for e in by_model.values() if (e or {}).get("locus")), "")
    stated = [e.get("stated_minutes") for e in by_model.values() if (e or {}).get("stated_minutes") is not None]
    return {
        "quote": quote, "locus": locus,
        # path 2 (option b): corroboration only — gross stays canonical. Reported when ANY model read
        # an explicit minutes statement; `agree` flags cross-model consistency of that stated number.
        "stated_minutes": stated[0] if stated else None,
        "stated_minutes_agree": len(set(stated)) == 1 if stated else None,
        "by_model": by_model,
    }


def build_closing_argument(district_id, *, merged_accepted, merged_unresolved,
                           nces_total, nces_by_level, schools_by_band,
                           evidence_by_reckey=None, capture_events=None, roster_names=None):
    """Compose the closing argument for one district from already-gathered ingredients. PURE.

    Inputs:
      merged_accepted / merged_unresolved : the output of AGG.merge_fact_runs over the district's
          production school_fact rows (each dict carries band, school, status, start_time, end_time,
          gross_minutes, method, models_json, rec_key, extraction_id).
      nces_total       : district.nces_school_count (scalar) — for the #237 contamination detector.
      nces_by_level    : {NCES level: count} — the per-band denominator source.
      schools_by_band  : {band: {"schools": [...]}} — the Stage-1 roster (claimed-band + name source).
      evidence_by_reckey : {rec_key: {url, reps, decision, reason, source_file, capture_time?}} from
          the immutable handoff; attached per school. Missing key -> evidence: None (surfaced honestly).
      capture_events   : district-grain state_event stage-3 capture rows (list of {created_at, outcome}).
      roster_names     : flattened roster names for the contamination detector's keeper hint.

    Returns the closing-argument dict (see the module/design note); self-contained, JSON-serialisable,
    ready to render at gate@8 and to FREEZE into the immutable approval receipt.
    """
    evidence_by_reckey = evidence_by_reckey or {}

    # Reshape merged school_fact rows to district_bands_from_facts' input shape (the server.py:1624
    # twin) — one source of truth for the per-band value, degenerate filter, and contamination flag.
    agg = [{"band": f["band"], "school": f["school"],
            "start": f.get("start_time"), "end": f.get("end_time"),
            "gross": f.get("gross_minutes"), "models": _models(f),
            "method": f.get("method")} for f in merged_accepted]
    bands = AGG.district_bands_from_facts(agg)
    degenerate = AGG.degenerate_school_facts(agg)
    contamination = AGG.detect_single_school_over_extraction(agg, nces_total, roster_names)

    # per (band, normalized-school) lookups off the winning merged fact — the merge already deduped to
    # one winner per (band, norm_school), so these are 1:1 with bands' school entries.
    reckey_of = {(f["band"], _norm(f["school"])): f.get("rec_key") for f in merged_accepted}
    factid_of = {(f["band"], _norm(f["school"])): f.get("fact_id") for f in merged_accepted}
    council_ev_of = {(f["band"], _norm(f["school"])): _council_evidence(f.get("evidence_json"))
                     for f in merged_accepted}
    override_of = {(f["band"], _norm(f["school"])): _override(f.get("human_determination"))
                   for f in merged_accepted}

    claimed = SS.real_bands_for_district(nces_by_level, schools_by_band)
    satisfied = set(bands.keys())

    out_bands = {}
    for band, b in bands.items():
        schools = []
        for sc in b["schools"]:
            key = (band, _norm(sc["school"]))
            rk = reckey_of.get(key)
            schools.append({**sc, "rec_key": rk, "fact_id": factid_of.get(key),
                            "evidence": evidence_by_reckey.get(rk) if rk else None,
                            "council_evidence": council_ev_of.get(key),
                            "human_override": override_of.get(key)})
        n_sampled, n_total = b["n_schools"], _band_denominator(band, nces_by_level)
        out_bands[band] = {
            "gross_minutes": b["gross_minutes"], "start_time": b["start_time"],
            "end_time": b["end_time"], "method": b["method"],
            "sampling": {
                "n_sampled": n_sampled, "n_total": n_total,
                "coverage": round(n_sampled / n_total, 3) if n_total else None,
                "plurality_share": _plurality_share(b["schools"]),
            },
            "schools": schools,
        }

    # The negative space — the honest half of the closing argument (design note §2c.4): what we did
    # NOT resolve, so the picture never reads as "we covered everything."
    negative_space = {
        "unresolved": merged_unresolved,
        "contamination": contamination,
        "degenerate_school_facts": degenerate,
        "claimed_bands": sorted(claimed),
        "unsatisfied_bands": sorted(claimed - satisfied),
        "coverage_gaps": {b: out_bands[b]["sampling"] for b in out_bands
                          if (out_bands[b]["sampling"]["n_total"] or 0)
                          > (out_bands[b]["sampling"]["n_sampled"] or 0)},
        # schools NCES couldn't cleanly band — not attributed to any denominator, stated as a caveat
        "unattributed_level_schools": {lvl: n for lvl, n in (nces_by_level or {}).items()
                                       if lvl not in SS.LEVEL_BAND},
    }

    return {
        "district_id": district_id,
        "bands": out_bands,
        "negative_space": negative_space,
        "capture_events": capture_events or [],
        "provenance": {"nces_total": nces_total, "nces_by_level": nces_by_level or {}},
    }


def min_band_coverage(ca):
    """The district's WEAKEST band coverage (schools sampled / NCES total) — the gate@8 confidence proxy
    for the calibration log (§2c.6). None if no band has a denominator. This is the single number that
    most cheaply says 'how thin is the thinnest part of this district's evidence.'"""
    covs = [b["sampling"]["coverage"] for b in ca.get("bands", {}).values()
            if b["sampling"]["coverage"] is not None]
    return min(covs) if covs else None


def fingerprint(ca):
    """A stable content hash of a closing argument's DETERMINATION — the per-band value + the exact set
    of accepted schools it rests on. Frozen into a gate@8 approval (STAGE8 §2b) so a later re-extraction
    that changes the picture makes the approval detectably STALE (the approved receipt no longer matches
    the live facts). Deliberately covers only what a reviewer signed off on (band → gross → schools),
    not volatile provenance (capture timestamps, evidence prose)."""
    import hashlib

    basis = []
    for band in sorted(ca.get("bands", {})):
        b = ca["bands"][band]
        schools = sorted((s.get("school"), s.get("gross")) for s in b.get("schools", []))
        basis.append((band, b.get("gross_minutes"), schools))
    return hashlib.sha256(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------------------------------
# I/O wrapper — gathers the ingredients and calls the pure builder. Thin by design; all real logic
# (and all the tests) live in build_closing_argument above.
# --------------------------------------------------------------------------------------------------

_HANDOFF_DIR = paths.ACQUISITION / "handoffs"


def _load_handoff_by_hash(handoff_hash):
    """The immutable handoff doc for a content hash (governance §5). Latest file wins if a hash was
    re-emitted; returns None if no file (an older run whose receipt was pruned)."""
    hits = sorted(glob.glob(str(_HANDOFF_DIR / f"handoff_{handoff_hash}_*.json")))
    if not hits:
        return None
    try:
        with open(hits[-1]) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _evidence_from_handoffs(district_id, handoff_hashes):
    """{rec_key: {url, reps, decision, reason}} for a district, read from its production handoffs —
    the frozen 'what we fed the council' record, self-contained (URL + rep files inline)."""
    ev = {}
    for h in handoff_hashes:
        doc = _load_handoff_by_hash(h)
        if not doc:
            continue
        for d in doc.get("districts", []):
            if d.get("district_id") != district_id:
                continue
            for rec in d.get("records", []):
                rk = rec.get("rec_key")
                if rk and rk not in ev:   # earliest handoff seen wins, matching merge's earliest-run rule
                    ev[rk] = {"url": rec.get("url"), "reps": rec.get("reps", []),
                              "decision": rec.get("decision"), "reason": rec.get("reason"),
                              "handoff_hash": h, "handoff_created_at": doc.get("created_at")}
    return ev


def load_closing_argument(session, district_id):
    """Gather one district's ingredients from the gov DB working store + the immutable handoff on
    disk, and build its closing argument. `session` is a governance SQLAlchemy session/connection."""
    from sqlalchemy import text

    facts = [dict(r._mapping) for r in session.execute(text("""
        SELECT f.*, e.handoff_hash, e.run_kind
        FROM school_fact f JOIN extraction e ON e.extraction_id = f.extraction_id
        WHERE f.district_id = :d AND e.run_kind = 'production'
    """), {"d": district_id}).all()]
    accepted, unresolved = AGG.merge_fact_runs(facts)

    handoff_hashes = sorted({f["handoff_hash"] for f in facts if f.get("handoff_hash")})
    evidence = _evidence_from_handoffs(district_id, handoff_hashes)
    # source_file (the reader that produced the extracted text) is a per-fact detail on school_fact —
    # fold it into each rec_key's evidence for the "read via <reader>" line.
    for f in facts:
        rk = f.get("rec_key")
        if rk in evidence and f.get("source_file"):
            evidence[rk].setdefault("source_file", f["source_file"])

    capture_events = [dict(r._mapping) for r in session.execute(text("""
        SELECT created_at, outcome FROM state_event
        WHERE district_id = :d AND stage = 3 ORDER BY created_at
    """), {"d": district_id}).all()]

    meta = session.execute(text("""
        SELECT d.nces_school_count AS nces_total, t.nces_by_level_json, t.schools_by_band_json
        FROM district d
        LEFT JOIN district_target t ON t.district_id = d.district_id
        WHERE d.district_id = :d
    """), {"d": district_id}).mappings().first() or {}
    nces_by_level = json.loads(meta["nces_by_level_json"]) if meta.get("nces_by_level_json") else {}
    schools_by_band = json.loads(meta["schools_by_band_json"]) if meta.get("schools_by_band_json") else {}
    roster_names = [sc.get("school") for m in (schools_by_band or {}).values()
                    for sc in (m or {}).get("schools", []) if sc.get("school")]

    return build_closing_argument(
        district_id, merged_accepted=accepted, merged_unresolved=unresolved,
        nces_total=meta.get("nces_total"), nces_by_level=nces_by_level,
        schools_by_band=schools_by_band, evidence_by_reckey=evidence,
        capture_events=capture_events, roster_names=roster_names)
