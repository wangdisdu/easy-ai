"""drop tb_app.enable_long_session: long session is now default-on for all agent apps

Revision ID: 0006_drop_enable_long_session
Revises: 0005_tool_governance
Create Date: 2026-04-27 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_drop_enable_long_session"
down_revision: str | Sequence[str] | None = "0005_tool_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tb_app", "enable_long_session")


def downgrade() -> None:
    op.add_column(
        "tb_app",
        sa.Column(
            "enable_long_session",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
