#!/usr/bin/env python3
"""Discovered domains — human-confirmed scoping domains a GEO discovery run derived (#164).

NCES CCD is authoritative and NEVER hand-edited; a district whose NCES WEBSITE is blank/junk can
still have a real, working domain (Millard 3173740 → mpsomaha.org, the #227/#229 motivating case).
A geo-scoped Stage-2 run derives a majority host from its result tally (discover.derive_domain);
that derivation is a PROPOSAL, surfaced with its full tally receipt, and becomes a row here only
on explicit human confirmation — the same propose-with-evidence/human-decides discipline as
CMS_HOSTS additions.

A confirmed row is a THIRD, clearly-labeled domain source (auditor-facing name: "discovered
domain"): the #229 admission guard accepts NCES-domain OR confirmed-discovered-domain, and every
batch receipt records WHICH source scoped it. The deriving run's discovery.json receipt keeps the
raw tally; this table is the working store; the git twin (paths.DISCOVERED_DOMAINS_JSON) is the
tracked backup. Design authority: issue #164's AGREED DESIGN (2026-07-19).
"""
from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb  # noqa: E402  (base-layer common→common import)
from infrastructure.acquisition.common.timeutil import utcnow as _now


class DiscoveredDomain(gdb.Base):
    """PRECIOUS human-confirmed discovered domain — one per district (a re-confirmation upserts,
    the receipt trail of the superseded value living in git history + the deriving receipts)."""
    __tablename__ = "discovered_domain"
    district_id: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String)
    derived_in_batch: Mapped[str] = mapped_column(String, default="")   # the geo batch whose tally proposed it
    tally_json: Mapped[dict] = mapped_column(JSON, default=dict)        # the host-tally receipt at confirmation
    confirmed_by: Mapped[str] = mapped_column(String)
    confirmed_at: Mapped[str] = mapped_column(String, default=_now)


class DiscoveredDomainDecision(gdb.Base):
    """PRECIOUS append-only decision log for derived-domain PROPOSALS (#572, the training corpus):
    every human confirm AND reject, with the tally receipt as its evidence. Confirmations
    additionally upsert the operative `discovered_domain` row; rejections live only here — the
    negative class the future auto-confirmation (a gate_mode ramp-up candidate) trains on.
    Disagreement is the primary product (the labeling-serves-learning principle)."""
    __tablename__ = "discovered_domain_decision"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String)
    domain: Mapped[str] = mapped_column(String)                        # the PROPOSED host
    decision: Mapped[str] = mapped_column(String)                      # 'confirm' | 'reject'
    reason: Mapped[str] = mapped_column(String, default="")            # required for reject
    derived_in_batch: Mapped[str] = mapped_column(String, default="")
    tally_json: Mapped[dict] = mapped_column(JSON, default=dict)       # the evidence at decision time
    actor: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=_now)


def record_decision(con, district_id: str, domain: str, decision: str, *, reason: str = "",
                    derived_in_batch: str = "", tally: dict | None = None,
                    actor: str) -> DiscoveredDomainDecision:
    """Append one proposal decision (confirm/reject) to the training corpus. Append-only —
    a changed mind is a NEW row (the history is the point)."""
    if decision not in ("confirm", "reject"):
        raise ValueError(f"decision must be 'confirm' or 'reject' (got {decision!r})")
    if decision == "reject" and not reason.strip():
        raise ValueError("a rejection needs a reason — it is the training signal")
    row = DiscoveredDomainDecision(
        district_id=district_id, domain=domain, decision=decision, reason=reason.strip(),
        derived_in_batch=derived_in_batch, tally_json=tally or {}, actor=actor)
    con.add(row)
    con.flush()
    return row


def latest_decisions(con, district_ids: list) -> dict:
    """{district_id: {decision, domain, reason, actor, created_at}} — the LATEST decision per
    district among `district_ids` (the Stage-2 card's 'already decided' state)."""
    if not district_ids:
        return {}
    out: dict = {}
    for r in (con.query(DiscoveredDomainDecision)
                 .filter(DiscoveredDomainDecision.district_id.in_(list(district_ids)))
                 .order_by(DiscoveredDomainDecision.id)):
        out[r.district_id] = {"decision": r.decision, "domain": r.domain, "reason": r.reason,
                              "actor": r.actor, "created_at": r.created_at}
    return out


def confirm(con, district_id: str, domain: str, *, derived_in_batch: str = "",
            tally: dict | None = None, actor: str) -> DiscoveredDomain:
    """Record a human confirmation (upsert — a district has ONE current discovered domain)."""
    from infrastructure.acquisition.common.discover import is_scoping_domain
    if not is_scoping_domain(domain):
        raise ValueError(f"not a usable scoping domain: {domain!r}")
    row = con.get(DiscoveredDomain, district_id)
    if row is None:
        row = DiscoveredDomain(district_id=district_id)
        con.add(row)
    row.domain = domain
    row.derived_in_batch = derived_in_batch
    row.tally_json = tally or {}
    row.confirmed_by = actor
    row.confirmed_at = _now()
    con.flush()
    return row


def get_domain(con, district_id: str) -> str | None:
    """The confirmed discovered domain for a district, or None."""
    row = con.get(DiscoveredDomain, district_id)
    return row.domain if row else None


def all_confirmed(con) -> dict:
    """district_id -> domain for every confirmed row (the #229 guard's second admission source)."""
    return {r.district_id: r.domain for r in con.query(DiscoveredDomain).all()}
