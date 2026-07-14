"""The rotating cross-family judge cascade (REQ-056 applied to review).

For each candidate, two cross-family voters adjudicate; only a split escalates to the third as
tie-breaker. Roles rotate per candidate (`roster.rotation_for`) so no model is permanently the
decider. This is the pipeline's own council pattern — the third-family judge fires only on genuine
disagreement, which is exactly what makes it load-bearing rather than a rubber stamp.

A candidate survives (`confirmed`) iff a majority of the judges that voted call it real: agreement of
the two voters settles it in one round (2 calls); a split is broken by the tie-breaker (3 calls).
Every judge call is spend-guarded and its real `usage.cost` settled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from infrastructure.acquisition.stage7_extract import openrouter as OR
from tools.crossfam_review import prompts as P
from tools.crossfam_review.dedup import Candidate
from tools.crossfam_review.roster import Model, rotation_for
from tools.crossfam_review.schemas import JUDGE_RESPONSE_FORMAT
from tools.crossfam_review.shards import REPO_ROOT
from tools.crossfam_review.spend import BudgetExceeded, SpendGuard

_CONTEXT_RADIUS = 40          # lines above/below the cited line to show the judge
_MAX_CONTEXT_LINES = 400      # cap for a line-less finding on a big file (keeps the judge call cheap)
_EST_JUDGE_COMPLETION = 1500  # terse verdict + a reasoning judge's thinking; reservation only (real
#                               cost settles from usage.cost — a low estimate only risks minor overshoot)


@dataclass
class Verdict:
    judge: str
    role: str            # voter_a | voter_b | tiebreaker
    verdict: str         # confirmed | refuted | error
    reason: str = ""
    cost_usd: float = 0.0


@dataclass
class Adjudication:
    candidate: Candidate
    verdicts: list[Verdict] = field(default_factory=list)
    confirmed: bool = False
    cost_usd: float = 0.0
    escalated: bool = False


def code_context(file: str, line: int) -> str:
    """The cited region: `line ± _CONTEXT_RADIUS`, or the file head if no usable line. Empty banner if
    the file is gone (a finding on a moved/deleted path — the judge will refute for lack of evidence)."""
    p = (REPO_ROOT / file) if file else None
    if not p or not p.exists() or not p.is_file():
        return f"<<file not found: {file}>>"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"<<could not read {file}: {e}>>"
    if line and line > 0:
        lo = max(0, line - 1 - _CONTEXT_RADIUS)
        hi = min(len(lines), line - 1 + _CONTEXT_RADIUS + 1)
    else:
        lo, hi = 0, min(len(lines), _MAX_CONTEXT_LINES)
    numbered = [f"{i + 1:>6}\t{lines[i]}" for i in range(lo, hi)]
    return f"===== {file} (lines {lo + 1}-{hi}) =====\n" + "\n".join(numbered)


def _parse_verdict(content: str) -> tuple[str, str]:
    """(verdict, reason) from a judge reply. Tolerant: JSON first, then substring sniff. Unknown →
    'refuted' (conservative: an unparseable verdict must not confirm a finding onto the tracker)."""
    import json
    import re
    if not content:
        return "refuted", "empty judge reply"
    t = content.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        d = json.loads(t)
        v = str(d.get("verdict", "")).strip().lower()
        if v in ("confirmed", "refuted"):
            return v, str(d.get("reason", "")).strip()
    except Exception:
        pass
    low = content.lower()
    if "confirm" in low and "refut" not in low:
        return "confirmed", content.strip()[:300]
    return "refuted", content.strip()[:300]


def _ask_judge(model: Model, role: str, cand: Candidate, ctx: str, guard: SpendGuard) -> Verdict:
    estimate = model.cost(len(ctx) // 4 + 400, _EST_JUDGE_COMPLETION)
    try:
        guard.reserve(estimate)
    except BudgetExceeded as e:
        return Verdict(model.id, role, "error", reason=str(e))
    actual = None
    rep = cand.members[0]
    rep.model = rep.model or "a finder"
    try:
        body = {"model": model.id,
                "messages": [{"role": "system", "content": P.JUDGE_SYSTEM},
                             P.judge_user_message(rep, ctx)],
                "response_format": JUDGE_RESPONSE_FORMAT}
        res = OR.call(body, max_tokens=8000)
        actual = float(res.cost_usd) if res.cost_usd is not None else model.cost(
            res.prompt_tokens, res.completion_tokens)
        if not res.ok:
            return Verdict(model.id, role, "error", reason=res.error or "call failed", cost_usd=actual)
        verdict, reason = _parse_verdict(res.content)
        return Verdict(model.id, role, verdict, reason=reason, cost_usd=actual)
    except OR.BillingAuthError:
        raise
    except Exception as e:  # noqa: BLE001
        return Verdict(model.id, role, "error", reason=str(e), cost_usd=actual or 0.0)
    finally:
        guard.settle(estimate, actual)


def _tally(verdicts: list[Verdict]) -> bool:
    """Majority of NON-error votes confirm → confirmed. All-error / tie-with-no-majority → not
    confirmed (conservative). A tie among an even count is only possible before escalation; the caller
    escalates on a split, so by decision time the count is odd or unanimous.

    Requires at least TWO non-error votes: if judges errored (e.g. the spend cap was hit mid-cascade),
    a finding must NOT be confirmed on a lone surviving vote — a 1-confirm / 2-error tally is
    inconclusive, not confirmed (the timeutil.py:14 weak-confirm seen in the 2026-07-13 smoke)."""
    conf = sum(1 for v in verdicts if v.verdict == "confirmed")
    ref = sum(1 for v in verdicts if v.verdict == "refuted")
    if conf + ref < 2:
        return False
    return conf > ref


def adjudicate(cand: Candidate, index: int, guard: SpendGuard) -> Adjudication:
    """Run the rotating cascade on one candidate. Two voters; escalate to the tie-breaker only on a
    split. `index` drives the deterministic role rotation."""
    voter_a, voter_b, tiebreaker = rotation_for(index)
    ctx = code_context(cand.file, cand.line)
    adj = Adjudication(candidate=cand)

    va = _ask_judge(voter_a, "voter_a", cand, ctx, guard)
    vb = _ask_judge(voter_b, "voter_b", cand, ctx, guard)
    adj.verdicts.extend([va, vb])

    live = [v for v in (va, vb) if v.verdict in ("confirmed", "refuted")]
    split = {v.verdict for v in live}
    # Escalate when the two voters disagree, OR when one/both errored (a lone surviving vote shouldn't
    # decide alone — let the third weigh in). Skip escalation only when both voters agreed cleanly.
    need_tiebreak = len(live) < 2 or len(split) > 1
    if need_tiebreak:
        vt = _ask_judge(tiebreaker, "tiebreaker", cand, ctx, guard)
        adj.verdicts.append(vt)
        adj.escalated = True

    adj.confirmed = _tally(adj.verdicts)
    adj.cost_usd = sum(v.cost_usd for v in adj.verdicts)
    return adj
