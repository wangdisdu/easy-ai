"""memory KV: tb_memory + tb_memory_audit (scope=user|app)

Revision ID: 0009_memory_kv
Revises: 0008_tool_hitl_timeout
Create Date: 2026-04-30 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_memory_kv"
down_revision: str | Sequence[str] | None = "0008_tool_hitl_timeout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_memory",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("memory_key", sa.String(length=255), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("scope", "scope_id", "memory_key", name="uk_tb_memory_scope_key"),
    )
    # 注入查询主路径：按 scope+scope_id 取最近 N 条
    op.create_index(
        "ix_tb_memory_scope_update",
        "tb_memory",
        ["scope", "scope_id", sa.text("update_time DESC")],
    )

    op.create_table(
        "tb_memory_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.BigInteger(), nullable=False),
        sa.Column("memory_key", sa.String(length=255), nullable=False),
        sa.Column("memory_value_before", sa.Text(), nullable=True),
        sa.Column("memory_value_after", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("app_id", sa.BigInteger(), nullable=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_tb_memory_audit_scope_time",
        "tb_memory_audit",
        ["scope", "scope_id", "create_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_tb_memory_audit_scope_time", table_name="tb_memory_audit")
    op.drop_table("tb_memory_audit")
    op.drop_index("ix_tb_memory_scope_update", table_name="tb_memory")
    op.drop_table("tb_memory")
