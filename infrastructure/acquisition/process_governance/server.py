#!/usr/bin/env python3
"""Stage 5 review app — local FastAPI server (single-user, localhost only).

Serves the 3-column review UI, the SQLite-backed record/label API, and the captured local
files (text/image/pdf) for inspection. NO AI anywhere — this is the human-labeling harness
around the deterministic signals computed by build_signals.py.

Run:  uvicorn server:app --reload --port 8005   (from this directory)
  or  python3 server.py
"""
import contextlib
import functools
import json
import os
import re
import signal
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

HERE = Path(__file__).resolve().parent
from infrastructure.acquisition.stage5_filter import build_signals as BS    # noqa: E402  (export_labels lives here, shared with ingest)
from infrastructure.acquisition.stage5_filter import release as REL         # noqa: E402  (filtered.json projection — REQ-094)
from infrastructure.acquisition.stage5_filter import detectors as DET       # noqa: E402  (#521 relevance-density event weights — the SSOT)
from infrastructure.acquisition.stage5_filter import drift                  # noqa: E402  (REQ-097 advisory drift verdict — #75)
from infrastructure.acquisition.common import db as gdb                     # noqa: E402  (isolated governance Postgres — REQ-103)
from infrastructure.acquisition.common import district_status as DS         # noqa: E402  (state_event log — gate@1 audit events)
from infrastructure.acquisition.common import calibration as CAL            # noqa: E402  (gate-decision calibration log — REQ-121)
from infrastructure.acquisition.common import gate_mode as GM               # noqa: E402  (per-gate manual/auto store — REQ-108, #104)
from infrastructure.acquisition.common import config_loader as CFGL         # noqa: E402  (#120 mode-stability knob — Settings toggle)
from infrastructure.acquisition.common.timeutil import utcnow               # noqa: E402  (#120 toggle provenance stamp)
from infrastructure.acquisition.stage5_filter import exploration_live as EAL  # noqa: E402  (gate@5 reject-audit demote-hook — REQ-120, #211)
from infrastructure.acquisition.process_governance import gate_calibration as GCAL  # noqa: E402  (console→calibration vocab)
from infrastructure.utilities import school_year as SY                      # noqa: E402  (calendar vocabulary — NOT the LCT DB; see pyproject importlinter note)
from infrastructure.acquisition.common import school_sampling as SS_SAMPLING  # noqa: E402  (latest NCES vintage + criteria text — Settings Exclusions view)
from infrastructure.acquisition.common import school_sampling as SS         # noqa: E402  (add-school candidate lookup)
from infrastructure.acquisition.stage1_queue import queue_batch as Q1       # noqa: E402  (build/persist a batch — REQ-102)
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE   # noqa: E402  (the batch working store)
from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict, BatchSchool  # noqa: E402
from infrastructure.acquisition.stage2_discover import headless as H2       # noqa: E402  (Stage 2 headless runner — REQ-104)
from infrastructure.acquisition.stage3_capture import headless as H3       # noqa: E402  (Stage 3 capture runner + DB-cache status)
from infrastructure.acquisition.stage4_process import headless as H4       # noqa: E402  (Stage 4 process runner + DB-cache status)
from infrastructure.acquisition.process_governance import stage6_dispatch as H6  # noqa: E402  (Stage 6 routing/release bridge — REQ-101)
from infrastructure.acquisition.process_governance import stage6_draft_store as DSTORE6  # noqa: E402  (Stage 6 draft-dispatch working store)
from infrastructure.acquisition.process_governance import stage7_execute as EX  # noqa: E402  (Stage 7 request-more-evidence execution — REQ-118)
from infrastructure.acquisition.process_governance import stage7_run as R7      # noqa: E402  (Stage 7 council extraction runner — #152)
from infrastructure.acquisition.stage6_handoff import handoff as HND6       # noqa: E402  (immutable handoff filename helper)
from infrastructure.acquisition.common import paths                         # noqa: E402  (RAW_CAPTURES — rep inspect)
from infrastructure.acquisition.stage6_handoff import councils as C6        # noqa: E402  (council registry — gate@6 override options)
from infrastructure.acquisition.stage6_handoff.models import Handoff        # noqa: E402  (precious handoff index row)
from infrastructure.acquisition.stage6_handoff.draft_models import DispatchDraft, DispatchDraftDistrict  # noqa: E402  (precious pre-freeze draft dispatch — register for init_precious_schema)
from infrastructure.acquisition.stage7_extract.models import Extraction, SchoolFact, ExtractionRequest, utcnow as _u7  # noqa: E402,F401  (precious Stage-7 results + request loop — register for init_precious_schema)
from infrastructure.acquisition.stage8_aggregate import aggregate as AGG        # noqa: E402  (gate@7 band rollup from school_fact)
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA8  # noqa: E402  (gate@8 closing-argument assembler)
from infrastructure.acquisition.stage8_aggregate import approval as APV8         # noqa: E402  (gate@8 approval record)
from infrastructure.acquisition.stage8_aggregate.models import Stage8Approval    # noqa: E402,F401  (precious gate@8 decision — register for init_precious_schema)
from infrastructure.acquisition.stage8_aggregate.models import BandExclusion     # noqa: E402,F401  (precious gate@8 exclude-from-band #257 — register for init_precious_schema)
from infrastructure.acquisition.stage8_aggregate.models import HumanAddedFact    # noqa: E402,F401  (precious gate@8 human-add #474 — register for init_precious_schema)
from infrastructure.acquisition.stage8_aggregate.models import SlotAssignment    # noqa: E402,F401  (precious gate@8 slot disposition #499 REQ-145 — register for init_precious_schema)


def _refresh_filtered(con, district_id: str) -> None:
    """Event-driven: a label/split change updates this district's filtered.json projection (REQ-094).
    Best-effort — the precious label/split is already committed + JSON-backed, and filtered.json is a
    regenerable projection that also refreshes on the next ingest, so a hiccup here must never fail
    the write."""
    try:
        REL.generate(con, district_id=district_id)
    except Exception as e:
        print(f"[warn] filtered.json refresh for {district_id} failed ({type(e).__name__}: {e}); "
              f"it will regenerate on the next ingest")

# Runtime-state locations come from the single source of truth (paths.py, via build_signals).
# The DB is now the isolated governance Postgres (gdb.session_scope), not a SQLite file.
LABELS_JSON = BS.LABELS_JSON
CLUSTER_SPLITS_JSON = BS.CLUSTER_SPLITS_JSON
RAW_DIR = BS.RAW_DIR


# ---------------------------------------------------------------- run coordination (issue #47)
# (a) Tracked subprocesses: stage runners spawn children (Node Playwright capture, `claude -p`
#     WebSearch) from daemon job threads — on server shutdown the daemon thread dies but the child
#     used to keep running (an orphan Node kept capturing). _tracked_run is a subprocess.run-compatible
#     wrapper that starts each child in its OWN PROCESS GROUP, registers it, and the lifespan shutdown
#     hook SIGTERMs any group still alive.
# (b) Per-batch run lock: discover/capture/process runs on the SAME batch are mutually exclusive
#     (a second run request gets a 409). This is an IN-PROCESS threading.Lock registry — cross-PROCESS
#     locking is out of scope (the console is a single localhost server; a second server instance or a
#     concurrent CLI run is not protected here).
_SUBPROCESSES: set = set()
_SUBPROC_GUARD = threading.Lock()
_BATCH_RUN_LOCKS: dict = {}                 # batch_id -> threading.Lock
_BATCH_RUN_GUARD = threading.Lock()


