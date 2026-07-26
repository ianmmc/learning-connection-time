"""Stage 7 request-more-evidence EXECUTION (REQ-118) — turn APPROVED gate@7 directives into real
back-edge work. This is the APP layer, so it is allowed to import across stages (the stage7 model +
the Stage-1 batch builder + the Stage-6 dispatch bridge); the stage packages stay independent.

Two mechanisms, matching the two shapes of an approved `ExtractionRequest` (STAGE7 §3F, governance
§11d):

  * NEW capture/discovery (7->2 rediscover, 7->3 recapture, 7->1 add-schools) → `compose_followup_batch`
    collects the approved directives into ONE targeted Stage-1 **follow-up batch** (batch_type=
    'follow-up'), a DRAFT reviewable at gate@1. Nothing runs straight to discovery — governance §11d:
    anything needing new capture/discovery returns to Stage 1, stays human-reviewable, and only then
    walks 2→3→4→5→6→7 normally. Collected into one batch honoring the 12-district cap (spillover → the
    next compose).

  * EXISTING representations (7->6 alternate-rep re-dispatch) → `execute_alternate_dispatch` (Slice 4)
    builds a NEW immutable Stage-6 dispatch from the named alternate reps and re-enters Stage 7 via the
    normal extract path — no new capture, so it bypasses Stage 1 (the one legitimate back-edge that does).

Guards: the REQ-051 budget governor's `max_request_rounds` is the per-district×band DEPTH guard, so the
cyclic loop provably terminates; the paid 7->6 re-extraction is budget-gated before any OpenRouter call.
An 'executed' directive is never re-fired (idempotency), and its `executed_ref` records the batch_id /
handoff_hash it produced (lineage).
"""
from __future__ import annotations

import json

from sqlalchemy import text

from pathlib import Path
from typing import NamedTuple

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import budget as BUD
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import discovered_domain as DDOM
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import school_sampling as SS
from infrastructure.acquisition.process_governance import stage6_dispatch as H6
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA8
from infrastructure.acquisition.stage1_queue import queue_batch as Q1
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import cost as COST6
from infrastructure.acquisition.stage6_handoff import handoff as HND
from infrastructure.acquisition.stage6_handoff import package as PKG6
from infrastructure.acquisition.stage7_extract import content as CONTENT
from infrastructure.acquisition.stage7_extract import models as M7
from infrastructure.acquisition.stage7_extract import requests as RQ

# The routes that need NEW capture/discovery and therefore route through a Stage-1 follow-up batch.
# 7->6 (existing reps) is the direct-dispatch path (execute_alternate_dispatch), NOT a batch route.
# Imported from the detector's canonical constants (issue #147) — never re-spell route strings.
NEWWORK_ROUTES = (RQ.ROUTE_REDISCOVER, RQ.ROUTE_RECAPTURE, RQ.ROUTE_ADD_SCHOOLS)


# ---------------------------------------------------------------------------
# Pure planner (no DB/network) — the collect / depth-guard / cap / band-expand logic
# ---------------------------------------------------------------------------
def plan_followup(requests: list, *, claimed_bands: dict, executed_rounds: dict = None,
                  cap: int = 12, max_rounds: int = None, defer_76: set = None,
                  covered_bands: dict = None, real_bands: dict = None,
                  satisfied_bands: dict = None) -> dict:
    """Decide the follow-up batch from approved NEW-work request dicts — PURE (unit-testable, the real
    logic). Steps: filter to NEW-work routes → SUPPRESS a request that can no longer add coverage
    (#176 defense-in-depth: a banded request whose band is covered/phantom, OR a band-less one for a
    district with no fillable gap left) → HOLD a request whose district still has an un-executed 7->6
    (#159: try the cheap in-hand alternate rep before spending on new discovery) → apply the
    per-district×band DEPTH guard → group by district in first-seen order (upstream attention sort
    preserved) → apply the 12-district cap (overflow spills, un-swept) → per kept district, the union
    of target bands (an explicit `band` from 7->2; a band-less 7->3/7->1 expands to the district's
    FILLABLE GAP — claimed ∩ real-when-known − covered — never to raw claimed bands, which would
    re-target phantom/covered bands through the band-less side door).

    requests:        [{request_id, district_id, route, band}]  (band may be None)
    claimed_bands:   {district_id: [band, ...]}                 (for band-less expansion)
    executed_rounds: {(district_id, band): n_already_executed}  (depth guard; band key may be None)
    defer_76:        {district_id, ...} with an un-executed 7->6 — their NEW-work requests are HELD
    covered_bands:   {district_id: {band, ...}} with accepted facts NOW (LIVE, re-read at compose — a
                     band another round covered between approval and execution must not re-fire; #176)
    satisfied_bands: {district_id: {band, ...}} whose gate@8 satisfied signal is True (REQ-149, live at
                     compose) — an ADDITIONAL suppressor beside covered_bands (Ian, 2026-07-15: the
                     hard gate stays; satisfied is the stronger stop — a confident band attracts no
                     more spend even while other bands keep the district in play)
    real_bands:      {district_id: {band, ...}} the district can actually satisfy (≥1 real school
                     SERVING the band — `school_sampling.real_bands_for_district`, fillability incl.
                     Stage 1's gap-fill). A banded request for a band absent here is a PHANTOM,
                     unfillable (#175). A district missing from the dict is unknown (not gated).
    Returns {targets, swept_ids, spilled, blocked, deferred, suppressed}."""
    executed_rounds = executed_rounds or {}
    defer_76 = defer_76 or set()
    covered_bands = covered_bands or {}
    real_bands = real_bands or {}
    satisfied_bands = satisfied_bands or {}

    def _fillable_gap(did) -> list:
        """The bands a follow-up for `did` could still fill, in claimed order: claimed ∩
        real-when-known − covered. The ONE predicate behind the band-less suppression + expansion."""
        fillable = [b for b in claimed_bands.get(did, []) if b in RQ.BANDS
                    and (did not in real_bands or b in real_bands[did])]
        return [b for b in fillable if b not in covered_bands.get(did, ())
                and b not in satisfied_bands.get(did, ())]

    blocked, deferred, suppressed, eligible = [], [], [], []
    for r in requests:
        if r["route"] not in NEWWORK_ROUTES:
            continue
        did, band = r["district_id"], r.get("band")
        # #176 defense-in-depth, checked LIVE at compose — never trusting the request's stale
        # detect-time band state (the #159 lesson). Banded (any new-work route): its band must still
        # be uncovered and fillable. Band-less (7->3/7->1): the district must still have SOME
        # fillable gap — a recapture for a district whose last gap was filled by another round
        # between approval and compose can add nothing (the stale-request door).
        reason = None
        if band:
            if band in covered_bands.get(did, ()):
                reason = f"band '{band}' now has accepted facts — already covered"
            elif band in satisfied_bands.get(did, ()):
                reason = (f"band '{band}' is SATISFIED (REQ-149: confident mode/coverage at gate@8)"
                          " — no more spend needed")
            elif did in real_bands and band not in real_bands[did]:
                reason = f"band '{band}' is phantom (no school serves those grades) — unfillable"
        elif not _fillable_gap(did):
            reason = ("no fillable band gap remains — every fillable claimed band is covered "
                      "(or none exists), so this recapture/add-schools can no longer add coverage")
        if reason:
            suppressed.append({"request_id": r["request_id"], "district_id": did, "band": band,
                               "route": r["route"], "reason": reason})
            continue
        if did in defer_76:
            # #159: an un-executed 7->6 (an already-captured alternate rep) may fill the band for free;
            # rediscovering NOW would spend on new discovery/capture prematurely. Held until the
            # district's 7->6s are executed (or rejected); re-detection then re-emits any still-empty band.
            deferred.append({"request_id": r["request_id"], "district_id": did,
                             "reason": "un-executed 7->6 (alternate rep) for this district — try it first"})
            continue
        used = executed_rounds.get((did, band), 0)
        if BUD.rounds_exhausted(used, max_rounds):     # #147: one depth-guard predicate
            blocked.append({"request_id": r["request_id"], "district_id": did, "band": band,
                            "reason": f"depth guard: {used} round(s) already executed (max {max_rounds})"})
            continue
        eligible.append(r)

    by_district: dict = {}
    for r in eligible:                       # first-seen order preserves the upstream attention sort
        by_district.setdefault(r["district_id"], []).append(r)

    ordered = list(by_district)
    kept, overflow = ordered[:cap], ordered[cap:]
    spilled = [{"district_id": d, "reason": f"{cap}-district follow-up cap reached; spills to the next batch"}
               for d in overflow]

    targets, swept_ids = {}, []
    for did in kept:
        bands: list = []
        for r in by_district[did]:
            if r.get("band"):
                if r["band"] not in bands:
                    bands.append(r["band"])
            else:
                for b in _fillable_gap(did):   # never raw claimed — no phantom/covered re-targeting
                    if b not in bands:
                        bands.append(b)
            swept_ids.append(r["request_id"])
        targets[did] = bands
    return {"targets": targets, "swept_ids": swept_ids, "spilled": spilled,
            "blocked": blocked, "deferred": deferred, "suppressed": suppressed}


