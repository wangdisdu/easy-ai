from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import Resp
from app.db.session import get_db
from app.model.observability_model import (
    AppHealthRow,
    ErrorAppRow,
    ModelTokenRow,
    OverviewStats,
    RecentRequestRow,
    TrendResp,
)
from app.service.observability_service import ObservabilityService

router = APIRouter(prefix="/observability", tags=["observability"])
service = ObservabilityService()


def _default_window(from_ms: int | None, to_ms: int | None) -> tuple[int, int]:
    """默认返回「今日 00:00 至当前」的毫秒区间。"""
    if to_ms is None:
        to_ms = int(time.time() * 1000)
    if from_ms is None:
        now = datetime.now()
        start = datetime(now.year, now.month, now.day)
        from_ms = int(start.timestamp() * 1000)
    return from_ms, to_ms


@router.get("/stats", response_model=Resp[OverviewStats])
def get_stats(
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> Resp[OverviewStats]:
    f, t = _default_window(from_ms, to_ms)
    return Resp(data=service.get_overview_stats(db, from_ms=f, to_ms=t))


@router.get("/trend", response_model=Resp[TrendResp])
def get_trend(
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    top: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_db),
) -> Resp[TrendResp]:
    f, t = _default_window(from_ms, to_ms)
    return Resp(data=service.get_trend(db, from_ms=f, to_ms=t, top=top))


@router.get("/tokens-by-model", response_model=Resp[list[ModelTokenRow]])
def get_tokens_by_model(
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> Resp[list[ModelTokenRow]]:
    f, t = _default_window(from_ms, to_ms)
    return Resp(data=service.get_tokens_by_model(db, from_ms=f, to_ms=t))


@router.get("/app-health", response_model=Resp[list[AppHealthRow]])
def get_app_health(
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    sort: str = Query(default="calls"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Resp[list[AppHealthRow]]:
    f, t = _default_window(from_ms, to_ms)
    return Resp(data=service.get_app_health(db, from_ms=f, to_ms=t, sort=sort, limit=limit))


@router.get("/errors-by-app", response_model=Resp[list[ErrorAppRow]])
def get_errors_by_app(
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Resp[list[ErrorAppRow]]:
    f, t = _default_window(from_ms, to_ms)
    return Resp(data=service.get_errors_by_app(db, from_ms=f, to_ms=t, limit=limit))


@router.get("/recent-requests", response_model=Resp[list[RecentRequestRow]])
def get_recent_requests(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Resp[list[RecentRequestRow]]:
    return Resp(data=service.get_recent_requests(db, limit=limit))
