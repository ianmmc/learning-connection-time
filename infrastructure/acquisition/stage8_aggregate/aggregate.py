"""Per-school -> district band aggregation + Path-1 council accept logic + mode-stability early-exit.

Pure logic, no I/O. Consumes per-school extractions (each: {band: net_minutes}) and produces
a district band value with the rule decided in ACQUISITION_PIPELINE.md:

  - Within a school, the COUNCIL decides the school's per-band value (cross-family agreement
    within TOL; judge breaks ties). See council_school().
  - Across schools, the district band value is the MODAL school value (ties/uncertain -> MEAN).
  - Mode-stability early-exit: stop sampling a band once the running mode is stable.

Cross-family agreement (the family buckets) uses the canonical map in
`common.model_families`, keyed by FULL OpenRouter model id — the ids the live Stage-7 path passes.
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

def council_school(votes, judge=None):
    """votes: {model: {band: minutes}}; judge: optional callable(band)->minutes (re-reads page).
    Returns {band: {"value": int|None, "consensus_models": [...], "method": str}} per band.
    Accept when a cluster has >=2 CROSS-FAMILY members within TOL; else judge; else None (fallback)."""
    out = {}
    for band in BANDS:
        vals = [(m, sch[band]) for m, sch in votes.items() if sch.get(band) is not None]
        if not vals:
            out[band] = {"value": None, "consensus_models": [], "method": "no_extraction"}; continue
        clusters = _cluster(vals)
        top = clusters[0]
        if len(top["members"]) >= 2 and _cross_family(top["members"]) >= 2:
            val = round(mean([v for _, v in top["members"]]))
            out[band] = {"value": val, "consensus_models": [m for m, _ in top["members"]], "method": "council_agree"}
        elif judge is not None:
            jv = judge(band)
            if jv is not None and PLAUSIBLE[0] <= jv <= PLAUSIBLE[1]:
                out[band] = {"value": jv, "consensus_models": ["judge"], "method": "judge"}
            else:
                out[band] = {"value": None, "consensus_models": [], "method": "judge_implausible"}
        else:
            out[band] = {"value": None, "consensus_models": [], "method": "no_consensus"}
    return out

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
# #638: ONE canonical HH:MM parser (was a private copy here + another in stage9 provenance).
from infrastructure.acquisition.common.timeutil import hhmm_to_min as _to_min

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

def consensus_school_facts(model_rows, judge_rows=None):
    """model_rows: {model_name: [ {grade_level, start_time, end_time, school_name}, ... ]}.
    Group every model's rows by (band, normalized-school-name); within each group the council
    agrees on START and END separately (cross-family, within TOL). Returns accepted per-school
    facts: [{band, school, start, end, gross, models, method}], plus the rejected/no-consensus.
    judge_rows: optional {model->rows} from the judge model, consulted on a (band,school) with
    no cross-family agreement."""
    groups = {}   # (band, nschool) -> {model: [(start_min, end_min, start_raw, end_raw)]}
    for model, rows in model_rows.items():
        for r in rows:
            b = r.get("grade_level");
            if b not in BANDS: continue
            s, e = _to_min(r.get("start_time")), _to_min(r.get("end_time"))
            if s is None or e is None: continue
            key = (b, _norm_school(r.get("school_name")))
            groups.setdefault(key, {}).setdefault(model, []).append((s, e, r.get("start_time"), r.get("end_time"), r))
    jgroups = {}
    if judge_rows:
        for model, rows in judge_rows.items():
            for r in rows:
                b = r.get("grade_level")
                if b not in BANDS: continue
                s, e = _to_min(r.get("start_time")), _to_min(r.get("end_time"))
                if s is None or e is None: continue
                jgroups.setdefault((b, _norm_school(r.get("school_name"))), []).append((s, e, r.get("start_time"), r.get("end_time"), r))

    accepted, unresolved = [], []
    for (band, nschool), per_model in groups.items():
        # #245: a group whose normalized name is empty or purely generic (e.g. an extracted
        # school_name of "" or "Schools") is not a real, distinct school — the #236 empty-key guard
        # deliberately keeps nschool non-empty for these (so two pathological all-stopword names don't
        # collide), which would otherwise let this junk reach `accepted` and inflate a band's school
        # list/count. Route it to unresolved instead — auditable, not a silent drop — matching the
        # manual-gate posture. norm_school_strict is the falsy-on-junk form (no empty-key fallback).
        if not _norm_school_strict(nschool):
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
        if not (s_ok and e_ok) and (band, nschool) in jgroups:   # judge tiebreak on the pair
            js, je = jgroups[(band, nschool)][0][0], jgroups[(band, nschool)][0][1]
            start_m, end_m, method = js, je, "judge"
            models = ["judge"]
            ev = {"judge": _evidence_of(jgroups[(band, nschool)][0][4])}
            meta_rows = [jgroups[(band, nschool)][0][4]]
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
        fact = {"band": band, "school": nschool,
                "start": f"{start_m//60:02d}:{start_m%60:02d}",
                "end": f"{end_m//60:02d}:{end_m%60:02d}",
                "gross": gross, "models": models, "method": method}
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
    review (detect-and-flag, never a silent drop — the #237 detector's posture)."""
    return [f for f in accepted if not _norm_school_strict(f.get("school", ""))]


def _clean_school_facts(accepted):
    """The complement of degenerate_school_facts (#245) — what district_bands_from_facts and
    detect_single_school_over_extraction actually aggregate/count distinct schools over."""
    return [f for f in accepted if _norm_school_strict(f.get("school", ""))]


def district_bands_from_facts(accepted):
    """Mode (deterministic) over accepted per-school gross values, per band. Returns
    {band: {gross_minutes, start, end, n_schools, method, schools:[...]}}. Facts with a degenerate
    school name (#245) are excluded from both the count and the value — see degenerate_school_facts()
    to get the excluded facts for review."""
    accepted = _clean_school_facts(accepted)
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
