"""REQ-164 Phase 4 — backfill legacy unstamped per-district receipts to the always-stamped convention.

Stages 4/5 historically wrote a FIXED-name per-district file (``processed.json`` / ``filtered.json``)
into ``lea-website-captures/<did>_<slug>/``. REQ-164 makes those ALWAYS datetime-stamped audit receipts
(``<basename>.<fs_stamp>.<writer>-<h8>.json`` via ``common/receipts.py``). This one-time script renames
each surviving legacy file in place to the stamped convention so already-processed districts match the
new naming — the writers themselves are converted in the companion change (Phase 3).

Scope: ``filtered`` (stage 5) ONLY — the one Phase-3 conversion whose writer + readers actually moved to
the stamped convention. ``processed.json`` (stage 4), ``discovery.json`` / ``candidates.json`` (stage 2)
stay FIXED handoffs: their EXISTENCE is a stage-done marker still read by fixed name, so they must NOT be
renamed until the deferred done-marker->gov_db inversion converts them (then this script grows to cover
them). ``captures.json`` is a fixed Node handoff and is never touched.

Timestamp source, in order (REQ-164: NEVER the filesystem create-date, which the external-drive migration
resets):
  1. gov_db ``state_event.created_at`` for the matching (district, stage) — the authoritative source.
  2. the ``district_status.json`` twin's history entry ``at`` for that stage — the offline equivalent.
  3. the file's ``st_mtime`` — last resort for an orphan with no gov_db/twin record, LOGGED at ``[warn]``.

Benchmark districts (``batch_type='benchmark'`` membership — batch_00000) get the basename suffixed
``_benchmark`` (e.g. ``processed_benchmark``), so the ``.``-anchored ``latest_receipt`` glob keeps them
invisible to a production ``latest_receipt(did,name,"processed")`` and self-evidently benchmark on disk.

Idempotent: a (dir, basename) that already has a stamped receipt is skipped. Requires the gov_db to be up
(Docker) for benchmark detection + the primary timestamp source; run ``--dry-run`` first.

Lives in the acquisition tree (not infrastructure/scripts/) because it imports the pipeline's
``common`` layer — infrastructure.scripts is forbidden from importing infrastructure.acquisition
(the import-linter layering contract).

Usage: ``python3 -m infrastructure.acquisition.maintenance.backfill_receipts [--dry-run] [--root <root>]``
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import receipts as RCPT
from infrastructure.acquisition.common import timeutil as TU

# Legacy fixed-name artifact stem -> (stage whose state_event dates it, target stamped basename).
# The target basename follows the unified `stage<N>_<stage_name>` convention (2026-07-23), so the legacy
# filename and the receipt basename deliberately DIFFER: filtered.json -> stage5_filter.<stamp>...
# Only Stage 5 is here — processed/discovery/candidates/captures still have their EXISTENCE read as a
# stage-done marker by fixed name, so renaming them would break reconcile (epic #617 converts them, and
# then they join this map as stage2_discover / stage2_candidates / stage3_capture / stage4_process).
LEGACY = {"filtered": (5, "stage5_filter")}


@dataclass
class Rename:
    old: Path
    new: Path
    basename: str          # the tagged target basename (may end in _benchmark)
    source: str            # which timestamp source won: state_event | district_status | mtime


def load_benchmark_ids(session) -> set:
    """District ids belonging to any batch_type='benchmark' batch (batch_00000 + any future benchmark
    batch). Thin alias over `common/benchmark.py` — THE definition since epic #617 consolidated the
    copies. Keys on batch_type, never the batch_00000 literal, so the tagging keeps working as the
    yardstick grows into new benchmark batches."""
    return BM.all_benchmark_district_ids(session)


def _stamp_from_state_event(session, district_id: str, stage: int) -> Optional[str]:
    """The latest state_event.created_at for (district, stage) as an fs_stamp, or None. The live file
    reflects the newest write, so the newest event dates it; event_id breaks a same-second tie."""
    if session is None:
        return None
    row = session.execute(text(
        "SELECT created_at FROM state_event WHERE district_id = :d AND stage = :s "
        "ORDER BY event_id DESC LIMIT 1"), {"d": district_id, "s": stage}).first()
    if not row or not row[0]:
        return None
    try:
        return TU.fs_stamp_from_iso(row[0])
    except ValueError:
        return None


def _stamp_from_status(status_doc: dict, district_id: str, stage: int) -> Optional[str]:
    """The latest district_status.json history entry for (district, stage) as an fs_stamp, or None."""
    d = (status_doc or {}).get("districts", {}).get(district_id)
    if not d:
        return None
    at = None
    for h in d.get("history", []):          # oldest -> newest; keep the last matching stage
        if h.get("stage") == stage and h.get("at"):
            at = h["at"]
    if not at:
        return None
    try:
        return TU.fs_stamp_from_iso(at)
    except ValueError:
        return None


def resolve_stamp(session, status_doc: dict, district_id: str, stage: int,
                  legacy: Path) -> tuple[str, str]:
    """(fs_stamp, source) for a legacy file, walking the fallback chain. mtime is last-resort."""
    s = _stamp_from_state_event(session, district_id, stage)
    if s:
        return s, "state_event"
    s = _stamp_from_status(status_doc, district_id, stage)
    if s:
        return s, "district_status"
    return TU.fs_stamp_from_epoch(legacy.stat().st_mtime), "mtime"


def _already_backfilled(ddir: Path, basename: str) -> bool:
    """True if a stamped receipt for this basename already exists (idempotency). Anchors on the
    ``.py-`` writer/hash segment so a legacy aside copy (``processed.<ts>.json``, no writer tag) does
    NOT count as already-done."""
    return any(p.name.startswith(f"{basename}.") and ".py-" in p.name
               for p in ddir.glob(f"{basename}.*.json"))


def plan_renames(root: Path, benchmark_ids: set, session, status_doc: dict) -> list[Rename]:
    """Every legacy processed/filtered file under `root`, with its computed stamped target."""
    plans: list[Rename] = []
    if not root.is_dir():
        return plans
    for ddir in sorted(p for p in root.iterdir() if p.is_dir() and "_" in p.name):
        district_id = ddir.name.split("_", 1)[0]
        is_bm = district_id in benchmark_ids
        for legacy_stem, (stage, basename) in LEGACY.items():
            legacy = ddir / f"{legacy_stem}.json"
            if not legacy.exists():
                continue
            target_base = f"{basename}_benchmark" if is_bm else basename
            if _already_backfilled(ddir, target_base):
                continue
            try:
                payload = json.loads(legacy.read_text())
            except (OSError, json.JSONDecodeError) as e:
                print(f"[warn] {legacy}: unreadable, skipped ({type(e).__name__}: {e})")
                continue
            stamp, source = resolve_stamp(session, status_doc, district_id, stage, legacy)
            new_name = RCPT.receipt_filename(target_base, payload, ts=stamp, writer="py")
            new_path = ddir / new_name
            if new_path.exists():        # a same-stamp same-content receipt already there — idempotent
                continue
            plans.append(Rename(legacy, new_path, target_base, source))
    return plans


def run(root: Optional[Path] = None, *, dry_run: bool = False, session=None,
        status_doc: Optional[dict] = None, benchmark_ids: Optional[set] = None) -> list[Rename]:
    """Backfill under `root` (default RAW_CAPTURES). Opens its own gov_db session only when it must load
    `benchmark_ids` from the DB; tests inject `benchmark_ids` + `status_doc` to run fully DB-free.
    Returns the list of (planned or applied) renames."""
    root = Path(root) if root else paths.RAW_CAPTURES
    owns_session = benchmark_ids is None and session is None
    if owns_session:
        cm = gdb.session_scope()
        session = cm.__enter__()
    try:
        if benchmark_ids is None:
            benchmark_ids = load_benchmark_ids(session)
        if status_doc is None:
            status_doc = _load_status_doc()
        plans = plan_renames(root, benchmark_ids, session, status_doc)
    finally:
        if owns_session:
            cm.__exit__(None, None, None)

    mtime_orphans = [p for p in plans if p.source == "mtime"]
    for p in plans:
        arrow = "would rename" if dry_run else "renamed"
        print(f"[{arrow}] {p.old.name} -> {p.new.name}  ({p.source})")
        if not dry_run:
            p.old.rename(p.new)
    if mtime_orphans:
        print(f"[warn] {len(mtime_orphans)} file(s) dated from st_mtime (no gov_db/twin record): "
              + ", ".join(str(p.old) for p in mtime_orphans))
    print(f"{'DRY RUN — ' if dry_run else ''}{len(plans)} receipt(s) "
          f"{'to backfill' if dry_run else 'backfilled'}.")
    return plans


def _load_status_doc() -> dict:
    """The district_status.json twin (offline timestamp fallback), or {} if absent/unreadable."""
    try:
        return json.loads(paths.STATUS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill legacy unstamped Stage-5 filtered receipts (REQ-164).")
    ap.add_argument("--dry-run", action="store_true", help="print planned renames, mutate nothing")
    ap.add_argument("--root", type=Path, default=None,
                    help="captures root (default: RAW_CAPTURES)")
    args = ap.parse_args()
    run(args.root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