# ---------------------------------------------------------------------------
# DB glue — read approved directives, plan, build + persist a DRAFT follow-up batch, flip requests
# ---------------------------------------------------------------------------
def _approved_newwork(session, handoff_hash: str = None) -> list:
    q = ("SELECT request_id, district_id, route, band, params_json FROM extraction_request "
         "WHERE status = 'approved' AND route = ANY(:routes)")
    params = {"routes": list(NEWWORK_ROUTES)}
    if handoff_hash:
        q += " AND handoff_hash = :h"
        params["h"] = handoff_hash
    q += " ORDER BY request_id"
    return [dict(m) for m in session.execute(text(q), params).mappings()]


def _attempted_schools(session, district_ids: list) -> dict:
    """{district_id: {school_id, ...}} already selected in an APPROVED batch (#162): the follow-up
    builder prefers UNTRIED NCES schools for a re-targeted band. `included` filters out
    human-rejected schools. DRAFT batches are excluded (review of a9c4486): a draft never ran
    discovery — its schools were NOT attempted — and an abandoned draft (batch_00009) would poison
    the untried set forever; an APPROVED batch is committed-to-run, so counting it also prevents
    double-queuing the same school across overlapping follow-ups. `abandoned` (#168) is excluded for
    the same reason as `draft`: `batch_store.abandon_batch` refuses any batch whose durable
    `first_approved_at` is set, so `abandoned` provably implies never-approved -> never-ran -> its
    schools were never attempted (that guard is what keeps this exclusion sound)."""
    if not district_ids:
        return {}
    out: dict = {}
    for did, sid in session.execute(text(
            "SELECT DISTINCT bs.district_id, bs.school_id FROM batch_school bs "
            "JOIN batch b ON b.batch_id = bs.batch_id "
            "WHERE bs.district_id = ANY(:d) AND bs.included IS TRUE "
            "AND b.status NOT IN ('draft', 'abandoned')"),
            {"d": list(district_ids)}).all():
        out.setdefault(did, set()).add(sid)
    return out


def _seed_urls_by_district(rows: list) -> dict:
    """{district_id: [url, ...]} from approved 7->3 (recapture) directives' params.target_urls (#161).
    Dormant today (no producer of target_urls yet), but the plumbing carries them if present."""
    out: dict = {}
    for r in rows:
        if r["route"] != RQ.ROUTE_RECAPTURE:
            continue
        for u in (json.loads(r.get("params_json") or "{}").get("target_urls") or []):
            out.setdefault(r["district_id"], [])
            if u not in out[r["district_id"]]:
                out[r["district_id"]].append(u)
    return out


def _json_col(value, default):
    """One parse contract for district_target's JSON text columns: text → json.loads; a driver/
    migration that hands back an already-parsed list/dict passes through; garbage → default.
    (Previously _claimed_bands parsed defensively while its siblings parsed bare — two conventions
    for the same table meant the same bad value degraded in one helper and crashed the other.)"""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _district_target_bands(session, district_ids: list) -> tuple:
    """(claimed, real) per district from ONE district_target read: claimed = the LEA's claim
    (band-less expansion); real = the bands ≥1 real school actually SERVES, via the one shared
    definition (`school_sampling.real_bands_for_district`, which owns the sbb traversal) — so the
    compose gate can never diverge from the detector's. A district with no row is omitted from
    `real` (unknown ⇒ not gated)."""
    if not district_ids:
        return {}, {}
    claimed, real = {}, {}
    for did, cb, by_level_j, sbb_j in session.execute(text(
            "SELECT district_id, lea_claimed_bands_json, nces_by_level_json, schools_by_band_json "
            "FROM district_target WHERE district_id = ANY(:d)"), {"d": list(district_ids)}):
        claimed[did] = _json_col(cb, [])
        # #498 (PR #500 review round): live roster rides along — see stage7_run's twin call sites.
        real[did] = SS.real_bands_for_district(_json_col(by_level_j, {}), _json_col(sbb_j, {}),
                                               band_rosters=SS.band_rosters_for_district(did))
    return claimed, real


def _covered_bands_now(session, district_ids: list) -> dict:
    """{district_id: {band, ...}} with an ACCEPTED fact right now — the LIVE coverage the #176 compose
    gate reads (a band another round filled between a 7->2's approval and this compose must not fire).
    stage7_run's per-district covered query is this predicate's single-district twin — keep aligned."""
    if not district_ids:
        return {}
    out: dict = {}
    # run_kind='production' only: a vision-lab PROBE's accepted fact is a measurement, never coverage —
    # without this join a probe could auto-reject a human-approved 7->2/7->3/7->1 as "already covered".
    for did, band in session.execute(text(
            "SELECT DISTINCT f.district_id, f.band FROM school_fact f "
            "JOIN extraction e ON e.extraction_id = f.extraction_id "
            "WHERE f.district_id = ANY(:d) AND f.status = 'accepted' AND f.band IS NOT NULL "
            "AND e.run_kind = 'production'"),
            {"d": list(district_ids)}):
        out.setdefault(did, set()).add(band)
    return out


def _executed_rounds(session, district_ids: list) -> dict:
    """{(district_id, band): ROUNDS} of already-EXECUTED directives — the depth-guard history,
    scoped to the districts under consideration (issue #148: never a full-table aggregate).
    Rounds = DISTINCT executed_ref, NOT rows (#153): a bundle/compose flips N directives to ONE
    executed_ref (one handoff / one batch = one round); COUNT(*) would over-count and depth-block a
    band-less request after a single bundled round of the district's 7->6s."""
    if not district_ids:
        return {}
    rows = session.execute(text(
        "SELECT district_id, band, COUNT(DISTINCT executed_ref) FROM extraction_request "
        "WHERE status = 'executed' AND district_id = ANY(:d) GROUP BY district_id, band"),
        {"d": list(district_ids)})
    return {(r[0], r[1]): r[2] for r in rows}


