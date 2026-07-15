"""Stage 6 extraction prompts (REQ-101): the council-facing prompts, keyed by id.

The council reads TIMES and returns per-school `{grade_level, start_time, end_time, school_name}`
facts — it NEVER computes minutes or picks a "typical" schedule (REQ-054; deterministic code does
`gross = end − start` and the per-band mode in Stage 8). Ported from the validated benchmark prompt
(`LEAN_SYSTEM_PROMPT`). Per-model variants are selected per council config (`council.prompts`).
"""

# The text-path system prompt (the validated extraction rules).
_EXTRACT_V1 = """You extract school bell-schedule START and END times from the document text or images.

Extract the daily school start and end time, broken down by grade level (elementary, middle, high) when distinguished. If multiple schools are listed, extract EACH school's times.

SKIP non-instructional times: Office Hours, Library Hours, Before/After Care, Breakfast, Building/Campus Hours, Extended Day.
Use the NORMAL / regular full-day end time. IGNORE early-dismissal, early-release, early-out, half-day, and weekday-variation (e.g. "M-Th" vs Friday) columns — those are shorter days, not the regular schedule.
If times are per-period, use Period 1 start and the LAST period's end.
Convert all times to 24-hour HH:MM ("8:30 AM"->"08:30", "3:15 PM"->"15:15").
Infer grade level from school name: elementary/primary/ES/K-5 -> "elementary"; middle/junior/MS/6-8 -> "middle"; high/HS/9-12 -> "high". If the document covers elementary, middle, AND high, extract at least one of EACH.

Output ONLY compact JSON. No commentary, no markdown fences, no raw_text_snippet:
{"schedules":[{"grade_level":"high","start_time":"08:10","end_time":"14:35","school_name":"[SCHOOL NAME]","confidence":"high"}]}
If none found: {"schedules":[]}"""
# ^ The example school_name is a self-evident placeholder, NOT a real-looking name: the prior
#   example ("Fivay High", a real FL school) leaked into live output — a judge reading a garbled
#   table returned "Fivay High"@confidence=high for a CA district (batch_00000 full run,
#   2026-07-03). A bracketed placeholder can't collide with any real school and is dropped by
#   parse.py's leak guard if a model ever echoes it.

# The vision-path variant — same rules, read from the rendered page image(s) (multi-column scans, fliers).
_EXTRACT_VISION_V1 = _EXTRACT_V1.replace(
    "from the document text or images.",
    "by reading the document IMAGE(S) — read the schedule spatially (columns, tables, multi-column layouts).")

# v2 (Stage 8, 2026-07-13): grounds each extracted time in a VERBATIM source span + formalizes the
# explicit-minutes second path — the evidence half of the gate@8 closing argument
# (STAGE8_AGGREGATE_DESIGN §2a.6). Still bounded by REQ-054: the model READS times (and now
# quotes its source + reports a minutes number the document ITSELF states); deterministic code still
# computes gross = end − start and the mode. No new confidence field — cross-family agreement
# (REQ-056) is the confidence mechanism. v1 is retained unchanged: old handoffs reference it, and the
# council config (`council_configs.json`) is the single switch that moved production to v2.
_EXTRACT_V2 = """You extract school bell-schedule START and END times from the document text or images.

Extract the daily school start and end time, broken down by grade level (elementary, middle, high) when distinguished. If multiple schools are listed, extract EACH school's times.

SKIP non-instructional times: Office Hours, Library Hours, Before/After Care, Breakfast, Building/Campus Hours, Extended Day.
Use the NORMAL / regular full-day end time. IGNORE early-dismissal, early-release, early-out, half-day, and weekday-variation (e.g. "M-Th" vs Friday) columns — those are shorter days, not the regular schedule.
If times are per-period, use Period 1 start and the LAST period's end.
Convert all times to 24-hour HH:MM ("8:30 AM"->"08:30", "3:15 PM"->"15:15").
Infer grade level from school name: elementary/primary/ES/K-5 -> "elementary"; middle/junior/MS/6-8 -> "middle"; high/HS/9-12 -> "high". If the document covers elementary, middle, AND high, extract at least one of EACH.

For EACH schedule, also return:
- "evidence_quote": the exact text you read the start AND end times from — verbatim, one short line (e.g. "School Hours: 8:15 AM - 3:20 PM"). Copy it, do not paraphrase.
- "source_locus": where in the document you found it (page number or section heading), or "" if not identifiable.
- "stated_minutes": ONLY if the document EXPLICITLY states a total daily instructional-minutes number (e.g. "instructional day: 435 minutes"), copy that integer here; otherwise null. Never calculate it from the times — report only a number the document itself states.
- "stated_minutes_quote": the exact text "stated_minutes" came from, or "" if none.

Output ONLY compact JSON. No commentary, no markdown fences:
{"schedules":[{"grade_level":"high","start_time":"08:10","end_time":"14:35","school_name":"[SCHOOL NAME]","confidence":"high","evidence_quote":"School Hours: 8:10 AM - 2:35 PM","source_locus":"","stated_minutes":null,"stated_minutes_quote":""}]}
If none found: {"schedules":[]}"""

