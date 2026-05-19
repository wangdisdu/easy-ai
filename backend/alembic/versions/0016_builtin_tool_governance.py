"""把 deepagents 框架内置写/执行类工具纳入 tb_tool 治理。

execute / write_file / edit_file 是 deepagents FilesystemMiddleware 注入的
框架工具,本系统不构造 tool 对象,只在 tb_tool 落一条 source='builtin' 的
治理记录,让 PolicyMiddleware 复用统一 ACL+HITL+审计(详见
docs/sandbox-design.md §5)。execute 默认 high(走 HITL),write_file /
edit_file 默认 medium。幂等:已存在同名 builtin 记录则跳过。

Revision ID: 0016_builtin_tool_governance
Revises: 0015_sandbox_image
Create Date: 2026-05-19 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_builtin_tool_governance"
down_revision: str | Sequence[str] | None = "0015_sandbox_image"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (tool_name, risk_level, description)
_BUILTIN_TOOLS = [
    ("execute", "high", "在隔离沙盒内执行 shell 命令(deepagents 框架内置)"),
    ("write_file", "medium", "新建文件(deepagents 框架内置)"),
    ("edit_file", "medium", "编辑已有文件(deepagents 框架内置)"),
]


def upgrade() -> None:
    from app.core.config import settings
    from app.core.snowflake import SnowflakeGenerator

    bind = op.get_bind()
    id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
    now_ms = bind.execute(
        sa.text("SELECT CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT)")
    ).scalar()

    for name, risk, desc in _BUILTIN_TOOLS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM tb_tool WHERE source = 'builtin' AND tool_name = :n"),
            {"n": name},
        ).scalar()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO tb_tool "
                "(id, source, tool_name, description, parameters, tool_group, "
                " risk_level, tool_status, create_time, update_time) "
                "VALUES (:id, 'builtin', :name, :desc, '{}', 'builtin', "
                " :risk, 'enabled', :ts, :ts)"
            ),
            {
                "id": id_gen.next_id(),
                "name": name,
                "desc": desc,
                "risk": risk,
                "ts": now_ms,
            },
        )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM tb_tool WHERE source = 'builtin' AND tool_name IN "
            "('execute', 'write_file', 'edit_file')"
        )
    )