def _tracked_run(cmd, *, input=None, capture_output=False, text=None, timeout=None, cwd=None):
    """subprocess.run-compatible runner that (1) starts the child in a new session/process group and
    (2) registers it so server shutdown can terminate the whole group (issue #47). Matches the call
    shapes the stage runners use (input/capture_output/text/timeout/cwd)."""
    kw: dict = {"cwd": cwd, "start_new_session": True}
    if capture_output:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if text:
        kw["text"] = True
    if input is not None:
        kw["stdin"] = subprocess.PIPE
    proc = subprocess.Popen(cmd, **kw)
    with _SUBPROC_GUARD:
        _SUBPROCESSES.add(proc)
    try:
        try:
            out, err = proc.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_group(proc)
            proc.wait()
            raise
    finally:
        with _SUBPROC_GUARD:
            _SUBPROCESSES.discard(proc)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def _terminate_group(proc) -> None:
    """SIGTERM a tracked child's whole process group (best-effort; it may already be gone)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _acquire_batch_run(batch_id: str):
    """Take the per-batch run lock (non-blocking) or 409. The job thread MUST release it in finally."""
    with _BATCH_RUN_GUARD:
        lock = _BATCH_RUN_LOCKS.setdefault(batch_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, f"a run is already in progress for this batch ({batch_id}) — "
                                 f"wait for it to finish before starting another stage")
    return lock


@contextlib.asynccontextmanager
async def _lifespan(app):
    """Startup: create the PRECIOUS batch tables if absent (idempotent; best-effort so the app still
    boots when Docker is down — DB calls then fail with the same clear error the Stage-5 path gives).
    Shutdown: terminate any still-running tracked subprocess groups (issue #47) so a dying server
    never orphans a Node capture / claude child. (Migrated from the deprecated @app.on_event.)"""
    try:
        gdb.init_precious_schema()
    except Exception as e:
        print(f"[warn] could not init batch schema at startup ({type(e).__name__}: {e}); "
              f"start Docker (lct_postgres) — queue endpoints will error until then")
    yield
    with _SUBPROC_GUARD:
        live = list(_SUBPROCESSES)
    for proc in live:
        _terminate_group(proc)


app = FastAPI(title="Stage 5 Review", lifespan=_lifespan)


@app.get("/api/tree")
def tree():
    """Districts -> records for the left column. Records carry tier + label status +
    cluster grouping (NOT the category hypothesis — that stays hidden until labeled)."""
    out = []
    with gdb.session_scope() as con:
        districts = con.execute(text("SELECT * FROM district ORDER BY name")).mappings().all()
        q = text("""SELECT r.rec_key, r.url, r.hash, r.kind, r.tier, r.sort_score, r.duplicate_of,
                      r.cluster_id, r.is_cluster_rep, r.cluster_size, r.is_emergent,
                      l.status, l.primary_label
               FROM record r LEFT JOIN label l ON l.rec_key=r.rec_key
               WHERE r.district_id=:did ORDER BY r.tier, r.sort_score DESC""")
        for d in districts:
            recs = [dict(r) for r in con.execute(q, {"did": d["district_id"]}).mappings()]
            t = con.execute(text("SELECT nces_by_level_json FROM district_target WHERE district_id=:did"),
                            {"did": d["district_id"]}).mappings().first()
            out.append({"district_id": d["district_id"], "name": d["name"], "state": d["state"],
                        "batch_id": d["batch_id"], "guessed_topology": d["guessed_topology"],
                        "labeled_topology": d["labeled_topology"], "nces_school_count": d["nces_school_count"],
                        "nces_by_level": json.loads(t["nces_by_level_json"]) if t else None,
                        "records": recs})
    return out


@app.get("/api/record/{rec_key}")
def record(rec_key: str):
    with gdb.session_scope() as con:
        r = con.execute(text("SELECT * FROM record WHERE rec_key=:rk"), {"rk": rec_key}).mappings().first()
        if not r:
            raise HTTPException(404, "no such record")
        reps = [dict(x) for x in con.execute(text(
            "SELECT source, filename, file_kind, n_chars, n_times, usable FROM representation WHERE rec_key=:rk"),
            {"rk": rec_key}).mappings()]
        lab_row = con.execute(text("SELECT * FROM label WHERE rec_key=:rk"), {"rk": rec_key}).mappings().first()
        label = dict(lab_row) if lab_row else {}
        # cluster members (siblings) so the panel can show the cascade + per-member split control
        members = []
        if r["cluster_id"]:
            for m in con.execute(text(
                    """SELECT r.rec_key, r.url, r.is_cluster_rep, l.status FROM record r
                       LEFT JOIN label l ON l.rec_key=r.rec_key
                       WHERE r.cluster_id=:cid ORDER BY r.is_cluster_rep DESC, r.tier, r.sort_score DESC"""),
                    {"cid": r["cluster_id"]}).mappings():
                members.append(dict(m))
        signals = json.loads(r["signals_json"])
        # category_hypothesis is returned but the FRONTEND keeps it hidden until labeled, to avoid
        # anchoring the human's judgment (methodological choice — see the design note).
        return {
            "rec_key": rec_key, "url": r["url"], "hash": r["hash"], "kind": r["kind"],
            "final_url": r["final_url"], "district_dir": r["district_dir"], "tier": r["tier"],
            "category_hypothesis": r["category_hypothesis"], "duplicate_of": r["duplicate_of"],
            "content_hash": r["content_hash"], "signals": signals, "representations": reps,
            "label": label, "cluster_id": r["cluster_id"], "is_cluster_rep": r["is_cluster_rep"],
            "cluster_size": r["cluster_size"], "cluster_members": members,
            "intended_schools": json.loads(r["intended_schools_json"] or "[]"),
            "candidate_tools": json.loads(r["candidate_tools_json"] or "[]"),
            "is_emergent": r["is_emergent"],
        }


# v2.1 label object = primary + facets + note + status (REQ-114). The legacy v2.0 `flags_json`
# column is an inert archive — never written here (a save must not touch it; the v2.1 UI has no
# flags controls, and writing payload.get("flags", []) wiped historical values on every save).
UPSERT_LABEL = text(
    """INSERT INTO label (rec_key, primary_label, facets_json, note, status, updated_at)
       VALUES (:rec_key, :primary_label, :facets_json, :note, :status, :updated_at)
       ON CONFLICT (rec_key) DO UPDATE SET
         primary_label=excluded.primary_label,
         facets_json=excluded.facets_json, note=excluded.note, status=excluded.status,
         updated_at=excluded.updated_at""")

# #228 "Reset labels": return a record to a truthful UNLABELED state. The reset itself is
# BS.reset_labels_bulk — the ONE definition of what a reset means (shared with the remediation
# tooling; PR #242 review killed the second hand-rolled copy). Reset-to-unlabeled, NOT a DELETE —
# ingest models an unlabeled record as a ROW with the DB-default status='unlabeled', and
# export_labels() only dumps status != 'unlabeled', so a reset correctly evicts the record from
# labels.json on the next export. The motivating case: a page that IS a valid schedule but for the
# WRONG district (Millard's unscoped contamination, #227) has no honest v2.1 label — target_absent
# and unusable both assert a false non-target ground truth — so unlabeled is the only truthful
# state, and it was unreachable until now.


# Facet keys that describe the REPRESENTATIVE's own file (the Axis-3 print-dialog handbook page
# range), not the cluster's shared content — cascading them stamped one file's page numbers onto
# every member (issue #64). The representative keeps them; members get the rest.
MEMBER_STRIPPED_FACET_KEYS = ("_pages", "_pages_list")


def cascade_facets(facets: dict | None) -> dict | None:
    """The facets a cluster-cascade save writes to MEMBERS: the shared answers minus the
    representative-specific location keys (issue #64)."""
    if facets is None:
        return None
    return {k: v for k, v in facets.items() if k not in MEMBER_STRIPPED_FACET_KEYS}


@app.post("/api/label/{rec_key}")
async def save_label(rec_key: str, payload: dict):
    with gdb.session_scope() as con:
        rec = con.execute(text(
            """SELECT r.district_id, r.cluster_id, r.is_cluster_rep, r.tier, r.sort_score, d.state,
                      r.signals_json::jsonb->>'content_school_year' AS content_school_year
               FROM record r LEFT JOIN district d ON d.district_id = r.district_id
               WHERE r.rec_key = :rk"""), {"rk": rec_key}).mappings().first()
        if not rec:
            raise HTTPException(404, "no such record")
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # facets (REQ-114): the V2 questionnaire — a dict of detector-mirroring tri-state answers +
        # structured where + harvest_pages_labeled. Stored as JSON; cascades to cluster members like the label.
        vals = {"primary_label": payload.get("primary_label"),
                "facets_json": json.dumps(payload.get("facets")) if payload.get("facets") is not None else None,
                "note": payload.get("note", ""),
                "status": payload.get("status", "labeled"), "updated_at": ts}
        con.execute(UPSERT_LABEL, {"rec_key": rec_key, **vals})
        # Cluster cascade: labeling the REPRESENTATIVE applies the same label to its (unsplit)
        # members, so a near-dup cluster is labeled once. Split members already have cluster_id
        # cleared, so they're naturally excluded. Member facets drop the rep-specific page-range
        # keys (issue #64) — the representative keeps them.
        cascaded = 0
        if rec["cluster_id"] and rec["is_cluster_rep"]:
            mf = cascade_facets(payload.get("facets"))
            member_vals = {**vals, "facets_json": json.dumps(mf) if mf is not None else None}
            for (m,) in con.execute(text("SELECT rec_key FROM record WHERE cluster_id=:cid AND rec_key!=:rk"),
                                    {"cid": rec["cluster_id"], "rk": rec_key}).fetchall():
                con.execute(UPSERT_LABEL, {"rec_key": m, **member_vals})
                cascaded += 1
        BS.recompute_labeled_topology(con, rec["district_id"])
        BS.recompute_attention(con, rec["district_id"])   # label/split changed canonical/resolved state -> refresh attention
        # gate@5 calibration (REQ-121/#210): log the shadow-mode record for this human label — the
        # combiner sort_score proxy vs. the tier-derived auto recommendation — on the SAME transaction.
        # None when there's no terminal decision (unlabeled / off-axis label). The corpus accrues forward.
        cal = GCAL.gate5_label_record(
            rec_key=rec_key, district_id=rec["district_id"], tier=rec["tier"], sort_score=rec["sort_score"],
            primary_label=vals["primary_label"], status=vals["status"], state=rec["state"], created_at=ts,
            content_school_year=rec["content_school_year"])
        if cal:
            CAL.record_calibration(con, cal)
        # gate@5 exploration-audit demote-hook (#211/REQ-120): labeling a reject re-evaluates the revocable
        # autonomy license off the LIVE coverage — self-healing (manual review regenerates exactly the
        # labels that restore coverage). DORMANT until gate@5 is set auto: configured manual → a cheap
        # point-read and an immediate return (the reject-bucket scan is skipped — PR #248 review).
        # SAVEPOINT + swallow (PR #248 review): the hook is advisory to a label save — a transient DB error
        # or a corrupt gate_mode row inside it must never roll back the human's already-applied label
        # (session_scope re-raises anything that escapes, discarding the whole transaction).
        try:
            with con.begin_nested():
                EAL.resolve_gate5_mode(con)
        except Exception as exc:   # noqa: BLE001 — best-effort hook, the label save is the priority
            print(f"[gate5-hook] resolve_gate5_mode failed (label save unaffected): {exc}")
        con.commit()   # persist before exporting, so the JSON backup only reflects committed state
        # Export-on-save: the precious label is backed up to the tracked JSON before we return,
        # so it survives DB loss with zero action from the user (no reliance on remembering).
        BS.export_labels(con, LABELS_JSON)
        _refresh_filtered(con, rec["district_id"])   # label event -> refresh filtered.json
    return {"ok": True, "cascaded": cascaded}


@app.post("/api/reset-labels")
async def reset_labels(payload: dict):
    """#228 gate@5 "Reset labels": return a record (scope='record') or a whole district
    (scope='district') to unlabeled — clearing primary + facets + note back to a neutral,
    truthful state. Mirrors save_label's side-effect set exactly (topology + attention recompute,
    then post-commit labels.json export + filtered.json refresh) so all derived state stays coherent
    and the JSON backup drops the reset rows. Reverses the cluster cascade: resetting a cluster
    REPRESENTATIVE resets every current member (same predicate the forward cascade used; split
    members have cluster_id cleared, so they self-exclude), matching how labeling a rep cascaded in.

    A reset carries no terminal decision, so it logs NO gate@5 calibration record (consistent with
    gate5_label_record returning None for an unlabeled status) — and it does NOT rewrite prior
    calibration history (auditability: past decisions stay on the log)."""
    scope = payload.get("scope")
    target_id = payload.get("target_id")
    if scope not in ("district", "record") or not target_id:
        raise HTTPException(400, "scope must be 'district'|'record' and target_id is required")
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with gdb.session_scope() as con:
        if scope == "district":
            did = target_id
            keys = [r[0] for r in con.execute(
                text("SELECT rec_key FROM record WHERE district_id=:d"), {"d": did}).fetchall()]
            if not keys:
                raise HTTPException(404, f"no records for district {did}")
        else:
            rec = con.execute(text("SELECT district_id, cluster_id, is_cluster_rep "
                                   "FROM record WHERE rec_key=:rk"), {"rk": target_id}).mappings().first()
            if not rec:
                raise HTTPException(404, f"no such record {target_id}")
            did = rec["district_id"]
            if rec["cluster_id"] and rec["is_cluster_rep"]:
                # reverse the cascade: reset the rep + every current member (rep's cluster_id included)
                keys = [r[0] for r in con.execute(
                    text("SELECT rec_key FROM record WHERE cluster_id=:c"), {"c": rec["cluster_id"]}).fetchall()]
            else:
                keys = [target_id]
        # ONE bulk statement (PR #242 review: was a per-key loop + a separate COUNT round-trip);
        # rowcount = the meaningful resets (rows that actually carried a label).
        n_meaningful = BS.reset_labels_bulk(con, keys, ts)
        BS.recompute_labeled_topology(con, did)
        BS.recompute_attention(con, did)
        # Same #211 demote-hook as save_label (PR #248 review): a reset REMOVES audited rejects from the
        # coverage window (`_labeled` excludes 'unlabeled'), so it must re-evaluate the license too — else
        # a stale 'auto' license outlives the coverage that earned it until some unrelated future label
        # save happens to re-fire the hook. Same savepoint isolation: advisory, never fails the reset.
        try:
            with con.begin_nested():
                EAL.resolve_gate5_mode(con)
        except Exception as exc:   # noqa: BLE001
            print(f"[gate5-hook] resolve_gate5_mode failed (reset unaffected): {exc}")
        con.commit()   # persist before exporting, so the JSON backup only reflects committed state
        BS.export_labels(con, LABELS_JSON)   # evicts the now-unlabeled rows from the tracked backup
        _refresh_filtered(con, did)
    return {"ok": True, "district_id": did, "scope": scope, "reset": int(n_meaningful), "records": len(keys)}


@app.post("/api/split/{rec_key}")
async def split_record(rec_key: str):
    """Pull one record OUT of its auto-cluster (it turned out to be genuinely unique). Cheap,
    DB-only: detach the record, re-fix the remaining cluster (new rep / collapse to singleton),
    and record a DURABLE split so re-ingest keeps it out. NOT a re-cluster (no re-shingling)."""
    with gdb.session_scope() as con:
        rec = con.execute(text("SELECT district_id, cluster_id FROM record WHERE rec_key=:rk"),
                          {"rk": rec_key}).mappings().first()
        if not rec:
            raise HTTPException(404, "no such record")
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Precious, durable override first (survives re-ingest + DB wipe via the JSON backup).
        con.execute(text("INSERT INTO cluster_split (rec_key, created_at) VALUES (:rk,:ts) "
                         "ON CONFLICT (rec_key) DO NOTHING"), {"rk": rec_key, "ts": ts})
        cid = rec["cluster_id"]
        if cid:
            # Split-out record + collapse-to-singleton below become SINGLETONS: their duplicate_of
            # (if any) is legitimate content-dedup state and is preserved — a singleton dup is
            # correctly suppressed while its first-seen partner stays canonical (#158 scope note).
            con.execute(text("UPDATE record SET cluster_id=NULL, is_cluster_rep=1, cluster_size=1 WHERE rec_key=:rk"),
                        {"rk": rec_key})
            rest = [row[0] for row in con.execute(text(
                "SELECT rec_key FROM record WHERE cluster_id=:cid ORDER BY tier, sort_score DESC"),
                {"cid": cid}).fetchall()]
            if len(rest) <= 1:   # cluster collapses — remaining record (if any) becomes a singleton
                for rk in rest:
                    con.execute(text("UPDATE record SET cluster_id=NULL, is_cluster_rep=1, cluster_size=1 WHERE rec_key=:rk"),
                                {"rk": rk})
            else:                # promote a new representative; refresh sizes
                for i, rk in enumerate(rest):
                    is_rep = 1 if i == 0 else 0
                    # #158 invariant: a MULTI-MEMBER cluster's rep must NOT carry duplicate_of (the
                    # rep is the cluster's one canonical member) — else CANONICAL_RECORD_WHERE
                    # matches NO member and the whole cluster silently drops from release/dispatch.
                    con.execute(text("UPDATE record SET is_cluster_rep=:rep, cluster_size=:sz"
                                     + (", duplicate_of=NULL" if is_rep else "")
                                     + " WHERE rec_key=:rk"),
                                {"rep": is_rep, "sz": len(rest), "rk": rk})
        BS.recompute_labeled_topology(con, rec["district_id"])
        BS.recompute_attention(con, rec["district_id"])   # label/split changed canonical/resolved state -> refresh attention
        con.commit()   # persist before exporting, so the JSON backup only reflects committed state
        BS.export_splits(con, CLUSTER_SPLITS_JSON)
        _refresh_filtered(con, rec["district_id"])   # split changes the canonical set -> refresh filtered.json
    return {"ok": True}


def _progress_counts(con) -> dict:
    """total = current records; labeled = non-unlabeled labels JOINed to a current record (issue #51):
    the precious `label` table deliberately keeps rows whose record vanished in a shrinking re-ingest,
    so counting the bare table could report labeled > total."""
    total = con.execute(text("SELECT COUNT(*) FROM record")).scalar()
    done = con.execute(text(
        "SELECT COUNT(*) FROM label l JOIN record r ON r.rec_key = l.rec_key "
        "WHERE l.status != 'unlabeled'")).scalar()
    return {"total": total, "labeled": done}


@app.get("/api/progress")
def progress():
    """Label progress + the REQ-097 drift verdict (#75). Drift is ADVISORY — a 'retune recommended'
    badge in the console header, never an auto-retune (CP ramp-up posture). Computed fresh per call
    (a dozen small scorecard reads); failure degrades to no-verdict, never breaks the header."""
    with gdb.session_scope() as con:
        out = _progress_counts(con)
    try:
        out["drift"] = drift.detect()
    except Exception:   # the monitor must never take down the console header
        out["drift"] = {"retune_recommended": False, "note": "drift detector unavailable"}
    return out


# ---------------------------------------------------------------- Stage 5 faceted console (the rework)
# District-driven, attention-first left pane. Group by DISTRICT facets; filter by RECORD facets (the
# district stays visible) + a hide-resolved district toggle; sort by district fields (incl. continuous)
# asc/desc. Server-side on the stored attention/facet columns so it scales to ~5M reps. The batch is
# gone here — "first_seen_at" (the first gate@5 event) replaces it; the district is the canonical unit.
_GROUP_COLS = {"none": None, "pipeline_state": "d.pipeline_state", "state": "d.state",
               "topology": "COALESCE(d.labeled_topology, d.guessed_topology)"}
# "recent" = the latest activity of ANY kind: stage progression OR a label edit (the completion log is
# coarse, so label.updated_at carries the per-URL judgments the user wants reflected). GREATEST ignores NULLs.
_RECENT = "GREATEST(ev.last_event, lbl.last_label)"
_SORT_COLS = {"attention": "d.attention_score", "name": "d.name", "enrollment": "dt.enrollment_k12",
              "schools": "d.nces_school_count", "recent": _RECENT, "first_seen": "ev.first_seen"}


def _like_escape(s: str) -> str:
    """Neutralize LIKE/ILIKE wildcards so a substring search matches them literally. Backslash first (else
    we'd escape our own escapes), then the two metacharacters. Postgres's default LIKE escape is `\\`, so
    no ESCAPE clause is needed — the escaped value goes in as a bind param, immune to string-literal rules."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@app.get("/api/stage5/districts")
def stage5_districts(
    group_by: str = "none", sort: str = "attention", dir: str = "desc",
    label: str | None = None,                          # 'labeled' | 'unlabeled' record filter
    tier: list[str] = Query(default=[]),               # record tier filter (repeatable)
    reason: list[str] = Query(default=[]),             # attention-reason record filter (repeatable)
    lane: str | None = None,                           # 'fp' | 'fn' error-review lane (#516)
    q: str | None = None,                              # rec_key substring search (#516)
    hide_resolved: bool = False,                       # district toggle: drop pipeline_state='complete'
    limit: int = 500, offset: int = 0,
):
    """The faceted district list + each district's (filtered) records. Sort/filter/paginate run in SQL
    on the stored attention/facet columns; grouping is applied over the returned page.

    Error-review lanes (#516) — disagreement between the machine tier and the human label is the tuning
    loop's fuel: `lane='fp'` = the money-leak queue (tier-A the human labeled `target_absent` — machine
    would auto-send, human said absent); `lane='fn'` = the #211 reject-audit sample (tier-D rejects drawn
    for a human to check for false negatives). A lane FOCUSES the list to districts that hold a matching
    record (not "filter URLs, keep districts" — a review queue wants only the districts with work)."""
    gcol = _GROUP_COLS.get(group_by, None)
    scol = _SORT_COLS.get(sort, "d.attention_score")
    order = "ASC" if dir == "asc" else "DESC"
    nulls = "NULLS LAST" if order == "DESC" else "NULLS FIRST"
    where, params = ["1=1"], {"lim": limit, "off": offset}
    if hide_resolved:
        where.append("(d.pipeline_state IS DISTINCT FROM 'complete')")
    with gdb.session_scope() as con:
        # Record-level predicates, built ONCE and shared: the RECORD query filters on them, and — when a
        # lane/search focuses the list — the district-focus subquery uses the SAME set. That agreement is
        # the #516 fix: a focus that ignored an active facet could list (and count in `total_districts`) a
        # district whose only lane-matching record then gets filtered out of its `records` (an empty row).
        rpred, rparams = [], {}          # shared record predicate fragments + their binds
        if label == "labeled":
            rpred.append("l.status IS NOT NULL AND l.status != 'unlabeled'")
        elif label == "unlabeled":
            rpred.append("(l.status IS NULL OR l.status = 'unlabeled')")
        if tier:
            rpred.append("r.tier = ANY(:tiers)"); rparams["tiers"] = tier
        if reason:   # the DOMINANT reason (reasons[0]) is element 0 of the JSON array text
            rpred.append("(r.attention_reasons_json::jsonb ->> 0) = ANY(:reasons)"); rparams["reasons"] = reason
        # #516 lane / rec_key search — a RECORD predicate that ALSO focuses the district list to the
        # districts holding a match (a review queue, not the keep-districts-visible facet behavior).
        focus_rec = None
        if lane == "fp":
            focus_rec = REL.MONEY_LEAK_WHERE           # the tier-A auto-send-but-human-called-absent rule (one home)
        elif lane == "fn":
            # ONE reject-audit draw per request, recomputed live (never cached) BY DESIGN — the sample must
            # reflect the CURRENT tier-D set (a re-tiered reject drops out). Single ix_record_tier-indexed
            # pass over the bounded reject bucket; see exploration_live.audit_sample.
            s = EAL.audit_sample(con)
            rparams["akeys"] = [r["rec_key"] for r in s["audited"]] + [r["rec_key"] for r in s["pending"]] or [""]
            focus_rec = "r.rec_key = ANY(:akeys)"
        if q:   # escape LIKE wildcards so a literal '%'/'_' in the search matches itself, not everything
            rparams["q"] = f"%{_like_escape(q)}%"
            focus_rec = (f"({focus_rec}) AND " if focus_rec else "") + "r.rec_key ILIKE :q"
        if focus_rec:
            rpred.append(focus_rec)
            # Focus the district list to districts holding a record that satisfies the WHOLE record
            # predicate set (facets + focus), so a focused district always has visible work in `records`.
            where.append("d.district_id IN (SELECT r.district_id FROM record r "
                         "LEFT JOIN label l ON l.rec_key=r.rec_key WHERE " + " AND ".join(rpred) + ")")
            params.update(rparams)                     # the subquery's binds ride the district query too
        # 1) districts: stored columns + first/last event from the log, filtered + sorted + paginated.
        #    COUNT(*) OVER() carries the pre-LIMIT total in the SAME pass — one query, not two, so the focus
        #    subquery is planned once (the old separate COUNT re-ran the join a second time; #516).
        drows = con.execute(text(f"""
            SELECT d.district_id, d.name, d.state, d.attention_score, d.attention_reasons_json,
                   d.pipeline_state, d.n_unlabeled, d.n_flagged, d.n_records,
                   d.guessed_topology, d.labeled_topology, d.nces_school_count,
                   dt.enrollment_k12, ev.first_seen, {_RECENT} AS last_event, COUNT(*) OVER() AS total_count
            FROM district d
            LEFT JOIN district_target dt ON dt.district_id = d.district_id
            LEFT JOIN (SELECT district_id, MIN(created_at) FILTER (WHERE stage=5) AS first_seen,
                              MAX(created_at) AS last_event FROM state_event GROUP BY district_id) ev
                   ON ev.district_id = d.district_id
            LEFT JOIN (SELECT r.district_id, MAX(l.updated_at) AS last_label FROM record r
                              JOIN label l ON l.rec_key=r.rec_key WHERE l.status!='unlabeled'
                              GROUP BY r.district_id) lbl ON lbl.district_id = d.district_id
            WHERE {' AND '.join(where)}
            ORDER BY {scol} {order} {nulls}, d.name ASC
            LIMIT :lim OFFSET :off"""), params).mappings().all()
        dids = [r["district_id"] for r in drows]
        total = drows[0]["total_count"] if drows else 0

        # 2) records for the returned page. Record facets filter URLs, not districts (a district stays
        #    visible even if all its records are filtered out) — EXCEPT under a lane/search, where the
        #    district-focus subquery above already guaranteed every listed district holds a full match.
        rwhere = ["r.district_id = ANY(:ids)"] + rpred
        rparams["ids"] = dids or [""]
        recs_by_did: dict = {}
        for r in con.execute(text(f"""
            SELECT r.rec_key, r.district_id, r.url, r.tier, r.attention_score, r.attention_reasons_json,
                   r.is_cluster_rep, r.cluster_id, r.cluster_size, r.is_emergent,
                   COALESCE(l.status,'unlabeled') AS label_status, l.primary_label
            FROM record r LEFT JOIN label l ON l.rec_key=r.rec_key
            WHERE {' AND '.join(rwhere)}
            ORDER BY r.attention_score DESC NULLS LAST, r.tier"""), rparams).mappings():
            recs_by_did.setdefault(r["district_id"], []).append({
                **{k: r[k] for k in ("rec_key", "url", "tier", "attention_score", "is_cluster_rep",
                                     "cluster_id", "cluster_size", "is_emergent", "label_status", "primary_label")},
                "attention_reasons": json.loads(r["attention_reasons_json"]) if r["attention_reasons_json"] else []})

    # 3) assemble districts, then group over the page (order preserved from the SQL sort).
    districts = []
    for r in drows:
        districts.append({
            "district_id": r["district_id"], "name": r["name"], "state": r["state"],
            "attention_score": r["attention_score"] or 0,
            "attention_reasons": json.loads(r["attention_reasons_json"]) if r["attention_reasons_json"] else [],
            "pipeline_state": r["pipeline_state"], "n_unlabeled": r["n_unlabeled"] or 0,
            "n_flagged": r["n_flagged"] or 0, "n_records": r["n_records"] or 0,
            "guessed_topology": r["guessed_topology"], "labeled_topology": r["labeled_topology"],
            "nces_school_count": r["nces_school_count"], "enrollment_k12": r["enrollment_k12"],
            "first_seen_at": r["first_seen"], "last_event_at": r["last_event"],
            "records": recs_by_did.get(r["district_id"], [])})

    def group_key(d):
        if group_by == "state":          return d["state"] or "—"
        if group_by == "pipeline_state": return d["pipeline_state"] or "untouched"
        if group_by == "topology":       return d["labeled_topology"] or d["guessed_topology"] or "unknown"
        return "all"
    groups: list = []
    seen: dict = {}
    for d in districts:
        k = group_key(d)
        if k not in seen:
            seen[k] = {"key": k, "n_districts": 0, "n_attention": 0, "districts": []}
            groups.append(seen[k])
        g = seen[k]
        g["districts"].append(d)
        g["n_districts"] += 1
        g["n_attention"] += 1 if (d["attention_score"] or 0) > 0 else 0
    return {"group_by": group_by, "sort": {"field": sort, "dir": order.lower()},
            "total_districts": total, "shown": len(districts), "groups": groups}


@app.get("/api/stage5/facets")
def stage5_facets():
    """The available group/filter options + their district/record counts — feeds the mini-dashboards
    and the filter menu so the UI never hardcodes the vocabulary."""
    with gdb.session_scope() as con:
        def counts(sql):
            return [{"value": r[0], "count": r[1]} for r in con.execute(text(sql)) if r[0] is not None]
        return {
            "group_by": list(_GROUP_COLS.keys()),
            "sort": list(_SORT_COLS.keys()),
            "pipeline_state": counts("SELECT pipeline_state, COUNT(*) FROM district GROUP BY pipeline_state ORDER BY 2 DESC"),
            "state": counts("SELECT state, COUNT(*) FROM district GROUP BY state ORDER BY 1"),
            "topology": counts("SELECT COALESCE(labeled_topology,guessed_topology), COUNT(*) FROM district GROUP BY 1 ORDER BY 2 DESC"),
            "tier": counts("SELECT tier, COUNT(*) FROM record GROUP BY tier ORDER BY 1"),
            "reason": counts("SELECT attention_reasons_json::jsonb->>0, COUNT(*) FROM record GROUP BY 1 ORDER BY 2 DESC"),
        }


@app.get("/api/detector-weights")
def detector_weights():
    """The relevance-density event weights (#521) — the ONE polarity/confidence source, mirrored from the
    Stage-5 detectors (`detectors.EVENT_WEIGHTS`, pinned to the live Vote confidences by a no-drift test).
    The console's heat-strip + bookmarks sign each positional event with these, so the visual density can
    never contradict the score. Served here so the frontend JS carries NO weights of its own — the
    anti-"second hand-tuned set" discipline #521 requires. Static config; the client fetches it once."""
    return {ev: {"polarity": pol, "weight": w} for ev, (pol, w) in DET.EVENT_WEIGHTS.items()}


def _backup_precious_table(con, select_sql: str, tracked_path) -> int:
    """THE one precious-table→tracked-JSON exporter body (epic-#499 review round: six hand-copied
    twins differing only in SQL + path — a future fix to the atomic-write/quarantine pattern that
    missed one would silently strip #178 protection from that table). Atomic write (tmp+replace);
    under pytest the tracked file is quarantine-redirected via guard_tracked_backup (issue #178)."""
    rows = con.execute(text(select_sql)).mappings().all()
    out = paths.guard_tracked_backup(tracked_path)
    paths.atomic_write_json(out, [dict(r) for r in rows])
    return len(rows)


# ---- follow-up flags (the top attention tier — a directive on a district or a record) ----
def _backup_followups(con) -> int:
    """Back the precious follow-up flags to a tracked JSON (the labels.json pattern), so a human
    directive survives a DB wipe."""
    return _backup_precious_table(
        con, "SELECT scope, target_id, district_id, directive, actor, created_at, resolved_at "
             "FROM followup_flag ORDER BY id", paths.FOLLOWUP_FLAGS_JSON)


def _backup_band_exclusions(con) -> int:
    """Back the precious gate@8 band-exclusions (#257) to a tracked JSON — a standing 'this school
    is not in this band' human judgment must survive a DB wipe and carry a git history."""
    return _backup_precious_table(
        con, "SELECT exclusion_id, district_id, band, norm_school, school, reason, actor, "
             "created_at FROM band_exclusion ORDER BY exclusion_id", paths.BAND_EXCLUSIONS_JSON)


def _backup_human_added(con) -> int:
    """Back the precious gate@8 hand-entered facts (#474) to a tracked JSON — a single-source human
    assertion feeding a published metric must survive a DB wipe and carry a git history."""
    return _backup_precious_table(
        con, "SELECT added_id, district_id, band, norm_school, school, start_time, end_time, "
             "source_url, reason, actor, created_at FROM human_added_fact ORDER BY added_id",
        paths.HUMAN_ADDED_FACTS_JSON)


def _backup_slot_assignments(con) -> int:
    """Back the precious gate@8 slot dispositions (#499 REQ-145) to a tracked JSON — a standing
    'this fact IS/IS NOT that roster slot' human judgment must survive a DB wipe and carry a git
    history."""
    return _backup_precious_table(
        con, "SELECT assignment_id, district_id, band, roster_school_id, norm_school_fact, school, "
             "disposition, reason, actor, created_at FROM slot_assignment ORDER BY assignment_id",
        paths.SLOT_ASSIGNMENTS_JSON)


def _backup_stage8_approvals(con) -> int:
    """Back the precious gate@8 approval decisions to a tracked JSON — a published-LCT authorization
    is an auditable governance decision that must survive a DB wipe and carry a git history.
    Append-only rows."""
    return _backup_precious_table(
        con, "SELECT approval_id, district_id, disposition, actor, reason, facts_fingerprint, "
             "receipt_json, created_at FROM stage8_approval ORDER BY approval_id",
        paths.STAGE8_APPROVALS_JSON)


# ---- discovered domains (#164 — human-confirmed geo-derivation proposals) ----
def _backup_discovered_domains(con) -> int:
    """Back the precious confirmed-discovered-domain rows to a tracked JSON — confirming a
    scoping domain for a blank-NCES district is an auditable governance decision."""
    return _backup_precious_table(
        con, "SELECT district_id, domain, derived_in_batch, tally_json, confirmed_by, confirmed_at "
             "FROM discovered_domain ORDER BY district_id", paths.DISCOVERED_DOMAINS_JSON)


@app.post("/api/discovered-domain")
async def discovered_domain_confirm(payload: dict):
    """#164: confirm a geo run's derived-host PROPOSAL as the district's discovered domain (the
    third, clearly-labeled domain source — NCES data is never modified). The proposal + its full
    host tally live in the deriving run's discovery.json `geo_discovery` block; this records the
    human decision (propose-with-evidence / human-confirms, the CMS_HOSTS discipline)."""
    from infrastructure.acquisition.common import discovered_domain as DDOM
    did = (payload.get("district_id") or "").strip()
    domain = (payload.get("domain") or "").strip()
    actor = payload.get("actor", "ian")
    if not did or not domain:
        raise HTTPException(400, "district_id and domain are required")
    try:
        with gdb.session_scope() as con:
            row = DDOM.confirm(con, did, domain, derived_in_batch=payload.get("derived_in_batch", ""),
                               tally=payload.get("tally"), actor=actor)
            out = {"district_id": row.district_id, "domain": row.domain,
                   "confirmed_by": row.confirmed_by, "confirmed_at": row.confirmed_at}
            _backup_discovered_domains(con)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


# ---- per-gate manual/auto mode (the ramp-up control surface — REQ-108, #104) ----
def _backup_gate_mode(con) -> int:
    """Back the precious per-gate mode rows to a tracked JSON — setting a gate auto is an auditable
    governance decision that must survive a DB wipe and carry a git history."""
    return _backup_precious_table(
        con, "SELECT gate, configured_mode, license_state, updated_at, actor "
             "FROM gate_mode ORDER BY gate", paths.GATE_MODE_JSON)


@functools.lru_cache(maxsize=2)
def _exclusions_snapshot(year):
    """The STANDING pre-queue exclusion corpus, derived live per NCES vintage (#229 UX rework,
    Ian 2026-07-14): the districts every batch draw refuses — no-usable-domain (#229) and
    grade-span-integrity — computed by the SAME eligible_pool + is_scoping_domain path the batch
    build uses (empty registry: the corpus-wide view, ignoring already-attempted). Cached per year
    (full lea/school CSV scans); the per-batch refusal receipts in Batch.meta_json are unchanged —
    this view is where a human READS the standing fact, the receipt is where it's FROZEN."""
    from infrastructure.acquisition.common.discover import domain_of, is_scoping_domain
    # empty registry SHAPE (not {}): already_attempted reads registry["districts"] — the corpus-wide
    # view deliberately ignores what's already been queued
    pool, _idx, gap_excluded = Q1.eligible_pool(year, {"districts": {}})
    no_domain = sorted(
        ({"district_id": did, "name": info["name"], "state": info["state"],
          "website": info["website"]}
         for did, info in pool.items()
         if not is_scoping_domain(domain_of(info["website"]))),
        key=lambda e: (e["state"], e["name"]))
    by_state = {}
    for e in no_domain:
        by_state[e["state"]] = by_state.get(e["state"], 0) + 1
    return {
        "available": True, "nces_year": year,
        "no_domain": {"count": len(no_domain), "by_state": by_state, "districts": no_domain},
        "grade_span_gap": {"count": len(gap_excluded), "districts": gap_excluded},
        "school_criteria": SS_SAMPLING.SCHOOL_CRITERIA_TEXT,
    }


@app.get("/api/exclusions")
def exclusions_view():
    """Settings → Exclusions: the standing pre-queue exclusion rules + the live excluded corpus.
    Degrades honestly when the NCES CSVs aren't on disk ({available: False}) — never a 500."""
    year = SS_SAMPLING.latest_nces_year()
    if not year:
        return {"available": False, "reason": "NCES CCD files not found on disk"}
    try:
        return _exclusions_snapshot(year)
    except FileNotFoundError as e:
        return {"available": False, "reason": str(e)}


@app.get("/api/data-years")
def data_years():
    """The data-year facts for the Settings panel (#254 adjacents): the derived current school year
    (July-1 rollover — never hand-bumped), the NCES primary CCD vintage (hand-bumped on ingest), and
    the acceptable bell-schedule years. Read-only vocabulary from utilities.school_year — surfacing it
    here is what keeps a stale hardcoded year impossible to miss at the console."""
    return {
        "current_school_year": SY.current_school_year(),
        "nces_primary_year": SY.NCES_PRIMARY_YEAR,
        "acceptable_bell_years": list(SY.ACCEPTABLE_BELL_YEARS),
        "covid_excluded_years": sorted(SY.COVID_EXCLUDED_YEARS),
    }


@app.get("/api/gate-mode")
def gate_mode_list():
    """Every gate's resolved mode for the Settings panel: the global 'default' + gate@1..gate@8, with
    defaults filled for unset gates (an empty table reads as every-gate-manual)."""
    with gdb.session_scope() as con:
        return {"gates": list(GM.GATES), "modes": list(GM.MODES), "settings": GM.all_modes(con)}


@app.post("/api/gate-mode")
async def gate_mode_set(payload: dict):
    """Set a gate's (or the global 'default') configured manual/auto mode. Pure ramp-up control — this
    persists the human's toggle; it does NOT itself flip any gate's runtime behavior (each gate stays
    manual until its own auto path is built — #211 for gate@5). Records a state-free audit via the row's
    actor/updated_at + the git-tracked backup. Invalid gate/mode → 400 (never a silent no-op)."""
    gate, mode = payload.get("gate"), payload.get("mode")
    actor = payload.get("actor", "ian")
    if gate not in GM._VALID_KEYS or mode not in GM.MODES:
        raise HTTPException(400, f"gate must be one of {sorted(GM._VALID_KEYS)} and mode one of {GM.MODES}")
    with gdb.session_scope() as con:
        GM.set_configured_mode(con, gate, mode, actor=actor)
        con.commit()
        _backup_gate_mode(con)
    return {"ok": True, "gate": gate, "mode": mode}


@app.get("/api/stage7/mode-stability")
def mode_stability_get():
    """The #120 knob for the Settings panel: the numeric params (read-only in the console — they are
    config-as-data, changed by PR) + the operational `enabled` kill-switch (the one field the toggle
    below may flip)."""
    doc = CFGL.load("stage7_mode_stability")
    return {"params": doc["params"], "governance": doc.get("governance", ""),
            "toggled_by": doc.get("toggled_by"), "toggled_at": doc.get("toggled_at")}


@app.post("/api/stage7/mode-stability")
async def mode_stability_toggle(payload: dict):
    """Flip the #120 early-exit on/off (the operational kill-switch — the gate-mode precedent).
    Writes ONLY `enabled` (+ toggled_by/at provenance) back to the git-tracked knob file — the
    numeric params are never console-writable; the resulting file diff is the audit trail. The next
    Stage-7 run reads the file fresh (no restart needed)."""
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(400, "enabled must be a boolean")
    kp = CFGL.knob_path("stage7_mode_stability")
    doc = json.loads(kp.read_text())
    doc["params"]["enabled"] = enabled
    doc["toggled_by"] = payload.get("actor", "ian")
    doc["toggled_at"] = utcnow()
    kp.write_text(json.dumps(doc, indent=2) + "\n")
    return {"ok": True, "enabled": enabled}


@app.get("/api/exploration-audit")
def exploration_audit_status():
    """gate@5's anti-survivorship reject-audit coverage meter + the pending randomized audit queue (#211,
    REQ-120). Read-only: reflects the live tier-D reject bucket, the sampler draw, and the current gate@5
    mode/license. The demote-hook itself fires on each gate@5 label (self-healing, `save_label`); this
    endpoint resolves the effective mode WITHOUT persisting so a status read never mutates precious state.
    Enforcement is DORMANT — `effective_mode` is 'manual' until a human sets gate@5 auto in Settings."""
    with gdb.session_scope() as con:
        # ONE draw serves everything (PR #248 review: this endpoint used to run the reject-population
        # query + sampler twice — once inside resolve, once for pending — which also let a mid-request
        # commit make the meter and the queue reflect two different population snapshots).
        sample = EAL.audit_sample(con)
        cov = EAL.coverage(con, sample=sample)
        st = EAL.resolve_gate5_mode(con, persist=False, cov=cov)
        st["pending"] = [{"rec_key": r["rec_key"], "district_id": r["district_id"],
                          "url": r["url"], "sort_score": r["sort_score"]} for r in sample["pending"][:200]]
        return st


@app.get("/api/followup")
def followup_list(district_id: str | None = None, include_resolved: bool = False):
    where = ["1=1"]
    params: dict = {}
    if district_id:
        where.append("district_id=:did"); params["did"] = district_id
    if not include_resolved:
        where.append("resolved_at IS NULL")
    with gdb.session_scope() as con:
        rows = con.execute(text(f"SELECT id, scope, target_id, district_id, directive, actor, created_at, "
                                f"resolved_at FROM followup_flag WHERE {' AND '.join(where)} ORDER BY id DESC"),
                           params).mappings().all()
    return [dict(r) for r in rows]


@app.post("/api/followup")
async def followup_create(payload: dict):
    """Flag a district or a record for follow-up with a directive (the top attention tier). Records a
    gate@5 state_event and refreshes the affected district's attention."""
    scope = payload.get("scope")
    target_id = payload.get("target_id")
    if scope not in ("district", "record") or not target_id:
        raise HTTPException(400, "scope must be 'district'|'record' and target_id is required")
    actor = payload.get("actor", "ian")
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with gdb.session_scope() as con:
        did = target_id if scope == "district" else con.execute(
            text("SELECT district_id FROM record WHERE rec_key=:rk"), {"rk": target_id}).scalar()
        if not did:
            raise HTTPException(404, f"no such {scope} {target_id}")
        con.execute(text("""INSERT INTO followup_flag (scope, target_id, district_id, directive, actor, created_at)
                            VALUES (:s,:t,:d,:dir,:a,:ts)"""),
                    {"s": scope, "t": target_id, "d": did, "dir": payload.get("directive", ""), "a": actor, "ts": ts})
        BS.recompute_attention(con, did)
        con.commit()
        _backup_followups(con)
    # No state_event: the governance log is completion-only (§11c). The flag IS its own audit row
    # (followup_flag, timestamped) and feeds the "recent change" sort alongside label.updated_at.
    return {"ok": True, "district_id": did}


@app.post("/api/followup/{flag_id}/resolve")
async def followup_resolve(flag_id: int, payload: dict):
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with gdb.session_scope() as con:
        did = con.execute(text("SELECT district_id FROM followup_flag WHERE id=:i"), {"i": flag_id}).scalar()
        if not did:
            raise HTTPException(404, f"no such flag {flag_id}")
        con.execute(text("UPDATE followup_flag SET resolved_at=:ts WHERE id=:i"), {"ts": ts, "i": flag_id})
        BS.recompute_attention(con, did)
        con.commit()
        _backup_followups(con)
    return {"ok": True, "district_id": did}


# ---- saved views (named left-pane presets; persistent UI convenience) ----
@app.get("/api/views")
def views_list(actor: str = "ian"):
    with gdb.session_scope() as con:
        rows = con.execute(text("SELECT id, name, config_json, created_at FROM saved_view "
                                "WHERE actor=:a ORDER BY name"), {"a": actor}).mappings().all()
    return [{"id": r["id"], "name": r["name"], "config": json.loads(r["config_json"] or "{}"),
             "created_at": r["created_at"]} for r in rows]


@app.post("/api/views")
async def views_save(payload: dict):
    """Create or overwrite (by name+actor) a named left-pane preset."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    actor = payload.get("actor", "ian")
    cfg = json.dumps(payload.get("config", {}))
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with gdb.session_scope() as con:
        existing = con.execute(text("SELECT id FROM saved_view WHERE actor=:a AND name=:n"),
                               {"a": actor, "n": name}).scalar()
        if existing:
            con.execute(text("UPDATE saved_view SET config_json=:c WHERE id=:i"), {"c": cfg, "i": existing})
            vid = existing
        else:
            vid = con.execute(text("INSERT INTO saved_view (actor, name, config_json, created_at) "
                                   "VALUES (:a,:n,:c,:ts) RETURNING id"),
                              {"a": actor, "n": name, "c": cfg, "ts": ts}).scalar()
    return {"ok": True, "id": vid}


@app.delete("/api/views/{view_id}")
async def views_delete(view_id: int):
    with gdb.session_scope() as con:
        con.execute(text("DELETE FROM saved_view WHERE id=:i"), {"i": view_id})
    return {"ok": True}


def _harvest_slice_fallback(district_dir: str, rec_hash: str):
    """A harvest_slice.txt that isn't in the legacy capture dir may live in the NEW derived-artifact
    location (issue #58 moved writes there; wave 1D added the resolver). Look the record up by
    (district_dir, hash) to get the ids resolve_harvest_slice needs. None if unresolvable."""
    try:
        with gdb.session_scope() as con:
            row = con.execute(text(
                "SELECT district_id, rec_key FROM record WHERE district_dir=:dd AND hash=:h"),
                {"dd": district_dir, "h": rec_hash}).first()
    except Exception:
        return None
    if not row:
        return None
    return BS.resolve_harvest_slice(row[0], district_dir, row[1])


@app.get("/files/{district_dir}/{rec_hash}/{filename}")
def serve_file(district_dir: str, rec_hash: str, filename: str):
    """Serve a captured file for inspection. Path-restricted to within a record's capture dir
    (Path.is_relative_to on resolved paths — issue #48; the old startswith idiom let a sibling dir
    with a shared prefix through, and an encoded ../ escape the capture dir)."""
    root = RAW_DIR.resolve()
    base = (root / district_dir / "captures" / rec_hash).resolve()
    target = (base / filename).resolve()
    if not (base.is_relative_to(root) and target.is_relative_to(base)):
        raise HTTPException(404, "not found")
    if not target.is_file():
        # harvest slices moved out of the raw capture dir (issue #58) — resolve new-location-first
        if filename == BS.HARVEST_SLICE_FILE:
            alt = _harvest_slice_fallback(district_dir, rec_hash)
            if alt is not None:
                return FileResponse(alt)
        raise HTTPException(404, "not found")
    return FileResponse(target)


# ---------------------------------------------------------------- gate@1 (Stage 1 Queue) console — REQ-102
# The governance DB is the working store for a batch; batch_NNNNN.json is the receipt regenerated from
# the rows. Edits are SOFT (included flags / row inserts) so the full proposed batch stays auditable.
# Batch-level lifecycle (draft -> approved) lives on the `batch` row; per-district gate@1 events are the
# auditable timeline.

def _record_gate1(district_rows, *, event_type: str, actor: str, note: str = "") -> None:
    """Record a per-district gate@1 event (approved/edited/reopened) — the auditable timeline that
    complements the batch-row lifecycle. `district_rows`: iterable of (district_id, name, state).
    A pure checkpoint event (no `stage`), so it never moves furthest_stage."""
    registry = DS.load()
    for did, name, state in district_rows:
        DS.record_stage(registry, did, name, state, stage_name="queue",
                        checkpoint="gate@1", event_type=event_type, actor=actor, notes=note)
    DS.save(registry)


@app.get("/api/queue")
def queue_list():
    with gdb.session_scope() as con:
        return BSTORE.list_batches(con)


@app.post("/api/queue/create")
async def queue_create(payload: dict):
    """Stratified auto-draw a new batch (synchronous — build_batch reads the full NCES corpus + DB, so
    this blocks ~10-20s; the UI shows a progress affordance). Writes the working store + receipt +
    stage=1 'queued' events, then returns the review payload."""
    year = payload.get("nces_year", "2024_25")
    n = int(payload.get("n", 12))
    batch_type = payload.get("batch_type", "first-run")
    actor = payload.get("actor", "ian")
    # Reserve the id UP FRONT in its own short transaction (issue #46): build_batch takes 10-20s, and
    # computing the number without persisting anything let a second concurrent create draw the SAME
    # number. The committed 'reserving' placeholder makes a duplicate draw fail fast on the PK;
    # create_batch (inside persist_batch) upgrades it to the real draft row.
    # #164: the batch's discovery scope. Geo composition is POLICY-GATED here (the caller-side
    # check the pure build_batch deliberately doesn't do): domain_only refuses; geo_for_blank /
    # geo_interleaved compose from the blank-domain pool; geo_all may compose from any district.
    scope = payload.get("discovery_scope", "domain")
    if scope not in ("domain", "geo"):
        raise HTTPException(400, f"discovery_scope must be 'domain' or 'geo' (got {scope!r})")
    from infrastructure.acquisition.common import discovered_domain as DDOM
    from infrastructure.acquisition.common import discovery_policy as DPOL
    with gdb.session_scope() as con:
        policy = DPOL.get_policy(con)
        discovered = DDOM.all_confirmed(con)
    if scope == "geo" and policy == "domain_only":
        raise HTTPException(409, "discovery_scope_policy is domain_only — geo first-run composition "
                                 "is not enabled (#164)")
    geo_pool = "all" if (scope == "geo" and policy == "geo_all") else "blank"
    with gdb.session_scope() as con:
        batch_id = BSTORE.reserve_next_batch(con, actor=actor)
    try:
        registry = DS.load()
        batch_doc, _gap, _domain_excluded, _n_elig = Q1.build_batch(
            year, n, batch_id, registry, scope=scope, discovered_domains=discovered, geo_pool=geo_pool)
        Q1.persist_batch(batch_doc, registry, batch_type=batch_type, actor=actor)
    except BaseException:
        with gdb.session_scope() as con:   # failed build — free the number (don't leave a dead placeholder)
            BSTORE.release_reservation(con, batch_id)
        raise
    with gdb.session_scope() as con:
        # #229: districts refused for a blank/unusable NCES domain travel IN batch_doc ->
        # Batch.meta_json -> to_view, so the refusals stay visible at gate@1 across reloads and in
        # the receipt — not only in this one create response (PR #242 review).
        return BSTORE.to_view(con, batch_id)


@app.get("/api/queue/{batch_id}")
def queue_get(batch_id: str):
    with gdb.session_scope() as con:
        try:
            return BSTORE.to_view(con, batch_id)
        except KeyError:
            raise HTTPException(404, f"no such batch {batch_id}")


@app.get("/api/queue/{batch_id}/roster/{district_id}")
def queue_roster_spine(batch_id: str, district_id: str):
    """#499 REQ-150: the district's LIVE roster spine for the gate@1 panel — every in-scope NCES
    school per band (slot_recs) with its live slot_state (unfilled = no accepted fact has ever
    matched it; the follow-up pursuit target list). Live compute, nothing persisted — the template
    visible from the start (batch_id is for the URL shape/audit only; the roster is never frozen
    per batch). 404 when CCD files are absent (the honest null — the caller shows 'roster
    unavailable', never a fabricated list)."""
    # THE one projection, not a parallel one (epic-#499 review round): an earlier draft rebuilt
    # project_slots here from a raw accepted-facts query — bypassing the #257 exclusions, #474
    # human adds, REQ-145 dispositions and REQ-146 band-fact projection gate@8 applies — so the
    # two gates silently disagreed about the same district's slot states. load_closing_argument
    # is the single assembled read path; this endpoint only reshapes its slot_projection.
    # record_drift_event=False (review round 2): this GET promises "nothing persisted" — the
    # roster_drift state_event is gate@8's to record, never a side effect of a view.
    with gdb.session_scope() as con:
        ca = CA8.load_closing_argument(con, district_id, record_drift_event=False)
    proj = ca.get("slot_projection") or {}
    if not proj:
        raise HTTPException(404, "live NCES roster unavailable (CCD files not on disk)")
    return {"district_id": district_id,
            "nces_year": (ca.get("provenance") or {}).get("denominator", {}).get("nces_year"),
            "criteria": SS_SAMPLING.SCHOOL_CRITERIA_TEXT,
            "bands": {b: {"slots": [{k: s_.get(k) for k in ("school_id", "roster_school", "gslo",
                                                            "gshi", "is_charter", "slot_state")}
                                    for s_ in p["slots"]],
                          "stats": p["stats"]}
                      for b, p in proj.items()}}


@app.post("/api/queue/{batch_id}/edit")
async def queue_edit(batch_id: str, payload: dict):
    """gate@1 soft edit: reject_district | reject_school | add_school. Mutates the working store,
    regenerates the receipt, and records a per-district gate@1 'edited' audit event."""
    op = payload.get("op")
    actor = payload.get("actor", "ian")
    did = payload.get("district_id")
    try:
        with gdb.session_scope() as con:
            if op == "reject_district":
                BSTORE.reject_district(con, batch_id, did)
                note = f"reject district {did}"
            elif op == "reject_school":
                sid = payload["school_id"]
                BSTORE.reject_school(con, batch_id, did, sid)
                note = f"reject school {sid} ({did})"
            elif op == "restore_district":
                BSTORE.restore_district(con, batch_id, did)
                note = f"restore district {did}"
            elif op == "restore_school":
                sid = payload["school_id"]
                BSTORE.restore_school(con, batch_id, did, sid)
                note = f"restore school {sid} ({did})"
            elif op == "add_school":
                BSTORE.add_school(con, batch_id, did, payload["school"], payload["bands"])
                note = f"add school {payload['school']['school_id']} -> {payload['bands']} ({did})"
            else:
                raise HTTPException(400, f"unknown edit op {op!r}")
            drow = con.get(BatchDistrict, (batch_id, did))
            dname, dstate = (drow.name, drow.state) if drow else (did, "")
            BSTORE.write_receipt(con, batch_id)
    except BSTORE.BatchLocked as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    _record_gate1([(did, dname, dstate)], event_type="edited", actor=actor, note=note)
    with gdb.session_scope() as con:
        return BSTORE.to_view(con, batch_id)


@app.post("/api/queue/{batch_id}/approve")
async def queue_approve(batch_id: str, payload: dict):
    """gate@1 approval — the batch-level transition + a gate@1 'approved' event per included district."""
    actor = payload.get("actor", "ian")
    try:
        with gdb.session_scope() as con:
            BSTORE.approve_batch(con, batch_id, actor)
            included = [(d.district_id, d.name, d.state) for d in con.scalars(
                select(BatchDistrict).where(BatchDistrict.batch_id == batch_id,
                                            BatchDistrict.included.is_(True)))]
    except BSTORE.BatchLocked as e:
        raise HTTPException(409, str(e))
    except KeyError:
        raise HTTPException(404, f"no such batch {batch_id}")
    _record_gate1(included, event_type="approved", actor=actor, note=f"gate@1 approved {batch_id}")
    with gdb.session_scope() as con:
        return BSTORE.to_view(con, batch_id)


@app.post("/api/queue/{batch_id}/reopen")
async def queue_reopen(batch_id: str, payload: dict):
    actor = payload.get("actor", "ian")
    with gdb.session_scope() as con:
        try:
            BSTORE.reopen_batch(con, batch_id, actor)
        except BSTORE.BatchLocked as e:   # #168: an abandoned batch is terminal — reopen refuses it
            raise HTTPException(409, str(e))
        except KeyError:
            raise HTTPException(404, f"no such batch {batch_id}")
        view = BSTORE.to_view(con, batch_id)
    _record_gate1([(d["district_id"], d["name"], d["state"]) for d in view["districts"] if d["included"]],
                  event_type="reopened", actor=actor, note=f"gate@1 reopened {batch_id}")
    return view


@app.post("/api/queue/{batch_id}/abandon")
async def queue_abandon(batch_id: str, payload: dict):
    """gate@1 abandon — retire a NEVER-APPROVED draft batch to a terminal `abandoned` status (#168).
    Records a per-district gate@1 'abandoned' event carrying who/when/why. Never-approved-only (see
    abandon_batch): a once-approved batch's schools are committed as attempted, so it can't be retired —
    the guard is on the durable first_approved_at, so reopen->abandon on a once-approved batch is refused.
    One session, mirroring queue_reopen: abandon only flips status, so the district rows survive for the
    same-session to_view (#198 review)."""
    actor = payload.get("actor", "ian")
    reason = payload.get("reason", "")
    with gdb.session_scope() as con:
        try:
            BSTORE.abandon_batch(con, batch_id, actor, reason)
        except BSTORE.BatchLocked as e:
            raise HTTPException(409, str(e))
        except KeyError:
            raise HTTPException(404, f"no such batch {batch_id}")
        view = BSTORE.to_view(con, batch_id)
    _record_gate1([(d["district_id"], d["name"], d["state"]) for d in view["districts"] if d["included"]],
                  event_type="abandoned", actor=actor,
                  note=f"gate@1 abandoned {batch_id}" + (f": {reason}" if reason else ""))
    return view


@app.get("/api/queue/{batch_id}/district/{district_id}/candidates")
def queue_candidates(batch_id: str, district_id: str):
    """The district's remaining eligible NCES schools (per band) not already selected — the pick-list
    for 'add school'. Reads the full NCES index for the batch's year (heavy; a rare action)."""
    with gdb.session_scope() as con:
        b = con.get(Batch, batch_id)
        if b is None:
            raise HTTPException(404, f"no such batch {batch_id}")
        year = b.nces_year
        selected = {s.school_id for s in con.scalars(select(BatchSchool).where(
            BatchSchool.batch_id == batch_id, BatchSchool.district_id == district_id,
            BatchSchool.included.is_(True)))}
    idx = SS.school_index(year).get(district_id, {})   # {band: [school dicts]}
    out = {b: avail for b, cands in idx.items()
           if (avail := [c for c in cands if c["school_id"] not in selected])}
    return {"batch_id": batch_id, "district_id": district_id, "candidates_by_band": out}


def _batch_from_db(batch_id: str) -> dict | None:
    """Resolve the batch straight from the governance DB working store in the CANONICAL batch_doc
    shape + lifecycle status (batch_store.to_working_doc: INCLUDED districts and INCLUDED schools
    only, one Batch fetch) — the DB is the source of truth for the batch (§7a-A / §11h); the
    on-disk receipt is never the transport (#526). A receipt file WITHOUT a DB row is not a
    supported state (receipts are always derived from the rows in the same transaction), so such
    a batch 404s upstream rather than falling back to disk — a deliberate #526 semantics change
    from the old receipt-loader path. Shared by every stage view (discover, capture, process) and
    autoflow. Previously built on to_view, whose district-level included filter left
    gate@1-EXCLUDED SCHOOLS in schools_by_band — a roster-poisoning trap for Stage 2, which
    builds its roster from schools_by_band. None if no such batch."""
    with gdb.session_scope() as con:
        return BSTORE.to_working_doc(con, batch_id)


# ---------------------------------------------------------------- Stage 2 (Discover) console — REQ-104
# Stage 2 is UNGATED, so the console surfaces it as STATUS/observability + an orchestration trigger
# (headless `claude -p` Wave 1, subscription-billed). The run is a background job; its status is the
# state_event log + the on-disk discovery.json (the filesystem is authoritative), projected here.
# In-process job board (single-user localhost): batch_id -> live run state. Ephemeral by design —
# the DURABLE record is the state_event log + discovery.json; this is just the live progress feed.
_DISCOVER_JOBS: dict = {}


def _job_view(batch_id: str) -> dict | None:
    j = _DISCOVER_JOBS.get(batch_id)
    if not j:
        return None
    return {"state": j["state"], "started_at": j["started_at"], "finished_at": j.get("finished_at"),
            "actor": j["actor"], "events": j["events"][-50:], "summary": j.get("summary"),
            "error": j.get("error")}


@app.get("/api/discover/{batch_id}")
def discover_status(batch_id: str):
    """Read-only Stage 2 status for a batch: lifecycle (must be gate@1-approved to run) + per-district
    discovery outcome, with the batch resolved from the DB working store (#526 — not the on-disk
    receipt), plus the live job feed (if a run is in flight)."""
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    districts = H2.status_for_batch(batch)
    return {"batch_id": batch_id, "batch_status": batch["batch_status"], "districts": districts,
            "rollup": H2.rollup(districts), "job": _job_view(batch_id)}


@app.post("/api/discover/{batch_id}/run")
async def discover_run(batch_id: str, payload: dict):
    """Trigger headless Stage 2 discovery for an approved batch as a BACKGROUND job (12 × `claude -p`
    WebSearch agents at cap-2 concurrency can't block a request). Guards: batch must be gate@1-approved,
    and no run already in flight. Live progress streams into _DISCOVER_JOBS; durable truth is the
    state_event log + discovery.json that run_batch writes."""
    actor = payload.get("actor", "ian")
    # Resolved at schedule time and captured by the _work closure — safe because a non-draft batch
    # is locked against gate@1 edits (batch_store._require_draft), so an approved batch's roster
    # cannot change before or while the background run uses it (the same invariant autoflow's
    # single-resolve comment states).
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    if batch["batch_status"] != "approved":
        raise HTTPException(409, f"batch {batch_id} is '{batch['batch_status']}' — gate@1 approval is "
                                 f"required before discovery")
    existing = _DISCOVER_JOBS.get(batch_id)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"discovery already running for {batch_id}")
    run_lock = _acquire_batch_run(batch_id)   # cross-stage mutual exclusion per batch (issue #47)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _DISCOVER_JOBS[batch_id] = job

    def _on_event(kind, p):
        job["events"].append({"kind": kind, **p})

    # Wave-2 `claude -p` children go through the tracked, process-group runner so a server shutdown
    # terminates them instead of orphaning them (issue #47).
    def _wave2(district, residual, domain):
        return H2._wave2_claude(district, residual, domain, _run=_tracked_run)

    def _work():
        try:
            job["summary"] = H2.run_batch(batch, actor=actor, on_event=_on_event,
                                          wave2_runner=_wave2)
            job["state"] = "done"
        except SystemExit as e:   # reconcile CONTROL FAILURE / billing-auth halt — surface, don't hide
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run_lock.release()

    threading.Thread(target=_work, name=f"discover-{batch_id}", daemon=True).start()
    return {"started": True, "batch_id": batch_id}


# ---------------------------------------------------------------- Stage 3 (Capture) console — REQ-110
# Stage 3 is UNGATED -> status/observability (a health/emergent readout read FROM THE DB cross-stage
# cache, the working store the Stage-3 finish hook keeps fresh) + an orchestration trigger (per-district
# Node Playwright capture, a background job). Durable truth = captures.json on disk + the state_event log.
_CAPTURE_JOBS: dict = {}


def _capture_job_view(batch_id: str) -> dict | None:
    j = _CAPTURE_JOBS.get(batch_id)
    if not j:
        return None
    return {"state": j["state"], "started_at": j["started_at"], "finished_at": j.get("finished_at"),
            "actor": j["actor"], "events": j["events"][-50:], "summary": j.get("summary"),
            "error": j.get("error")}


@app.get("/api/capture/{batch_id}")
def capture_status(batch_id: str):
    """Read-only Stage 3 status for a batch: per-district capture outcome + the CMS/host distribution,
    read from the DB cross-stage cache, plus the live job feed (if a run is in flight)."""
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    st = H3.status_for_batch(batch)
    return {"batch_id": batch_id, "batch_status": batch["batch_status"], **st,
            "job": _capture_job_view(batch_id)}


@app.post("/api/capture/{batch_id}/run")
async def capture_run(batch_id: str, payload: dict):
    """Trigger Stage 3 capture for a discovered batch as a BACKGROUND job (per-district Node Playwright
    subprocesses can't block a request). Guard: no run already in flight. Live progress streams into
    _CAPTURE_JOBS; durable truth is captures.json + the state_event log + the DB cache that run_batch
    writes."""
    actor = payload.get("actor", "ian")
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    existing = _CAPTURE_JOBS.get(batch_id)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"capture already running for {batch_id}")
    run_lock = _acquire_batch_run(batch_id)   # cross-stage mutual exclusion per batch (issue #47)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _CAPTURE_JOBS[batch_id] = job

    def _on_event(kind, p):
        job["events"].append({"kind": kind, **p})

    def _work():
        try:
            # Node children run through the tracked, process-group runner so a server shutdown
            # terminates them instead of orphaning a capture (issue #47).
            job["summary"] = H3.run_batch(batch, actor=actor, on_event=_on_event, _run=_tracked_run)
            job["state"] = "done"
        except SystemExit as e:   # reconcile CONTROL FAILURE — surface, don't hide
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run_lock.release()

    threading.Thread(target=_work, name=f"capture-{batch_id}", daemon=True).start()
    return {"started": True, "batch_id": batch_id}


@app.post("/api/capture/{batch_id}/retry")
async def capture_retry(batch_id: str, payload: dict):
    """#116: re-attempt the batch's RETRYABLE capture failures (not_attempted/not_recovered) as a
    background job — same job/lock machinery as /run; one-attempt errs (security_block,
    needs_oauth_reauth) are never re-hit (headless.retry_partial)."""
    actor = payload.get("actor", "ian")
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    existing = _CAPTURE_JOBS.get(batch_id)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"capture already running for {batch_id}")
    run_lock = _acquire_batch_run(batch_id)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _CAPTURE_JOBS[batch_id] = job

    def _on_event(kind, p):
        job["events"].append({"kind": kind, **p})

    def _work():
        try:
            job["summary"] = H3.retry_partial(batch, actor=actor, on_event=_on_event, _run=_tracked_run)
            job["state"] = "done"
        except SystemExit as e:
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run_lock.release()

    threading.Thread(target=_work, name=f"capture-retry-{batch_id}", daemon=True).start()
    return {"started": True, "batch_id": batch_id, "mode": "retry"}


# ---------------------------------------------------------------- Stage 4 (Process) console — REQ-111
# Stage 4 is UNGATED -> status/observability (a processing-health + tool-effectiveness readout read FROM
# THE DB cross-stage cache, the working store the Stage-4 finish hook keeps fresh) + an orchestration
# trigger (the local harvesters, run IN-PROCESS as a background job). Unlike Stage 2/3 the work is plain
# Python, not a subprocess. Durable truth = processed.json on disk + the state_event log.
_PROCESS_JOBS: dict = {}


def _process_job_view(batch_id: str) -> dict | None:
    j = _PROCESS_JOBS.get(batch_id)
    if not j:
        return None
    return {"state": j["state"], "started_at": j["started_at"], "finished_at": j.get("finished_at"),
            "actor": j["actor"], "events": j["events"][-50:], "summary": j.get("summary"),
            "error": j.get("error")}


@app.get("/api/process/{batch_id}")
def process_status(batch_id: str):
    """Read-only Stage 4 status for a batch: per-district process outcome + usable-doc counts + the
    usable-representations-by-tool distribution, read from the DB cross-stage cache, plus the live job
    feed (if a run is in flight)."""
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    st = H4.status_for_batch(batch)
    return {"batch_id": batch_id, "batch_status": batch["batch_status"], **st,
            "job": _process_job_view(batch_id)}


@app.post("/api/process/{batch_id}/run")
async def process_run(batch_id: str, payload: dict):
    """Trigger Stage 4 processing for a captured batch as a BACKGROUND job (the per-district local
    harvesters run sequentially and can't block a request). Guard: no run already in flight. Live
    progress streams into _PROCESS_JOBS; durable truth is processed.json + the state_event log + the DB
    cache that run_batch writes."""
    actor = payload.get("actor", "ian")
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    existing = _PROCESS_JOBS.get(batch_id)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"processing already running for {batch_id}")
    run_lock = _acquire_batch_run(batch_id)   # cross-stage mutual exclusion per batch (issue #47)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _PROCESS_JOBS[batch_id] = job

    def _on_event(kind, p):
        job["events"].append({"kind": kind, **p})

    def _work():
        try:
            summary = run_stage4_with_ingest(batch, actor=actor, on_event=_on_event)
            job["summary"] = summary
            job["state"] = "done"
        except SystemExit as e:   # reconcile / file-existence CONTROL FAILURE — surface, don't hide
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run_lock.release()

    threading.Thread(target=_work, name=f"process-{batch_id}", daemon=True).start()
    return {"started": True, "batch_id": batch_id}


