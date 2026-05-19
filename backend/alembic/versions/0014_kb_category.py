"""知识库文档分类(树形, 单归属): tb_kb_category + tb_kb_document.category_id

纯 easy-ai 侧组织维度, RAGFlow 不感知。本次为 add-only 迁移:
- 建 tb_kb_category(parent_id/id_path/level 物化路径树)
- tb_kb_document 加 category_id(0=未分类)
- 把旧 category 字符串按 kb 维度去重 → 建根级分类 → 回填 category_id
- 旧 category 列保留(只读), 下个迭代单独迁移删除

详见 docs/knowledge-rag-integration-design.md。

Revision ID: 0014_kb_category
Revises: 0013_kb_doc_progress
Create Date: 2026-05-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_kb_category"
down_revision: str | Sequence[str] | None = "0013_kb_doc_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_kb_category",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kb_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        # 0 = 挂在知识库根下
        sa.Column("parent_id", sa.BigInteger(), nullable=False, server_default="0"),
        # 物化路径 /<id>/<id>/ 以自身结尾, 子树/级联用前缀匹配
        sa.Column("id_path", sa.String(length=1024), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "kb_id", "parent_id", "name", name="uk_tb_kb_category_sibling"
        ),
    )
    op.create_index("ix_tb_kb_category_kb_id", "tb_kb_category", ["kb_id"])
    op.create_index("ix_tb_kb_category_parent_id", "tb_kb_category", ["parent_id"])

    op.add_column(
        "tb_kb_document",
        sa.Column(
            "category_id", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "ix_tb_kb_document_category_id", "tb_kb_document", ["category_id"]
    )

    _migrate_legacy_categories()


def _migrate_legacy_categories() -> None:
    """旧 tb_kb_document.category 字符串 → 根级 tb_kb_category, 回填 category_id。

    同一 kb 内相同字符串合并为一个分类节点。空串 / NULL 保持 category_id=0。
    """
    from app.core.config import settings
    from app.core.snowflake import SnowflakeGenerator

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT DISTINCT kb_id, category FROM tb_kb_document "
            "WHERE category IS NOT NULL AND category <> ''"
        )
    ).fetchall()
    if not rows:
        return

    id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
    now_ms = bind.execute(
        sa.text("SELECT CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT)")
    ).scalar()

    for kb_id, category in rows:
        cid = id_gen.next_id()
        bind.execute(
            sa.text(
                "INSERT INTO tb_kb_category "
                "(id, kb_id, name, parent_id, id_path, level, sort, "
                " create_time, update_time) "
                "VALUES (:id, :kb_id, :name, 0, :id_path, 1, 0, :ts, :ts)"
            ),
            {
                "id": cid,
                "kb_id": kb_id,
                "name": category,
                "id_path": f"/{cid}/",
                "ts": now_ms,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE tb_kb_document SET category_id = :cid "
                "WHERE kb_id = :kb_id AND category = :name"
            ),
            {"cid": cid, "kb_id": kb_id, "name": category},
        )


def downgrade() -> None:
    op.drop_index("ix_tb_kb_document_category_id", table_name="tb_kb_document")
    op.drop_column("tb_kb_document", "category_id")
    op.drop_index("ix_tb_kb_category_parent_id", table_name="tb_kb_category")
    op.drop_index("ix_tb_kb_category_kb_id", table_name="tb_kb_category")
    op.drop_table("tb_kb_category")
