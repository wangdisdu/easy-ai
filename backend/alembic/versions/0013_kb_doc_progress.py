"""tb_kb_document 加解析进度元数据:parse_progress / parse_begin_at /
parse_duration_sec / parse_progress_msg。

前端 parsing 状态行用这几个字段渲染百分比进度条 + 已耗时 + RAGFlow 当前阶段
提示;数据由 ``_sync_doc_status`` 从 RAGFlow 的 document.progress /
process_begin_at / process_duration / progress_msg 透传。

Revision ID: 0013_kb_doc_progress
Revises: 0012_system_setting
Create Date: 2026-05-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_kb_doc_progress"
down_revision: str | Sequence[str] | None = "0012_system_setting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tb_kb_document",
        sa.Column("parse_progress", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tb_kb_document",
        sa.Column("parse_begin_at", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "tb_kb_document",
        sa.Column("parse_duration_sec", sa.Float(), nullable=True),
    )
    op.add_column(
        "tb_kb_document",
        sa.Column("parse_progress_msg", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tb_kb_document", "parse_progress_msg")
    op.drop_column("tb_kb_document", "parse_duration_sec")
    op.drop_column("tb_kb_document", "parse_begin_at")
    op.drop_column("tb_kb_document", "parse_progress")
