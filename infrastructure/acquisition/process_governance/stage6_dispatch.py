"""Stage 6 release->routing bridge (REQ-101, app layer).

The one module allowed to import BOTH stage5 `release` and the stage6 modules — it lives in
`process_governance` (the top app layer) precisely so the stage packages stay independent (the §12
import-linter contract: stage6 must not import stage5). It reads the Stage-5 release decision from the
governance DB, enriches each `send` rep with the size signals routing/cost need, and hands it to the
pure `package` assembler — producing the in-memory handoff package (slice 5 persists it immutably).
"""
import json
from pathlib import Path

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import calibration as CAL
from infrastructure.acquisition.common import district_status as DS
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
        content year wins, then time density (the prefer-recent tie discipline).
      * "or A-scoring" (the REQ's unlabeled arm) is STRUCTURALLY ready but inactive: no detector emits
        a hub category today (hub-ness is human/topology knowledge), so an unlabeled tier-A record can
        never satisfy the hub test — when a hub detector exists, it joins this predicate, not a new pass.
    ZERO recall cost by construction: hold, never reject; verified_only composes upstream (a labeled
    hub IS a labeled target, so it survives training-grade mode)."""
    hubs = [r for r in sendables if r.get("label") in HUB_LABELS]
    if not hubs:
        return None, set()
    winner = max(hubs, key=lambda r: (r["year"] if r["year"] is not None else -1, r.get("n_times") or 0))
    return winner["rec_key"], {r["rec_key"] for r in sendables if r["rec_key"] != winner["rec_key"]}


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


def district_release_input(session, district_id: str, verified_only: bool = False):
    """Read one district's release decision from the DB, shaped for stage6 assembly:
    `(district_meta, [records])`. Returns None if the district isn't present.

    `verified_only` (gate@6 training-grade mode): dispatch ONLY human-labeled target sends. The
    speculative unlabeled tier-A auto-sends (`reason == auto:tier-A`) are downgraded to `hold` — not
    silently dropped — so they stay traceable and can be labeled later. Stage-5's `filtered.json` is
    unaffected: this is a dispatch-time choice, not a change to the release rule."""
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
                              "n_times": max((r.get("n_times") or 0) for r in rec.get("reps") or [{}]),
                              "wd_strong": any(d.get("name") == "lf_nonstandard_day"
                                               and d.get("strength") == "strong"
                                               for d in sig.get("detectors") or []),
                              "schools": rec.get("intended_schools") or []})
    # #107 prefer-recent (dispatch-time): HOLD a stale same-school sibling — the newest still sends, the
    # older is available for a cheap 7->6 re-dispatch if extraction fails. Composes after verified_only.
    by_key = {rd["rec_key"]: rd for rd in records}   # O(1) lookup instead of rescanning `records` per hold
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
    # itself; every other surviving send is HELD for the 7→6 back-edge. Runs AFTER prefer-recent so a
    # stale hub already held by a newer same-school sibling can't be the winner.
    survivors = [s for s in sendables if by_key[s["rec_key"]]["decision"] == "send"]
    hub_winner, hub_holds = _hub_priority_holds(survivors)
    for rk in hub_holds:
        rd = by_key.get(rk)
        if rd is not None and rd["decision"] == "send":
            rd["decision"], rd["send"] = "hold", []
            rd["reason"] = f"hub-priority:first-dispatch-narrowed-to:{hub_winner}"
    return district, records


def build_handoff_package(session, district_ids, councils=None, cost_model=None, overrides=None,
                          verified_only=False, dispatch_type=BM.DISPATCH_PRODUCTION) -> dict:
    """Assemble the in-memory handoff package for `district_ids` from the DB release decision.
    Pure stage6 logic does the routing/pricing; this layer only supplies the data. `overrides` =
    gate@6 per-rep council overrides ({"<rec_key>::<file>": council_id}). `verified_only` = gate@6
    training-grade mode (labeled targets only); stamped onto the package so preview + freeze agree.
    `dispatch_type` (#618) is stamped the same way — validated but NOT forced here; the provenance
    guard runs at freeze (`assert_dispatch_type_allowed`), so a preview can still be BUILT and
    displayed for a draft that currently can't be frozen. That is what lets the human see the problem
    and fix it, rather than the console failing to render the draft at all."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    BM.validate_dispatch_type(dispatch_type)
    districts = []
    for did in district_ids:
        di = district_release_input(session, did, verified_only=verified_only)
        if di:
            districts.append(di)
    package = PKG6.assemble_package(districts, councils, cost_model, overrides)
    package["verified_only"] = bool(verified_only)
    package["dispatch_type"] = dispatch_type
    return package


def benchmark_reps_in_package(session, package: dict) -> list:
    """The package's representations carrying BENCHMARK provenance, as [{district_id, rec_key}].

    REPRESENTATION grain, never district grain (#618). A district that merely *was* in a benchmark
    batch is not the question — epic #617 exists to retire exactly that proxy. The question is whether
    the reps this dispatch actually selected trace back to benchmark injection
    (`capture.source='benchmark_gt'`), which is real and mixed after a #620 re-run: Node's #174
    follow-up seeding carries prior records verbatim into the new manifest, so a re-run district
    legitimately holds stale `gt://` reps alongside fresh ones."""
    by_key = {r["rec_key"]: d["district_id"]
              for d in package.get("districts", []) for r in d.get("records", [])
              if r.get("rec_key")}
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
                     dispatch_type=BM.DISPATCH_PRODUCTION):
    """Freeze + record a dispatch (up to — not including — the paid Stage-7 calls): build the package
    from the DB release decision, freeze it, RECORD the index row + state events (atomic on `session`),
    then write the immutable file LAST — so any DB failure rolls back cleanly with no orphaned record,
    and a same-identity collision (FileExistsError) leaves the prior dispatch intact. `verified_only` =
    gate@6 training-grade mode (labeled targets only), frozen into the doc's identity. Returns (doc, path)."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    districts_input, metas, fingerprints, skipped = [], {}, {}, []
    for did in district_ids:
        di = district_release_input(session, did, verified_only=verified_only)
        if not di:
            skipped.append(did)          # unknown district — skipped from the package (surfaced below)
            continue
        meta, _records = di
        districts_input.append(di)
        metas[did] = meta
        fingerprints[did] = REL.district_fingerprints(session, did)
    if not districts_input:
        # Refuse to freeze a 0-district handoff (issue #53): an all-unknown (or empty) selection is
        # an operator error, not a dispatchable artifact.
        raise ValueError(
            "dispatch refused: the effective selection is empty — "
            + (f"none of the selected districts exist in the release store "
               f"(unknown ids skipped: {skipped})" if skipped else "no districts were selected"))
    package = PKG6.assemble_package(districts_input, councils, cost_model, overrides)
    package["verified_only"] = bool(verified_only)
    package["dispatch_type"] = BM.validate_dispatch_type(dispatch_type)
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
