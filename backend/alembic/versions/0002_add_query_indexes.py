"""add query indexes

Revision ID: 0002_add_query_indexes
Revises: 0001_initial
Create Date: 2026-04-21 00:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_add_query_indexes"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_tb_conversation_user_status_update_time",
        "tb_conversation",
        ["user_id", "status", "update_time"],
    )
    op.create_index(
        "ix_tb_conversation_app_id",
        "tb_conversation",
        ["app_id"],
    )
    op.create_index(
        "ix_tb_conversation_message_conversation_time",
        "tb_conversation_message",
        ["conversation_id", "create_time"],
    )
    op.create_index(
        "ix_tb_app_log_create_time",
        "tb_app_log",
        ["create_time"],
    )
    op.create_index(
        "ix_tb_app_log_app_time",
        "tb_app_log",
        ["app_id", "create_time"],
    )
    op.create_index(
        "ix_tb_app_log_model_time",
        "tb_app_log",
        ["model", "create_time"],
    )
    op.create_index(
        "ix_tb_app_type_status_create_time",
        "tb_app",
        ["app_type", "app_status", "create_time"],
    )
    op.create_index(
        "ix_tb_app_tool_app_id",
        "tb_app_tool",
        ["app_id"],
    )
    op.create_index(
        "ix_tb_app_skill_app_id",
        "tb_app_skill",
        ["app_id"],
    )
    op.create_index(
        "ix_tb_skill_tool_skill_id",
        "tb_skill_tool",
        ["skill_id"],
    )
    op.create_index(
        "ix_tb_user_role_role_user",
        "tb_user_role",
        ["role_id", "user_id"],
    )
    op.create_index(
        "ix_tb_user_group_member_group_user",
        "tb_user_group_member",
        ["group_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tb_user_group_member_group_user", table_name="tb_user_group_member")
    op.drop_index("ix_tb_user_role_role_user", table_name="tb_user_role")
    op.drop_index("ix_tb_skill_tool_skill_id", table_name="tb_skill_tool")
    op.drop_index("ix_tb_app_skill_app_id", table_name="tb_app_skill")
    op.drop_index("ix_tb_app_tool_app_id", table_name="tb_app_tool")
    op.drop_index("ix_tb_app_type_status_create_time", table_name="tb_app")
    op.drop_index("ix_tb_app_log_model_time", table_name="tb_app_log")
    op.drop_index("ix_tb_app_log_app_time", table_name="tb_app_log")
    op.drop_index("ix_tb_app_log_create_time", table_name="tb_app_log")
    op.drop_index(
        "ix_tb_conversation_message_conversation_time",
        table_name="tb_conversation_message",
    )
    op.drop_index("ix_tb_conversation_app_id", table_name="tb_conversation")
    op.drop_index("ix_tb_conversation_user_status_update_time", table_name="tb_conversation")
