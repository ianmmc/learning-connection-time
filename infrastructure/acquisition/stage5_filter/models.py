"""PRECIOUS Stage-5 tables as SQLAlchemy models on the governance Base (REQ-103).

These hold HUMAN decisions that must survive re-ingest and never be casually dropped:
  - label         — the ground-truth labels (primary_label + flags + note) keyed on rec_key
  - cluster_split — records the reviewer pulled out of an auto-cluster (a durable override)

They get models + create_all (vs the regenerable cache tables' drop/rebuild DDL) precisely
because they're precious and stable. Both are also backed to version-controlled JSON
(labels.json / cluster_splits.json) and re-imported on ingest — that JSON remains the
engine-independent, git-diffable source of truth; these tables are the queryable live copy.
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common.db import Base


class Label(Base):
    __tablename__ = "label"

    rec_key: Mapped[str] = mapped_column(String, primary_key=True)
    primary_label: Mapped[str | None] = mapped_column(String)
    flags_json: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="unlabeled")
    updated_at: Mapped[str | None] = mapped_column(String)


class ClusterSplit(Base):
    __tablename__ = "cluster_split"

    rec_key: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[str | None] = mapped_column(String)
