"""Stage 6 release->routing bridge (REQ-101, app layer).

The one module allowed to import BOTH stage5 `release` and the stage6 modules — it lives in
`process_governance` (the top app layer) precisely so the stage packages stay independent (the §12
import-linter contract: stage6 must not import stage5). It reads the Stage-5 release decision from the
governance DB, enriches each `send` rep with the size signals routing/cost need, and hands it to the
pure `package` assembler — producing the in-memory handoff package (slice 5 persists it immutably).
"""
import json
from pathlib import Path

from infrastructure.acquisition.common import calibration as CAL
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.process_governance import gate_calibration as GCAL
from infrastructure.acquisition.stage5_filter import release as REL
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
    for rec in REL.load_district_records(session, district_id):
        d = REL.decide(rec)
        decision, reason, send = d["decision"], d["reason"], d["send"]
        if verified_only and decision == "send" and rec.get("label") not in REL.TARGET_LABELS:
            decision, reason, send = "hold", f"verified-only:held({reason})", []
        records.append({
            "rec_key": rec["rec_key"], "url": rec.get("url"),
            "decision": decision, "reason": reason,
            "signals": rec.get("signals") or {},
            "send": _enrich_send(send, rec.get("reps"), rec, district.get("district_dir")),
        })
    return district, records


def build_handoff_package(session, district_ids, councils=None, cost_model=None, overrides=None,
                          verified_only=False) -> dict:
    """Assemble the in-memory handoff package for `district_ids` from the DB release decision.
    Pure stage6 logic does the routing/pricing; this layer only supplies the data. `overrides` =
    gate@6 per-rep council overrides ({"<rec_key>::<file>": council_id}). `verified_only` = gate@6
    training-grade mode (labeled targets only); stamped onto the package so preview + freeze agree."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    districts = []
    for did in district_ids:
        di = district_release_input(session, did, verified_only=verified_only)
        if di:
            districts.append(di)
    package = PKG6.assemble_package(districts, councils, cost_model, overrides)
    package["verified_only"] = bool(verified_only)
    return package


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
        council_ids=sorted((doc.get("councils") or {}).keys())))
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
                     councils=None, cost_model=None, overrides=None, verified_only=False):
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
    doc = HND.freeze(package, councils, fingerprints, created_by=created_by)
    path = (Path(root) if root else HND.DEFAULT_ROOT) / HND.handoff_filename(doc)
    record_dispatch(session, doc, path, actor=created_by, metas=metas)
    HND.write(doc, root=root)            # the immutable file LAST (commit-order: DB record, then disk)
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
