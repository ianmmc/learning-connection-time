"""Cross-stage per-district status registry for the acquisition pipeline (all 9 stages).

One JSON file, one entry per district that has ENTERED the pipeline (passed Stage 1's
pre-queue exclusion filters). Pre-queue exclusions (CTC, not-operating, grade-span gap)
are NOT recorded here -- they're live filters recomputed from is_shared_service_entity /
LEA_TYPE_TEXT / grade-span every run, never a frozen list (see ACQUISITION_PIPELINE.md
Stage 1). Keyed by district_id for O(1) lookup -- structure over scan-ability, since this
is process input read by every batch-build run, not primarily a human-read record.

already_attempted() only excludes a district once it has reached Stage 3 (Capture) --
a district merely queued (Stage 1) or searched (Stage 2) has had no real, costly attempt
yet and stays eligible for redraw (e.g. after a queue-time bug fix).

Schema reference: data/acquisition/status/district_status.example.json
Doc: docs/ACQUISITION_PIPELINE.md (Stage 1), docs/diagrams/acquisition_pipeline_flow.md
"""
from datetime import datetime, timezone
import json

from infrastructure.acquisition.common import paths  # noqa: E402  (single source of truth for runtime-state locations — REQ-087)

STATUS_FILE = paths.STATUS_FILE
SCHEMA_VERSION = 1

# Stage 3 = Capture is the first stage with a real, costly attempt (an actual fetch of a
# district/school page). Stage 1 (Queue) and Stage 2 (Discover) just target/search -- a
# district that only reached one of those has not actually been "tried" yet, so it must
# stay eligible for redraw (e.g. after a Stage 1 bug fix). Found 2026-06-22: re-running
# queue_batch.py after a school_sampling.py fix silently excluded every district from the
# prior (never-captured) batch_00001, masking the fix instead of demonstrating it.
ATTEMPTED_THRESHOLD_STAGE = 3


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict:
    if not STATUS_FILE.exists():
        return {"schema_version": SCHEMA_VERSION, "last_updated": None, "districts": {}}
    return json.loads(STATUS_FILE.read_text())


def save(registry: dict) -> None:
    registry["schema_version"] = SCHEMA_VERSION
    registry["last_updated"] = _now()
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(registry, indent=2))


def already_attempted(registry: dict, district_id: str) -> bool:
    """True only once a district has reached Stage 3 (Capture) or beyond -- Stage 1/2-only
    districts (queued or searched but never actually fetched) remain eligible for redraw."""
    d = registry["districts"].get(district_id)
    return d is not None and d.get("furthest_stage", 0) >= ATTEMPTED_THRESHOLD_STAGE


def record_stage(
    registry: dict,
    district_id: str,
    name: str,
    state: str,
    stage: int,
    stage_name: str,
    outcome: str,
    topology: str | None = None,
    batch_id: str | None = None,
    notes: str = "",
) -> dict:
    """Update (or create) a district's current-stage snapshot and append to its history."""
    d = registry["districts"].setdefault(district_id, {"name": name, "state": state, "history": []})
    d["name"] = name
    d["state"] = state
    d["furthest_stage"] = stage
    d["stage_name"] = stage_name
    d["outcome"] = outcome
    d["topology"] = topology
    d["batch_id"] = batch_id
    d["notes"] = notes
    d["history"].append({"stage": stage, "stage_name": stage_name, "outcome": outcome, "at": _now()})
    return d