def _benchmark_district_ids(session, district_ids: list) -> set:
    """The subset of `district_ids` belonging to any batch_type='benchmark' batch. Request execution
    must never rebadge these into a follow-up batch (issue #134).

    Thin alias over `common/benchmark.py` — THE definition since epic #617 consolidated the three
    hand-maintained copies (this one, Stage 9's, and server.py's IS_BENCHMARK_SQL). GRAIN WARNING:
    district-MEMBERSHIP, which #619 replaces with dispatch provenance for the write-eligibility
    callers; see that module's docstring."""
    return BM.benchmark_district_ids(session, district_ids)


def _refuse_benchmark_reps(session, package: dict):
    """#644: apply #618's freeze provenance guard on the gate@7 BACK-EDGE freeze paths, returning
    this module's `{"ok": False, "reason": ...}` refusal instead of raising.

    The guard existed but had ONE call site (`stage6_dispatch.dispatch_handoff`) against THREE freeze
    paths — the two here called `HND.freeze` directly and never set `dispatch_type`, so it defaulted
    to `production`. A 7->6 directive names its alternate reps by rec_key from the district's LIVE
    reps, and a batch_00000 district holds `benchmark_gt` captures, so these paths could mint a
    production dispatch carrying injected `gt://` reps — exactly what #618 refuses elsewhere.

    It never fired only because the #134 membership wall above keeps benchmark districts away from
    both paths, which made a district-identity ACCIDENT load-bearing for a provenance rule — the
    coupling epic #617 exists to retire, and it would have broken the moment #134 was re-keyed (#620).

    Returns None when the freeze may proceed. The refusal is a normal action result, not an
    exception, because both callers are console actions whose contract is a refusal dict; the
    exception form stays the right shape at gate@6, where a raise rolls the session back."""
    try:
        H6.assert_dispatch_type_allowed(session, package)
    except ValueError as e:
        return {"ok": False, "reason": str(e)}
    return None


def _defer_76_districts(session, district_ids: list, max_rounds=None) -> set:
    """Districts with an UN-EXECUTED 7->6 (status pending or approved) that CAN STILL EXECUTE —
    #159: their NEW-work (7->2) requests are HELD at compose so the cheap in-hand alternate rep is
    tried before new discovery. A rejected or executed 7->6 does not defer. NEITHER does a district
    whose 7->6 ROUNDS are exhausted (review R2): its un-executed 7->6s are depth-blocked zombies that
    can never fire — deferring on them would hold the district's rediscovery FOREVER (live case:
    Las Cruces, 2/2 rounds spent, #279/#284/#288 un-executed). Exhausted -> the correct escalation is
    to let the 7->2 proceed."""
    if not district_ids:
        return set()
    rows = session.execute(text(
        "SELECT DISTINCT district_id FROM extraction_request "
        f"WHERE route = :r AND status IN {RQ.OPEN_STATUSES_SQL} AND district_id = ANY(:d)"),
        {"r": RQ.ROUTE_ALT_REP, "d": list(district_ids)})
    cands = {r[0] for r in rows}
    if max_rounds is None:
        return cands
    return {d for d in cands if _executed_rounds_76(session, d) < max_rounds}


class Gathered(NamedTuple):
    """The compose inputs `_gather` reads — named fields, not a hand-aligned positional tuple (the
    arity grew 6→8 in one PR and two adjacent `{}` slots type-check identically when swapped)."""
    rows: list
    claimed: dict
    exec_rounds: dict
    defer_76: set
    covered: dict
    real: dict
    batch_id: str | None
    benchmark_excluded: list
    # None-default like every other dict input in this module (epic-#499 review round): a NamedTuple
    # field default is ONE object shared by every instance that omits it — a `= {}` here is the
    # mutable-default footgun waiting for the first in-place `g.satisfied[did] = ...`.
    satisfied: dict | None = None    # REQ-149: {district_id: {band,...}} satisfied at gate@8, live

    @classmethod
    def empty(cls, rows=None, benchmark_excluded=None):
        return cls(rows or [], {}, {}, set(), {}, {}, None, benchmark_excluded or [])


def _gather(session, handoff_hash: str, max_rounds=None, ca_cache: dict = None) -> "Gathered":
    """Read the detector inputs on `session`: the approved NEW-work rows (benchmark districts
    EXCLUDED — the wall, #134), per-district claimed + real bands (ONE district_target read),
    the executed-round history (depth guard), the districts to defer (un-executed 7->6, #159),
    the LIVE covered bands (the #176/#175 coverage/phantom gate), and the next free batch id.
    `ca_cache` (optional {district_id: closing_argument}) is shared with the compose caller so the
    per-district closing-argument assembly runs ONCE per compose, not once per consumer."""
    rows = _approved_newwork(session, handoff_hash)
    if not rows:
        return Gathered.empty()
    dids = sorted({r["district_id"] for r in rows})
    bm = _benchmark_district_ids(session, dids)
    benchmark_excluded = [{"district_id": r["district_id"], "request_id": r["request_id"],
                           "reason": "benchmark district (batch_00000) — walled off from execution"}
                          for r in rows if r["district_id"] in bm]
    rows = [r for r in rows if r["district_id"] not in bm]
    if not rows:
        return Gathered.empty(benchmark_excluded=benchmark_excluded)
    dids = sorted({r["district_id"] for r in rows})
    claimed, real = _district_target_bands(session, dids)
    exec_rounds = _executed_rounds(session, dids)
    defer_76 = _defer_76_districts(session, dids, max_rounds)
    covered = _covered_bands_now(session, dids)
    satisfied = _satisfied_bands_now(session, dids, ca_cache=ca_cache)
    batch_id = f"batch_{BSTORE.next_batch_number(session):05d}"
    return Gathered(rows, claimed, exec_rounds, defer_76, covered, real, batch_id,
                    benchmark_excluded, satisfied)


def _load_ca_cached(session, did, cache):
    """One closing-argument assembly per district per compose — the loader is ~9 sequential
    queries plus CCD file reads, and compose consumes it twice (satisfied, then unfilled slots).
    record_drift_event=False (review round 2): compose is a planner, and its dry_run preview
    promises NO writes — the roster_drift audit event is gate@8's to record, never a compose
    side effect."""
    if cache is not None and did in cache:
        return cache[did]
    ca = CA8.load_closing_argument(session, did, record_drift_event=False)
    if cache is not None:
        cache[did] = ca
    return ca


def _satisfied_bands_now(session, district_ids: list, ca_cache: dict = None) -> dict:
    """{district_id: {band,...}} whose gate@8 satisfied signal (REQ-149) is True RIGHT NOW — the
    live closing argument per district (the same live-read posture as _covered_bands_now).
    COST HONESTY (epic-#499 review round): this runs over EVERY district holding an approved
    new-work directive — the pre-cap set, because suppression decides WHICH districts make the
    cap cut — so its cost scales with the approved-request backlog, not plan_followup's cap.
    Fine at today's volume; the batched ANY(:d) rewrite (the _covered_bands_now shape) is the
    known next step if the backlog grows to hundreds. Best-effort per district: a failure means
    NO suppression for that district — the covered_bands hard gate still applies, so a failure
    can only cost money, never coverage."""
    out: dict = {}
    for did in district_ids:
        try:
            ca = _load_ca_cached(session, did, ca_cache)
            sat = {b for b, ob in (ca.get("bands") or {}).items()
                   if (ob.get("satisfied") or {}).get("satisfied")}
            if sat:
                out[did] = sat
        except Exception:  # noqa: BLE001 — best-effort; the hard gate remains
            continue
    return out


