"""Cross-stage per-district lifecycle state for the acquisition pipeline (all 9 stages).

**REQ-099: this is now an EVENT LOG in the isolated governance Postgres DB**, not a JSON
registry. Every stage transition / checkpoint is an append-only `state_event` row; the
"where is each district" snapshot is the derived `current_state` SQL view (latest event +
furthest stage reached). The DB is the authoritative store; `district_status.json` is demoted
to a **regenerable, version-controlled backup + human-readable view** (written on every save,
re-importable after a DB wipe — the same precious-backup pattern as labels.json).

The **in-memory `registry` contract is unchanged** so the stage scripts barely change:
`load()` builds the registry from the DB; `record_stage(registry, …)` and
`already_attempted(registry, …)` are PURE in-memory dict ops (no DB) that also buffer the new
event; `save(registry)` flushes the buffered events to `state_event` and regenerates the JSON.

The log is UNIFIED (REQ-099 decision): it records both stage-progression events (queued /
discovered / captured / processed — `stage`+`outcome`) AND checkpoint lifecycle events (CP-A
approved, CP-B released, … — `checkpoint`+`event_type`), one timeline per district. `actor`
carries identity (`auto:stage3`, `ian`, `auto:scheduler`) from day one (governance §7a-D).

already_attempted() still only excludes a district once it has reached Stage 3 (Capture) — a
district merely queued (Stage 1) or searched (Stage 2) has had no real, costly attempt yet and
stays eligible for redraw (e.g. after a queue-time bug fix).

Schema reference: data/acquisition/status/district_status.example.json
Doc: docs/ACQUISITION_PIPELINE.md (Stage 1), docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md §3
"""
from datetime import datetime, timezone
import json

from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import paths  # noqa: E402  (single source of truth for runtime-state locations — REQ-087)
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (isolated governance Postgres — REQ-103)

STATUS_FILE = paths.STATUS_FILE
SCHEMA_VERSION = 2   # 1 = JSON registry; 2 = Postgres state_event log + regenerable JSON backup

# Stage 3 = Capture is the first stage with a real, costly attempt (an actual fetch of a
# district/school page). Stage 1 (Queue) and Stage 2 (Discover) just target/search -- a
# district that only reached one of those has not actually been "tried" yet, so it must
# stay eligible for redraw (e.g. after a Stage 1 bug fix). Found 2026-06-22: re-running
# queue_batch.py after a school_sampling.py fix silently excluded every district from the
# prior (never-captured) batch_00001, masking the fix instead of demonstrating it.
ATTEMPTED_THRESHOLD_STAGE = 3


class StateEvent(gdb.Base):
    """PRECIOUS append-only lifecycle event (one row per stage transition / checkpoint). Never
    dropped; backed to district_status.json. `current_state` (a view) projects the snapshot."""
    __tablename__ = "state_event"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)
    stage: Mapped[int | None] = mapped_column(Integer)            # 1..9, or NULL for a pure checkpoint event
    stage_name: Mapped[str | None] = mapped_column(String)
    checkpoint: Mapped[str | None] = mapped_column(String)        # 'CP-A' | 'CP-B' | 'CP-C' | NULL
    event_type: Mapped[str] = mapped_column(String)              # progression: the outcome; checkpoint: approved/released/…
    outcome: Mapped[str | None] = mapped_column(String)
    topology: Mapped[str | None] = mapped_column(String)
    batch_id: Mapped[str | None] = mapped_column(String)
    fingerprints_json: Mapped[str | None] = mapped_column(String)  # (config,labels,data) at the moment, when relevant
    actor: Mapped[str | None] = mapped_column(String)            # 'auto:stage3' | 'ian' | 'auto:scheduler' | …
    note: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


# current_state: the derived snapshot (one row per district). furthest_stage = MAX(stage) ever
# reached (drives already_attempted, monotonic even if a re-discovery event has a lower stage);
# the displayed snapshot comes from the latest STAGE event; name/state fall back to the latest
# event of any kind. event_id (serial) is the definitive ordering tiebreaker within a second.
CURRENT_STATE_VIEW = """
CREATE OR REPLACE VIEW current_state AS
WITH max_stage AS (
  SELECT district_id, MAX(stage) AS furthest_stage FROM state_event GROUP BY district_id
),
latest_stage AS (
  SELECT DISTINCT ON (district_id)
    district_id, name, state, stage_name, outcome, topology, batch_id
  FROM state_event WHERE stage IS NOT NULL
  ORDER BY district_id, event_id DESC
),
latest_any AS (
  SELECT DISTINCT ON (district_id)
    district_id, name AS any_name, state AS any_state,
    event_type AS last_event_type, checkpoint AS last_checkpoint, created_at AS last_event_at
  FROM state_event ORDER BY district_id, event_id DESC
)
SELECT m.district_id,
       COALESCE(ls.name, la.any_name)  AS name,
       COALESCE(ls.state, la.any_state) AS state,
       m.furthest_stage, ls.stage_name, ls.outcome, ls.topology, ls.batch_id,
       la.last_event_type, la.last_checkpoint, la.last_event_at
FROM max_stage m
LEFT JOIN latest_stage ls ON ls.district_id = m.district_id
LEFT JOIN latest_any   la ON la.district_id = m.district_id
"""

