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

# Prompt-example leak guard: names a model can only have copied from the system prompt's few-shot
# example, never read from a document. "Fivay High" (the pre-2026-07-03 example) leaked into live
# output at confidence=high; the DEEP fix was replacing the example with the self-evident
# "[SCHOOL NAME]" (prompts.py), which is all this guard now needs to match. "fivay high" was REMOVED
# from this set (#144): Fivay High is a REAL school (Pasco County FL, a top-100 district squarely in
# our target universe) — blacklisting it permanently blinded extraction to a real school, while the
# current prompt no longer contains the string so that leak cannot recur. Never add a real school
# name here; fix the prompt instead and keep only self-evident placeholders.
_PROMPT_LEAK_NAMES = {"[school name]"}


def _is_prompt_leak(sched: dict) -> bool:
    return str(sched.get("school_name", "")).strip().lower() in _PROMPT_LEAK_NAMES


def _scrub_campus_names(sched: dict) -> dict:
    """v4 (#499 REQ-148): campus_names gets the SAME placeholder leak guard as school_name — a
    model echoing the prompt's example placeholder into the campus list would otherwise flow into
    the slot-spine's campus fill. Non-list/absent values normalize away (pre-v4 rows untouched)."""
    camps = sched.get("campus_names")
    if isinstance(camps, list):
        clean = [c for c in camps
                 if str(c).strip() and str(c).strip().lower() not in _PROMPT_LEAK_NAMES]
        if clean:
            sched["campus_names"] = clean
        else:
            sched.pop("campus_names", None)
    elif camps is not None:
        sched.pop("campus_names", None)
    return sched


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
            obj = json.loads(m.group(0))
        except Exception:
            continue
        if not _is_prompt_leak(obj):
            out.append(_scrub_campus_names(obj))
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
    return [_scrub_campus_names(s) for s in scheds
            if isinstance(s, dict) and not _is_prompt_leak(s)]
