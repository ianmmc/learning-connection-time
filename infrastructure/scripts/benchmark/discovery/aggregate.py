"""Per-school -> district band aggregation + Path-1 council accept logic + mode-stability early-exit.

Pure logic, no I/O. Consumes per-school extractions (each: {band: net_minutes}) and produces
a district band value with the rule decided in ACQUISITION_PIPELINE.md:

  - Within a school, the COUNCIL decides the school's per-band value (cross-family agreement
    within TOL; judge breaks ties). See council_school().
  - Across schools, the district band value is the MODAL school value (ties/uncertain -> MEAN).
  - Mode-stability early-exit: stop sampling a band once the running mode is stable.

Family buckets (must be cross-family for agreement to count):
  google: gemini-2.5-flash, gemini-2.5-flash-lite | mistral: mistral-small-24b, mistral-large-2512
  deepseek: deepseek-v3.2 | qwen: qwen3-235b
"""
from collections import Counter
from statistics import mean

TOL = 15          # minutes: two values "agree" if within +/-TOL
BANDS = ("elementary", "middle", "high")
PLAUSIBLE = (240, 480)   # net instructional minutes/day sanity gate

FAMILY = {
    "gemini-2.5-flash": "google", "gemini-2.5-flash-lite": "google",
    "mistral-small-24b": "mistral", "mistral-large-2512": "mistral",
    "deepseek-v3.2": "deepseek", "qwen3-235b": "qwen",
}
def family(model): return FAMILY.get(model, model)

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
    """school_values: list of accepted per-school minutes for ONE band -> district value.
    Modal (within TOL grid); if no clear plurality (tie), fall back to arithmetic mean."""
    vals = [v for v in school_values if v is not None]
    if not vals: return None, "no_schools"
    clusters = _cluster([("_", v) for v in vals])
    if len(clusters) >= 2 and len(clusters[0]["members"]) == len(clusters[1]["members"]):
        return round(mean(vals)), "mean_tiebreak"        # ambiguous mode -> mean
    return round(clusters[0]["center"]), "modal"

def aggregate_district(per_school):
    """per_school: list of {band: accepted_minutes}. Returns {band: {value, method, n}}."""
    out = {}
    for band in BANDS:
        sv = [s.get(band) for s in per_school if s.get(band) is not None]
        val, method = aggregate_band(sv)
        out[band] = {"value": val, "method": method, "n": len(sv)}
    return out
