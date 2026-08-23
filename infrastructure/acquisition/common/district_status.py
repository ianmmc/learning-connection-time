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
Doc: docs/ACQUISITION_PIPELINE.md (Stage 1), docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md §3
"""
import json
import re
from datetime import datetime, timezone

from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import paths  # noqa: E402  (single source of truth for runtime-state locations — REQ-087)
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (isolated governance Postgres — REQ-103)
from infrastructure.acquisition.common.timeutil import utcnow as _now

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
# the displayed snapshot comes from the latest STAGE event. name/state resolve to the latest
# NON-NULL/non-empty value across ALL events (#165: not every writer carries them, and the old
# latest-row-wins fallback nulled the header for exactly the districts furthest along — every
# extracted district read state NULL). batch_id deliberately stays event-accurate (the latest
# stage event's value, NULL included): batch membership's authority is batch_district, and
# faking the last-seen batch onto an ad-hoc dispatch's extraction would mislead. event_id
# (serial) is the definitive ordering tiebreaker within a second.
# NOT BATCH-SAFE: this view is one GLOBAL row per district -- joining it per-batch attributes a
# district's first-run progress to every later batch containing it (the #339 bug). A consumer
# needing per-batch state must aggregate state_event scoped to (batch_id, district_id); see
# batch_store._batch_progress for the canonical shape.
CURRENT_STATE_VIEW = """
CREATE OR REPLACE VIEW current_state AS
WITH max_stage AS (
  SELECT district_id, MAX(stage) AS furthest_stage FROM state_event GROUP BY district_id
),
latest_stage AS (
  SELECT DISTINCT ON (district_id)
    district_id, stage_name, outcome, topology, batch_id
  FROM state_event WHERE stage IS NOT NULL
  ORDER BY district_id, event_id DESC
),
latest_name AS (
  SELECT DISTINCT ON (district_id) district_id, name
  FROM state_event WHERE name IS NOT NULL AND name <> ''
  ORDER BY district_id, event_id DESC
),
latest_state_val AS (
  SELECT DISTINCT ON (district_id) district_id, state
  FROM state_event WHERE state IS NOT NULL AND state <> ''
  ORDER BY district_id, event_id DESC
),
latest_any AS (
  SELECT DISTINCT ON (district_id)
    district_id,
    event_type AS last_event_type, checkpoint AS last_checkpoint, created_at AS last_event_at
  FROM state_event ORDER BY district_id, event_id DESC
)
SELECT m.district_id,
       ln.name,
       lsv.state,
       m.furthest_stage, ls.stage_name, ls.outcome, ls.topology, ls.batch_id,
       la.last_event_type, la.last_checkpoint, la.last_event_at
