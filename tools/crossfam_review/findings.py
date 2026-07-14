"""The Finding record + tolerant parsing of a model's review reply.

A finder returns compact JSON `{"findings":[{...}]}`; models being models, some wrap it in markdown
fences, add a preamble, or truncate the tail. `parse_findings()` tolerates all three the same way the
extraction parser does (`stage7_extract.parse`): strip fences, try a clean parse, then salvage
individual `{...}` finding objects from the partial text. A malformed single object is skipped, never
fatal — one bad finding must not sink a shard's whole review.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

SEVERITIES = ("critical", "major", "minor")
# Map our severity vocabulary onto the repo's existing sev:* labels (gh label list, 2026-07-13).
SEV_LABEL = {"critical": "sev:critical", "major": "sev:major", "minor": "sev:minor"}

# A single finding object: a {...} span mentioning "summary" (the one always-present field). Non-greedy,
# no nested braces — matches the salvage regex style in stage7_extract.parse._SCHED_OBJ.
_FINDING_OBJ = re.compile(r'\{[^{}]*?"summary"[^{}]*?\}', re.DOTALL)


@dataclass
class Finding:
    """One defect claim from one finder. `model`/`shard_id` are stamped by the caller, not the model."""
    file: str                       # repo-relative path the finding is in
    line: int                       # 1-based line (0 if the model gave none)
    severity: str                   # critical | major | minor (normalized; unknown → minor)
    category: str                   # short kebab slug: correctness | security | efficiency | ...
    summary: str                    # one-sentence statement of the defect
    failure_scenario: str           # concrete inputs/state → wrong output/crash
    model: str = ""                 # finder model id (stamped by finder.py)
    shard_id: str = ""              # shard it was found in (stamped by finder.py)
    confidence: str = ""            # the model's own hedge, if given (verbatim)

    def key(self) -> tuple:
        """Coarse identity for dedup: same file + same ~line-neighborhood + same category. Line is
        bucketed to 10 so two models citing lines 41 and 44 of the same bug collapse together."""
        return (self.file, self.line // 10, self.category.strip().lower())

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_sev(v) -> str:
    s = str(v or "").strip().lower()
    if s in SEVERITIES:
        return s
    # tolerate common synonyms models emit
    if s in ("high", "urgent", "blocker"):
        return "critical"
    if s in ("medium", "moderate"):
        return "major"
    if s in ("low", "trivial", "nit", "info", "informational"):
        return "minor"
    return "minor"


def _coerce(obj: dict) -> Optional[Finding]:
    """Build a Finding from one parsed object, tolerating missing/renamed fields. Returns None only
    if there's no usable summary (a finding with nothing to say is dropped)."""
    if not isinstance(obj, dict):
        return None
    summary = str(obj.get("summary") or obj.get("title") or "").strip()
    if not summary:
        return None
    line_raw = obj.get("line", obj.get("line_number", 0))
    try:
        line = int(line_raw)
    except (TypeError, ValueError):
        line = 0
    return Finding(
        file=str(obj.get("file") or obj.get("path") or "").strip(),
        line=max(0, line),
        severity=_norm_sev(obj.get("severity")),
        category=str(obj.get("category") or "correctness").strip().lower(),
        summary=summary,
        failure_scenario=str(obj.get("failure_scenario") or obj.get("scenario")
                             or obj.get("detail") or "").strip(),
        confidence=str(obj.get("confidence") or "").strip(),
    )


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def parse_findings(content: str) -> list[Finding]:
    """Return the findings from a model reply. `[]` on empty. Clean parse first; salvage individual
    finding objects if the whole payload won't parse (truncation / fence / preamble)."""
    if not content or not content.strip():
        return []
    text = _strip_fences(content)
    objs: list = []
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            objs = data.get("findings") or data.get("issues") or []
        elif isinstance(data, list):
            objs = data
    except Exception:
        objs = []
    if not objs:  # salvage from partial / prose-wrapped text
        objs = []
        for m in _FINDING_OBJ.finditer(text):
            try:
                objs.append(json.loads(m.group(0)))
            except Exception:
                continue
    out = []
    for o in objs:
        f = _coerce(o)
        if f is not None:
            out.append(f)
    return out
