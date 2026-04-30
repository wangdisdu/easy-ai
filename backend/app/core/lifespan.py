from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.app.checkpoint_purger import CheckpointPurger
from app.app.checkpointer_factory import get_checkpointer_factory
from app.app.hitl_timeout_worker import HitlTimeoutWorker
from app.core.bootstrap import ensure_default_admin
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期：启动期初始化共享资源，关闭期释放。"""
    # 默认 admin 种子保留原行为。
    ensure_default_admin()

    factory = get_checkpointer_factory()
    await factory.start()

    purger: CheckpointPurger | None = None
    if settings.purge_enabled:
        purger = CheckpointPurger(
            interval_seconds=settings.purge_interval_seconds,
            ttl_days=settings.purge_ttl_days,
        )
        await purger.start()

    hitl_worker = HitlTimeoutWorker(
        interval_seconds=settings.hitl_timeout_check_interval_seconds,
        default_timeout_seconds=settings.hitl_timeout_seconds,
    )
    await hitl_worker.start()

    try:
        yield
    finally:
        await hitl_worker.stop()
        if purger is not None:
            await purger.stop()
        await factory.close()
        logger.info("checkpointer closed")
