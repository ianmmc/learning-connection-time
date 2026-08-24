"""Per-school -> district band aggregation: council consensus, the per-band mode, and the
mode-stability early-exit.

Pure logic, no I/O. The rule, per ACQUISITION_PIPELINE.md:

  - Within a school, the COUNCIL agrees the school's (start, end) pair — cross-family agreement
    within TOL, judge breaks ties (REQ-056). See `consensus_school_facts()`, the live entry point.
  - Deterministic code then computes `gross = end - start`; models never compute minutes and never
    pick a "typical" schedule (REQ-054), and the metric is GROSS bell-to-bell, never net (REQ-055).
  - Across schools, the district band value is the MODAL school value (ties/uncertain -> MEAN).
  - Mode-stability early-exit: stop sampling a band once the running mode is stable.

Cross-family agreement (the family buckets) uses the canonical map in
`common.model_families`, keyed by FULL OpenRouter model id — the ids the live Stage-7 path passes.

`aggregate_band`/`aggregate_district` take already-decided per-school MINUTES rather than times, so
they predate the REQ-054 split; `aggregate_district` survives only as the arithmetic the mode rule
is specified in (exercised by `tests/test_aggregate.py`), while `aggregate_band` itself is still the
live per-band mode primitive `district_bands_from_facts` calls. New callers want
`consensus_school_facts` + `district_bands_from_facts`.
"""
from collections import Counter
from statistics import mean

# Single source of truth for family buckets (REQ-056); aliased to `family` so `_cross_family` reads
# naturally. Consumes FULL OpenRouter ids (e.g. "google/gemini-2.5-flash-lite").
from infrastructure.acquisition.common.model_families import family_of as family

TOL = 15          # minutes: two values "agree" if within +/-TOL
BANDS = ("elementary", "middle", "high")
PLAUSIBLE = (240, 510)   # gross bell-to-bell minutes/day sanity gate (real days run to ~8.5h)

def _cluster(values, tol=TOL):
    """Greedy cluster of (model, minutes) by within-tol proximity; return clusters sorted largest-first."""
    items = sorted(values, key=lambda mv: mv[1])
    clusters = []
    for model, v in items:
        for c in clusters:
            if abs(v - c["center"]) <= tol:
                c["members"].append((model, v)); c["center"] = mean([x[1] for x in c["members"]]); break
        else:
            clusters.append({"center": float(v), "members": [(model, v)]})
    clusters.sort(key=lambda c: len(c["members"]), reverse=True)
    return clusters

def _cross_family(members):
    return len({family(m) for m, _ in members})

def mode_stable(values, window=5, min_n=3, min_share=0.6):
    """Early-exit for large-district band sampling. True when, over the last `window` schools,
    (a) the cumulative modal value (on the TOL grid) is unchanged, AND (b) that mode actually
    commands a plurality >= min_share of all values so far. Condition (b) prevents a mode that
    locked in early from masking a genuinely scattered band (where later schools keep disagreeing)."""
    if len(values) < max(min_n, window): return False
    grid = [round(v / TOL) * TOL for v in values]
    tail_modes = [Counter(grid[: i + 1]).most_common(1)[0][0] for i in range(len(grid) - window, len(grid))]
    if len(set(tail_modes)) != 1: return False
    mode_val, mode_n = Counter(grid).most_common(1)[0]
    return mode_n / len(grid) >= min_share

def aggregate_band(school_values):
    """school_values: list of accepted per-school gross minutes for ONE band -> district value.
    The MODE = the single most common value (exact). On a tie between distinct values, fall back
    to the arithmetic mean. (Earlier version returned a tolerance-cluster's MEAN center, which is
    NOT the mode — e.g. {380:26, 390:2, 345:1} wrongly gave 381 instead of 380.)"""
    vals = [v for v in school_values if v is not None]
    if not vals: return None, "no_schools"
    counts = Counter(vals).most_common()        # [(value, n), ...] descending
    if len(counts) >= 2 and counts[0][1] == counts[1][1]:
        return round(mean(vals)), "mean_tiebreak"   # genuine tie between distinct values -> mean
    return counts[0][0], "modal"                  # the actual most-common gross value

def aggregate_district(per_school):
    """per_school: list of {band: accepted_minutes}. Returns {band: {value, method, n}}."""
    out = {}
    for band in BANDS:
        sv = [s.get(band) for s in per_school if s.get(band) is not None]
        val, method = aggregate_band(sv)
        out[band] = {"value": val, "method": method, "n": len(sv)}
    return out


# ============================================================================
# Per-school CONSENSUS (the correct flow): models assert per-school {school, band,
# start, end} FACTS; the council agrees on each school's (start,end) pair; code
# computes gross = end-start; the per-band district value is the mode over the
# agreed per-school gross values. Models never compute minutes or pick a mode.
# ============================================================================
import re as _re
# School-name normalization is shared with the Stage-7 GT validator (they must match identically) —
# one home in common (REQ-117). See common.school_match.
from infrastructure.acquisition.common.school_match import norm_school as _norm_school
from infrastructure.acquisition.common.school_match import norm_school_strict as _norm_school_strict
from infrastructure.acquisition.common.school_match import resolve_school_identity
from infrastructure.acquisition.common.school_match import _base as _base_name
# #789: the facility-token list is IMPORTED, never hand-copied — the two screens must not drift.
from infrastructure.acquisition.common.school_sampling import FACILITY_NAME_TOKENS

