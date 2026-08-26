"""Stage 3 (Capture) batch runner -- the console's orchestration + observability entry.

Stage 3 is UNGATED: the console surfaces it as STATUS/observability (a health / emergent readout) plus a
run trigger. This mirrors the Stage 2 headless runner exactly -- Python orchestrates (reconcile
filesystem-authoritative, SEQUENTIAL per-district so there is one registry writer, events for the job
feed), and a SUBPROCESS does the risky/external work. Here that subprocess is the Node Playwright capture
(`capture_discovery.mjs district <ROOT> <district_dir>`), one fresh process per district -- batch-scoped,
so a run never re-captures the rest of RAW_DIR.

After each district's captures.json lands, `capture_stage3.finish_district` records the state_event AND
projects the capture receipts into the live DB cache (common/cache_ingest) -- which is what the console
reads. The DB is the working store; captures.json on disk is the regenerable, authoritative source.

Driven by `run_batch()` (the console's POST /api/capture/{batch_id}/run trigger) or as a CLI:
  python3 -m infrastructure.acquisition.stage3_capture.headless run <batch_id|path>
"""
import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import batch_types as BT
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage3_capture import capture_stage3 as C3

RAW_DIR = paths.RAW_CAPTURES
CAPTURE_MJS = paths.REPO_ROOT / "infrastructure" / "scraper" / "capture_discovery.mjs"
CAPTURE_DEADLINE_S = 600   # the Node-owns-shutdown budget passed to the capture: once it passes, Node
                           # stops pulling new pages, records the rest `not_attempted`, and writes a
                           # PARTIAL captures.json (captured_partial) instead of being killed with its
                           # work orphaned. A large district (LAS CRUCES, 128 candidates) captures what
                           # fits and cleanly reports the remainder, retriable later.
DRAIN_BUFFER_S = 240       # headroom for in-flight pages to finish + the manifest write after the
                           # deadline (each page is bounded by the per-op timeouts: goto 15 (#225,
                           # GOTO_WAIT in capture_discovery.mjs) / fetch 20 / screenshot+pdf 45 each).
                           # The Python subprocess timeout is the BACKSTOP —
                           # it only fires if Node itself hangs; then reconstruct-from-disk recovers it.
CAPTURE_TIMEOUT_S = CAPTURE_DEADLINE_S + DRAIN_BUFFER_S   # subprocess backstop (> Node's own deadline)
CONCURRENCY = 5            # within-district page concurrency passed to the Node script


def load_batch_any(batch_ref: str) -> dict:
    """Accept either a batch receipt path or a bare batch_id (resolved under paths.QUEUE_DIR)."""
    p = Path(batch_ref)
    if not p.exists():
        p = paths.QUEUE_DIR / (batch_ref if batch_ref.endswith(".json") else f"{batch_ref}.json")
    if not p.exists():
        raise SystemExit(f"batch not found: {batch_ref} (looked at {p})")
    return json.loads(p.read_text())


def find_batch_districts(batch: dict) -> list:
    """The batch's districts that are READY for capture -- i.e. on disk with discovery.json +
    candidates.json (C3.find_districts builds the dir + header fields from disk). Districts still
    awaiting Stage 2 naturally drop out here (and show as `awaiting_discovery` in status)."""
    ids = {d["district_id"] for d in batch["districts"]}
    return [d for d in C3.find_districts(RAW_DIR) if d["district_id"] in ids]


def candidate_count(ddir: Path) -> int:
    """Number of capture-plan URLs in a district's candidates.json (0 if empty/absent/unreadable).
    Zero == Stage 2 found no links (district_outcome `manual_flag_all`) == nothing for Playwright to
    capture. The authoritative pre-capture signal: a no-link district is terminal at Stage 2 and is
    never dispatched (we know it has no links before sending it into the process)."""
    cf = ddir / "candidates.json"
    try:
        return len(json.loads(cf.read_text()).get("candidates", []))
    except (json.JSONDecodeError, OSError, AttributeError, TypeError):
        return 0


