"""Parse a council model's reply into per-school fact rows (REQ-117).

The prompt (`stage6.extract.v1`) asks for compact JSON `{"schedules":[{grade_level,start_time,
end_time,school_name,confidence}]}` and NOTHING else — but models still occasionally wrap it in
markdown fences or truncate the tail on a long district. `parse_schedules()` tolerates both:
strips fences, tries a clean parse, and on failure salvages individual schedule objects from the
partial text (ported from the archived `_salvage_schedules`). Pure — no network, no deps.

The rows are returned verbatim (the model's own strings); time-normalization, cross-family
consensus, and `gross = end − start` are downstream (Stage 8 consensus + deterministic code) —
this module only turns text into a list of dicts.
"""
from __future__ import annotations

import json
import re

# A single schedule object: a {...} span (no nested braces) that mentions a start time.
_SCHED_OBJ = re.compile(r'\{[^{}]*?"start_time"[^{}]*?\}', re.DOTALL)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _salvage(text: str) -> list[dict]:
    out = []
    for m in _SCHED_OBJ.finditer(text):
        try:
            out.append(json.loads(m.group(0)))
        except Exception:
            pass
    return out


def parse_schedules(content: str) -> list[dict]:
    """Return the list of schedule dicts from a model reply. `[]` on empty/none.
    Clean parse first; salvage individual objects if the whole payload won't parse."""
    if not content or not content.strip():
        return []
    txt = _strip_fences(content)
    try:
        obj = json.loads(txt)
    except Exception:
        return _salvage(txt)
    if isinstance(obj, dict):
        scheds = obj.get("schedules", [])
    elif isinstance(obj, list):
        scheds = obj
    else:
        scheds = []
    return [s for s in scheds if isinstance(s, dict)]
