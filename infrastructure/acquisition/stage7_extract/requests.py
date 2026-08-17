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
  - **district** — a *claimed band* (from the NCES/LEA span) is not DONE → **7→2** (targeted
    rediscover for that band / **7→1** add schools). #694: with the gate@8 slot projection in hand
    (slot_gaps), done = SATISFIED (REQ-149) or no open unfilled slots, and the directive names the
    specific unfilled schools; without it, the legacy boolean (0 accepted facts across all URLs).

Benchmark note: for `batch_type == "benchmark"` (batch_00000) the routes don't *execute* (the batch
is walled off, and its reps are frozen `gt://` artifacts with no alternates/recapture) — but the
detection is still valid and is exactly how we test this logic against a known corpus.
"""
from __future__ import annotations

from infrastructure.acquisition.common.model_families import DEGRADED_TRUNCATED, strongest_kind

BANDS = ("elementary", "middle", "high")

# route labels (the cyclic back-edges) — kept as literals so the persisted request is self-describing
ROUTE_ALT_REP = "7->6"      # re-dispatch a different already-captured rep of the same URL
ROUTE_RECAPTURE = "7->3"    # recapture the URL (no alternate rep)
ROUTE_REDISCOVER = "7->2"   # targeted discovery for a missing band
ROUTE_ADD_SCHOOLS = "7->1"  # follow-up batch adding specific schools

# The statuses under which a directive is OPEN (a human can still action it) — the ONE definition
# (PR #240 review: this pair was previously spelled inline six times across three files). The _SQL
# form is for inlining into raw text() queries (module constant, never user input).
OPEN_STATUSES = ("pending", "approved")
OPEN_STATUSES_SQL = "(" + ", ".join(f"'{s}'" for s in OPEN_STATUSES) + ")"

# #694 x #696: how many span-only (outside-Stage-1-pool) schools a band-gap directive may name as
# assumption-check targets — bounded by design (the #696 settlement: the pool is what follow-up
# CHASES; span-only K-8s get a small sample to TEST the Stage-9 tie-rule assumption, never a
# band-filling campaign).
MODE_CHECK_MAX = 2


def open_unfilled_slots(proj_band: dict) -> list:
    """The ONE 'truly unheard' slot predicate (#694): unfilled AND no match attached. An AMBIGUOUS
    slot also reads slot_state 'unfilled', but the pipeline already HOLDS a fact for it — it waits
    on a human disposition, not on more paid discovery. Shared by `slot_gap_summary` (detect) and
    `stage7_execute._unfilled_slots_now` (compose) so the two can never diverge."""
    return [s for s in (proj_band.get("slots") or [])
            if s.get("slot_state") == "unfilled" and not s.get("match")]


def slot_gap_summary(ca: dict, pool_by_band: dict = None):
    """Compress a gate@8 closing argument into the detector's per-band slot-gap view (#694). PURE.

    Slot state is computed ONLY by `slot_spine.project_slots` via the closing-argument assembly —
    this reads the artifact, it never re-projects (the one-home fitness the issue requires: Stage 7
    and Stage 8 derive slot state from the SAME module).

    `pool_by_band` — {band: {school_id, ...}} of the Stage-1 sampling pool (relation 1,
    `schools_by_band_json`): unfilled slots inside it are the schools follow-up CHASES; unfilled
    slots outside it (span-only K-8s, relation 2 minus relation 1 — the #696 gap) are eligible only
    as bounded assumption-check targets. Pool UNKNOWN for a band (band absent from the snapshot /
    no snapshot) ⇒ every slot counts as in-pool (the honest degradation: no capping without
    evidence for it). A KNOWN-EMPTY pool (band present, zero schools — Stage 1 selected nothing
    for it) is NOT unknown: every slot is outside-pool and the #696 cap applies (#703 review —
    `if pool` would have collapsed the two, the #702 absence-vs-empty bug class).

    A slot carrying a standing human `reject` disposition is EXCLUDED from targets (#694 AC: the
    human looked and answered; robo-chasing it re-asks). `confirm_extra` needs no handling here —
    project_slots already turns it into a FILLED human-confirmed slot, so it never appears
    unfilled. Returns {band: {satisfied, unfilled: [{school_id, name, in_pool}], n_slots,
    n_filled, n_rejected}}, or None when the artifact has no slot projection (no live roster —
    the caller falls back to the covered-band boolean)."""
    sp = (ca or {}).get("slot_projection") or {}
    if not sp:
        return None
    rejects = {(a.get("band"), str(a.get("roster_school_id")))
               for a in ((ca.get("negative_space") or {}).get("slot_assignments") or [])
               if a.get("disposition") == "reject" and a.get("roster_school_id")}
    bands_meta = ca.get("bands") or {}
    out = {}
    for band, p in sp.items():
        # A ZERO-SLOT band (facts landed as extras against no roster — CCD has no rows for the
        # district, or none serve the band) carries no slot knowledge at all: emitting an empty
        # unfilled list would read as 'done' — absence of data as completion, the exact bug class
        # #702's empty-pool finding pinned. Omit the band; band_done falls back to the covered
        # boolean for it.
        if not ((p.get("stats") or {}).get("n_slots") or 0):
            continue
        pool = (pool_by_band or {}).get(band)
        unfilled, n_rejected = [], 0
        for s in open_unfilled_slots(p):
            sid = str(s.get("school_id") or "")
            if (band, sid) in rejects:
                n_rejected += 1
                continue
            unfilled.append({"school_id": sid, "name": s.get("roster_school", ""),
                             "in_pool": (sid in pool) if pool is not None else True})
        st = p.get("stats") or {}
        out[band] = {
            # A zero-fact band has no bands[] entry (and thus no REQ-149 signal) — honestly
            # unsatisfied, exactly the population slot-grain pursuit most needs to reach.
            "satisfied": bool(((bands_meta.get(band) or {}).get("satisfied") or {}).get("satisfied")),
            "unfilled": unfilled,
            "n_slots": st.get("n_slots") or 0, "n_filled": st.get("n_filled") or 0,
            "n_rejected": n_rejected}
    return out


def band_done(band: str, have: set, slot_gaps: dict = None) -> bool:
    """The ONE per-band 'no follow-up needed' predicate (#694): slot-grain when the band's slot
    state is known — done ⇔ satisfied (REQ-149) or no open unfilled slots — and the covered-band
    boolean (`band in have`, ≥1 accepted fact) otherwise. Shared by `detect_requests` (emission)
    and `stage7_run.withdraw_satisfied_requests` (#233 withdrawal) so the two can never disagree —
    a directive emitted under one predicate and withdrawn under a weaker one would churn
    (emit → withdraw → re-emit) every round."""
    g = (slot_gaps or {}).get(band)
    if g is not None:
        return bool(g.get("satisfied")) or not g.get("unfilled")
    return band in have


def _accepted_by_record(result: dict) -> dict:
    """rec_key → count of accepted facts across its reps."""
    counts: dict = {}
    for rep in result.get("reps", []):
        counts[rep["rec_key"]] = counts.get(rep["rec_key"], 0) + len(rep.get("accepted") or [])
    return counts


def _sent_inventory(result: dict) -> dict:
    """rec_key → files in first-seen order — the ONE traversal of `reps` both views below derive
    from, so 'first sent' and 'all sent' can never disagree on what a dispatch actually sent."""
    out: dict = {}
    for rep in result.get("reps", []):
        out.setdefault(rep["rec_key"], []).append(rep.get("file"))
    return out


def _sent_file(result: dict) -> dict:
    """rec_key → the file we sent (first rep seen) — for the request's human reason."""
    return {k: v[0] for k, v in _sent_inventory(result).items()}


def _sent_files(result: dict) -> dict:
    """rec_key → sorted list of ALL files sent this result (#231). One dispatch can send several reps
    of a record; the persisted request must name every one so the NEXT round's history exclusion can
    subtract them all — the single first-seen `sent_file` stays for the human-readable reason."""
    return {k: sorted({f for f in v if f}) for k, v in _sent_inventory(result).items()}


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
                    band_schools: dict = None, covered_bands=None, real_bands=None,
                    slot_gaps: dict = None, explain: dict = None) -> list:
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
    `real_bands`      — bands SERVED by ≥1 real NCES school (`school_sampling.real_bands_for_district`
                          — fillability, agreeing with Stage 1's own placement incl. its gap-fill).
                          When known, it gates the loop against COVERAGE-BLIND spend (#176):
                            • a claimed band NOT in real_bands is a PHANTOM (no school serves those
                              grades); a 7→2 rediscover can never fill it, so it is never emitted (#175);
                            • once every FILLABLE target band (claimed ∩ real) has facts — or none is
                              fillable at all — no follow-up can add claimed coverage, so barren-rep
                              7→6/7→3 are suppressed too (#170/#176: the Aspire $0.076
                              vision-escalation-for-nothing).
                          None ⇒ phantom detection is OFF (no per-band drop); the barren-rep coverage
                          gate still applies using the claim alone, and requires a non-empty claimed
                          target set (an all-unknown district keeps its remedies).
    `slot_gaps`       — #694: `slot_gap_summary(closing_argument, pool_by_band)` — per-band slot
                          state from the gate@8 projection (the SAME module Stage 8 reads, via the
                          app layer). When a band's slot state is known, the district-altitude gate
                          moves from the per-band boolean ('has ≥1 fact') to slot grain: pursue
                          until the band is SATISFIED (REQ-149) or out of open unfilled slots, and
                          name the specific unfilled schools in params. Fabrication-safe by
                          construction: the summary derives from the DISTRICT-WIDE closing argument
                          (all prior extractions), never from this result alone — a partial result's
                          silence about a slot is not evidence the slot is empty (the Las Cruces
                          rule at slot grain). None / band-missing ⇒ the legacy covered-band
                          boolean for that band (honest degradation; all pre-#694 pins hold).
    `explain`         — optional dict the detector fills with why nothing was emitted (detect-time
                          suppression is NON-emission — nothing persists — so this is the caller's
                          hook to log it; the compose layer's `suppressed` bucket covers its own gate):
                          {suppressed_barren_reps: n, phantom_bands: [...]}.

    Returns a list of `{district_id, altitude, route, target, band, params, reason}`.
    """
    alternates_by_rec = alternates_by_rec or {}
    band_schools = band_schools or {}
    did = result.get("district_id")
    files = _sent_file(result)
    files_all = _sent_files(result)   # #231: the full send, recorded on the request as lineage
    reqs: list = []

    # Coverage state, computed ONCE up front (both gates read it). `have` = this result's bands ∪ the
    # district-wide covered bands (a partial result alone must not fabricate a gap). `target_bands` =
    # the bands worth chasing = claimed ∩ real (phantoms dropped when real_bands is known); if real is
    # unknown, fall back to the claim. `no_fillable_gap` = no follow-up can add claimed coverage:
    # every fillable target band is DONE — #694: done at slot grain (satisfied / no open unfilled
    # slots) where slot state is known, covered-band boolean otherwise — INCLUDING the all-phantom
    # corner (real known, target empty): such a district can never satisfy any claimed band, so
    # barren-rep remedies would loop forever against the depth guard for nothing. With real UNKNOWN
    # an empty claim does NOT suppress (can't tell all-phantom from no-data). Slot grain deliberately
    # WIDENS the barren-rep window (#694): a band covered-but-unsatisfied keeps its 7→6/7→3 remedies
    # alive — re-reading reps in hand is exactly the cheap evidence a thin band needs.
    have = _bands_with_facts(result) | {b for b in (covered_bands or ()) if b in BANDS}
    claimed_set = {b for b in (claimed_bands or []) if b in BANDS}
    target_bands = claimed_set & set(real_bands) if real_bands is not None else claimed_set
    _done = {b for b in target_bands if band_done(b, have, slot_gaps)}
    no_fillable_gap = (target_bands <= _done) if real_bands is not None \
        else (bool(target_bands) and target_bands <= _done)
    if explain is not None:
        explain["phantom_bands"] = sorted(claimed_set - target_bands) if real_bands is not None else []
        explain["suppressed_barren_reps"] = 0

    # --- representation / URL altitude: a sent record produced no accepted facts ---
    # #709 (REQ-174): records whose zero came from a COUNCIL-DEGRADED rep (a voter structurally
    # lost to its context window) — their zero is evidence about the council, never about the
    # document, so the remedy reason says re-route and the suppression is counted apart from
    # barren (a reader of `explain` must not conclude these documents were empty).
    # #793: `window_truncated` is the second degradation shape — the voter ANSWERED, but only
    # partway. It is counted and worded apart from a refusal because the two mislead differently:
    # a refusal invites "the document was empty", a truncation invites "that was the whole roster".
    # #799: a record can send SEVERAL reps in one dispatch (see the module docstring), so kinds are
    # MERGED across all of a record's markers, never last-write-wins (the #785 shape: a dict
    # comprehension on a non-unique key silently discarding a sibling). #798/#810: which kind wins —
    # and what an absent/empty `kinds` means — is `strongest_kind`'s ONE decision in the base layer,
    # not re-expressed here in a second idiom.
    degraded_kinds: dict = {}
    for rep in result.get("reps", []):
        if rep.get("council_degraded"):
            degraded_kinds.setdefault(rep["rec_key"], []).extend(
                (rep["council_degraded"].get("kinds") or {}).values())
    if explain is not None:
        explain["suppressed_degraded_reps"] = 0
        explain["suppressed_truncated_reps"] = 0
    for rec_key, n_acc in _accepted_by_record(result).items():
        degraded = rec_key in degraded_kinds
        truncated_only = degraded and strongest_kind(degraded_kinds[rec_key]) == DEGRADED_TRUNCATED
        if n_acc > 0:
            # #797: a TRUNCATED rep with facts is a known-PARTIAL read. The zero-yield gate below
            # catches refusals (zero by construction, cannot miss) and would miss truncations
            # (a partial yield is their NORMAL case — Baldwin kept 355 facts from a cut reply).
            # Fact count is not evidence of completeness here.
            if not truncated_only:
                continue
            ranked = rank_alternates(alternates_by_rec.get(rec_key) or [])
            if no_fillable_gap or not ranked:
                # no fillable gap: nothing a remedy could add. No alternate: nothing at THIS
                # altitude can help — recapturing the same URL re-reads the same document into the
                # same window; the band-grain remedies pursue any gap. Either way the count keeps
                # the run log honest that a completed-looking district rests on a partial read.
                if explain is not None:
                    explain["suppressed_truncated_reps"] += 1
                continue
            sent = files.get(rec_key)
            reqs.append({
                "district_id": did, "altitude": "representation", "route": ROUTE_ALT_REP,
                "target": rec_key, "band": None,
                "params": {"sent_file": sent, "sent_files": files_all.get(rec_key, []),
                           "alternate_reps": ranked, "council_degraded": True,
                           "partial_read": True},
                "reason": (f"known-PARTIAL read: a voter's reply was TRUNCATED at the model window "
                           f"— the {n_acc} accepted fact(s) are the head of the document, not "
                           f"necessarily all of it; " + _alt_reason(sent, ranked))})
            continue
        if no_fillable_gap:
            # #170/#176: every fillable band already covered (or none exists) — no barren-rep remedy
            # can add claimed coverage. Non-emission by design: re-detection re-emits if coverage
            # regresses; `explain` carries the count so the run log isn't silent about it.
            if explain is not None:
                explain["suppressed_truncated_reps" if truncated_only else
                        "suppressed_degraded_reps" if degraded
                        else "suppressed_barren_reps"] += 1
            continue
        alts = alternates_by_rec.get(rec_key) or []
        sent = files.get(rec_key)
        deg_note = (("council-degraded (a voter's reply was TRUNCATED at its context window — the "
                     "read was partial, so this zero is NOT evidence the document is empty): "
                     if truncated_only else
                     "council-degraded (a voter's context window refused the rep — the zero is "
                     "NOT evidence the document is empty): ") if degraded else "")
        if alts:
            ranked = rank_alternates(alts)   # #155: best-first (higher-yield text before vision)
            reqs.append({
                "district_id": did, "altitude": "representation", "route": ROUTE_ALT_REP,
                "target": rec_key, "band": None,
                "params": {"sent_file": sent, "sent_files": files_all.get(rec_key, []),
                           "alternate_reps": ranked,
                           **({"council_degraded": True} if degraded else {})},
                "reason": deg_note + _alt_reason(sent, ranked)})
        else:
            reqs.append({
                "district_id": did, "altitude": "url", "route": ROUTE_RECAPTURE,
                "target": rec_key, "band": None,
                "params": {"sent_file": sent, "sent_files": files_all.get(rec_key, []),
                           **({"council_degraded": True} if degraded else {})},
                "reason": deg_note +
                          f"sent rep '{sent}' yielded 0 accepted facts and no alternate rep exists — "
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

    # --- district altitude: a fillable claimed band is not DONE (DISTRICT-WIDE state — a partial
    # result alone must not fabricate a gap). `target_bands` is the ONE predicate source: claimed ∩
    # BANDS ∩ real-when-known, so a phantom band (#175: no school serves those grades) never emits a
    # 7->2 here. #694: with slot state known, done = satisfied (REQ-149) or no open unfilled slots —
    # a band with 1 of 12 roster slots filled is a GAP (the Cleveland shape #692 measured), and the
    # directive names the specific unfilled schools; without slot state, the legacy zero-facts
    # boolean. Iterating claimed_bands (not the set) preserves the claim's order in the output. ---
    for band in claimed_bands or []:
        if band not in target_bands or band in _done:
            continue
        schools = band_schools.get(band) or []
        params = {"band": band, "schools": schools}
        g = (slot_gaps or {}).get(band)
        if g is not None:
            # #694 x #696: pool slots (relation 1) are what follow-up chases; span-only slots
            # (relation 2 minus relation 1 — K-8s placed in another band's pool) are named only as
            # a BOUNDED assumption-check sample (does the K-8's bell match the band mode the
            # Stage-9 tie rule will hand its grades?). Deterministic pick: lowest school_id.
            # .get() throughout (#703 review): the summary always populates these keys, but this
            # is a public pure function — an under-shaped slot_gaps entry (a test double, a future
            # summary variant) must degrade like everything else in this module, never KeyError
            # the whole district's detection pass.
            gaps = g.get("unfilled") or []
            in_pool = [u for u in gaps if u.get("in_pool")]
            span_only = sorted((u for u in gaps if not u.get("in_pool")),
                               key=lambda u: u.get("school_id") or "")
            mode_check = span_only[:MODE_CHECK_MAX]
            params["unfilled_schools"] = [{"school_id": u.get("school_id") or "",
                                           "name": u.get("name") or ""} for u in in_pool]
            params["mode_check_schools"] = [{"school_id": u.get("school_id") or "",
                                             "name": u.get("name") or ""} for u in mode_check]
            n_slots, n_filled = g.get("n_slots") or 0, g.get("n_filled") or 0
            params["n_slots"], params["n_filled"] = n_slots, n_filled
            names = [u.get("name") or "" for u in in_pool[:3]]
            more = len(in_pool) - len(names)
            reason = (f"claimed band '{band}' has {n_filled} of {n_slots} roster slots "
                      f"filled and is not satisfied (REQ-149)")
            if in_pool:
                reason += (f" — {len(in_pool)} unfilled school(s) to pursue: "
                           + ", ".join(names) + (f" (+{more} more)" if more > 0 else ""))
            if mode_check:
                reason += (f"; {len(mode_check)} span-only assumption-check target(s) "
                           f"(does the K-8 bell match the band mode? #696): "
                           + ", ".join(u.get("name") or "" for u in mode_check))
        else:
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
