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


def _effective_times(f, ov):
    """The OPERATIVE (start, end, gross) for a merged fact = the human override APPLIED over the council's
    reading. A recorded times-override REPLACES the council value in the displayed determination AND in
    the modal calculation (§2a.3, revised 2026-07-13): the reviewer is correcting the number they are
    about to approve, so the mode must see it — otherwise the override is cosmetic and the human approves
    a value they already corrected away from. The council's original stays on the fact for the receipt.

    Only a times-override recomputes: a fact with no start/end override keeps its stored gross VERBATIM
    (no re-derivation, so a non-overridden fact is byte-identical to before). An override supplying only
    one endpoint keeps the council's other endpoint; the recombined pair goes through the CANONICAL
    `AGG.gross_from_times` — the same parse + REQ-055 PLAUSIBLE gate the council path enforces (15c67c4
    review: the first draft's inline arithmetic bypassed the gate AND silently reverted to the stale
    council gross on an unparseable override while still claiming it applied). An invalid stored override
    is NOT applied: council values stand and `error` names why, so the console shows a visible
    "override invalid" state instead of lying in either direction. The endpoint validates before storing
    (server.py), so this path is defense-in-depth for legacy/hand-written rows.

    `ov` is the caller's already-parsed `_override(...)` result (or None). Returns
    {start, end, gross, error} — error ∈ (None, "override_unparseable", "override_implausible")."""
    ov = ov or {}
    if not (ov.get("start_time") or ov.get("end_time")):
        return {"start": f.get("start_time"), "end": f.get("end_time"),
                "gross": f.get("gross_minutes"), "error": None}
    start = ov.get("start_time") or f.get("start_time")
    end = ov.get("end_time") or f.get("end_time")
    gross, err = AGG.gross_from_times(start, end)
    if err:
        return {"start": f.get("start_time"), "end": f.get("end_time"),
                "gross": f.get("gross_minutes"), "error": f"override_{err}"}
    return {"start": start, "end": end, "gross": gross, "error": None}


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
        # an explicit minutes statement. `agree` is a THREE-state flag (review round, PR #252): True =
        # >=2 models stated the same number (real cross-model corroboration), False = >=2 stated and
        # they differ, None = only one model stated it — single-source, NOT agreement; rendering a lone
        # reading as "models agree" would overstate corroboration, the exact dishonesty §2c.4 forbids.
        "stated_minutes": stated[0] if stated else None,
        "stated_minutes_agree": (len(set(stated)) == 1) if len(stated) >= 2 else None,
        "n_models_stated": len(stated),
        "by_model": by_model,
    }


