"""应用集成(对外 API 网关)四张表。

详见 docs/application-integration-design.md §11。

- tb_integration:集成应用主表
- tb_integration_key:API Key,key_hash 全局唯一(SHA-256),明文不入库
- tb_integration_app:绑定关系,(integration_id, app_type, app_id) 复合主键
- tb_integration_quota_day:日配额持久化,进程重启后从此表 hydrate

Revision ID: 0019_integration
Revises: 0018_seed_sandbox_image
Create Date: 2026-05-20 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_integration"
down_revision: str | Sequence[str] | None = "0018_seed_sandbox_image"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_integration",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # active / disabled,创建即 active,无 draft 中间态
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        # 三态:NULL=继承全局默认,0=不限,>0=具体阈值
        sa.Column("quota", sa.Integer(), nullable=True),
        sa.Column("rate_limit", sa.Integer(), nullable=True),
        # 调用超时(秒),NULL=继承全局默认
        sa.Column("timeout", sa.Integer(), nullable=True),
        # 逗号分隔 IP 白名单,空=不限制
        sa.Column("whitelist", sa.Text(), nullable=True),
        # 过期时间(Unix ms),NULL=永不过期
        sa.Column("expire_at", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("name", name="uk_tb_integration_name"),
    )
    op.create_index(
        "idx_tb_integration_status", "tb_integration", ["status", "deleted_at"]
    )

    op.create_table(
        "tb_integration_key",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("integration_id", sa.BigInteger(), nullable=False),
        # 前缀(用于列表显示,如 sk-prod-9f3)
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        # 末尾(用于列表显示,如 xY2k),与 prefix 拼出 sk-prod-9f3****xY2k
        sa.Column("key_suffix", sa.String(length=16), nullable=False),
        # 完整 Key 的 SHA-256,**不存明文**
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        # active / disabled
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        # NULL=继承 Integration 级
        sa.Column("rate_limit", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.BigInteger(), nullable=True),
        # 重置时打标记,旧 hash 立即失效
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("key_hash", name="uk_tb_integration_key_hash"),
    )
    op.create_index(
        "idx_tb_integration_key_intg",
        "tb_integration_key",
        ["integration_id", "deleted_at"],
    )

    op.create_table(
        "tb_integration_app",
        sa.Column("integration_id", sa.BigInteger(), nullable=False),
        # app_type 进主键以避免跨表 ID 冲突(P1 的 kb_push 指向知识库表,而非应用表)
        sa.Column("app_type", sa.String(length=32), nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "integration_id", "app_type", "app_id", name="pk_tb_integration_app"
        ),
    )
    op.create_index(
        "idx_tb_integration_app_lookup",
        "tb_integration_app",
        ["app_type", "app_id"],
    )

    op.create_table(
        "tb_integration_quota_day",
        sa.Column("integration_id", sa.BigInteger(), nullable=False),
        # yyyymmdd
        sa.Column("day", sa.String(length=8), nullable=False),
        sa.Column("day_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("integration_id", "day", name="pk_tb_integration_quota_day"),
    )


def downgrade() -> None:
    op.drop_table("tb_integration_quota_day")
    op.drop_index("idx_tb_integration_app_lookup", table_name="tb_integration_app")
    op.drop_table("tb_integration_app")
    op.drop_index("idx_tb_integration_key_intg", table_name="tb_integration_key")
    op.drop_table("tb_integration_key")
    op.drop_index("idx_tb_integration_status", table_name="tb_integration")
    op.drop_table("tb_integration")
