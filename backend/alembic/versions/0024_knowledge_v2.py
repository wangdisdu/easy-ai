"""知识库 v2: 组织层(知识库 / 分类 / 文档)与向量化层(RAG 库)解耦。

一次性推到 v2 终态。**不兼容 v1 数据,允许清库重建后再 upgrade**。

变更:
- 新表 ``tb_rag_dataset``: RAG 库, 持有 embedding / 分块配置(对应 RAGFlow Dataset)
- 新表 ``tb_kb_category_mapping``: 分类 → RAG 库(N:1, ``category_id`` 唯一互斥)
- 新表 ``tb_sync_log``: 知识集成 / 向量化 执行记录
- ``tb_kb``: 退化为纯组织层, 删 8 个 v1 向量化字段
  (ragflow_dataset_id / embedding_model / chunk_method / parser_config /
  doc_count / chunk_count / status / last_synced_at)
- ``tb_kb_document``: 增 ``storage_path`` / ``rag_dataset_id``,
  ``parse_status`` 改名 ``vectorize_status``, 删旧 ``category`` 字符串列

详见 ``docs/knowledge-v2-design.md``。

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

    # ── 新表: 分类 → RAG 库 映射 ──
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

    # ── tb_kb: 删除 8 个 v1 向量化遗留列(已迁至 tb_rag_dataset)──
    op.drop_column("tb_kb", "ragflow_dataset_id")
    op.drop_column("tb_kb", "embedding_model")
    op.drop_column("tb_kb", "chunk_method")
    op.drop_column("tb_kb", "parser_config")
    op.drop_column("tb_kb", "doc_count")
    op.drop_column("tb_kb", "chunk_count")
    op.drop_column("tb_kb", "status")
    op.drop_column("tb_kb", "last_synced_at")

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

    op.add_column("tb_kb", sa.Column("last_synced_at", sa.BigInteger(), nullable=True))
    op.add_column(
        "tb_kb",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
    )
    op.add_column(
        "tb_kb",
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tb_kb",
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("tb_kb", sa.Column("parser_config", sa.Text(), nullable=True))
    op.add_column("tb_kb", sa.Column("chunk_method", sa.String(length=64), nullable=True))
    op.add_column("tb_kb", sa.Column("embedding_model", sa.String(length=255), nullable=True))
    op.add_column("tb_kb", sa.Column("ragflow_dataset_id", sa.String(length=255), nullable=True))

    op.drop_index("ix_tb_sync_log_type_time", table_name="tb_sync_log")
    op.drop_table("tb_sync_log")
    op.drop_table("tb_kb_category_mapping")
    op.drop_table("tb_rag_dataset")