def _unfilled_slots_now(session, district_ids: list, ca_cache: dict = None) -> dict:
    """{district_id: {band: [school_id, ...]}} — the live gate@8 slot projection's UNFILLED slots
    (#499 REQ-150): the roster's own gap list, read at compose for the plan's target districts
    (bounded by the cap; the closing arguments are cache-shared with _satisfied_bands_now).
    Reads the artifact's full slot_projection — NOT bands[b].slots — so a claimed band with ZERO
    accepted facts (no bands entry at all, the population slot-grain pursuit most needs to reach)
    still contributes its whole unheard roster (epic-#499 review round). Feeds
    build_followup_batch's preferred_by_did; best-effort per district — absence degrades to the
    #162 untried heuristic, never blocks."""
    out: dict = {}
    for did in district_ids:
        try:
            ca = _load_ca_cached(session, did, ca_cache)
            per_band = {}
            for band, p in (ca.get("slot_projection") or {}).items():
                # `not match` (review round 2): an AMBIGUOUS slot also reads slot_state
                # "unfilled", but the pipeline already HOLDS a fact for it — it's waiting on a
                # human disposition, not on more paid discovery. Pursuing it re-buys data we
                # have, every compose, until someone clicks. Truly unheard = unfilled AND no
                # match attached (the same predicate the blanket projection uses).
                ids = [s_["school_id"] for s_ in (p.get("slots") or [])
                       if s_.get("slot_state") == "unfilled" and not s_.get("match")
                       and s_.get("school_id")]
                if ids:
                    per_band[band] = ids
            if per_band:
                out[did] = per_band
        except Exception:  # noqa: BLE001 — best-effort; the untried heuristic remains
            continue
    return out


def _flip(session, swept_ids: list, executed_ref: str) -> None:
    """Flip the swept directives to 'executed' with `executed_ref` (the follow-up batch_id, or the
    7->6 dispatch's handoff_hash) as their lineage, guarded on status='approved' so a partial retry
    never double-flips (idempotency). The ONE home for this statement (issue #147)."""
    session.execute(text(
        "UPDATE extraction_request SET status = 'executed', executed_ref = :b, executed_at = :t "
        "WHERE request_id = ANY(:ids) AND status = 'approved'"),
        {"b": executed_ref, "t": M7.utcnow(), "ids": list(swept_ids)})


def _reject_suppressed(session, suppressed: list) -> None:
    """Resolve compose-suppressed directives to 'rejected' with the machine actor + reason — a
    suppressed request (band covered/phantom, or no fillable gap left) would otherwise stay
    'approved' forever, re-suppressing on every future compose (zombie). Guarded on
    status='approved' (idempotent); a human can reverse via the gate@7 review endpoint."""
    now = M7.utcnow()
    for sp in suppressed:
        session.execute(text(
            "UPDATE extraction_request SET status = 'rejected', reviewed_by = 'auto:compose-gate', "
            "reviewed_at = :t, review_note = :n WHERE request_id = :id AND status = 'approved'"),
            {"t": now, "n": f"compose-suppressed: {sp['reason']}", "id": sp["request_id"]})


def _flag_escalation_exhausted(session, district_ids: list, rounds: dict) -> None:
    """#164 PR 3b: mark a ladder-exhausted district with ONE unresolved district-scoped
    followup_flag — the manual-review marker the ladder ends on (5->1 and 7->1 both end here).
    Deduped on an existing UNRESOLVED auto flag so a re-compose never stacks markers; a human
    resolving the flag re-arms it (a later exhaustion is a fresh event worth a fresh flag)."""
    from infrastructure.acquisition.stage5_filter.models import FollowupFlag
    now = M7.utcnow()
    for did in district_ids:
        open_auto = session.execute(text(
            "SELECT 1 FROM followup_flag WHERE district_id = :d AND scope = 'district' "
            "AND actor = 'auto:escalation-ladder' AND resolved_at IS NULL LIMIT 1"),
            {"d": did}).first()
        if open_auto:
            continue
        session.add(FollowupFlag(
            scope="district", target_id=did, district_id=did,
            directive=(f"#164 escalation ladder exhausted ({rounds[did]['domain']} domain + "
                       f"{rounds[did]['geo']} geo follow-up round(s) approved, still unsatisfied) — "
                       "needs manual discovery/triage"),
            actor="auto:escalation-ladder", created_at=now))
    session.flush()


def _preview_districts(batch_doc: dict) -> list:
    """A compact per-district preview of a would-be follow-up batch (#154 compose modal): the target
    bands, each band's query_strategy (#160 new_schools|widen_queries) + school count, and seed URLs."""
    out = []
    for d in batch_doc.get("districts", []):
        sbb = d.get("schools_by_band", {})
        out.append({
            "district_id": d["district_id"], "name": d.get("name", ""), "state": d.get("state", ""),
            "bands": [{"band": b, "query_strategy": sbb[b].get("query_strategy"),
                       "n_schools": len(sbb[b].get("schools", []))} for b in sbb],
            "seed_urls": d.get("seed_urls", [])})
    return out


