"""默认沙盒镜像种子:easy-ai/sandbox-desktop:latest 作为 is_default,
让 ./deploy.sh up 后新环境直接可用,不必手动登 UI 建镜像。

镜像由 docker-compose 的 sandbox-desktop 服务在 sandbox profile 下本地构建
(`docker compose --profile sandbox build sandbox-desktop`)。

幂等:已存在同 image 引用则跳过。

Revision ID: 0018_seed_sandbox_image
Revises: 0017_computer_use_governance
Create Date: 2026-05-19 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_seed_sandbox_image"
down_revision: str | Sequence[str] | None = "0017_computer_use_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "桌面(可视化)"
_IMAGE = "easy-ai/sandbox-desktop:latest"
_DESC = "默认可视化沙盒镜像:Xvfb+Chromium+noVNC,支持中文,带 computer-use 工具"


def upgrade() -> None:
    from app.core.config import settings
    from app.core.snowflake import SnowflakeGenerator

    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM tb_sandbox_image WHERE image = :img"),
        {"img": _IMAGE},
    ).scalar()
    if exists:
        return

    id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
    now_ms = bind.execute(
        sa.text("SELECT CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT)")
    ).scalar()
    # 设为默认前先清掉其他默认(保证 is_default 全局唯一)
    bind.execute(sa.text("UPDATE tb_sandbox_image SET is_default = 0 WHERE is_default = 1"))
    bind.execute(
        sa.text(
            "INSERT INTO tb_sandbox_image "
            "(id, name, image, description, is_default, enabled, create_time, update_time) "
            "VALUES (:id, :name, :image, :desc, 1, 1, :ts, :ts)"
        ),
        {
            "id": id_gen.next_id(),
            "name": _NAME,
            "image": _IMAGE,
            "desc": _DESC,
            "ts": now_ms,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM tb_sandbox_image WHERE image = :img"),
        {"img": _IMAGE},
    )
