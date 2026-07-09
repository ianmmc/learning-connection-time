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
"""
from sqlalchemy import text


def assert_runnable(sess, batch_id: str) -> None:
    """Halt (SystemExit) if `batch_id` is a terminal `abandoned` batch. No-op for any other status
    (including a batch this DB has never seen — a receipt-only dev batch stays runnable)."""
    status = sess.execute(
        text("SELECT status FROM batch WHERE batch_id = :b"), {"b": batch_id}).scalar()
    if status == "abandoned":
        raise SystemExit(
            f"batch {batch_id} is abandoned (terminal); refusing to run a pipeline stage on it")
