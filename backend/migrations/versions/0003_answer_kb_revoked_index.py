"""Add a covering index on answer(knowledge_base_id, revoked, knowledge_point_id).

`list_knowledge_points` (issue #4) counts active answers per knowledge point
with `WHERE knowledge_base_id = ? AND revoked = 0 GROUP BY
knowledge_point_id`. Neither existing index on `answer` leads with
knowledge_base_id (`ix_answer_resolve` and the FK index both lead with
knowledge_point_id), so that query would require a full table scan as the
table grows. Found by the Kimi review gate on PR #20.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_answer_kb_revoked_kp",
        "answer",
        ["knowledge_base_id", "revoked", "knowledge_point_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_answer_kb_revoked_kp", table_name="answer")
