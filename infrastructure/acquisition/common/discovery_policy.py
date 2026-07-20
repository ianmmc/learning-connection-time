#!/usr/bin/env python3
"""Discovery-scope policy — the #164 control surface for GEO-scoped first-run composition.

One governance setting, `discovery_scope_policy`, governing FIRST-RUN batch composition ONLY
(the 5->1 / 7->1 escalation loops are failure-driven follow-ups, individually gate@1'd, and are
deliberately NOT gated here — otherwise the conservative default would block the very repair
mechanism that makes it safe to stay conservative). Four positions, in escalation order:

  1. domain_only      -- geo first-run composition refused (the high-supervision default)
  2. geo_for_blank    -- geo first-runs ALLOWED for blank-domain districts; operator picks per batch
  3. geo_interleaved  -- the standard draw picks each batch's scope probabilistically, weighted by
                         the remaining blank-domain vs domained populations (batch records the draw)
  4. geo_all          -- geo composition allowed for ANY district (the measured geo-vs-domain
                         comparison mode; feeds #118's attribution)

AUDIT-FIRST STORE: the table is an append-only EVENT LOG (policy changes are governance decisions);
the current policy is simply the latest row, an empty table reads as `domain_only`. `advance_one_step`
is the #164 auto-advance: exactly domain_only -> geo_for_blank (never further), for the moment the
domain-scoped eligible pool drains — auto-act compliant (observable via the event row + console
notice, reversible via set_policy). Design authority: issue #164's AGREED DESIGN (2026-07-19).
"""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb  # noqa: E402  (base-layer common→common import)
from infrastructure.acquisition.common.timeutil import utcnow as _now

POLICIES = ("domain_only", "geo_for_blank", "geo_interleaved", "geo_all")
DEFAULT_POLICY = "domain_only"     # high-supervision-first


class DiscoveryPolicyEvent(gdb.Base):
    """PRECIOUS append-only policy-change event. Current policy == the latest row; empty table ==
    DEFAULT_POLICY. `trigger` records WHY (a human set it / the pool-drained auto-advance)."""
    __tablename__ = "discovery_policy_event"
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy: Mapped[str] = mapped_column(String)
    previous: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    trigger: Mapped[str] = mapped_column(String, default="")   # e.g. 'human', 'auto-advance: pool drained (N left)'
    created_at: Mapped[str] = mapped_column(String, default=_now)


def get_policy(con) -> str:
    """The current policy: the latest event row, or DEFAULT_POLICY for an empty table."""
    row = con.query(DiscoveryPolicyEvent).order_by(DiscoveryPolicyEvent.event_id.desc()).first()
    return row.policy if row else DEFAULT_POLICY


def set_policy(con, policy: str, *, actor: str, trigger: str = "human") -> str:
    """Append a policy-change event (idempotent no-op when unchanged — no event spam).
    Serialized via a transaction-scoped advisory lock (#568 review): the pool-drain
    auto-advance is a genuine second writer alongside a human console set, and an
    unserialized read-modify-append could fork the audit chain's `previous` linkage."""
    from sqlalchemy import text as _text
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES} (got {policy!r})")
    con.execute(_text("SELECT pg_advisory_xact_lock(hashtext('discovery_scope_policy'))"))
    previous = get_policy(con)
    if policy == previous:
        return policy
    con.add(DiscoveryPolicyEvent(policy=policy, previous=previous, actor=actor, trigger=trigger))
    con.flush()
    return policy


def advance_one_step(con, *, actor: str, trigger: str) -> str | None:
    """The #164 auto-advance: domain_only -> geo_for_blank, exactly one step, never further —
    any other current position is a no-op (returns None). The caller supplies the evidence
    string (e.g. 'domain-scoped eligible pool exhausted; 2,409 blank-domain districts remain')."""
    if get_policy(con) != "domain_only":
        return None
    return set_policy(con, "geo_for_blank", actor=actor, trigger=f"auto-advance: {trigger}")
