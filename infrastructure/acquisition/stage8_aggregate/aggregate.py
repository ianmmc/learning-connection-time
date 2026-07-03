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

def _to_min(t):
    if not t: return None
    m = _re.match(r"\s*(\d{1,2}):(\d{2})", str(t))
    if not m: return None
    return int(m.group(1)) * 60 + int(m.group(2))

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
            groups.setdefault(key, {}).setdefault(model, []).append((s, e, r.get("start_time"), r.get("end_time")))
    jgroups = {}
    if judge_rows:
        for model, rows in judge_rows.items():
            for r in rows:
                b = r.get("grade_level")
                if b not in BANDS: continue
                s, e = _to_min(r.get("start_time")), _to_min(r.get("end_time"))
                if s is None or e is None: continue
                jgroups.setdefault((b, _norm_school(r.get("school_name"))), []).append((s, e, r.get("start_time"), r.get("end_time")))

    accepted, unresolved = [], []
    for (band, nschool), per_model in groups.items():
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
        elif s_ok and e_ok:
            start_m = round(mean([v for _, v in sc[0]["members"]]))
            end_m   = round(mean([v for _, v in ec[0]["members"]]))
            models = sorted({m for m, _ in sc[0]["members"]} | {m for m, _ in ec[0]["members"]})
        else:
            unresolved.append({"band": band, "school": nschool,
                               "starts": {m: v[0][2] for m, v in per_model.items()},
                               "ends": {m: v[0][3] for m, v in per_model.items()}})
            continue
        gross = end_m - start_m
        if not (PLAUSIBLE[0] <= gross <= PLAUSIBLE[1]):
            unresolved.append({"band": band, "school": nschool, "gross": gross, "reason": "implausible"}); continue
        accepted.append({"band": band, "school": nschool,
                         "start": f"{start_m//60:02d}:{start_m%60:02d}",
                         "end": f"{end_m//60:02d}:{end_m%60:02d}",
                         "gross": gross, "models": models, "method": method})
    return accepted, unresolved

def district_bands_from_facts(accepted):
    """Mode (deterministic) over accepted per-school gross values, per band. Returns
    {band: {gross_minutes, start, end, n_schools, method, schools:[...]}}."""
    out = {}
    for band in BANDS:
        facts = [f for f in accepted if f["band"] == band]
        if not facts: continue
        grosses = [f["gross"] for f in facts]
        val, method = aggregate_band(grosses)
        # representative start/end = those of a school whose gross is closest to the modal value
        rep = min(facts, key=lambda f: abs(f["gross"] - val))
        out[band] = {"gross_minutes": val, "start_time": rep["start"], "end_time": rep["end"],
                     "n_schools": len(facts), "method": method,
                     "schools": [{"school": f["school"], "start_time": f["start"], "end_time": f["end"],
                                  "gross": f["gross"], "models": f["models"],
                                  "human_determination": ""}   # USER verifies each school's start/end here
                                 for f in facts]}
    return out