def _plan_sha256(ddir: Path) -> str:
    """The capture-plan fingerprint (#116 review): sha256 over the SORTED UNIQUE fragment-stripped
    candidate URLs — the Python mirror of the mjs planSha256. Passed to the retryable-only Node
    run, which recomputes over its OWN read and aborts on mismatch: a district can sit in two
    batches at once (follow-ups re-include by design) with only per-batch run locks, so a
    concurrent Stage-2 candidates.json rewrite between retry selection and the Node read is
    reachable and must fail loudly, never silently conflate two plans in one manifest."""
    cands = json.loads((ddir / "candidates.json").read_text()).get("candidates", [])
    urls = sorted({C3._strip_fragment(c["url"]) for c in cands
                   if isinstance(c, dict) and isinstance(c.get("url"), str)})
    return hashlib.sha256("\n".join(urls).encode()).hexdigest()


class CaptureTimeout(RuntimeError):
    """A backstop timeout that the artifact did NOT redeem — i.e. a real timeout over unfinished
    work. Distinct from the bare `subprocess.TimeoutExpired` because #916 means that exception no
    longer decides anything on its own: it is caught, the manifest is consulted, and only an
    unredeemed timeout is re-raised as this."""


# The district-status note is built as f"{type(e).__name__}: …", so `timed_out` is recognized by
# exception NAME. Both names must be listed: `TimeoutExpired` for events written before #916 (the
# historical rows still in gov_db) and `CaptureTimeout` for the ones written since. ONE home for the
# rule (REQ-182) — the first draft of the #916 fix left the inline `note.startswith("TimeoutExpired")`
# at status_for_batch and silently reclassified every genuine timeout as a plain `failed`.
_TIMEOUT_NOTE_PREFIXES = ("TimeoutExpired", "CaptureTimeout")


def is_timeout_note(note: str) -> bool:
    """True when a capture failure note describes a backstop timeout (vs. any other error)."""
    return (note or "").startswith(_TIMEOUT_NOTE_PREFIXES)


def _stream_to_text(stream) -> str:
    """Normalize a subprocess output stream to str. Needed because `subprocess.run` populates
    `TimeoutExpired.stdout` as **bytes even under `text=True`** (the decoding happens in the normal
    return path, which a timeout never reaches) and as None when nothing was captured. Handing bytes
    to `_capture_summary_from_stdout` would silently never match — a CAPTURE_SUMMARY that IS there
    read as absent, i.e. #916 all over again one layer down."""
    if stream is None:
        return ""
    return stream.decode("utf-8", "replace") if isinstance(stream, bytes) else stream


def _capture_summary_from_stdout(stdout: str, dir_name: str) -> dict | None:
    """Parse the district's CAPTURE_SUMMARY line from the Node run's stdout — the subprocess return
    channel (#670). One line per district, tagged, JSON payload; a multi-district run prints several,
    so match on the `dir` field. None when absent (the caller decides that's an error)."""
    for line in reversed((stdout or "").splitlines()):
        if line.startswith("CAPTURE_SUMMARY "):
            try:
                s = json.loads(line[len("CAPTURE_SUMMARY "):])
            except json.JSONDecodeError:
                continue
            if s.get("dir") == dir_name:
                return s
    return None


