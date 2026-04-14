"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-15 00:00:00

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 约定:
# - id / create_user / update_user / create_time / update_time 列在所有表中重复,
#   用下面的 helper 统一声明,避免 20 行 × 14 表的噪音。
# - 字符串列统一 VARCHAR(255) 或 TEXT,匹配 CLAUDE.md 的约束。


def _audit_cols() -> list[sa.Column]:
    return [
        sa.Column("create_time", sa.BigInteger, nullable=False),
        sa.Column("update_time", sa.BigInteger, nullable=False),
        sa.Column("create_user", sa.BigInteger, nullable=True),
        sa.Column("update_user", sa.BigInteger, nullable=True),
    ]


def _pk() -> sa.Column:
    return sa.Column("id", sa.BigInteger, primary_key=True)


def upgrade() -> None:
    op.create_table(
        "tb_user",
        _pk(),
        sa.Column("account", sa.String(255), nullable=False),
        sa.Column("passwd", sa.Text, nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(255), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("account", name="uk_tb_user_account"),
    )

    op.create_table(
        "tb_user_group",
        _pk(),
        sa.Column("code", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("code", name="uk_tb_user_group_code"),
    )

    op.create_table(
        "tb_user_group_member",
        _pk(),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("group_id", sa.BigInteger, nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("user_id", "group_id", name="uk_tb_user_group_member_user_group"),
    )

    op.create_table(
        "tb_role",
        _pk(),
        sa.Column("code", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("permissions", sa.Text, nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("code", name="uk_tb_role_code"),
    )

    op.create_table(
        "tb_user_role",
        _pk(),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("role_id", sa.BigInteger, nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("user_id", "role_id", name="uk_tb_user_role_user_role"),
    )

    op.create_table(
        "tb_mcp_server",
        _pk(),
        sa.Column("server_name", sa.String(255), nullable=False),
        sa.Column("transport", sa.String(255), nullable=False),
        sa.Column("endpoint_url", sa.Text, nullable=False),
        sa.Column("headers", sa.Text, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("server_status", sa.String(255), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("server_name", name="uk_tb_mcp_server_name"),
    )

    op.create_table(
        "tb_tool",
        _pk(),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("parameters", sa.Text, nullable=False),
        sa.Column("tool_group", sa.String(255), nullable=True),
        sa.Column("risk_level", sa.String(255), nullable=True),
        sa.Column("tool_status", sa.String(255), nullable=False),
        sa.Column("mcp_server_id", sa.BigInteger, nullable=True),
        sa.Column("api_config", sa.Text, nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "tb_skill",
        _pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("instruction", sa.Text, nullable=False),
        sa.Column("skill_status", sa.String(255), nullable=False),
        sa.Column("current_version", sa.String(255), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "tb_skill_tool",
        _pk(),
        sa.Column("skill_id", sa.BigInteger, nullable=False),
        sa.Column("tool_id", sa.BigInteger, nullable=False),
        sa.Column("tool_source", sa.String(255), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint(
            "skill_id", "tool_source", "tool_name", name="uk_tb_skill_tool_skill_source_name"
        ),
    )

    op.create_table(
        "tb_skill_version",
        _pk(),
        sa.Column("skill_id", sa.BigInteger, nullable=False),
        sa.Column("version", sa.String(255), nullable=False),
        sa.Column("version_note", sa.Text, nullable=True),
        sa.Column("skill_snapshot", sa.Text, nullable=True),
        sa.Column("published_time", sa.BigInteger, nullable=False),
        *_audit_cols(),
    )

    op.create_table(
        "tb_llm_provider",
        _pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider_type", sa.String(255), nullable=False),
        sa.Column("base_url", sa.Text, nullable=False),
        sa.Column("api_key", sa.Text, nullable=True),
        sa.Column("status", sa.String(255), nullable=False),
        sa.Column("last_check", sa.BigInteger, nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("name", name="uk_tb_llm_provider_name"),
    )

    op.create_table(
        "tb_llm_model",
        _pk(),
        sa.Column("provider_id", sa.BigInteger, nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("model_type", sa.String(255), nullable=False),
        sa.Column("status", sa.String(255), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("provider_id", "model", name="uk_tb_llm_model_provider_model"),
    )

    op.create_table(
        "tb_app",
        _pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("app_type", sa.String(255), nullable=False),
        sa.Column("app_status", sa.String(255), nullable=False),
        sa.Column("app_config", sa.Text, nullable=True),
        sa.Column("provider_id", sa.BigInteger, nullable=True),
        sa.Column("model_id", sa.BigInteger, nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("model_setting", sa.Text, nullable=True),
        sa.Column("access_scope", sa.String(255), nullable=False),
        sa.Column("rate_limit", sa.Integer, nullable=False),
        sa.Column("enable_log", sa.Integer, nullable=False),
        sa.Column("version_id", sa.String(255), nullable=True),
        sa.Column("current_version", sa.String(255), nullable=True),
        sa.Column("flowise_chatflow_id", sa.String(64), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "tb_app_tool",
        _pk(),
        sa.Column("app_id", sa.BigInteger, nullable=False),
        sa.Column("tool_id", sa.BigInteger, nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("app_id", "tool_id", name="uk_tb_app_tool_app_tool"),
    )

    op.create_table(
        "tb_app_skill",
        _pk(),
        sa.Column("app_id", sa.BigInteger, nullable=False),
        sa.Column("skill_id", sa.BigInteger, nullable=False),
        sa.Column("skill_name", sa.String(255), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("app_id", "skill_id", name="uk_tb_app_skill_app_skill"),
    )

    op.create_table(
        "tb_app_version",
        _pk(),
        sa.Column("app_id", sa.BigInteger, nullable=False),
        sa.Column("version", sa.String(255), nullable=False),
        sa.Column("version_note", sa.Text, nullable=True),
        sa.Column("app_snapshot", sa.Text, nullable=True),
        sa.Column("published_time", sa.BigInteger, nullable=False),
        *_audit_cols(),
    )

    op.create_table(
        "tb_app_log",
        _pk(),
        sa.Column("app_id", sa.BigInteger, nullable=True),
        sa.Column("app_type", sa.String(255), nullable=True),
        sa.Column("provider_id", sa.BigInteger, nullable=True),
        sa.Column("model_id", sa.BigInteger, nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("request_type", sa.String(255), nullable=False),
        sa.Column("request_payload", sa.Text, nullable=True),
        sa.Column("response_payload", sa.Text, nullable=True),
        sa.Column("success", sa.Integer, nullable=False),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("langfuse_trace_id", sa.String(255), nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        *_audit_cols(),
    )


def downgrade() -> None:
    for t in (
        "tb_app_log",
        "tb_app_version",
        "tb_app_skill",
        "tb_app_tool",
        "tb_app",
        "tb_llm_model",
        "tb_llm_provider",
        "tb_skill_version",
        "tb_skill_tool",
        "tb_skill",
        "tb_tool",
        "tb_mcp_server",
        "tb_user_role",
        "tb_role",
        "tb_user_group_member",
        "tb_user_group",
        "tb_user",
    ):
        op.drop_table(t)
