"""app category: tb_app_category + tb_app_category_rel; migrate tb_skill.category

Revision ID: 0010_category
Revises: 0009_memory_kv
Create Date: 2026-05-11 00:00:00

"""

import time
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.config import settings
from app.core.snowflake import SnowflakeGenerator

revision: str = "0010_category"
down_revision: str | Sequence[str] | None = "0009_memory_kv"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tb_app_category",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("code", name="uk_tb_app_category_code"),
    )
    op.create_index("ix_tb_app_category_sort", "tb_app_category", ["sort_order"])

    op.create_table(
        "tb_app_category_rel",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("create_time", sa.BigInteger(), nullable=False),
        sa.Column("update_time", sa.BigInteger(), nullable=False),
        sa.Column("create_user", sa.BigInteger(), nullable=True),
        sa.Column("update_user", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "category_id", "target_type", "target_id", name="uk_tb_app_category_rel_uniq"
        ),
    )
    # 反向查询：按目标取分类
    op.create_index(
        "ix_tb_app_category_rel_target",
        "tb_app_category_rel",
        ["target_type", "target_id"],
    )
    # 正向查询：按分类筛 app / skill
    op.create_index(
        "ix_tb_app_category_rel_cat_type",
        "tb_app_category_rel",
        ["category_id", "target_type"],
    )

    # 迁移：tb_skill.category 自由字符串 → tb_app_category 分类 + tb_app_category_rel(target=skill)
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, category FROM tb_skill " "WHERE category IS NOT NULL AND category <> ''"
        )
    ).fetchall()
    if rows:
        gen = SnowflakeGenerator(settings.snowflake_worker_id)
        now_ms = int(time.time() * 1000)
        name_to_cid: dict[str, int] = {}
        for _skill_id, category_name in rows:
            if category_name not in name_to_cid:
                cid = gen.next_id()
                name_to_cid[category_name] = cid
                bind.execute(
                    sa.text(
                        "INSERT INTO tb_app_category "
                        "(id, code, name, sort_order, create_time, update_time) "
                        "VALUES (:id, :code, :name, 0, :ts, :ts)"
                    ),
                    {
                        "id": cid,
                        "code": category_name,
                        "name": category_name,
                        "ts": now_ms,
                    },
                )
        for skill_id, category_name in rows:
            bind.execute(
                sa.text(
                    "INSERT INTO tb_app_category_rel "
                    "(id, category_id, target_type, target_id, create_time, update_time) "
                    "VALUES (:id, :cid, 'skill', :tid, :ts, :ts)"
                ),
                {
                    "id": gen.next_id(),
                    "cid": name_to_cid[category_name],
                    "tid": skill_id,
                    "ts": now_ms,
                },
            )

    op.drop_column("tb_skill", "category")


def downgrade() -> None:
    op.add_column("tb_skill", sa.Column("category", sa.String(length=255), nullable=True))
    # 反向回填 skill 的旧字符串（每个 skill 只取一条分类名，多分类场景会丢精度，downgrade 仅做兜底）
    op.execute(
        "UPDATE tb_skill SET category = sub.name FROM ("
        "  SELECT r.target_id AS sid, c.name FROM tb_app_category_rel r "
        "  JOIN tb_app_category c ON c.id = r.category_id "
        "  WHERE r.target_type = 'skill'"
        ") sub WHERE tb_skill.id = sub.sid"
    )

    op.drop_index("ix_tb_app_category_rel_cat_type", table_name="tb_app_category_rel")
    op.drop_index("ix_tb_app_category_rel_target", table_name="tb_app_category_rel")
    op.drop_table("tb_app_category_rel")
    op.drop_index("ix_tb_app_category_sort", table_name="tb_app_category")
    op.drop_table("tb_app_category")
