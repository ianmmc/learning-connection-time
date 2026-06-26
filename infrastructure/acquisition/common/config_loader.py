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
    """The live list of values the pipeline consumes. Two supported knob shapes:
      * full provenance per item:  {"entries": [{"value": ..., <provenance>}, ...]}
        (use for consequential, individually-justified items, e.g. cms_hosts)
      * baseline + tracked additions:  {"baseline": {...}, "values": [...],
        "additions": [{"value": ..., <provenance>}, ...]}
        (use for large lists where the bulk shares one baseline provenance and only the
        deltas need individual justification, e.g. keyword lists)
    Order preserved: entries, or baseline values then additions."""
    doc = load(name)
    if "entries" in doc:
        return [e["value"] for e in doc["entries"]]
    return list(doc.get("values", [])) + [a["value"] for a in doc.get("additions", [])]
