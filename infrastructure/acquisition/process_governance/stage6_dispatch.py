"""Stage 6 release->routing bridge (REQ-101, app layer).

The one module allowed to import BOTH stage5 `release` and the stage6 modules — it lives in
`process_governance` (the top app layer) precisely so the stage packages stay independent (the §12
import-linter contract: stage6 must not import stage5). It reads the Stage-5 release decision from the
governance DB, enriches each `send` rep with the size signals routing/cost need, and hands it to the
pure `package` assembler — producing the in-memory handoff package (slice 5 persists it immutably).
"""
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


def _record_dispatched_events(doc: dict, actor: str) -> None:
    """Record a `dispatched` gate@6 state_event per district, referencing the handoff hash + the
    frozen (config,labels,data) fingerprints. Mirrors the §12 Stage-4->5 event-recording pattern."""
    registry = DS.load()
    for d in doc.get("districts", []):
        did = d["district_id"]
        cur = registry["districts"].get(did, {})
        DS.record_stage(registry, did, cur.get("name", ""), cur.get("state", ""),
                        checkpoint="gate@6", event_type="dispatched", actor=actor,
                        fingerprints=(doc.get("fingerprints") or {}).get(did), notes=doc["handoff_hash"])
    DS.save(registry)


def record_dispatch(session, doc: dict, path, actor: str = "human") -> str:
    """Persist a dispatch: the precious handoff index row + the per-district `dispatched` state_events."""
    hid = insert_handoff_row(session, doc, path)
    _record_dispatched_events(doc, actor)
    return hid


def dispatch_handoff(session, district_ids, created_by: str = "human", root=None,
                     councils=None, cost_model=None):
    """Freeze + record a dispatch (up to — not including — the paid Stage-7 calls): build the package
    from the DB release decision, freeze it to the immutable artifact, write it, and record the index
    row + state events. Returns (doc, path). gate@6 (manual/auto + cost gate) wraps this later."""
    councils = councils or C6.load_configs()
    cost_model = cost_model or COST6.load_cost_model()
    package = build_handoff_package(session, district_ids, councils, cost_model)
    fingerprints = {did: REL.district_fingerprints(session, did)
                    for did in district_ids if REL.load_district(session, did)}
    doc = HND.freeze(package, councils, fingerprints, created_by=created_by)
    path = HND.write(doc, root=root)
    record_dispatch(session, doc, path, actor=created_by)
    return doc, path