def run_stage4_with_ingest(batch: dict, *, actor: str, on_event) -> dict:
    """Stage 4 AND its Stage-5 hand-off, as ONE operation — the invariant 'Stage 4 complete implies
    the Stage-5 ingest was attempted' lives HERE, not in each caller's memory (#240 review: #235
    happened precisely because autoflow was a second run_batch call site that forgot the ingest the
    first one remembered). Any future entry point calls THIS, never H4.run_batch directly. The
    ingest is idempotent (per-district delete+rebuild) and self-guards on batch completeness, so no
    todo-gating is needed at call sites. Returns Stage 4's summary."""
    summary = H4.run_batch(batch, actor=actor, on_event=on_event)
    _ingest_stage5_if_complete(batch, on_event)
    return summary


def _ingest_stage5_if_complete(batch: dict, on_event) -> None:
    """The Stage-4 -> Stage-5 handoff. If every district in `batch` is now resolved (processed or
    terminally no-link), run the INCREMENTAL Stage-5 ingest for just this batch (BS.ingest_batch —
    leaves prior batches untouched) and record a Stage-5 progression event per ingested district
    (furthest_stage -> 5), so the batch is durably "done through Stage 4 / in Stage 5". Best-effort:
    Stage 4's processed.json is already the durable record, so an ingest hiccup is surfaced as an
    event (and re-runnable via build_signals) but never fails the successful Stage-4 job."""
    rollup = H4.status_for_batch(batch)["rollup"]
    if rollup["resolved"] < rollup["total"]:
        # Not fully processed (failures awaiting retry) — defer the ingest to a later run. NOT silent
        # (#235 review): the autoflow chain has no later run, so the caller must be able to see that
        # the batch landed at gate@5 WITHOUT its ingest, or the deferral reads as 'nothing new'.
        on_event("stage5_ingest_deferred",
                 {"batch_id": batch["batch_id"], "resolved": rollup["resolved"],
                  "total": rollup["total"],
                  "hint": "re-run Stage 4 for the unresolved district(s), then re-trigger the ingest"})
        return
    # The INGEST gets its own try (#240 review): the DB writes are atomic inside ingest_batch, and
    # only a failure of the ingest ITSELF may be recorded as ingest_failed. A throw in the
    # bookkeeping below (registry write) must never mislabel genuinely-committed Stage-5 data.
    try:
        ids = [d["district_id"] for d in batch["districts"]]
        summary = BS.ingest_batch(ids)
    except Exception as e:
        on_event("stage5_ingest_failed", {"batch_id": batch["batch_id"], "error": str(e)[:200]})
        # #235: the failure must survive the process — the in-memory job event and stdout both vanish,
        # leaving district_status.json showing a clean stage-4 finish followed by silence,
        # indistinguishable from "nothing new surfaced". Record it durably per district.
        try:
            registry = DS.load()
            for d in batch["districts"]:
                DS.record_stage(registry, d["district_id"], d.get("name", ""), d.get("state", ""),
                                stage=5, stage_name="filter", outcome="ingest_failed",
                                actor="auto:stage5", batch_id=batch["batch_id"])
            DS.save(registry)
        except Exception as e2:
            print(f"[warn] could not durably record the ingest failure either: {e2}")
        print(f"[warn] Stage 5 ingest for {batch['batch_id']} failed ({type(e).__name__}: {e}); "
              f"re-run `python3 -m infrastructure.acquisition.stage5_filter.build_signals` manually")
        return
    try:
        registry = DS.load()
        for did in summary["districts"]:
            d = next((x for x in batch["districts"] if x["district_id"] == did), {})
            DS.record_stage(registry, did, d.get("name", ""), d.get("state", ""), stage=5,
                            stage_name="filter", outcome="ingested", actor="auto:stage5",
                            batch_id=batch["batch_id"])
        DS.save(registry)
        on_event("stage5_ingested", {"batch_id": batch["batch_id"], "n_districts": summary["n_districts"],
                                     "n_records": summary["n_records"], "n_send": summary["n_send"]})
    except Exception as e:
        # The ingest SUCCEEDED — only the progression bookkeeping failed. Say exactly that.
        on_event("stage5_bookkeeping_failed", {"batch_id": batch["batch_id"], "error": str(e)[:200]})
        print(f"[warn] Stage 5 ingest for {batch['batch_id']} SUCCEEDED but recording the progression "
              f"failed ({type(e).__name__}: {e}); the signal tables are correct, re-save the registry")