# #693 rung-4 exclusion screen: an UNMATCHED extracted name that pattern-matches an
# excluded-school-type (standalone preschool/EC, alternative/credit-recovery, adult/evening ed —
# the classes _eligible keeps out of the roster denominator) is routed to `unresolved` with an
# explicit reason, never accepted into a band mode and never silently dropped. Applies ONLY after
# roster resolution fails: a rostered school never reaches this (its roster presence already
# passed _eligible). Review #789: the once-bare words (adult/evening/virtual/cyber) over-matched
# ordinary thematic names ('Evening Star Elementary') — they now require a program-type phrase;
# bare 'cyber' is dropped entirely (true virtual schools are excluded upstream by the CCD
# virtual-ids list in _eligible, not by name). The facility tokens ride in from the one shared
# list (#222's FACILITY_NAME_TOKENS).
_EXCLUDED_NAME = _re.compile(
    r"\b(pre\s?k|prek|preschool|pre\s?kindergarten|early\s+childhood|early\s+learning|ecc|eclc"
    r"|head\s+start|alternative|credit\s+recovery"
    r"|adult\s+(?:ed|education|learning|school)|evening\s+(?:school|program|academy)"
    r"|virtual\s+(?:school|academy|learning|program)|online\s+(?:school|academy)"
    r"|" + "|".join(_re.escape(t).replace(r"\ ", r"\s+") for t in FACILITY_NAME_TOKENS)
    + r")\b")
# #638: ONE canonical HH:MM parser (was a private copy here + another in stage9 provenance).
from infrastructure.acquisition.common.timeutil import hhmm_to_min as _to_min

def _normalize_ambiguous_end(s, e):
    """#716: deterministic 12h→24h END normalization at the consensus boundary. A voter that
    echoes the document's 12-hour clock verbatim ('3:30') parses 720 minutes from a voter that
    normalized to 24h ('15:30') — near-perfect substantive agreement minted into disagreement at
    scale (Washoe: 67 of ~106 schools unresolved on exactly this shape). The ambiguity is fully
    resolvable deterministically in this domain: no school day ENDS between 01:00 and 06:59, so an
    end inside that window is afternoon: +720. The window is the ONLY trigger (#732 review): every
    genuine PM-dismissal echo lands in it (12h dismissals 1:00–6:59pm; no real school dismisses
    after 18:59), so a broader `end < start` rule adds no recall — while it WOULD launder a
    genuinely garbled/transposed pair (start 13:00 / end 07:45 → a fabricated 19:45 accepted fact)
    that the plausibility gate correctly routes to unresolved for human review, and could mint an
    invalid >23:59 clock string. Window max (06:59) + 720 = 18:59, so the result is always a valid
    time. Applied uniformly to voter AND judge rows, BEFORE clustering, per REQ-054 (time
    interpretation lives in deterministic code, never in model formatting). Starts are never
    touched (the symmetric ambiguity doesn't exist: schools start in the morning), and the
    human-override path (gross_from_times) is deliberately excluded — auto-correcting a human's
    typo would mask it instead of failing loud."""
    if s is not None and e is not None and 60 <= e <= 419:
        e += 720
    return e


def is_plausible(gross):
    """THE plausibility gate (REQ-055): is a gross bell-to-bell minutes/day value inside PLAUSIBLE?
    One predicate, shared by the council path (consensus_school_facts) and the human-override path
    (closing_argument via gross_from_times) — commit 15c67c4's review found the override path had
    re-implemented gross-from-times WITHOUT this gate, letting a typo'd override (gross=125) become a
    district's modal determination when the same number from a model would have been rejected."""
    return gross is not None and PLAUSIBLE[0] <= gross <= PLAUSIBLE[1]

def gross_from_times(start, end):
    """Parse two HH:MM strings and compute gross = end − start, gated to PLAUSIBLE. The PUBLIC,
    canonical string-input path — anything outside this module that needs gross-from-times calls THIS
    (not the private _to_min + inline arithmetic; the 15c67c4 review flagged that cross-module reach).
    Returns (gross, None) on success, (None, "unparseable") if either time won't parse, or
    (None, "implausible") when the pair parses but the gross fails the REQ-055 gate."""
    s, e = _to_min(start), _to_min(end)
    if s is None or e is None:
        return None, "unparseable"
    g = e - s
    if not is_plausible(g):
        return None, "implausible"
    return g, None

# #254: deterministic school-year parsing — NEVER trust the model's formatting. The plausibility
# window + the COVID wall come from the calendar single-source-of-truth (moved to
# infrastructure.utilities.school_year precisely so acquisition can read it without breaching the
# acquisition↛database import contract).
from infrastructure.utilities.school_year import COVID_EXCLUDED_YEARS as _COVID_YEARS
from infrastructure.utilities.school_year import current_school_year as _current_school_year

_SY_4DIGIT = _re.compile(r"((?:19|20)\d{2})\s*[-–—/]\s*((?:19|20)?\d{2})(?!\d)")
_SY_2DIGIT = _re.compile(r"(?<!\d)(\d{2})\s*[-–—/]\s*(\d{2})(?!\d)")
_SY_FLOOR = 2023   # first post-COVID year — anything older is unusable for bell schedules


def format_school_year(start: int) -> str:
    """2025 -> '2025-26' (the canonical stored form)."""
    return f"{start}-{(start + 1) % 100:02d}"


