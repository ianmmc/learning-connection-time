"""File confirmed findings on the GitHub tracker under a campaign label.

Follows the repo's existing review-campaign convention (labels like `code-review-2026-07-06`,
`fable-review-2026-07-04`): one distinct campaign label so the whole batch is trivially bulk-triaged
or bulk-closed later — which is exactly the "catalog everything, dedup later based on those records"
workflow Ian described. Each issue also carries an `area:*` and a `sev:*` label from the existing set.

Every issue body ends with a stable `<!-- crossfam-fp:... -->` fingerprint so a re-run is idempotent:
`existing_fingerprints()` reads them back and `create_issue` skips a candidate already filed. Nothing
here runs unless the orchestrator is in `--live` mode; `dry_run=True` returns the exact payload it
WOULD create without touching the network.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass

from tools.crossfam_review.council import Adjudication
from tools.crossfam_review.findings import SEV_LABEL, dedup_key

REPO = "ianmmc/learning-connection-time"
_TITLE_MAX = 250   # GitHub issue-title practical cap


def campaign_label(stamp: str) -> str:
    """e.g. 'crossfam-review-2026-07-13' — the batch's own label."""
    return f"crossfam-review-{stamp}"


def fingerprint(adj: Adjudication) -> str:
    c = adj.candidate
    f, lb, cat = dedup_key(c.file, c.line, c.category)   # the ONE shared coarse key (not a 4th copy)
    raw = f"{f}|{lb}|{cat}|{c.summary.strip().lower()[:80]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@dataclass
class IssuePayload:
    title: str
    body: str
    labels: list[str]
    fingerprint: str


def _title(adj: Adjudication) -> str:
    """`[crossfam] <summary> (<file>:<line>)`, capped at _TITLE_MAX with the LOCATION SUFFIX PRESERVED:
    the summary is truncated to whatever room the (always-parenthesized) location leaves, so the final
    cap never cuts through the '(file:line)' and leaves a dangling paren."""
    c = adj.candidate
    prefix = "[crossfam] "
    loc = f"{c.file}:{c.line}" if c.line else (c.file or "?")
    suffix = f" ({loc})"
    if len(prefix) + len(suffix) > _TITLE_MAX:          # pathological: the path alone overruns — elide it
        keep = _TITLE_MAX - len(prefix) - len(" (…)")
        suffix = f" (…{loc[-keep:]})" if keep > 0 else ""
    body_budget = max(0, _TITLE_MAX - len(prefix) - len(suffix))
    summary = c.summary.rstrip(".")[:body_budget]
    return (prefix + summary + suffix)[:_TITLE_MAX]


def _finder_models(adj: Adjudication) -> list[str]:
    """The distinct finder model ids that reported this defect (order-stable), for the 'discovered by'
    line and the machine marker — the raw material for later per-model effectiveness analysis."""
    seen: list[str] = []
    for m in adj.candidate.members:
        if m.model and m.model not in seen:
            seen.append(m.model)
    return seen


def _meta_marker(adj: Adjudication) -> str:
    """A machine-parseable footer capturing WHICH models found and judged this, so a later sweep can
    query the tracker (`gh issue list --json body`) and measure per-model finder yield + judge
    behavior without re-deriving anything. One compact JSON line; the fingerprint stays separate."""
    c = adj.candidate
    meta = {
        "finders": _finder_models(adj),
        "families": sorted(c.families),
        "agree_count": c.agree_count,
        "severity": c.severity,
        "category": c.category,
        "escalated": adj.escalated,
        "judges": [{"judge": v.judge, "role": v.role, "verdict": v.verdict, "severity": v.severity}
                   for v in adj.verdicts],
    }
    return "<!-- crossfam-meta:" + json.dumps(meta, separators=(",", ":")) + " -->"


