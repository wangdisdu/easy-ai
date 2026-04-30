"""drop tb_tool_fingerprint: governance simplified to ACL + audit (no fingerprint / dual-signer)

Revision ID: 0007_drop_tool_fingerprint
Revises: 0006_drop_enable_long_session
Create Date: 2026-04-29 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_drop_tool_fingerprint"
down_revision: str | Sequence[str] | None = "0006_drop_enable_long_session"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("tb_tool_fingerprint")


def downgrade() -> None:
    op.create_table(
        "tb_tool_fingerprint",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tool_id", sa.BigInteger(), nullable=False),
        sa.Column("last_trusted_hash", sa.String(length=64), nullable=False),
        sa.Column("last_trusted_at", sa.BigInteger(), nullable=False),
        sa.Column("signers", sa.Text(), nullable=False),
        sa.Column("pending_hash", sa.String(length=64), nullable=True),
        sa.Column("pending_at", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("tool_id", name="uk_tb_tool_fingerprint_tool_id"),
    )
