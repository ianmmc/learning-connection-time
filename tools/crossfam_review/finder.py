"""The finder pass: run one model over one shard → parsed, stamped findings + telemetry.

Reuses the pipeline's paid client (`stage7_extract.openrouter.call`) verbatim — same streaming,
truncation-retry, and `usage.cost` telemetry the extraction stage trusts. This module only builds the
review request, guards spend, and parses the reply into `Finding`s.
"""
from __future__ import annotations

from dataclasses import dataclass

from infrastructure.acquisition.stage7_extract import openrouter as OR
from tools.crossfam_review import prompts as P
from tools.crossfam_review.schemas import FINDER_RESPONSE_FORMAT
from tools.crossfam_review.findings import Finding, parse_findings
from tools.crossfam_review.roster import Model
from tools.crossfam_review.shards import Shard
from tools.crossfam_review.spend import BudgetExceeded, SpendGuard

# Assumed completion size for the pre-call reservation only (real cost settles from usage.cost). A
# bounded review (≤12 findings, prompts.py) is ~3-4k content tokens, but a REASONING finder also
# spends reasoning tokens (billed as completion) before the answer, so reserve generously.
_EST_COMPLETION_TOKENS = 8000
# Review needs far more headroom than extraction's 16k default: a reasoning finder (gpt-5.1-codex-mini
# etc.) must fit its thinking AND the bounded findings answer inside one budget, or it truncates with
# the answer still unwritten (the glm empty-content failure, 2026-07-13). OR retries a truncated reply
# once at its 32k hard ceiling, so passing the ceiling gives the most room the client allows.
_REVIEW_MAX_TOKENS = 32000


@dataclass
class FinderResult:
    model: str
    shard_id: str
    findings: list[Finding]
    ok: bool
    cost_usd: float
    raw_content: str = ""   # the model's verbatim reply — persisted as an audit receipt (raw_replies.jsonl)
    finish_reason: str | None = None
    error: str | None = None
    skipped: bool = False   # refused by the spend guard (not an error — expected at the cap)
    empty: bool = False     # ok call but no content (a reasoning finder that spent its whole budget
    #                         thinking — billed, 0 findings; surfaced so it isn't silently a clean pass)


def _settle_cost(model: Model, res: OR.CallResult, estimate: float) -> float:
    """Prefer OpenRouter's billed cost; fall back to computing it from returned token counts; last
    resort the pre-call estimate. Never under-count."""
    if res.cost_usd is not None:
        return float(res.cost_usd)
    if res.prompt_tokens or res.completion_tokens:
        return model.cost(res.prompt_tokens, res.completion_tokens)
    return estimate


def run_finder(model: Model, shard: Shard, guard: SpendGuard) -> FinderResult:
    """One (model, shard) review. Reserves an estimate, calls, settles the real cost, parses findings
    and stamps each with the model + shard. A guard refusal returns skipped=True (no call made)."""
    estimate = model.cost(shard.est_tokens + 600, _EST_COMPLETION_TOKENS)
    try:
        guard.reserve(estimate)
    except BudgetExceeded as e:
        return FinderResult(model.id, shard.shard_id, [], ok=False, cost_usd=0.0,
                            error=str(e), skipped=True)

    body = {"model": model.id,
            "messages": [{"role": "system", "content": P.FINDER_SYSTEM},
                         P.finder_user_message(shard.render())],
            "response_format": FINDER_RESPONSE_FORMAT}
    actual = None
    try:
        res = OR.call(body, max_tokens=_REVIEW_MAX_TOKENS)
        actual = _settle_cost(model, res, estimate)
        if not res.ok:
            return FinderResult(model.id, shard.shard_id, [], ok=False, cost_usd=actual,
                                error=res.error or "call failed")
        if not (res.content or "").strip():
            # Billed but empty — the reasoning-drowned case. ok=True (the call itself succeeded) but
            # flagged so the run summary shows it produced nothing rather than a clean zero.
            return FinderResult(model.id, shard.shard_id, [], ok=True, cost_usd=actual, empty=True,
                                finish_reason=res.finish_reason, error="empty content (reasoning-only?)")
        findings = parse_findings(res.content)
        for f in findings:
            f.model = model.id
            f.shard_id = shard.shard_id
            if not f.file:                       # a finding with no path can't be filed — anchor to shard
                f.file = shard.rel_files()[0] if shard.files else ""
        # A non-empty reply that parsed to nothing is a possible parse-miss worth the audit trail; a
        # reply that parsed fine still keeps its raw content as a receipt (auditability, commandment #1).
        return FinderResult(model.id, shard.shard_id, findings, ok=True, cost_usd=actual,
                            raw_content=res.content, finish_reason=res.finish_reason)
    except OR.BillingAuthError:
        raise                                    # key/balance dead — the orchestrator must halt the run
    except Exception as e:                       # noqa: BLE001 — a per-call miss, never sinks the run
        return FinderResult(model.id, shard.shard_id, [], ok=False, cost_usd=actual or 0.0, error=str(e))
    finally:
        guard.settle(estimate, actual)
