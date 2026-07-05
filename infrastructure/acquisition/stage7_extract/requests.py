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


def rank_alternates(alts: list) -> list:
    """Order 7->6 alternate reps BEST-FIRST (#155) — pure. The escalation ladder is
    partial-text → FULLER text → vision, NOT "prefer image": a richer text extraction of the same
    document is the cheapest high-yield retry, and vision is the escalation tried when text is
    exhausted. So:
      1. readable TEXT with usable yield (n_times > 0), highest n_times first;
      2. IMAGE reps (the vision escalation);
      3. text with no extractable times (n_times 0/None) — near-useless, last.
    (Live evidence #122/#155: Marion's MHS rep failed as `camelot_hybrid.txt` while `pdftotext.txt`
    n_times=57 sat unused; Pittsylvania's `harvest_slice.txt` failed while `pdftotext.txt` n_times=86
    was available — the old image-first pick sent `raster_p-01.png` and recovered nothing.)"""
    def key(a):
        kind = a.get("kind")
        nt = a.get("n_times") or 0
        fn = a.get("file") or ""      # deterministic tie-break (equal n_times is common: pdftotext
        if kind == "text" and nt > 0:  # vs tesseract often both hit the same count) — never DB order
            return (0, -nt, fn)
        if kind == "image":
            return (1, 0, fn)
        return (2, 0, fn)
    return sorted(alts, key=key)


def _alt_reason(sent: str, ranked: list) -> str:
    """Honest 7->6 reason describing the TOP-ranked alternate (#155) — 'escalate to vision' only when
    the pick actually IS vision; a yield-bearing text retry is named as such; and a zero-yield text
    top pick (nothing better exists) is called what it is, not 'higher-yield'."""
    top = ranked[0]
    n = len(ranked)
    if top.get("kind") == "image":
        return (f"sent rep '{sent}' yielded 0 accepted facts; escalate to VISION on '{top['file']}' "
                f"({n} alternate rep(s) available) — text is exhausted for this URL")
    nt = top.get("n_times")
    if nt:
        return (f"sent rep '{sent}' yielded 0 accepted facts; retry with a higher-yield TEXT "
                f"extraction '{top['file']}' (n_times={nt}) before escalating to vision "
                f"({n} alternate rep(s) available)")
    return (f"sent rep '{sent}' yielded 0 accepted facts; only zero-yield alternate(s) remain — "
            f"last-resort retry on '{top['file']}' ({n} alternate rep(s) available)")


def detect_requests(result: dict, *, claimed_bands, alternates_by_rec: dict = None,
                    band_schools: dict = None, covered_bands=None) -> list:
    """Emit routed request objects for one district's extraction `result` (a `run_council_streaming`
    per-district dict: {district_id, reps[], accepted[], unresolved[], bands}).

    `claimed_bands`   — the bands the district claims (from `district_target.lea_claimed_bands_json`).
    `alternates_by_rec` — {rec_key: [{file, kind, n_times}, ...]} of OTHER captured reps of the same
                          URL not sent this dispatch (drives 7→6 vs 7→3). Empty/None ⇒ none known.
    `band_schools`    — optional {band: [school names]} (from `schools_by_band_json`) to name the
                          targets in a district-band request.
    `covered_bands`   — bands with accepted facts DISTRICT-WIDE (across ALL prior extractions —
                          `SELECT DISTINCT band FROM school_fact ... status='accepted'`). Without it,
                          a PARTIAL result (a 1-record 7→6 re-dispatch) fabricates band gaps: the
                          single record covers nothing, so every claimed band looks empty and a
                          spurious 7→2 fires per band (live: Las Cruces #285-287/#289-291). The
                          district-altitude check unions this with the result's own facts.

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
            ranked = rank_alternates(alts)   # #155: best-first (higher-yield text before vision)
            reqs.append({
                "district_id": did, "altitude": "representation", "route": ROUTE_ALT_REP,
                "target": rec_key, "band": None,
                "params": {"sent_file": sent, "alternate_reps": ranked},
                "reason": _alt_reason(sent, ranked)})
        else:
            reqs.append({
                "district_id": did, "altitude": "url", "route": ROUTE_RECAPTURE,
                "target": rec_key, "band": None,
                "params": {"sent_file": sent},
                "reason": f"sent rep '{sent}' yielded 0 accepted facts and no alternate rep exists — "
                          f"recapture the URL"})

    # #159: how many records in this district have an UNEXHAUSTED existing rep (a 7->6 remedy)?
    # A band-gap 7->2 is premature while these exist — re-extracting an already-captured alternate
    # (free of new discovery/capture) may fill the band. We DEFER the rediscover rather than spend on
    # new discovery. This is a DISTRICT-level signal, deliberately NOT per-band attribution: the
    # motivating case (Marion's MHS bell table) is an EMERGENT record with empty intended_schools —
    # unattributable to a band pre-extraction — and name-matching the 76% that do carry intended
    # schools is fragile and wouldn't cover it. The compose step (Chunk 4) reads `pending_alt_reps`
    # and holds the 7->2 until the district's 7->6s are executed; then re-detection re-emits any band
    # still empty. (Per-band suppression via name-matching was considered and rejected as fragile.)
    n_alt_rep = sum(1 for r in reqs if r["route"] == ROUTE_ALT_REP)

    # --- district altitude: a claimed band has no accepted facts anywhere (DISTRICT-WIDE: this
    # result's facts ∪ covered_bands from prior extractions — a partial result alone must not
    # fabricate a gap) ---
    have = _bands_with_facts(result) | {b for b in (covered_bands or ()) if b in BANDS}
    for band in claimed_bands or []:
        if band not in BANDS or band in have:
            continue
        schools = band_schools.get(band) or []
        params = {"band": band, "schools": schools}
        reason = (f"claimed band '{band}' has 0 accepted facts across all URLs"
                  + (f" ({len(schools)} school(s) known)" if schools else ""))
        if n_alt_rep:
            params["pending_alt_reps"] = n_alt_rep
            reason += (f" — DEFER: {n_alt_rep} barren record(s) with an unexhausted alternate rep "
                       f"(7->6) to try first; rediscover only if the band is still empty after")
        else:
            reason += " — targeted rediscover for that band"
        reqs.append({
            "district_id": did, "altitude": "district", "route": ROUTE_REDISCOVER,
            "target": did, "band": band, "params": params, "reason": reason})
    return reqs
