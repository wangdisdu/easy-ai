"""tb_skill 增加 emoji 列。

技能卡片可显示自定义 emoji 作为图标(可选,缺省走前端 fallback)。

Revision ID: 0025_skill_emoji
Revises: 0024_knowledge_v2
Create Date: 2026-05-26 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_skill_emoji"
down_revision: str | Sequence[str] | None = "0024_knowledge_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tb_skill", sa.Column("emoji", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("tb_skill", "emoji")