# ----------------------------- Stage 6 — Dispatch routing/release (gate@6, REQ-101) -----------------------------
# Build a handoff package from the Stage-5 release decision, review routed councils + estimated cost,
# then APPROVE & FREEZE (gate@6) — writes the immutable handoff_<hash>.json + records the dispatch.
# Stops at the seam: NO paid Stage-7 calls here.


@app.get("/api/handoff/candidates")
def handoff_candidates():
    """Stage-5 districts available to dispatch, each with `n_send` (canonical records `release.decide`
    will SEND — labeled targets + unlabeled tier-A, MINUS the #241 pre-2017-18 validity-floor holds),
    `n_verified` (the human-labeled-target subset of n_send — what a `verified_only` dispatch sends), and
    `n_hold` (unlabeled tier-B/C awaiting a gate@5 label, PLUS the floor-held tier-A records). Mirrors
    decide()'s tier gate + #241 floor (the `:floor` bind is release.SPED_BASELINE_YEAR — the single source
    of truth), so the badge reflects what dispatch actually sends, not the whole recall-biased funnel. It is
    a per-record UPPER BOUND: #107 prefer-recent may HOLD a further stale same-school sibling at dispatch
    time (a cross-record decision this per-record count can't show). Reuses release.CANONICAL_RECORD_WHERE.
    Preview stays authoritative for the exact representation count + cost.

    Also carries a per-district DISPATCH-HISTORY signal (#171) so the console can distinguish fresh
    from already-sent districts (re-selecting a dispatched one is wasted spend): `n_dispatched` /
    `last_dispatched_at` from the gate@6 `dispatched` state_events; `n_extracted` = PRODUCTION
    extractions that ACCEPTED >=1 fact (n_accepted>0 — an all-errors run persists a row but has no
    facts, so bare row-existence would falsely read as 'has data'; #198 review); and `is_benchmark`
    computed server-side by the SAME rule as the dispatch wall (`batch_type='benchmark'` membership,
    not the batch_00000 id literal — the GT corpus grows into new benchmark batches; #198 review)."""
    # Target labels are a BOUND list parameter computed per request (issue #62): the old module-level
    # _TARGET_IN froze the vocabulary at import time AND string-interpolated it into the SQL.
    targets = sorted(BS.TARGET_LABELS)
    with gdb.session_scope() as con:
        rows = con.execute(text(
            f"""SELECT d.district_id, d.name, d.state, d.labeled_topology, d.batch_id,
                       COALESCE(t.n_send, 0) AS n_send, COALESCE(t.n_verified, 0) AS n_verified,
                       COALESCE(t.n_hold, 0) AS n_hold,
                       COALESCE(disp.n_dispatched, 0) AS n_dispatched, disp.last_dispatched_at,
                       COALESCE(ext.n_extracted, 0) AS n_extracted,
                       {IS_BENCHMARK_SQL.format(alias='d')} AS is_benchmark
                FROM district d
                LEFT JOIN (
                    SELECT r.district_id,
                      COUNT(*) FILTER (WHERE l.primary_label = ANY(:targets)
                                          OR (l.primary_label IS NULL AND r.tier = 'A'
                                              AND NOT (COALESCE(r.signals_json::jsonb->>'content_school_year',
                                                                '9999-99') < :floor))) AS n_send,
                      COUNT(*) FILTER (WHERE l.primary_label = ANY(:targets)) AS n_verified,
                      COUNT(*) FILTER (WHERE l.primary_label IS NULL
                                          AND (r.tier IN ('B', 'C')
                                               OR (r.tier = 'A'
                                                   AND COALESCE(r.signals_json::jsonb->>'content_school_year',
                                                                '9999-99') < :floor))) AS n_hold
                    FROM record r LEFT JOIN label l ON l.rec_key = r.rec_key
                    WHERE {REL.CANONICAL_RECORD_WHERE}
                    GROUP BY r.district_id
                ) t ON t.district_id = d.district_id
                LEFT JOIN (
                    SELECT district_id, COUNT(*) AS n_dispatched, MAX(created_at) AS last_dispatched_at
                    FROM state_event
                    WHERE checkpoint = 'gate@6' AND event_type = 'dispatched'
                    GROUP BY district_id
                ) disp ON disp.district_id = d.district_id
                LEFT JOIN (
                    SELECT district_id, COUNT(*) AS n_extracted
                    FROM extraction WHERE run_kind = 'production' AND n_accepted > 0
                    GROUP BY district_id
                ) ext ON ext.district_id = d.district_id
                ORDER BY n_send DESC, n_hold DESC, d.district_id"""),
            {"targets": targets, "floor": SY.SPED_BASELINE_YEAR}).mappings().all()
        return [dict(r) for r in rows]


