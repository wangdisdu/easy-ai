"""tb_tool.hitl_timeout_seconds: per-tool HITL 等待上限，NULL 走全局 default

Revision ID: 0008_tool_hitl_timeout
Revises: 0007_drop_tool_fingerprint
Create Date: 2026-04-29 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_tool_hitl_timeout"
down_revision: str | Sequence[str] | None = "0007_drop_tool_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tb_tool",
        sa.Column("hitl_timeout_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tb_tool", "hitl_timeout_seconds")
