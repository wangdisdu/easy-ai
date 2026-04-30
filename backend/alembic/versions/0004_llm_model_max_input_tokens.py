"""add max_input_tokens to tb_llm_model

Revision ID: 0004_llm_model_max_input_tokens
Revises: 0003_long_session
Create Date: 2026-04-25 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_llm_model_max_input_tokens"
down_revision: str | Sequence[str] | None = "0003_long_session"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tb_llm_model",
        sa.Column("max_input_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tb_llm_model", "max_input_tokens")
