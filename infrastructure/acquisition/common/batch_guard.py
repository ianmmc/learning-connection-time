"""Shared batch-runnability guard (#168 review).

The single validation boundary every pipeline-stage entry point passes through, so no entry point can
run a stage on a TERMINAL `abandoned` batch. The console's Stage-2 run endpoint already refuses a
non-approved batch, but the headless CLI runners (`python3 -m ...stageN.headless run <batch_id>`) load
the on-disk receipt — which carries no status — so without this they would happily run a retired batch,
recording discovery/state events for a batch whose schools are excluded from the attempted-set
(`stage7_execute._attempted_schools`) -> the #162 double-queue poison.

Lives in `common` because the stages are independent siblings under the import-linter layering contract
(they may not import each other), so a guard shared across stage2/3/4 must sit in the base layer. Raw
SQL by table name — no stage-module import (the contract is about imports, not table names; see
PIPELINE_GOVERNANCE_AND_STATE §10). Raising SystemExit matches the headless's existing hard-stop
convention (`load_batch_any` raises SystemExit for a missing batch); it halts the run loudly.

Two grains (#206 review — the batch-grain guard alone left the older per-district CLIs unguarded):
  assert_runnable(sess, batch_id)            — batch-grain: the headless run_batch runners + the Stage-2
                                               legacy CLI, which operate on a whole batch.
  assert_district_runnable(sess, district_dir) — district-grain: the Stage-3/4 legacy CLIs
                                               (finish / reconstruct / run) operate on one on-disk
                                               district dir with no batch argument; the dir's
                                               discovery.json records the batch that produced it, and
                                               that batch's terminality is what the work would violate.
"""
import json
from pathlib import Path

from sqlalchemy import text


def assert_runnable(sess, batch_id: str) -> None:
    """Halt (SystemExit) if `batch_id` is a terminal `abandoned` batch. No-op for any other status
    (including a batch this DB has never seen — a receipt-only dev batch stays runnable)."""
    status = sess.execute(
        text("SELECT status FROM batch WHERE batch_id = :b"), {"b": batch_id}).scalar()
    if status == "abandoned":
        raise SystemExit(
            f"batch {batch_id} is abandoned (terminal); refusing to run a pipeline stage on it")


def assert_district_runnable(sess, district_dir) -> None:
    """District-grain guard for the per-district CLI ops: the dir's discovery.json records the batch
    that produced this district's artifacts — refuse (SystemExit) if THAT batch is abandoned. A dir
    with no discovery.json / no batch_id makes no batch claim and stays runnable (pre-batch dev data)."""
    disc = Path(district_dir) / "discovery.json"
    if not disc.exists():
        return
    try:
        batch_id = json.loads(disc.read_text()).get("batch_id")
    except (OSError, ValueError):
        return                      # unreadable receipt is the reconcile checks' concern, not the guard's
    if batch_id:
        assert_runnable(sess, batch_id)