def build_closing_argument(district_id, *, merged_accepted, merged_unresolved,
                           nces_total, nces_by_level, schools_by_band,
                           evidence_by_reckey=None, capture_events=None, roster_names=None,
                           exclusions=None, human_added=None, band_rosters=None,
                           merged_superseded=None, year_conflicts=None):
    """Compose the closing argument for one district from already-gathered ingredients. PURE.

    Inputs:
      merged_accepted / merged_unresolved : the output of AGG.merge_fact_runs over the district's
          production school_fact rows (each dict carries band, school, status, start_time, end_time,
          gross_minutes, method, models_json, rec_key, extraction_id).
      nces_total       : district.nces_school_count (scalar) — for the #237 contamination detector.
      nces_by_level    : {NCES level: count} — the per-band denominator source.
      schools_by_band  : {band: {"schools": [...]}} — the Stage-1 roster (claimed-band + name source).
      evidence_by_reckey : {rec_key: {url, reps, decision, reason, ...}} from the immutable handoff;
          the FALLBACK evidence source. When a merged fact carries `handoff_evidence` (attached by
          load_closing_argument from the fact's OWN handoff — the run that actually produced the
          winning times, review round PR #252), that wins; this map covers facts whose own handoff
          receipt is missing. Missing everywhere -> evidence: None (surfaced honestly).
      capture_events   : district-grain state_event stage-3 capture rows (list of {created_at, outcome}).
      roster_names     : flattened roster names for the contamination detector's keeper hint.
      band_rosters     : #253 — SS.band_rosters_for_district's live ccd_sch fillability roster
          ({band: {total, by_source, schools}, "_unattributed": [...], "_year": ...}), or None when
          the CCD files aren't on disk. When present it is the band DENOMINATOR (a KG-08
          'Elementary' K-8 counts toward middle — the Santa Fe 200%-coverage fix); when None the
          old clean-LEVEL denominator stands, marked as such in the sampling provenance.
      exclusions       : #257 — the district's standing human band-exclusions, list of
          {band, school, reason, actor, created_at}. An excluded (band, school) is a fact whose
          OBSERVATION is correct but whose band membership is stale (the temporal grade-reconfiguration
          class — Coffee County's Kinston/Zion Chapel). Excluded facts leave the band's mode/count but
          stay VISIBLE (struck-through at render, in the frozen receipt) — a recorded, auditable human
          decision, never a deletion. Matching is on the normalized school name (same axis as the merge),
          scoped per (band, school): a K-12 can be excluded from `elementary` and kept in `high`.
      merged_superseded : #254 — the year-superseded accepted facts merge_fact_runs set aside
          (with_superseded=True): a known, NEWER school_year beat a known older one for the same
          (band, school). Surfaced in negative_space so the reviewer SEES why the stale rows left
          the mode (no-silent-caps); each entry pairs the loser with its superseding winner.
      year_conflicts   : #254 — AGG.detect_year_conflicts over the raw cross-run rows: the
          (band, school) groups mixing known years or known/unknown, each side carrying its
          source_file as a format HINT for the reviewer (never an automatic rule).

    Returns the closing-argument dict (see the module/design note); self-contained, JSON-serialisable,
    ready to render at gate@8 and to FREEZE into the immutable approval receipt.
    """
    evidence_by_reckey = evidence_by_reckey or {}

    # ONE enrichment pass over the merged facts (15c67c4 review: the earlier shape parsed the override
    # twice and derived "was it overridden" three independent ways) — each fact is paired with its
    # parsed override and its override-EFFECTIVE times, and everything downstream reads this one
    # structure. The (start, end, gross) fed to the MODE are the effective values (§2a.3, revised
    # 2026-07-13): a human correction to a school's times moves the band's mode, not just an annotation.
    enriched = []
    for f in merged_accepted:
        ov = _override(f.get("human_determination"))
        enriched.append((f, ov, _effective_times(f, ov)))

    # Reshape to district_bands_from_facts' input shape (the server.py gate@7 twin) — one source of
    # truth for the per-band value, degenerate filter, and contamination flag.
    agg = [{"band": f["band"], "school": f["school"],
            "start": eff["start"], "end": eff["end"], "gross": eff["gross"],
            "models": _models(f), "method": f.get("method"),
            "applies_to": f.get("applies_to")} for f, ov, eff in enriched]

    # #257: apply the standing human band-exclusions BEFORE the mode — an excluded (band, norm_school)
    # leaves the band's value/count entirely (the human sibling of the automatic exclude-but-surface
    # detectors: degenerate_school_facts #245, contamination #237). Applied exclusions are carried for
    # the receipt/render; a stored exclusion matching no current fact is dormant (kept in the DB, not
    # reported here — it re-applies automatically if a follow-up re-extracts that school).
    excl_of = {(e["band"], _norm(e["school"])): e for e in (exclusions or [])}
    included_agg = [r for r in agg if (r["band"], _norm(r["school"])) not in excl_of]
    applied_exclusions = sorted(
        ({**excl_of[(r["band"], _norm(r["school"]))], "school": r["school"]}
         for r in agg if (r["band"], _norm(r["school"])) in excl_of),
        key=lambda e: (e["band"], _norm(e["school"])))

    # #474: hand-entered schools (the last-resort fallback to #473 re-extraction) VOTE in the mode like
    # any human determination (§2a.3) — the API validated times/plausibility/citation before storing;
    # the defensive re-derivation here mirrors _effective_times' posture (a legacy/hand-written row
    # that no longer parses is dropped from the mode, never silently trusted). An exclusion on the same
    # (band, school) beats the add — a struck school can't be re-injected by a stale hand-entry.
    human_of = {}
    for ha in (human_added or []):
        key = (ha["band"], _norm(ha["school"]))
        if key in excl_of:
            continue
        gross, err = AGG.gross_from_times(ha.get("start_time"), ha.get("end_time"))
        if err:
            continue
        human_of[key] = ha
        included_agg.append({"band": ha["band"], "school": ha["school"], "start": ha["start_time"],
                             "end": ha["end_time"], "gross": gross, "models": [],
                             "method": "human_added"})

    bands = AGG.district_bands_from_facts(included_agg)
    degenerate = AGG.degenerate_school_facts(agg)
    contamination = AGG.detect_single_school_over_extraction(agg, nces_total, roster_names)

    # #253 A1: combined-scope extracted names ('k8 schools', 'milagro and ortiz schools') — a group
    # description landing as one pseudo-school row. Detect-and-flag (#237 posture): the flagged fact
    # KEEPS its vote until the reviewer disposes (exclude via #257, or the roster-template
    # slot-projection once built). Campus resolution matches against the FULL live roster when
    # band_rosters is present (the Stage-1 roster_names list is only the selected subset).
    cs_roster = list(roster_names or [])
    for _b, _m in ((band_rosters or {}).items()):
        if isinstance(_m, dict) and _m.get("schools"):
            cs_roster.extend(_m["schools"])
    cs_of, combined_scope = {}, []
    for r in agg:
        key = (r["band"], _norm(r["school"]))
        if key in cs_of:
            continue
        # #254: a council applies_to == "multiple" reading merges into this flag surface — the UNION
        # of the deterministic name detector and the page's own stated scope (same render; `source`
        # says which said so). A scope warning is a warning, whichever side raised it.
        m = SS.combined_scope_name(r["school"], cs_roster)
        council_scope = r.get("applies_to") == "multiple"
        if m or council_scope:
            m = {**(m or {"school": r["school"], "kind": "council_scope", "campuses": []}),
                 "source": "name+council" if (m and council_scope) else
                           "council" if council_scope else "name"}
            cs_of[key] = m
            combined_scope.append({**m, "band": r["band"],
                                   "excluded": key in excl_of})

    # per-(band, normalized-school) lookup off the winning merged fact — the merge already deduped to
    # one winner per (band, norm_school), so this is 1:1 with bands' school entries. The evidence
    # attached here is resolved from the WINNING fact itself: its own handoff's record when the loader
    # supplied it (`handoff_evidence` — the run that actually produced the displayed times), else the
    # rec_key fallback map; `source_file` comes from the same winning fact, never from an unordered
    # sibling row (both were review-round fixes, PR #252: the old rec_key-only join could attach a
    # DIFFERENT run's URL/reader to the times being approved).
    fact_of = {(f["band"], _norm(f["school"])): (f, ov, eff) for f, ov, eff in enriched}

    def _school_evidence(f):
        ev = f.get("handoff_evidence") or (evidence_by_reckey.get(f.get("rec_key")) if f.get("rec_key") else None)
        if ev and f.get("source_file"):
            ev = {**ev, "source_file": f["source_file"]}
        return ev

    claimed = SS.real_bands_for_district(nces_by_level, schools_by_band)
    satisfied = set(bands.keys())

    out_bands = {}
    for band, b in bands.items():
        schools = []
        for sc in b["schools"]:
            ha = human_of.get((band, _norm(sc["school"])))
            if ha:
                # #474: a hand-entered school has no council fields — it carries its citation instead,
                # rendered visibly tagged (the mirror of #257's struck-but-visible treatment).
                schools.append({**sc, "rec_key": None, "fact_id": None,
                                "council_start_time": None, "council_end_time": None,
                                "council_gross": None, "evidence": None, "council_evidence": None,
                                "human_override": None, "override_applied": False,
                                "override_error": None,
                                "school_year": None,
                                "human_added": {"source_url": ha.get("source_url"),
                                                "reason": ha.get("reason"), "actor": ha.get("actor"),
                                                "created_at": ha.get("created_at")}})
                continue
            f, ov, eff = fact_of.get((band, _norm(sc["school"])), ({}, None, {}))
            # sc.start_time/end_time/gross are the OVERRIDE-EFFECTIVE values (they came through `agg`);
            # carry the COUNCIL original alongside so the row can show "council read X → override Y".
            # `override_applied`/`override_error` are the SERVER-computed truth (one derivation, here),
            # so the console never re-derives override state from raw fields (15c67c4 review).
            schools.append({**sc, "rec_key": f.get("rec_key"), "fact_id": f.get("fact_id"),
                            "council_start_time": f.get("start_time"), "council_end_time": f.get("end_time"),
                            "council_gross": f.get("gross_minutes"),
                            "evidence": _school_evidence(f),
                            "council_evidence": _council_evidence(f.get("evidence_json")),
                            "human_override": ov,
                            "override_applied": bool(ov) and not eff.get("error")
                                                and bool(ov.get("start_time") or ov.get("end_time")),
                            "override_error": eff.get("error"),
                            # #254: the year the page itself stated (council consensus), or None —
                            # rendered as a muted chip beside the times
                            "school_year": f.get("school_year"),
                            "combined_scope": cs_of.get((band, _norm(sc["school"])))})
        # #257: the band's excluded schools ride along AFTER the included rows — struck-through at
        # render, in the frozen receipt, NOT in the mode/count above (bands was built exclusion-first).
        for (xband, xnorm), e in sorted(excl_of.items()):
            if xband != band:
                continue
            f, ov, eff = fact_of.get((band, xnorm), (None, None, None))
            if f is None:
                continue
            schools.append({"school": f["school"], "start_time": eff["start"], "end_time": eff["end"],
                            "gross": eff["gross"], "models": _models(f), "human_determination": "",
                            "rec_key": f.get("rec_key"), "fact_id": f.get("fact_id"),
                            "council_start_time": f.get("start_time"), "council_end_time": f.get("end_time"),
                            "council_gross": f.get("gross_minutes"),
                            "evidence": _school_evidence(f),
                            "council_evidence": _council_evidence(f.get("evidence_json")),
                            "human_override": ov,
                            "override_applied": bool(ov) and not eff.get("error")
                                                and bool(ov.get("start_time") or ov.get("end_time")),
                            "override_error": eff.get("error"),
                            "school_year": f.get("school_year"),
                            "combined_scope": cs_of.get((band, xnorm)),
                            "excluded": e})
        # #253: the denominator is the LIVE band-SERVING roster when available (a KG-08 'Elementary'
        # K-8 counts toward middle — Santa Fe's middle reads 4-of-9, not 4-of-2), with the old
        # clean-LEVEL count kept alongside for continuity and as the fallback when the CCD files
        # aren't on disk. The receipt carries the denominator's own provenance (design note §2c:
        # "if the denominator is wrong, every sufficiency statistic lies").
        n_sampled = b["n_schools"]
        n_total_level = _band_denominator(band, nces_by_level)
        broster = (band_rosters or {}).get(band)
        if broster:
            n_total = broster["total"]
            denom = {"source": "band_roster", "by_source": broster["by_source"],
                     "nces_year": (band_rosters or {}).get("_year")}
        else:
            n_total = n_total_level
            denom = {"source": "nces_level", "by_source": None, "nces_year": None}
        out_bands[band] = {
            "gross_minutes": b["gross_minutes"], "start_time": b["start_time"],
            "end_time": b["end_time"], "method": b["method"],
            "sampling": {
                "n_sampled": n_sampled, "n_total": n_total,
                "n_total_level_only": n_total_level,
                "coverage": round(n_sampled / n_total, 3) if n_total else None,
                "plurality_share": _plurality_share(b["schools"]),
                "denominator": denom,
            },
            "schools": schools,
        }

    # #258: name-vs-level mismatch flags, both surfaces. The ROSTER side catches the Coffee County
    # signature at its source ('Zion Chapel High School', NCES-tagged Other, placed in elementary by
    # Stage 1); the FACTS side catches a level-token extracted name landing in a contradicting band
    # (extracted names often differ from roster names — Coffee County's came through as 'zion chapel
    # k12', which correctly does NOT flag: a K-12 name serves any band). Detect-and-flag only (#237
    # posture): surfaced for the human, never dropped.
    mismatches, seen_mm = [], set()
    for band, meta in (schools_by_band or {}).items():
        for sc in (meta or {}).get("schools") or []:
            name = sc.get("school") or sc.get("name")
            m = SS.name_level_mismatch(name, sc.get("level"), [band])
            if m and (m["school"], band) not in seen_mm:
                seen_mm.add((m["school"], band))
                mismatches.append({**m, "surface": "roster", "band": band})
    for r in agg:
        m = SS.name_level_mismatch(r["school"], None, [r["band"]])
        if m and (m["school"], r["band"]) not in seen_mm:
            seen_mm.add((m["school"], r["band"]))
            mismatches.append({**m, "surface": "fact", "band": r["band"]})

    # #473 detector: an unsatisfied band whose SIBLING bands hold accepted facts from an
    # already-captured rep — a strong "the data may be in that doc, re-read it" flag (the TUSD
    # signature: the hub artifact that filled middle+high also contains the elementary schedules).
    # A heuristic surfaced for the reviewer, not a certainty — same posture as #258.
    sibling_reps, seen_rk = [], set()
    for f, ov, eff in enriched:
        rk = f.get("rec_key")
        if not rk or rk in seen_rk:
            continue
        seen_rk.add(rk)
        ev = _school_evidence(f) or {}
        sibling_reps.append({"rec_key": rk, "url": ev.get("url"),
                             "source_file": f.get("source_file")})
    recoverable = ([{"band": band, "from_reps": sibling_reps}
                    for band in sorted(claimed - satisfied)] if sibling_reps else [])

    # #254: pair each year-superseded fact with the winner that displaced it — the reviewer must SEE
    # why the stale rows left the mode (no-silent-caps), with both years and both grosses side by side.
    superseded_out = []
    for f in (merged_superseded or []):
        w = fact_of.get((f["band"], _norm(f["school"])))
        win = w[0] if w else {}
        superseded_out.append({
            "band": f["band"], "school": f["school"],
            "school_year": f.get("school_year"), "gross": f.get("gross_minutes"),
            "start_time": f.get("start_time"), "end_time": f.get("end_time"),
            "source_file": f.get("source_file"),
            "superseded_by": {"school": win.get("school"),
                              "school_year": win.get("school_year"),
                              "gross": win.get("gross_minutes"),
                              "source_file": win.get("source_file")}})

    # The negative space — the honest half of the closing argument (design note §2c.4): what we did
    # NOT resolve, so the picture never reads as "we covered everything."
    negative_space = {
        "unresolved": merged_unresolved,
        "contamination": contamination,
        "degenerate_school_facts": degenerate,
        # #257: every APPLIED human band-exclusion — the audit surface that survives even when the
        # excluded school's whole band vanished from `bands` (nothing left to render it under).
        "band_exclusions": applied_exclusions,
        # #258: name-vs-NCES-level/band mismatch flags (detect-and-flag, never auto-reject)
        "name_level_mismatches": mismatches,
        # #253: combined-scope extracted names (group descriptions counted as one pseudo-school) —
        # flagged for review; the fact keeps its vote until the reviewer disposes
        "combined_scope_facts": combined_scope,
        # #473: unsatisfied bands with sibling-band facts from an already-captured rep — recover
        # candidates (re-extract the rep at gate@8; #474 hand-add is the fallback)
        "recoverable_bands": recoverable,
        # #254: year-superseded facts (a known NEWER year beat a known older one) — why the stale
        # rows left the mode, with both sides visible; and every (band, school) group mixing year
        # knowledge, each side's source_file riding along as a format HINT for the reviewer
        "superseded_facts": superseded_out,
        "year_conflicts": year_conflicts or [],
        "claimed_bands": sorted(claimed),
        "unsatisfied_bands": sorted(claimed - satisfied),
        "coverage_gaps": {b: out_bands[b]["sampling"] for b in out_bands
                          if (out_bands[b]["sampling"]["n_total"] or 0)
                          > (out_bands[b]["sampling"]["n_sampled"] or 0)},
        # schools NCES couldn't cleanly band — not attributed to any denominator, stated as a caveat
        "unattributed_level_schools": {lvl: n for lvl, n in (nces_by_level or {}).items()
                                       if lvl not in SS.LEVEL_BAND},
    }

    # #253: schools the live roster couldn't attribute to ANY band (unparseable span + ambiguous
    # LEVEL) — the roster-side sibling of unattributed_level_schools; surfaced, never dropped.
    if band_rosters and band_rosters.get("_unattributed"):
        negative_space["unattributed_roster_schools"] = band_rosters["_unattributed"]

    return {
        "district_id": district_id,
        "bands": out_bands,
        "negative_space": negative_space,
        "capture_events": capture_events or [],
        "provenance": {
            "nces_total": nces_total, "nces_by_level": nces_by_level or {},
            # #253: the denominator's own provenance (§2c) — source + the criteria disclaimer the
            # console shows beside every coverage stat (Ian, 2026-07-14: the auditor must see what
            # the denominator counts: virtual/alternative/adult campuses are excluded).
            "denominator": {
                "source": "band_roster" if band_rosters else "nces_level",
                "nces_year": (band_rosters or {}).get("_year"),
                "criteria": "Open, regular NCES schools only (virtual, alternative, special-ed and "
                            "adult-ed campuses excluded; standalone preschools excluded). A school "
                            "counts toward every band its NCES LEVEL or its own grade span serves — "
                            "a K-8 counts toward elementary AND middle.",
            },
        },
    }