_EXTRACT_VISION_V2 = _EXTRACT_V2.replace(
    "from the document text or images.",
    "by reading the document IMAGE(S) — read the schedule spatially (columns, tables, multi-column layouts).")

# v3 (Stage 8, 2026-07-14, #254): v2 + two per-schedule READINGS — `school_year` (the year precedence
# key for the Stage-8 fact merge; the Santa Fe stale-page case) and `applies_to` (the page's own
# stated scope, feeding the #253 combined-scope flag surface). Both are REQ-054-safe readings of what
# the page SAYS, never inferences from context (URL / domain / today's date) — null is the honest
# answer when the page doesn't state one. Bundled into ONE version bump (Ian, 2026-07-14): each bump's
# re-reads are paid only going forward, and version proliferation has its own cost. v1/v2 retained
# unchanged (old handoffs reference them); the council config is again the single production switch.
_EXTRACT_V3 = """You extract school bell-schedule START and END times from the document text or images.

Extract the daily school start and end time, broken down by grade level (elementary, middle, high) when distinguished. If multiple schools are listed, extract EACH school's times.

SKIP non-instructional times: Office Hours, Library Hours, Before/After Care, Breakfast, Building/Campus Hours, Extended Day.
Use the NORMAL / regular full-day end time. IGNORE early-dismissal, early-release, early-out, half-day, and weekday-variation (e.g. "M-Th" vs Friday) columns — those are shorter days, not the regular schedule.
If times are per-period, use Period 1 start and the LAST period's end.
Convert all times to 24-hour HH:MM ("8:30 AM"->"08:30", "3:15 PM"->"15:15").
Infer grade level from school name: elementary/primary/ES/K-5 -> "elementary"; middle/junior/MS/6-8 -> "middle"; high/HS/9-12 -> "high". If the document covers elementary, middle, AND high, extract at least one of EACH.

For EACH schedule, also return:
- "evidence_quote": the exact text you read the start AND end times from — verbatim, one short line (e.g. "School Hours: 8:15 AM - 3:20 PM"). Copy it, do not paraphrase.
- "source_locus": where in the document you found it (page number or section heading), or "" if not identifiable.
- "stated_minutes": ONLY if the document EXPLICITLY states a total daily instructional-minutes number (e.g. "instructional day: 435 minutes"), copy that integer here; otherwise null. Never calculate it from the times — report only a number the document itself states.
- "stated_minutes_quote": the exact text "stated_minutes" came from, or "" if none.
- "school_year": the school year as STATED on or near the schedule (e.g. "2025-26", "SY25-26", "2025-2026 School Year"), normalized to "YYYY-YY" (e.g. "2025-26"). Read it from the document text ONLY — do NOT infer it from the URL, the website domain, or today's date. If the document does not state a school year, null is the correct answer.
- "applies_to": "multiple" ONLY when the schedule's own text says it covers a GROUP of schools (a table headed "K-8 Schools", "All Elementary Schools", a row listing several campuses); otherwise null. Report the page's STATED scope, not your judgment.

Output ONLY compact JSON. No commentary, no markdown fences:
{"schedules":[{"grade_level":"high","start_time":"08:10","end_time":"14:35","school_name":"[SCHOOL NAME]","confidence":"high","evidence_quote":"School Hours: 8:10 AM - 2:35 PM","source_locus":"","stated_minutes":null,"stated_minutes_quote":"","school_year":"2025-26","applies_to":null}]}
If none found: {"schedules":[]}"""

