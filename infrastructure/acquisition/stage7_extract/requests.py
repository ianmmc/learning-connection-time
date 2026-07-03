"""Stage 7 — the request-more-evidence loop: DETECTION + ROUTING (REQ-117, STAGE7 §4).

When the council can't confidently answer, the pipeline gets more evidence via the cyclic back-edges
(7→6/3/2/1). Per the decided design (Ian, 2026-07-03): **detection + routing are deterministic
scripts, not the model** — auditable, local, zero OpenRouter cost (the REQ-054 read-vs-decide split,
extended to routing). This module is that script: pure, no DB, no network, fully unit-testable. It
reads an extraction *outcome* + signals we already hold and emits routed **request objects**; the
app layer (`process_governance/stage7_run.py`) supplies the DB-derived inputs and executes/persists.

Three altitudes (the pipeline's own hierarchy):
  - **representation** — a sent rep yielded 0 usable facts, but *another captured rep of the same URL
    exists* → **7→6** (re-dispatch the alternate, e.g. text→vision; no new capture).
  - **URL** — a sent rep yielded 0 facts and *no alternate rep exists* → **7→3** (recapture the URL).
  - **district** — a *claimed band* (from the NCES/LEA span) has 0 accepted facts across all URLs →
    **7→2** (targeted rediscover for that band / **7→1** add schools).

Benchmark note: for `batch_type == "benchmark"` (batch_00000) the routes don't *execute* (the batch
is walled off, and its reps are frozen `gt://` artifacts with no alternates/recapture) — but the
detection is still valid and is exactly how we test this logic against a known corpus.
"""
from __future__ import annotations

BANDS = ("elementary", "middle", "high")

# route labels (the cyclic back-edges) — kept as literals so the persisted request is self-describing
ROUTE_ALT_REP = "7->6"      # re-dispatch a different already-captured rep of the same URL
ROUTE_RECAPTURE = "7->3"    # recapture the URL (no alternate rep)
ROUTE_REDISCOVER = "7->2"   # targeted discovery for a missing band
ROUTE_ADD_SCHOOLS = "7->1"  # follow-up batch adding specific schools


def _accepted_by_record(result: dict) -> dict:
    """rec_key → count of accepted facts across its reps."""
    counts: dict = {}
    for rep in result.get("reps", []):
        counts[rep["rec_key"]] = counts.get(rep["rec_key"], 0) + len(rep.get("accepted") or [])
    return counts


def _sent_file(result: dict) -> dict:
    """rec_key → the file we sent (first rep seen) — for the request's human reason."""
    out: dict = {}
    for rep in result.get("reps", []):
        out.setdefault(rep["rec_key"], rep.get("file"))
    return out


def _bands_with_facts(result: dict) -> set:
    return {f.get("band") for f in (result.get("accepted") or []) if f.get("band") in BANDS}


def detect_requests(result: dict, *, claimed_bands, alternates_by_rec: dict = None,
                    band_schools: dict = None) -> list:
    """Emit routed request objects for one district's extraction `result` (a `run_council_streaming`
    per-district dict: {district_id, reps[], accepted[], unresolved[], bands}).

    `claimed_bands`   — the bands the district claims (from `district_target.lea_claimed_bands_json`).
    `alternates_by_rec` — {rec_key: [{file, kind}, ...]} of OTHER captured reps of the same URL not
                          sent this dispatch (drives 7→6 vs 7→3). Empty/None ⇒ no alternates known.
    `band_schools`    — optional {band: [school names]} (from `schools_by_band_json`) to name the
                          targets in a district-band request.

    Returns a list of `{district_id, altitude, route, target, band, params, reason}`.
    """
    alternates_by_rec = alternates_by_rec or {}
    band_schools = band_schools or {}
    did = result.get("district_id")
    files = _sent_file(result)
    reqs: list = []

    # --- representation / URL altitude: a sent record produced no accepted facts ---
    for rec_key, n_acc in _accepted_by_record(result).items():
        if n_acc > 0:
            continue
        alts = alternates_by_rec.get(rec_key) or []
        sent = files.get(rec_key)
        if alts:
            reqs.append({
                "district_id": did, "altitude": "representation", "route": ROUTE_ALT_REP,
                "target": rec_key, "band": None,
                "params": {"sent_file": sent, "alternate_reps": alts},
                "reason": f"sent rep '{sent}' yielded 0 accepted facts; "
                          f"{len(alts)} alternate rep(s) available for this URL — try another modality"})
        else:
            reqs.append({
                "district_id": did, "altitude": "url", "route": ROUTE_RECAPTURE,
                "target": rec_key, "band": None,
                "params": {"sent_file": sent},
                "reason": f"sent rep '{sent}' yielded 0 accepted facts and no alternate rep exists — "
                          f"recapture the URL"})

    # --- district altitude: a claimed band has no accepted facts anywhere ---
    have = _bands_with_facts(result)
    for band in claimed_bands or []:
        if band not in BANDS or band in have:
            continue
        schools = band_schools.get(band) or []
        reqs.append({
            "district_id": did, "altitude": "district", "route": ROUTE_REDISCOVER,
            "target": did, "band": band,
            "params": {"band": band, "schools": schools},
            "reason": f"claimed band '{band}' has 0 accepted facts across all URLs"
                      + (f" ({len(schools)} school(s) known)" if schools else "")
                      + " — targeted rediscover for that band"})
    return reqs
