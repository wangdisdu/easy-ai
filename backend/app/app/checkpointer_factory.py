from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Checkpoint 表统一放这个 schema，不与业务表混在 public schema。
_CHECKPOINT_SCHEMA = "lg_checkpoint"
_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 10


def _to_raw_conninfo(sqlalchemy_url: str) -> str:
    """把 SQLAlchemy 的 postgresql+psycopg:// 前缀剥掉，给 psycopg 用原生 postgresql://。"""
    prefix = "postgresql+psycopg://"
    if sqlalchemy_url.startswith(prefix):
        return "postgresql://" + sqlalchemy_url[len(prefix) :]
    return sqlalchemy_url


class CheckpointerFactory:
    """进程级单例。持有 AsyncConnectionPool + AsyncPostgresSaver。

    生命周期由 FastAPI lifespan 管理：start() 在启动时调一次，close() 在关闭时调。
    LangGraph 的 setup() 幂等，内部用 checkpoint_migrations 表做版本管理，
    这里每次 start 都会调一次，跨版本升级自动生效；schema 由 alembic 提前建好。
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._conninfo = _to_raw_conninfo(database_url or settings.database_url)
        self._pool: AsyncConnectionPool | None = None
        self._saver: AsyncPostgresSaver | None = None

    async def start(self) -> None:
        if self._saver is not None:
            return
        conn_kwargs: dict[str, Any] = {
            "autocommit": True,
            "prepare_threshold": 0,
            # 把连接的 search_path 固定到 checkpoint schema，saver 建表落在这里。
            "options": f"-c search_path={_CHECKPOINT_SCHEMA}",
        }
        self._pool = AsyncConnectionPool(
            conninfo=self._conninfo,
            min_size=_POOL_MIN_SIZE,
            max_size=_POOL_MAX_SIZE,
            kwargs=conn_kwargs,
            open=False,
        )
        await self._pool.open()
        self._saver = AsyncPostgresSaver(self._pool)
        await self._saver.setup()
        logger.info("checkpointer ready (schema=%s)", _CHECKPOINT_SCHEMA)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
        self._pool = None
        self._saver = None

    def get(self) -> AsyncPostgresSaver:
        if self._saver is None:
            raise RuntimeError(
                "CheckpointerFactory.start() has not been called; "
                "ensure the FastAPI lifespan initializes the checkpointer."
            )
        return self._saver


_factory: CheckpointerFactory | None = None


def get_checkpointer_factory() -> CheckpointerFactory:
    """进程级共享的 factory。第一次调用懒构造；lifespan 负责 start/close。"""
    global _factory
    if _factory is None:
        _factory = CheckpointerFactory()
    return _factory