def _body(adj: Adjudication, stamp: str) -> str:
    c = adj.candidate
    fams = ", ".join(sorted(c.families)) or "—"
    discovered = ", ".join(f"`{m}`" for m in _finder_models(adj)) or "—"
    votes = "\n".join(
        f"- **{v.role}** `{v.judge}` → **{v.verdict}**: {v.reason}" for v in adj.verdicts)
    finders = "\n".join(
        f"- `{m.model}` (shard `{m.shard_id}`): {m.summary}" for m in c.members)
    return f"""\
**File:** `{c.file}`{(' line ' + str(c.line)) if c.line else ''}
**Severity:** {c.severity} · **Category:** {c.category}
**Discovered by:** {discovered}
**Cross-family corroboration:** {c.agree_count} finder families ({fams})

### The defect
{c.summary}

**Failure scenario:** {c.failure_scenario or '—'}

### Judge council ({'escalated to tie-breaker' if adj.escalated else 'voters agreed'})
{votes}

### Raw finder reports
{finders}

---
<sub>Filed by the cross-family external review harness ({stamp}). Confirmed by cross-family judge
cascade; awaiting human triage. Verify before fixing — external models can be confidently wrong.</sub>
<!-- crossfam-fp:{fingerprint(adj)} -->
{_meta_marker(adj)}"""


def build_payload(adj: Adjudication, stamp: str) -> IssuePayload:
    c = adj.candidate
    labels = [campaign_label(stamp)]
    if c.area_label:
        labels.append(c.area_label)
    labels.append(SEV_LABEL.get(c.severity, "sev:minor"))
    return IssuePayload(title=_title(adj), body=_body(adj, stamp), labels=labels,
                        fingerprint=fingerprint(adj))


def ensure_label(stamp: str, live: bool) -> None:
    """Create the campaign label if missing (idempotent). No-op in dry-run."""
    if not live:
        return
    label = campaign_label(stamp)
    subprocess.run(
        ["gh", "label", "create", label, "--repo", REPO,
         "--color", "B60205", "--description", f"Cross-family external review ({stamp})",
         "--force"],
        check=False, capture_output=True, text=True)


def existing_fingerprints(stamp: str, live: bool) -> set[str]:
    """Fingerprints already on the tracker under this campaign label, so a re-run skips them."""
    if not live:
        return set()
    out = subprocess.run(
        # A campaign label can accumulate thousands of issues across repeated runs/resumes; the old
        # --limit 500 silently dropped fingerprints beyond that window, re-filing duplicates. `gh`
        # paginates internally up to --limit, so a ceiling well above any real campaign fetches them all.
        ["gh", "issue", "list", "--repo", REPO, "--label", campaign_label(stamp),
         "--state", "all", "--limit", "100000", "--json", "body"],
        check=False, capture_output=True, text=True)
    seen: set[str] = set()
    if out.returncode == 0 and out.stdout.strip():
        try:
            for row in json.loads(out.stdout):
                body = row.get("body") or ""
                marker = "<!-- crossfam-fp:"
                if marker in body:
                    seen.add(body.split(marker, 1)[1].split("-->", 1)[0].strip())
        except Exception:
            pass
    return seen


def parse_meta_marker(body: str) -> dict | None:
    """Recover the crossfam-meta JSON from a filed issue's body (the inverse of `_meta_marker`), so a
    later effectiveness analysis can read per-model attribution straight off the tracker. None if absent."""
    marker = "<!-- crossfam-meta:"
    if marker not in body:
        return None
    try:
        return json.loads(body.split(marker, 1)[1].rsplit("-->", 1)[0].strip())
    except Exception:
        return None


def create_issue(payload: IssuePayload, *, live: bool) -> dict:
    """Create the issue (live) or return the payload it WOULD create (dry-run)."""
    if not live:
        return {"dry_run": True, "title": payload.title, "labels": payload.labels,
                "fingerprint": payload.fingerprint}
    args = ["gh", "issue", "create", "--repo", REPO,
            "--title", payload.title, "--body", payload.body]
    for lb in payload.labels:
        args += ["--label", lb]
    out = subprocess.run(args, check=False, capture_output=True, text=True)
    if out.returncode != 0:
        return {"error": out.stderr.strip(), "title": payload.title}
    return {"url": out.stdout.strip(), "title": payload.title, "fingerprint": payload.fingerprint}
