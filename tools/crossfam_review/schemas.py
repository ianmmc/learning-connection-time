"""Strict JSON-schema response formats for finders and judges.

Every model in the roster advertises `structured_outputs` support (checked against the OpenRouter
catalog 2026-07-13), so we force each reply to conform to an exact schema rather than relying on the
prompt + a tolerant salvage parser. This eliminates fence/preamble/truncation ambiguity, guarantees
every required field is present, types `line` as an integer and `severity`/`verdict` as enums, and
even caps the finder at 12 findings structurally (`maxItems`). The tolerant parser
(`findings.parse_findings`, `council._parse_verdict`) stays as defense-in-depth for the rare provider
that honors the schema loosely.

Passed to the paid client as `response_format` inside the request body — a standard OpenAI SDK field
the shared `openrouter.call` forwards as-is (unlike the `reasoning` param, which the SDK rejects).
"""
from __future__ import annotations

_FINDING_ITEM = {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "line": {"type": "integer"},
        "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
        "category": {"type": "string"},
        "summary": {"type": "string"},
        "failure_scenario": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["file", "line", "severity", "category", "summary", "failure_scenario", "confidence"],
    "additionalProperties": False,
}

FINDER_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "code_review_findings",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "findings": {"type": "array", "maxItems": 12, "items": _FINDING_ITEM},
            },
            "required": ["findings"],
            "additionalProperties": False,
        },
    },
}

JUDGE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "review_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["confirmed", "refuted"]},
                "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                "reason": {"type": "string"},
            },
            "required": ["verdict", "severity", "reason"],
            "additionalProperties": False,
        },
    },
}
