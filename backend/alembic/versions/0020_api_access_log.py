"""对外网关调用日志表 tb_api_access_log。

记录 /open/v1/* 每次调用的结果(成功 / 鉴权拒绝 / 限流拒绝 / 上游错误),
用于"调用日志"页面与限流拒绝分析。详见 docs/application-integration-design.md §14。

Revision ID: 0020_api_access_log
Revises: 0019_integration
Create Date: 2026-05-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_api_access_log"
down_revision: str | Sequence[str] | None = "0019_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_api_access_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        # 鉴权失败发生在解析集成之前时,下面四列可能为空
        sa.Column("integration_id", sa.BigInteger(), nullable=True),
        sa.Column("key_id", sa.BigInteger(), nullable=True),
        sa.Column("app_type", sa.String(length=32), nullable=True),
        sa.Column("app_id", sa.BigInteger(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        # 业务码:OK / API_KEY_INVALID / APP_NOT_BOUND / RATE_LIMITED / UPSTREAM_ERROR ...
        sa.Column("code", sa.String(length=64), nullable=False),
        # 限流细分:KEY_RPM / INTEGRATION_RPM / DAY_QUOTA;非限流为空
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("request_bytes", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "idx_tb_api_access_log_intg",
        "tb_api_access_log",
        ["integration_id", "create_time"],
    )


def downgrade() -> None:
    op.drop_index("idx_tb_api_access_log_intg", table_name="tb_api_access_log")
    op.drop_table("tb_api_access_log")
