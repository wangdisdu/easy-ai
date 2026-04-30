"""tool governance: tb_tool_policy + tb_tool_fingerprint + tb_tool_audit

Revision ID: 0005_tool_governance
Revises: 0004_llm_model_max_input_tokens
Create Date: 2026-04-26 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_tool_governance"
down_revision: str | Sequence[str] | None = "0004_llm_model_max_input_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 工具策略规则集
    op.create_table(
        "tb_tool_policy",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tool_id", sa.BigInteger(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("when_ast", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="shadow"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("superseded_by_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
    )
    # PolicyMiddleware 运行期主查询：按 tool 取当前版本规则按 priority 排序
    op.create_index(
        "ix_tb_tool_policy_tool_active",
        "tb_tool_policy",
        ["tool_id", "superseded_by_id", "priority"],
    )

    # 工具指纹
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

    # 工具治理审计流（append-only）
    op.create_table(
        "tb_tool_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("tool_id", sa.BigInteger(), nullable=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("app_id", sa.BigInteger(), nullable=True),
        sa.Column("parameters_snapshot", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("matched_rule_id", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
    )
    # 治理大盘按工具 / 时间筛
    op.create_index(
        "ix_tb_tool_audit_tool_time",
        "tb_tool_audit",
        ["tool_id", "create_time"],
    )
    # 单会话审计追溯
    op.create_index(
        "ix_tb_tool_audit_conv_time",
        "tb_tool_audit",
        ["conversation_id", "create_time"],
    )

    # 复用 tb_tool.risk_level：把存量空值回填默认 'low'。
    # service 层已校验枚举（VALID_RISK_LEVELS），存量数据这次保险落实。
    op.execute("UPDATE tb_tool SET risk_level = 'low' WHERE risk_level IS NULL OR risk_level = ''")


def downgrade() -> None:
    op.drop_index("ix_tb_tool_audit_conv_time", table_name="tb_tool_audit")
    op.drop_index("ix_tb_tool_audit_tool_time", table_name="tb_tool_audit")
    op.drop_table("tb_tool_audit")
    op.drop_table("tb_tool_fingerprint")
    op.drop_index("ix_tb_tool_policy_tool_active", table_name="tb_tool_policy")
    op.drop_table("tb_tool_policy")
    # 不回滚 risk_level 回填（数据修复后保留）
