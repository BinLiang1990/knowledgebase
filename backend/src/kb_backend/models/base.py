from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# Microsecond precision (fsp=6) — plain MySQL DATETIME has whole-second
# resolution, so two rows written within the same second get identical
# created_at values. That breaks the "effective_time DESC, created_at DESC"
# tie-break the resolve algorithm (docs/PRD.md §4.6.1) depends on to pick a
# deterministic winner. Found by the Codex outer-gate review on PR #17.
def created_at_column() -> Mapped[datetime]:
    return mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))


# SQLAlchemy's `server_onupdate=` is Python-side metadata only for MySQL — it
# is never rendered into CREATE TABLE DDL, so a raw SQL UPDATE (bypassing the
# ORM) would silently leave `updated_at` stale. MySQL's DDL syntax folds
# "ON UPDATE ..." into the same DEFAULT clause, so it has to be spelled out in
# the server_default text itself. Also found by the Codex outer-gate review.
def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )
