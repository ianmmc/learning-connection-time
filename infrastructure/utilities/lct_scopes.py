"""The ONE home for the #1017 level-scope quarantine (REQ-190).

CCD/EDFacts FS059 counts a teacher as "elementary" by state and local practice (any grade span not above
grade 8), so `teachers_elementary` / `teachers_secondary` pair a state-practice numerator with a fixed
K-5 / 6-12 denominator and are not comparable across states. Until the school-file band scopes replace
them (#1022) and they are retired (#1023), every presenter — the calc script's console and text report,
the QA JSON, the stored `lct_calculations.notes` row, the CSV/parquet exports, the gate@8 sign-off preview,
the postgres MCP server — labels them through THIS module. No presenter spells the caveat itself
(tests/test_level_scope_quarantine.py pins that).

Lives in `utilities/` because both `infrastructure.database` (models, the MCP server) and
`infrastructure.scripts` (the calc) must import it without either importing the other.
"""
from __future__ import annotations

TEACHER_LEVEL_SCOPES = ("teachers_elementary", "teachers_secondary")

LEVEL_SPLIT_CAVEAT = "not comparable across states: the CCD level split follows state practice (#1017)"

# The durable per-row marker. It rides in `level_lct_notes` (-> `lct_calculations.notes`, the CSV/parquet
# `level_lct_notes` column) ahead of the safeguard flags, so a SQL reader or a downstream file sees it
# without consulting any report. It is NOT a data-quality finding about the district: `data_quality_notes`
# strips it before anything counts "districts with QA notes".
QUARANTINE_TOKEN = "QUARANTINED_1017"

QUARANTINED_SCOPES: dict[str, str] = {scope: LEVEL_SPLIT_CAVEAT for scope in TEACHER_LEVEL_SCOPES}

_SEP = "; "


def quarantine_caption(scope: str) -> str | None:
    """The caveat for a quarantined scope, None for every other scope."""
    return QUARANTINED_SCOPES.get(scope)


def with_quarantine_token(scope: str, notes: str | None) -> str:
    """`notes` with QUARANTINE_TOKEN prepended when `scope` is quarantined; unchanged otherwise.
    Idempotent: a note that already starts with the token is returned as is."""
    notes = notes or ""
    if scope not in QUARANTINED_SCOPES or notes == QUARANTINE_TOKEN or notes.startswith(QUARANTINE_TOKEN + _SEP):
        return notes
    return f"{QUARANTINE_TOKEN}{_SEP}{notes}" if notes else QUARANTINE_TOKEN


def data_quality_notes(notes: str | None) -> str:
    """`notes` minus the quarantine token — what counts as a per-district data-quality note."""
    parts = [p for p in (notes or "").split(_SEP) if p and p != QUARANTINE_TOKEN]
    return _SEP.join(parts)