def _capture_one(district: dict, *, retryable_only: bool = False, plan_sha: str = None,
                 _run=subprocess.run) -> dict:
    """Run the Node Playwright capture for ONE district dir (a fresh subprocess). Raises on a non-zero
    exit or a missing captures.json, so run_batch records the district `failed` rather than silently
    advancing it. `retryable_only` (#116): the Node run seeds from the prior manifest and re-attempts
    ONLY retryable failures (see RETRYABLE_ERR_PREFIXES); `plan_sha` rides along so Node can verify
    the plan hasn't been rewritten since selection (_plan_sha256).

    Returns the CAPTURE_SUMMARY dict (#670) after cross-checking it against the manifest: Node emits
    the summary only after a successful manifest write, so a missing line, or a records count that
    disagrees with the manifest as read now, means the run was killed or truncated mid-write — a LOUD
    failure (raise -> `failed` state_event), never an inference from artifact existence. The summary
    is stamped onto the stage-3 outcome event so completeness is a gov_db fact."""
    cmd = ["node", str(CAPTURE_MJS), "district", str(RAW_DIR), district["dir"].name,
           str(CONCURRENCY), str(CAPTURE_DEADLINE_S)]   # Node owns its deadline; the subprocess timeout is a backstop
    if retryable_only:
        cmd.append("retryable-only")
        if plan_sha:
            cmd.append(f"plan-sha256={plan_sha}")
    # #916: the Python timeout is a BACKSTOP over a deadline Node owns (CAPTURE_DEADLINE_S). It can
    # fire LATE -- after Node has written captures.json and printed its summary -- and `TimeoutExpired`
    # is raised by the call itself, so every check below used to be skipped and a COMPLETE capture was
    # recorded `failed` (ORANGE `1201440`, batch_00044: 416 records, all ok=true, logged as a timeout).
    # A false `failed` is not merely cosmetic: it leaves the district `awaiting_capture` with
    # `retriable == 0`, so stage4.js offers a note instead of a Run control and the only way forward is
    # a RE-CAPTURE -- the redo path, which seeds from the prior manifest (#174). A first-run district
    # silently becomes a redo district.
    #
    # So the timeout does not decide the outcome; the ARTIFACT does. Both paths converge on the same
    # three checks below. What the timeout path drops is only the returncode check -- a killed process
    # has no meaningful exit status -- and that is the weakest of the four anyway: #670 established
    # that the manifest + summary + count agreement are what prove completeness. A timeout over
    # incomplete work still fails loudly on exactly those checks.
    backstop_timeout = False
    try:
        proc = _run(cmd, capture_output=True, text=True, timeout=CAPTURE_TIMEOUT_S,
                    cwd=str(paths.REPO_ROOT))
    except subprocess.TimeoutExpired as e:
        backstop_timeout = True
        stdout = _stream_to_text(e.stdout)
    else:
        if proc.returncode != 0:
            raise RuntimeError(f"node capture exit {proc.returncode}: "
                               f"{(proc.stderr or proc.stdout)[:300]}")
        stdout = proc.stdout
    if not (district["dir"] / "captures.json").exists():
        if backstop_timeout:
            raise CaptureTimeout(
                f"node capture timed out after {CAPTURE_TIMEOUT_S}s and wrote no captures.json")
        raise RuntimeError("node capture finished but wrote no captures.json")
    summary = _capture_summary_from_stdout(stdout, district["dir"].name)
    if summary is None:
        raise RuntimeError("node capture wrote captures.json but printed no CAPTURE_SUMMARY line "
                           "(killed or crashed between the manifest write and the summary)")
    n_manifest = len(json.loads((district["dir"] / "captures.json").read_text()))
    if summary.get("n_records") != n_manifest:
        raise RuntimeError(f"capture summary/manifest mismatch for {district['district_id']}: "
                           f"summary n_records={summary.get('n_records')} vs manifest {n_manifest} "
                           f"(truncated or concurrently rewritten)")
    if backstop_timeout:
        # Accepting the work must NOT erase that the backstop fired (#792: a fix that removes a
        # failure's VISIBILITY instead of the failure). The flag rides the summary onto the
        # completion event (fingerprints_json.capture_summary), so "this district only just made it"
        # stays a queryable gov_db fact and a rising rate is detectable rather than silent.
        summary["backstop_timeout"] = True
    return summary