@app.post("/api/handoff/preview")
async def handoff_preview(payload: dict):
    """Build the in-memory handoff package for the selected districts (routed + priced) — no persist.
    `overrides` = gate@6 per-rep council overrides ({"<rec_key>::<file>": council_id})."""
    ids = payload.get("district_ids") or []
    overrides = payload.get("overrides") or {}
    verified_only = bool(payload.get("verified_only"))
    with gdb.session_scope() as con:
        pkg = H6.build_handoff_package(con, ids, overrides=overrides, verified_only=verified_only)
    # The staleness token (issue #37): dispatch rebuilds the package from the live DB, so what the
    # human approved on screen can drift (a label edit, a re-ingest) between preview and freeze. The
    # console echoes this back as `expected_identity`; dispatch 409s on mismatch.
    pkg["preview_identity"] = HND6.package_identity(pkg)
    return pkg


@app.post("/api/handoff/dispatch")
async def handoff_dispatch(payload: dict):
    """gate@6 approve: freeze the immutable handoff + record the dispatch (the index row + per-district
    `dispatched` state_events). Stops at the seam — no paid OpenRouter calls (that's Stage 7)."""
    ids = payload.get("district_ids") or []
    actor = payload.get("actor", "ian")
    overrides = payload.get("overrides") or {}
    verified_only = bool(payload.get("verified_only"))
    expected_identity = payload.get("expected_identity")   # optional (issue #37) — the console always
    if not ids:                                            # sends it; a bare CLI/test POST still works
        raise HTTPException(400, "no districts selected")
    try:
        with gdb.session_scope() as con:
            if expected_identity:
                # Preview→freeze staleness gate (issue #37): rebuild the package the same way the
                # preview did and compare identities BEFORE freezing anything.
                pkg = H6.build_handoff_package(con, ids, overrides=overrides,
                                               verified_only=verified_only)
                if HND6.package_identity(pkg) != expected_identity:
                    raise HTTPException(409, "release changed since preview — the package that would "
                                             "be frozen no longer matches what was reviewed; re-preview "
                                             "before dispatching")
            doc, path = H6.dispatch_handoff(con, ids, created_by=actor, overrides=overrides,
                                            verified_only=verified_only)
    except FileExistsError:
        raise HTTPException(409, "an identical handoff was just dispatched (same content within the "
                                 "same second) — the prior one stands; retry in a moment if intended")
    cost = doc.get("cost") or {}
    return {"handoff_id": HND6.handoff_filename(doc)[:-5], "handoff_hash": doc["handoff_hash"],
            "verified_only": bool(doc.get("verified_only")),
            "n_districts": len(doc.get("districts", [])), "n_reps": cost.get("n_reps", 0),
            "total_usd": cost.get("total_usd", 0.0), "provenance": cost.get("provenance", "unknown"),
            "path": str(path)}


@app.get("/api/handoffs")
def handoff_list():
    """The dispatched handoffs index (newest first). `n_extracted` = districts already extracted for
    this handoff (so the UI can show run/re-run/done); `running` = a live extraction job (#152)."""
    with gdb.session_scope() as con:
        rows = con.execute(text(
            "SELECT handoff_hash, handoff_id, created_at, created_by, status, n_districts, n_reps, "
            "total_usd, cost_provenance FROM handoff ORDER BY created_at DESC")).mappings().all()
        out = []
        for r in rows:
            d = dict(r)
            d["n_extracted"] = con.execute(text(
                "SELECT COUNT(*) FROM extraction WHERE handoff_hash = :h"), {"h": r["handoff_hash"]}).scalar()
            job = _EXTRACT_JOBS.get(r["handoff_hash"])
            d["running"] = bool(job and job["state"] == "running")
            out.append(d)
        return out


@app.get("/api/handoffs/{handoff_id}")
def handoff_detail(handoff_id: str):
    """A frozen dispatch's FULL district/rep package by id — today's `/api/handoffs` only returns
    list-level summary fields (the full package only ever existed transiently in `preview()`'s
    response). Reads the `handoff` row for lifecycle/cost fields + the frozen JSON file off disk for
    the package, + the DERIVED `origin` ('draft' | 'stage7' | 'console'), computed live from receipts by
    `DSTORE6.classify_origin` — never stored (see `stage6_draft_store._origin_case` for the rule)."""
    with gdb.session_scope() as con:
        row = con.execute(text(
            "SELECT handoff_id, handoff_hash, created_at, created_by, status, path, n_districts, "
            "n_reps, total_usd, cost_provenance FROM handoff WHERE handoff_id = :h"),
            {"h": handoff_id}).mappings().first()
        if not row:
            raise HTTPException(404, f"no such handoff {handoff_id}")
        origin = DSTORE6.classify_origin(con, row["handoff_hash"])
        n_extracted = con.execute(text(
            "SELECT COUNT(*) FROM extraction WHERE handoff_hash = :h"), {"h": row["handoff_hash"]}).scalar()
        job = _EXTRACT_JOBS.get(row["handoff_hash"])
    try:
        doc = R7.load_handoff(row["path"])
    except (OSError, ValueError) as e:
        raise HTTPException(404, f"handoff file unreadable: {e}")
    return {**dict(row), "origin": origin, "n_extracted": n_extracted,
           "running": bool(job and job["state"] == "running"), "package": doc}


# ---------------------------------------------------------------- gate@6 draft dispatch (pre-freeze)
# The mutable, reopenable container a human builds up before freezing — mirrors gate@1's Batch pattern.
# Districts + per-rep council overrides are the only persisted state; representations are re-derived
# live from the Stage-5 release decision on every read (never shadowed/duplicated here).

def _record_gate6_draft(district_rows, *, event_type: str, actor: str, note: str = "") -> None:
    """Record per-district gate@6 draft-edit events — the auditable timeline alongside the draft row's
    own lifecycle. `district_rows`: iterable of (district_id, name, state), mirroring `_record_gate1`:
    the registry is district-KEYED, so a draft-scoped op (set_verified_only) records against the draft's
    included districts — never against the draft id itself, which `record_stage`'s unconditional
    setdefault would insert as a fake "district" row into the precious status registry. A pure
    checkpoint event (no `stage`), so it never moves furthest_stage. Granular event_type
    (draft_add_district / draft_set_override / ...) rather than one coarse 'draft_edited', so a later
    'why did this draft's package look different than expected' has a real trail."""
    rows = list(district_rows)
    if not rows:
        return
    registry = DS.load()
    for did, name, state in rows:
        DS.record_stage(registry, did, name, state, stage_name="dispatch",
                        checkpoint="gate@6", event_type=event_type, actor=actor, notes=note)
    DS.save(registry)


@app.get("/api/dispatch")
def dispatch_list():
    """Combined left-pane rows: drafts (in-progress, actionable) + dispatched handoffs (read-only
    history), the latter tagged with an origin flag. Drafts sort first (most-recently-created first,
    surfacing in-progress work); handoffs sort newest-first."""
    with gdb.session_scope() as con:
        return DSTORE6.list_dispatch_rows(con)


@app.post("/api/dispatch/create")
async def dispatch_create(payload: dict):
    """Create an empty draft (instant — no upfront district-selection prompt; districts are added
    inside the draft detail view)."""
    actor = (payload or {}).get("actor", "ian")
    with gdb.session_scope() as con:
        draft_id = DSTORE6.create_draft(con, actor=actor)
        return DSTORE6.to_view(con, draft_id)


@app.get("/api/dispatch/{draft_id}")
def dispatch_get(draft_id: str):
    with gdb.session_scope() as con:
        try:
            return DSTORE6.to_view(con, draft_id)
        except KeyError:
            raise HTTPException(404, f"no such draft {draft_id}")


@app.get("/api/dispatch/{draft_id}/candidates")
def dispatch_candidates(draft_id: str):
    """Eligible-to-add districts for this draft — reuses handoff_candidates()'s query, filtered to
    exclude districts already `included=True` in the draft."""
    with gdb.session_scope() as con:
        d = con.get(DispatchDraft, draft_id)
        if d is None:
            raise HTTPException(404, f"no such draft {draft_id}")
        already = {r.district_id for r in con.scalars(select(DispatchDraftDistrict).where(
            DispatchDraftDistrict.draft_id == draft_id, DispatchDraftDistrict.included.is_(True)))}
    all_candidates = handoff_candidates()
    return [c for c in all_candidates if c["district_id"] not in already]


