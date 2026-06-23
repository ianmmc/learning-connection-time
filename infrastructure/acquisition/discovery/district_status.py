"""Cross-stage per-district status registry for the acquisition pipeline (all 9 stages).

One JSON file, one entry per district that has ENTERED the pipeline (passed Stage 1's
pre-queue exclusion filters). Pre-queue exclusions (CTC, not-operating, grade-span gap)
are NOT recorded here -- they're live filters recomputed from is_shared_service_entity /
LEA_TYPE_TEXT / grade-span every run, never a frozen list (see ACQUISITION_PIPELINE.md
Stage 1). Keyed by district_id for O(1) lookup -- structure over scan-ability, since this
is process input read by every batch-build run, not primarily a human-read record.

Schema reference: data/acquisition/status/district_status.example.json
Doc: docs/ACQUISITION_PIPELINE.md (Stage 1), docs/diagrams/acquisition_pipeline_flow.md
"""
from datetime import datetime, timezone
from pathlib import Path
import json

STATUS_FILE = Path("data/acquisition/status/district_status.json")
SCHEMA_VERSION = 1


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
    return district_id in registry["districts"]


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