INSERT_STATE_EVENT = text(
    """INSERT INTO state_event (district_id, name, state, stage, stage_name, checkpoint,
         event_type, outcome, topology, batch_id, fingerprints_json, actor, note, created_at)
       VALUES (:district_id, :name, :state, :stage, :stage_name, :checkpoint,
         :event_type, :outcome, :topology, :batch_id, :fingerprints_json, :actor, :note, :created_at)""")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_schema() -> None:
    """Create the precious state_event table (never dropped) + the current_state view, if absent.
    Idempotent. Called at the top of load()/save() so the stage scripts need no separate setup."""
    StateEvent.__table__.create(gdb.get_engine(), checkfirst=True)
    with gdb.session_scope() as s:
        s.execute(text(CURRENT_STATE_VIEW))


# ----------------------------- in-memory registry ops (NO DB — pure dict) -----------------------------
def already_attempted(registry: dict, district_id: str) -> bool:
    """True only once a district has reached Stage 3 (Capture) or beyond -- Stage 1/2-only
    districts (queued or searched but never actually fetched) remain eligible for redraw."""
    d = registry["districts"].get(district_id)
    return d is not None and (d.get("furthest_stage") or 0) >= ATTEMPTED_THRESHOLD_STAGE


def record_stage(
    registry: dict,
    district_id: str,
    name: str,
    state: str,
    stage: int | None = None,
    stage_name: str | None = None,
    outcome: str | None = None,
    topology: str | None = None,
    batch_id: str | None = None,
    notes: str = "",
    *,
    checkpoint: str | None = None,
    event_type: str | None = None,
    actor: str | None = None,
    fingerprints: dict | None = None,
) -> dict:
    """Update the in-memory snapshot + history AND buffer a state_event (flushed by save()). Pure
    in-memory — no DB touch — so the stage scripts' reconcile logic and the unit tests need no DB.

    A stage-progression event passes `stage`/`outcome` (the default `event_type` is the outcome,
    `actor` is `auto:stage{stage}`). A checkpoint event passes `checkpoint`/`event_type`/`actor`
    (e.g. CP-A approved by `ian`) and usually no `stage` — it doesn't move `furthest_stage`."""
    d = registry["districts"].setdefault(district_id, {"name": name, "state": state, "history": []})
    d["name"] = name
    d["state"] = state
    d["notes"] = notes
    if stage is not None:
        d["furthest_stage"] = max(d.get("furthest_stage") or 0, stage)   # deepest stage ever reached
        d["stage_name"] = stage_name
        d["outcome"] = outcome
        d["topology"] = topology
        d["batch_id"] = batch_id
    et = event_type or outcome or ("checkpoint" if checkpoint else "event")
    act = actor or (f"auto:stage{stage}" if stage is not None else "auto")
    at = _now()
    hist = {"stage": stage, "stage_name": stage_name, "outcome": outcome, "at": at}
    if checkpoint or event_type or (actor and actor != f"auto:stage{stage}"):
        hist.update({k: v for k, v in (("checkpoint", checkpoint), ("event_type", et),
                                       ("actor", act)) if v})
    d["history"].append(hist)
    registry.setdefault("_events", []).append({
        "district_id": district_id, "name": name, "state": state, "stage": stage,
        "stage_name": stage_name, "checkpoint": checkpoint, "event_type": et, "outcome": outcome,
        "topology": topology, "batch_id": batch_id,
        "fingerprints_json": json.dumps(fingerprints) if fingerprints else None,
        "actor": act, "note": notes, "created_at": at})
    return d


# ----------------------------- DB-backed persistence -----------------------------
def load() -> dict:
    """Build the in-memory registry from the DB current_state view (the snapshot per district),
    plus an empty `_events` buffer for new events. Requires the governance DB (Docker up)."""
    ensure_schema()
    reg = {"schema_version": SCHEMA_VERSION, "last_updated": None, "districts": {}, "_events": []}
    with gdb.session_scope() as s:
        for r in s.execute(text(
            "SELECT district_id, name, state, furthest_stage, stage_name, outcome, topology, batch_id "
            "FROM current_state")).mappings():
            reg["districts"][r["district_id"]] = {
                "name": r["name"], "state": r["state"], "furthest_stage": r["furthest_stage"] or 0,
                "stage_name": r["stage_name"], "outcome": r["outcome"], "topology": r["topology"],
                "batch_id": r["batch_id"], "history": []}
    return reg