def min_band_coverage(ca):
    """The district's WEAKEST band coverage (schools sampled / NCES total) — the gate@8 confidence proxy
    for the calibration log (§2c.6). None if no band has a denominator. This is the single number that
    most cheaply says 'how thin is the thinnest part of this district's evidence.'"""
    covs = [b["sampling"]["coverage"] for b in ca.get("bands", {}).values()
            if b["sampling"]["coverage"] is not None]
    return min(covs) if covs else None


def fingerprint(ca):
    """A stable content hash of a closing argument's DETERMINATION — the per-band value, the exact set
    of accepted schools it rests on, each school's human override, AND the applied band-exclusions
    (#257). Frozen into a gate@8 approval (STAGE8 §2b) so any later change to the picture makes the
    approval detectably STALE. Overrides are IN the basis by design (review round, PR #252): an override
    recorded AFTER a district was approved is a new human determination the approval never covered —
    excluding it left `is_stale` False after exactly the kind of change the staleness check exists to
    catch. Exclusions follow the same rule (they move the mode AND are themselves human determinations);
    they enter both per-school (the `excluded` marker) and via negative_space.band_exclusions, which
    covers the fully-excluded-band case where no school row remains to carry the marker. Deliberately
    still excludes volatile provenance (capture timestamps, evidence prose) — those don't change what
    was signed off on."""
    import hashlib

    def _ov(s):
        ov = s.get("human_override")
        if not ov:
            return None
        return (ov.get("start_time"), ov.get("end_time"), ov.get("reason") or ov.get("note"))

    def _ex(s):
        e = s.get("excluded")
        return (e.get("reason"), e.get("actor")) if e else None

    def _ha(s):
        h = s.get("human_added")
        return (h.get("source_url"), h.get("reason")) if h else None

    basis = []
    for band in sorted(ca.get("bands", {})):
        b = ca["bands"][band]
        # key=str-of-tuple: determinism is all the sort needs, and it can't raise on a None-vs-tuple
        # comparison if two entries ever tie on (school, gross)
        schools = sorted(((s.get("school"), s.get("gross"), _ov(s), _ex(s), _ha(s))
                          for s in b.get("schools", [])), key=str)
        basis.append((band, b.get("gross_minutes"), schools))
    exclusions = sorted(((e.get("band"), e.get("school"), e.get("reason"))
                         for e in ca.get("negative_space", {}).get("band_exclusions", [])), key=str)
    basis.append(("__band_exclusions__", exclusions))
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
    """Evidence for a district read from its production handoffs — the frozen 'what we fed the council'
    record, self-contained (URL + rep files inline). Returns TWO maps:
      by_hash_rk : {(handoff_hash, rec_key): ev} — the precise lookup, so a fact's evidence can come
                   from the fact's OWN run's handoff (review round, PR #252: an earlier draft deduped
                   per rec_key over `sorted(handoff_hashes)` — a LEXICOGRAPHIC sort of content hashes,
                   uncorrelated with run order, while merge_fact_runs picks winners by extraction_id —
                   so the displayed URL could belong to a different run than the displayed times);
      by_rk      : {rec_key: ev} — the fallback for a fact whose own handoff receipt is missing,
                   first-seen in the CALLER's hash order (the caller passes run-chronological order).
    """
    by_hash_rk, by_rk = {}, {}
    for h in handoff_hashes:
        doc = _load_handoff_by_hash(h)
        if not doc:
            continue
        for d in doc.get("districts", []):
            if d.get("district_id") != district_id:
                continue
            for rec in d.get("records", []):
                rk = rec.get("rec_key")
                if not rk:
                    continue
                ev = {"url": rec.get("url"), "reps": rec.get("reps", []),
                      "decision": rec.get("decision"), "reason": rec.get("reason"),
                      "handoff_hash": h, "handoff_created_at": doc.get("created_at")}
                by_hash_rk.setdefault((h, rk), ev)
                by_rk.setdefault(rk, ev)
    return by_hash_rk, by_rk


