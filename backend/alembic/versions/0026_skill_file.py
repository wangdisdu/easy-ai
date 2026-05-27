"""新表 tb_skill_file:技能捆绑文件(references/scripts/templates/assets)。

每个技能除主文档 SKILL.md(存 tb_skill.instruction)外,
还可以附带 4 类辅助文件:
- references: 参考文档(渐进披露,运行时按需 read)
- scripts:   脚本(物化进沙箱可执行)
- templates: 模板
- assets:    资源

rel_path 首段决定 kind;路径合法性在 service 层强校验。

Revision ID: 0026_skill_file
Revises: 0025_skill_emoji
Create Date: 2026-05-26 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_skill_file"
down_revision: str | Sequence[str] | None = "0025_skill_emoji"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_skill_file",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("rel_path", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("executable", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("skill_id", "rel_path", name="uk_tb_skill_file_skill_path"),
    )
    op.create_index("idx_tb_skill_file_skill", "tb_skill_file", ["skill_id"])


def downgrade() -> None:
    op.drop_index("idx_tb_skill_file_skill", table_name="tb_skill_file")
    op.drop_table("tb_skill_file")