def compose_followup_batch(*, year: str = "2024_25", actor: str = "ian", handoff_hash: str = None,
                           cap: int = 12, session=None, dry_run: bool = False) -> dict:
    """Sweep APPROVED 7->2/7->3/7->1 directives into targeted, DRAFT Stage-1 follow-up batch(es)
    (reviewable at gate@1), flipping the swept directives to 'executed' with THEIR district's
    batch_id as `executed_ref`. Benchmark (batch_00000) districts are EXCLUDED — the wall (#134).
    Scope to one run with `handoff_hash`, else all approved NEW-work directives.

    #164 PR 3b — the 7->1 second-loop scope split: a target district's ladder position is derived
    from its ever-approved follow-up history (`batch_store.followup_rounds`): 0 rounds -> the
    domain-scoped batch (loop 1, unchanged); >=1 round, geo not yet exhausted
    (`batch_store.geo_ladder_exhausted`, shared with the 5->1 zero-yield composer, #575) ->
    a GEO-scoped batch with forced-widened vocabulary (loop 2); geo ladder exhausted -> the
    directive is auto-rejected + the district gets an unresolved followup_flag (manual review).
    Scope-purity means one compose can emit up to TWO batches (`batches` in the result); the
    legacy top-level batch_id/n_* fields carry the first batch id + the totals.

    ATOMICITY (#139): every batch's rows + every per-batch directive flip commit in ONE transaction
    (batch_store on the same session), so a crash can never leave a batch persisted with its
    directives still 'approved' (the duplicate-batch hazard). Only directives whose district
    actually made it into its scope's batch are flipped — a district build_followup_batch skips
    stays 'approved' and re-sweepable (#136). The regenerable receipt files + the registry updates
    happen AFTER commit (file-last, like dispatch_handoff), best-effort. `session` = the
    inject-or-own idiom: an injected (test) session does the DB work only — no receipt/registry
    side effects escape a rollback.
    Returns {batch_id, n_requests, n_districts, batches, targets, spilled, blocked, skipped,
    escalation_exhausted, benchmark_excluded}."""
    b = BUD.load_budget()

    def _work(s) -> dict:
        ca_cache: dict = {}    # one closing-argument load per district per compose (shared below)
        g = _gather(s, handoff_hash, b.max_request_rounds, ca_cache=ca_cache)
        if not g.rows:
            return {**_empty_result(), "benchmark_excluded": g.benchmark_excluded}

        plan = plan_followup(g.rows, claimed_bands=g.claimed, executed_rounds=g.exec_rounds,
                             cap=cap, max_rounds=b.max_request_rounds, defer_76=g.defer_76,
                             covered_bands=g.covered, real_bands=g.real,
                             satisfied_bands=g.satisfied or {})
        if not dry_run:
            # A suppressed directive is RESOLVED, not skipped: its band is covered/phantom (or the
            # district has no fillable gap left), so it could otherwise never leave 'approved' — it
            # would re-enter _approved_newwork and re-suppress on EVERY future compose, forever.
            # Auto-reject with an explicit machine actor + the reason as the review note: auditable,
            # visible in the gate@7 card ("rejected by auto:compose-gate"), and human-REVERSIBLE via
            # the review endpoint (set back to pending). If coverage later regresses, re-detection on
            # the new handoff emits a FRESH request — this row is history, not a lock.
            _reject_suppressed(s, plan["suppressed"])
        if not plan["targets"]:
            return {**_empty_result(), "spilled": plan["spilled"], "blocked": plan["blocked"],
                    "deferred": plan["deferred"], "suppressed": plan["suppressed"],
                    "benchmark_excluded": g.benchmark_excluded}

        # ------- #164 PR 3b: the 7->1 second-loop SCOPE SPLIT (the escalation ladder's compose leg).
        # Ladder position is DERIVED from ever-approved follow-up batch history (never a stored
        # counter): 0 prior rounds -> domain-scoped follow-up (loop 1, current behavior); >=1 prior
        # round with no geo round yet -> escalate to GEO + widened vocabulary (loop 2 — hypothesis:
        # page-finding, not the domain, was fine; now try the open web around the district's
        # geography); a geo round already ran -> the ladder is exhausted: manual flag, no compose.
        # Scope-purity (a batch is domain XOR geo by construction) means one compose can emit up to
        # TWO batches; each directive's executed_ref is ITS district's batch — two reservations,
        # ONE transaction.
        target_dids = list(plan["targets"])
        rounds = BSTORE.followup_rounds(s, target_dids)
        # #575 review: exhaustion is the ONE shared predicate (BSTORE.geo_ladder_exhausted) — this
        # composer must never disagree with the 5->1 zero-yield composer about the same district.
        exhausted_dids = [d for d in target_dids if BSTORE.geo_ladder_exhausted(rounds[d])]
        geo_dids = [d for d in target_dids
                    if d not in exhausted_dids and (rounds[d]["domain"] + rounds[d]["geo"]) >= 1]
        domain_dids = [d for d in target_dids if d not in exhausted_dids and d not in geo_dids]
        did_by_id = {r["request_id"]: r["district_id"] for r in g.rows}
        escalation_exhausted = [
            {"request_id": rid, "district_id": did_by_id[rid], "band": None, "route": None,
             "reason": (f"7->1 escalation exhausted: {rounds[did_by_id[rid]]['domain']} domain + "
                        f"{rounds[did_by_id[rid]]['geo']} geo follow-up round(s) already approved — "
                        "manually flagged for review")}
            for rid in plan["swept_ids"] if did_by_id[rid] in exhausted_dids]
        if not dry_run and escalation_exhausted:
            # Same resolution mechanism as the coverage gate: reject (human-reversible at gate@7,
            # note carries the story) + ONE unresolved district-scoped followup_flag as the manual
            # ladder-end marker (deduped — a re-compose must not stack flags).
            _reject_suppressed(s, escalation_exhausted)
            _flag_escalation_exhausted(s, exhausted_dids, rounds)

        # Follow-up shaping inputs (#162 untried schools, #161 seed URLs), scoped to the plan's targets.
        buildable = domain_dids + geo_dids
        attempted = _attempted_schools(s, buildable)
        seed_urls = _seed_urls_by_district([r for r in g.rows if r["district_id"] in set(buildable)])
        # #499 REQ-150: slot-grain pursuit — the live projection's unfilled slots, restricted to
        # the plan's target bands, ride into selection as the preferred set.
        unfilled = _unfilled_slots_now(s, buildable, ca_cache=ca_cache)
        slot_targets = {did: {b: unfilled[did][b] for b in bands
                              if b in unfilled.get(did, {})}
                        for did, bands in plan["targets"].items() if unfilled.get(did)}
        slot_targets = {did: m for did, m in slot_targets.items() if m}
        plan["slot_targets"] = slot_targets
        # #164 review: the dual-source guard is only as good as its inputs — without this, a
        # human-confirmed discovered domain was invisible to every automatic back-edge sweep and
        # the district hit the #229 skip forever.
        dd = DDOM.all_confirmed(s)

        base_n = int(g.batch_id[6:])              # _gather reserved the first free number
        composed, skipped = [], []
        for scope, dids in (("domain", domain_dids), ("geo", geo_dids)):
            if not dids:
                continue
            bid = f"batch_{base_n + len(composed):05d}"
            doc, skipped_g = Q1.build_followup_batch(
                year, bid, {d: plan["targets"][d] for d in dids},
                attempted_by_did=attempted, seed_urls_by_did=seed_urls,
                preferred_by_did=slot_targets, scope=scope, discovered_domains=dd,
                force_widen_dids=(set(dids) if scope == "geo" else None))
            skipped.extend(skipped_g)
            if not doc["districts"]:              # every district of this scope was un-buildable
                continue
            built = {d["district_id"] for d in doc["districts"]}
            flip_ids = [i for i in plan["swept_ids"] if did_by_id[i] in built]
            composed.append({"batch_id": bid, "scope": scope, "doc": doc, "flip_ids": flip_ids})
        if not composed:                          # nothing buildable in either scope
            return {**_empty_result(), "spilled": plan["spilled"], "blocked": plan["blocked"],
                    "deferred": plan["deferred"], "suppressed": plan["suppressed"], "skipped": skipped,
                    "escalation_exhausted": escalation_exhausted,
                    "benchmark_excluded": g.benchmark_excluded}

        common = {"targets": plan["targets"], "spilled": plan["spilled"], "blocked": plan["blocked"],
                  "deferred": plan["deferred"], "suppressed": plan["suppressed"], "skipped": skipped,
                  "escalation_exhausted": escalation_exhausted,
                  "benchmark_excluded": g.benchmark_excluded}
        if dry_run:                               # #154 modal preview — NO create_batch, NO flip
            return {"batch_id": composed[0]["batch_id"], "dry_run": True,
                    "n_requests": sum(len(c["flip_ids"]) for c in composed),
                    "n_districts": sum(len(c["doc"]["districts"]) for c in composed),
                    "batches": [{"batch_id": c["batch_id"], "scope": c["scope"],
                                 "n_requests": len(c["flip_ids"]),
                                 "n_districts": len(c["doc"]["districts"]),
                                 "preview": _preview_districts(c["doc"])} for c in composed],
                    "preview": [p for c in composed for p in _preview_districts(c["doc"])],
                    **common}

        # Rows + flips on ONE session (atomic, #139): both batches' rows and BOTH per-batch directive
        # flips commit together. Flip ONLY the directives whose district made it into ITS scope's
        # batch (#136) — a skipped district's directive stays 'approved', re-sweepable.
        for c in composed:
            BSTORE.create_batch(s, c["doc"], batch_type="follow-up", redo_attempted=True, actor=actor)
            _flip(s, c["flip_ids"], c["batch_id"])
        return {"batch_id": composed[0]["batch_id"],
                "n_requests": sum(len(c["flip_ids"]) for c in composed),
                "n_districts": sum(len(c["doc"]["districts"]) for c in composed),
                "batches": [{"batch_id": c["batch_id"], "scope": c["scope"],
                             "n_requests": len(c["flip_ids"]),
                             "n_districts": len(c["doc"]["districts"])} for c in composed],
                **common,
                "_batch_districts": [{"district_id": d["district_id"], "name": d.get("name", ""),
                                      "state": d.get("state", ""), "batch_id": c["batch_id"]}
                                     for c in composed for d in c["doc"]["districts"]]}

    if session is not None:
        out = _work(session)                      # DB-only; a rolling-back test session leaks nothing
        out.pop("_batch_districts", None)
        return out

    gdb.init_precious_schema()                    # ensure executed_ref/executed_at columns exist
    with gdb.session_scope() as s:
        out = _work(s)
    batch_districts = out.pop("_batch_districts", None)
    if out["batch_id"] and batch_districts:
        # Post-commit, best-effort (file-last, like dispatch_handoff): the receipts are regenerable
        # FROM the committed rows; the registry backup is regenerable from the DB. One receipt per
        # composed batch (#164 PR 3b: the scope split can emit two).
        try:
            with gdb.session_scope() as s:
                for c in out.get("batches") or [{"batch_id": out["batch_id"]}]:
                    BSTORE.write_receipt(s, c["batch_id"])
            registry = DS.load()
            for d in batch_districts:
                DS.record_stage(registry, d["district_id"], d["name"], d["state"],
                                stage=1, stage_name="queue", outcome="queued",
                                batch_id=d.get("batch_id") or out["batch_id"])
            DS.save(registry)
        except Exception as e:  # noqa: BLE001 — receipts/registry are regenerable; the DB committed
            print(f"[warn] follow-up receipt/registry refresh failed ({type(e).__name__}: {e}); "
                  f"the DB is authoritative — regenerate later")
    return out


def _empty_result() -> dict:
    return {"batch_id": None, "n_requests": 0, "n_districts": 0, "targets": {}, "batches": [],
            "spilled": [], "blocked": [], "deferred": [], "suppressed": [], "skipped": [],
            "escalation_exhausted": [], "benchmark_excluded": []}


# ===========================================================================
# 7->6 — DIRECT alternate-representation re-dispatch (existing reps; bypasses Stage 1)
# ===========================================================================
def pick_alternate(alternate_reps: list) -> dict | None:
    """Choose which already-captured alternate rep to re-dispatch — the yield-RANKED top
    (`requests.rank_alternates` (#155): higher-yield TEXT before vision before dregs, NOT image-first).
    Defensive kind filter (#140): a binary rep (kind 'pdf'/'bin') is never dispatchable — it would
    route to the text council and be read as raw bytes (paid mojibake). Feed LIVE reps carrying
    n_times (see `live_alternates`) so ranking is correct even for a request persisted before ranking
    landed (its stored alternate_reps lack n_times)."""
    readable = [a for a in (alternate_reps or [])
                if a.get("kind") == "text" or CONTENT.is_image_kind(a.get("kind"))]
    ranked = RQ.rank_alternates(readable)
    return ranked[0] if ranked else None


def live_alternates(rec: dict, sent_files: set) -> list:
    """Dispatchable alternate reps of a record, read LIVE from `rec['reps']` (release-loader shape:
    source/filename/file_kind/n_times/usable) — NOT the request's stored params, so old requests
    (persisted before the #155 ranking + n_times) still pick correctly. Excludes already-sent files,
    non-usable reps, chrome segments, and non-readable kinds (#140). Carries n_times for the ranker."""
    out = []
    for rp in rec.get("reps") or []:
        fn, kind = rp.get("filename"), rp.get("file_kind")
        if fn in sent_files or not rp.get("usable"):
            continue
        if (rp.get("source") or "").startswith("segment:"):
            continue
        if kind == "text" or CONTENT.is_image_kind(kind):
            out.append({"file": fn, "kind": kind, "n_times": rp.get("n_times")})
    return out


def build_alternate_input(meta: dict, rec: dict, alt: dict, *, council_id: str = None) -> tuple:
    """Synthesize the ONE-record dispatch input (+ council override) that re-dispatches the NAMED
    alternate rep instead of the release winner — the 7->6 bridge. `overrides` picks the council
    ({rec_key::file: council_id}); an image alt with no explicit council defaults to the 'image'
    council (the text→vision escalation). Returns (districts_input, overrides) for assemble_package.
    Size fields are joined from the record's representation rows (cost inputs; the flat bootstrap model
    ignores them, but the measured model will not)."""
    reps_by_file = {r.get("filename"): r for r in (rec.get("reps") or [])}
    rr = reps_by_file.get(alt["file"], {})
    send_entry = {"file": alt["file"], "kind": alt.get("kind"),
                  "n_chars": rr.get("n_chars"), "n_times": rr.get("n_times"),
                  "n_schools": len(rec.get("intended_schools") or []) or None}
    record = {"rec_key": rec["rec_key"], "url": rec.get("url"), "decision": "send",
              "reason": "7->6 alternate-rep re-dispatch (REQ-118)",
              "signals": rec.get("signals") or {}, "send": [send_entry]}
    cid = council_id or ("image" if CONTENT.is_image_kind(alt.get("kind")) else None)
    overrides = {f"{rec['rec_key']}::{alt['file']}": cid} if cid else {}
    return [(meta, [record])], overrides


def _load_request(session, request_id: int) -> dict | None:
    row = session.execute(text(
        "SELECT request_id, district_id, route, band, target, params_json, status "
        "FROM extraction_request WHERE request_id = :id"), {"id": request_id}).mappings().first()
    return dict(row) if row else None


def _executed_rounds_76(session, district_id: str) -> int:
    """DISTINCT executed handoffs (ROUNDS, not rows) for a district's 7->6s (#153): a bundle flips N
    requests to ONE `executed_ref`, so counting rows would over-count and trip the depth guard after a
    single bundled round — count distinct executed_ref. 7->6 band is always NULL, so it's per-district."""
    return session.execute(text(
        "SELECT COUNT(DISTINCT executed_ref) FROM extraction_request WHERE status = 'executed' "
        "AND route = :r AND district_id = :d"),
        {"r": RQ.ROUTE_ALT_REP, "d": district_id}).scalar() or 0


def _sent_files_by_rec(session, district_id: str) -> dict:
    """{rec_key: {failed files}} for the district — the union of every sent file across ALL its 7->6
    requests (F4: a rep that failed once, and so generated a 7->6, must never be re-dispatched — not
    even in a later round for a different rec-key request). DB-only: a failed-and-requested rep is
    exactly some 7->6's sent_file(s), so no handoff-doc I/O is needed.
    Reads BOTH `sent_files` (#231: the FULL set of files one dispatch sent for this record) and the
    legacy single `sent_file` (older persisted requests, and the field detect_requests still writes for
    the human-readable reason) — a dispatch that sent two reps of one record, only one of which the
    request names via `sent_file`, must not leave the other re-offerable next round.
    Routes match stage7_run._district_request_inputs (#231): 7->6 AND 7->3 — a file recorded only on a
    RECAPTURE request is just as sent/failed as one on an alternate-rep request."""
    out: dict = {}
    for target, pj in session.execute(text(
            "SELECT target, params_json FROM extraction_request "
            "WHERE district_id = :d AND route IN (:r6, :r3)"),
            {"d": district_id, "r6": RQ.ROUTE_ALT_REP, "r3": RQ.ROUTE_RECAPTURE}).all():
        p = json.loads(pj or "{}")
        files = set(p.get("sent_files") or [])
        if p.get("sent_file"):
            files.add(p["sent_file"])
        if files:
            out.setdefault(target, set()).update(files)
    return out


