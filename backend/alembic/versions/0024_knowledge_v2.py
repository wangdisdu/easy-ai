"""知识库 v2: RAG 库 / 分类映射 / 同步日志, 文档增 blob 与向量化状态。

知识库管理重构 —— 组织层(知识库/分类/文档)与向量化层(RAG 库)解耦,
easy-ai 成为文档真相源。详见 docs/knowledge-v2-design.md。

tb_kb 的向量化旧列(embedding_model / chunk_method / ragflow_dataset_id 等)
暂留, 待数据迁移脚本搬运到 tb_rag_dataset 后, 由后续 migration 删除。

Revision ID: 0024_knowledge_v2
Revises: 0023_app_metric_minute
Create Date: 2026-05-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_knowledge_v2"
down_revision: str | Sequence[str] | None = "0023_app_metric_minute"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 新表: RAG 库 ──
    op.create_table(
        "tb_rag_dataset",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ragflow_dataset_id", sa.String(length=255), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("chunk_method", sa.String(length=64), nullable=False),
        sa.Column("parser_config", sa.Text(), nullable=True),
        sa.Column("doc_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_synced_at", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tb_rag_dataset"),
    )

    # ── 新表: 分类 → RAG 库 映射(category_id 唯一保证互斥)──
    op.create_table(
        "tb_kb_category_mapping",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("rag_dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tb_kb_category_mapping"),
        sa.UniqueConstraint("category_id", name="uk_tb_kb_category_mapping_category"),
    )

    # ── 新表: 同步日志 ──
    op.create_table(
        "tb_sync_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("log_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("target_kb_id", sa.BigInteger(), nullable=True),
        sa.Column("target_dataset_id", sa.BigInteger(), nullable=True),
        sa.Column("docs_added", sa.Integer(), nullable=False),
        sa.Column("docs_updated", sa.Integer(), nullable=False),
        sa.Column("docs_deleted", sa.Integer(), nullable=False),
        sa.Column("chunks_created", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tb_sync_log"),
    )
    op.create_index("ix_tb_sync_log_type_time", "tb_sync_log", ["log_type", "create_time"])

    # ── tb_kb: 向量化旧列放宽为可空(暂留, 后续 migration 删除)──
    op.alter_column(
        "tb_kb",
        "embedding_model",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "tb_kb",
        "chunk_method",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    # ── tb_kb_document: 增 blob 与 RAG 库归属, parse_status 改名, 删旧分类列 ──
    op.add_column(
        "tb_kb_document",
        sa.Column("storage_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "tb_kb_document",
        sa.Column("rag_dataset_id", sa.BigInteger(), nullable=True),
    )
    op.alter_column(
        "tb_kb_document",
        "parse_status",
        new_column_name="vectorize_status",
        existing_type=sa.String(length=32),
    )
    op.drop_column("tb_kb_document", "category")


def downgrade() -> None:
    op.add_column(
        "tb_kb_document",
        sa.Column("category", sa.String(length=255), nullable=True),
    )
    op.alter_column(
        "tb_kb_document",
        "vectorize_status",
        new_column_name="parse_status",
        existing_type=sa.String(length=32),
    )
    op.drop_column("tb_kb_document", "rag_dataset_id")
    op.drop_column("tb_kb_document", "storage_path")

    op.alter_column(
        "tb_kb",
        "chunk_method",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "tb_kb",
        "embedding_model",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.drop_index("ix_tb_sync_log_type_time", table_name="tb_sync_log")
    op.drop_table("tb_sync_log")
    op.drop_table("tb_kb_category_mapping")
    op.drop_table("tb_rag_dataset")
