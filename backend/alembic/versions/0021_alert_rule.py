"""可观测性告警规则与触发记录表 tb_alert_rule / tb_alert_record。

tb_alert_rule  — 告警规则,由告警评估器周期扫描。
tb_alert_record — 告警触发记录,「告警中心」页消费。
详见 docs/observability-alert-design.md。

Revision ID: 0021_alert_rule
Revises: 0020_api_access_log
Create Date: 2026-05-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_alert_rule"
down_revision: str | Sequence[str] | None = "0020_api_access_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_alert_rule",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("target_error_type", sa.String(length=64), nullable=True),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("threshold_unit", sa.String(length=16), nullable=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("notify_channels", sa.Text(), nullable=False),
        sa.Column("message_template", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("trigger_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_triggered_at", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
    )
    op.create_index("idx_tb_alert_rule_enabled", "tb_alert_rule", ["enabled"])

    op.create_table(
        "tb_alert_record",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=True),
        sa.Column("app_name", sa.String(length=255), nullable=True),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("triggered_at", sa.BigInteger(), nullable=False),
        sa.Column("resolved_at", sa.BigInteger(), nullable=True),
        sa.Column("acknowledged_at", sa.BigInteger(), nullable=True),
        sa.Column("acknowledged_by", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
    )
    op.create_index("idx_tb_alert_record_status", "tb_alert_record", ["status", "triggered_at"])


def downgrade() -> None:
    op.drop_index("idx_tb_alert_record_status", table_name="tb_alert_record")
    op.drop_table("tb_alert_record")
    op.drop_index("idx_tb_alert_rule_enabled", table_name="tb_alert_rule")
    op.drop_table("tb_alert_rule")
