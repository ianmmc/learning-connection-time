"""Stage 8 precious DB model: the gate@8 approval record (STAGE8_AGGREGATE_DESIGN §2b/§2c/§2e).

`stage8_approval` = one human decision on a district's whole closing argument — the attorney's-closing-
argument verdict. Commit grain is PER-DISTRICT, all-or-nothing (§2e): LCT is a district-level metric, so a
band is never published alone. Each row FREEZES the closing argument it acted on (`receipt_json`, self-
contained + offline-auditable, the immutable-handoff discipline) + a `facts_fingerprint` so a later
re-extraction that changes the picture makes the approval detectably stale. A re-decision after a back-edge
round is a NEW row — history is append-only, never rewritten.

PRECIOUS (a human governance decision — never in the Stage-5 ingest drop list; git-backed to
`stage8_approvals.json`), governance DB only. Registered on the governance `Base`; created via
`init_precious_schema()` once the app (or the Stage-8 path) imports this module.
"""
from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common.timeutil import utcnow


class Stage8Approval(gdb.Base):
    """One gate@8 decision on a district. `disposition`: 'approved' (Stage 9 may write all bands) or
    'sent_back' (a band is unsatisfied / the picture was rejected → an 8→1/8→6 back-edge; a reason is
    required). Append-only: the LATEST row per district is the live decision."""
    __tablename__ = "stage8_approval"

    approval_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    disposition: Mapped[str] = mapped_column(String)                 # approved | sent_back
    actor: Mapped[str] = mapped_column(String)                       # 'ian' | 'auto:...'
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # required for sent_back; optional note on approve
    facts_fingerprint: Mapped[str] = mapped_column(String)          # closing_argument.fingerprint() at decision time
    receipt_json: Mapped[str] = mapped_column(Text)                 # the frozen closing-argument snapshot
    created_at: Mapped[str] = mapped_column(String, default=utcnow)


# newest-decision-per-district lookup (the console badge + Stage-9 eligibility both hit this)
Index("ix_stage8_approval_latest", Stage8Approval.district_id, Stage8Approval.approval_id.desc())


class BandExclusion(gdb.Base):
    """#257: a standing human 'exclude school from band' decision — the fact's OBSERVATION is correct
    but its band membership is stale (the temporal grade-reconfiguration class: enrollment is 2023-24,
    bell schedules are 2025-26, and a school can re-span in between — Coffee County's Kinston/Zion
    Chapel). DISTRICT-grain, keyed (district_id, band, norm_school), deliberately NOT fact-grain: the
    knowledge 'it's a high school now, I checked the site' is about the school, so it must survive a
    follow-up re-extraction minting new fact rows — a fact-attached exclusion would silently vanish and
    re-pollute the band. Applied at closing-argument build time (excluded facts leave the band's
    mode/count, stay visible struck-through); frozen into every gate@8 receipt; reversible before freeze
    by deleting the row (the receipts preserve what was operative at each decision).

    PRECIOUS (a human governance decision — git-backed to band_exclusions.json, swept by pre-commit)."""
    __tablename__ = "band_exclusion"

    exclusion_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    band: Mapped[str] = mapped_column(String)                        # elementary | middle | high
    norm_school: Mapped[str] = mapped_column(String)                 # school_match.norm_school key (the merge axis)
    school: Mapped[str] = mapped_column(String)                      # display name as the reviewer saw it
    reason: Mapped[str] = mapped_column(Text)                        # REQUIRED — the resolving knowledge
    actor: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)


# one standing exclusion per (district, band, school) — re-excluding replaces, restoring deletes
Index("ux_band_exclusion_key", BandExclusion.district_id, BandExclusion.band,
      BandExclusion.norm_school, unique=True)


class HumanAddedFact(gdb.Base):
    """#474: a hand-entered (school, band, start, end) — the LAST-RESORT fallback when targeted
    re-extraction (#473) cannot recover a band the reviewer can see in a captured artifact. Single-
    source and unvalidated by the council, so every row REQUIRES a cited source artifact/URL (the
    audit trail, commandment #1) and passes the same gross/plausibility gate as extracted values.
    Votes in the band mode like any human determination (§2a.3); rendered visibly tagged
    'human-added + source', mirroring #257's never-out-of-sight treatment. DISTRICT-grain like
    BandExclusion (survives re-extraction); removing = DELETE (history lives in the frozen receipts).

    PRECIOUS (git-backed to human_added_facts.json, swept by pre-commit)."""
    __tablename__ = "human_added_fact"

    added_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    band: Mapped[str] = mapped_column(String)                        # elementary | middle | high
    norm_school: Mapped[str] = mapped_column(String)
    school: Mapped[str] = mapped_column(String)
    start_time: Mapped[str] = mapped_column(String)
    end_time: Mapped[str] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(Text)                    # REQUIRED — the cited artifact
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)


# one hand-entry per (district, band, school) — re-adding replaces, removing deletes
Index("ux_human_added_fact_key", HumanAddedFact.district_id, HumanAddedFact.band,
      HumanAddedFact.norm_school, unique=True)
