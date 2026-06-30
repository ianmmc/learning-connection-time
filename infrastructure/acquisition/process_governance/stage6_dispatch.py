"""Stage 6 release->routing bridge (REQ-101, app layer).

The one module allowed to import BOTH stage5 `release` and the stage6 modules — it lives in
`process_governance` (the top app layer) precisely so the stage packages stay independent (the §12
import-linter contract: stage6 must not import stage5). It reads the Stage-5 release decision from the
governance DB, enriches each `send` rep with the size signals routing/cost need, and hands it to the
pure `package` assembler — producing the in-memory handoff package (slice 5 persists it immutably).
"""
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import cost as COST6
from infrastructure.acquisition.stage6_handoff import package as PKG6


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
