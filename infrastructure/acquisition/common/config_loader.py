"""Loader for the config-as-data layer — versioned tunables under paths.CONFIG_DIR (REQ-088).

Each knob is a JSON file shaped:

    {"knob": "<name>", "description": "...", "governance": "...",
     "entries": [{"value": ..., "added": "YYYY-MM-DD", "rationale": "...",
                  "evidence": "...", "approved_by": "...", "loop_tier": 0}, ...]}

Per-entry provenance, so a knob doubles as its own decision log (the lineage/audit principle).
JSON is the format precisely so the Node half of the pipeline reads the *same* files natively —
this module is the Python reader; there is no separate Node loader to keep in sync.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

PROVENANCE_FIELDS = ("value", "added", "rationale", "evidence", "approved_by", "loop_tier")


def knob_path(name: str) -> Path:
    return paths.CONFIG_DIR / f"{name}.json"


def load(name: str) -> dict:
    """The full knob document, including per-entry provenance."""
    return json.loads(knob_path(name).read_text())


def values(name: str) -> list:
    """Just the live list of entry values — what the pipeline actually consumes."""
    return [e["value"] for e in load(name).get("entries", [])]