# ----------------------------------------------------------------- status / observability (reads the DB)
def status_for_batch(batch: dict) -> dict:
    """Read-only Stage-3 observability for a batch, FROM THE DB cross-stage cache (the working store the
    Stage-3 finish hook keeps fresh). Per district, one of four states:
      - `awaiting_discovery` — no discovery yet (no candidates.json on disk)
      - `manual_flag_all`    — discovered but ZERO links (terminal at Stage 2; never captured) — the
                               SAME label Stage 2 uses, sourced from the candidate count, NOT a Stage-3
                               artifact (so it's correct even for the empty-capture districts the old
                               pre-skip runs left behind)
      - `todo`               — has links, not captured yet
      - `done`               — captured; outcome + counts (ok/failed/emergent) + the err breakdown
    Batch-level: a rollup + the CMS/host distribution (governance §11f). SELF-HEALING like Stage 2: a
    captured district whose rows aren't in the cache yet (pre-hook / DB-down run) is ingested on view."""
    ids = [d["district_id"] for d in batch["districts"]]
    ondisk = {d["district_id"]: d for d in C3.find_districts(RAW_DIR)}   # id -> {dir, name, ...}
    cand_n = {did: candidate_count(dk["dir"]) for did, dk in ondisk.items()}
    # A REDO BATCH IS BATCH-SCOPED (#647). `captures.json` existing means "this district has been
    # captured at some point" — the right question for an ordinary batch, the WRONG one for a batch
    # whose purpose is re-capturing districts that already hold artifacts: every district read `done`,
    # the rollup read `todo: 0`, and stage3.js disables the Run control (`retriable > 0`), so the redo
    # could not be started — while `reconcile(redo=True)` would have processed every one of them.
    # Ordinary batches keep the disk rule byte-for-byte.
    #
    # ONE variable feeds BOTH the per-district status loop below and `done_ids`. They are the same
    # question and must never be able to disagree: the first draft of this fix re-keyed only
    # `done_ids` and the loop kept reading the disk set, so the status did not move at all.
    #
    # #671: the scoping helper asks for a stage OUTCOME after this batch's dispatch, not merely the
    # dispatch. Dispatch is stamped for the whole todo list up front, so the dispatch-only rule read
    # `done` — with the PRIOR run's capture counts — from t=0 of a redo until the district's own work
    # finished. Because non-`done` districts take the zeroed row defaults below, correcting the
    # predicate also stops the stale metrics rendering as current; there is no second fix for that.
    captured = {did for did, dk in ondisk.items() if (dk["dir"] / "captures.json").exists()}
    if BT.redoes_attempted(batch):
        captured &= DS.completed_by_batch(batch["batch_id"], "capture", ids)

    # Capture FAILURES (timeout / Node crash) write a `failed` capture event with no stage number --
    # so without this they read as `todo`, indistinguishable from "not attempted" (the Brookwood bug:
    # the failure showed only in the run log). Surface the latest capture event per district; if it's
    # `failed`, the district is `failed`, not `todo` — and not `done` either:
    #
    # This comment used to assert that a failure "leaves NO captures.json". #670 disproved it: a LATE
    # timeout kills the subprocess after it has already written one (Orange County FL `1201440`, 119
    # ok=true records + a TimeoutExpired event), and artifact-existence then outranked the failure so
    # the district rendered a clean `done`. The rule is now a VETO on every batch type: a district
    # whose latest capture event is `failed` is subtracted from `captured`, so the gov_db failure
    # outranks the artifact (epic #723's frame — the DB is the working store, disk is evidence).
    # Strictly-withdrawing: the no-events case keeps the disk rule byte-for-byte, protecting the
    # historical corpus whose completion events predate the stamps from reverting to `todo`
    # (re-paying for capture). #622's full done-marker inversion inherits the pinned falsifier
    # (test_670_failed_latest_event_vetoes_disk_done_on_an_ordinary_batch).
    failed_caps: dict = {}
    with gdb.session_scope() as con:
        CI.ensure_cache_schema(con)
        for r in con.execute(text(
                """SELECT DISTINCT ON (district_id) district_id, event_type, note
                   FROM state_event WHERE stage_name = 'capture' AND district_id = ANY(:ids)
                   ORDER BY district_id, event_id DESC"""), {"ids": ids or [""]}).mappings():
            if r["event_type"] == "failed":
                failed_caps[r["district_id"]] = r["note"]
    captured -= set(failed_caps)
    # `done` = discovered, HAD links, and captured. (No-link districts never capture -> manual_flag_all.)
    done_ids = [d["district_id"] for d in batch["districts"]
                if d["district_id"] in captured and cand_n.get(d["district_id"], 0) > 0]

    with gdb.session_scope() as con:
        cached_ids = {r[0] for r in con.execute(text(
            "SELECT DISTINCT district_id FROM capture WHERE district_id = ANY(:ids)"),
            {"ids": done_ids or [""]})}
    for did in done_ids:                     # self-heal: ingest captures the cache is missing
        if did not in cached_ids:
            CI.cache_capture(ondisk[did]["dir"], did)

    rows_by_did: dict = {}
    with gdb.session_scope() as con:
        for r in con.execute(text(
                """SELECT district_id, ok, source, err, final_host, fingerprint_json
                   FROM capture WHERE district_id = ANY(:ids)"""), {"ids": done_ids or [""]}).mappings():
            rows_by_did.setdefault(r["district_id"], []).append(dict(r))

    districts, hosts, cmss = [], Counter(), Counter()
    for d in batch["districts"]:
        did = d["district_id"]
        row = {"district_id": did, "name": d["name"], "state": d.get("state", ""),
               "domain": d.get("domain", ""), "outcome": None, "n_captures": 0, "n_ok": 0,
               "n_failed": 0, "n_emergent": 0, "errs": {}}
        if did not in ondisk:
            districts.append({**row, "status": "awaiting_discovery"})
            continue
        if cand_n.get(did, 0) == 0:          # discovered, no links -> terminal manual_flag_all
            districts.append({**row, "status": "manual_flag_all", "outcome": "manual_flag_all"})
            continue
        if did not in captured:
            if did in failed_caps:           # capture errored/timed out -> failed (retriable), not todo
                note = failed_caps[did] or ""
                st = "timed_out" if is_timeout_note(note) else "failed"
                districts.append({**row, "status": st, "outcome": st, "error": note[:300]})
            else:
                districts.append({**row, "status": "todo"})
            continue
        caps = rows_by_did.get(did, [])
        n_ok = sum(1 for c in caps if c["ok"])
        n_failed = sum(1 for c in caps if not c["ok"])
        errs = Counter(c["err"] or "unknown" for c in caps if not c["ok"])
        for c in caps:
            if c["ok"] and c["final_host"]:
                hosts[c["final_host"]] += 1
                try:
                    hint = (json.loads(c["fingerprint_json"]) or {}).get("cms_hint")
                except (json.JSONDecodeError, TypeError):
                    hint = None
                if hint:
                    cmss[hint] += 1
        outcome = ("captured_all" if n_failed == 0 else
                   "capture_failed_all" if n_ok == 0 else "captured_partial")
        districts.append({**row, "status": "done", "outcome": outcome, "n_captures": len(caps),
                          "n_ok": n_ok, "n_failed": n_failed,
                          "n_emergent": sum(1 for c in caps if c["source"] == "emergent"),
                          "errs": dict(errs)})

    return {"districts": districts, "rollup": _rollup(districts),
            "hosts": hosts.most_common(), "cms": cmss.most_common()}