def build_alternate_bundle_input(meta: dict, selections: list) -> tuple:
    """ONE multi-record dispatch input for a district's BUNDLED 7->6 (#153) — selections =
    [(rec, alt), ...]. Reuses `build_alternate_input` per record and merges into a single
    (meta, [records]) + merged council overrides, so N alternate-rep re-dispatches ride ONE immutable
    handoff = ONE round (the depth guard counts rounds, not reps)."""
    records, overrides = [], {}
    for rec, alt in selections:
        (di, ov) = build_alternate_input(meta, rec, alt)
        (_m, recs), = di
        records.extend(recs)
        overrides.update(ov)
    return [(meta, records)], overrides


def _bundle_alternate(s, district_id: str, actor: str, root) -> dict:
    """Core (session-in): bundle ALL approved 7->6 directives for one district into a SINGLE Stage-6
    dispatch = one round. Benchmark-walled (#134), depth-guarded by ROUNDS (#153), each record's rep
    chosen yield-ranked from live reps excluding every already-failed file (#155/F4). Flips every
    bundled directive to 'executed' with the one handoff_hash. Returns the bundle result."""
    if _benchmark_district_ids(s, [district_id]):
        return {"ok": False, "reason": f"district {district_id} is a benchmark district (batch_00000) "
                                       f"— walled off from request execution"}
    reqs = s.execute(text(
        "SELECT request_id, target FROM extraction_request "
        "WHERE district_id = :d AND route = :r AND status = 'approved' ORDER BY request_id"),
        {"d": district_id, "r": RQ.ROUTE_ALT_REP}).mappings().all()
    if not reqs:
        return {"ok": False, "reason": f"no approved 7->6 directive for district {district_id}"}

    b = BUD.load_budget()
    used = _executed_rounds_76(s, district_id)
    if b.rounds_exhausted(used):                        # #147: one depth-guard predicate
        return {"ok": False, "blocked": True,
                "reason": f"depth guard: {used} round(s) already executed for {district_id} 7->6 "
                          f"(max {b.max_request_rounds})"}

    meta = REL.load_district(s, district_id)
    if not meta:
        return {"ok": False, "reason": f"district {district_id} not in the release store"}
    # #148: load ONLY the approved requests' target records (a handful), not the whole district.
    recs_by_key = {r["rec_key"]: r for r in REL.load_records_by_key(s, [req["target"] for req in reqs])}
    sent_by_rec = _sent_files_by_rec(s, district_id)

    selections, swept, skipped = [], [], []
    for req in reqs:
        rec = recs_by_key.get(req["target"])
        if not rec:
            skipped.append({"request_id": req["request_id"], "target": req["target"],
                            "reason": "record not found in the release store"})
            continue
        alt = pick_alternate(live_alternates(rec, sent_by_rec.get(req["target"], set())))
        if not alt:
            skipped.append({"request_id": req["request_id"], "target": req["target"],
                            "reason": "no dispatchable alternate rep left (all reps sent/exhausted)"})
            continue
        selections.append((rec, alt))
        swept.append(req["request_id"])
    if not selections:
        return {"ok": False, "skipped": skipped,
                "reason": f"no dispatchable alternate across the {len(reqs)} approved 7->6(s)"}

    councils = C6.load_configs()
    cost_model = COST6.load_cost_model()
    districts_input, overrides = build_alternate_bundle_input(meta, selections)
    package = PKG6.assemble_package(districts_input, councils, cost_model, overrides)
    if not package["cost"]["n_reps"]:
        return {"ok": False, "reason": "the bundled alternates produced an empty dispatch package"}
    package["verified_only"] = False
    if (refusal := _refuse_benchmark_reps(s, package)) is not None:
        return refusal
    fps = {district_id: REL.district_fingerprints(s, district_id)}
    doc = HND.freeze(package, councils, fps, created_by=actor)
    path = (Path(root) if root else HND.DEFAULT_ROOT) / HND.handoff_filename(doc)
    # Commit-order (#143, mirrors dispatch_handoff): every DB statement FIRST (index row +
    # state_events + the directive flips), the immutable file LAST — a DB failure rolls back cleanly
    # with no orphaned file. The district_status backup refresh is post-commit (below), never here.
    H6.record_dispatch(s, doc, path, actor=actor, metas={district_id: meta})
    _flip(s, swept, doc["handoff_hash"])          # ALL bundled directives -> one executed_ref = one round
    HND.write(doc, root=root)
    return {"ok": True, "handoff_hash": doc["handoff_hash"], "path": str(path),
            "n_bundled": len(selections), "swept": swept, "skipped": skipped,
            "alt_files": [a["file"] for _, a in selections]}


def _run_bundle_or_own(work_fn, session):
    """inject-or-own + post-commit best-effort district_status export, shared by the 7->6 bundle entry
    points. An injected (test) session does DB-only work — no receipt/registry side effects escape a
    rollback. The export runs AFTER commit on a SEPARATE session (the altitude lesson #143/#139:
    export_status reads the current_state view; a failure there must never poison the load-bearing
    dispatch transaction)."""
    if session is not None:
        return work_fn(session)
    gdb.init_precious_schema()
    with gdb.session_scope() as s:
        out = work_fn(s)
    if out.get("ok"):
        try:
            with gdb.session_scope() as s2:
                DS.export_status(s2)
        except Exception as e:  # noqa: BLE001 — the DB is authoritative; the backup regenerates
            print(f"[warn] district_status.json refresh failed after 7->6 bundle "
                  f"({type(e).__name__}: {e}); the DB is authoritative — regenerate later")
    return out


def compose_alternate_bundle(district_id: str, *, actor: str = "ian", root=None, session=None) -> dict:
    """Bundle ALL approved 7->6 directives for a district into ONE immutable Stage-6 dispatch = one
    round (#153) and re-enter Stage 7 via the normal extract path (no new capture; bypasses Stage 1).
    The prior dispatches are untouched (history preserved). The PAID re-extraction is a separate,
    budget-gated Stage-7 run. `session` follows the inject-or-own idiom."""
    return _run_bundle_or_own(lambda s: _bundle_alternate(s, district_id, actor, root), session)


