"""gate@8 approval — record + query the human's per-district decision (STAGE8 §2b/§2e).

The one WRITE the standalone Stage 8 adds. `record_decision` freezes the closing argument a reviewer
acted on into a precious `stage8_approval` row + a `state_event` (checkpoint='gate@8'), append-only.
`decision_status` tells the console (and, later, Stage 9) whether a district is currently approved AND
whether that approval is still fresh vs the live facts.

DB I/O over the governance session (the closing-argument assembly + fingerprint are pure — in
`closing_argument`). Manual-first: `actor` is the human today; the same rows carry `auto:...` when a
future confidence-escalating gate@8 is licensed (§2d), no schema change.
"""
from __future__ import annotations

import json

from sqlalchemy import text

from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common.timeutil import utcnow
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA

DISPOSITIONS = ("approved", "sent_back")


def record_decision(con, closing_argument, *, disposition, actor="ian", reason=None,
                    name="", state=None):
    """Record a gate@8 decision on a whole district (§2e per-district grain). Freezes `closing_argument`
    as the receipt + its fingerprint. `disposition` ∈ DISPOSITIONS; a 'sent_back' REQUIRES a reason (why
    the picture isn't publishable / which band routes an 8→1). Writes the precious row + a state_event.
    Returns the new approval_id. The caller commits (and backs up the tracked JSON), matching gate_mode."""
    if disposition not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {DISPOSITIONS} (got {disposition!r})")
    if disposition == "sent_back" and not (reason or "").strip():
        raise ValueError("a 'sent_back' decision requires a reason (why the district isn't publishable)")

    did = closing_argument["district_id"]
    fp = CA.fingerprint(closing_argument)
    now = utcnow()
    approval_id = con.execute(text(
        "INSERT INTO stage8_approval "
        "(district_id, disposition, actor, reason, facts_fingerprint, receipt_json, created_at) "
        "VALUES (:d, :disp, :actor, :reason, :fp, :receipt, :t) RETURNING approval_id"),
        {"d": did, "disp": disposition, "actor": actor, "reason": reason, "fp": fp,
         "receipt": json.dumps(closing_argument), "t": now}).scalar()

    con.execute(DS.INSERT_STATE_EVENT, {
        "district_id": did, "name": name, "state": state, "stage": 8, "stage_name": "aggregate",
        "checkpoint": "gate@8", "event_type": disposition, "outcome": None, "topology": None,
        "batch_id": None, "fingerprints_json": json.dumps({"facts": fp}), "actor": actor,
        "note": reason, "created_at": now})
    return approval_id


def latest_decision(con, district_id):
    """The newest gate@8 decision for a district, or None if never decided. dict-shaped."""
    row = con.execute(text(
        "SELECT approval_id, district_id, disposition, actor, reason, facts_fingerprint, created_at "
        "FROM stage8_approval WHERE district_id=:d ORDER BY approval_id DESC LIMIT 1"),
        {"d": district_id}).mappings().first()
    return dict(row) if row else None


def decision_status(con, district_id, *, current_fingerprint=None):
    """The console/Stage-9 view of a district's gate@8 state: {decided, disposition, is_approved,
    is_stale, ...}. `is_stale` is True when the latest decision's frozen fingerprint no longer matches
    the live facts (`current_fingerprint`) — a re-extraction changed the picture after the decision, so
    the approval no longer authorizes a write until re-reviewed (§2b re-write boundary)."""
    latest = latest_decision(con, district_id)
    if not latest:
        return {"decided": False, "disposition": None, "is_approved": False, "is_stale": False,
                "latest": None}
    is_stale = bool(current_fingerprint) and current_fingerprint != latest["facts_fingerprint"]
    return {"decided": True, "disposition": latest["disposition"],
            "is_approved": latest["disposition"] == "approved" and not is_stale,
            "is_stale": is_stale, "latest": latest}
