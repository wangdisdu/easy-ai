"""沙盒镜像配置表 tb_sandbox_image。

平台级镜像目录,Agent 应用在 app_config.sandbox.image_id 里从中选一个作为
沙盒镜像;未选则用 is_default 的那条。add-only,不回填数据。

详见 docs/sandbox-design.md §7。

Revision ID: 0015_sandbox_image
Revises: 0014_kb_category
Create Date: 2026-05-19 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_sandbox_image"
down_revision: str | Sequence[str] | None = "0014_kb_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_sandbox_image",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        # 容器镜像引用,如 python:3.12-slim 或 registry.example.com/ns/img:tag
        sa.Column("image", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # 默认资源画像,透传 OpenSandbox create(resource=...);空=不限制。
        # 形如 cpu="1"/"0.5"、memory="512Mi"/"2Gi"。
        sa.Column("cpu", sa.String(length=64), nullable=True),
        sa.Column("memory", sa.String(length=64), nullable=True),
        # 1 = app 未显式选镜像时的兜底
        sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("name", name="uk_tb_sandbox_image_name"),
    )


def downgrade() -> None:
    op.drop_table("tb_sandbox_image")
