"""system setting: tb_system_setting

平台级 key-value 配置表。当前 M1.5 仅用于存 AI 基础设施默认指针
(ai.default.embedding_model_id 等),后续按需扩展更多 key。

Revision ID: 0012_system_setting
Revises: 0011_knowledge
Create Date: 2026-05-14 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_system_setting"
down_revision: str | Sequence[str] | None = "0011_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_system_setting",
        sa.Column("setting_key", sa.String(length=128), primary_key=True),
        sa.Column("setting_value", sa.Text(), nullable=True),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("tb_system_setting")
