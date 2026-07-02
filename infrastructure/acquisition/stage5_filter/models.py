"""PRECIOUS Stage-5 tables as SQLAlchemy models on the governance Base (REQ-103).

These hold HUMAN decisions that must survive re-ingest and never be casually dropped:
  - label         — the ground-truth labels (primary_label + flags + note) keyed on rec_key
  - cluster_split — records the reviewer pulled out of an auto-cluster (a durable override)
  - followup_flag — a "needs manual follow-up, do X" directive on a district or a record (the top
                    attention tier; the whole point of gate@5). PRECIOUS — backed to JSON like labels.
  - saved_view    — a named left-pane preset (group/filter/sort). Persistent UI convenience, NOT
                    pipeline state, so it survives re-ingest but is not git-backed.

They get models + create_all (vs the regenerable cache tables' drop/rebuild DDL) precisely
because they're precious/persistent and stable. label/cluster_split/followup_flag are also backed
to version-controlled JSON and re-imported on ingest — that JSON remains the engine-independent,
git-diffable source of truth; these tables are the queryable live copy.
"""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common.db import Base


class Label(Base):
    __tablename__ = "label"

    rec_key: Mapped[str] = mapped_column(String, primary_key=True)
    primary_label: Mapped[str | None] = mapped_column(String)
    # LEGACY (v2.0) — inert archive. Values were folded into facets_json by migrate_label_v21
    # (the human `duplicate` flag retired outright: programmatic dedup — record.duplicate_of +
    # near-dup clustering — owns that). No live code reads or writes this column; kept only so
    # historical values and the migration path survive. Do not resurrect.
    flags_json: Mapped[str | None] = mapped_column(String)
    # facets_json (REQ-114): the V2 facet questionnaire — detector-mirroring tri-state answers + a structured
    # 'where' + harvest_pages_labeled. Additive to primary_label; precious + JSON-backed like the rest.
    facets_json: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(String)
    # server_default mirrors the original sqlite `DEFAULT 'unlabeled'` so the ingest's raw
    # `INSERT INTO label (rec_key)` gets the default at the DB (not just the ORM) — REQ-103.
    status: Mapped[str] = mapped_column(String, default="unlabeled", server_default="unlabeled")
    updated_at: Mapped[str | None] = mapped_column(String)


class ClusterSplit(Base):
    __tablename__ = "cluster_split"

    rec_key: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[str | None] = mapped_column(String)


class FollowupFlag(Base):
    """A human "needs manual follow-up" directive — the top attention tier (gate@5's reason to exist).
    `scope` is 'district' or 'record'; `target_id` is the district_id or rec_key. `directive` is the
    free-text "what to do." An unresolved flag (resolved_at IS NULL) floors the target's attention."""
    __tablename__ = "followup_flag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String)            # 'district' | 'record'
    target_id: Mapped[str] = mapped_column(String)        # district_id or rec_key
    district_id: Mapped[str] = mapped_column(String)      # denormalized for the district rollup join
    directive: Mapped[str | None] = mapped_column(String)
    actor: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str | None] = mapped_column(String)
    resolved_at: Mapped[str | None] = mapped_column(String)


class SavedView(Base):
    """A named left-pane preset (group/filter/sort config_json), per actor. Persistent UI convenience."""
    __tablename__ = "saved_view"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str | None] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    config_json: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str | None] = mapped_column(String)
