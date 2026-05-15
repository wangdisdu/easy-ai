"""knowledge base: tb_kb + tb_kb_document

每个 tb_kb 与 RAGFlow Dataset 1:1 映射。本地表只承载业务建模、权限与状态缓存,
真正的 parse / chunk / embed / retrieve 都在 RAGFlow。详见
docs/knowledge-rag-integration-design.md §4。

Revision ID: 0011_knowledge
Revises: 0010_category
Create Date: 2026-05-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_knowledge"
down_revision: str | Sequence[str] | None = "0010_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_kb",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # RAGFlow Dataset ID; 创建中或解绑后为空
        sa.Column("ragflow_dataset_id", sa.String(length=255), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("chunk_method", sa.String(length=64), nullable=False),
        sa.Column("parser_config", sa.Text(), nullable=True),
        # 缓存值, 后台 poller 定时回填
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        # draft / ready / syncing / error
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("last_synced_at", sa.BigInteger(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("code", name="uk_tb_kb_code"),
    )
    # 列表常用过滤
    op.create_index("ix_tb_kb_create_user", "tb_kb", ["create_user"])
    op.create_index("ix_tb_kb_status", "tb_kb", ["status"])

    op.create_table(
        "tb_kb_document",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kb_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        # file / ones / api_pull / api_push / confluence
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_meta", sa.Text(), nullable=True),
        sa.Column("ragflow_doc_id", sa.String(length=255), nullable=True),
        # pending / parsing / done / error / cancelled
        sa.Column(
            "parse_status", sa.String(length=32), nullable=False, server_default="pending"
        ),
        sa.Column("chunks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("kb_id", "name", name="uk_tb_kb_document_kb_name"),
    )
    # 后台 poller 扫 parsing/pending 用; 列表按 kb 过滤用
    op.create_index(
        "ix_tb_kb_document_parse_status", "tb_kb_document", ["parse_status"]
    )
    op.create_index("ix_tb_kb_document_kb_id", "tb_kb_document", ["kb_id"])


def downgrade() -> None:
    op.drop_index("ix_tb_kb_document_kb_id", table_name="tb_kb_document")
    op.drop_index("ix_tb_kb_document_parse_status", table_name="tb_kb_document")
    op.drop_table("tb_kb_document")
    op.drop_index("ix_tb_kb_status", table_name="tb_kb")
    op.drop_index("ix_tb_kb_create_user", table_name="tb_kb")
    op.drop_table("tb_kb")