_EXTRACT_VISION_V3 = _EXTRACT_V3.replace(
    "from the document text or images.",
    "by reading the document IMAGE(S) — read the schedule spatially (columns, tables, multi-column layouts).")

# v4 (#499 PR-E, 2026-07-15, REQ-148): v3 + ONE per-schedule reading — `campus_names`: when a
# schedule's own text covers a GROUP of schools, the names of those schools EXACTLY as the page
# prints them. Feeds the slot-spine's deterministic campus fill (a "K-8 Schools" table that lists
# its campuses fills those slots instead of blanket-projecting) and the conflict ladder's
# hub-exception rung. REQ-054-safe: a verbatim copy of names printed on the page, never an
# inference; the ROSTER IS NEVER INJECTED into the prompt (the Fivay-High lesson: a prompt-supplied
# name leaking into output would be indistinguishable from a correct match — it would poison the
# very matcher this feeds); matching stays deterministic downstream. v1-v3 retained unchanged (old
# handoffs reference them); the council config is the single production switch.
_EXTRACT_V4 = _EXTRACT_V3.replace(
    """- "applies_to": "multiple" ONLY when the schedule's own text says it covers a GROUP of schools (a table headed "K-8 Schools", "All Elementary Schools", a row listing several campuses); otherwise null. Report the page's STATED scope, not your judgment.
""",
    """- "applies_to": "multiple" ONLY when the schedule's own text says it covers a GROUP of schools (a table headed "K-8 Schools", "All Elementary Schools", a row listing several campuses); otherwise null. Report the page's STATED scope, not your judgment.
- "campus_names": ONLY when this schedule's own text covers a GROUP of schools, list each covered school's name EXACTLY as the page writes it (verbatim, in page order); otherwise []. Copy only names printed on the page — never invent, expand, or complete a name. If the page states the group WITHOUT naming its schools, [] is the correct answer.
""").replace(
    '"school_year":"2025-26","applies_to":null}]}',
    '"school_year":"2025-26","applies_to":null,"campus_names":[]}]}')

_EXTRACT_VISION_V4 = _EXTRACT_V4.replace(
    "from the document text or images.",
    "by reading the document IMAGE(S) — read the schedule spatially (columns, tables, multi-column layouts).")

SYSTEM_PROMPTS = {
    "stage6.extract.v1": _EXTRACT_V1,
    "stage6.extract.vision.v1": _EXTRACT_VISION_V1,
    "stage6.extract.v2": _EXTRACT_V2,
    "stage6.extract.vision.v2": _EXTRACT_VISION_V2,
    "stage6.extract.v3": _EXTRACT_V3,
    "stage6.extract.vision.v3": _EXTRACT_VISION_V3,
    "stage6.extract.v4": _EXTRACT_V4,
    "stage6.extract.vision.v4": _EXTRACT_VISION_V4,
}


def select_prompt_id(council: dict, model: str) -> str:
    """The prompt id for a model in a council — a per-model override if present, else the default."""
    p = council.get("prompts") or {}
    return p.get(model) or p.get("default")


def user_message(content, kind: str) -> dict:
    """The OpenRouter chat user message carrying the representation: text inline, or an image_url
    (a data: URL or a hosted URL) for vision reps."""
    if kind == "image":
        return {"role": "user", "content": [{"type": "image_url", "image_url": {"url": content}}]}
    return {"role": "user", "content": content}