def _dispatch_recover_band(s, district_id: str, band: str, rec_key: str, file: str,
                           actor: str, root) -> dict:
    """#473 core (session-in): gate@8 'recover band' — re-dispatch the NAMED, ALREADY-SENT rep (the
    hub doc that filled the sibling bands) so the council re-reads it for the missing band. Stage-7
    re-extraction, NOT re-discovery: the artifact is on disk. Full-rep re-extraction is safe with no
    band-targeted prompting because merge_fact_runs is fill-gaps-never-overwrite (property-tested):
    new facts for the missing band fill the hole; re-read sibling facts can't evict the earliest
    accepted. Mints an APPROVED 7->6 ExtractionRequest for lineage (the gate@8 click IS the human
    approval — same posture as the override/exclude actions), then freezes an immutable one-record
    dispatch and flips the request executed. The PAID extraction stays a separate, budget-gated
    Stage-7 run at gate@7 — this action only stages the work. Benchmark-walled, ROUNDS depth-guarded
    like every 7->6."""
    if _benchmark_district_ids(s, [district_id]):
        return {"ok": False, "reason": f"district {district_id} is a benchmark district (batch_00000)"}
    b = BUD.load_budget()
    used = _executed_rounds_76(s, district_id)
    if b.rounds_exhausted(used):
        return {"ok": False, "blocked": True,
                "reason": f"depth guard: {used} round(s) already executed for {district_id} 7->6 "
                          f"(max {b.max_request_rounds})"}
    meta = REL.load_district(s, district_id)
    if not meta:
        return {"ok": False, "reason": f"district {district_id} not in the release store"}
    recs = REL.load_records_by_key(s, [rec_key])
    rec = recs[0] if recs else None
    if not rec:
        return {"ok": False, "reason": f"record {rec_key} not found in the release store"}
    rep = next((r for r in (rec.get("reps") or []) if r.get("filename") == file), None)
    if not rep:
        return {"ok": False, "reason": f"rep {file!r} not found on record {rec_key}"}
    kind = rep.get("file_kind")
    if kind != "text" and not CONTENT.is_image_kind(kind):
        return {"ok": False, "reason": f"rep {file!r} has kind {kind!r} — not dispatchable (#140)"}

    req = M7.ExtractionRequest(
        district_id=district_id, handoff_hash=rec.get("handoff_hash") or "", altitude="representation",
        route=RQ.ROUTE_ALT_REP, target=rec_key, band=band,
        params_json=json.dumps({"file": file, "origin": "gate8_recover_band"}),
        reason=f"gate@8 recover-band (#473): {band} empty; sibling bands extracted from this rep",
        status="approved", reviewed_by=actor)
    s.add(req)
    s.flush()

    councils = C6.load_configs()
    cost_model = COST6.load_cost_model()
    districts_input, overrides = build_alternate_input(meta, rec, {"file": file, "kind": kind})
    package = PKG6.assemble_package(districts_input, councils, cost_model, overrides)
    if not package["cost"]["n_reps"]:
        return {"ok": False, "reason": "the recover-band rep produced an empty dispatch package"}
    package["verified_only"] = False
    if (refusal := _refuse_benchmark_reps(s, package)) is not None:
        return refusal
    fps = {district_id: REL.district_fingerprints(s, district_id)}
    doc = HND.freeze(package, councils, fps, created_by=actor)
    path = (Path(root) if root else HND.DEFAULT_ROOT) / HND.handoff_filename(doc)
    # Commit-order (#143): every DB statement first, the immutable file last.
    H6.record_dispatch(s, doc, path, actor=actor, metas={district_id: meta})
    _flip(s, [req.request_id], doc["handoff_hash"])
    HND.write(doc, root=root)
    return {"ok": True, "handoff_hash": doc["handoff_hash"], "path": str(path),
            "request_id": req.request_id, "file": file,
            "next": "trigger the extraction from the Stage 6 (Dispatch) console — the new dispatch is listed there; results then land at gate@7 (paid, budget-gated)"}


def recover_band_dispatch(district_id: str, band: str, rec_key: str, file: str, *,
                          actor: str = "ian", root=None, session=None) -> dict:
    """#473 entry point (inject-or-own, same idiom as compose_alternate_bundle)."""
    return _run_bundle_or_own(
        lambda s: _dispatch_recover_band(s, district_id, band, rec_key, file, actor, root), session)


def execute_alternate_dispatch(request_id: int, *, actor: str = "ian", root=None, session=None) -> dict:
    """Fire an APPROVED 7->6 directive — by bundling its WHOLE district's approved 7->6s into one round
    (#153: approve the several you want, execute one, they all go as a single cyclic round so the depth
    guard bounds cycles, not components). A thin resolver over `compose_alternate_bundle`; the request
    is validated (exists / is a 7->6 / is approved) before the district bundle runs."""
    def work(s) -> dict:
        req = _load_request(s, request_id)
        if not req:
            return {"ok": False, "reason": f"no such request {request_id}"}
        if req["route"] != RQ.ROUTE_ALT_REP:
            return {"ok": False, "reason": f"request {request_id} is {req['route']}, not a 7->6 re-dispatch"}
        if req["status"] != "approved":
            return {"ok": False, "reason": f"request {request_id} is {req['status']}, not approved"}
        return _bundle_alternate(s, req["district_id"], actor, root)
    return _run_bundle_or_own(work, session)


# ---------------------------------------------------------------------------
# CLI — CLI-first per the ramp-up model; the console buttons wrap the same functions
# ---------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Stage 7 request-more-evidence execution (REQ-118)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compose-followup", help="sweep approved 7->2/7->3/7->1 into a draft follow-up batch")
    c.add_argument("--handoff", help="scope to one handoff_hash (else all approved NEW-work)")
    c.add_argument("--year", default="2024_25")
    c.add_argument("--actor", default="cli")
    c.add_argument("--cap", type=int, default=12)
    e = sub.add_parser("execute", help="fire an approved 7->6 — bundles its whole district's approved "
                                       "7->6s into one round (#153)")
    e.add_argument("request_id", type=int)
    e.add_argument("--actor", default="cli")
    eb = sub.add_parser("execute-bundle", help="bundle a DISTRICT's approved 7->6s into one round")
    eb.add_argument("district_id")
    eb.add_argument("--actor", default="cli")
    a = ap.parse_args()

    if a.cmd == "compose-followup":
        out = compose_followup_batch(year=a.year, actor=a.actor, handoff_hash=a.handoff, cap=a.cap)
        if not out["batch_id"]:
            print("No approved NEW-work directives to compose.")
        else:
            for c in out.get("batches") or []:
                print(f"Draft follow-up {c['batch_id']} ({c['scope']}-scoped): "
                      f"{c['n_districts']} district(s), {c['n_requests']} directive(s) executed. "
                      f"Review at gate@1.")
        for ex in out.get("escalation_exhausted", []):
            print(f"  ladder exhausted: req {ex['request_id']} {ex['district_id']} ({ex['reason']})")
        for sp in out.get("spilled", []):
            print(f"  spilled: {sp['district_id']} ({sp['reason']})")
        for su in out.get("suppressed", []):      # #176 gate — auto-rejected, human-reversible at gate@7
            print(f"  suppressed: req {su['request_id']} {su['district_id']}"
                  f"{'/' + su['band'] if su.get('band') else ''} ({su['reason']})")
        for bl in out.get("blocked", []):
            print(f"  blocked (depth guard): req {bl['request_id']} {bl['district_id']}/{bl['band']}")
        for df in out.get("deferred", []):
            print(f"  deferred (#159): req {df['request_id']} {df['district_id']} ({df['reason']})")
        for sk in out.get("skipped", []):
            print(f"  skipped: {sk['district_id']} ({sk['reason']})")
        for bm in out.get("benchmark_excluded", []):
            print(f"  benchmark-excluded: req {bm['request_id']} {bm['district_id']} ({bm['reason']})")
    elif a.cmd in ("execute", "execute-bundle"):
        out = (execute_alternate_dispatch(a.request_id, actor=a.actor) if a.cmd == "execute"
               else compose_alternate_bundle(a.district_id, actor=a.actor))
        if out["ok"]:
            print(f"Bundled {out['n_bundled']} alternate-rep re-dispatch(es) "
                  f"({', '.join(out['alt_files'])}) → new handoff {out['handoff_hash']} = one round. "
                  f"Run Stage 7 on it to extract (budget-gated).")
            for sk in out.get("skipped", []):
                print(f"  skipped: req {sk['request_id']} {sk['target']} ({sk['reason']})")
        else:
            print(f"Refused: {out['reason']}")


if __name__ == "__main__":
    main()
