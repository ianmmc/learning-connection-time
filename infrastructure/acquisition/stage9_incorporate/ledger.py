"""Stage 9 governance-side stamp — the 'incorporated' state_event that closes a district's per-band
lifecycle, plus the idempotency read a re-run consults. Governance session only (this module never
imports the LCT layer; the cross-DB write lives in incorporate.py).

The stamp reuses the free-string `state_event.checkpoint` column (no migration) at stage=9, and
carries the WRITTEN fingerprint in `fingerprints_json` so a later run can compare live-fp vs
incorporated-fp (equal -> already done; approval fresh but != -> a correction to re-write). The LCT
`bell_schedules` row is the source of truth; this ledger is the derived record, written AFTER the LCT
commit (a crash between leaves a lagging ledger the next run reconciles, never a stamp without a row).
"""
from __future__ import annotations

import json

from sqlalchemy import text

from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common.timeutil import utcnow


def record_incorporation(con, district_id, *, fingerprint, approval_id, bands,
                         actor="auto:stage9", name="", state=None, mapper=None):
    """Append an 'incorporated' state_event (stage=9). `bands` = {grade_level: method} just written.
    `mapper` = mapping.MAPPING_VERSION at write time (#631) — half of the idempotency key."""
    con.execute(DS.INSERT_STATE_EVENT, {
        "district_id": district_id, "name": name, "state": state,
        "stage": 9, "stage_name": "incorporate", "checkpoint": "incorporated",
        "event_type": "incorporated", "outcome": None, "topology": None, "batch_id": None,
        "fingerprints_json": json.dumps({"facts": fingerprint, "approval_id": approval_id,
                                         "bands": bands, "mapper": mapper}),
        "actor": actor,
        "note": (f"wrote {len(bands)} band(s): "
                 + ",".join(f"{b}={m}" for b, m in sorted(bands.items()))),
        "created_at": utcnow()})


def latest_incorporation(con, district_id):
    """The newest Stage-9 'incorporated' event for a district, or None:
    {fingerprint, approval_id, bands, created_at}."""
    row = con.execute(text(
        "SELECT fingerprints_json, created_at FROM state_event "
        "WHERE district_id=:d AND checkpoint='incorporated' "
        "ORDER BY event_id DESC LIMIT 1"), {"d": district_id}).mappings().first()
    if not row:
        return None
    fp = json.loads(row["fingerprints_json"] or "{}")
    return {"fingerprint": fp.get("facts"), "approval_id": fp.get("approval_id"),
            "bands": fp.get("bands"), "mapper": fp.get("mapper"),   # absent pre-#631 → None
            "created_at": row["created_at"]}