# District-level capture failures (retriable, NOT resolved): a generic error or a timeout. Both count
# as `failed` in the rollup; the per-district status distinguishes `timed_out` for the UI.
FAILED_STATUSES = ("failed", "timed_out")


def _rollup(districts: list) -> dict:
    done = [d for d in districts if d["status"] == "done"]
    flagged = sum(1 for d in districts if d["status"] == "manual_flag_all")
    total = len(districts)
    return {
        "total": total,
        "done": len(done),
        "manual_flag_all": flagged,
        "todo": sum(1 for d in districts if d["status"] == "todo"),
        # district-level capture failures (timeout / crash) — retriable; NOT counted as resolved
        "failed": sum(1 for d in districts if d["status"] in FAILED_STATUSES),
        "awaiting_discovery": sum(1 for d in districts if d["status"] == "awaiting_discovery"),
        # resolved = captured OR terminally flagged; the batch's Stage-3 is complete when resolved==total
        "resolved": len(done) + flagged,
        "captured_all": sum(1 for d in done if d["outcome"] == "captured_all"),
        "captured_partial": sum(1 for d in done if d["outcome"] == "captured_partial"),
        "capture_failed_all": sum(1 for d in done if d["outcome"] == "capture_failed_all"),
        "n_captures": sum(d["n_captures"] for d in done),
        "n_failed": sum(d["n_failed"] for d in done),
        "n_emergent": sum(d["n_emergent"] for d in done),
    }


