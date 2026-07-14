"""Collapse raw findings from 11 finders into unique candidates for the judge council.

11 diverse models over 37 shards produce heavy overlap — the same real bug surfaces from many
families (which is itself a strong signal). Dedup clusters by coarse identity (file + ~line bucket +
category, see `Finding.key`) so the council adjudicates each distinct defect ONCE, not once per model
that noticed it. The count of families that independently flagged a cluster rides along as
`agree_count` — a cross-family corroboration signal the council and triage both use.

Deliberately conservative: clustering only merges findings that agree on file, neighborhood, AND
category. Two genuinely different bugs on the same line stay separate (different category), and a bug
reported at lines 41 and 44 merges (same 10-line bucket). Semantic near-duplicates the key misses are
caught later by the judge/triage, never silently dropped here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tools.crossfam_review.findings import Finding

_SEV_RANK = {"critical": 0, "major": 1, "minor": 2}


@dataclass
class Candidate:
    """A cluster of findings judged to be the same defect. The representative is the highest-severity
    member; all members and the corroborating families are retained for triage + the issue body."""
    file: str
    line: int
    category: str
    severity: str
    summary: str
    failure_scenario: str
    members: list[Finding] = field(default_factory=list)
    families: set[str] = field(default_factory=set)

    @property
    def agree_count(self) -> int:
        return len(self.families)

    @property
    def area_label(self) -> str:
        # set by cluster() from the shard's area; stored on the representative finding's shard.
        return self._area

    _area: str = ""


def _family(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else model_id


def cluster(findings: list[Finding], shard_area: dict[str, str] | None = None) -> list[Candidate]:
    """Group findings by `Finding.key()`; the representative is the most severe member (ties → the
    one with the longest failure_scenario, a weak proxy for the most-substantiated report). Returned
    sorted by (severity, -agree_count, file) so triage and the council see the scariest, most-corroborated
    defects first — which also fixes the council's rotation order deterministically."""
    shard_area = shard_area or {}
    groups: dict[tuple, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.key(), []).append(f)

    cands: list[Candidate] = []
    for members in groups.values():
        rep = min(members, key=lambda f: (_SEV_RANK.get(f.severity, 3), -len(f.failure_scenario)))
        c = Candidate(
            file=rep.file, line=rep.line, category=rep.category, severity=rep.severity,
            summary=rep.summary, failure_scenario=rep.failure_scenario,
            members=list(members), families={_family(m.model) for m in members if m.model},
        )
        c._area = shard_area.get(rep.shard_id, "")
        cands.append(c)

    cands.sort(key=lambda c: (_SEV_RANK.get(c.severity, 3), -c.agree_count, c.file, c.line))
    return cands
