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


def record_incorporation_blocked(con, district_id, *, status, reason, actor="auto:stage9",
                                 approval_id=None, fingerprint=None, name="", state=None):
    """#682: an APPROVED district whose Stage-9 write did not happen — refused by one of the write's
    own guards (`not_eligible`: benchmark provenance / stale / foreign collision, or `no_bands`) or
    faulted (`error`). Same stage=9 state_event log as `record_incorporation`, event_type
    'incorporation_blocked', with the machine status in `outcome` and the guard's own words in the note.

    Why it exists: the approve→write arrow fires POST-COMMIT and never fails the approval (the human's
    decision is precious and stands whatever the write does), so without this stamp a miss is a
    SILENCE — the timeline would end at 'approved' while production holds nothing, which is exactly
    the state #682 was filed on (Worcester, 2026-07-28). Paired with `record_incorporation`, the two
    make "approved but never written" a queryable state instead of an absence."""
    con.execute(DS.INSERT_STATE_EVENT, {
        "district_id": district_id, "name": name, "state": state,
        "stage": 9, "stage_name": "incorporate", "checkpoint": "incorporation_blocked",
        "event_type": "incorporation_blocked", "outcome": status, "topology": None, "batch_id": None,
        "fingerprints_json": json.dumps({"facts": fingerprint, "approval_id": approval_id}),
        "actor": actor,
        "note": f"{status}: {reason}" if reason else status,
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


def latest_attempt(con, district_id):
    """The newest Stage-9 OUTCOME of either kind — 'incorporated' or 'incorporation_blocked' — or
    None if the write has never been attempted for this district (#682).

    `latest_incorporation` above answers "what is written" (the idempotency key, deliberately blind
    to failures); this answers "what happened last", which is what a reviewer needs to see after
    clicking Approve. Keeping them separate means a later blocked attempt can never make a written
    district look unwritten to the idempotency check."""
    row = con.execute(text(
        "SELECT checkpoint, outcome, note, fingerprints_json, created_at FROM state_event "
        "WHERE district_id=:d AND checkpoint IN ('incorporated', 'incorporation_blocked') "
        "ORDER BY event_id DESC LIMIT 1"), {"d": district_id}).mappings().first()
    if not row:
        return None
    fp = json.loads(row["fingerprints_json"] or "{}")
    return {"kind": row["checkpoint"], "status": row["outcome"], "note": row["note"],
            "fingerprint": fp.get("facts"), "approval_id": fp.get("approval_id"),
            "bands": fp.get("bands"), "created_at": row["created_at"]}