# ----------------------------------------------------------------------------------- the batch run
def run_batch(batch: dict, *, actor: str = "auto:stage3", on_event=None, _run=subprocess.run) -> dict:
    """Deterministic Stage 3 (Capture) for a batch: reconcile (filesystem is truth; a
    registry-ahead-of-disk CONTROL FAILURE raises SystemExit and halts), then per todo district run the
    Node capture subprocess -> capture_stage3.finish_district (state_event + DB cache upsert).
    SEQUENTIAL (one registry writer, no race). `on_event(kind, payload)` feeds the console job board.
    `_run` is injectable for tests (no live Node subprocess).

    `batch` is the resolved working-store dict ({batch_id, districts:[{district_id,name,state,...}]}) —
    the caller passes it from the DB (the console) or the receipt (the CLI), so the runner never reaches
    for the on-disk receipt itself."""
    batch_id = batch["batch_id"]
    with gdb.session_scope() as _con:      # #168: never run a stage on a terminal abandoned batch
        BG.assert_runnable(_con, batch_id)

    def emit(kind, **payload):
        if on_event:
            on_event(kind, {"batch_id": batch_id, **payload})

    # Per-district saves defer the district_status.json regeneration (export=False; issue #49) — one
    # explicit DS.export() at run end (in a finally, so a crash still exports the committed events).
    try:
        districts = find_batch_districts(batch)
        registry = DS.load()
        todo, skipped = C3.reconcile(districts, registry,
                                     redo=BT.redoes_attempted(batch))
        DS.save(registry, export=False)
        # Drop no-link districts (Stage 2 manual_flag_all -> empty candidates.json) BEFORE dispatch: they
        # have nothing for Playwright, are terminal at Stage 2, and get no Stage-3 artifact/event (they
        # surface as `manual_flag_all` in status, sourced from the discovery state). Cheap pre-capture skip
        # that matters at continuous-running scale.
        n_cands = {d["district_id"]: candidate_count(d["dir"]) for d in todo}   # one read per district (#454)
        no_link = [d for d in todo if n_cands[d["district_id"]] == 0]
        todo = [d for d in todo if n_cands[d["district_id"]] > 0]
        for d in no_link:
            emit("skipped_no_links", district_id=d["district_id"], name=d["name"])
        emit("reconciled", todo=[d["district_id"] for d in todo],
             skipped=[d["district_id"] for d in skipped], no_links=[d["district_id"] for d in no_link])
        if not todo:
            return {"batch_id": batch_id, "todo": 0, "skipped": len(skipped),
                    "no_links": len(no_link), "results": []}

        results = _dispatch_and_finish(todo, batch_id=batch_id, actor=actor, emit=emit, _run=_run)
        return {"batch_id": batch_id, "todo": len(todo), "skipped": len(skipped),
                "no_links": len(no_link), "results": results}
    finally:
        DS.export()   # one full district_status.json regeneration per run (issue #49)


