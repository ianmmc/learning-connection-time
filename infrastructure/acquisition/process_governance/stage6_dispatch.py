"""Stage 6 release->routing bridge (REQ-101, app layer).

The one module allowed to import BOTH stage5 `release` and the stage6 modules — it lives in
`process_governance` (the top app layer) precisely so the stage packages stay independent (the §12
import-linter contract: stage6 must not import stage5). It reads the Stage-5 release decision from the
governance DB, enriches each `send` rep with the size signals routing/cost need, and hands it to the
pure `package` assembler — producing the in-memory handoff package (slice 5 persists it immutably).
"""
import json
from pathlib import Path

from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import cost as COST6
from infrastructure.acquisition.stage6_handoff import handoff as HND
from infrastructure.acquisition.stage6_handoff import package as PKG6
from infrastructure.acquisition.stage6_handoff.models import Handoff


def _enrich_send(decision_send: list, reps: list) -> list:
    """Join each release `send` entry ({file, kind, pages?}) back to its representation row to attach
    `n_chars`/`n_times` (which the release descent dropped) — routing keys on kind, cost on size."""
    by_file = {r.get("filename"): r for r in (reps or [])}
    out = []
    for s in decision_send or []:
        rr = by_file.get(s.get("file"), {})
        out.append({**s, "n_chars": rr.get("n_chars"), "n_times": rr.get("n_times")})
    return out


def district_release_input(session, district_id: str):
    """Read one district's release decision from the DB, shaped for stage6 assembly:
    `(district_meta, [records])`. Returns None if the district isn't present."""
    district = REL.load_district(session, district_id)
    if not district:
        return None
    records = []
    for rec in REL.load_district_records(session, district_id):
        d = REL.decide(rec)
        records.append({
            "rec_key": rec["rec_key"], "url": rec.get("url"),
            "decision": d["decision"], "reason": d["reason"],
            "signals": rec.get("signals") or {},
            "send": _enrich_send(d["send"], rec.get("reps")),
        })
    return district, records


def build_handoff_package(session, district_ids, councils=None, cost_model=None) -> dict:
    """Assemble the in-memory handoff package for `district_ids` from the DB release decision.
    Pure stage6 logic does the routing/pricing; this layer only supplies the data."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    districts = []
    for did in district_ids:
        di = district_release_input(session, did)
        if di:
            districts.append(di)
    return PKG6.assemble_package(districts, councils, cost_model)


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
    (stage=NULL), so it never moves furthest_stage. The git-tracked JSON backup is refreshed best-effort."""
    for d in doc.get("districts", []):
        did = d["district_id"]
        meta = metas.get(did) or {}
        fp = (doc.get("fingerprints") or {}).get(did)
        session.execute(DS.INSERT_STATE_EVENT, {
            "district_id": did, "name": meta.get("name", ""), "state": None,
            "stage": None, "stage_name": None, "checkpoint": "gate@6",
            "event_type": "dispatched", "outcome": None, "topology": meta.get("labeled_topology"),
            "batch_id": None, "fingerprints_json": json.dumps(fp) if fp else None,
            "actor": actor, "note": doc.get("handoff_hash"), "created_at": HND._now()})
    session.flush()
    try:
        DS.export_status(session)   # refresh district_status.json from the now-flushed events (the DB is truth)
    except Exception as e:
        print(f"[warn] district_status.json backup refresh failed after dispatch "
              f"({type(e).__name__}: {e}); the DB is authoritative — re-export later")


def record_dispatch(session, doc: dict, path, actor: str = "human", metas: dict = None) -> str:
    """Persist a dispatch atomically on `session`: the precious handoff index row + the per-district
    `dispatched` state_events (real district names from `metas`)."""
    hid = insert_handoff_row(session, doc, path)
    _record_dispatched_events(session, doc, actor, metas or {})
    return hid


def dispatch_handoff(session, district_ids, created_by: str = "human", root=None,
                     councils=None, cost_model=None):
    """Freeze + record a dispatch (up to — not including — the paid Stage-7 calls): build the package
    from the DB release decision, freeze it, RECORD the index row + state events (atomic on `session`),
    then write the immutable file LAST — so any DB failure rolls back cleanly with no orphaned record,
    and a same-identity collision (FileExistsError) leaves the prior dispatch intact. Returns (doc, path)."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    districts_input, metas, fingerprints = [], {}, {}
    for did in district_ids:
        di = district_release_input(session, did)
        if not di:
            continue                     # unknown district — silently skipped from the package
        meta, _records = di
        districts_input.append(di)
        metas[did] = meta
        fingerprints[did] = REL.district_fingerprints(session, did)
    package = PKG6.assemble_package(districts_input, councils, cost_model)
    doc = HND.freeze(package, councils, fingerprints, created_by=created_by)
    path = (Path(root) if root else HND.DEFAULT_ROOT) / HND.handoff_filename(doc)
    record_dispatch(session, doc, path, actor=created_by, metas=metas)
    HND.write(doc, root=root)            # the immutable file LAST (commit-order: DB record, then disk)
    return doc, path
