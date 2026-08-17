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


def _sched_items(obj) -> list[dict] | None:
    """The schedule dicts a decoded value carries, leak-scrubbed — or None if it isn't a schedule
    carrier at all (scan its interior instead). A carrier is a dict with "start_time" (one schedule)
    or a dict with a "schedules" list (a complete wrapper stranded in prose)."""
    if not isinstance(obj, dict):
        return None
    if "start_time" in obj:
        return [] if _is_prompt_leak(obj) else [_scrub_campus_names(obj)]
    scheds = obj.get("schedules")
    if isinstance(scheds, list):
        return [_scrub_campus_names(s) for s in scheds
                if isinstance(s, dict) and "start_time" in s and not _is_prompt_leak(s)]
    return None


def _salvage(text: str) -> list[dict]:
    """Recover schedule objects from text the clean parse rejected, using the real JSON parser
    (`raw_decode`) at each `{` — a regex can't cross braces inside string values, and captured
    text carries braces in school names/notes (#276). Whatever parses and carries schedules is
    consumed whole; anything else is scanned interior-first."""
    out = []
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        items = _sched_items(obj)
        if items is None:
            i = text.find("{", i + 1)      # not a carrier — look for nested candidates
        else:
            out.extend(items)
            i = text.find("{", end)
    return out


# #812 — DEGENERATE REPETITION. A voter can fall into a loop, emitting one row over and over until
# max_tokens cuts it off, and the pipeline recorded that as a large successful extraction: Stroudsburg
# 4222860 (a SEVEN-school district) "returned 420 facts" that are `MCTI` repeated 420 times. A corpus
# scan of all 2,340 fact-bearing calls found 6 with a distinct-row ratio <= 0.005 — and those 6 are
# EXACTLY the 6 truncated-with-facts calls in the receipt store. The next-lowest ratio is 0.143 (7
# identical rows, incidental redundancy in a document, not a runaway), so 0.10 separates the two
# populations with room on both sides. `MIN_ROWS` is belt-and-braces: at ratio <= 0.10 a call needs
# >= 10 rows arithmetically anyway.
REPETITION_MAX_DISTINCT_RATIO = 0.10
REPETITION_MIN_ROWS = 10
# The fields that make a schedule row's IDENTITY. Two rows agreeing on all four carry no information
# the first one didn't — consensus already groups by (band, normalized school), so collapsing them
# changes no outcome; it only stops a loop from LOOKING like a big roster.
_IDENTITY_KEYS = ("school_name", "grade_level", "start_time", "end_time")


def _identity(sched: dict) -> tuple:
    return tuple(str(sched.get(k) or "").strip().lower() for k in _IDENTITY_KEYS)


def dedupe_identical(scheds: list) -> list:
    """Drop rows identical on `_IDENTITY_KEYS`, first-seen order preserved (the first occurrence
    keeps its evidence/campus fields). ALWAYS correct — never thresholded — so `n_facts` means
    'distinct schedules read' everywhere rather than 'rows the model emitted'."""
    seen, out = set(), []
    for s in scheds or []:
        if not isinstance(s, dict):
            continue
        k = _identity(s)
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def degenerate_repetition(scheds: list) -> "dict | None":
    """Was this a repetition LOOP rather than a read? Pure, over a RAW (pre-dedupe) fact list — so
    it derives identically from a stored receipt's `facts` on the #716 replay, at zero spend.
    Returns {n_rows, n_distinct, ratio} or None.

    A loop is NOT a partial roster: sizing its call larger only buys more duplicate rows, and its
    remedy is 're-route, this document made the model loop', never 'the tail was dropped'."""
    rows = [s for s in (scheds or []) if isinstance(s, dict)]
    if len(rows) < REPETITION_MIN_ROWS:
        return None
    n_distinct = len({_identity(s) for s in rows})
    ratio = n_distinct / len(rows)
    if ratio > REPETITION_MAX_DISTINCT_RATIO:
        return None
    return {"n_rows": len(rows), "n_distinct": n_distinct, "ratio": round(ratio, 4)}


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
        scheds = obj.get("schedules")
    elif isinstance(obj, list):
        scheds = obj
    else:
        scheds = None
    if not isinstance(scheds, list):   # {"schedules": null/scalar/dict} = "found nothing" (#362)
        return []
    return [_scrub_campus_names(s) for s in scheds
            if isinstance(s, dict) and not _is_prompt_leak(s)]
