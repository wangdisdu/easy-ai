"""知识库 v2 收尾: 删除 tb_kb 的 v1 向量化遗留列。

删除列: ragflow_dataset_id / embedding_model / chunk_method / parser_config
/ doc_count / chunk_count / status / last_synced_at —— 它们已迁至 tb_rag_dataset。

⚠️ 部署顺序约束:本 migration **必须在 ``scripts/migrate_knowledge_v2.py``
数据迁移执行完毕后** 才能应用,因为该脚本要读取这些列把数据搬到 tb_rag_dataset。

正确流程(不要直接 ``alembic upgrade head`` 一步到位):
    uv run alembic upgrade 0024_knowledge_v2     # 只到 0024
    uv run python scripts/migrate_knowledge_v2.py # 数据迁移 + blob 回填
    uv run alembic upgrade head                   # 再应用 0025

Revision ID: 0025_drop_tb_kb_legacy_columns
Revises: 0024_knowledge_v2
Create Date: 2026-05-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_drop_tb_kb_legacy_columns"
down_revision: str | Sequence[str] | None = "0024_knowledge_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tb_kb", "ragflow_dataset_id")
    op.drop_column("tb_kb", "embedding_model")
    op.drop_column("tb_kb", "chunk_method")
    op.drop_column("tb_kb", "parser_config")
    op.drop_column("tb_kb", "doc_count")
    op.drop_column("tb_kb", "chunk_count")
    op.drop_column("tb_kb", "status")
    op.drop_column("tb_kb", "last_synced_at")


def downgrade() -> None:
    op.add_column("tb_kb", sa.Column("ragflow_dataset_id", sa.String(length=255), nullable=True))
    op.add_column("tb_kb", sa.Column("embedding_model", sa.String(length=255), nullable=True))
    op.add_column("tb_kb", sa.Column("chunk_method", sa.String(length=64), nullable=True))
    op.add_column("tb_kb", sa.Column("parser_config", sa.Text(), nullable=True))
    op.add_column(
        "tb_kb",
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tb_kb",
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tb_kb",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
    )
    op.add_column("tb_kb", sa.Column("last_synced_at", sa.BigInteger(), nullable=True))