def _dispatch_and_finish(todo: list, *, batch_id: str, actor: str, emit, _run,
                         retryable_only: bool = False, dispatch_notes: str = "") -> list:
    """The shared dispatch + capture + finish + error-isolation loop for run_batch AND retry_partial
    (#116 review: one copy, so a future fix to the loop can't silently apply to only one of them).
    SEQUENTIAL (one registry writer). A SystemExit is a CONTROL FAILURE and propagates."""
    registry = DS.load()
    for d in todo:
        DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage_name="capture",
                        event_type="dispatched", actor=actor, batch_id=batch_id, notes=dispatch_notes)
        emit("dispatched", district_id=d["district_id"], name=d["name"])
    DS.save(registry, export=False)

    results = []
    for d in todo:
        did = d["district_id"]
        try:
            summary = _capture_one(d, retryable_only=retryable_only, plan_sha=d.get("_plan_sha"), _run=_run)
            registry = DS.load()
            # batch_id stamps the stage=3 completion event (#647) — the dispatched/failed events
            # above always carried it; without it here "did THIS batch capture this district" is
            # unanswerable from gov_db, which is what forced the console onto the filesystem.
            # summary (#670) stamps intended-vs-achieved onto the same event.
            outcome = C3.finish_district(d, registry, batch_id, summary=summary)   # + upserts the DB cache
            DS.save(registry, export=False)
            results.append({"district_id": did, "name": d["name"], "outcome": outcome})
            emit("completed", district_id=did, name=d["name"], outcome=outcome)
        except SystemExit:
            raise   # CONTROL FAILURE -- never swallow
        except Exception as e:
            registry = DS.load()
            DS.record_stage(registry, did, d["name"], d["state"], stage_name="capture",
                            event_type="failed", actor=actor, batch_id=batch_id,
                            notes=f"{type(e).__name__}: {str(e)[:200]}")
            DS.save(registry, export=False)
            results.append({"district_id": did, "name": d["name"], "outcome": "error",
                            "error": f"{type(e).__name__}: {str(e)[:200]}"})
            emit("failed", district_id=did, name=d["name"], error=str(e)[:200])
    return results


# ----------------------------------------------------------------------------------- partial retry (#116)
# Python mirror of the mjs isRetryableErr predicate -- crash/deadline remnants only. NOT retryable:
# security_block (the one-attempt WAF rule, CLAUDE.md Critical Rule 3), needs_oauth_reauth (fails
# identically until Drive Tier 2 -- #115), binary_fetch_* (the origin already answered).
RETRYABLE_ERR_PREFIXES = ("not_attempted", "not_recovered")


def _retryable_failures(ddir: Path) -> int:
    """How many of a district's failed capture records a partial retry could actually re-attempt:
    ok=false, a retryable err class, AND the URL is still in the capture plan (candidates.json) --
    the Node delta re-run re-queues only planned URLs, so a failed EMERGENT record can't retry this
    way (its parent page is ok and won't re-render; that's #117's recovery territory, not this one's).
    Reads the on-disk manifest deliberately: Stage 3's own reconcile stance is filesystem-is-truth
    for its own artifacts, and this is the same file the Node run will seed from.

    RAISES on an unreadable/malformed manifest (review): swallowing it as `return 0` made a corrupt
    captures.json indistinguishable from "nothing to retry" — the silent-wedge state the #267
    corrupt-manifest convention exists to prevent. retry_partial catches per district and reports."""
    caps = json.loads((ddir / "captures.json").read_text())
    cand_urls = {C3._strip_fragment(c["url"])
                 for c in json.loads((ddir / "candidates.json").read_text()).get("candidates", [])
                 if isinstance(c, dict) and isinstance(c.get("url"), str)}
    return sum(1 for r in caps if isinstance(r, dict) and not r.get("ok")
               and str(r.get("err") or "").startswith(RETRYABLE_ERR_PREFIXES)
               and isinstance(r.get("url"), str) and C3._strip_fragment(r["url"]) in cand_urls)