def parse_school_year(s):
    """Defensive parse of a model-returned `school_year` READING -> start-year int, or None.
    The v3 prompt asks for 'YYYY-YY', but a model's formatting is never trusted (#254): accepts
    '2025-26', '2025-2026', 'SY25-26', '2025/26', with surrounding prose. Requires a CONSECUTIVE
    pair (a '2025-27' hallucination is garbage, not a year), rejects COVID years (Rule #2) and
    anything outside [2023, current+1] — the same window ACCEPTABLE_BELL_YEARS spans, plus one
    year of forward slack for a schedule published ahead of its year. None = unknown, which the
    merge treats as COEXIST (never auto-oldest — Ian, 2026-07-14)."""
    if not s:
        return None
    t = str(s).strip()
    m = _SY_4DIGIT.search(t)
    if m:
        y1 = int(m.group(1))
        y2 = int(m.group(2)) if len(m.group(2)) == 4 else (y1 // 100) * 100 + int(m.group(2))
    else:
        m = _SY_2DIGIT.search(t)
        if not m:
            return None
        y1, y2 = 2000 + int(m.group(1)), 2000 + int(m.group(2))
    if y2 != y1 + 1:
        return None
    if format_school_year(y1) in _COVID_YEARS:
        return None
    if not (_SY_FLOOR <= y1 <= int(_current_school_year()[:4]) + 1):
        return None
    return y1


def _evidence_of(row):
    """Pull the v2 going-forward evidence fields off a raw model row (STAGE8 §2a.6): the verbatim
    quote the times were read from, an optional page/section locus, and any EXPLICITLY-stated daily
    minutes (path 2) + its own quote. Tolerant of v1 rows that lack all of them — returns an all-empty
    dict, which the caller treats as 'no evidence' and does not attach. stated_minutes is coerced to
    int-or-None; deterministic gross stays canonical (option (b)) — this is corroboration, not a value."""
    sm = row.get("stated_minutes")
    try:
        sm = int(sm) if sm not in (None, "") else None
    except (TypeError, ValueError):
        sm = None
    out = {"quote": (row.get("evidence_quote") or "").strip(),
           "locus": (row.get("source_locus") or "").strip(),
           "stated_minutes": sm,
           "stated_minutes_quote": (row.get("stated_minutes_quote") or "").strip()}
    # #254 (v3): the raw per-model READINGS ride the same evidence carry — on a year DISAGREEMENT the
    # fact stores school_year=None and the reviewer sees each model's reading here.
    sy = (row.get("school_year") or "").strip() if row.get("school_year") else ""
    at = (row.get("applies_to") or "").strip() if row.get("applies_to") else ""
    if sy:
        out["school_year"] = sy
    if at:
        out["applies_to"] = at
    return out

def _has_evidence(ev):
    """True if a per-model evidence map carries anything worth persisting (any quote/locus/minutes,
    or a v3 year/scope reading). stated_minutes checks `is not None`, not truthiness (PR #252 review)
    — a parsed 0 is garbage worth SURFACING for review, not silently dropping, matching
    _council_evidence's own zero-safe filter."""
    return any(e["quote"] or e["locus"] or e["stated_minutes"] is not None or e["stated_minutes_quote"]
               or e.get("school_year") or e.get("applies_to")
               for e in ev.values())

def consensus_school_facts(model_rows, judge_rows=None, context=None):
    """model_rows: {model_name: [ {grade_level, start_time, end_time, school_name}, ... ]}.
    Group every model's rows by (band, normalized-school-name); within each group the council
    agrees on START and END separately (cross-family, within TOL). Returns accepted per-school
    facts: [{band, school, start, end, gross, models, method}], plus the rejected/no-consensus.
    judge_rows: optional {model->rows} from the judge model, consulted on a (band,school) with
    no cross-family agreement.

    context (#707): optional deterministic per-rep context that can RESOLVE a degenerate school
    name instead of silently dropping paid cross-family consensus —
      {"band_grain": bool,                  # the record's human label is district_hub_by_band:
                                            #   band referents ARE the expected grain there
       "roster_by_band": {band: [names]}}   # the Stage-1 slot spine; an N=1 band resolves a bare
                                            #   'hs'/'ms' uniquely to its only school
    A resolved degenerate converts ONLY on cross-family VOTER agreement (never the judge — a
    single re-emission must not mint a fact the guard would otherwise refuse), lands with a
    distinguishing method ('band_referent' | 'roster_unique') so gate@8 sees exactly what it is
    (#241's visible-and-confirmable posture), and a band_referent keeps its referent name so the
    #253 combined-scope detector + REQ-146 band-grain projection classify it downstream. A
    degenerate name in a >1-school band with no band-grain label is still refused."""
    # #693: roster-anchored identity resolution at the grouping boundary. The resolver is pure and
    # deterministic (the #716 replay re-derives identical groupings); it changes GROUPING only —
    # consensus thresholds and the judge's non-minting rule are untouched. Resolution info is
    # remembered per resolved key for the fact's identity marking (gate@8 visibility).
    roster_recs = (context or {}).get("roster_recs") or {}
    _rcache = {}

    def _resolve(b, raw_name):
        raw_key = _norm_school(raw_name)
        if not roster_recs or not raw_key:
            return raw_key, None
        if (b, raw_key) not in _rcache:
            _rcache[(b, raw_key)] = resolve_school_identity(raw_key, b, roster_recs)
        return _rcache[(b, raw_key)]

    groups = {}   # (band, nschool) -> {model: [(start_min, end_min, start_raw, end_raw)]}
    ident = {}    # (band, nschool) -> {"school_id","roster_school","rostered_bands",
                  #                     "rules":{raw_key: rule}} | {"rule":"ambiguous",...} | None
    for model, rows in model_rows.items():
        for r in rows:
            b = r.get("grade_level");
            if b not in BANDS: continue
            s, e = _to_min(r.get("start_time")), _to_min(r.get("end_time"))
            e = _normalize_ambiguous_end(s, e)   # #716: 12h echo -> 24h, before clustering
            if s is None or e is None: continue
            rkey, rinfo = _resolve(b, r.get("school_name"))
            key = (b, rkey)
            if rinfo and rinfo.get("school_id"):
                gi = ident.get(key)
                if not (gi and gi.get("school_id")):   # a None/ambiguous placeholder never wins
                    gi = {k: rinfo[k] for k in ("school_id", "roster_school", "rostered_bands")}
                    gi["rules"] = {}
                    ident[key] = gi
                if rinfo["rule"] != "exact":           # exact is the norm, not worth an audit row
                    gi["rules"][rinfo["resolved_from"]] = rinfo["rule"]
            elif key not in ident:
                ident[key] = rinfo     # None (unmatched) or {"rule": "ambiguous", ...}
            groups.setdefault(key, {}).setdefault(model, []).append((s, e, r.get("start_time"), r.get("end_time"), r))
    jgroups = {}
    if judge_rows:
        for model, rows in judge_rows.items():
            for r in rows:
                b = r.get("grade_level")
                if b not in BANDS: continue
                s, e = _to_min(r.get("start_time")), _to_min(r.get("end_time"))
                e = _normalize_ambiguous_end(s, e)   # #716: uniform — judge rows too
                if s is None or e is None: continue
                jkey, _ = _resolve(b, r.get("school_name"))   # judge rows group by the SAME
                jgroups.setdefault((b, jkey), []).append((s, e, r.get("start_time"), r.get("end_time"), r))

    accepted, unresolved = [], []

    # ---- #721: band adjudication by roster placement, BEFORE consensus ----------------------
    # Same resolved school_id claimed under 2+ bands — or unanimously under ONE band the roster
    # says the school does not serve (#779: a unanimous misread must not be silently accepted
    # with a self-contradictory identity). The roster — not the voters — adjudicates:
    # a multiband campus keeps each claimed-and-rostered band; a single-band-rostered school's
    # wrong-band claim folds into its one rostered band; a wrong-band claim against a MULTIband
    # roster has no deterministic destination and surfaces as an explicit band_disagreement.
    # level_collapse names never reach here: their bands resolve to DIFFERENT school_ids (P5).
    # jalias (#781): adjudication moves group keys, but the judge was consulted under the
    # PRE-adjudication key — every kept key remembers its source keys so the tiebreak can still
    # find the judge's answer.
    jalias = {}
    by_sid = {}
    for key, info in ident.items():
        if info and info.get("school_id"):
            by_sid.setdefault(info["school_id"], []).append(key)
    for sid, keys in by_sid.items():
        bands = sorted({b for b, _ in keys})
        rostered = set(ident[keys[0]].get("rostered_bands") or [])
        if not rostered or set(bands) <= rostered and len(bands) < 2:
            continue                       # single claimed band the roster confirms: nothing to do
        adjudication = {"band_adjudication": None, "claimed_bands": bands}

        def _votes_for(band):
            # #780: per kept band, a model's OWN-band votes win; other-band votes are BACKFILL
            # for models absent in this band (Gerlach's cross-band singletons still meet), never
            # an overwrite — a campus whose bands genuinely differ keeps each band's own times,
            # evidence, and v3/v4 readings. Fresh dict per band: no shared object.
            own = groups.get((band, keys[0][1])) or {}
            models = {m for k in keys for m in groups.get(k, {})}
            return {m: list(own.get(m) or [v for k in keys if k[0] != band
                                           for v in (groups.get(k) or {}).get(m, [])])
                    for m in models}

        if len(rostered) > 1:
            keep = [k for k in keys if k[0] in rostered]
            if not keep:
                # #779: unanimous (or split) claims, NONE in a rostered band, 2+ rostered bands:
                # no deterministic destination — surface, never guess.
                starts = {f"{m} [{k[0]}]": v[0][2] for k in keys for m, v in groups[k].items()}
                ends = {f"{m} [{k[0]}]": v[0][3] for k in keys for m, v in groups[k].items()}
                unresolved.append({"band": bands[0], "school": keys[0][1],
                                   "reason": "band_disagreement", "starts": starts, "ends": ends,
                                   "identity": {"claimed_bands": bands,
                                                "rostered_bands": sorted(rostered),
                                                "school_id": sid,
                                                "roster_school": ident[keys[0]].get("roster_school")}})
                for k in keys:
                    del groups[k]
                continue
            adjudication["band_adjudication"] = "roster_multiband"
        else:
            # single-band rostered: the roster band wins; a claim in a band the school does not
            # serve is a voter attribute error, not a second school (#779: including UNANIMOUS)
            tb = next(iter(rostered))
            keep = [(tb, keys[0][1])]
            adjudication["band_adjudication"] = "roster_band"
            ident.setdefault(keep[0], ident[keys[0]])
        new_votes = {k: _votes_for(k[0]) for k in keep}      # build BEFORE mutating groups
        for key in keys:
            if key not in keep:
                del groups[key]
        for key in keep:
            groups[key] = new_votes[key]
            ident[key] = {**ident[key], **adjudication}
            jalias[key] = [k for k in keys if k != key]

    # ---- #721 option 3: unmatched same-name cross-band singletons become ONE visible row -----
    # No roster to adjudicate with (hub docs, 91% of unmatched — findings report §4): the loss is
    # made explicit and human-adjudicable instead of two ordinary-looking no-consensus rows.
    # Gated on roster_recs (#778): a no-context caller (council lab) must stay byte-identical —
    # the same contract the screen and marking already honor. Only TRULY-unmatched keys sweep
    # (#784): an 'ambiguous' resolution is a name-disambiguation problem carrying its candidate
    # list — collapsing it to claimed_bands would discard exactly what the reviewer needs.
    unmatched_by_name = {}
    if roster_recs:
        for (b, k), info in ident.items():
            # strict-degenerate keys ('junior high school', '') are GENERIC REFERENTS, not one
            # school claimed in two bands — they belong to the #245 guard / #707 resolution
            # downstream, and sweeping them would shadow the more specific
            # degenerate_school_name reason (found replaying 4222860, findings report §9).
            if info is None and (b, k) in groups and _norm_school_strict(k):
                unmatched_by_name.setdefault(k, []).append((b, k))
    for k, keys in unmatched_by_name.items():
        singles = [key for key in keys if len(groups[key]) == 1]
        if len(singles) < 2 or len({b for b, _ in singles}) < 2:
            continue
        # #785: keyed (model [band]) — a model claiming the same name under TWO bands keeps both
        # votes in the audit trail; a model-keyed dict silently overwrote the earlier band's.
        starts = {f"{m} [{key[0]}]": v[0][2] for key in singles for m, v in groups[key].items()}
        ends = {f"{m} [{key[0]}]": v[0][3] for key in singles for m, v in groups[key].items()}
        unresolved.append({"band": sorted(b for b, _ in singles)[0], "school": k,
                           "reason": "band_disagreement",
                           "starts": starts, "ends": ends,
                           "identity": {"claimed_bands": sorted({b for b, _ in singles})}})
        for key in singles:
            del groups[key]
    for (band, nschool), per_model in groups.items():
        # #245: a group whose normalized name is empty or purely generic (e.g. an extracted
        # school_name of "" or "Schools") is not a real, distinct school — the #236 empty-key guard
        # deliberately keeps nschool non-empty for these (so two pathological all-stopword names don't
        # collide), which would otherwise let this junk reach `accepted` and inflate a band's school
        # list/count. Route it to unresolved instead — auditable, not a silent drop — matching the
        # manual-gate posture. norm_school_strict is the falsy-on-junk form (no empty-key fallback).
        degenerate = not _norm_school_strict(nschool)
        resolution = None                      # #707: (method, resolved_school_name) or None
        if degenerate and context:
            roster = (context.get("roster_by_band") or {}).get(band) or []
            if context.get("band_grain") and nschool:
                # a district_hub_by_band record's band referent IS the expected grain — keep the
                # referent name; the #253/REQ-146 machinery classifies + projects it downstream.
                # (nschool truthy: a fully-EMPTY extracted name stays junk even on a hub — #245.)
                resolution = ("band_referent", nschool)
            elif len(roster) == 1:
                # the slot spine holds the unique resolution: 'hs' in a one-high-school district
                resolution = ("roster_unique", _norm_school(roster[0]))
        if degenerate and resolution is None:
            unresolved.append({"band": band, "school": nschool, "reason": "degenerate_school_name",
                               "starts": {m: v[0][2] for m, v in per_model.items()},
                               "ends": {m: v[0][3] for m, v in per_model.items()}})
            continue
        # one (start,end) per model for this school (first/representative)
        starts = [(m, v[0][0]) for m, v in per_model.items()]
        ends   = [(m, v[0][1]) for m, v in per_model.items()]
        sc, ec = _cluster(starts), _cluster(ends)
        s_ok = len(sc[0]["members"]) >= 2 and _cross_family(sc[0]["members"]) >= 2
        e_ok = len(ec[0]["members"]) >= 2 and _cross_family(ec[0]["members"]) >= 2
        method = "council_agree"
        if degenerate and not (s_ok and e_ok):
            # #707: a resolved degenerate converts ONLY on cross-family voter agreement — never
            # the judge (a single re-emission must not mint what the guard would refuse)
            unresolved.append({"band": band, "school": nschool, "reason": "degenerate_school_name",
                               "starts": {m: v[0][2] for m, v in per_model.items()},
                               "ends": {m: v[0][3] for m, v in per_model.items()}})
            continue
        # judge tiebreak on the pair. #781: band adjudication may have MOVED this group's key —
        # the judge answered under the band it was actually consulted on, so the pre-adjudication
        # source keys (jalias) are checked when the adjudicated key itself has no judge row.
        jkey = next((cand for cand in [(band, nschool)] + jalias.get((band, nschool), [])
                     if cand in jgroups), None)
        if not (s_ok and e_ok) and jkey is not None:
            js, je = jgroups[jkey][0][0], jgroups[jkey][0][1]
            start_m, end_m, method = js, je, "judge"
            models = ["judge"]
            ev = {"judge": _evidence_of(jgroups[jkey][0][4])}
            meta_rows = [jgroups[jkey][0][4]]
        elif s_ok and e_ok:
            start_m = round(mean([v for _, v in sc[0]["members"]]))
            end_m   = round(mean([v for _, v in ec[0]["members"]]))
            models = sorted({m for m, _ in sc[0]["members"]} | {m for m, _ in ec[0]["members"]})
            ev = {m: _evidence_of(per_model[m][0][4]) for m in models if m in per_model}
            meta_rows = [per_model[m][0][4] for m in sorted(per_model)]
        else:
            unresolved.append({"band": band, "school": nschool,
                               "starts": {m: v[0][2] for m, v in per_model.items()},
                               "ends": {m: v[0][3] for m, v in per_model.items()}})
            continue
        gross = end_m - start_m
        if not is_plausible(gross):
            unresolved.append({"band": band, "school": nschool, "gross": gross, "reason": "implausible"}); continue
        info = ident.get((band, nschool))
        # #693 rung 4: an unmatched name that pattern-matches an excluded school type routes to
        # unresolved — auditable, off the band mode, never silently dropped. Gated on roster_recs:
        # a no-roster context (council_lab benchmark runs, roster-load failure) screens nothing,
        # matching the resolver's own no-roster no-op. Rung 5: an unmatched CLEAN name survives
        # as the name-in-lieu identity, marked so gate@8 sees it and no roster slot fills from it.
        # #789: the screen reads the RAW extracted names (the page's own words) — the norm key
        # has already stripped 'academy'/'school', so a phrase like 'virtual academy' can never
        # match it.
        if not degenerate and roster_recs and info is None and any(
                _EXCLUDED_NAME.search(f" {_base_name(v[0][4].get('school_name') or '')} ")
                for v in per_model.values()):
            unresolved.append({"band": band, "school": nschool, "reason": "excluded_school_type",
                               "starts": {m: v[0][2] for m, v in per_model.items()},
                               "ends": {m: v[0][3] for m, v in per_model.items()}})
            continue
        school_out = nschool
        if degenerate:
            # #707: the resolution's method REPLACES council_agree so gate@8 sees exactly what
            # this is; roster_unique also rewrites the name to the band's only roster school
            # (filling its slot); band_referent keeps the referent for the #253/REQ-146 detectors.
            method, school_out = resolution[0], resolution[1]
        fact = {"band": band, "school": school_out,
                "start": f"{start_m//60:02d}:{start_m%60:02d}",
                "end": f"{end_m//60:02d}:{end_m%60:02d}",
                "gross": gross, "models": models, "method": method}
        if degenerate:
            fact["resolved_from"] = nschool    # the raw referent, auditable on the fact itself
        elif roster_recs:
            # #693/#721 identity marking (v5, persisted to identity_json): what the roster said
            # about this fact's school, so gate@8 sees merges/ambiguity/unmatched — attached only
            # when a roster was consulted, so no-context callers stay byte-identical.
            if info and info.get("school_id"):
                fact["identity"] = {k: v for k, v in info.items() if k != "rules" or v}
            elif info and info.get("rule") == "ambiguous":
                fact["identity"] = info
            else:
                fact["identity"] = {"roster": "unmatched"}
        if _has_evidence(ev):   # only v2+ rows carry it; v1 accepted facts stay byte-identical
            fact["evidence"] = ev
        # #254 (v3): categorical corroboration — NEVER part of the (band, norm_school) grouping key
        # and never a vote on times. school_year = the consensus reading when ALL models that read a
        # PARSEABLE year agree (deterministic parse — the model's formatting is never trusted);
        # disagreement -> no year on the fact, per-model readings stay in evidence above.
        # applies_to = "multiple" when ANY model read a group-of-schools scope (a scope warning is a
        # warning — OR semantics). Keys attached only when read, so pre-v3 facts stay byte-identical.
        years = {parse_school_year(r.get("school_year")) for r in meta_rows}
        years.discard(None)
        if len(years) == 1:
            fact["school_year"] = format_school_year(years.pop())
        if any(str(r.get("applies_to") or "").strip().lower() == "multiple" for r in meta_rows):
            fact["applies_to"] = "multiple"
        # #499 (v4, REQ-148): campus_names = the sorted UNION of the verbatim names any model read
        # off the page (recall over precision here — downstream matching is deterministic against
        # the roster, so a hallucinated/garbled name simply matches nothing; nothing arithmetic
        # ever touches these). Attached only when non-empty — pre-v4 facts stay byte-identical.
        camps = sorted({str(c).strip() for r in meta_rows
                        for c in (r.get("campus_names") or []) if str(c).strip()})
        if camps:
            fact["campus_names"] = camps
        accepted.append(fact)
    return accepted, unresolved

def merge_fact_runs(facts, *, with_superseded=False):
    """Cumulative Stage-7 truth across a district's production runs (REQ-122, #232): follow-up
    rounds FILL GAPS, they never regress solid signal advancing to Stage 8. `facts`: school_fact
    dicts from ANY number of runs, each carrying `extraction_id` (run order), `band`, `school`,
    `status` (+ optionally the v3 `school_year` reading). Returns (accepted, unresolved) — or
    (accepted, unresolved, superseded) when `with_superseded` — deduped per (band, school):
      - an ACCEPTED fact beats any unresolved for the same school, in either run order — a later
        thin retry cannot knock out an earlier solid extraction (the Brownsville 7→0 case);
      - among multiple ACCEPTED, PROVENANCE first (#662): a fact from honest production work
        supersedes one whose representation was benchmark-injected (`benchmark_provenance` truthy on
        the row, set by the caller), for the same school, regardless of run order or year. An
        injected artifact is a deliberately-older curated document that was never release data, so
        it must never outrank a real reading — and it cannot be beaten on the year axis below,
        because those artifacts overwhelmingly carry no parseable year at all (measured: 957 of 957).
        Rows with no `benchmark_provenance` key are all honest, so this axis is inert for every
        existing caller. It applies only when the group holds BOTH kinds — an all-injected group is
        left alone rather than emptied;
      - among multiple ACCEPTED (#254, the Santa Fe stale-page case): a fact with a known, MORE
        RECENT parseable school_year supersedes a fact with a known OLDER one, regardless of
        extraction order. Precedence applies ONLY between two KNOWN years (Ian, 2026-07-14:
        unknown-year facts COEXIST — every pre-v3 fact is unknown, and absence of a printed year
        is never evidence of staleness); ties and unknown cases fall through unchanged to
      - the EARLIEST run wins (fill-gaps-not-overwrite; correcting a solid fact is a gate@8 human
        determination, never a silent later-run override);
      - among UNRESOLVED only: the LATEST run wins (the freshest disagreement diagnostic).
    Year-superseded facts are KEPT, not dropped — the third return list — so the closing argument
    can surface WHY the stale rows left the mode (no-silent-caps). The never-regress rule is
    untouched: year precedence only ever compares accepted vs accepted.
    Pure + deterministic + order-independent (a group's winner is selected set-wise, not by a
    pairwise fold — a known-vs-known / known-vs-unknown / eid triangle would otherwise make the
    outcome depend on row order); output sorted by (band, school). The caller supplies rows from
    run_kind='production' extractions only.

    The dedup key RE-NORMALIZES the stored school string through the CURRENT norm_school (PR #247
    review): school_fact.school is persisted at extraction time, so rows written under an older
    stopword list carry a stale key ('lincoln unified district' vs today's 'lincoln') — exact-string
    matching would treat the same physical school as two, fragmenting the cross-run merge with no
    backfill path. norm_school is idempotent, so re-normalizing current-vintage keys is a no-op."""
    groups = {}
    for f in facts:
        groups.setdefault((f["band"], _norm_school(f["school"])), []).append(f)
    best, superseded = {}, []
    for key, rows in groups.items():
        acc = [f for f in rows if f["status"] == "accepted"]
        if acc:
            # #662, and it runs BEFORE the year axis on purpose: an injected `gt://` artifact carries
            # a deliberately-older school year and was never release data, so honest production work
            # must beat it whatever either side's year says. Losing rows are KEPT (superseded), never
            # dropped — the closing argument surfaces WHY they left the mode (no-silent-caps).
            honest = [f for f in acc if not f.get("benchmark_provenance")]
            if honest and len(honest) < len(acc):
                superseded.extend(f for f in acc if f.get("benchmark_provenance"))
                acc = honest
            known = [y for f in acc if (y := parse_school_year(f.get("school_year"))) is not None]
            newest = max(known) if known else None
            survivors, losers = [], []
            for f in acc:
                y = parse_school_year(f.get("school_year"))
                (losers if (y is not None and y < newest) else survivors).append(f)
            superseded.extend(losers)
            # earliest accepted stands among the survivors; min() is stable, so two rows from the
            # SAME run keep the first row seen (the strict-< behavior the PR #221 mutants pinned)
            best[key] = min(survivors, key=lambda f: f["extraction_id"])
        else:
            best[key] = max(rows, key=lambda f: f["extraction_id"])   # freshest diagnostic
    key_fn = lambda f: (f["band"], f["school"])  # noqa: E731
    out = (sorted((f for f in best.values() if f["status"] == "accepted"), key=key_fn),
           sorted((f for f in best.values() if f["status"] != "accepted"), key=key_fn))
    if with_superseded:
        return out + (sorted(superseded, key=lambda f: (f["band"], f["school"], f["extraction_id"])),)
    return out


def detect_year_conflicts(facts):
    """#254 detect-and-flag: the (band, norm_school) groups whose ACCEPTED facts mix school-year
    knowledge — two different KNOWN years (which precedence resolves; `resolved` True) or a
    known/unknown mix (which COEXISTS unresolved; `resolved` False) — so the gate@8 reviewer sees
    every ambiguity, including the ones the automation handled. Each side carries its
    `source_file` as a FORMAT HINT for the human (Ian, 2026-07-14: a hint surfaced, never an
    automatic rule — Santa Fe's own stale facts came from a live webpage). Input = the same raw
    cross-run rows merge_fact_runs consumes; pure + deterministic."""
    groups = {}
    for f in facts:
        if f["status"] != "accepted":
            continue
        groups.setdefault((f["band"], _norm_school(f["school"])), []).append(f)
    out = []
    for (band, nschool), rows in sorted(groups.items()):
        parsed = [parse_school_year(f.get("school_year")) for f in rows]
        known = {y for y in parsed if y is not None}
        n_unknown = sum(1 for y in parsed if y is None)
        if len(known) < 1 or (len(known) == 1 and n_unknown == 0):
            continue                       # all-unknown, or one known year across the board: no mix
        out.append({"band": band, "school": nschool,
                    "years": sorted(format_school_year(y) for y in known),
                    "mixes_unknown": n_unknown > 0,
                    # two distinct KNOWN years resolve by precedence; a known/unknown mix coexists
                    "resolved": len(known) >= 2 and n_unknown == 0,
                    "sides": [{"extraction_id": f["extraction_id"],
                               "school_year": f.get("school_year"),
                               "gross": f.get("gross_minutes"),
                               "source_file": f.get("source_file")} for f in rows]})
    return out


def degenerate_school_facts(accepted):
    """#245: the accepted facts whose school name is degenerate — empty, or normalizes to nothing
    distinguishing under norm_school_strict (purely generic/stopword tokens, e.g. 'schools'). These are
    extraction noise, not a real distinct school; left in a band's rollup they inflate `n_schools` and
    pollute `schools[]` (found validating #236 against real Stage-7 data: Elmbrook, district 5501770,
    middle band, carried an accepted fact named bare 'schools'). `consensus_school_facts` now routes new
    facts like this to `unresolved` instead of `accepted` at extraction time — but a fact persisted
    BEFORE that fix already sits in the DB as accepted, so `district_bands_from_facts`/
    `detect_single_school_over_extraction` both filter through this same predicate at read time
    (self-healing, the same pattern `merge_fact_runs` uses for stale-vintage norm_school keys — no
    backfill needed). Returns the excluded facts themselves so a caller can surface them for human
    review (detect-and-flag, never a silent drop — the #237 detector's posture).
    #730: stays the exact complement of _clean_school_facts — a #707 band_referent resolution is
    NOT degenerate noise (it must never appear here while also voting in the band rollup)."""
    return [f for f in accepted
            if not (_norm_school_strict(f.get("school", "")) or f.get("method") == "band_referent")]


def _clean_school_facts(accepted):
    """The complement of degenerate_school_facts (#245) — what district_bands_from_facts and
    detect_single_school_over_extraction actually aggregate/count distinct schools over.

    #730 (#707 review): a `band_referent` fact DELIBERATELY keeps its degenerate referent name —
    consensus resolved it via the record's district_hub_by_band label, so re-deriving degeneracy
    from the school string here would silently drop the very fact #707 accepted (the band then
    reads as having no evidence at all, at every call site: the run rollup, gate@7, gate@8's
    closing argument, and the reaggregate replay). The #245 junk class this filter exists for is
    UNRESOLVED noise; a method-marked resolution is not noise. (`roster_unique` rewrites to a real
    roster name and passes the strict check on its own.)"""
    return [f for f in accepted
            if _norm_school_strict(f.get("school", "")) or f.get("method") == "band_referent"]


def _dedupe_resolved_aliases(accepted):
    """#733 (#707 review): a `roster_unique` fact is a RESOLVED ALIAS of its band's only school.
    When the pool also holds a directly-named fact for the same (band, school) — the common shape:
    a main page naming 'Lewiston High School' plus a hub page saying just 'HS', extracted as two
    reps — the alias must not double-vote in the mode or inflate n_schools past the roster (the
    direct reading is the stronger evidence and wins). Two roster_unique aliases of the same
    school keep only the first (deterministic by pool order). Non-roster_unique facts are
    untouched, preserving the pre-#707 behavior exactly."""
    directs = {(f["band"], f["school"]) for f in accepted if f.get("method") != "roster_unique"}
    seen_aliases, out = set(), []
    for f in accepted:
        if f.get("method") == "roster_unique":
            key = (f["band"], f["school"])
            if key in directs or key in seen_aliases:
                continue
            seen_aliases.add(key)
        out.append(f)
    return out


def district_bands_from_facts(accepted):
    """Mode (deterministic) over accepted per-school gross values, per band. Returns
    {band: {gross_minutes, start, end, n_schools, method, schools:[...]}}. Facts with a degenerate
    school name (#245) are excluded from both the count and the value — see degenerate_school_facts()
    to get the excluded facts for review — EXCEPT a #707 band_referent resolution (#730), which
    votes once for its band; and a roster_unique alias never double-counts its school (#733)."""
    accepted = _dedupe_resolved_aliases(_clean_school_facts(accepted))
    out = {}
    for band in BANDS:
        facts = [f for f in accepted if f["band"] == band]
        if not facts: continue
        grosses = [f["gross"] for f in facts]
        val, method = aggregate_band(grosses)
        # #403: aggregate_band ignores None VALUES, so val is None only when every fact's gross is
        # None — nothing aggregable, omit the band (same posture as an empty band). A None-gross fact
        # must not crash (or win) the representative min() below; it stays in schools[] though — it's
        # an accepted fact, and hiding it would be a silent drop.
        if val is None: continue
        # representative start/end = those of a school whose gross is closest to the value
        rep = min((f for f in facts if f["gross"] is not None),
                  key=lambda f: abs(f["gross"] - val))
        # #627 INVARIANT: a band that carries representative times must be internally consistent —
        # its gross MUST equal the span of those times, or Stage 9's bell_schedules cross-check
        # (minutes ≤ end−start) fails loud. A mean_tiebreak VALUE is a synthetic average that
        # matches NO single school's schedule (the two tied schools have distinct spans), so the
        # rep's span != val; emit the value WITHOUT representative times (per-school real times stay
        # in schools[] below). Every other method takes a single school's (start,end,gross) verbatim,
        # so rep["gross"] == val and the times are kept.
        keep_times = method != "mean_tiebreak" and rep["gross"] == val
        rep_start = rep["start"] if keep_times else None
        rep_end = rep["end"] if keep_times else None
        out[band] = {"gross_minutes": val, "start_time": rep_start, "end_time": rep_end,
                     "n_schools": len(facts), "method": method,
                     "schools": [{"school": f["school"], "start_time": f["start"], "end_time": f["end"],
                                  "gross": f["gross"], "models": f["models"],
                                  "human_determination": ""}   # USER verifies each school's start/end here
                                 for f in facts]}
    return out


def detect_single_school_over_extraction(accepted, nces_school_count, roster_names=None):
    """Cross-LEA contamination detector (#237). A single-school LEA (NCES school count == 1) that
    yields MORE THAN ONE distinct school is contaminated: a charter-network campus (its own 1-school
    LEA) whose siblings' schedules were pulled from a shared CMO website (e.g. ascendlearning.org
    serves all 12 Ascend campuses), or a blank-domain unscoped capture (the Millard #227 class).
    Detection is reliable — a 1-school LEA cannot legitimately have >1 school. Picking WHICH school is
    the real one is NOT reliable (shared network names like 'ascend' recur across every sibling;
    acronyms like 'DECA' == 'Dayton Early College Academy' fail a name match), so this FLAGS for human
    review and does NOT auto-reject — matching the manual-gate posture. `roster_matched` is the one
    trustworthy keeper hint (the LEA's own Stage-1 roster), surfaced when available. Returns None when
    not applicable (not a single-school LEA, or only one distinct school extracted).

    `accepted`: per-school fact dicts whose 'school' was norm_school-normalized at WRITE time — the
    distinct-count re-normalizes through the CURRENT function so a stopword-list change can't split
    one school into two stale-vintage keys (a false contamination flag; norm_school is idempotent so
    current keys pass through unchanged). Degenerate-named facts (#245 — empty or purely-generic, e.g.
    'schools') are excluded before counting: an empty/junk name is not itself a real distinct school,
    and counting it would produce a FALSE contamination flag on an otherwise-clean single-school LEA
    (one real school + one piece of extraction noise reading as "2 distinct schools"). The roster is
    filtered through norm_school_strict: an all-stopword roster entry (a scraped 'School District'
    header) is junk, not a matchable school — the plain form's empty-key fallback would smuggle it
    through as a roster_matched keeper hint. `roster_names`: the LEA's Stage-1 schools_by_band school
    names, if available (the allow-list)."""
    if nces_school_count != 1:
        return None
    distinct = sorted({_norm_school(f["school"]) for f in _clean_school_facts(accepted) if f.get("school")})
    if len(distinct) <= 1:
        return None
    roster = {k for r in (roster_names or []) if (k := _norm_school_strict(r))}
    return {
        "suspected": True,
        "reason": "single_school_lea_over_extraction",
        "n_distinct_schools": len(distinct),
        "distinct_schools": distinct,
        "roster_matched": [k for k in distinct if k in roster],  # reliable keepers when roster present
    }
