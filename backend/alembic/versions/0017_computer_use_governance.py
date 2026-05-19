"""把 computer-use 桌面操控工具纳入 tb_tool 治理(Tier 3)。

screenshot 只读=low(放行);click/type/key 等会改变桌面状态=high,走
§5 PolicyMiddleware HITL。与 0016 同样以 source='builtin' 种入,agent_app
的 _governed_builtin_metadata 自动覆盖。幂等:已存在同名 builtin 则跳过。

Revision ID: 0017_computer_use_governance
Revises: 0016_builtin_tool_governance
Create Date: 2026-05-19 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_computer_use_governance"
down_revision: str | Sequence[str] | None = "0016_builtin_tool_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (tool_name, risk_level, description)
_TOOLS = [
    ("screenshot", "low", "截取沙盒桌面画面(只读,computer-use)"),
    ("click", "high", "在桌面坐标单击(computer-use)"),
    ("double_click", "high", "在桌面坐标双击(computer-use)"),
    ("right_click", "high", "在桌面坐标右键(computer-use)"),
    ("move_mouse", "low", "移动鼠标不点击(computer-use)"),
    ("scroll", "high", "在桌面滚动(computer-use)"),
    ("type_text", "high", "在焦点处输入文本(computer-use)"),
    ("press_key", "high", "按键/组合键(computer-use)"),
]

_NAMES = "', '".join(t[0] for t in _TOOLS)


def upgrade() -> None:
    from app.core.config import settings
    from app.core.snowflake import SnowflakeGenerator

    bind = op.get_bind()
    id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
    now_ms = bind.execute(
        sa.text("SELECT CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT)")
    ).scalar()

    for name, risk, desc in _TOOLS:
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
                "VALUES (:id, 'builtin', :name, :desc, '{}', 'computer-use', "
                " :risk, 'enabled', :ts, :ts)"
            ),
            {"id": id_gen.next_id(), "name": name, "desc": desc, "risk": risk, "ts": now_ms},
        )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(f"DELETE FROM tb_tool WHERE source = 'builtin' AND tool_name IN ('{_NAMES}')")
    )