@app.post("/api/dispatch/{draft_id}/edit")
async def dispatch_edit(draft_id: str, payload: dict):
    """gate@6 draft edit: add_district | remove_district | restore_district | set_override |
    clear_override | set_verified_only. One delegated mutation endpoint, mirrors gate@1's
    `/api/queue/{batch_id}/edit`. Mutates the working store and records a gate@6 draft-edit audit
    event (district-scoped for district/override ops, draft-scoped for set_verified_only); returns
    the fresh draft-detail view (always-current pricing)."""
    op = payload.get("op")
    actor = payload.get("actor", "ian")
    did = payload.get("district_id")
    district_scoped_ops = {"add_district", "remove_district", "restore_district",
                          "set_override", "clear_override"}
    # Validate the payload SHAPE up front, so a malformed request is a clean 400 — not an unhandled
    # IntegrityError 500 (a None district_id reaching the NOT-NULL PK insert) and not a KeyError
    # miscaught below as a 404 (that handler means "unknown district/draft", a different failure).
    if op in district_scoped_ops and not did:
        raise HTTPException(400, f"{op} requires a district_id")
    if op in ("set_override", "clear_override"):
        required = ("rec_key", "file") + (("council_id",) if op == "set_override" else ())
        missing = [k for k in required if not payload.get(k)]
        if missing:
            raise HTTPException(400, f"{op} requires {', '.join(missing)}")
    affected = []          # [(district_id, name, state)] the audit events record against
    try:
        with gdb.session_scope() as con:
            if op == "add_district":
                DSTORE6.add_district(con, draft_id, did)
                note = f"add district {did}"
            elif op == "remove_district":
                DSTORE6.remove_district(con, draft_id, did)
                note = f"remove district {did}"
            elif op == "restore_district":
                DSTORE6.restore_district(con, draft_id, did)
                note = f"restore district {did}"
            elif op == "set_override":
                DSTORE6.set_override(con, draft_id, did, payload["rec_key"], payload["file"],
                                     payload["council_id"])
                note = f"override {payload['rec_key']}::{payload['file']} -> {payload['council_id']}"
            elif op == "clear_override":
                DSTORE6.clear_override(con, draft_id, did, payload["rec_key"], payload["file"])
                note = f"clear override {payload['rec_key']}::{payload['file']}"
            elif op == "set_verified_only":
                DSTORE6.set_verified_only(con, draft_id, bool(payload.get("verified_only")))
                note = f"set verified_only={bool(payload.get('verified_only'))}"
            else:
                raise HTTPException(400, f"unknown edit op {op!r}")
            if op in district_scoped_ops:
                # the district's REAL name/state, never the bare id — district_status.record_stage
                # unconditionally overwrites `name` (no blank-guard), so passing `did` twice would
                # silently clobber a district's real name in the shared, precious status registry.
                drow = con.execute(text("SELECT name, state FROM district WHERE district_id = :d"),
                                   {"d": did}).mappings().first()
                if drow:
                    affected = [(did, drow["name"] or did, drow["state"] or "")]
                else:
                    # Unknown to the signals store: don't fail the edit, but leave a VISIBLE marker
                    # in the audit note instead of silently recording the bare id as a name.
                    affected = [(did, did, "")]
                    note += " [district not found in signals store]"
            elif op == "set_verified_only":
                # Draft-scoped op: record against the draft's included districts (the rows whose
                # send-set the mode flip actually changes) — mirrors gate@1's batch-level abandon,
                # which also fans out to per-district events. Empty draft -> nothing to record.
                affected = [tuple(r) for r in con.execute(text(
                    "SELECT dd.district_id, COALESCE(d.name, dd.district_id), COALESCE(d.state, '') "
                    "FROM dispatch_draft_district dd "
                    "LEFT JOIN district d ON d.district_id = dd.district_id "
                    "WHERE dd.draft_id = :dr AND dd.included ORDER BY dd.ord"), {"dr": draft_id})]
        _record_gate6_draft(affected, event_type=f"draft_{op}", actor=actor, note=note)
    except DSTORE6.DraftLocked as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    with gdb.session_scope() as con:
        return DSTORE6.to_view(con, draft_id)


@app.post("/api/dispatch/{draft_id}/freeze")
async def dispatch_freeze(draft_id: str, payload: dict):
    """gate@6 approve: freeze a draft into the immutable handoff, via the UNCHANGED
    `stage6_dispatch.dispatch_handoff` (this endpoint only supplies a persisted draft_id as the
    trigger). The draft's lifecycle fields are set in the SAME transaction as the freeze."""
    actor = (payload or {}).get("actor", "ian")
    expected_identity = (payload or {}).get("expected_identity")
    try:
        with gdb.session_scope() as con:
            doc = DSTORE6.freeze_draft(con, draft_id, actor, expected_identity=expected_identity)
    except DSTORE6.DraftLocked as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(409 if "changed since" in msg else 400, msg)
    except FileExistsError:
        raise HTTPException(409, "an identical handoff was just dispatched (same content within the "
                                 "same second) — the prior one stands; retry in a moment if intended")
    cost = doc.get("cost") or {}
    return {"draft_id": draft_id, "handoff_id": HND6.handoff_filename(doc)[:-5],
           "handoff_hash": doc["handoff_hash"], "verified_only": bool(doc.get("verified_only")),
           "n_districts": len(doc.get("districts", [])), "n_reps": cost.get("n_reps", 0),
           "total_usd": cost.get("total_usd", 0.0), "provenance": cost.get("provenance", "unknown")}


@app.post("/api/dispatch/{draft_id}/abandon")
async def dispatch_abandon(draft_id: str, payload: dict):
    """Terminal abandon (reason optional), mirrors gate@1's `queue_abandon`."""
    actor = (payload or {}).get("actor", "ian")
    reason = (payload or {}).get("reason", "")
    try:
        with gdb.session_scope() as con:
            DSTORE6.abandon_draft(con, draft_id, actor, reason)
            view = DSTORE6.to_view(con, draft_id)
    except DSTORE6.DraftLocked as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    return view


# In-process extraction job board (single-user localhost), keyed by handoff_hash. Ephemeral by
# design — the DURABLE record is the `extraction`/`school_fact` rows run_council_streaming persists
# per district; this is just the live progress feed (mirrors _DISCOVER_JOBS, issue #47 pattern).
_EXTRACT_JOBS: dict = {}


def _extract_job_view(hh: str) -> dict | None:
    j = _EXTRACT_JOBS.get(hh)
    if not j:
        return None
    return {"state": j["state"], "started_at": j["started_at"], "finished_at": j["finished_at"],
            "actor": j["actor"], "error": j["error"], "summary": j["summary"],
            "n_events": len(j["events"]), "events": j["events"][-30:]}


@app.get("/api/extract/run/{handoff_hash}")
def extract_run_status(handoff_hash: str):
    """Live status of a Stage-7 extraction background job (#152). {state:'idle'} if none seen."""
    return _extract_job_view(handoff_hash) or {"state": "idle"}


@app.post("/api/extract/{handoff_hash}/run")
async def extract_run(handoff_hash: str, payload: dict):
    """Run the PAID Stage-7 council extraction for a DISPATCHED handoff as a BACKGROUND job (#152).
    The gate@6 dispatch approval IS the go-ahead — no separate approval. Resolves the frozen handoff
    file, runs `run_council_streaming` (durable/resumable per district, REQ-051 budget-gated, benchmark
    output still walled from Stage-9), streaming per-district progress into _EXTRACT_JOBS. Resumable:
    a re-run skips districts already extracted for this handoff. Returns immediately."""
    payload = payload or {}
    actor = payload.get("actor", "ian")
    with gdb.session_scope() as con:
        row = con.execute(text("SELECT path, status FROM handoff WHERE handoff_hash = :h"),
                          {"h": handoff_hash}).mappings().first()
    if not row:
        raise HTTPException(404, f"no such handoff {handoff_hash}")
    existing = _EXTRACT_JOBS.get(handoff_hash)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"extraction already running for {handoff_hash}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _EXTRACT_JOBS[handoff_hash] = job

    def _on_district(did, pd):
        bands = pd.get("bands") or {}
        job["events"].append({
            "district_id": did, "name": pd.get("name"),
            "n_accepted": len(pd.get("accepted") or []), "n_unresolved": len(pd.get("unresolved") or []),
            "bands": {b: (v or {}).get("gross_minutes") for b, v in bands.items()},
            "cost_usd": (pd.get("telemetry") or {}).get("cost_usd")})

    def _work():
        try:
            doc = R7.load_handoff(row["path"])
            summ = R7.run_council_streaming(doc, persist=True, created_by=actor, on_district=_on_district)
            failed = summ.get("failed") or []
            job["summary"] = {"n_districts": len(summ.get("districts", {})),
                              "n_failed": len(failed), "failed": failed}
            # #173: individual districts can fail without aborting the batch — a run that finished with
            # any failed district is `partial` (the good districts ARE durable), not a clean `done`.
            job["state"] = "partial" if failed else "done"
        except R7.OR.BillingAuthError as e:   # 401/402 — every later paid call fails identically → halt
            job["state"], job["error"] = "halted", f"BILLING/AUTH: {e}"
        except SystemExit as e:   # no key / #82 vision guard — surface, don't hide
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:    # noqa: BLE001
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    threading.Thread(target=_work, name=f"extract-{handoff_hash}", daemon=True).start()
    return {"started": True, "handoff_hash": handoff_hash}


@app.get("/api/handoff/councils")
def handoff_councils():
    """The council registry (id / name / input_kinds) for the gate@6 per-rep override dropdown."""
    return [{"id": cid, "name": c.get("name", cid), "input_kinds": c.get("input_kinds", [])}
            for cid, c in C6.load_configs().items()]


@app.get("/api/handoff/inspect")
def handoff_inspect(district_id: str, rec_key: str, file: str):
    """Serve one representation's file (text / image / pdf) for gate@6 inspection. Resolves
    RAW_CAPTURES/<district_dir>/captures/<hash>/<file>; path-safe (basename-only file + hex hash)."""
    if not file or "/" in file or "\\" in file or ".." in file:
        raise HTTPException(400, "bad file")
    if ":" not in rec_key or not re.fullmatch(r"[0-9a-fA-F]+", rec_key.split(":", 1)[1]):
        raise HTTPException(400, "bad rec_key")
    h = rec_key.split(":", 1)[1]
    with gdb.session_scope() as con:
        ddir = con.execute(text("SELECT district_dir FROM district WHERE district_id = :d"),
                           {"d": district_id}).scalar()
    if not ddir:
        raise HTTPException(404, "no such district")
    fp = paths.RAW_CAPTURES / ddir / "captures" / h / file
    if not fp.exists():
        # harvest slices moved out of the raw capture dir (issue #58) — resolve new-location-first,
        # legacy fallback (issue #48: this resolver only knew the legacy captures path)
        if file == BS.HARVEST_SLICE_FILE:
            alt = BS.resolve_harvest_slice(district_id, ddir, rec_key)
            if alt is not None:
                return FileResponse(alt)
        raise HTTPException(404, f"file not found: {file}")
    return FileResponse(fp)


# THE benchmark wall, as one SQL fragment (review round, PR #252 — it was inlined verbatim at two call
# sites, and Stage 9's write boundary will need it a third time; a rule this load-bearing gets ONE
# definition so a future change can't silently leave the gates disagreeing about what's benchmark).
# Keys on batch_type='benchmark' membership, never the batch_00000 id literal — the GT corpus grows
# into new benchmark batches. `{alias}` = the outer query's district-bearing table alias.
IS_BENCHMARK_SQL = """EXISTS (SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id
                              WHERE bd.district_id = {alias}.district_id
                                AND b.batch_type = 'benchmark')"""


# REQ-122 cumulative counts — the SQL twin of AGG.merge_fact_runs's accepted/unresolved rule ("a pair
# counts unresolved only if NO run ever accepted it"). Module-level so tests can execute THIS text and
# cross-check it against merge_fact_runs on shared fixture rows — the two must never drift.
CUMULATIVE_FACT_COUNTS_SQL = """SELECT f.district_id,
       COUNT(DISTINCT (f.band, f.school))
         FILTER (WHERE f.status = 'accepted') AS n_accepted,
       COUNT(DISTINCT (f.band, f.school))
         - COUNT(DISTINCT (f.band, f.school))
             FILTER (WHERE f.status = 'accepted') AS n_unresolved
FROM school_fact f
JOIN extraction fe ON fe.extraction_id = f.extraction_id
WHERE fe.run_kind = 'production'
GROUP BY f.district_id"""


@app.get("/api/extract/districts")
def extract_districts():
    """gate@7 left pane: districts with a Stage-7 extraction. `handoff_hash`/`cost_usd`/`created_at`
    are the LATEST run's header; `n_accepted`/`n_unresolved` are CUMULATIVE distinct (band, school)
    counts across ALL production runs (REQ-122/#232 — the latest-run rollup columns made a district
    whose scoped retry yielded 0 read as a total failure). A pair counts unresolved only if NO run
    ever accepted it — the same rule as AGG.merge_fact_runs. Attention-first (most pending requests,
    then most unresolved). Excludes PROBE runs (`run_kind='probe'` — the vision-council A/B from
    image_handoff_variant, not a production dispatch), which are experiments, not a review surface
    (#148)."""
    with gdb.session_scope() as con:
        rows = con.execute(text(
            f"""SELECT e.district_id, e.handoff_hash,
                      COALESCE(cf.n_accepted, 0) AS n_accepted,
                      COALESCE(cf.n_unresolved, 0) AS n_unresolved, e.cost_usd,
                      e.n_reps, e.created_at, d.name, d.state,
                      COALESCE(rq.n_pending, 0) AS n_pending, COALESCE(rq.n_requests, 0) AS n_requests
               FROM extraction e
               JOIN (SELECT district_id, MAX(extraction_id) mx FROM extraction
                     WHERE run_kind = 'production' GROUP BY district_id) L
                 ON L.mx = e.extraction_id
               LEFT JOIN district d ON d.district_id = e.district_id
               LEFT JOIN ({CUMULATIVE_FACT_COUNTS_SQL}) cf
                 ON cf.district_id = e.district_id
               LEFT JOIN (SELECT district_id,
                                 COUNT(*) FILTER (WHERE status = 'pending') n_pending, COUNT(*) n_requests
                          FROM extraction_request GROUP BY district_id) rq
                 ON rq.district_id = e.district_id
               ORDER BY n_pending DESC, n_unresolved DESC, e.district_id""")).mappings().all()
        return [dict(r) for r in rows]


def _district_loop_ctx(con, district_id: str) -> dict:
    """#154: the per-DISTRICT request-loop state, computed ONCE per detail call (not per request):
    the depth cap, rounds spent, and whether compose would LIVE-defer this district's NEW-work
    (EX._defer_76_districts — the same check compose runs, so the card never disagrees with compose)."""
    maxr = EX.BUD.load_budget().max_request_rounds
    rounds = EX._executed_rounds_76(con, district_id)
    defer_set = EX._defer_76_districts(con, [district_id], maxr)
    n_unexec_76 = con.execute(text(
        "SELECT COUNT(*) FROM extraction_request WHERE district_id = :d AND route = :r "
        f"AND status IN {EX.RQ.OPEN_STATUSES_SQL}"),
        {"d": district_id, "r": EX.RQ.ROUTE_ALT_REP}).scalar()
    return {"maxr": maxr, "rounds_76": rounds, "defers": district_id in defer_set,
            "n_unexec_76": n_unexec_76}


def _request_lineage(con, district_id: str, req: dict, ctx: dict) -> dict | None:
    """#154: make the request loop legible — WHERE an executed directive went (+ the target's live
    state) and WHY an approved/pending one can't fire yet. `ctx` = _district_loop_ctx (LIVE state —
    never the request's detect-time params, which go stale once the district's 7->6s run or are
    rejected). Returns a small dict the card renders, or None for an ordinary reviewable request."""
    route, status, ref = req["route"], req["status"], req.get("executed_ref")
    if status == "executed" and ref:
        if route == EX.RQ.ROUTE_ALT_REP:                       # 7->6 -> a new Stage-6 handoff
            h = con.execute(text("SELECT status, n_districts FROM handoff WHERE handoff_hash = :h"),
                            {"h": ref}).mappings().first()
            n_ext = con.execute(text("SELECT COUNT(*) FROM extraction WHERE handoff_hash = :h"),
                                {"h": ref}).scalar()
            job = _EXTRACT_JOBS.get(ref)
            # #186: a `partial` job (some districts failed while others extracted) must NOT read as a
            # clean "extracted" — the reviewer needs to see the remedy only partly landed.
            n_failed = (job.get("summary") or {}).get("n_failed") if job else None
            state = ("extracting…" if job and job["state"] == "running"
                     else f"partial — {n_failed} failed" if job and job["state"] == "partial"
                     else "extracted" if n_ext else "dispatched — run extraction at Stage 6")
            return {"kind": "handoff", "ref": ref, "state": state, "n_extracted": n_ext,
                    "n_districts": h["n_districts"] if h else None}
        b = con.execute(text("SELECT status FROM batch WHERE batch_id = :b"), {"b": ref}).mappings().first()
        af = _AUTOFLOW_JOBS.get(ref)
        state = (f"auto-flow: {af['stage']}" if af and af["state"] == "running"
                 else "auto-flow done → gate@5" if af and af["state"] == "done"
                 else f"auto-flow {af['state']}" if af
                 else (b["status"] if b else "batch gone"))
        return {"kind": "batch", "ref": ref, "state": state, "batch_status": b["status"] if b else None}
    if route == EX.RQ.ROUTE_ALT_REP and status in ("approved", "pending"):
        if ctx["maxr"] is not None and ctx["rounds_76"] >= ctx["maxr"]:
            return {"blocked": True, "reason": f"depth guard: {ctx['rounds_76']}/{ctx['maxr']} 7->6 "
                                               f"rounds spent — this alternate-rep re-dispatch can "
                                               f"no longer execute"}
    if route == EX.RQ.ROUTE_REDISCOVER and status in ("approved", "pending") and ctx["defers"]:
        return {"deferred": True, "reason": f"{ctx['n_unexec_76']} un-executed 7->6 for this district — "
                                            f"compose holds this rediscover until they run (#159)"}
    return None


