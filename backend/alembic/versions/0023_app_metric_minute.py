"""指标分钟级聚合表 tb_app_metric_minute。

从 tb_app_log 派生的预聚合指标时序,服务可观测性面板与告警溯源曲线。
详见 docs/observability-metrics-rollup-design.md。

Revision ID: 0023_app_metric_minute
Revises: 0022_seed_alert_rule
Create Date: 2026-05-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_app_metric_minute"
down_revision: str | Sequence[str] | None = "0022_seed_alert_rule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_app_metric_minute",
        sa.Column("bucket_start", sa.BigInteger(), nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("latency_count", sa.Integer(), nullable=False),
        sa.Column("latency_sum", sa.BigInteger(), nullable=False),
        sa.Column("latency_histogram", sa.Text(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_start", "app_id", name="pk_tb_app_metric_minute"),
    )


def downgrade() -> None:
    op.drop_table("tb_app_metric_minute")
