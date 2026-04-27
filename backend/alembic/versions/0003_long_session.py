"""long session checkpointer groundwork

Revision ID: 0003_long_session
Revises: 0002_add_query_indexes
Create Date: 2026-04-24 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_long_session"
down_revision: str | Sequence[str] | None = "0002_add_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # LangGraph checkpoint 相关表统一建在独立 schema；表本体由 AsyncPostgresSaver.setup()
    # 在 FastAPI lifespan 启动时幂等创建（内部 checkpoint_migrations 版本表管理）。
    op.execute("CREATE SCHEMA IF NOT EXISTS lg_checkpoint")

    # tb_app：长会话总开关，默认关闭保留老行为。
    op.add_column(
        "tb_app",
        sa.Column(
            "enable_long_session",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # tb_conversation：线程标识 + checkpoint 生命周期状态。
    op.add_column(
        "tb_conversation",
        sa.Column("thread_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tb_conversation",
        sa.Column(
            "checkpoint_status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
    )
    op.create_unique_constraint(
        "uk_tb_conversation_thread_id", "tb_conversation", ["thread_id"]
    )

    # 会话审计事件表：checkpoint 重建 / 清理等，后续 Policy 层审计流也可复用。
    op.create_table(
        "tb_session_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_tb_session_audit_conv",
        "tb_session_audit",
        ["conversation_id", "create_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_tb_session_audit_conv", table_name="tb_session_audit")
    op.drop_table("tb_session_audit")
    op.drop_constraint("uk_tb_conversation_thread_id", "tb_conversation", type_="unique")
    op.drop_column("tb_conversation", "checkpoint_status")
    op.drop_column("tb_conversation", "thread_id")
    op.drop_column("tb_app", "enable_long_session")
    # 不在 downgrade 里删 lg_checkpoint schema，避免误伤已有 checkpoint 数据。
    # 如需彻底回退，手动 DROP SCHEMA lg_checkpoint CASCADE。