def save(registry: dict, *, export: bool = True) -> int:
    """Flush the buffered events to state_event (append), then regenerate district_status.json from
    the full DB log (the version-controlled backup + human view). Returns the # events written.

    `export=False` (issue #49): batch runners save per district in a loop, and regenerating the FULL
    JSON from the whole event log on every save is O(N²) over a run. They pass export=False per
    district and call one explicit `export()` at run end (and in their `finally`, so a crash still
    exports). Default True keeps the single-call behavior for every other caller."""
    ensure_schema()
    events = registry.get("_events", [])
    with gdb.session_scope() as s:
        for ev in events:
            s.execute(INSERT_STATE_EVENT, ev)
        s.commit()                 # persist before exporting, so the backup only reflects committed state
        if export:
            export_status(s)
    registry["_events"] = []
    return len(events)


def export() -> int:
    """Regenerate district_status.json from the committed DB log in a fresh session — the explicit
    run-end companion to save(export=False) (issue #49). Returns the # districts exported."""
    ensure_schema()
    with gdb.session_scope() as s:
        return export_status(s)


def export_status(s, out=None) -> int:
    """Regenerate district_status.json from the full state_event log: per district, the snapshot
    (from current_state) + the full ordered history[]. The precious, git-tracked backup (atomic)."""
    out = out or STATUS_FILE
    snap = {r["district_id"]: dict(r) for r in s.execute(text(
        "SELECT district_id, name, state, furthest_stage, stage_name, outcome, topology, batch_id "
        "FROM current_state")).mappings()}
    districts = {}
    for did, sn in sorted(snap.items()):
        districts[did] = {
            "name": sn["name"], "state": sn["state"], "furthest_stage": sn["furthest_stage"] or 0,
            "stage_name": sn["stage_name"], "outcome": sn["outcome"], "topology": sn["topology"],
            "batch_id": sn["batch_id"], "history": [], "notes": ""}
    for r in s.execute(text(
        "SELECT district_id, stage, stage_name, outcome, checkpoint, event_type, actor, note, created_at "
        "FROM state_event ORDER BY district_id, event_id")).mappings():
        d = districts.setdefault(r["district_id"], {"history": [], "notes": ""})
        h = {"stage": r["stage"], "stage_name": r["stage_name"], "outcome": r["outcome"], "at": r["created_at"]}
        if r["checkpoint"] or (r["event_type"] and r["event_type"] != r["outcome"]):
            h.update({k: v for k, v in (("checkpoint", r["checkpoint"]), ("event_type", r["event_type"]),
                                        ("actor", r["actor"])) if v})
        d["history"].append(h)
        if r["note"]:
            d["notes"] = r["note"]   # carry the latest non-empty note up to the district level
    doc = {"schema_version": SCHEMA_VERSION, "last_updated": _now(), "districts": districts}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2))
    tmp.replace(out)   # atomic
    return len(districts)


def import_status_json(src=None) -> int:
    """Replay a district_status.json backup into state_event — the migration / post-wipe restore
    path. Idempotent: a NO-OP if state_event already has rows (so it never double-inserts). Each
    district's history[] becomes events; per-event topology/batch_id default to the snapshot's.
    Returns the # events inserted."""
    src = src or STATUS_FILE
    ensure_schema()
    if not src.exists():
        return 0
    doc = json.loads(src.read_text())
    n = 0
    with gdb.session_scope() as s:
        if s.execute(text("SELECT 1 FROM state_event LIMIT 1")).first():
            return 0   # already populated — don't duplicate
        for did, d in doc.get("districts", {}).items():
            for h in d.get("history", []):
                stage = h.get("stage")
                s.execute(INSERT_STATE_EVENT, {
                    "district_id": did, "name": d.get("name"), "state": d.get("state"),
                    "stage": stage, "stage_name": h.get("stage_name"),
                    "checkpoint": h.get("checkpoint"),
                    "event_type": h.get("event_type") or h.get("outcome") or "event",
                    "outcome": h.get("outcome"), "topology": d.get("topology"),
                    "batch_id": d.get("batch_id"),
                    "fingerprints_json": None,
                    "actor": h.get("actor") or (f"auto:stage{stage}" if stage is not None else "auto:migrated"),
                    "note": d.get("notes", ""), "created_at": h.get("at") or _now()})
                n += 1
    return n