FROM max_stage m
LEFT JOIN latest_stage     ls  ON ls.district_id  = m.district_id
LEFT JOIN latest_name      ln  ON ln.district_id  = m.district_id
LEFT JOIN latest_state_val lsv ON lsv.district_id = m.district_id
LEFT JOIN latest_any       la  ON la.district_id  = m.district_id
"""

INSERT_STATE_EVENT = text(
    """INSERT INTO state_event (district_id, name, state, stage, stage_name, checkpoint,
         event_type, outcome, topology, batch_id, fingerprints_json, actor, note, created_at)
       VALUES (:district_id, :name, :state, :stage, :stage_name, :checkpoint,
         :event_type, :outcome, :topology, :batch_id, :fingerprints_json, :actor, :note, :created_at)""")




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


_REMEDIATION_TS_RE = re.compile(r"_(\d{8}T\d{6}Z)$")
# #575 review: bound the "any past receipt sanctions any future desync, forever" exposure the
# KNOWN RESIDUAL below documents. A receipt older than this no longer excuses a registry-ahead-of-
# disk halt — something else likely went wrong, and a human should see it. Parsed from the receipt
# directory's OWN timestamp (no DB read), so the deliberately DB-free reconciles stay DB-free.
REMEDIATION_RECEIPT_MAX_AGE_DAYS = 30


def remediation_receipt(district_id: str):
    """The newest on-disk decontamination restore point for a district, still within its trust
    window (data/acquisition/remediation/<district_id>_<ts>/, written by remediate_contamination
    BEFORE it mutates anything), or None. The ONE shared home (#572) for the check every stage
    reconcile consults: remediation deliberately removes a district's artifacts while PRESERVING
    its state history (auditability), so registry-ahead-of-disk is that path's expected, receipted
    end state — the stage redoes the work fresh instead of halting.

    KNOWN RESIDUAL (documented trade-off, #572, narrowed #575): the receipt is not STAGE-scoped —
    a receipt from a Stage-2 remediation still excuses a Stage-3/4 desync for the same district. It
    IS now time-bound (REMEDIATION_RECEIPT_MAX_AGE_DAYS): a once-remediated district that later
    loses artifacts for a BAD reason only gets silently redone within that window, not forever.
    Bounded to redundant spend either way, never silent trust: the sanctioned path always REDOES
    the stage (fresh receipts, merge mode), nothing missing is assumed done. Full stage/recency
    tightening (compare the receipt timestamp against the district's latest stage-N state_event)
    needs a DB read inside the deliberately DB-free reconciles — revisit if remediation volume
    grows past a handful of districts."""
    rdir = paths.ACQUISITION / "remediation"
    if not rdir.exists():
        return None
    hits = sorted(p for p in rdir.iterdir() if p.name.startswith(f"{district_id}_") and p.is_dir())
    if not hits:
        return None
    newest = hits[-1]
    m = _REMEDIATION_TS_RE.search(newest.name)
    if m:
        try:
            ts = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
            if age_days > REMEDIATION_RECEIPT_MAX_AGE_DAYS:
                return None
        except ValueError:
            pass   # malformed timestamp — fall through, trust the receipt as before (#572 behavior)
    return newest


def completed_by_batch(batch_id: str, stage_name: str, ids: list) -> set:
    """Districts THIS batch actually FINISHED at `stage_name`: it dispatched them, AND a stage
    outcome landed afterwards. The one home for batch-scoped stage done-ness (#647/#655/#671).

    #671 — WHY THE DISPATCH ALONE IS NOT ENOUGH. This replaces `dispatched_by_batch`, whose
    docstring closed on the claim that made it a bug: *"a batch ... that did dispatch it and left
    an artifact did [complete it]"*. False. The artifact can predate the dispatch by weeks, and
    every stage stamps `dispatched` for the WHOLE todo list up front (stage2 headless ~L472, stage3
    ~L300, stage4 ~L305) rather than per district as work reaches it. So from t=0 of a redo run,
    any district holding a prior run's artifact satisfied both conjuncts at once and rendered
    `done` — with the PRIOR run's metrics — until its own work happened to finish. Measured on the
    live corpus before the fix: 8 districts read `done` for work that never happened, 7 of them for
    over a month (a Stage-4 redo dispatched 2026-07-22 that never completed), and because
    `retriable == todo + failed == 0` hides the console's Run control, they could not be re-run
    from the console at all. The false `done` also SUPPRESSED THE FIX for itself.

    Why event ORDER, not the completion event's own `batch_id`: completion events are only stamped
    from #647 onward (stage-3 carried it on 28 of 147 rows, stage-4 on 0 of 128), so keying on the
    stamp would declare every historical follow-up batch un-run — 18 of them — and invite a re-run
    of work already paid for. `event_id > the dispatch's` is correct in BOTH eras.

    What counts as an outcome: `stage IS NOT NULL`. `record_stage` sets `stage` for every real
    stage progression and leaves it NULL for exactly `dispatched` and `failed` — verified against
    the live log, where those two are the ONLY stage-NULL event types at these three stages.
    `failed` deliberately does not count: a batch that errored did not finish the district. That
    also retires the certain half of #670 — a late capture timeout that leaves a populated
    captures.json no longer outranks its own failure event (Orange County FL `1201440`, whose only
    stage outcome is `batch_00000`'s benchmark injection three weeks BEFORE `batch_00031` dispatched
    it).

    THE OUTCOME MUST BELONG TO THIS DISPATCH, NOT MERELY FOLLOW IT (#885). "After this batch's
    dispatch" alone is satisfied by a LATER batch's completion, because `event_id` is a global
    serial. That reintroduces #671 one level up — dispatch-ownership checked, completion-ownership
    not — and the trigger is the remediation path itself: re-run one of the 7 stuck districts under
    a new batch and the OLD batch's console page (clickable indefinitely) would flip back to `done`
    and show the NEW batch's metrics. So the outcome must also land BEFORE the next dispatch of the
    same district+stage — the window this dispatch owns, closed by whatever superseded it.

    Why not simply `AND e.batch_id = :b`, as the issue proposed: only 22.4% of `process` outcomes
    and 35.0% of `capture` outcomes carry a batch_id at all (they were stamped from #647 onward),
    so that filter WITHDRAWS 36 GENUINE COMPLETIONS across the redo batches — the precise regression
    the event-order design exists to avoid. Measured both ways before choosing; the window rule
    agrees with the pre-#885 predicate on all 159 live done-districts while still closing the hole.

    Strictly contained in the old predicate: asserted across all 43 batches x 3 stages on the live
    corpus, this set is never a superset of `dispatched_by_batch`'s, so the change can only ever
    withdraw a false `done` — never assert a new one. Rerunnable:
    `docs/technical-notes/production-quality-control-research/2026-08-22-batch-done-predicate-measure.py`."""
    with gdb.session_scope() as con:
        return {r[0] for r in con.execute(
            text("""WITH disp AS (
                      SELECT district_id, MAX(event_id) AS dispatch_id
                        FROM state_event
                       WHERE stage_name = :nm AND event_type = 'dispatched'
                         AND batch_id = :b AND district_id = ANY(:ids)
                       GROUP BY district_id),
                    owned AS (
                      SELECT disp.district_id, disp.dispatch_id,
                             (SELECT MIN(n.event_id) FROM state_event n
                               WHERE n.district_id = disp.district_id
                                 AND n.stage_name = :nm AND n.event_type = 'dispatched'
                                 AND n.event_id > disp.dispatch_id) AS superseded_at
                        FROM disp)
                    SELECT owned.district_id FROM owned
                     WHERE EXISTS (SELECT 1 FROM state_event e
                                    WHERE e.district_id = owned.district_id
                                      AND e.stage_name = :nm
                                      AND e.stage IS NOT NULL
                                      AND e.event_id > owned.dispatch_id
                                      AND (owned.superseded_at IS NULL
                                           OR e.event_id < owned.superseded_at))"""),
            {"nm": stage_name, "b": batch_id, "ids": ids or [""]})}


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
        registry["_events"] = []   # #330: cleared the moment the commit lands, so a caller that
        if export:                 # retries save() after an export failure can NOT double-insert
            # An export failure PROPAGATES (review: server.py's _ingest_stage5_if_complete
            # relies on it to fire its stage5_bookkeeping_failed discriminator). That is safe
            # now precisely because the buffer above is already cleared -- the #330 hazard was
            # the retry-after-propagation double-insert, not the propagation itself. The
            # committed events stay durable either way; a later save()/export() regenerates
            # the JSON backup.
            export_status(s)
    return len(events)


def export() -> int:
    """Regenerate district_status.json from the committed DB log in a fresh session — the explicit
    run-end companion to save(export=False) (issue #49). Returns the # districts exported."""
    ensure_schema()
    with gdb.session_scope() as s:
        return export_status(s)


def export_status(s, out=None) -> int:
    """Regenerate district_status.json from the full state_event log: per district, the snapshot
    (from current_state) + the full ordered history[]. The precious, git-tracked backup (atomic).
    Under pytest the tracked file is quarantine-redirected (issue #178) — tests must never churn it."""
    out = paths.guard_tracked_backup(out or STATUS_FILE)
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
    paths.atomic_write_json(out, doc)
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
