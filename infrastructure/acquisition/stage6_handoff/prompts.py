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
{"schedules":[{"grade_level":"high","start_time":"08:10","end_time":"14:35","school_name":"Fivay High","confidence":"high"}]}
If none found: {"schedules":[]}"""

# The vision-path variant — same rules, read from the rendered page image(s) (multi-column scans, fliers).
_EXTRACT_VISION_V1 = _EXTRACT_V1.replace(
    "from the document text or images.",
    "by reading the document IMAGE(S) — read the schedule spatially (columns, tables, multi-column layouts).")

SYSTEM_PROMPTS = {
    "stage6.extract.v1": _EXTRACT_V1,
    "stage6.extract.vision.v1": _EXTRACT_VISION_V1,
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