def load_closing_argument(session, district_id):
    """Gather one district's ingredients from the gov DB working store + the immutable handoff on
    disk, and build its closing argument. `session` is a governance SQLAlchemy session/connection."""
    from sqlalchemy import text

    facts = [dict(r._mapping) for r in session.execute(text("""
        SELECT f.*, e.handoff_hash, e.run_kind
        FROM school_fact f JOIN extraction e ON e.extraction_id = f.extraction_id
        WHERE f.district_id = :d AND e.run_kind = 'production'
        ORDER BY f.extraction_id, f.fact_id
    """), {"d": district_id}).all()]
    # #254: with_superseded surfaces the year-superseded facts; the conflict detector runs on the
    # same raw cross-run rows (it needs group-level visibility the merged winners no longer carry).
    accepted, unresolved, superseded = AGG.merge_fact_runs(facts, with_superseded=True)
    year_conflicts = AGG.detect_year_conflicts(facts)

    # Handoffs in RUN-chronological order (earliest extraction_id that referenced each hash) — the same
    # axis merge_fact_runs picks winners on, never lexicographic hash order (review round, PR #252).
    first_run = {}
    for f in facts:
        h = f.get("handoff_hash")
        if h and h not in first_run:
            first_run[h] = f["extraction_id"]
    handoff_hashes = sorted(first_run, key=first_run.get)
    by_hash_rk, by_rk = _evidence_from_handoffs(district_id, handoff_hashes)
    # Attach each WINNING fact's evidence from its own run's handoff (falling back to the earliest-run
    # record for its rec_key when that receipt file is missing). source_file rides on the fact itself,
    # so the builder folds the winning fact's reader in — no cross-row setdefault race.
    for f in accepted:
        f["handoff_evidence"] = (by_hash_rk.get((f.get("handoff_hash"), f.get("rec_key")))
                                 or by_rk.get(f.get("rec_key")))

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

    # #257: the district's standing human band-exclusions (precious band_exclusion table) — matched
    # in the builder on the same norm_school axis the merge dedupes on.
    exclusions = [dict(r._mapping) for r in session.execute(text("""
        SELECT band, school, norm_school, reason, actor, created_at
        FROM band_exclusion WHERE district_id = :d ORDER BY band, norm_school
    """), {"d": district_id}).all()]

    # #474: the district's hand-entered schools (precious human_added_fact table).
    human_added = [dict(r._mapping) for r in session.execute(text("""
        SELECT band, school, norm_school, start_time, end_time, source_url, reason, actor, created_at
        FROM human_added_fact WHERE district_id = :d ORDER BY band, norm_school
    """), {"d": district_id}).all()]

    # #253: the LIVE band-serving denominator roster (Ian, 2026-07-14: derive from ccd_sch live,
    # never freeze — the approval receipt snapshots it at sign-off). None (missing CCD files) falls
    # back to the clean-LEVEL denominator inside the builder, marked as such in the provenance.
    try:
        band_rosters = SS.band_rosters_for_district(district_id)
    except Exception:
        band_rosters = None

    return build_closing_argument(
        district_id, merged_accepted=accepted, merged_unresolved=unresolved,
        nces_total=meta.get("nces_total"), nces_by_level=nces_by_level,
        schools_by_band=schools_by_band, evidence_by_reckey=by_rk,
        capture_events=capture_events, roster_names=roster_names,
        exclusions=exclusions, human_added=human_added, band_rosters=band_rosters,
        merged_superseded=superseded, year_conflicts=year_conflicts)