def retry_partial(batch: dict, *, actor: str = "auto:stage3-retry", on_event=None,
                  _run=subprocess.run) -> dict:
    """#116: re-attempt the RETRYABLE failures of a batch's already-captured districts. Selects
    districts whose captures.json holds >=1 retryable planned-URL failure (not_attempted from a
    deadline truncation, not_recovered from a crash reconstruct) and re-runs the Node capture in
    retryable-only mode: prior ok records carry verbatim (never re-hit), retryable failures are
    dropped-and-re-attempted, and non-retryable failures (security_block / needs_oauth_reauth /
    binary_fetch_*) carry untouched -- the one-attempt rule holds. The union manifest lands via
    the same finish_district path as a first run (state_event + DB cache upsert), so the outcome
    honestly re-resolves (captured_partial -> captured_all when the retry clears the remainder)."""
    batch_id = batch["batch_id"]
    with gdb.session_scope() as _con:
        BG.assert_runnable(_con, batch_id)

    def emit(kind, **payload):
        if on_event:
            on_event(kind, {"batch_id": batch_id, **payload})

    try:
        districts = find_batch_districts(batch)
        todo, unreadable = [], []
        for d in districts:
            if not (d["dir"] / "captures.json").exists():
                continue
            try:
                n = _retryable_failures(d["dir"])
            except SystemExit:
                raise   # CONTROL FAILURE -- never swallow
            except Exception as e:
                # Loud, per-district (#267 convention: a corrupt manifest must never read as
                # "nothing to retry") — surfaced in the event stream AND the summary, district
                # skipped, the rest of the batch proceeds.
                err = f"{type(e).__name__}: {str(e)[:200]}"
                unreadable.append({"district_id": d["district_id"], "name": d["name"], "error": err})
                emit("retry_unreadable", district_id=d["district_id"], name=d["name"], error=err)
                continue
            if n > 0:
                # Fingerprint the plan we just selected against — the Node run re-verifies it
                # (plan-sha256 arg) so a concurrent Stage-2 rewrite can't silently invalidate
                # this selection between here and the subprocess's own read.
                d["_plan_sha"] = _plan_sha256(d["dir"])
                todo.append(d)
        emit("retry_reconciled", todo=[d["district_id"] for d in todo],
             unreadable=[u["district_id"] for u in unreadable])
        if not todo:
            return {"batch_id": batch_id, "todo": 0, "results": [], "unreadable": unreadable}
        results = _dispatch_and_finish(todo, batch_id=batch_id, actor=actor, emit=emit, _run=_run,
                                       retryable_only=True,
                                       dispatch_notes="partial retry (#116): retryable failures only")
        return {"batch_id": batch_id, "todo": len(todo), "results": results, "unreadable": unreadable}
    finally:
        DS.export()


def main():
    ap = argparse.ArgumentParser(description="Stage 3 (Capture) batch runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="capture an approved+discovered batch (per-district Node subprocess)")
    p.add_argument("batch", help="batch_id or path to batch_NNNNN.json receipt")
    p.add_argument("--actor", default="ian")
    pr = sub.add_parser("retry", help="#116: re-attempt retryable failures (not_attempted/not_recovered) "
                                      "of a batch's captured_partial districts; one-attempt errs carry")
    pr.add_argument("batch", help="batch_id or path to batch_NNNNN.json receipt")
    pr.add_argument("--actor", default="ian")
    a = ap.parse_args()
    if a.cmd == "run":
        batch = load_batch_any(a.batch)   # CLI loads the receipt; the console passes a DB-resolved dict
        summary = run_batch(batch, actor=a.actor,
                            on_event=lambda k, p: print(f"[{k}] " + json.dumps(p)))
        print(json.dumps(summary, indent=2))
    elif a.cmd == "retry":
        batch = load_batch_any(a.batch)
        summary = retry_partial(batch, actor=a.actor,
                                on_event=lambda k, p: print(f"[{k}] " + json.dumps(p)))
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
