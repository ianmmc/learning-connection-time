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
from sqlalchemy import JSON, String
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
