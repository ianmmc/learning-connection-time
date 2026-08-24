"""Stage 6 release->routing bridge (REQ-101, app layer).

The one module allowed to import BOTH stage5 `release` and the stage6 modules — it lives in
`process_governance` (the top app layer) precisely so the stage packages stay independent (the §12
import-linter contract: stage6 must not import stage5). It reads the Stage-5 release decision from the
governance DB, enriches each `send` rep with the size signals routing/cost need, and hands it to the
pure `package` assembler — producing the in-memory handoff package (slice 5 persists it immutably).
"""
import json
from pathlib import Path
from typing import NamedTuple

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import calibration as CAL
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import extraction_delta as XD
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import receipts as RCPT
from infrastructure.acquisition.process_governance import gate_calibration as GCAL
from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402  (HUB_LABELS — the taxonomy's canonical home)
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.utilities import school_year as SY  # calendar SSOT; prefer-recent read (#107) — NOT the LCT DB
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import cost as COST6
from infrastructure.acquisition.stage6_handoff import handoff as HND
from infrastructure.acquisition.stage6_handoff import package as PKG6
from infrastructure.acquisition.stage6_handoff.models import Handoff


def _enrich_send(decision_send: list, reps: list, rec: dict = None, district_dir: str = None) -> list:
    """Join each release `send` entry ({file, kind, pages?}) back to its representation row to attach
    the size inputs cost.py documents (issue #55) — routing keys on kind, cost on size:
      * `n_chars`/`n_times` from the representation row (None for binaries);
      * `n_schools` = len(record.intended_schools) when known (the output-token scaler cost._n_schools
        expects; falls back there to n_times, then the model's default floor);
      * `n_bytes` = on-disk file size for a binary rep whose n_chars is None — the documented size
        PROXY the future measured vision-token model needs (no current formula reads it)."""
    by_file = {r.get("filename"): r for r in (reps or [])}
    rec = rec or {}
    n_schools = len(rec.get("intended_schools") or []) or None
    rec_hash = (rec.get("rec_key") or "").split(":", 1)[-1]
    base = (paths.RAW_CAPTURES / district_dir / "captures" / rec_hash) \
        if (district_dir and rec_hash) else None
    out = []
    for s in decision_send or []:
        rr = by_file.get(s.get("file"), {})
        e = {**s, "n_chars": rr.get("n_chars"), "n_times": rr.get("n_times"), "n_schools": n_schools}
        if e["n_chars"] is None and base is not None and s.get("file"):
            try:
                e["n_bytes"] = (base / s["file"]).stat().st_size
            except OSError:
                e["n_bytes"] = None
        out.append(e)
    return out


def _content_start_year(signals: dict):
    """The record's content school year as a start-year int, or None (unknown/absent/malformed)."""
    try:
        return SY.start_year((signals or {}).get("content_school_year"))
    except (ValueError, TypeError):
        return None


def _prefer_recent_holds(sendables: list) -> set:
    """#107 prefer-recent (a DISPATCH decision — STAGE6 §3G): among send-eligible siblings covering the
    SAME intended school, keep the most recent and HOLD the stale ones. `sendables` = list of
    {rec_key, year:int|None, schools:list[str]} for records currently deciding `send`. Returns the set
    of rec_keys to HOLD.

    ZERO recall cost by construction: a record is held ONLY when, for EVERY intended school it covers,
    some sibling for that school has a strictly-newer year — so a record that is newest for any school
    it covers (or has no intended school, or no known year) is always kept. Cross-school band-coverage
    redundancy (a district hub superseding school docs) is deliberately NOT done here — that needs
    coverage logic and is #83's job; grouping by shared school is the safe subset."""
    max_by_school = {}
    for r in sendables:
        if r["year"] is None:
            continue
        for sc in r["schools"]:
            max_by_school[sc] = max(max_by_school.get(sc, r["year"]), r["year"])
    holds = set()
    for r in sendables:
        if r["year"] is None or not r["schools"]:
            continue
        if all(max_by_school[sc] > r["year"] for sc in r["schools"]):
            holds.add(r["rec_key"])
    return holds


# REQ-116 (#83): the hub label vocabulary — a human-labeled district hub (per-school or per-band
# listing) is the one URL whose best rep suffices for a district's FIRST dispatch. Imported from its
# canonical home (build_signals owns the label taxonomy) — the #543-#547 review found this was a
# hand-retyped copy that a future taxonomy addition could silently miss.
HUB_LABELS = BS.HUB_LABELS

# #679: the hold reason for a benchmark-provenance rep excluded from a PRODUCTION dispatch's default
# selection. The console keys a display row on this exact string (a server-computed decision field,
# like `decision === "send"` — NOT a client-side provenance re-derivation, which the arch manifest
# forbids), so the two spellings are pinned together by test_stage6_production_eligibility.
INELIGIBLE_PRODUCTION_REASON = "benchmark-rep:ineligible-for-production"

# #691: hub-priority's hold reason (prefix + the winner's rec_key). Same client/server discipline as
# INELIGIBLE_PRODUCTION_REASON — the console keys its held-row display on this server-computed
# spelling; the two are pinned together by test_stage6_dispatch_bridge's console-visibility test.
HUB_PRIORITY_REASON_PREFIX = "hub-priority:first-dispatch-narrowed-to:"

# #717: the already-extracted delta's hold reason. Same client/server discipline as the two above —
# the console keys its held-row display on this server-computed spelling, pinned by
# test_stage6_already_extracted_delta.
ALREADY_EXTRACTED_REASON = "already-extracted:prior-production-run"

# Transient key carrying the reps the #717 delta removed from a record, so `release_bundle` can
# price the AVOIDED spend through the same assembler. Underscore-prefixed and stripped by
# `assemble_record` — it must never reach the frozen artifact.
ALREADY_EXTRACTED_KEY = "_already_extracted_send"

# #691 (Rule B, measured 2026-07-29): the hub-priority YIELD FLOOR multiple. A LABELED sibling whose
# `n_times_in_window` is >= this multiple of the winner's is NOT held — the hub label's
# "covers all bands" presumption is overridden by materially better labeled evidence. k=2 chosen from
# the corpus measurement (docs/technical-notes/production-quality-control-research/
# 2026-07-29-issue691-hub-priority-rule-measurement.md): it recovers every observed failure (Essex's
# 112/61/57 vs a 21-time news feed; Bentonville's 52/49 vs an 8-time page) while leaving every
# genuinely dense hub's one-send first dispatch intact (Bridgeport 196, Fairbanks 80, Bangor 26 —
# corpus separation was clean: overridden winners 8-34, untouched winners 75-196). Rule A ("never
# hold labeled targets") measured +197 sends (+115%) and failed the Bangor regression pin.
HUB_YIELD_FLOOR_MULT = 2


def _hub_priority_holds(sendables: list) -> tuple:
    """REQ-116 (#83) hub-priority narrowing (a DISPATCH decision — STAGE6 §4): when a district's send
    set contains a HUMAN-LABELED district hub, the best hub is the only URL the first dispatch needs —
    every other send is HELD (available for the 7→6 back-edge). `sendables` = [{rec_key, label,
    year:int|None, n_times:int}]. Returns (winner_rec_key|None, set of rec_keys to hold).

    Operational semantics (the AC REQ-116 lacked, authored with #83):
      * "covers all bands" is a PRESUMPTION carried by the hub label itself — district_hub_by_school /
        district_hub_by_band mean "a page listing schedules across the district's schools/bands." No
        per-record claimed-band data exists to verify against, and none is needed for safety: the
        Stage-7 coverage gates + request-more-evidence loop detect an under-covering hub and pull the
        HELD reps back via 7→6 — the presumption costs at most one cheap retry round, while a correct
        presumption saves every redundant per-school send on round 1 (the REQ's point).
      * "best representation of that URL" = best_send's existing per-record pick; BETWEEN hubs, newest
        content year wins, then IN-WINDOW time density (`nitw` — the same metric as the yield floor;
        see the #691 paragraph below).
      * "or A-scoring" (the REQ's unlabeled arm) is STRUCTURALLY ready but inactive: no detector emits
        a hub category today (hub-ness is human/topology knowledge), so an unlabeled tier-A record can
        never satisfy the hub test — when a hub detector exists, it joins this predicate, not a new pass.
    ZERO recall cost by construction: hold, never reject; verified_only composes upstream (a labeled
    hub IS a labeled target, so it survives training-grade mode).

    #691 (Rule B): the presumption above failed measurably — Essex Westford's labeled hub was a
    news feed with 21 in-window times, and narrowing held a 112-time list plus 61/57-time bell
    tables behind it; the Stage-7 safety net never fired because the hub was partially productive.
    The yield floor bounds the presumption with evidence already in hand: a LABELED sibling carrying
    `n_times_in_window` >= HUB_YIELD_FLOOR_MULT x the winner's stays SENT (labeled only — unlabeled
    tier-A auto-sends still narrow, which is REQ-116's actual savings). `n_times_in_window` is a
    text-capture signal, so an image-only hub can under-count and over-send — the safe direction
    (extra labeled sends, never fewer).

    Between-hubs tie-break is BY `nitw` (in-window density), matching the floor's basis — not
    `n_times` (raw rep density), which can diverge materially (13/42 hub-labeled districts measured
    2026-07-29) even though the winning HUB never changed on the measured corpus either way. Kept
    consistent so the tie-break and the floor are provably answering the same question."""
    hubs = [r for r in sendables if r.get("label") in HUB_LABELS]
    if not hubs:
        return None, set()
    winner = max(hubs, key=lambda r: (r["year"] if r["year"] is not None else -1, r.get("nitw") or 0))
    floor = HUB_YIELD_FLOOR_MULT * (winner.get("nitw") or 1)
    holds = {r["rec_key"] for r in sendables
             if r["rec_key"] != winner["rec_key"]
             and not (r.get("label") and (r.get("nitw") or 0) >= floor)}
    return winner["rec_key"], holds


# #540: the Edlio bell_schedules APP family — one school's schedule surface materialized as sibling
# pages (the bare app hub listing all variants + a dedicated page per variant + printerfriendly
# twins). The first vendor profile under REQ-153; the family key is the URL module (works even where
# the Stage-3 fingerprint is absent), the vendor identity is corroborated by cms_hint='edlioschool.com'.
import re as _re
_EDLIO_APP_RE = _re.compile(r"^(https?://[^/]+)/apps/bell_schedules(?:/|$)", _re.I)


def _sibling_variant_holds(sendables: list) -> dict:
    """#540 sibling-aware dispatch (the prefer-recent pattern, keyed on the CMS app family): among
    send-eligible siblings of ONE Edlio bell_schedules app, send the best page and HOLD the rest —
    a variant-only page (early dismissal / remote / delay) whose regular-day sibling is present must
    not each cost a council call. Returns {held_rec_key: winner_rec_key}.

    Family key = (host, the record's intended-school set): the #543-#547 review found host-only
    grouping collapsed genuinely DIFFERENT schools' pages served from one district-level host into
    one family, dropping a school's only send — same school-scoping discipline as
    _prefer_recent_holds. Ranking (ascending; min wins): a HUMAN-LABELED record outranks an
    unlabeled sibling unconditionally, hub labels first (the same review reproduced a labeled
    district hub — and separately a labeled school_bell_table — held in favor of an unlabeled
    denser sibling, silently defeating REQ-116 before _hub_priority_holds ever saw the hub; a
    label is a human judgment this URL-shape heuristic must never override). Then: no strong
    wrong-day vote beats one (variant pages fire lf_nonstandard_day strong); the bare app hub (no
    ?id= param) beats a variant permalink; then newest year, then densest. ZERO recall cost: a
    family with only variant pages still sends its best, and a labeled record can only ever be
    held in favor of ANOTHER labeled record of the same family (the prefer-recent precedent)."""
    fams = {}
    for r in sendables:
        m = _EDLIO_APP_RE.match(r.get("url") or "")
        if m:
            key = (m.group(1).lower(), tuple(sorted(r.get("schools") or [])))
            fams.setdefault(key, []).append(r)
    holds = {}
    for fam in fams.values():
        if len(fam) < 2:
            continue
        winner = min(fam, key=lambda r: (
            0 if r.get("label") in HUB_LABELS else (1 if r.get("label") else 2),
            bool(r.get("wd_strong")), bool(_re.search(r"[?&]id=", r.get("url") or "")),
            -(r["year"] if r.get("year") is not None else -1), -(r.get("n_times") or 0)))
        for r in fam:
            if r["rec_key"] != winner["rec_key"]:
                holds[r["rec_key"]] = winner["rec_key"]
    return holds


def district_release_input(session, district_id: str, verified_only: bool = False,
                           dispatch_type: str = BM.DISPATCH_PRODUCTION, redo: bool = False):
    """Read one district's release decision from the DB, shaped for stage6 assembly:
    `(district_meta, [records])`. Returns None if the district isn't present.

    `verified_only` (gate@6 training-grade mode): dispatch ONLY human-labeled target sends. The
    speculative unlabeled tier-A auto-sends (`reason == auto:tier-A`) are downgraded to `hold` — not
    silently dropped — so they stay traceable and can be labeled later. Stage-5's `filtered.json` is
    unaffected: this is a dispatch-time choice, not a change to the release rule.

    `redo` (#717 declared-redo opt-in): by DEFAULT a rep a prior production run already bought is
    held (reason `already-extracted`) rather than re-sent — the delta Stage 3 has had for capture
    since REQ-172. `redo=True` re-admits them for a deliberate re-extraction (a changed council, a
    distrusted value). It is a MODE, declared once for the whole draft and stamped on the receipt,
    not a per-district exception: per-district re-extraction already has two purpose-built,
    reason-bearing homes — the 7->6 alternate-rep bundle (REQ-118) and gate@8 recover-band (#473) —
    and a third spelling here is exactly the implemented-twice-drifts class this codebase keeps
    paying for. Compose a narrower draft (drafts are built district-by-district) to redo one
    district. Never applies to a benchmark dispatch, which exists to re-extract by design.

    `dispatch_type` (#679): while `production`, a benchmark-provenance rep (capture source
    'benchmark_gt') is structurally incapable of being frozen — `assert_dispatch_type_allowed`
    refuses it — so it must not enter the DEFAULT send set either. Before #679 the selection
    optimised without that constraint and the guard was handed winners it had to refuse; on Bangor
    the injected hub tied its fresh twin, won by iteration order, and hub-priority held the fresh
    one — deselecting the winner left the district with ZERO sends. Excluded reps are HELD (visible,
    reason `benchmark-rep:ineligible-for-production`), never dropped; an explicit
    `dispatch_type='benchmark'` re-admits them (the Council Lab opt-in)."""
    district = REL.load_district(session, district_id)
    if not district:
        return None
    records = []
    sendables = []   # currently-`send` records, for the prefer-recent pass below
    for rec in REL.load_district_records(session, district_id):
        d = REL.decide(rec)
        decision, reason, send = d["decision"], d["reason"], d["send"]
        if verified_only and decision == "send" and rec.get("label") not in REL.TARGET_LABELS:
            decision, reason, send = "hold", f"verified-only:held({reason})", []
        rd = {
            "rec_key": rec["rec_key"], "url": rec.get("url"),
            "label": rec.get("label"),   # #691: the gate@6 held-row display names what the hold suppressed
            "decision": decision, "reason": reason,
            "signals": rec.get("signals") or {},
            "send": _enrich_send(send, rec.get("reps"), rec, district.get("district_dir")),
        }
        records.append(rd)
        if decision == "send":
            sig = rec.get("signals") or {}
            sendables.append({"rec_key": rec["rec_key"], "label": rec.get("label"),
                              "url": rec.get("url"),
                              "year": _content_start_year(sig),
                              # #869: the SENDABLE pool's density, not every rep's. `max` over all
                              # reps let a footer/nav count (scored since #841) decide which Edlio
                              # sibling wins the family — while best_send refuses to ever send that
                              # footer. Same pool the send uses, so the tie-break ranks records by
                              # evidence a dispatch could actually read. (0 live districts change.)
                              "n_times": max((r.get("n_times") or 0)
                                             for r in (REL.sendable_text_reps(rec.get("reps") or [])
                                                       or [{}])),
                              # #691 yield floor input — the in-window count from the record's signals
                              "nitw": int(sig.get("n_times_in_window") or 0),
                              "wd_strong": any(d.get("name") == "lf_nonstandard_day"
                                               and d.get("strength") == "strong"
                                               for d in sig.get("detectors") or []),
                              "schools": rec.get("intended_schools") or []})
    by_key = {rd["rec_key"]: rd for rd in records}   # O(1) lookup instead of rescanning `records` per hold
    # #679 production-eligibility — FIRST, before every narrowing pass (prefer-recent,
    # sibling-variant, hub-priority), so none of them ever sees an ineligible candidate: applied
    # after, Bangor's fresh hub stays held by a winner that is then removed, and the district
    # composes zero sends. HOLD, never drop — the rep stays visible/badged (#662 decision 4 governs
    # display; this governs selection). Skipped for an explicit benchmark dispatch, where gt:// reps
    # are legitimately eligible.
    if dispatch_type != BM.DISPATCH_BENCHMARK and sendables:
        ineligible = BM.benchmark_provenance_rec_keys(session, [s["rec_key"] for s in sendables])
        for rk in ineligible:
            rd = by_key.get(rk)
            if rd is not None and rd["decision"] == "send":
                rd["decision"], rd["send"] = "hold", []
                rd["reason"] = INELIGIBLE_PRODUCTION_REASON
        sendables = [s for s in sendables if s["rec_key"] not in ineligible]
    # #107 prefer-recent (dispatch-time): HOLD a stale same-school sibling — the newest still sends, the
    # older is available for a cheap 7->6 re-dispatch if extraction fails. Composes after verified_only.
    for rk in _prefer_recent_holds(sendables):
        rd = by_key.get(rk)
        if rd is not None and rd["decision"] == "send":
            csy = (rd["signals"] or {}).get("content_school_year")
            rd["decision"], rd["send"] = "hold", []
            rd["reason"] = f"stale-sibling:{csy}:newer-same-school-sends"
    # #540 sibling-variant (dispatch-time): among one Edlio bell_schedules app's sibling pages, the
    # best (labeled > non-variant > hub-shaped-URL > newest > densest) sends; the rest hold. Runs
    # after prefer-recent, before hub-priority. The "a labeled hub then supersedes whatever
    # survived" guarantee holds ONLY because the sibling ranking is label-aware (labels rank first,
    # hubs first among labels) — the #543-#547 review reproduced a label-blind version of this pass
    # holding the labeled hub before hub-priority ever saw it. If the ranking is ever edited, that
    # property is pinned by test_labeled_hub_survives_its_sibling_family_end_to_end.
    survivors = [s for s in sendables if by_key[s["rec_key"]]["decision"] == "send"]
    for rk, winner_rk in _sibling_variant_holds(survivors).items():
        rd = by_key.get(rk)
        if rd is not None and rd["decision"] == "send":
            rd["decision"], rd["send"] = "hold", []
            rd["reason"] = f"sibling-variant:same-app-page-sends:{winner_rk}"
    # REQ-116 (#83) hub-priority (dispatch-time): a labeled district hub narrows the FIRST dispatch to
    # itself; every other surviving send is HELD for the 7→6 back-edge — EXCEPT a labeled sibling
    # clearing the #691 yield floor, which stays sent. Runs AFTER prefer-recent so a stale hub
    # already held by a newer same-school sibling can't be the winner.
    survivors = [s for s in sendables if by_key[s["rec_key"]]["decision"] == "send"]
    hub_winner, hub_holds = _hub_priority_holds(survivors)
    for rk in hub_holds:
        rd = by_key.get(rk)
        if rd is not None and rd["decision"] == "send":
            rd["decision"], rd["send"] = "hold", []
            rd["reason"] = f"{HUB_PRIORITY_REASON_PREFIX}{hub_winner}"
    # #717 already-extracted delta (dispatch-time): a rep a prior PRODUCTION run already bought is
    # HELD, not re-sent — REQ-160 guarantees the duplicate result cannot even change anything
    # (earliest wins), so the re-purchase is spend with zero informational gain. `redo=True` is the
    # declared-redo opt-in (REQ-170 posture) and skips this pass entirely.
    #
    # LAST, deliberately — after prefer-recent / sibling-variant / hub-priority. Those passes RANK
    # candidates against each other; if the delta ran first it would remove a rep from the pool that
    # hub-priority was about to elect, and the district could compose a WORSE send instead of a
    # cheaper one. Running last means the delta only ever subtracts from a set already chosen, so it
    # can change the price but never the choice. (Same ordering lesson as #679, from the opposite
    # side: THAT pass must run FIRST because ineligibility is structural — the rep can never be
    # frozen — whereas already-extracted is a property of the rep's HISTORY, not its eligibility.)
    #
    # Held per REP, not per record: a record can carry one rep already bought and another never sent
    # (a text rep extracted last week beside a raster nobody has read). Only a record left with no
    # sendable rep at all becomes a `hold`.
    if not redo and dispatch_type != BM.DISPATCH_BENCHMARK:
        done = XD.already_extracted_reps(session, district_id)
        if done:
            for rd in records:
                if rd["decision"] != "send":
                    continue
                keep, dropped = [], []
                for rp in (rd["send"] or []):
                    (dropped if (rd["rec_key"], rp.get("file")) in done else keep).append(rp)
                if not dropped:
                    continue
                # The reps the delta removed, kept on the record so the cost preview can price
                # what was AVOIDED through the same assembler the send set uses (never a second
                # cost spelling). `assemble_record` rebuilds a clean dict, so this never reaches
                # the frozen artifact.
                rd[ALREADY_EXTRACTED_KEY] = dropped
                if keep:
                    rd["send"] = keep       # partially bought: send only the unread reps
                else:
                    rd["decision"], rd["send"] = "hold", []
                    rd["reason"] = ALREADY_EXTRACTED_REASON
    return district, records


def build_handoff_package(session, district_ids, councils=None, cost_model=None, overrides=None,
                          verified_only=False, dispatch_type=BM.DISPATCH_PRODUCTION,
                          redo=False) -> dict:
    """Assemble the in-memory handoff package for `district_ids` from the DB release decision.
    Pure stage6 logic does the routing/pricing; this layer only supplies the data. `overrides` =
    gate@6 per-rep council overrides ({"<rec_key>::<file>": council_id}). `verified_only` = gate@6
    training-grade mode (labeled targets only); stamped onto the package so preview + freeze agree.
    `dispatch_type` (#618) is stamped the same way — validated but NOT forced here; the provenance
    guard runs at freeze (`assert_dispatch_type_allowed`), so a preview can still be BUILT and
    displayed for a draft that currently can't be frozen. That is what lets the human see the problem
    and fix it, rather than the console failing to render the draft at all."""
    return release_bundle(session, district_ids, councils=councils, cost_model=cost_model,
                          overrides=overrides, verified_only=verified_only,
                          dispatch_type=dispatch_type, redo=redo).package


class ReleaseBundle(NamedTuple):
    """Everything one assembly of a release produces: the priced `package`, plus the per-district
    `metas` / `fingerprints` and the `skipped` ids only the freeze path needs.

    It exists so PREVIEW and FREEZE can be the same assembly rather than two independent ones (#659).
    That is not only a cost saving: `/api/handoff/dispatch`'s staleness gate computed the identity
    from build A and then froze build B, so anything that changed between them — a label edit, a
    re-price — passed the gate and was frozen unseen. Reusing one bundle closes that window, which is
    what the gate (issue #37) was for.

    FINGERPRINTS ARE NOT HERE, deliberately: only the freeze path embeds them, and a preview render
    (every gate@6 draft view) would otherwise pay a per-district labels/config query it never uses."""
    package: dict
    metas: dict
    skipped: list


def release_bundle(session, district_ids, *, councils=None, cost_model=None, overrides=None,
                   verified_only=False, dispatch_type=BM.DISPATCH_PRODUCTION,
                   redo=False) -> ReleaseBundle:
    """Assemble a release ONCE — the single home for "read the DB decision and price it".

    `dispatch_type` is validated but NOT forced (the #618 provenance guard runs at freeze), so a
    preview can still be BUILT and displayed for a draft that currently cannot be frozen. That is what
    lets the human see the offending reps and deselect them, rather than the console failing to render
    the draft at all.

    `redo` (#717) rides through to `district_release_input` and is stamped on the package, so the
    PREVIEW the human signs off and the FROZEN artifact agree about whether the already-extracted
    delta applied — the same preview/freeze-parity discipline `verified_only` and `dispatch_type`
    already follow (#659)."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    BM.validate_dispatch_type(dispatch_type)
    districts, metas, skipped = [], {}, []
    for did in district_ids:
        di = district_release_input(session, did, verified_only=verified_only,
                                    dispatch_type=dispatch_type, redo=redo)
        if not di:
            skipped.append(did)      # unknown district — dropped from the package (surfaced by callers)
            continue
        districts.append(di)
        metas[did] = di[0]
    package = PKG6.assemble_package(districts, councils, cost_model, overrides)
    package["verified_only"] = bool(verified_only)
    package["dispatch_type"] = dispatch_type
    package["redo"] = bool(redo)
    package["cost"]["reextraction"] = _price_avoided(districts, councils, cost_model, overrides)
    # #912: a PARTIALLY-held record keeps decision "send", so the held-row blocks (keyed on the hold
    # reason) never show its dropped sibling rep — the reviewer would see a normal-looking send row
    # with no sign a rep was subtracted. Sidecar map {rec_key: [files]} for the console to badge
    # per-record; preview-only (assemble_record strips the transient key, so the frozen artifact
    # never carries it — same as the reextraction cost line). Dormant on today's corpus (every live
    # sent record carries exactly one rep) but load-bearing the moment one carries two.
    package["already_extracted_partial"] = {
        rd["rec_key"]: [rp.get("file") for rp in rd[ALREADY_EXTRACTED_KEY]]
        for _meta, recs in districts for rd in recs
        if rd.get(ALREADY_EXTRACTED_KEY) and rd.get("decision") == "send"}
    return ReleaseBundle(package, metas, skipped)


def _price_avoided(districts, councils, cost_model, overrides) -> dict:
    """#717 acceptance: the gate@6 preview must separate NEW spend from RE-EXTRACTION spend.

    With the delta on (the default) the re-extraction reps are HELD, so this is what the delta
    AVOIDED — priced by re-running the reps it removed through `assemble_package`, the same
    assembler the send set uses. Pricing them any other way would be a second cost spelling, and
    the two would drift the first time the cost model changed.

    `{n_reps: 0, usd: 0.0}` when nothing was held — including under `redo=True`, where the delta
    never ran and every rep is priced as new in `total_usd`."""
    shadow = []
    for meta, recs in districts:
        held = [{**rd, "decision": "send", "send": rd[ALREADY_EXTRACTED_KEY]}
                for rd in recs if rd.get(ALREADY_EXTRACTED_KEY)]
        if held:
            shadow.append((meta, held))
    if not shadow:
        return {"n_reps": 0, "usd": 0.0}
    pkg = PKG6.assemble_package(shadow, councils, cost_model, overrides)
    return {"n_reps": pkg["cost"]["n_reps"], "usd": pkg["cost"]["total_usd"]}


def benchmark_reps_in_package(session, package: dict) -> list:
    """The package's SELECTED representations carrying BENCHMARK provenance, as
    [{district_id, rec_key}].

    REPRESENTATION grain, never district grain (#618). A district that merely *was* in a benchmark
    batch is not the question — epic #617 exists to retire exactly that proxy. The question is whether
    the reps this dispatch actually selected trace back to benchmark injection
    (`capture.source='benchmark_gt'`), which is real and mixed after a #620 re-run: Node's #174
    follow-up seeding carries prior records verbatim into the new manifest, so a re-run district
    legitimately holds stale `gt://` reps alongside fresh ones.

    Scoped to records that actually carry send reps (#679): a held/rejected record rides in the
    package for traceability but dispatches nothing, so its provenance must not refuse the freeze —
    the eligibility pass in `district_release_input` HOLDS ineligible gt:// reps by design, and
    flagging those holds here would re-refuse the exact dispatch the hold made freezable."""
    by_key = {r["rec_key"]: d["district_id"]
              for d in package.get("districts", []) for r in d.get("records", [])
              if r.get("rec_key") and r.get("reps")}
    if not by_key:
        return []
    flagged = BM.benchmark_provenance_rec_keys(session, list(by_key))
    return [{"district_id": by_key[k], "rec_key": k} for k in sorted(flagged)]


def assert_dispatch_type_allowed(session, package: dict) -> None:
    """REFUSE to freeze a production dispatch that selected any benchmark-provenance representation.

    Refuse rather than silently force the dispatch to benchmark: a dispatch carries ONE type, so
    auto-forcing would let a single stale `gt://` rep wall every OTHER district in the same dispatch
    off from the Stage-9 write — one operator slip silently costing unrelated districts their LCT
    minutes. The human deselects the rep, or opts the whole dispatch in as benchmark on purpose.

    An explicit `dispatch_type='benchmark'` always passes: that is the Council Lab opt-in, and a
    benchmark dispatch is *allowed* to contain production reps (that is the point of an A/B)."""
    if BM.is_benchmark_dispatch(package):
        return
    flagged = benchmark_reps_in_package(session, package)
    if flagged:
        shown = ", ".join(f"{f['district_id']}:{f['rec_key']}" for f in flagged[:5])
        more = f" (+{len(flagged) - 5} more)" if len(flagged) > 5 else ""
        raise ValueError(
            f"dispatch refused: {len(flagged)} selected representation(s) carry benchmark provenance "
            f"(capture source '{BM.BENCHMARK_CAPTURE_SOURCE}') — {shown}{more}. A benchmark rep must "
            f"not ride in a production dispatch (it terminates at gate@7 and never reaches Stage 9). "
            f"Deselect those records, or set dispatch_type='benchmark' to run this as a Council Lab "
            f"A/B on purpose.")


# ----------------------------- recording a dispatch (DB index + state) -----------------------------
def insert_handoff_row(session, doc: dict, path) -> str:
    """Insert the precious `handoff` index row for a frozen handoff doc; returns the handoff_id."""
    hid = HND.handoff_filename(doc)[:-5]   # the file stem (strip '.json')
    cost = doc.get("cost") or {}
    session.add(Handoff(
        handoff_id=hid, handoff_hash=doc["handoff_hash"], created_at=doc["created_at"],
        created_by=doc.get("created_by", "human"), status="dispatched", path=str(path),
        n_districts=len(doc.get("districts", [])), n_reps=cost.get("n_reps", 0),
        total_usd=cost.get("total_usd", 0.0), cost_provenance=cost.get("provenance", "unknown"),
        district_ids=[d["district_id"] for d in doc.get("districts", [])],
        council_ids=sorted((doc.get("councils") or {}).keys()),
        # #618: mirror the frozen doc's own type onto the queryable index, so the provenance-scoped
        # guards (#619) can join school_fact -> extraction.handoff_hash -> handoff without opening
        # the file. The doc on disk stays the authority; this row is the index over it.
        dispatch_type=BM.effective_dispatch_type(doc)))
    session.flush()
    return hid


def _record_dispatched_events(session, doc: dict, actor: str, metas: dict) -> None:
    """Record a `dispatched` gate@6 state_event per district ON THE SAME SESSION as the handoff row
    (so the index row + the events commit atomically — `current_state` is a VIEW over `state_event`,
    no separate snapshot to update). Carries the district's real name (from `metas`, not a possibly-empty
    current_state lookup), the frozen fingerprints, and the handoff hash. A pure checkpoint event
    (stage=NULL), so it never moves furthest_stage. The district_status.json backup is NOT refreshed
    here (issue #39): these events are flushed-not-committed, and dispatch_handoff writes the immutable
    file after this — an export now could bake phantom `dispatched` events into the backup if the file
    write then failed and the DB rolled back. The export runs LAST, in dispatch_handoff."""
    ts = HND._now()
    for d in doc.get("districts", []):
        did = d["district_id"]
        meta = metas.get(did) or {}
        fp = (doc.get("fingerprints") or {}).get(did)
        session.execute(DS.INSERT_STATE_EVENT, {
            "district_id": did, "name": meta.get("name", ""), "state": meta.get("state"),
            "stage": None, "stage_name": None, "checkpoint": "gate@6",
            "event_type": "dispatched", "outcome": None, "topology": meta.get("labeled_topology"),
            "batch_id": None, "fingerprints_json": json.dumps(fp) if fp else None,
            "actor": actor, "note": doc.get("handoff_hash"), "created_at": ts})
        # gate@6 calibration (REQ-121/#210): a shadow-mode row per dispatched district, on THIS session
        # alongside the state_event — the n_send proxy vs. the accept-only human dispatch decision.
        # n_send counts records with a decision of "send" AND a non-empty reps list (#218 review):
        # release.decide can emit decision="send" with zero usable reps (";no-usable-rep"), and a record
        # that dispatched nothing must not read as a send — that phantom would log agreed=True for a
        # dispatch that paid for nothing. (Distinct from package.py's n_send_reps, which counts FILES.)
        n_send = sum(1 for r in d.get("records", []) if r.get("decision") == "send" and r.get("reps"))
        CAL.record_calibration(session, GCAL.gate6_dispatch_record(
            handoff_hash=doc.get("handoff_hash"), district_id=did, n_send=n_send,
            state=meta.get("state"), created_at=ts))
    session.flush()


def record_dispatch(session, doc: dict, path, actor: str = "human", metas: dict = None) -> str:
    """Persist a dispatch atomically on `session`: the precious handoff index row + the per-district
    `dispatched` state_events (real district names from `metas`)."""
    hid = insert_handoff_row(session, doc, path)
    _record_dispatched_events(session, doc, actor, metas or {})
    return hid


def dispatch_handoff(session, district_ids, created_by: str = "human", root=None,
                     councils=None, cost_model=None, overrides=None, verified_only=False,
                     dispatch_type=BM.DISPATCH_PRODUCTION, bundle=None, redo=False):
    """Freeze + record a dispatch (up to — not including — the paid Stage-7 calls): build the package
    from the DB release decision, freeze it, RECORD the index row + state events (atomic on `session`),
    then write the immutable file LAST — so any DB failure rolls back cleanly with no orphaned record,
    and a same-identity collision (FileExistsError) leaves the prior dispatch intact. `verified_only` =
    gate@6 training-grade mode (labeled targets only), frozen into the doc's identity. `redo` (#717)
    likewise: it changes WHICH reps compose, so it must be frozen into the identity — a dispatch that
    redoes and a dispatch that does not are different artifacts. Returns (doc, path)."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    # #659: reuse the caller's assembly when it has one (the staleness gate just built it), so the
    # package whose identity was checked is the package that gets frozen — not an equivalent rebuild.
    b = bundle or release_bundle(session, district_ids, councils=councils, cost_model=cost_model,
                                 overrides=overrides, verified_only=verified_only,
                                 dispatch_type=dispatch_type, redo=redo)
    metas, skipped = b.metas, b.skipped
    if not b.package.get("districts"):
        # Refuse to freeze a 0-district handoff (issue #53): an all-unknown (or empty) selection is
        # an operator error, not a dispatchable artifact.
        raise ValueError(
            "dispatch refused: the effective selection is empty — "
            + (f"none of the selected districts exist in the release store "
               f"(unknown ids skipped: {skipped})" if skipped else "no districts were selected"))
    package = b.package
    package["dispatch_type"] = BM.validate_dispatch_type(package.get("dispatch_type"))
    # freeze-only, and after the 0-district refusal so an empty selection costs no queries
    fingerprints = {did: REL.district_fingerprints(session, did) for did in metas}
    # #618: the provenance guard, BEFORE the freeze — the frozen artifact is immutable, so a wrong
    # dispatch_type is unrecoverable. Raising here rolls the session back with nothing written, the
    # same posture as the 0-district refusal above.
    assert_dispatch_type_allowed(session, package)
    doc = HND.freeze(package, councils, fingerprints, created_by=created_by)
    path = (Path(root) if root else HND.DEFAULT_ROOT) / HND.handoff_filename(doc)
    record_dispatch(session, doc, path, actor=created_by, metas=metas)
    HND.write(doc, root=root)            # the immutable file LAST (commit-order: DB record, then disk)
    _stage6_capture_receipts(doc, path)  # REQ-164: per-district audit receipt pointing at the handoff
    # district_status.json refresh runs TRULY LAST (issue #39): only after the file write succeeded —
    # if write() had raised, the session would roll back and an earlier export would have baked
    # phantom `dispatched` events into the git-tracked backup. Best-effort, as everywhere: the DB is
    # authoritative and the backup regenerates on the next save/export.
    try:
        DS.export_status(session)
    except Exception as e:
        print(f"[warn] district_status.json backup refresh failed after dispatch "
              f"({type(e).__name__}: {e}); the DB is authoritative — re-export later")
    return doc, path


def _stage6_capture_receipts(doc: dict, handoff_path: Path) -> None:
    """One per-district Stage-6 audit receipt into each district's capture dir (REQ-164). The handoff is
    a per-DISPATCH bundle (acquisition/handoffs/handoff_<hash>_<ts>.json — the authoritative immutable
    file); this projects each district's slice (the council package it was dispatched under) and points
    at that file. Best-effort per district — the handoff file + gov DB are authoritative, so a disk
    hiccup is logged, never a failed dispatch (the receipt is regenerable)."""
    hh = doc.get("handoff_hash")
    for d in doc.get("districts", []):
        did = d.get("district_id")
        if not did:
            continue
        try:
            RCPT.write_receipt(did, "", "stage6_dispatch", {
                "stage": 6, "stage_name": "dispatch", "checkpoint": "gate@6", "district_id": did,
                "handoff_hash": hh,
                "authoritative": f"acquisition/handoffs/{handoff_path.name} + gov_db:handoff/extraction_request",
                "handoff_file": handoff_path.name, "district": d})
        except Exception as e:  # noqa: BLE001 — the receipt is regenerable; never fail a dispatch
            print(f"[warn] Stage 6 capture-dir receipt failed for {did} "
                  f"({type(e).__name__}: {e}); regenerable from the handoff file")
