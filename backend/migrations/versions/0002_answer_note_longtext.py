"""Widen answer.note from TEXT to LONGTEXT.

docs/PRD.md §4.5 校验规则: content/note 均不设长度上限. `content` was already
LONGTEXT from issue #1, but `note` was left as plain TEXT (65,535-byte cap) —
a note longer than that would raise a raw DB error at commit instead of the
documented "no limit" behavior. Found by the Codex outer-gate review on
PR #20 (round 5).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "answer",
        "note",
        existing_type=sa.Text(),
        type_=mysql.LONGTEXT(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "answer",
        "note",
        existing_type=mysql.LONGTEXT(),
        type_=sa.Text(),
        existing_nullable=True,
    )