@app.get("/api/extract/district/{district_id}")
def extract_district(district_id: str):
    """gate@7 detail: the district's CUMULATIVE Stage-7 truth — accepted/unresolved per-school facts
    merged across ALL production runs (REQ-122/#232: a follow-up round fills gaps, it never regresses
    solid signal — the latest-run-only read made a scoped 7→6 retry LOOK like it erased an earlier
    run's accepted facts) + the band rollup over that merge + the request-more-evidence directives.
    `extraction` stays the LATEST run's header (what ran last, at what cost)."""
    with gdb.session_scope() as con:
        ext = con.execute(text(
            "SELECT extraction_id, handoff_hash, created_at, created_by, cost_usd, "
            "n_accepted, n_unresolved, n_reps, n_reps_skipped FROM extraction "
            "WHERE district_id = :d AND run_kind = 'production' "     # #148: exclude probe runs
            "ORDER BY extraction_id DESC LIMIT 1"), {"d": district_id}).mappings().first()
        if not ext:
            raise HTTPException(404, "no extraction for this district")
        facts = con.execute(text(
            # every production run's facts, each carrying its run id + handoff (per-fact provenance
            # a reviewer can trace); the pure merge picks the per-(band,school) winner (REQ-122).
            "SELECT f.extraction_id, e.handoff_hash, f.band, f.school, f.status, f.start_time, "
            "f.end_time, f.gross_minutes, f.method, f.models_json, f.detail_json, f.rec_key, "
            "f.source_file FROM school_fact f "
            "JOIN extraction e ON e.extraction_id = f.extraction_id "
            "WHERE f.district_id = :d AND e.run_kind = 'production' "
            "ORDER BY f.status, f.band, f.school"),
            {"d": district_id}).mappings().all()
        accepted, unresolved = AGG.merge_fact_runs([dict(f) for f in facts])
        agg = [{"band": a["band"], "school": a["school"], "gross": a["gross_minutes"],
                "start": a["start_time"], "end": a["end_time"],
                "models": json.loads(a["models_json"] or "[]"), "method": a["method"]}
               for a in accepted if a["gross_minutes"] is not None]
        bands = AGG.district_bands_from_facts(agg)
        # #245: degenerate-named facts (empty, or purely-generic like "Schools") are excluded from the
        # rollup above — surface them here so a human sees WHY a school vanished, never a silent drop.
        degenerate = AGG.degenerate_school_facts(agg)
        # #237: flag single-school-LEA over-extraction (charter-network sibling contamination on a
        # shared CMO domain, or a blank-domain unscoped capture — the Millard #227 class) for the
        # reviewing human. DETECT-AND-FLAG ONLY, never auto-reject: picking the real school is
        # unreliable (shared network names recur, acronyms fail a name match), so the human decides.
        # Display-only — does not touch stored fact status.
        meta = con.execute(text(
            "SELECT d.nces_school_count AS nces, dt.schools_by_band_json AS sbb FROM district d "
            "LEFT JOIN district_target dt ON dt.district_id = d.district_id WHERE d.district_id = :d"),
            {"d": district_id}).mappings().first()
        roster = []
        if meta and meta["sbb"]:
            try:
                for _band, info in json.loads(meta["sbb"]).items():
                    roster += [s.get("name") or s.get("school") for s in (info or {}).get("schools", [])
                               if isinstance(s, dict)]
            except (ValueError, TypeError, AttributeError):
                # TypeError included (PR #247 review): json.loads raises it (not ValueError) on a
                # non-str input — e.g. a text->JSONB column migration handing back a pre-parsed dict —
                # and the intent here is degrade-to-no-roster, never a 500.
                roster = []
        # Epic-#499 review round: the FULL live roster, matching gate@8's cs_roster (REQ-145's
        # "detector sees beyond the Stage-1 selected subset" applies to BOTH call sites) — the
        # narrow subset here made gate@7 flag contamination gate@8 correctly suppresses when the
        # matching sibling school simply wasn't selected into the batch. CCD-absent degrades to
        # the Stage-1 subset (the pre-#499 behavior).
        try:
            _br = SS_SAMPLING.band_rosters_for_district(district_id)
        except Exception:
            _br = None
        for _b, _m in (_br or {}).items():
            if isinstance(_m, dict) and _m.get("schools"):
                roster += _m["schools"]
        contamination = AGG.detect_single_school_over_extraction(
            agg, meta["nces"] if meta else None, roster)
        # ALL of the district's directives, across every handoff (#137): pinning to the latest
        # extraction's handoff_hash made pending directives from an earlier handoff invisible (and
        # unreviewable) the moment a newer extraction landed — e.g. right after a 7->6 re-dispatch ran.
        reqs = con.execute(text(
            "SELECT request_id, handoff_hash, altitude, route, target, band, params_json, reason, "
            "status, reviewed_by, reviewed_at, review_note, created_at, executed_ref, executed_at "
            "FROM extraction_request "
            "WHERE district_id = :d ORDER BY status = 'pending' DESC, altitude, route, band"),
            {"d": district_id}).mappings().all()
        ctx = _district_loop_ctx(con, district_id)                 # #154: LIVE loop state, once
        req_dicts = []
        for r in reqs:
            d = dict(r)
            # #147: the server classifies the route (from the RQ constants) so the JS never re-spells
            # '7->2'/'7->6' — a new/renamed route flows through automatically instead of silently
            # stranding approved directives whose route the client doesn't recognize.
            d["is_newwork"] = d["route"] in EX.NEWWORK_ROUTES      # 7->2/7->3/7->1 → follow-up batch sweep
            d["is_alt_rep"] = d["route"] == EX.RQ.ROUTE_ALT_REP    # 7->6 → executes on its own
            d["lineage"] = _request_lineage(con, district_id, d, ctx)  # where it went / why it can't
            req_dicts.append(d)
        # The extraction header keeps the LATEST run's identity/cost, but its per-run n_accepted/
        # n_unresolved are overridden with the CUMULATIVE counts — otherwise the payload ships two
        # contradictory counts of the same thing (REQ-122 one field deeper: a barren scoped retry
        # would show n_accepted=0 beside a non-empty accepted[]).
        ext_out = dict(ext)
        ext_out["n_accepted"], ext_out["n_unresolved"] = len(accepted), len(unresolved)
        return {"extraction": ext_out, "bands": bands, "accepted": accepted,
                "unresolved": unresolved, "requests": req_dicts, "contamination": contamination,
                "degenerate_school_facts": degenerate}


# ==================== Stage 8 / gate@8 — Aggregate (the closing argument) ====================
@app.get("/api/aggregate/districts")
def aggregate_districts():
    """gate@8 left pane: the closing-argument review queue — districts with production facts whose gate@7
    request loop is QUIESCED (no open request; the §2 entry condition), each badged with its latest gate@8
    decision. Undecided first, then most unresolved (attention-first). Cheap counts only; the full closing
    argument loads on click.

    EXCLUDES benchmark districts via the shared IS_BENCHMARK_SQL wall — the SAME fragment the dispatch
    preview uses (one definition, review round PR #252). gate@8 authorizes the Stage-9 LCT write, and
    benchmark stays walled off; it is ALSO how the growing GT yardstick works (a non-benchmark district
    promoted here becomes verified GT — benchmark districts are already the yardstick, so they don't
    re-flow through this gate)."""
    with gdb.session_scope() as con:
        rows = con.execute(text(
            f"""SELECT p.district_id, d.name, d.state,
                      COALESCE(cf.n_accepted, 0) AS n_accepted,
                      COALESCE(cf.n_unresolved, 0) AS n_unresolved, s8.disposition
               FROM (SELECT DISTINCT district_id FROM extraction WHERE run_kind='production') p
               LEFT JOIN district d ON d.district_id = p.district_id
               LEFT JOIN ({CUMULATIVE_FACT_COUNTS_SQL}) cf ON cf.district_id = p.district_id
               LEFT JOIN LATERAL (SELECT disposition FROM stage8_approval a
                                  WHERE a.district_id = p.district_id
                                  ORDER BY approval_id DESC LIMIT 1) s8 ON true
               WHERE COALESCE(cf.n_accepted, 0) > 0
                 AND NOT EXISTS (SELECT 1 FROM extraction_request r
                                 WHERE r.district_id = p.district_id
                                   AND r.status IN {EX.RQ.OPEN_STATUSES_SQL})
                 AND NOT {IS_BENCHMARK_SQL.format(alias='p')}
               ORDER BY (s8.disposition IS NOT NULL), n_unresolved DESC, p.district_id""")).mappings().all()
        return [dict(r) for r in rows]


@app.get("/api/aggregate/district/{district_id}")
def aggregate_district_detail(district_id: str):
    """The closing argument for one district (band claim + dereferenced evidence + sampling + negative
    space) + its gate@8 decision status (approved / sent_back / pending, and whether an approval has gone
    STALE against the live facts). The top-level `fingerprint` is the review token: the client MUST echo
    it back to POST /api/aggregate/decision, which refuses (409) if the live facts no longer match —
    closing the review→click window (see aggregate_decision)."""
    with gdb.session_scope() as con:
        ca = CA8.load_closing_argument(con, district_id)
        fp = CA8.fingerprint(ca)
        status = APV8.decision_status(con, district_id, current_fingerprint=fp)
        return {"closing_argument": ca, "decision": status, "fingerprint": fp}


@app.post("/api/aggregate/override")
async def aggregate_override(payload: dict):
    """Record a human override of one school's extracted times, with a REQUIRED reason (§2a.3). Stored on
    school_fact.human_determination as an auditable JSON record; the council's original times are NEVER
    destroyed (kept on the fact). The override is OPERATIVE the moment it's recorded: the closing
    argument recomputes the band mode over the override-effective times (revised 2026-07-13), so the
    displayed determination the reviewer approves reflects the correction.

    A times-override is VALIDATED before it's stored (15c67c4 review): the effective pair (override
    value where given, council's endpoint otherwise) must parse as HH:MM and pass the REQ-055 PLAUSIBLE
    gate via the canonical AGG.gross_from_times — the same bar every council-extracted fact meets. A
    typo'd '3pm' or a pair yielding gross=125 gets an immediate 400 with the reason, instead of being
    stored and silently failing three layers downstream. 400 on missing fact_id/reason or an invalid
    times pair, 404 on no such fact."""
    fact_id, reason = payload.get("fact_id"), (payload.get("reason") or "").strip()
    actor = payload.get("actor", "ian")
    ov_start = (payload.get("start_time") or "").strip() or None
    ov_end = (payload.get("end_time") or "").strip() or None
    # `is None`, not truthiness (review round, PR #252): a falsy-but-present id (0) must reach the
    # SELECT and 404 honestly, not be misreported as "missing" — SERIAL PKs start at 1 today, but the
    # validation shouldn't encode that assumption.
    if fact_id is None or not reason:
        raise HTTPException(400, "fact_id and a non-empty reason are required")
    with gdb.session_scope() as con:
        row = con.execute(text("SELECT start_time, end_time FROM school_fact WHERE fact_id = :f"),
                          {"f": fact_id}).mappings().first()
        if row is None:
            raise HTTPException(404, f"no school_fact {fact_id}")
        if ov_start or ov_end:
            eff_start = ov_start or row["start_time"]
            eff_end = ov_end or row["end_time"]
            _, err = AGG.gross_from_times(eff_start, eff_end)
            if err:
                raise HTTPException(400, f"override rejected ({err}): effective times "
                                         f"{eff_start!r}–{eff_end!r} must both parse as HH:MM and give "
                                         f"a gross inside {AGG.PLAUSIBLE} min")
        det = json.dumps({"start_time": ov_start, "end_time": ov_end,
                          "reason": reason, "actor": actor, "at": _u7()})
        con.execute(text("UPDATE school_fact SET human_determination = :d WHERE fact_id = :f"),
                    {"d": det, "f": fact_id})
        con.commit()
    return {"ok": True, "fact_id": fact_id}


@app.post("/api/aggregate/exclude")
async def aggregate_exclude(payload: dict):
    """#257: record a standing human 'exclude school from band' (with a REQUIRED reason) — the human
    sibling of the automatic exclude-but-surface detectors (#245/#237). District-grain, keyed
    (district_id, band, norm_school), so it survives follow-up re-extraction (a fact-attached exclusion
    would vanish with the next winning fact and re-pollute the band). OPERATIVE immediately: the closing
    argument recomputes the band mode over the non-excluded schools; the excluded fact stays visible
    (struck-through) and the exclusion enters the receipt + staleness fingerprint. Re-excluding the same
    (band, school) replaces the record (fresh reason/actor/timestamp). 400 on a missing field or an
    unknown band."""
    from infrastructure.acquisition.common.school_match import norm_school, norm_school_strict

    did, band = payload.get("district_id"), payload.get("band")
    school, reason = (payload.get("school") or "").strip(), (payload.get("reason") or "").strip()
    actor = payload.get("actor", "ian")
    if not did or not school or not reason:
        raise HTTPException(400, "district_id, school and a non-empty reason are required")
    if band not in AGG.BANDS:
        raise HTTPException(400, f"band must be one of {AGG.BANDS}")
    # guard on the STRICT normalization (a pure-stopword name like 'schools' is the #245 degenerate
    # class — already out of every rollup, so excluding it is meaningless); the stored KEY uses the
    # non-strict norm_school, the same axis the merge and the builder match on.
    if not norm_school_strict(school):
        raise HTTPException(400, f"school name {school!r} is degenerate (#245) — nothing to exclude")
    key = norm_school(school)
    with gdb.session_scope() as con:
        con.execute(text("DELETE FROM band_exclusion WHERE district_id = :d AND band = :b "
                         "AND norm_school = :n"), {"d": did, "b": band, "n": key})
        con.execute(text("INSERT INTO band_exclusion (district_id, band, norm_school, school, reason, "
                         "actor, created_at) VALUES (:d, :b, :n, :s, :r, :a, :t)"),
                    {"d": did, "b": band, "n": key, "s": school, "r": reason, "a": actor, "t": _u7()})
        _backup_band_exclusions(con)
        con.commit()
    return {"ok": True, "district_id": did, "band": band, "norm_school": key}


@app.post("/api/aggregate/exclude/restore")
async def aggregate_exclude_restore(payload: dict):
    """#257: lift a standing band-exclusion (reversible-before-freeze). A hard DELETE is correct for
    auditability here: every gate@8 decision froze the exclusions operative at that moment into its
    receipt, so history is preserved where it matters — the receipts — while the live picture returns
    the school to its band's mode. 404 if no such exclusion."""
    from infrastructure.acquisition.common.school_match import norm_school

    did, band, school = payload.get("district_id"), payload.get("band"), (payload.get("school") or "").strip()
    if not did or not school or band not in AGG.BANDS:
        raise HTTPException(400, "district_id, band and school are required")
    with gdb.session_scope() as con:
        n = con.execute(text("DELETE FROM band_exclusion WHERE district_id = :d AND band = :b "
                             "AND norm_school = :n"),
                        {"d": did, "b": band, "n": norm_school(school)}).rowcount
        if not n:
            raise HTTPException(404, f"no exclusion for {school!r} in {band} of {did}")
        _backup_band_exclusions(con)
        con.commit()
    return {"ok": True}


@app.post("/api/aggregate/human-add")
async def aggregate_human_add(payload: dict):
    """#474: hand-enter a school's times into a band — the LAST-RESORT fallback when re-extraction
    (#473) can't recover data the reviewer can see in a captured artifact. Single-source and
    council-unvalidated, so the bar is higher than an override: a CITED SOURCE (http/https URL or
    artifact id) is required alongside the reason, BOTH times are required (a new school has no
    council endpoint to fall back on), and the pair passes the same canonical gross_from_times +
    REQ-055 PLAUSIBLE gate as every extracted value. Votes in the band mode immediately (§2a.3);
    rendered visibly tagged; in the receipt + staleness fingerprint. Re-adding the same
    (band, school) replaces. An existing #257 exclusion on the same (band, school) is refused —
    lift the exclusion first (the two records must never fight silently)."""
    from infrastructure.acquisition.common.school_match import norm_school, norm_school_strict

    did, band = payload.get("district_id"), payload.get("band")
    school = (payload.get("school") or "").strip()
    start, end = (payload.get("start_time") or "").strip(), (payload.get("end_time") or "").strip()
    source, reason = (payload.get("source_url") or "").strip(), (payload.get("reason") or "").strip()
    actor = payload.get("actor", "ian")
    if not did or not school or not reason:
        raise HTTPException(400, "district_id, school and a non-empty reason are required")
    if band not in AGG.BANDS:
        raise HTTPException(400, f"band must be one of {AGG.BANDS}")
    if not source:
        raise HTTPException(400, "a cited source (source_url) is REQUIRED for a hand-entered value (#474)")
    if not (start and end):
        raise HTTPException(400, "both start_time and end_time are required for a hand-added school")
    if not norm_school_strict(school):
        raise HTTPException(400, f"school name {school!r} is degenerate (#245)")
    gross, err = AGG.gross_from_times(start, end)
    if err:
        raise HTTPException(400, f"hand-entered times rejected ({err}): {start!r}–{end!r} must both "
                                 f"parse as HH:MM and give a gross inside {AGG.PLAUSIBLE} min")
    key = norm_school(school)
    with gdb.session_scope() as con:
        excl = con.execute(text("SELECT reason FROM band_exclusion WHERE district_id = :d "
                                "AND band = :b AND norm_school = :n"),
                           {"d": did, "b": band, "n": key}).mappings().first()
        if excl:
            raise HTTPException(409, f"{school!r} is excluded from {band} (#257: {excl['reason']}) — "
                                     f"restore the exclusion before hand-adding")
        # Review round 2: a hand-add duplicating a STILL-ACCEPTED council fact would put two rows
        # for one school into the mode (a double vote) and the slot projection (a silently-dropped
        # duplicate). Corrections to an extracted value go through the per-school OVERRIDE — #474
        # is for schools the council MISSED, so an existing accepted fact refuses the add.
        for r in con.execute(text(
                "SELECT DISTINCT f.school FROM school_fact f "
                "JOIN extraction e ON e.extraction_id = f.extraction_id "
                "WHERE f.district_id = :d AND f.band = :b AND f.status = 'accepted' "
                "AND e.run_kind = 'production'"), {"d": did, "b": band}):
            if norm_school(r[0] or "") == key:
                raise HTTPException(409, f"{school!r} already has an accepted council fact in "
                                         f"{band} — correct it with the per-school override, "
                                         f"not a hand-add (#474 is for schools the council missed)")
        con.execute(text("DELETE FROM human_added_fact WHERE district_id = :d AND band = :b "
                         "AND norm_school = :n"), {"d": did, "b": band, "n": key})
        con.execute(text("INSERT INTO human_added_fact (district_id, band, norm_school, school, "
                         "start_time, end_time, source_url, reason, actor, created_at) "
                         "VALUES (:d, :b, :n, :s, :st, :en, :u, :r, :a, :t)"),
                    {"d": did, "b": band, "n": key, "s": school, "st": start, "en": end,
                     "u": source, "r": reason, "a": actor, "t": _u7()})
        _backup_human_added(con)
        con.commit()
    return {"ok": True, "district_id": did, "band": band, "norm_school": key, "gross": gross}


@app.post("/api/aggregate/human-add/remove")
async def aggregate_human_add_remove(payload: dict):
    """#474: withdraw a hand-entered school (reversible-before-freeze; history lives in the frozen
    receipts, same posture as #257 restore). 404 if no such entry."""
    from infrastructure.acquisition.common.school_match import norm_school

    did, band, school = payload.get("district_id"), payload.get("band"), (payload.get("school") or "").strip()
    if not did or not school or band not in AGG.BANDS:
        raise HTTPException(400, "district_id, band and school are required")
    with gdb.session_scope() as con:
        n = con.execute(text("DELETE FROM human_added_fact WHERE district_id = :d AND band = :b "
                             "AND norm_school = :n"),
                        {"d": did, "b": band, "n": norm_school(school)}).rowcount
        if not n:
            raise HTTPException(404, f"no hand-added entry for {school!r} in {band} of {did}")
        _backup_human_added(con)
        con.commit()
    return {"ok": True}


@app.post("/api/aggregate/slot-assign")
async def aggregate_slot_assign(payload: dict):
    """#499 REQ-145: record a standing human SLOT DISPOSITION — the resolution the projection
    refuses to auto-make. Verbs: 'assign' (bind fact→slot), 'reject' (fact is NOT that slot),
    'confirm_extra' (the extra is a real school NCES missed — becomes a human-confirmed slot,
    denominator +1; roster_school_id must be empty). District-grain (survives re-extraction),
    keyed (district, band, slot, fact); re-posting replaces. Reason REQUIRED (the resolving
    knowledge). Enters the receipt + staleness fingerprint."""
    from infrastructure.acquisition.common.school_match import norm_school, norm_school_strict
    from infrastructure.acquisition.common.slot_spine import DISPOSITIONS

    did, band = payload.get("district_id"), payload.get("band")
    school = (payload.get("school") or "").strip()          # the FACT's display name
    slot_id = (payload.get("roster_school_id") or "").strip()
    disposition = payload.get("disposition")
    reason, actor = (payload.get("reason") or "").strip(), payload.get("actor", "ian")
    if not did or not school or not reason:
        raise HTTPException(400, "district_id, school and a non-empty reason are required")
    if band not in AGG.BANDS:
        raise HTTPException(400, f"band must be one of {AGG.BANDS}")
    if disposition not in DISPOSITIONS:
        raise HTTPException(400, f"disposition must be one of {DISPOSITIONS}")
    if disposition in ("assign", "reject") and not slot_id:
        raise HTTPException(400, f"{disposition} requires roster_school_id (the NCESSCH slot key)")
    if disposition == "confirm_extra" and slot_id:
        raise HTTPException(400, "confirm_extra takes no roster_school_id — it CREATES the slot")
    if not norm_school_strict(school):
        raise HTTPException(400, f"school name {school!r} is degenerate (#245) — nothing to dispose")
    # Epic-#499 review round: an assign/reject must name a slot that EXISTS in the district's live
    # roster at write time — a mistyped/stale slot_id would otherwise insert cleanly and surface
    # only later as an orphan, byte-identical to legitimate roster drift (the data-entry mistake
    # hides inside the drift signal). CCD-absent skips the check (best-effort, never blocks).
    if disposition in ("assign", "reject"):
        try:
            _rosters = SS_SAMPLING.band_rosters_for_district(did)
        except Exception:
            _rosters = None
        if _rosters is not None:
            live_ids = {rc.get("school_id")
                        for rc in ((_rosters.get(band) or {}).get("slot_recs") or [])}
            if slot_id not in live_ids:
                raise HTTPException(400, f"roster_school_id {slot_id!r} is not a live {band} "
                                         f"slot for {did} — refresh the view and re-pick")
    key = norm_school(school)
    with gdb.session_scope() as con:
        con.execute(text("DELETE FROM slot_assignment WHERE district_id = :d AND band = :b "
                         "AND roster_school_id = :s AND norm_school_fact = :n"),
                    {"d": did, "b": band, "s": slot_id, "n": key})
        con.execute(text(
            "INSERT INTO slot_assignment (district_id, band, roster_school_id, norm_school_fact, "
            "school, disposition, reason, actor, created_at) "
            "VALUES (:d, :b, :s, :n, :sc, :dp, :r, :a, :t)"),
            {"d": did, "b": band, "s": slot_id, "n": key, "sc": school, "dp": disposition,
             "r": reason, "a": actor, "t": _u7()})
        _backup_slot_assignments(con)
        con.commit()
    return {"ok": True, "district_id": did, "band": band, "norm_school_fact": key,
            "disposition": disposition}


@app.post("/api/aggregate/slot-assign/remove")
async def aggregate_slot_assign_remove(payload: dict):
    """#499 REQ-145: retire a standing slot disposition (reversible-before-freeze; the orphan
    flags' resolution path). Hard DELETE — history lives in the frozen receipts. 404 if absent."""
    from infrastructure.acquisition.common.school_match import norm_school

    did, band = payload.get("district_id"), payload.get("band")
    school = (payload.get("school") or "").strip()
    slot_id = (payload.get("roster_school_id") or "").strip()
    if not did or not school or band not in AGG.BANDS:
        raise HTTPException(400, "district_id, band and school are required")
    with gdb.session_scope() as con:
        n = con.execute(text("DELETE FROM slot_assignment WHERE district_id = :d AND band = :b "
                             "AND roster_school_id = :s AND norm_school_fact = :n"),
                        {"d": did, "b": band, "s": slot_id, "n": norm_school(school)}).rowcount
        if not n:
            raise HTTPException(404, f"no slot disposition for {school!r} in {band} of {did}")
        _backup_slot_assignments(con)
        con.commit()
    return {"ok": True}


@app.post("/api/aggregate/recover-band")
async def aggregate_recover_band(payload: dict):
    """#473: gate@8 'recover band' — stage a re-extraction of the NAMED already-captured rep for a
    band that came out empty while its siblings were extracted from the same doc (the TUSD class).
    Mints an approved 7->6 request (lineage) + an immutable dispatch; the PAID extraction is then run
    at gate@7 (budget-gated) — this endpoint spends nothing. Benchmark-walled + depth-guarded in the
    executor."""
    did, band = payload.get("district_id"), payload.get("band")
    rec_key, file = payload.get("rec_key"), payload.get("file")
    if not did or band not in AGG.BANDS or not rec_key or not file:
        raise HTTPException(400, "district_id, band, rec_key and file are required")
    out = EX.recover_band_dispatch(did, band, rec_key, file, actor=payload.get("actor", "ian"))
    if not out.get("ok"):
        raise HTTPException(409 if out.get("blocked") else 400, out.get("reason", "recover-band failed"))
    return out


@app.post("/api/aggregate/decision/{district_id}")
async def aggregate_decision(district_id: str, payload: dict):
    """Record the gate@8 verdict on the WHOLE district (§2e, all-or-nothing): 'approved' (Stage 9 may
    write every band) or 'sent_back' (a reason is REQUIRED → an 8→1/8→6 back-edge). Re-loads the closing
    argument SERVER-side (never trusts the client's copy), freezes it as the receipt + fingerprint, fires
    the gate@8 calibration hook (accruing from day one), commits, and backs up the tracked JSON.

    `expected_fingerprint` is REQUIRED (review round, PR #252): the fingerprint the GET handed the
    reviewer with the page they actually read. The server-side re-load alone guarded against a tampered
    client payload but NOT against a legitimate DB write landing between the reviewer's GET and their
    click (a Stage-7 follow-up completing, another session's override) — with no prior approval to
    compare against, `is_stale` had nothing to flag, so the verdict silently froze facts the human never
    saw. A mismatch now returns 409: reload, re-review, decide again."""
    disposition, reason = payload.get("disposition"), payload.get("reason")
    expected_fp = payload.get("expected_fingerprint")
    actor = payload.get("actor", "ian")
    if disposition not in APV8.DISPOSITIONS:
        raise HTTPException(400, f"disposition must be one of {APV8.DISPOSITIONS}")
    if not expected_fp:
        raise HTTPException(400, "expected_fingerprint is required — send the fingerprint from the "
                                 "district detail view you reviewed")
    with gdb.session_scope() as con:
        ca = CA8.load_closing_argument(con, district_id)
        if not ca.get("bands"):
            raise HTTPException(400, f"district {district_id} has no accepted facts to decide on")
        live_fp = CA8.fingerprint(ca)
        if live_fp != expected_fp:
            raise HTTPException(409, "the district's facts changed after you loaded the page "
                                     f"(reviewed {expected_fp}, live {live_fp}) — reload and re-review "
                                     "before deciding")
        meta = con.execute(text("SELECT name, state FROM district WHERE district_id = :d"),
                           {"d": district_id}).mappings().first() or {}
        try:
            approval_id = APV8.record_decision(con, ca, disposition=disposition, actor=actor,
                                               reason=reason, name=meta.get("name", ""),
                                               state=meta.get("state"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        cal = GCAL.gate8_decision_record(
            district_id=district_id, disposition=disposition,
            min_coverage=CA8.min_band_coverage(ca), state=meta.get("state"),
            run_kind="production", created_at=_u7())
        if cal:
            CAL.record_calibration(con, cal)
        con.commit()
        _backup_stage8_approvals(con)
    return {"ok": True, "approval_id": approval_id, "disposition": disposition}


@app.post("/api/extract/request/{request_id}")
async def extract_request_review(request_id: int, payload: dict):
    """gate@7 action: approve / reject / reopen a request-more-evidence directive (records
    who/when/note). This stays PURE review under the ramp-up model (governance §11b) — approving a
    directive does NOT execute it. EXECUTION is a separate, explicit step (REQ-118): 7→6 via
    POST /api/extract/execute/{id}; 7→2/7→3/7→1 collected via POST /api/extract/compose-followup."""
    status = payload.get("status")
    if status not in ("approved", "rejected", "pending"):
        raise HTTPException(400, "status must be approved | rejected | pending")
    with gdb.session_scope() as con:
        # 'executed' is TERMINAL (#135): a fired directive must never be reopened/re-approved — the
        # depth guard COUNTS rows whose current status is 'executed', so a reopen would decrement the
        # safety counter and allow unlimited paid re-fires (and overwrite the lineage of the first
        # firing). The UI hides the button; this WHERE clause is the actual gate.
        # RETURNING carries the row's identity out of the UPDATE itself (#218 review) — no re-SELECT,
        # and a None row preserves the exact 404-vs-409 distinction the old rowcount check made.
        req = con.execute(text(
            "UPDATE extraction_request SET status = :s, reviewed_by = :by, reviewed_at = :now, "
            "review_note = :note WHERE request_id = :id AND status != 'executed' "
            "RETURNING district_id, band, handoff_hash"),
            {"s": status, "by": payload.get("actor", "ian"), "now": _u7(),
             "note": payload.get("note"), "id": request_id}).mappings().first()
        if not req:
            cur = con.execute(text(
                "SELECT status FROM extraction_request WHERE request_id = :id"),
                {"id": request_id}).scalar()
            if cur is None:
                raise HTTPException(404, "no such request")
            raise HTTPException(409, "executed directives are terminal — they cannot be reopened "
                                     "(the depth guard and lineage key off the executed status)")
        # gate@7 calibration (REQ-121/#210): log the shadow-mode record for a TERMINAL review decision —
        # the council agreement ratio proxy vs. the human's approve/reject of the directive. Skipped for
        # a 'pending' reopen. Same transaction as the UPDATE above. run_kind='production' matches the
        # gate@7 surfaces (#148: a probe run's stats must never masquerade as the reviewed run's).
        if status in ("approved", "rejected"):
            ext = con.execute(text(
                """SELECT n_accepted, n_unresolved, run_kind FROM extraction
                   WHERE district_id = :did AND handoff_hash = :hh AND run_kind = 'production'
                   ORDER BY extraction_id DESC LIMIT 1"""),
                {"did": req["district_id"], "hh": req["handoff_hash"]}).mappings().first() or {}
            st = con.execute(text("SELECT state FROM district WHERE district_id = :did"),
                             {"did": req["district_id"]}).scalar()
            cal = GCAL.gate7_request_record(
                request_id=request_id, district_id=req["district_id"], status=status,
                n_accepted=ext.get("n_accepted"), n_unresolved=ext.get("n_unresolved"),
                band=req["band"], state=st, run_kind=ext.get("run_kind"), created_at=_u7())
            if cal:
                CAL.record_calibration(con, cal)
        # A REOPEN re-runs the #233 premise check (#240 review): without this, reopening a withdrawn
        # (or rejected) directive silently resurrects work whose gap may no longer exist. If the
        # premise is STILL satisfied, the row re-withdraws immediately with a fresh note — the human
        # sees exactly why; if the gap genuinely re-opened, it stays pending. Human stays the boss,
        # the state stays honest.
        rewithdrawn = None
        if status == "pending":
            hits = R7.withdraw_satisfied_requests(con, req["district_id"])
            rewithdrawn = next((note for rid, note in hits if rid == request_id), None)
    out = {"request_id": request_id, "status": status}
    if rewithdrawn:
        out.update(status="withdrawn", rewithdrawn=True, note=rewithdrawn)
    return out


# ---- #157: follow-up auto-flow — gate@1 auto-pass + auto-run Stages 2->3->4, stop at gate@5 ----
# A follow-up batch carries an already-approved gate@7 decision, so re-gating it at gate@1 and clicking
# Start on each of Stages 2/3/4 is redundant (governance §11b ramp-up; the gate@1/stage-trigger de-facto
# gates auto-advance for follow-ups). gate@5 (new URLs = data quality) and gate@6 (spend) stay manual.
_AUTOFLOW_JOBS: dict = {}


def _autoflow_view(batch_id: str) -> dict | None:
    j = _AUTOFLOW_JOBS.get(batch_id)
    if not j:
        return None
    return {k: j[k] for k in ("state", "stage", "started_at", "finished_at", "actor", "error", "stages")}


@app.get("/api/followup/autoflow/{batch_id}")
def followup_autoflow_status(batch_id: str):
    """Live status of a follow-up auto-flow (#157). {state:'idle'} if none seen."""
    return _autoflow_view(batch_id) or {"state": "idle"}


def _autoflow_followup(batch_id: str, actor: str) -> None:
    """One supervisor thread: gate@1 auto-approve -> Stage 2 discover -> Stage 3 capture -> Stage 4
    process, landing at gate@5. Holds the per-batch run lock across the whole chain (a manual stage
    run 409s while it flows); any stage's failure halts the chain and records where. gate@6 stays
    manual — the spend gate is never auto-crossed."""
    from infrastructure.acquisition.common.timeutil import utcnow as _now

    job = {"state": "running", "stage": "approve", "started_at": _now(), "finished_at": None,
           "actor": actor, "error": None, "stages": {}}
    _AUTOFLOW_JOBS[batch_id] = job
    try:
        lock = _acquire_batch_run(batch_id)
    except HTTPException as e:
        job["state"], job["error"], job["finished_at"] = "error", f"batch busy: {e.detail}", _now()
        return
    try:
        # gate@1 auto-approve (idempotent: a re-run finds it already approved). The swallow is
        # STATUS-AWARE (#168/#198 review): approve_batch raises BatchLocked for ANY non-draft status, so
        # only carry on when the batch is genuinely already 'approved'. A terminal 'abandoned' (or a
        # stray 'reserving' placeholder, or a vanished batch) must HALT the chain, not silently run —
        # its schools are excluded from the attempted-set, so running it would re-queue them (#162).
        try:
            with gdb.session_scope() as con:
                BSTORE.approve_batch(con, batch_id, actor)
                included = [(d.district_id, d.name, d.state) for d in con.scalars(
                    select(BatchDistrict).where(BatchDistrict.batch_id == batch_id,
                                                BatchDistrict.included.is_(True)))]
            _record_gate1(included, event_type="approved", actor=actor,
                          note=f"gate@1 auto-approved (follow-up autoflow) {batch_id}")
        except BSTORE.BatchLocked:
            with gdb.session_scope() as con:
                b = con.get(Batch, batch_id)     # expire_on_commit=False → status readable after close
            if not b or b.status != "approved":
                job["state"], job["error"], job["finished_at"] = (
                    "error", f"{batch_id} is {b.status if b else 'missing'}; not runnable via autoflow", _now())
                return
            # else: genuinely already approved (idempotent re-run) — carry on into the stage chain
        job["stages"]["gate1"] = "approved"

        # One DB resolve for the whole chain (#526): the batch is approved (locked against gate@1
        # edits), so its working-store content is stable across the stage runs.
        batch = _batch_from_db(batch_id)

        job["stage"] = "discover"                 # Stage 2
        def _w2(district, residual, domain):
            return H2._wave2_claude(district, residual, domain, _run=_tracked_run)
        s2 = H2.run_batch(batch, actor=actor, wave2_runner=_w2)
        job["stages"]["discover"] = (s2 or {}).get("summary", s2)

        job["stage"] = "capture"                  # Stage 3
        s3 = H3.run_batch(batch, actor=actor, _run=_tracked_run)
        job["stages"]["capture"] = (s3 or {}).get("summary", s3)

        # Stage 4 + the Stage-5 ingest as ONE operation (#235: autoflow used to stop after run_batch
        # without ever ingesting — the batch_00014-00017 silent failure; the shared helper makes the
        # hand-off impossible to forget at any call site). Events use the same {kind: ...} shape as
        # every other job-event bucket in this file.
        job["stage"] = "process"                  # Stage 4 (+ filter ingest)
        def _ev(kind, p):
            job["stages"].setdefault("events", []).append({"kind": kind, **p})
        s4 = run_stage4_with_ingest(batch, actor=actor, on_event=_ev)
        job["stages"]["process"] = (s4 or {}).get("summary", s4)

        job["stage"], job["state"] = "gate@5", "done"     # landed at the review gate — STOP
    except SystemExit as e:
        job["state"], job["error"] = "halted", f"CONTROL FAILURE at {job['stage']}: {e}"
    except Exception as e:  # noqa: BLE001
        job["state"], job["error"] = "error", f"{type(e).__name__} at {job['stage']}: {e}"
    finally:
        lock.release()
        job["finished_at"] = _now()


@app.post("/api/extract/compose-followup/preview")
async def extract_compose_followup_preview(payload: dict):
    """#154 modal: a DRY-RUN of compose — what the follow-up batch WOULD contain (districts, target
    bands + query strategy, seed URLs) and what's spilled/blocked/deferred/benchmark-excluded — with
    NO create_batch and NO directive flip. Lets the operator review before committing in-place."""
    try:
        return EX.compose_followup_batch(
            year=payload.get("year", "2024_25"), actor=payload.get("actor", "ian"),
            handoff_hash=payload.get("handoff_hash"), cap=int(payload.get("cap", 12)), dry_run=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"compose preview failed: {type(e).__name__}: {e}")


@app.post("/api/extract/compose-followup")
async def extract_compose_followup(payload: dict):
    """REQ-118 execution (7→2/7→3/7→1): sweep APPROVED NEW-work directives into ONE targeted DRAFT
    Stage-1 follow-up batch, flipping those directives to 'executed'. Then (#157, unless
    `autoflow=false`) AUTO-FLOW it: gate@1 auto-pass + Stages 2→3→4 in the background, stopping at
    gate@5 — a follow-up carries an already-approved gate@7 decision, so the downstream gates don't
    re-ask. Scope to one run with `handoff_hash`, else all approved NEW-work."""
    try:
        out = EX.compose_followup_batch(
            year=payload.get("year", "2024_25"), actor=payload.get("actor", "ian"),
            handoff_hash=payload.get("handoff_hash"), cap=int(payload.get("cap", 12)))
    except Exception as e:  # noqa: BLE001 — surface the failure to the operator, don't 500 opaquely
        raise HTTPException(400, f"compose-followup failed: {type(e).__name__}: {e}")
    if out.get("batch_id") and payload.get("autoflow", True):
        threading.Thread(target=_autoflow_followup, args=(out["batch_id"], payload.get("actor", "ian")),
                         name=f"autoflow-{out['batch_id']}", daemon=True).start()
        out["autoflow_started"] = True
    return out


@app.post("/api/extract/execute/{request_id}")
async def extract_execute(request_id: int, payload: dict):
    """REQ-118 execution (7→6): fire an APPROVED alternate-rep directive — bundling its whole
    district's approved 7→6s into ONE immutable Stage-6 dispatch = one round (#153), of the
    yield-ranked alternate reps (no new capture; bypasses Stage 1/5), so it re-enters Stage 7 via the
    normal extract path. Depth-guarded by ROUNDS (REQ-051 max_request_rounds). Returns the new
    handoff_hash + n_bundled/swept/skipped; the paid re-extraction is a subsequent Stage-7 run."""
    payload = payload or {}
    try:
        out = EX.execute_alternate_dispatch(request_id, actor=payload.get("actor", "ian"))
    except FileExistsError:
        raise HTTPException(409, "an identical alternate dispatch was just created — the prior one stands")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"execute failed: {type(e).__name__}: {e}")
    if not out.get("ok"):
        raise HTTPException(409, out.get("reason", "execution refused"))
    return out


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


if __name__ == "__main__":
    import uvicorn
    # The governance Postgres must be reachable AND ingested (run build_signals.py). Fail fast with
    # a clear hint rather than 500ing on the first request.
    try:
        with gdb.session_scope() as con:
            con.execute(text("SELECT 1 FROM record LIMIT 1"))
    except Exception as e:
        raise SystemExit(f"governance DB not reachable/ingested ({type(e).__name__}: {e}) — "
                         f"start Docker (lct_postgres) and run build_signals.py first.")
    uvicorn.run(app, host="127.0.0.1", port=8005)
